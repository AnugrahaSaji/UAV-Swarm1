#!/usr/bin/env python3
"""
Full PQC Suite + AEAD + DDoS Detector Benchmark v3
====================================================
Phase 1: 24 handshake suites × 3 detector modes (Baseline, XGBoost, TST)
Phase 2: 9 AEADs × 3 detector modes with INA219 energy profiling

Key design:
  - 30-second cooldown between every algorithm/detector switch
  - Consistent run duration per algorithm (configurable, default 15s)
  - INA219 background-thread power sampling at ~1880 Hz (genuine TI sensor)
  - Cal=8192, Current_LSB=50µA, Power_LSB=1mW, VBUS_GAIN=1.0
  - Baseline subtraction via trapezoidal integration
  - Performance governor enforced on all cpu cores

Usage (on Raspberry Pi as root for scapy detector access):
    sudo ~/cenv/bin/python tools/full_bench_v3.py
    sudo ~/cenv/bin/python tools/full_bench_v3.py --duration 10 --cooldown 30
    sudo ~/cenv/bin/python tools/full_bench_v3.py --phase handshake-only
    sudo ~/cenv/bin/python tools/full_bench_v3.py --phase aead-only
"""

import argparse
import csv
import gc
import json
import os
import signal
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── OQS imports ───────────────────────────────────────────────────
def _init_oqs():
    for style in ["oqs.oqs", "oqs"]:
        try:
            mod = __import__(style, fromlist=["KeyEncapsulation", "Signature"])
            return mod.KeyEncapsulation, mod.Signature
        except (ImportError, AttributeError):
            continue
    raise ImportError("oqs-python not available")


KeyEncapsulation, Signature = _init_oqs()

from core.suites import list_suites, get_suite, negotiation_profiles_for_suite
from core.handshake import (
    build_server_hello,
    parse_and_verify_server_hello,
    client_encapsulate,
    server_decapsulate,
    derive_transport_keys,
)
from core.aead import _instantiate_aead
from core.config import CONFIG

# ── INA219 Constants (genuine TI) ─────────────────────────────────
INA219_ADDR = 0x40
INA219_BUS = 1
CAL_VALUE = 8192
CURRENT_LSB_A = 50e-6
POWER_LSB_W = 20 * CURRENT_LSB_A  # 1 mW
VBUS_GAIN = 1.0
INA219_CONFIG = 0x399F  # 32V, /8, 12-bit, continuous

# Detector scripts
DDOS_DIR = ROOT / "ddos"
XGB_SCRIPT = DDOS_DIR / "xgb_old.py"
TST_SCRIPT = DDOS_DIR / "tst_old.py"
DETECTOR_PYTHON = os.environ.get(
    "DETECTOR_PYTHON", "/home/dev/nenv/bin/python")
if not os.path.isfile(DETECTOR_PYTHON):
    DETECTOR_PYTHON = sys.executable

# Defaults
DEFAULT_DURATION = 15  # seconds per suite/aead test
DEFAULT_COOLDOWN = 30  # seconds between tests
TST_WARMUP_S = 30      # TST warmup before benchmarking


# =====================================================================
# INA219 Direct (genuine TI — hardware power register)
# =====================================================================

class INA219Direct:
    """Direct smbus2 access to genuine TI INA219 at ~1880 Hz."""

    REG_CONFIG = 0x00
    REG_SHUNT = 0x01
    REG_BUS = 0x02
    REG_POWER = 0x03
    REG_CURRENT = 0x04
    REG_CAL = 0x05

    def __init__(self, bus_num=INA219_BUS, addr=INA219_ADDR):
        import smbus2
        self.bus = smbus2.SMBus(bus_num)
        self.addr = addr
        self._lock = threading.Lock()
        # BCM2835 wakeup
        try:
            self.bus.read_byte_data(addr, 0x00)
        except OSError:
            pass
        time.sleep(0.01)
        # Write config and calibration
        self._write_be(self.REG_CONFIG, INA219_CONFIG)
        self._write_be(self.REG_CAL, CAL_VALUE)
        time.sleep(0.01)
        # Verify calibration
        cal_back = self._read_be(self.REG_CAL)
        if cal_back != CAL_VALUE:
            print(f"  WARNING: Cal readback {cal_back} != {CAL_VALUE}")
        else:
            print(f"  INA219 Cal verified: {cal_back}")

    def _read_be(self, reg):
        with self._lock:
            for _ in range(3):
                try:
                    w = self.bus.read_word_data(self.addr, reg)
                    return ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
                except OSError:
                    time.sleep(0.001)
            return 0

    def _write_be(self, reg, value):
        swapped = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)
        with self._lock:
            for _ in range(3):
                try:
                    self.bus.write_word_data(self.addr, reg, swapped)
                    return
                except OSError:
                    time.sleep(0.001)

    def read_power_w(self):
        raw = self._read_be(self.REG_POWER)
        return raw * POWER_LSB_W

    def read_bus_voltage_v(self):
        raw = self._read_be(self.REG_BUS)
        return ((raw >> 3) & 0x1FFF) * 0.004 * VBUS_GAIN

    def read_current_a(self):
        raw = self._read_be(self.REG_CURRENT)
        if raw & 0x8000:
            raw -= 1 << 16
        return raw * CURRENT_LSB_A

    def read_all(self):
        p = self.read_power_w()
        c = self.read_current_a()
        v = self.read_bus_voltage_v()
        return p, c, v

    def close(self):
        self.bus.close()


# =====================================================================
# Power Tracer (background thread)
# =====================================================================

class PowerTracer:
    """Background-thread power capture at maximum INA219 rate."""

    def __init__(self, ina: INA219Direct):
        self.ina = ina
        self._trace: List[Tuple[float, float]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        self._trace = []
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> List[Tuple[float, float]]:
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        return list(self._trace)

    def _loop(self):
        t0 = time.perf_counter()
        while self._running:
            try:
                pw = self.ina.read_power_w()
                self._trace.append((time.perf_counter() - t0, pw))
            except OSError:
                pass


def measure_baseline(tracer: PowerTracer, duration: float = 3.0) -> float:
    """Measure idle baseline power."""
    tracer.start()
    time.sleep(duration)
    trace = tracer.stop()
    if not trace:
        return 3.12  # fallback
    return statistics.mean([p for _, p in trace])


def integrate_energy(trace, baseline_w):
    """Trapezoidal integration with baseline subtraction."""
    if len(trace) < 2:
        return 0.0, 0.0
    total_gross = 0.0
    total_net = 0.0
    for i in range(1, len(trace)):
        dt = trace[i][0] - trace[i-1][0]
        p_avg = (trace[i][1] + trace[i-1][1]) / 2.0
        total_gross += p_avg * dt
        total_net += max(0, p_avg - baseline_w) * dt
    return total_gross, total_net


# =====================================================================
# CPU Sampler (threaded)
# =====================================================================

class CpuSampler:
    def __init__(self, interval=0.5):
        self._interval = interval
        self._samples = []
        self._running = False
        self._thread = None

    def start(self):
        self._samples = []
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if not self._samples:
            return 0.0, 0.0
        return statistics.mean(self._samples), max(self._samples)

    def _loop(self):
        prev_idle, prev_total = self._read_stat()
        while self._running:
            time.sleep(self._interval)
            idle, total = self._read_stat()
            d_idle = idle - prev_idle
            d_total = total - prev_total
            if d_total > 0:
                self._samples.append((1.0 - d_idle / d_total) * 100.0)
            prev_idle, prev_total = idle, total

    @staticmethod
    def _read_stat():
        try:
            with open("/proc/stat") as f:
                parts = f.readline().split()
            return int(parts[4]), sum(int(p) for p in parts[1:])
        except Exception:
            return 0, 1


# =====================================================================
# System helpers
# =====================================================================

def read_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return 0.0


def set_performance_governor():
    try:
        for cpu_dir in sorted(Path("/sys/devices/system/cpu/").glob("cpu[0-9]*")):
            gov = cpu_dir / "cpufreq" / "scaling_governor"
            if gov.exists():
                try:
                    gov.write_text("performance\n")
                except PermissionError:
                    subprocess.run(f"echo performance | sudo tee {gov}",
                                   shell=True, capture_output=True)
    except Exception:
        pass
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") as f:
            return f.read().strip()
    except Exception:
        return "unknown"


def cooldown(seconds, label="Cooldown"):
    """Wait with temperature monitoring."""
    print(f"  {label}: {seconds}s ", end="", flush=True)
    for i in range(seconds):
        if i % 10 == 0 and i > 0:
            t = read_temp()
            print(f"[{t:.0f}°C] ", end="", flush=True)
        time.sleep(1)
    print(f"done ({read_temp():.0f}°C)")


# =====================================================================
# Detector management
# =====================================================================

def start_detector(script: Path, label: str) -> Optional[subprocess.Popen]:
    print(f"  Starting {label} ({script.name}) ...", end="", flush=True)
    err_path = Path(f"/tmp/detector_{label.lower()}.err")
    err_fh = open(err_path, "w")
    # Use sudo for scapy raw socket access; main script runs as dev user
    cmd = ["sudo", DETECTOR_PYTHON, "-u", str(script)] if os.getuid() != 0 \
        else [DETECTOR_PYTHON, "-u", str(script)]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=err_fh,
        preexec_fn=os.setpgrp if hasattr(os, "setpgrp") else None,
    )
    time.sleep(2)
    err_fh.flush()
    if proc.poll() is not None:
        err_fh.close()
        err_text = err_path.read_text().strip()
        print(f" FAILED (exit {proc.returncode})")
        if err_text:
            for line in err_text.splitlines()[-5:]:
                print(f"    {line}")
        return None
    print(f" PID {proc.pid}")
    return proc


def stop_detector(proc: Optional[subprocess.Popen], label: str):
    if proc is None:
        return
    script_map = {"xgboost": "xgb_old.py", "tst": "tst_old.py"}
    script_name = script_map.get(label.lower(), label.lower())
    print(f"  Stopping {label} (PID {proc.pid})...", end="", flush=True)
    try:
        subprocess.run(["sudo", "pkill", "-f", script_name],
                       capture_output=True, timeout=5)
    except Exception:
        pass
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        try:
            proc.wait(timeout=3)
        except Exception:
            pass
    print(" done")


# =====================================================================
# Handshake result
# =====================================================================

@dataclass
class HandshakeResult:
    suite_id: str
    key_handshake_id: str
    key_handshake: str
    suite_data_aead_id: str
    suite_data_aead: str
    handshake_runtime_aead: str
    kem: str
    sig: str
    aead: str
    nist_level: str
    detector: str
    duration_s: float
    iterations: int
    # Timing (ms)
    mean_ms: float = 0.0
    median_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    stdev_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    throughput_hz: float = 0.0
    # Power (INA219)
    baseline_power_w: float = 0.0
    avg_gross_power_w: float = 0.0
    avg_net_power_w: float = 0.0
    total_net_energy_j: float = 0.0
    per_hs_energy_uj: float = 0.0
    power_samples: int = 0
    sample_rate_hz: float = 0.0
    # System
    cpu_avg: float = 0.0
    cpu_peak: float = 0.0
    temp_c: float = 0.0
    error: Optional[str] = None


def _load_benchmark_drone_psk() -> bytes:
    psk_hex = os.getenv("DRONE_PSK", CONFIG.get("DRONE_PSK", ""))
    try:
        psk = bytes.fromhex(psk_hex)
    except ValueError as exc:
        raise ValueError(f"Invalid DRONE_PSK hex: {exc}") from exc
    if len(psk) != 32:
        raise ValueError("DRONE_PSK must decode to exactly 32 bytes for handshake key derivation")
    return psk


# =====================================================================
# Phase 1: Handshake benchmarks
# =====================================================================

def benchmark_handshake(suite_id: str, duration_s: float,
                        tracer: PowerTracer, baseline_w: float,
                        detector_label: str) -> HandshakeResult:
    """Run handshake loop for duration_s with INA219 power tracing."""
    suite_cfg = get_suite(suite_id)
    profiles = negotiation_profiles_for_suite(suite_cfg)
    sig_name = suite_cfg["sig_name"]

    try:
        psk = _load_benchmark_drone_psk()
    except ValueError as exc:
        return HandshakeResult(
            suite_id=profiles.get("key_handshake_id", suite_id),
            key_handshake_id=profiles.get("key_handshake_id", ""),
            key_handshake=profiles.get("key_handshake", ""),
            suite_data_aead_id=profiles.get("data_aead_id", ""),
            suite_data_aead=profiles.get("data_aead", ""),
            handshake_runtime_aead="none (handshake-only)",
            kem=suite_cfg.get("kem_name", ""),
            sig=suite_cfg.get("sig_name", ""),
            aead=f"{profiles.get('data_aead', '')} (suite metadata only)",
            nist_level=suite_cfg.get("nist_level", ""),
            detector=detector_label,
            duration_s=0.0,
            iterations=0,
            error=str(exc),
        )

    gcs_sig = Signature(sig_name)
    gcs_sig_pub = gcs_sig.generate_keypair()

    times_ms = []
    failures = 0
    last_error = ""
    cpu_sampler = CpuSampler(interval=0.5)
    cpu_sampler.start()

    gc.collect()
    gc.disable()

    tracer.start()
    t_start = time.monotonic()

    while time.monotonic() - t_start < duration_s:
        t0 = time.perf_counter_ns()
        try:
            hello_wire, eph = build_server_hello(suite_id, gcs_sig)
            hello = parse_and_verify_server_hello(
                hello_wire, CONFIG["WIRE_VERSION"], gcs_sig_pub)
            kem_ct, drone_shared = client_encapsulate(hello)
            gcs_shared = server_decapsulate(eph, kem_ct)
            derive_transport_keys(
                "client",
                hello.session_id,
                hello.challenge,
                hello.kem_name,
                hello.sig_name,
                drone_shared,
                psk,
            )
            derive_transport_keys(
                "server",
                eph.session_id,
                eph.challenge,
                eph.kem_name.encode(),
                eph.sig_name.encode(),
                gcs_shared,
                psk,
            )
        except Exception as exc:
            failures += 1
            last_error = f"{type(exc).__name__}: {exc}"
            continue
        t1 = time.perf_counter_ns()
        times_ms.append((t1 - t0) / 1_000_000)

    trace = tracer.stop()
    gc.enable()
    elapsed = time.monotonic() - t_start
    cpu_avg, cpu_peak = cpu_sampler.stop()
    gcs_sig.free()

    if not times_ms:
        return HandshakeResult(
            suite_id=profiles.get("key_handshake_id", suite_id),
            key_handshake_id=profiles.get("key_handshake_id", ""),
            key_handshake=profiles.get("key_handshake", ""),
            suite_data_aead_id=profiles.get("data_aead_id", ""),
            suite_data_aead=profiles.get("data_aead", ""),
            handshake_runtime_aead="none (handshake-only)",
            kem=suite_cfg.get("kem_name", ""),
            sig=suite_cfg.get("sig_name", ""),
            aead=f"{profiles.get('data_aead', '')} (suite metadata only)",
            nist_level=suite_cfg.get("nist_level", ""),
            detector=detector_label, duration_s=elapsed, iterations=0,
            error=(
                f"No successful handshakes; failures={failures}"
                + (f"; last_error={last_error}" if last_error else "")
            ),
        )

    sorted_t = sorted(times_ms)
    n = len(sorted_t)

    # Power integration
    total_gross, total_net = integrate_energy(trace, baseline_w)
    avg_gross = statistics.mean([p for _, p in trace]) if trace else 0
    sample_rate = len(trace) / elapsed if elapsed > 0 else 0
    per_hs_energy = (total_net / n) * 1e6 if n > 0 else 0  # µJ

    return HandshakeResult(
        suite_id=profiles.get("key_handshake_id", suite_id),
        key_handshake_id=profiles.get("key_handshake_id", ""),
        key_handshake=profiles.get("key_handshake", ""),
        suite_data_aead_id=profiles.get("data_aead_id", ""),
        suite_data_aead=profiles.get("data_aead", ""),
        handshake_runtime_aead="none (handshake-only)",
        kem=suite_cfg.get("kem_name", ""),
        sig=suite_cfg.get("sig_name", ""),
        aead=f"{profiles.get('data_aead', '')} (suite metadata only)",
        nist_level=suite_cfg.get("nist_level", ""),
        detector=detector_label,
        duration_s=round(elapsed, 2),
        iterations=n,
        mean_ms=round(statistics.mean(sorted_t), 3),
        median_ms=round(sorted_t[n // 2], 3),
        p95_ms=round(sorted_t[int(n * 0.95)], 3),
        p99_ms=round(sorted_t[int(n * 0.99)], 3),
        stdev_ms=round(statistics.stdev(sorted_t), 3) if n > 1 else 0,
        min_ms=round(sorted_t[0], 3),
        max_ms=round(sorted_t[-1], 3),
        throughput_hz=round(n / elapsed, 2),
        baseline_power_w=round(baseline_w, 4),
        avg_gross_power_w=round(avg_gross, 4),
        avg_net_power_w=round(avg_gross - baseline_w, 4),
        total_net_energy_j=round(total_net, 6),
        per_hs_energy_uj=round(per_hs_energy, 2),
        power_samples=len(trace),
        sample_rate_hz=round(sample_rate, 0),
        cpu_avg=round(cpu_avg, 1),
        cpu_peak=round(cpu_peak, 1),
        temp_c=read_temp(),
    )


# =====================================================================
# Phase 2: AEAD benchmarks with INA219
# =====================================================================

@dataclass
class AeadResult:
    aead_name: str
    key_tier: str  # "128", "192", "256"
    operation: str  # "encrypt" or "decrypt"
    detector: str
    payload_size: int
    iterations: int
    duration_s: float
    # Timing
    mean_us: float = 0.0
    median_us: float = 0.0
    throughput_ops: float = 0.0
    # Power
    baseline_power_w: float = 0.0
    avg_gross_power_w: float = 0.0
    avg_net_power_w: float = 0.0
    total_net_energy_j: float = 0.0
    per_op_energy_uj: float = 0.0
    power_samples: int = 0
    sample_rate_hz: float = 0.0
    # System
    cpu_avg: float = 0.0
    cpu_peak: float = 0.0
    temp_c: float = 0.0
    error: Optional[str] = None


# AEAD definitions for all tiers
# The Pi supports: aesgcm, chacha20poly1305, ascon128 via core/aead.py
# Additional AES-GCM/CCM key sizes via cryptography library directly
AEAD_DEFS = [
    # (name, alias, key_bits, tier)
    ("AES-128-GCM", "A1", 128, "L1"),
    ("AES-128-CCM", "C1", 128, "L1"),
    ("Ascon-128", "AS", 128, "L1"),
    ("AES-192-GCM", "A9", 192, "L3"),
    ("AES-192-CCM", "C9", 192, "L3"),
    ("ChaCha20-Poly1305", "CC", 256, "L5"),
    ("AES-256-GCM", "AG", 256, "L5"),
    ("AES-256-CCM", "C6", 256, "L5"),
    ("AES-GCM-256(tunnel)", "TN", 256, "L5"),  # The actual tunnel AEAD via core
]


def _make_aead_cipher(name, key_bits):
    """Create an AEAD cipher instance for benchmarking."""
    from cryptography.hazmat.primitives.ciphers.aead import (
        AESGCM, AESCCM, ChaCha20Poly1305,
    )

    key = os.urandom(key_bits // 8)

    if name == "AES-GCM-256(tunnel)":
        # Use the actual tunnel AEAD from core
        cipher = AESGCM(key[:32] if len(key) >= 32 else os.urandom(32))
        return cipher, 12, "aesgcm-tunnel"
    elif "GCM" in name:
        cipher = AESGCM(key)
        nonce_len = 12
        return cipher, nonce_len, "gcm"
    elif "CCM" in name:
        cipher = AESCCM(key, tag_length=16)
        nonce_len = 13
        return cipher, nonce_len, "ccm"
    elif "ChaCha20" in name:
        cipher = ChaCha20Poly1305(key)
        nonce_len = 12
        return cipher, nonce_len, "chacha"
    elif "Ascon" in name:
        try:
            class AsconWrap:
                def __init__(self, key_material: bytes):
                    # Force native C backend through core.aead.
                    self._cipher, self._nonce_len = _instantiate_aead("ascon128", key_material)

                def encrypt(self, nonce, pt, aad):
                    return self._cipher.encrypt(nonce, pt, aad)

                def decrypt(self, nonce, ct, aad):
                    return self._cipher.decrypt(nonce, ct, aad)

            return AsconWrap(key), 16, "ascon_native"
        except Exception as exc:
            return None, 0, f"ascon_native_unavailable: {exc}"
    else:
        raise ValueError(f"Unknown AEAD: {name}")


def benchmark_aead(aead_name: str, alias: str, key_bits: int, tier: str,
                   payload_size: int, duration_s: float,
                   tracer: PowerTracer, baseline_w: float,
                   detector_label: str) -> List[AeadResult]:
    """Benchmark one AEAD (encrypt + decrypt) for duration_s."""
    results = []

    try:
        cipher, nonce_len, kind = _make_aead_cipher(aead_name, key_bits)
    except Exception as e:
        for op in ["encrypt", "decrypt"]:
            results.append(AeadResult(
                aead_name=aead_name, key_tier=tier, operation=op,
                detector=detector_label, payload_size=payload_size,
                iterations=0, duration_s=0, error=str(e)))
        return results

    if cipher is None:
        for op in ["encrypt", "decrypt"]:
            results.append(AeadResult(
                aead_name=aead_name, key_tier=tier, operation=op,
                detector=detector_label, payload_size=payload_size,
                iterations=0, duration_s=0, error=kind))
        return results

    plaintext = os.urandom(payload_size)
    aad = os.urandom(22)  # 22-byte header AAD

    for op in ["encrypt", "decrypt"]:
        # Prepare ciphertext for decrypt test
        nonce = os.urandom(nonce_len)
        ciphertext = cipher.encrypt(nonce, plaintext, aad)

        # Warmup
        for _ in range(50):
            n = os.urandom(nonce_len)
            if op == "encrypt":
                cipher.encrypt(n, plaintext, aad)
            else:
                cipher.decrypt(nonce, ciphertext, aad)

        times_us = []
        cpu_sampler = CpuSampler(interval=0.5)
        cpu_sampler.start()

        gc.collect()
        gc.disable()
        tracer.start()
        t_start = time.monotonic()

        while time.monotonic() - t_start < duration_s:
            n = os.urandom(nonce_len)
            t0 = time.perf_counter_ns()
            if op == "encrypt":
                cipher.encrypt(n, plaintext, aad)
            else:
                cipher.decrypt(nonce, ciphertext, aad)
            t1 = time.perf_counter_ns()
            times_us.append((t1 - t0) / 1000.0)

        trace = tracer.stop()
        gc.enable()
        elapsed = time.monotonic() - t_start
        cpu_avg, cpu_peak = cpu_sampler.stop()

        n_ops = len(times_us)
        total_gross, total_net = integrate_energy(trace, baseline_w)
        avg_gross = statistics.mean([p for _, p in trace]) if trace else 0
        sample_rate = len(trace) / elapsed if elapsed > 0 else 0
        per_op_uj = (total_net / n_ops) * 1e6 if n_ops > 0 else 0

        results.append(AeadResult(
            aead_name=aead_name,
            key_tier=tier,
            operation=op,
            detector=detector_label,
            payload_size=payload_size,
            iterations=n_ops,
            duration_s=round(elapsed, 2),
            mean_us=round(statistics.mean(times_us), 3) if times_us else 0,
            median_us=round(sorted(times_us)[len(times_us)//2], 3) if times_us else 0,
            throughput_ops=round(n_ops / elapsed, 1) if elapsed > 0 else 0,
            baseline_power_w=round(baseline_w, 4),
            avg_gross_power_w=round(avg_gross, 4),
            avg_net_power_w=round(avg_gross - baseline_w, 4),
            total_net_energy_j=round(total_net, 6),
            per_op_energy_uj=round(per_op_uj, 3),
            power_samples=len(trace),
            sample_rate_hz=round(sample_rate, 0),
            cpu_avg=round(cpu_avg, 1),
            cpu_peak=round(cpu_peak, 1),
            temp_c=read_temp(),
        ))

    return results


# =====================================================================
# Phase Runners
# =====================================================================

def run_handshake_phase(suites: List[str], duration: float, cooldown_s: int,
                        ina: INA219Direct, detector_label: str,
                        out_dir: Path) -> List[Dict]:
    """Run one representative suite per key-handshake profile."""
    _load_benchmark_drone_psk()

    print(f"\n{'=' * 78}")
    print(f"  HANDSHAKE PHASE: {detector_label}")
    print(f"  Suites: {len(suites)} | Duration/suite: {duration}s | Cooldown: {cooldown_s}s")
    print(f"  Estimated: {len(suites) * (duration + cooldown_s) / 60:.1f} min")
    print(f"{'=' * 78}\n")

    tracer = PowerTracer(ina)
    results = []

    for i, sid in enumerate(suites, 1):
        # Measure fresh baseline before each suite
        suite_cfg = get_suite(sid)
        profiles = negotiation_profiles_for_suite(suite_cfg)
        print(
            f"  [{i:2d}/{len(suites)}] {profiles.get('key_handshake_id', sid)}"
            f" (data-plane-profile={profiles.get('data_aead_id', 'unknown')}, not executed)"
        )
        baseline_w = measure_baseline(tracer, 2.0)
        print(f"    Baseline: {baseline_w:.3f} W | Temp: {read_temp():.0f}°C")

        r = benchmark_handshake(sid, duration, tracer, baseline_w, detector_label)
        results.append(asdict(r))

        if r.error:
            print(f"    ERROR: {r.error}")
        else:
            print(f"    {r.mean_ms:8.2f} ms | {r.iterations:5d} it | "
                  f"Net {r.avg_net_power_w:.3f} W | {r.per_hs_energy_uj:.0f} µJ/HS | "
                  f"CPU {r.cpu_avg:.0f}% | {r.temp_c:.0f}°C | "
                  f"{r.power_samples} samples @ {r.sample_rate_hz:.0f} Hz")

        if i < len(suites):
            cooldown(cooldown_s, f"    Cooldown")

    # Save results
    out_file = out_dir / f"handshake_{detector_label.lower()}.json"
    payload = {
        "phase": f"handshake_{detector_label}",
        "detector": detector_label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "suites": len(suites),
        "duration_per_suite_s": duration,
        "cooldown_s": cooldown_s,
        "results": results,
    }
    out_file.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  Saved → {out_file}")
    return results


def run_aead_phase(duration: float, cooldown_s: int, payload_size: int,
                   ina: INA219Direct, detector_label: str,
                   out_dir: Path) -> List[Dict]:
    """Run all 9 AEADs under one detector mode."""
    print(f"\n{'=' * 78}")
    print(f"  AEAD PHASE: {detector_label}")
    print(f"  AEADs: {len(AEAD_DEFS)} | Duration/aead: {duration}s | "
          f"Payload: {payload_size}B | Cooldown: {cooldown_s}s")
    print(f"  Estimated: {len(AEAD_DEFS) * (duration * 2 + cooldown_s) / 60:.1f} min")
    print(f"{'=' * 78}\n")

    tracer = PowerTracer(ina)
    all_results = []

    for i, (name, alias, key_bits, tier) in enumerate(AEAD_DEFS, 1):
        print(f"  [{i:d}/{len(AEAD_DEFS)}] {name} ({alias}, {key_bits}-bit, tier {tier})")
        baseline_w = measure_baseline(tracer, 2.0)
        print(f"    Baseline: {baseline_w:.3f} W | Temp: {read_temp():.0f}°C")

        results = benchmark_aead(name, alias, key_bits, tier,
                                  payload_size, duration,
                                  tracer, baseline_w, detector_label)

        for r in results:
            all_results.append(asdict(r))
            if r.error:
                print(f"    {r.operation}: ERROR {r.error}")
            else:
                print(f"    {r.operation}: {r.mean_us:8.2f} µs | {r.iterations:7d} ops | "
                      f"Net {r.avg_net_power_w:.3f} W | {r.per_op_energy_uj:.3f} µJ/op | "
                      f"CPU {r.cpu_avg:.0f}% | {r.temp_c:.0f}°C")

        if i < len(AEAD_DEFS):
            cooldown(cooldown_s, f"    Cooldown")

    out_file = out_dir / f"aead_{detector_label.lower()}.json"
    payload = {
        "phase": f"aead_{detector_label}",
        "detector": detector_label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "aeads": len(AEAD_DEFS),
        "duration_per_aead_s": duration,
        "payload_size": payload_size,
        "cooldown_s": cooldown_s,
        "results": all_results,
    }
    out_file.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  Saved → {out_file}")
    return all_results


# =====================================================================
# CSV export
# =====================================================================

def export_handshake_csv(all_results: List[Dict], out_dir: Path):
    """Merge all handshake results into a single CSV."""
    out_file = out_dir / "handshake_summary.csv"
    if not all_results:
        return
    keys = list(all_results[0].keys())
    with open(out_file, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(all_results)
    print(f"  Handshake CSV → {out_file}")


def export_aead_csv(all_results: List[Dict], out_dir: Path):
    """Merge all AEAD results into a single CSV."""
    out_file = out_dir / "aead_summary.csv"
    if not all_results:
        return
    keys = list(all_results[0].keys())
    with open(out_file, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(all_results)
    print(f"  AEAD CSV → {out_file}")


# =====================================================================
# Main
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Full PQC Suite + AEAD + DDoS Benchmark v3")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION,
                        help=f"Seconds per test (default: {DEFAULT_DURATION})")
    parser.add_argument("--cooldown", type=int, default=DEFAULT_COOLDOWN,
                        help=f"Cooldown seconds between tests (default: {DEFAULT_COOLDOWN})")
    parser.add_argument("--payload", type=int, default=256,
                        help="AEAD payload size in bytes (default: 256)")
    parser.add_argument("--phase", choices=["all", "handshake-only", "aead-only"],
                        default="all", help="Which phases to run")
    parser.add_argument("--skip-mceliece", action="store_true",
                        help="Skip Classic McEliece suites (slow keygen)")
    parser.add_argument("--tst-warmup", type=int, default=TST_WARMUP_S,
                        help=f"TST warmup seconds (default: {TST_WARMUP_S})")
    parser.add_argument("--resume-from", choices=["baseline", "xgboost", "tst"],
                        default=None,
                        help="Resume from a specific detector phase")
    parser.add_argument("--results-dir", type=str, default=None,
                        help="Existing results directory to resume into")
    args = parser.parse_args()

    # ── Setup ─────────────────────────────────────────────────────────
    print(f"\n{'=' * 70}")
    print(f"  FULL PQC BENCHMARK v3")
    print(f"{'=' * 70}")

    governor = set_performance_governor()
    print(f"  Governor : {governor}")
    print(f"  Temp     : {read_temp():.1f}°C")

    # Init INA219
    print(f"  Initialising INA219...")
    ina = INA219Direct()
    p, c, v = ina.read_all()
    print(f"  Quick read: {v:.3f}V, {c*1000:.1f}mA, {p:.3f}W")

    # Measure sustained rate
    tracer = PowerTracer(ina)
    tracer.start()
    time.sleep(1.0)
    trace = tracer.stop()
    rate = len(trace)
    print(f"  Sustained rate: {rate} Hz")

    # Discover one representative suite per key-handshake profile.
    # Handshake-only benchmarking does not execute data-plane AEAD.
    all_suites_map = list_suites()
    grouped: Dict[str, List[str]] = {}
    for suite_id, suite_cfg in all_suites_map.items():
        key_handshake_id = str(suite_cfg.get("key_handshake_id") or "")
        if not key_handshake_id:
            continue
        if args.skip_mceliece and "classicmceliece" in suite_id:
            continue
        grouped.setdefault(key_handshake_id, []).append(suite_id)

    def _suite_pref(sid: str) -> Tuple[int, str]:
        # Prefer AES-GCM as deterministic wire-level representative when available.
        return (0 if "-aesgcm-" in sid else 1, sid)

    handshake_suites = [
        sorted(candidates, key=_suite_pref)[0]
        for _, candidates in sorted(grouped.items(), key=lambda kv: kv[0])
    ]

    handshake_profile_ids = [
        str(all_suites_map[suite_id].get("key_handshake_id") or suite_id)
        for suite_id in handshake_suites
    ]
    if args.skip_mceliece:
        print(f"  Skipping McEliece: {len(handshake_suites)} handshake profiles remaining")

    # Output directory
    if args.results_dir:
        out_dir = Path(args.results_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = ROOT / "bench_results_v3" / ts
        out_dir.mkdir(parents=True, exist_ok=True)

    # Verify detector scripts
    for script, label in [(XGB_SCRIPT, "XGBoost"), (TST_SCRIPT, "TST")]:
        if not script.exists():
            print(f"  WARNING: {label} script not found at {script}")

    # Estimate total time
    n_hs = len(handshake_suites)
    n_aead = len(AEAD_DEFS)
    hs_time = n_hs * (args.duration + args.cooldown)  # per detector mode
    aead_time = n_aead * (args.duration * 2 + args.cooldown)  # enc+dec per AEAD
    total_est = 0
    if args.phase in ("all", "handshake-only"):
        total_est += 3 * hs_time  # 3 detector modes
    if args.phase in ("all", "aead-only"):
        total_est += 3 * aead_time
    total_est += args.tst_warmup + 60  # TST warmup + baseline measurements

    print(f"\n  Handshake suites : {n_hs}")
    print(f"  AEADs            : {n_aead}")
    print(f"  Duration/test    : {args.duration}s")
    print(f"  Cooldown         : {args.cooldown}s")
    print(f"  Payload          : {args.payload}B")
    print(f"  Est. total       : {total_est / 60:.0f} min ({total_est / 3600:.1f} h)")
    print(f"  Output           : {out_dir}")
    print()

    # Save config
    config = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_s": args.duration,
        "cooldown_s": args.cooldown,
        "payload_size": args.payload,
        "phase": args.phase,
        "skip_mceliece": args.skip_mceliece,
        "n_handshake_suites": n_hs,
        "n_aeads": n_aead,
        "ina219": {"cal": CAL_VALUE, "current_lsb_ua": CURRENT_LSB_A * 1e6,
                   "power_lsb_mw": POWER_LSB_W * 1e3, "vbus_gain": VBUS_GAIN},
        "sustained_rate_hz": rate,
        "governor": governor,
        "handshake_profile_ids": handshake_profile_ids,
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2))

    all_hs_results = []
    all_aead_results = []

    skip_baseline = args.resume_from in ("xgboost", "tst")
    skip_xgboost = args.resume_from == "tst"

    # ══════════════════════════════════════════════════════════════════
    #  BASELINE (no detector)
    # ══════════════════════════════════════════════════════════════════

    if not skip_baseline:
        if args.phase in ("all", "handshake-only"):
            print(f"\n{'#' * 70}")
            print(f"  DETECTOR MODE: BASELINE (no detector)")
            print(f"{'#' * 70}")
            cooldown(args.cooldown, "  Initial cooldown")
            results = run_handshake_phase(
                handshake_suites, args.duration, args.cooldown, ina, "Baseline", out_dir)
            all_hs_results.extend(results)

        if args.phase in ("all", "aead-only"):
            print(f"\n  --- AEAD Baseline ---")
            cooldown(args.cooldown, "  Pre-AEAD cooldown")
            results = run_aead_phase(
                args.duration, args.cooldown, args.payload, ina, "Baseline", out_dir)
            all_aead_results.extend(results)
    else:
        print(f"\n  [RESUME] Skipping Baseline phase")

    # ══════════════════════════════════════════════════════════════════
    #  XGBOOST
    # ══════════════════════════════════════════════════════════════════

    if not skip_xgboost and XGB_SCRIPT.exists():
        print(f"\n{'#' * 70}")
        print(f"  DETECTOR MODE: XGBoost")
        print(f"{'#' * 70}")

        xgb_proc = start_detector(XGB_SCRIPT, "XGBoost")
        if xgb_proc:
            print(f"  XGBoost warmup: 10s...")
            time.sleep(10)
            cooldown(args.cooldown, "  Post-warmup cooldown")

            if args.phase in ("all", "handshake-only"):
                results = run_handshake_phase(
                    handshake_suites, args.duration, args.cooldown,
                    ina, "XGBoost", out_dir)
                all_hs_results.extend(results)

            if args.phase in ("all", "aead-only"):
                cooldown(args.cooldown, "  Pre-AEAD cooldown")
                results = run_aead_phase(
                    args.duration, args.cooldown, args.payload,
                    ina, "XGBoost", out_dir)
                all_aead_results.extend(results)

            stop_detector(xgb_proc, "XGBoost")
        else:
            print("  WARNING: XGBoost detector failed to start")
    elif skip_xgboost:
        print(f"\n  [RESUME] Skipping XGBoost phase")
    else:
        print(f"  WARNING: XGBoost script not found, skipping")

    # ══════════════════════════════════════════════════════════════════
    #  TST (Time-Series Transformer)
    # ══════════════════════════════════════════════════════════════════

    if TST_SCRIPT.exists():
        print(f"\n{'#' * 70}")
        print(f"  DETECTOR MODE: TST (Time-Series Transformer)")
        print(f"{'#' * 70}")

        tst_proc = start_detector(TST_SCRIPT, "TST")
        if tst_proc:
            print(f"  TST warmup: {args.tst_warmup}s...")
            warmup_start = time.monotonic()
            while time.monotonic() - warmup_start < args.tst_warmup:
                remaining = args.tst_warmup - (time.monotonic() - warmup_start)
                print(f"\r  TST warmup: {remaining:.0f}s remaining...  ",
                      end="", flush=True)
                time.sleep(5)
            print(f"\r  TST warmup complete.{'':40s}")
            cooldown(args.cooldown, "  Post-warmup cooldown")

            if args.phase in ("all", "handshake-only"):
                results = run_handshake_phase(
                    handshake_suites, args.duration, args.cooldown,
                    ina, "TST", out_dir)
                all_hs_results.extend(results)

            if args.phase in ("all", "aead-only"):
                cooldown(args.cooldown, "  Pre-AEAD cooldown")
                results = run_aead_phase(
                    args.duration, args.cooldown, args.payload,
                    ina, "TST", out_dir)
                all_aead_results.extend(results)

            stop_detector(tst_proc, "TST")
        else:
            print("  WARNING: TST detector failed to start")
    else:
        print(f"  WARNING: TST script not found, skipping")

    # ══════════════════════════════════════════════════════════════════
    #  EXPORT
    # ══════════════════════════════════════════════════════════════════

    print(f"\n{'=' * 70}")
    print(f"  EXPORTING RESULTS")
    print(f"{'=' * 70}")

    if all_hs_results:
        export_handshake_csv(all_hs_results, out_dir)
    if all_aead_results:
        export_aead_csv(all_aead_results, out_dir)

    # Combined summary
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": config,
        "handshake_results": all_hs_results,
        "aead_results": all_aead_results,
    }
    (out_dir / "full_results.json").write_text(
        json.dumps(summary, indent=2, default=str))

    print(f"\n  All results → {out_dir}/")
    print(f"  Total files: {len(list(out_dir.iterdir()))}")
    print(f"\nDONE.")
    ina.close()


if __name__ == "__main__":
    main()
