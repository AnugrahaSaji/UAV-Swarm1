#!/usr/bin/env python3
"""
DDoS Detector Overhead Benchmark v2
=====================================
Comprehensive benchmark reusing the same INA219 power monitoring and
per-primitive timing infrastructure as bench/benchmark_pqc.py.

Three phases:
  1. BASELINE — 72 suites × 10 s, no detector
  2. + XGB    — xgb.py background + same benchmark
  3. + TST    — tst.py background (5 min warm-up) + same benchmark

Collected per suite
-------------------
  Handshake  : mean, median, p95, p99, stdev, min, max, throughput
  Power      : INA219 voltage / current / power per-handshake, energy
  CPU        : continuous threaded sampling during suite
  Primitives : build_hello, parse_verify, encap, decap, derive_keys (µs)
  System     : temperature, RSS, load_avg, cpu_freq
  Environment: governor, kernel, oqs version, git info

Usage (Raspberry Pi, root for scapy detectors):
    sudo ~/nenv/bin/python bench_ddos_v2.py
    sudo ~/nenv/bin/python bench_ddos_v2.py --duration 5
    sudo ~/nenv/bin/python bench_ddos_v2.py --suites 10
"""

import argparse
import json
import os
import platform
import signal
import socket
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── OQS imports (same compat as benchmark_pqc.py) ────────────────────
_LIBOQS_PYTHON_DIR = os.environ.get(
    "LIBOQS_PYTHON_DIR",
    os.path.expanduser("~/quantum-safe/liboqs-python"),
)
if os.path.isdir(_LIBOQS_PYTHON_DIR) and _LIBOQS_PYTHON_DIR not in sys.path:
    sys.path.insert(0, _LIBOQS_PYTHON_DIR)


def _init_oqs():
    for style in ["oqs.oqs", "oqs"]:
        try:
            mod = __import__(style, fromlist=["KeyEncapsulation", "Signature"])
            return mod.KeyEncapsulation, mod.Signature
        except (ImportError, AttributeError):
            continue
    raise ImportError("oqs-python not available – set LIBOQS_PYTHON_DIR")


KeyEncapsulation, Signature = _init_oqs()

from core.suites import list_suites, get_suite
from core.handshake import (
    build_server_hello,
    parse_and_verify_server_hello,
    client_encapsulate,
    server_decapsulate,
    derive_transport_keys,
)
from core.config import CONFIG

# ── Constants ─────────────────────────────────────────────────────────
DDOS_DIR = ROOT / "ddos"
XGB_SCRIPT = DDOS_DIR / "xgb_old.py"
TST_SCRIPT = DDOS_DIR / "tst_old.py"
PYTHON = sys.executable
DETECTOR_PYTHON = os.environ.get(
    "DETECTOR_PYTHON", "/home/dev/nenv/bin/python")
if not os.path.isfile(DETECTOR_PYTHON):
    DETECTOR_PYTHON = PYTHON
TST_WARMUP_S = 300
DEFAULT_DURATION = 10

# INA219 bus-voltage gain correction — see core/power_monitor.py for rationale.
_VBUS_GAIN = float(os.environ.get("INA219_VBUS_GAIN", "1.22"))
_INA219_CONFIG = 0x399F
_INA219_CAL = 8192
_INA219_POWER_LSB_MW = 1.0


# =====================================================================
# INA219 Power Monitor  (same class used by bench/benchmark_pqc.py)
# =====================================================================

class PowerMonitor:
    """INA219 power sensor — smbus2-direct preferred, adafruit fallback.

    pi-ina219 is NOT usable on RPi4: it uses Adafruit_GPIO's
    write_i2c_block_data which triggers the BCM2835 I2C block-data
    corruption bug (EIO on first transaction, permanently).
    """

    def __init__(self, power_only: bool = True):
        self._available = False
        self._backend = None       # "smbus2" | "adafruit"
        self._ina = None
        self._bus = None            # smbus2.SMBus for direct reads
        self._samples: List[Dict[str, float]] = []
        self._sampling = False
        self._shunt_ohm = 0.1
        self._power_only = bool(power_only)

        # ── 1. smbus2 direct (most reliable on RPi4) ────────────────
        try:
            import smbus2 as _smb
            bus = _smb.SMBus(1)
            # BCM2835 first-transaction warm-up
            try:
                bus.read_byte_data(0x40, 0x00)
            except OSError:
                pass
            # Verify we can read config register (retry for idle-zero bug)
            for _attempt in range(3):
                try:
                    w = bus.read_word_data(0x40, 0x00)
                    raw = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
                    if raw != 0:
                        try:
                            # Configure genuine TI profile so POWER register is valid.
                            bus.write_word_data(0x40, 0x00, ((
                                _INA219_CONFIG & 0xFF) << 8) | ((_INA219_CONFIG >> 8) & 0xFF))
                            bus.write_word_data(0x40, 0x05, ((
                                _INA219_CAL & 0xFF) << 8) | ((_INA219_CAL >> 8) & 0xFF))
                        except Exception:
                            pass
                        self._bus = bus
                        self._backend = "smbus2"
                        self._available = True
                        return
                except OSError:
                    pass
            bus.close()
        except Exception:
            pass

        # ── 2. adafruit-circuitpython-ina219 ────────────────────────
        try:
            import board
            import adafruit_ina219
            i2c = board.I2C()
            self._ina = adafruit_ina219.INA219(i2c)
            self._backend = "adafruit"
            self._available = True
        except Exception:
            pass

    @property
    def available(self) -> bool:
        return self._available

    def read_once(self) -> Dict[str, Optional[float]]:
        if not self._available:
            return {"voltage_v": None, "current_ma": None, "power_mw": None}
        try:
            if self._backend == "smbus2" and self._bus is not None:
                bus = self._bus
                addr = 0x40
                if self._power_only:
                    try:
                        w = bus.read_word_data(addr, 0x03)
                        raw_p = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
                        return {
                            "voltage_v": None,
                            "current_ma": None,
                            "power_mw": raw_p * _INA219_POWER_LSB_MW,
                            "timestamp_ns": time.time_ns(),
                        }
                    except OSError:
                        return {"voltage_v": None, "current_ma": None, "power_mw": None}
                for _att in range(3):
                    try:
                        # Bus voltage (reg 0x02): bits[15:3] × 4 mV
                        w = bus.read_word_data(addr, 0x02)
                        raw_v = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
                        v = ((raw_v >> 3) & 0x1FFF) * 0.004 * _VBUS_GAIN
                        if v < 0.1 and _att < 2:
                            continue  # BCM2835 idle-zero retry
                        # Shunt voltage (reg 0x01): signed 16-bit, 10 µV LSB
                        w = bus.read_word_data(addr, 0x01)
                        raw_sh = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
                        if raw_sh & 0x8000:
                            raw_sh -= 1 << 16
                        shunt_v = raw_sh * 10e-6
                        c_a = abs(shunt_v / self._shunt_ohm)
                        c = c_a * 1000.0  # mA
                        p = v * c          # mW (V × mA)
                        return {
                            "voltage_v": v,
                            "current_ma": c,
                            "power_mw": p,
                            "timestamp_ns": time.time_ns(),
                        }
                    except OSError:
                        pass
                return {"voltage_v": None, "current_ma": None, "power_mw": None}
            else:  # adafruit
                v = self._ina.bus_voltage * _VBUS_GAIN  # V
                c = abs(self._ina.current)       # mA (may be negative)
                p = v * c                        # mW (V × mA)
                return {
                    "voltage_v": v,
                    "current_ma": c,
                    "power_mw": p,
                    "timestamp_ns": time.time_ns(),
                }
        except Exception:
            return {"voltage_v": None, "current_ma": None, "power_mw": None}

    def start_sampling(self) -> None:
        self._samples = []
        self._sampling = True

    def stop_sampling(self) -> List[Dict[str, float]]:
        self._sampling = False
        return self._samples

    def sample(self) -> None:
        if self._sampling and self._available:
            reading = self.read_once()
            if reading.get("power_mw") is not None:
                self._samples.append(reading)

    def compute_energy(self, samples: List[Dict[str, float]],
                       duration_s: float) -> Optional[float]:
        if not samples or duration_s <= 0:
            return None
        powers = [s["power_mw"] for s in samples
                  if s.get("power_mw") is not None]
        if not powers:
            return None
        return sum(powers) / len(powers) * duration_s  # mW × s = mJ


# =====================================================================
# Continuous CPU sampler (threaded – replaces broken 0.1 s snapshot)
# =====================================================================

class CpuSampler:
    """Read /proc/stat every *interval* s in a background thread."""

    def __init__(self, interval: float = 0.5):
        self._interval = interval
        self._samples: List[float] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._samples = []
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> Tuple[float, float, List[float]]:
        """Return (avg_cpu%, peak_cpu%, raw_samples)."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if not self._samples:
            return 0.0, 0.0, []
        avg = statistics.mean(self._samples)
        peak = max(self._samples)
        return avg, peak, list(self._samples)

    def _loop(self) -> None:
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
    def _read_stat() -> Tuple[int, int]:
        try:
            with open("/proc/stat") as f:
                parts = f.readline().split()
            idle = int(parts[4])
            total = sum(int(p) for p in parts[1:])
            return idle, total
        except Exception:
            return 0, 1


# =====================================================================
# System helpers
# =====================================================================

def read_cpu_temp() -> Optional[float]:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None


def read_mem_rss_mb() -> float:
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
        return 0.0
    except Exception:
        return 0.0


def read_load_avg() -> float:
    try:
        return os.getloadavg()[0]
    except Exception:
        return 0.0


def read_cpu_freq_mhz() -> float:
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return 0.0


def set_performance_governor() -> str:
    """Attempt to set performance governor on all CPUs. Returns actual governor."""
    try:
        for cpu_dir in sorted(Path("/sys/devices/system/cpu/").glob("cpu[0-9]*")):
            gov_path = cpu_dir / "cpufreq" / "scaling_governor"
            if gov_path.exists():
                try:
                    gov_path.write_text("performance\n")
                except PermissionError:
                    subprocess.run(
                        f"echo performance | sudo tee {gov_path}",
                        shell=True, capture_output=True)
    except Exception:
        pass
    # Read back actual governor
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") as f:
            return f.read().strip()
    except Exception:
        return "unknown"


def collect_environment() -> Dict[str, Any]:
    """Collect environment metadata (same fields as benchmark_pqc.py)."""
    cpu_model = "unknown"
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name") or line.startswith("Model"):
                    cpu_model = line.split(":")[1].strip()
                    break
    except Exception:
        cpu_model = platform.processor() or "unknown"

    governor = "unknown"
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") as f:
            governor = f.read().strip()
    except Exception:
        pass

    oqs_ver = oqs_py_ver = "unknown"
    try:
        import oqs
        oqs_ver = oqs.oqs_version()
        oqs_py_ver = oqs.__version__
    except Exception:
        pass

    git_commit = git_branch = "unknown"
    git_clean = False
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            git_commit = r.stdout.strip()
        r = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            git_branch = r.stdout.strip()
        r = subprocess.run(["git", "status", "--porcelain"],
                           capture_output=True, text=True, timeout=5)
        git_clean = r.returncode == 0 and not r.stdout.strip()
    except Exception:
        pass

    return {
        "hostname": socket.gethostname(),
        "cpu_model": cpu_model,
        "cpu_freq_governor": governor,
        "cpu_freq_mhz": read_cpu_freq_mhz(),
        "kernel_version": platform.release(),
        "python_version": sys.version,
        "oqs_version": oqs_ver,
        "oqs_python_version": oqs_py_ver,
        "git_commit": git_commit,
        "git_branch": git_branch,
        "git_clean": git_clean,
        "timestamp_iso": datetime.now(timezone.utc).isoformat(),
        "power_sensor": "INA219",
    }


# =====================================================================
# Per-handshake primitive timing
# =====================================================================

@dataclass
class PrimitiveTimings:
    """Per-handshake step timings in nanoseconds."""
    build_hello_ns: int = 0
    parse_verify_ns: int = 0
    encap_ns: int = 0
    decap_ns: int = 0
    derive_keys_client_ns: int = 0
    derive_keys_server_ns: int = 0


# =====================================================================
# Suite result (comprehensive)
# =====================================================================

@dataclass
class SuiteResult:
    suite_id: str
    kem: str
    sig: str
    aead: str
    nist_level: str
    duration_s: float
    iterations: int

    # Timing statistics (µs)
    mean_us: float = 0.0
    median_us: float = 0.0
    p95_us: float = 0.0
    p99_us: float = 0.0
    stdev_us: float = 0.0
    min_us: float = 0.0
    max_us: float = 0.0
    throughput_hz: float = 0.0

    # Per-primitive averages (µs)
    build_hello_avg_us: float = 0.0
    parse_verify_avg_us: float = 0.0
    encap_avg_us: float = 0.0
    decap_avg_us: float = 0.0
    derive_keys_client_avg_us: float = 0.0
    derive_keys_server_avg_us: float = 0.0

    # Power (INA219)
    avg_power_mw: Optional[float] = None
    avg_voltage_v: Optional[float] = None
    avg_current_ma: Optional[float] = None
    avg_energy_mj_per_hs: Optional[float] = None
    total_energy_mj: Optional[float] = None
    power_samples_count: int = 0
    power_sample_rate_hz: float = 0.0

    # CPU (continuous sampler)
    cpu_avg: float = 0.0
    cpu_peak: float = 0.0

    # System
    temp_c: float = 0.0
    load_avg: float = 0.0
    mem_rss_mb: float = 0.0
    cpu_freq_mhz: float = 0.0

    # Artifact sizes (bytes) – first handshake only
    public_key_bytes: Optional[int] = None
    signature_bytes: Optional[int] = None
    ciphertext_bytes: Optional[int] = None
    shared_secret_bytes: Optional[int] = None

    error: Optional[str] = None


# =====================================================================
# Single-suite benchmark  (time-based + full metrics)
# =====================================================================

def benchmark_suite(suite_id: str, duration_s: float,
                    power_monitor: PowerMonitor,
                    cpu_sampler: CpuSampler) -> SuiteResult:
    """Run handshake loop for *duration_s* seconds with full instrumentation."""
    suite_cfg = get_suite(suite_id)
    sig_name = suite_cfg["sig_name"]

    # One-time: generate GCS signing keypair
    gcs_sig = Signature(sig_name)
    gcs_sig_pub = gcs_sig.generate_keypair()

    times_us: List[float] = []
    prim_timings: List[PrimitiveTimings] = []
    all_power_samples: List[Dict[str, float]] = []
    energy_per_hs: List[float] = []
    errors = 0

    # Artifact sizes (record on first iteration)
    pk_bytes = sig_bytes = ct_bytes = ss_bytes = None

    # Start continuous CPU sampling
    cpu_sampler.start()
    t_start = time.monotonic()

    while time.monotonic() - t_start < duration_s:
        # ── Per-handshake power sampling (same pattern as benchmark_pqc.py) ──
        power_monitor.start_sampling()
        hs_wall_start = time.time_ns()
        t0 = time.perf_counter_ns()

        try:
            power_monitor.sample()

            # Step 1: build_server_hello
            s1 = time.perf_counter_ns()
            hello_wire, eph = build_server_hello(suite_id, gcs_sig)
            e1 = time.perf_counter_ns()
            power_monitor.sample()

            # Step 2: parse_and_verify
            s2 = time.perf_counter_ns()
            hello = parse_and_verify_server_hello(
                hello_wire, CONFIG["WIRE_VERSION"], gcs_sig_pub)
            e2 = time.perf_counter_ns()
            power_monitor.sample()

            # Step 3: client_encapsulate
            s3 = time.perf_counter_ns()
            kem_ct, drone_shared = client_encapsulate(hello)
            e3 = time.perf_counter_ns()
            power_monitor.sample()

            # Step 4: server_decapsulate
            s4 = time.perf_counter_ns()
            gcs_shared = server_decapsulate(eph, kem_ct)
            e4 = time.perf_counter_ns()
            power_monitor.sample()

            # Step 5: derive_transport_keys (client)
            s5 = time.perf_counter_ns()
            derive_transport_keys(
                "client", hello.session_id, hello.kem_name,
                hello.sig_name, drone_shared)
            e5 = time.perf_counter_ns()
            power_monitor.sample()

            # Step 6: derive_transport_keys (server)
            s6 = time.perf_counter_ns()
            derive_transport_keys(
                "server", eph.session_id, eph.kem_name.encode(),
                eph.sig_name.encode(), gcs_shared)
            e6 = time.perf_counter_ns()
            power_monitor.sample()

        except Exception:
            errors += 1
            power_monitor.stop_sampling()
            continue

        t1 = time.perf_counter_ns()
        hs_wall_end = time.time_ns()
        hs_duration_s = (hs_wall_end - hs_wall_start) / 1e9

        # Collect power samples for this handshake
        samples = power_monitor.stop_sampling()
        all_power_samples.extend(samples)
        energy = power_monitor.compute_energy(samples, hs_duration_s)
        if energy is not None:
            energy_per_hs.append(energy)

        times_us.append((t1 - t0) / 1_000)
        prim_timings.append(PrimitiveTimings(
            build_hello_ns=e1 - s1,
            parse_verify_ns=e2 - s2,
            encap_ns=e3 - s3,
            decap_ns=e4 - s4,
            derive_keys_client_ns=e5 - s5,
            derive_keys_server_ns=e6 - s6,
        ))

        # Artifact sizes (first iteration)
        if pk_bytes is None:
            pk_bytes = len(hello.kem_pub)
            sig_bytes = len(hello.signature)
            ct_bytes = len(kem_ct)
            ss_bytes = len(drone_shared)

    elapsed = time.monotonic() - t_start
    cpu_avg, cpu_peak, _ = cpu_sampler.stop()

    gcs_sig.free()

    if not times_us:
        return SuiteResult(
            suite_id=suite_id,
            kem=suite_cfg.get("kem_name", ""),
            sig=suite_cfg.get("sig_name", ""),
            aead=suite_cfg.get("aead_name", ""),
            nist_level=suite_cfg.get("nist_level", ""),
            duration_s=elapsed,
            iterations=0,
            error=f"{errors} errors, 0 successful",
        )

    sorted_t = sorted(times_us)
    n = len(sorted_t)

    # Per-primitive averages (ns → µs)
    bh_avg = statistics.mean([p.build_hello_ns for p in prim_timings]) / 1_000
    pv_avg = statistics.mean([p.parse_verify_ns for p in prim_timings]) / 1_000
    ec_avg = statistics.mean([p.encap_ns for p in prim_timings]) / 1_000
    dc_avg = statistics.mean([p.decap_ns for p in prim_timings]) / 1_000
    dkc_avg = statistics.mean([p.derive_keys_client_ns for p in prim_timings]) / 1_000
    dks_avg = statistics.mean([p.derive_keys_server_ns for p in prim_timings]) / 1_000

    # Power aggregates
    avg_power = avg_voltage = avg_current = None
    total_energy = None
    avg_energy_per_hs = None
    if all_power_samples:
        powers = [s["power_mw"] for s in all_power_samples
                  if s.get("power_mw") is not None]
        voltages = [s["voltage_v"] for s in all_power_samples
                    if s.get("voltage_v") is not None]
        currents = [s["current_ma"] for s in all_power_samples
                    if s.get("current_ma") is not None]
        if powers:
            avg_power = statistics.mean(powers)
        if voltages:
            avg_voltage = statistics.mean(voltages)
        if currents:
            avg_current = statistics.mean(currents)
        if avg_power is not None:
            total_energy = avg_power * elapsed  # mW × s = mJ
    if energy_per_hs:
        avg_energy_per_hs = statistics.mean(energy_per_hs)

    return SuiteResult(
        suite_id=suite_id,
        kem=suite_cfg.get("kem_name", ""),
        sig=suite_cfg.get("sig_name", ""),
        aead=suite_cfg.get("aead_name", ""),
        nist_level=suite_cfg.get("nist_level", ""),
        duration_s=elapsed,
        iterations=n,
        mean_us=statistics.mean(sorted_t),
        median_us=sorted_t[n // 2],
        p95_us=sorted_t[int(n * 0.95)],
        p99_us=sorted_t[int(n * 0.99)],
        stdev_us=statistics.stdev(sorted_t) if n > 1 else 0.0,
        min_us=sorted_t[0],
        max_us=sorted_t[-1],
        throughput_hz=n / elapsed,
        build_hello_avg_us=bh_avg,
        parse_verify_avg_us=pv_avg,
        encap_avg_us=ec_avg,
        decap_avg_us=dc_avg,
        derive_keys_client_avg_us=dkc_avg,
        derive_keys_server_avg_us=dks_avg,
        avg_power_mw=avg_power,
        avg_voltage_v=avg_voltage,
        avg_current_ma=avg_current,
        avg_energy_mj_per_hs=avg_energy_per_hs,
        total_energy_mj=total_energy,
        power_samples_count=len(all_power_samples),
        power_sample_rate_hz=(len(all_power_samples) / elapsed) if elapsed > 0 else 0.0,
        cpu_avg=cpu_avg,
        cpu_peak=cpu_peak,
        temp_c=read_cpu_temp() or 0.0,
        load_avg=read_load_avg(),
        mem_rss_mb=read_mem_rss_mb(),
        cpu_freq_mhz=read_cpu_freq_mhz(),
        public_key_bytes=pk_bytes,
        signature_bytes=sig_bytes,
        ciphertext_bytes=ct_bytes,
        shared_secret_bytes=ss_bytes,
    )


# =====================================================================
# Phase runner
# =====================================================================

def run_phase(phase_name: str, suites: List[str], duration: float,
              out_dir: Path, power_monitor: PowerMonitor) -> Dict[str, Any]:
    """Benchmark every suite for *duration* seconds each."""
    print(f"\n{'=' * 78}")
    print(f"  PHASE: {phase_name}")
    print(f"  Suites: {len(suites)}  |  Duration/suite: {duration}s")
    print(f"  Estimated: {len(suites) * duration / 60:.1f} min")
    print(f"  Power sensor: {'INA219 active' if power_monitor.available else 'NOT available'}")
    print(f"{'=' * 78}\n")

    cpu_sampler = CpuSampler(interval=0.5)
    phase_start = time.monotonic()
    results: List[Dict[str, Any]] = []

    for i, sid in enumerate(suites, 1):
        print(f"  [{i:3d}/{len(suites)}]  {sid:<55s} ", end="", flush=True)
        try:
            r = benchmark_suite(sid, duration, power_monitor, cpu_sampler)
            results.append(asdict(r))
            if r.error:
                print(f"ERROR: {r.error}")
            else:
                pwr_str = f"  {r.avg_power_mw:.0f}mW" if r.avg_power_mw else ""
                rate_str = f"  {r.power_sample_rate_hz:.0f}Hz"
                print(f"{r.mean_us / 1000:8.1f} ms  ({r.iterations:5d} it)  "
                      f"CPU {r.cpu_avg:4.1f}%  {r.temp_c:.0f}°C{pwr_str}{rate_str}")
        except Exception as exc:
            print(f"EXCEPTION: {exc}")
            results.append({"suite_id": sid, "error": str(exc)})

    phase_elapsed = time.monotonic() - phase_start

    payload = {
        "phase": phase_name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_suites": len(suites),
        "duration_per_suite_s": duration,
        "phase_elapsed_s": round(phase_elapsed, 1),
        "results": results,
    }

    out_file = out_dir / f"{phase_name}.json"
    out_file.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  Saved → {out_file}  ({phase_elapsed:.0f}s total)")
    return payload


# =====================================================================
# Detector management  (unchanged from v1)
# =====================================================================

def start_detector(script: Path, label: str) -> Optional[subprocess.Popen]:
    print(f"  Starting {label} ({script.name}) via {DETECTOR_PYTHON}...",
          end="", flush=True)
    err_path = Path(f"/tmp/detector_{label.lower().replace(' ', '_')}.err")
    err_fh = open(err_path, "w")
    proc = subprocess.Popen(
        [DETECTOR_PYTHON, "-u", str(script)],
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
    print(f"  Stopping {label} (PID {proc.pid})...", end="", flush=True)
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
    except Exception:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            proc.kill()
        proc.wait(timeout=3)
    print(" done")


# =====================================================================
# Comparison  (enhanced with power ordering check)
# =====================================================================

def build_comparison(baseline: Dict, xgb_data: Dict, tst_data: Dict,
                     out_dir: Path):
    def _index(data):
        idx = {}
        for r in data.get("results", []):
            sid = r.get("suite_id")
            if sid and r.get("mean_us"):
                idx[sid] = r
        return idx

    base_idx = _index(baseline)
    xgb_idx = _index(xgb_data)
    tst_idx = _index(tst_data)

    rows = []
    for sid in base_idx:
        b = base_idx[sid]
        x = xgb_idx.get(sid)
        t = tst_idx.get(sid)
        row = {
            "suite_id": sid,
            "baseline_mean_ms": round(b["mean_us"] / 1000, 2),
            "baseline_throughput": round(b["throughput_hz"], 2),
            "baseline_cpu_avg": round(b.get("cpu_avg", 0), 2),
            "baseline_power_mw": b.get("avg_power_mw"),
        }
        if x and x.get("mean_us"):
            row["xgb_mean_ms"] = round(x["mean_us"] / 1000, 2)
            row["xgb_overhead_pct"] = round(
                (x["mean_us"] - b["mean_us"]) / b["mean_us"] * 100, 2)
            row["xgb_throughput"] = round(x["throughput_hz"], 2)
            row["xgb_cpu_avg"] = round(x.get("cpu_avg", 0), 2)
            row["xgb_power_mw"] = x.get("avg_power_mw")
        if t and t.get("mean_us"):
            row["tst_mean_ms"] = round(t["mean_us"] / 1000, 2)
            row["tst_overhead_pct"] = round(
                (t["mean_us"] - b["mean_us"]) / b["mean_us"] * 100, 2)
            row["tst_throughput"] = round(t["throughput_hz"], 2)
            row["tst_cpu_avg"] = round(t.get("cpu_avg", 0), 2)
            row["tst_power_mw"] = t.get("avg_power_mw")
        rows.append(row)

    # ── Aggregate stats ──
    xgb_oh = [r["xgb_overhead_pct"] for r in rows if "xgb_overhead_pct" in r]
    tst_oh = [r["tst_overhead_pct"] for r in rows if "tst_overhead_pct" in r]

    # ── Ordering check: no-ddos < xgb < tst ──
    cpu_order_ok = power_order_ok = 0
    cpu_order_fail = power_order_fail = 0
    for r in rows:
        bc = r.get("baseline_cpu_avg", 0)
        xc = r.get("xgb_cpu_avg")
        tc = r.get("tst_cpu_avg")
        if xc is not None and tc is not None:
            if bc <= xc <= tc:
                cpu_order_ok += 1
            else:
                cpu_order_fail += 1
        bp = r.get("baseline_power_mw")
        xp = r.get("xgb_power_mw")
        tp = r.get("tst_power_mw")
        if bp is not None and xp is not None and tp is not None:
            if bp <= xp <= tp:
                power_order_ok += 1
            else:
                power_order_fail += 1

    summary = {
        "total_suites": len(rows),
        "xgb_overhead_mean_pct": round(statistics.mean(xgb_oh), 2) if xgb_oh else None,
        "xgb_overhead_median_pct": round(statistics.median(xgb_oh), 2) if xgb_oh else None,
        "xgb_overhead_max_pct": round(max(xgb_oh), 2) if xgb_oh else None,
        "tst_overhead_mean_pct": round(statistics.mean(tst_oh), 2) if tst_oh else None,
        "tst_overhead_median_pct": round(statistics.median(tst_oh), 2) if tst_oh else None,
        "tst_overhead_max_pct": round(max(tst_oh), 2) if tst_oh else None,
        "cpu_ordering_correct": cpu_order_ok,
        "cpu_ordering_violated": cpu_order_fail,
        "power_ordering_correct": power_order_ok,
        "power_ordering_violated": power_order_fail,
    }

    comparison = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "per_suite": rows,
    }

    out_file = out_dir / "comparison.json"
    out_file.write_text(json.dumps(comparison, indent=2, default=str))

    # ── Pretty-print ──
    W = 95
    print(f"\n{'=' * W}")
    print("  COMPARISON SUMMARY")
    print(f"{'=' * W}")
    print(f"  {'Suite':55s} {'Baseline':>10s}  {'+ XGB':>10s}  {'+ TST':>10s}")
    print(f"  {'-' * 55} {'-' * 10}  {'-' * 10}  {'-' * 10}")

    for r in rows[:20]:
        bl = f"{r['baseline_mean_ms']:8.1f}ms"
        xg = f"{r.get('xgb_mean_ms', 0):8.1f}ms" if "xgb_mean_ms" in r else "       N/A"
        ts = f"{r.get('tst_mean_ms', 0):8.1f}ms" if "tst_mean_ms" in r else "       N/A"
        print(f"  {r['suite_id'][:55]:55s} {bl}  {xg}  {ts}")
    if len(rows) > 20:
        print(f"  ... ({len(rows) - 20} more)")

    print(f"\n  OVERHEAD (mean across suites):")
    print(f"    XGBoost : {summary.get('xgb_overhead_mean_pct', 'N/A')}%  "
          f"(median {summary.get('xgb_overhead_median_pct', 'N/A')}%)")
    print(f"    TST     : {summary.get('tst_overhead_mean_pct', 'N/A')}%  "
          f"(median {summary.get('tst_overhead_median_pct', 'N/A')}%)")

    print(f"\n  ORDERING CHECK  (no-ddos ≤ xgb ≤ tst):")
    print(f"    CPU   : {cpu_order_ok} correct / {cpu_order_fail} violated")
    print(f"    Power : {power_order_ok} correct / {power_order_fail} violated")
    print(f"\n  Results → {out_dir}/")
    print(f"{'=' * W}\n")

    return comparison


# =====================================================================
# Main
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="DDoS Detector Overhead Benchmark v2 (full metrics)")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION,
                        help="Seconds per suite (default: 10)")
    parser.add_argument("--suites", type=int, default=0,
                        help="Limit to first N suites (0 = all)")
    parser.add_argument("--skip-baseline", action="store_true")
    parser.add_argument("--skip-xgb", action="store_true")
    parser.add_argument("--skip-tst", action="store_true")
    parser.add_argument("--tst-warmup", type=int, default=TST_WARMUP_S,
                        help=f"TST warm-up seconds (default: {TST_WARMUP_S})")
    parser.add_argument("--full-vip", action="store_true",
                        help="Measure voltage+current+power per sample (slower). Default is fast power-only mode.")
    args = parser.parse_args()

    # ── 1.  Set performance governor ──────────────────────────────────
    print("\n── Setting CPU governor to 'performance' ──")
    governor = set_performance_governor()
    print(f"  Governor : {governor}")
    print(f"  CPU freq : {read_cpu_freq_mhz():.0f} MHz")

    # ── 2.  Initialise INA219 power monitor ──────────────────────────
    power_monitor = PowerMonitor(power_only=not args.full_vip)
    print(f"  INA219   : {'available (' + power_monitor._backend + ')' if power_monitor.available else 'NOT detected'}")
    print(f"  INA mode : {'power-only (fast)' if not args.full_vip else 'voltage+current+power'}")
    if power_monitor.available:
        snap = power_monitor.read_once()
        print(f"  Baseline : {snap.get('voltage_v', 0):.2f} V  "
              f"{snap.get('current_ma', 0):.0f} mA  "
              f"{snap.get('power_mw', 0):.0f} mW")

    # ── 3.  Discover suites ──────────────────────────────────────────
    all_suites = sorted(list_suites().keys())
    if args.suites > 0:
        all_suites = all_suites[:args.suites]

    total_per_phase = len(all_suites) * args.duration
    phases = 3 - args.skip_baseline - args.skip_xgb - args.skip_tst
    est_total = phases * total_per_phase + (
        args.tst_warmup if not args.skip_tst else 0)

    print(f"\n{'=' * 70}")
    print(f"  DDoS DETECTOR OVERHEAD BENCHMARK v2")
    print(f"{'=' * 70}")
    print(f"  Suites        : {len(all_suites)}")
    print(f"  Duration/suite: {args.duration}s")
    print(f"  Per phase     : {total_per_phase / 60:.1f} min")
    print(f"  Phases        : {phases}")
    print(f"  Est. total    : {est_total / 60:.0f} min")
    print()

    for script in [XGB_SCRIPT, TST_SCRIPT]:
        if not script.exists():
            print(f"ERROR: {script} not found")
            sys.exit(1)

    # Output directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "bench_ddos_results" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save environment + config
    env = collect_environment()
    config = {
        "suites": len(all_suites),
        "duration_per_suite_s": args.duration,
        "tst_warmup_s": args.tst_warmup,
        "environment": env,
        "power_sensor_available": power_monitor.available,
        "power_mode": "power_only" if not args.full_vip else "full_vip",
        "suite_list": all_suites,
    }
    (out_dir / "environment.json").write_text(json.dumps(env, indent=2))
    (out_dir / "config.json").write_text(json.dumps(config, indent=2))

    # ── Phase 1: Baseline ─────────────────────────────────────────────
    baseline_data = None
    if not args.skip_baseline:
        baseline_data = run_phase(
            "baseline", all_suites, args.duration, out_dir, power_monitor)

    # ── Phase 2: + XGBoost ────────────────────────────────────────────
    xgb_data = None
    if not args.skip_xgb:
        print("\n── Starting XGBoost detector ──")
        xgb_proc = start_detector(XGB_SCRIPT, "XGBoost")
        if xgb_proc:
            print(f"  Waiting 5 s for XGB warm-up...")
            time.sleep(5)
            xgb_data = run_phase(
                "xgb", all_suites, args.duration, out_dir, power_monitor)
            stop_detector(xgb_proc, "XGBoost")
        else:
            print("  WARNING: XGBoost failed to start, skipping phase")

    # ── Phase 3: + TST ────────────────────────────────────────────────
    tst_data = None
    if not args.skip_tst:
        print("\n── Starting TST detector ──")
        tst_proc = start_detector(TST_SCRIPT, "TST")
        if tst_proc:
            print(f"  TST warm-up: {args.tst_warmup}s ({args.tst_warmup / 60:.0f} min)...")
            warmup_start = time.monotonic()
            while time.monotonic() - warmup_start < args.tst_warmup:
                remaining = args.tst_warmup - (time.monotonic() - warmup_start)
                print(f"\r  TST warm-up: {remaining:.0f}s remaining...  ",
                      end="", flush=True)
                time.sleep(10)
            print(f"\r  TST warm-up complete.{'':40s}")

            tst_data = run_phase(
                "tst", all_suites, args.duration, out_dir, power_monitor)
            stop_detector(tst_proc, "TST")
        else:
            print("  WARNING: TST failed to start, skipping phase")

    # ── Comparison ────────────────────────────────────────────────────
    if baseline_data and (xgb_data or tst_data):
        build_comparison(
            baseline_data,
            xgb_data or {"results": []},
            tst_data or {"results": []},
            out_dir,
        )
    else:
        print("\n  Not enough data for comparison")

    print(f"\n  All results → {out_dir}/")
    print("DONE.")


if __name__ == "__main__":
    main()
