#!/usr/bin/env python3
"""INA219 hardware-power-register energy benchmarking for PQC primitives.

Uses genuine TI INA219 calibrated registers:
  Cal=8192, Current_LSB=50µA, Power_LSB=1mW, VBUS_GAIN=1.0

Design:
  - Background thread reads INA219 POWER register (0x03) at ~1750 Hz
  - Main thread runs crypto operations in a tight loop
  - Power trace is captured continuously during the entire crypto batch
  - Trapezoidal integration gives total energy
  - Baseline idle power is subtracted for net energy per operation

For each cryptographic primitive:
  - 200 iterations (configurable)
  - Full high-frequency power trace capture
  - Trapezoidal integration for total energy
  - Baseline (idle) subtraction for net energy
"""

from __future__ import annotations

import argparse
import csv
import gc
import json
import os
import sys
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# INA219 constants (genuine TI, Cal=8192)
# ---------------------------------------------------------------------------
INA219_ADDR = 0x40
INA219_I2C_BUS = 1
INA219_REG_CONFIG = 0x00
INA219_REG_SHUNT = 0x01
INA219_REG_BUS = 0x02
INA219_REG_POWER = 0x03
INA219_REG_CURRENT = 0x04
INA219_REG_CAL = 0x05

CAL_VALUE = 8192
CURRENT_LSB_A = 50e-6       # 50 µA per bit
POWER_LSB_W = 20 * CURRENT_LSB_A  # = 1 mW per bit
VBUS_GAIN = 1.0             # Genuine TI — no correction

CONFIG_VALUE = 0x399F  # 32V, /8, 12-bit, continuous shunt+bus

# Target crypto primitives
TARGET_KEMS = [
    "ML-KEM-512", "ML-KEM-768", "ML-KEM-1024",
    "HQC-128", "HQC-192", "HQC-256",
    "Classic-McEliece-348864", "Classic-McEliece-460896",
    "Classic-McEliece-8192128",
]

TARGET_SIGS = [
    "ML-DSA-44", "ML-DSA-65", "ML-DSA-87",
    "Falcon-512", "Falcon-1024",
    "SPHINCS+-SHA2-128s-simple", "SPHINCS+-SHA2-192s-simple",
    "SPHINCS+-SHA2-256s-simple",
]

TARGET_AEADS = ["AES-256-GCM", "ChaCha20-Poly1305", "Ascon-128a"]

DEFAULT_ITERATIONS = 200
BASELINE_DURATION_S = 3.0
WARMUP_ITERATIONS = 5
MIN_TRACE_DURATION_S = 2.0  # minimum measurement window for fast ops


@dataclass
class EnergyResult:
    primitive_type: str
    algorithm: str
    operation: str
    iterations: int
    total_samples: int
    sample_rate_hz: float
    total_duration_s: float
    per_op_duration_ms: float
    baseline_power_w: float
    avg_gross_power_w: float
    avg_net_power_w: float
    total_gross_energy_j: float
    total_net_energy_j: float
    per_op_net_energy_j: float
    per_op_net_energy_uj: float
    csv_path: str


class INA219Direct:
    """Direct I2C to INA219 via smbus2 for maximum throughput."""

    def __init__(self, bus_num: int = INA219_I2C_BUS, addr: int = INA219_ADDR):
        import smbus2
        self.addr = addr
        self.bus = smbus2.SMBus(bus_num)
        self._lock = threading.Lock()
        try:
            self.bus.read_byte_data(addr, 0x00)
        except OSError:
            pass
        self._configure()
        self._write_calibration()

    def _write_word_be(self, reg: int, value: int):
        word_le = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)
        with self._lock:
            self.bus.write_word_data(self.addr, reg, word_le)

    def _read_word_be(self, reg: int) -> int:
        with self._lock:
            for attempt in range(3):
                try:
                    word_le = self.bus.read_word_data(self.addr, reg)
                    val = ((word_le & 0xFF) << 8) | ((word_le >> 8) & 0xFF)
                    if val == 0 and reg in (0x00, 0x02) and attempt < 2:
                        continue
                    return val
                except OSError:
                    if attempt == 2:
                        raise
        return 0

    def _read_word_be_signed(self, reg: int) -> int:
        val = self._read_word_be(reg)
        return val - (1 << 16) if val & 0x8000 else val

    def _configure(self):
        self._write_word_be(INA219_REG_CONFIG, CONFIG_VALUE)
        time.sleep(0.001)
        try:
            self._read_word_be(INA219_REG_CONFIG)
        except OSError:
            pass

    def _write_calibration(self):
        self._write_word_be(INA219_REG_CAL, CAL_VALUE)
        time.sleep(0.001)
        readback = self._read_word_be(INA219_REG_CAL)
        if readback != CAL_VALUE:
            print(f"WARNING: Cal readback={readback} (expected {CAL_VALUE})")
        else:
            print(f"INA219 Cal verified: {readback} (0x{readback:04X})")

    def read_power_w(self) -> float:
        """Single I2C transaction -> power in watts."""
        raw = self._read_word_be(INA219_REG_POWER)
        return raw * POWER_LSB_W

    def read_current_a(self) -> float:
        raw = self._read_word_be_signed(INA219_REG_CURRENT)
        return raw * CURRENT_LSB_A

    def read_bus_voltage_v(self) -> float:
        raw = self._read_word_be(INA219_REG_BUS)
        return ((raw >> 3) & 0x1FFF) * 0.004 * VBUS_GAIN

    def read_all(self) -> tuple[float, float, float]:
        p = self.read_power_w()
        c = self.read_current_a()
        v = self.read_bus_voltage_v()
        return p, c, v

    def close(self):
        if self.bus:
            self.bus.close()


class PowerTracer:
    """Background-thread power trace capture at maximum INA219 rate."""

    def __init__(self, ina: INA219Direct):
        self.ina = ina
        self._trace: list[tuple[float, float]] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        """Start background power capture."""
        self._trace = []
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> list[tuple[float, float]]:
        """Stop capture and return trace as [(time_s, power_w), ...]."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        return list(self._trace)

    def _capture_loop(self):
        trace = self._trace
        ina = self.ina
        t0 = time.perf_counter()
        while self._running:
            try:
                pw = ina.read_power_w()
                trace.append((time.perf_counter() - t0, pw))
            except OSError:
                pass  # I2C glitch — skip sample


def integrate_energy(trace: list[tuple[float, float]]) -> float:
    """Trapezoidal integration of power trace -> energy in joules."""
    if len(trace) < 2:
        return 0.0
    energy = 0.0
    for i in range(1, len(trace)):
        dt = trace[i][0] - trace[i - 1][0]
        avg_p = (trace[i][1] + trace[i - 1][1]) / 2.0
        energy += avg_p * dt
    return energy


def trace_stats(trace: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    """Return (duration_s, avg_power, sample_count, sample_rate_hz)."""
    if len(trace) < 2:
        return (0, 0, len(trace), 0)
    dur = trace[-1][0] - trace[0][0]
    avg = sum(p for _, p in trace) / len(trace)
    rate = len(trace) / dur if dur > 0 else 0
    return (dur, avg, len(trace), rate)


def save_trace_csv(trace: list[tuple[float, float]], path: Path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_s", "power_w"])
        for ts, pw in trace:
            w.writerow([f"{ts:.6f}", f"{pw:.6f}"])


def measure_baseline(ina: INA219Direct, tracer: PowerTracer,
                     duration_s: float = BASELINE_DURATION_S) -> float:
    """Capture idle baseline power."""
    print(f"  Measuring idle baseline ({duration_s:.1f}s)...")
    time.sleep(0.3)  # settle
    tracer.start()
    time.sleep(duration_s)
    trace = tracer.stop()
    if not trace:
        return 0.0
    dur, avg, n, rate = trace_stats(trace)
    print(f"  Baseline: {avg:.4f} W ({n} samples, {rate:.0f} Hz)")
    return avg


# ---------------------------------------------------------------------------
# Crypto imports
# ---------------------------------------------------------------------------

def _import_oqs():
    from oqs.oqs import KeyEncapsulation, Signature
    return KeyEncapsulation, Signature


def _get_aesgcm():
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM


def _get_chacha20():
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    return ChaCha20Poly1305


def _get_ascon():
    try:
        import ascon
        if hasattr(ascon, 'ascon_encrypt'):
            return ascon.ascon_encrypt, ascon.ascon_decrypt
        return ascon.encrypt, ascon.decrypt
    except ImportError:
        import pyascon
        return pyascon.ascon_encrypt, pyascon.ascon_decrypt


# ---------------------------------------------------------------------------
# Benchmark functions — threaded power capture
# ---------------------------------------------------------------------------

def bench_kem(
    ina: INA219Direct,
    tracer: PowerTracer,
    kem_name: str,
    operation: str,
    iterations: int,
    baseline_power: float,
    traces_dir: Path,
) -> Optional[EnergyResult]:
    KeyEncapsulation, _ = _import_oqs()
    print(f"  {kem_name} / {operation} ({iterations} iters)...")

    # Warmup + validate
    try:
        kem = KeyEncapsulation(kem_name)
        pk = kem.generate_keypair()
        ct, ss = kem.encap_secret(pk)
        _ = kem.decap_secret(ct)
    except Exception as e:
        print(f"    SKIP: {e}")
        return None

    for _ in range(WARMUP_ITERATIONS):
        if operation == "keygen":
            k = KeyEncapsulation(kem_name)
            k.generate_keypair()
        elif operation == "encaps":
            kem.encap_secret(pk)
        elif operation == "decaps":
            kem.decap_secret(ct)

    gc.collect()
    gc.disable()
    time.sleep(0.1)  # let system settle

    # Start power capture in background
    tracer.start()
    t0 = time.perf_counter()

    # Run crypto in tight loop — repeat batches until MIN_TRACE_DURATION_S met
    total_iters = 0
    while True:
        if operation == "keygen":
            for _ in range(iterations):
                k = KeyEncapsulation(kem_name)
                k.generate_keypair()
        elif operation == "encaps":
            for _ in range(iterations):
                kem.encap_secret(pk)
        elif operation == "decaps":
            for _ in range(iterations):
                kem.decap_secret(ct)
        total_iters += iterations
        if time.perf_counter() - t0 >= MIN_TRACE_DURATION_S:
            break

    elapsed = time.perf_counter() - t0
    trace = tracer.stop()
    gc.enable()

    return _build_result("KEM", kem_name, operation, total_iters, trace,
                         elapsed, baseline_power, traces_dir)


def bench_sig(
    ina: INA219Direct,
    tracer: PowerTracer,
    sig_name: str,
    operation: str,
    iterations: int,
    baseline_power: float,
    traces_dir: Path,
) -> Optional[EnergyResult]:
    _, Signature = _import_oqs()
    print(f"  {sig_name} / {operation} ({iterations} iters)...")

    msg = b"Benchmark message for PQC signature verification" * 4

    try:
        sig = Signature(sig_name)
        pk = sig.generate_keypair()
        signature = sig.sign(msg)
        _ = sig.verify(msg, signature, pk)
    except Exception as e:
        print(f"    SKIP: {e}")
        return None

    for _ in range(WARMUP_ITERATIONS):
        if operation == "keygen":
            s = Signature(sig_name)
            s.generate_keypair()
        elif operation == "sign":
            sig.sign(msg)
        elif operation == "verify":
            sig.verify(msg, signature, pk)

    gc.collect()
    gc.disable()
    time.sleep(0.1)

    tracer.start()
    t0 = time.perf_counter()

    total_iters = 0
    while True:
        if operation == "keygen":
            for _ in range(iterations):
                s = Signature(sig_name)
                s.generate_keypair()
        elif operation == "sign":
            for _ in range(iterations):
                sig.sign(msg)
        elif operation == "verify":
            for _ in range(iterations):
                sig.verify(msg, signature, pk)
        total_iters += iterations
        if time.perf_counter() - t0 >= MIN_TRACE_DURATION_S:
            break

    elapsed = time.perf_counter() - t0
    trace = tracer.stop()
    gc.enable()

    return _build_result("SIG", sig_name, operation, total_iters, trace,
                         elapsed, baseline_power, traces_dir)


def bench_aead(
    ina: INA219Direct,
    tracer: PowerTracer,
    aead_name: str,
    operation: str,
    iterations: int,
    baseline_power: float,
    traces_dir: Path,
    payload_size: int = 1024,
) -> Optional[EnergyResult]:
    print(f"  {aead_name} / {operation} ({iterations} iters, {payload_size}B)...")

    plaintext = os.urandom(payload_size)
    aad = b"PQ-MAVTunnel AEAD benchmark AAD"

    try:
        if aead_name == "AES-256-GCM":
            AESGCM = _get_aesgcm()
            key = os.urandom(32)
            cipher = AESGCM(key)
            nonce_enc = os.urandom(12)
            ct = cipher.encrypt(nonce_enc, plaintext, aad)

            def encrypt_fn():
                n = os.urandom(12)
                cipher.encrypt(n, plaintext, aad)

            def decrypt_fn():
                cipher.decrypt(nonce_enc, ct, aad)

        elif aead_name == "ChaCha20-Poly1305":
            ChaCha20Poly1305 = _get_chacha20()
            key = os.urandom(32)
            cipher = ChaCha20Poly1305(key)
            nonce_enc = os.urandom(12)
            ct = cipher.encrypt(nonce_enc, plaintext, aad)

            def encrypt_fn():
                n = os.urandom(12)
                cipher.encrypt(n, plaintext, aad)

            def decrypt_fn():
                cipher.decrypt(nonce_enc, ct, aad)

        elif aead_name == "Ascon-128a":
            ascon_encrypt, ascon_decrypt = _get_ascon()
            key = os.urandom(16)
            nonce = os.urandom(16)
            ct = ascon_encrypt(key, nonce, aad, plaintext, variant="Ascon-128a")

            def encrypt_fn():
                ascon_encrypt(key, nonce, aad, plaintext, variant="Ascon-128a")

            def decrypt_fn():
                ascon_decrypt(key, nonce, aad, ct, variant="Ascon-128a")

        else:
            print(f"    SKIP: Unknown AEAD {aead_name}")
            return None

        for _ in range(WARMUP_ITERATIONS):
            encrypt_fn()
            decrypt_fn()

    except Exception as e:
        print(f"    SKIP: {e}")
        return None

    gc.collect()
    gc.disable()
    time.sleep(0.1)

    tracer.start()
    t0 = time.perf_counter()

    fn = encrypt_fn if operation == "encrypt" else decrypt_fn
    total_iters = 0
    while True:
        for _ in range(iterations):
            fn()
        total_iters += iterations
        if time.perf_counter() - t0 >= MIN_TRACE_DURATION_S:
            break

    elapsed = time.perf_counter() - t0
    trace = tracer.stop()
    gc.enable()

    op_label = f"{operation}_{payload_size}B"
    return _build_result("AEAD", aead_name, op_label, total_iters, trace,
                         elapsed, baseline_power, traces_dir)


def _build_result(
    ptype: str, algo: str, operation: str, iterations: int,
    trace: list[tuple[float, float]], elapsed: float,
    baseline_power: float, traces_dir: Path,
) -> Optional[EnergyResult]:
    """Build EnergyResult from a power trace."""
    if len(trace) < 2:
        print(f"    WARNING: Only {len(trace)} samples — result unreliable")
        if not trace:
            return None

    dur, avg_power, n_samples, rate = trace_stats(trace)
    energy = integrate_energy(trace)
    net_power = max(0, avg_power - baseline_power)
    net_energy = max(0, energy - baseline_power * dur)

    safe_name = algo.replace("+", "plus").replace("-", "_").replace(" ", "_")
    csv_name = f"trace_{safe_name}_{operation}.csv"
    csv_path = traces_dir / csv_name
    save_trace_csv(trace, csv_path)

    per_op_net_e = net_energy / iterations if iterations > 0 else 0

    result = EnergyResult(
        primitive_type=ptype,
        algorithm=algo,
        operation=operation,
        iterations=iterations,
        total_samples=n_samples,
        sample_rate_hz=round(rate, 1),
        total_duration_s=round(dur, 4),
        per_op_duration_ms=round(elapsed / iterations * 1000, 3),
        baseline_power_w=round(baseline_power, 4),
        avg_gross_power_w=round(avg_power, 4),
        avg_net_power_w=round(net_power, 4),
        total_gross_energy_j=round(energy, 6),
        total_net_energy_j=round(net_energy, 6),
        per_op_net_energy_j=round(per_op_net_e, 9),
        per_op_net_energy_uj=round(per_op_net_e * 1e6, 3),
        csv_path=str(csv_path),
    )
    print(f"    {dur:.2f}s, {n_samples} samples @ {rate:.0f} Hz, "
          f"net {net_power:.3f}W, {result.per_op_net_energy_uj:.1f} uJ/op")
    return result


def print_summary_table(results: list[EnergyResult]):
    print("\n" + "=" * 120)
    print(f"{'Type':<6} {'Algorithm':<30} {'Operation':<20} {'Iters':>5} "
          f"{'ms/op':>8} {'Gross W':>8} {'Net W':>8} {'Net uJ/op':>12} "
          f"{'Samples':>8} {'Hz':>7}")
    print("-" * 120)
    current_type = ""
    for r in results:
        if r.primitive_type != current_type:
            if current_type:
                print("-" * 120)
            current_type = r.primitive_type
        print(f"{r.primitive_type:<6} {r.algorithm:<30} {r.operation:<20} "
              f"{r.iterations:>5} {r.per_op_duration_ms:>8.3f} "
              f"{r.avg_gross_power_w:>8.4f} {r.avg_net_power_w:>8.4f} "
              f"{r.per_op_net_energy_uj:>12.3f} {r.total_samples:>8} "
              f"{r.sample_rate_hz:>7.0f}")
    print("=" * 120)


def main():
    parser = argparse.ArgumentParser(
        description="INA219 energy benchmarking for PQC primitives (threaded)")
    parser.add_argument("-n", "--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("-o", "--output-dir", type=str, default="energy_bench_results")
    parser.add_argument("--kem-only", action="store_true")
    parser.add_argument("--sig-only", action="store_true")
    parser.add_argument("--aead-only", action="store_true")
    parser.add_argument("--skip-mceliece", action="store_true",
                        help="Skip Classic-McEliece (very slow keygen)")
    parser.add_argument("--aead-payload", type=int, default=1024)
    parser.add_argument("--baseline-duration", type=float, default=BASELINE_DURATION_S)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    traces_dir = output_dir / "traces"
    traces_dir.mkdir(parents=True, exist_ok=True)

    do_all = not (args.kem_only or args.sig_only or args.aead_only)

    print("=" * 70)
    print("INA219 Energy Benchmarking for PQC Primitives (Threaded)")
    print(f"  Cal={CAL_VALUE}, Current_LSB={CURRENT_LSB_A*1e6:.0f}uA, "
          f"Power_LSB={POWER_LSB_W*1000:.1f}mW, VBUS_GAIN={VBUS_GAIN}")
    print(f"  Iterations: {args.iterations}")
    print(f"  Output: {output_dir}")
    print("=" * 70)

    print("\nInitializing INA219...")
    ina = INA219Direct()
    tracer = PowerTracer(ina)

    # Quick verification read
    p, c, v = ina.read_all()
    print(f"  Quick read: {v:.3f}V, {c*1000:.1f}mA, {p:.4f}W")

    # Measure sampling rate
    print("  Measuring sustained sampling rate...")
    tracer.start()
    time.sleep(1.0)
    rate_trace = tracer.stop()
    if len(rate_trace) > 1:
        rate_dur = rate_trace[-1][0] - rate_trace[0][0]
        sustained_hz = len(rate_trace) / rate_dur if rate_dur > 0 else 0
        print(f"  Sustained rate: {sustained_hz:.0f} Hz "
              f"({len(rate_trace)} samples in {rate_dur:.2f}s)")

    # Baseline
    print("\n--- BASELINE ---")
    baseline_power = measure_baseline(ina, tracer, duration_s=args.baseline_duration)

    results: list[EnergyResult] = []

    # =========================================================
    # KEM Benchmarks
    # =========================================================
    if do_all or args.kem_only:
        print("\n--- KEM BENCHMARKS ---")
        kems = TARGET_KEMS
        if args.skip_mceliece:
            kems = [k for k in kems if "McEliece" not in k]

        for kem_name in kems:
            print(f"\n[KEM] {kem_name}")
            bl = measure_baseline(ina, tracer, duration_s=1.0)
            baseline_power = (baseline_power + bl) / 2.0

            for op in ["keygen", "encaps", "decaps"]:
                r = bench_kem(ina, tracer, kem_name, op,
                              args.iterations, baseline_power, traces_dir)
                if r:
                    results.append(r)

    # =========================================================
    # Signature Benchmarks
    # =========================================================
    if do_all or args.sig_only:
        print("\n--- SIGNATURE BENCHMARKS ---")
        for sig_name in TARGET_SIGS:
            print(f"\n[SIG] {sig_name}")
            bl = measure_baseline(ina, tracer, duration_s=1.0)
            baseline_power = (baseline_power + bl) / 2.0

            for op in ["keygen", "sign", "verify"]:
                r = bench_sig(ina, tracer, sig_name, op,
                              args.iterations, baseline_power, traces_dir)
                if r:
                    results.append(r)

    # =========================================================
    # AEAD Benchmarks
    # =========================================================
    if do_all or args.aead_only:
        print("\n--- AEAD BENCHMARKS ---")
        for aead_name in TARGET_AEADS:
            print(f"\n[AEAD] {aead_name}")
            bl = measure_baseline(ina, tracer, duration_s=1.0)
            baseline_power = (baseline_power + bl) / 2.0

            for op in ["encrypt", "decrypt"]:
                r = bench_aead(ina, tracer, aead_name, op,
                               args.iterations, baseline_power, traces_dir,
                               payload_size=args.aead_payload)
                if r:
                    results.append(r)

    # =========================================================
    # Output
    # =========================================================
    print_summary_table(results)

    json_path = output_dir / "energy_results.json"
    with open(json_path, "w") as f:
        json.dump({
            "metadata": {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "cal_value": CAL_VALUE,
                "current_lsb_ua": CURRENT_LSB_A * 1e6,
                "power_lsb_mw": POWER_LSB_W * 1000,
                "vbus_gain": VBUS_GAIN,
                "iterations": args.iterations,
                "aead_payload_bytes": args.aead_payload,
                "baseline_power_w": round(baseline_power, 4),
            },
            "results": [asdict(r) for r in results],
        }, f, indent=2)
    print(f"\nResults saved to {json_path}")

    csv_path = output_dir / "energy_summary.csv"
    with open(csv_path, "w", newline="") as f:
        if results:
            w = csv.DictWriter(f, fieldnames=list(asdict(results[0]).keys()))
            w.writeheader()
            for r in results:
                w.writerow(asdict(r))
    print(f"Summary CSV saved to {csv_path}")

    ina.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
