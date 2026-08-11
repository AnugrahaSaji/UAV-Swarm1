#!/usr/bin/env python3
"""
DDoS Model Power & Inference Benchmark
=======================================
Comprehensive comparison of LightGBM, XGBoost, and RandomForest
on Raspberry Pi 4 with INA219 power measurement.

Phases:
  1. BASELINE — idle power for --duration seconds
  2. LightGBM — continuous inference + power
  3. XGBoost  — continuous inference + power
  4. RandomForest — continuous inference + power

Reports per model:
  - Inference latency: mean / median / p95 / p99
  - INA219 power: avg mW, delta above baseline, energy per inference
  - CPU utilisation, temperature, memory
  - Model metadata: size, load time, features, classes

Requires INA219 on I2C bus 1, addr 0x40, shunt 0.1 Ohm.

Usage:
    python bench_power_inference.py
    python bench_power_inference.py --duration 15
    python bench_power_inference.py --duration 10 --warmup 50
"""

import argparse
import json
import os
import pickle
import statistics
import sys
import time
import warnings
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_DIR))

from features import FEATURE_NAMES, generate_synthetic_features

# ── Constants ────────────────────────────────────────────────────────
MODEL_PATHS = {
    "LightGBM": _DIR / "models" / "lgbm_model.pkl",
    "XGBoost": _DIR / "models" / "xgb_model.pkl",
    "RandomForest": _DIR / "models" / "rf_model.pkl",
    "TST": _DIR / "models" / "tst_model.pth",
}

DEFAULT_DURATION = 10
DEFAULT_WARMUP = 100
TEMPERATURE = 1.5
INA219_HZ = 100  # sampling rate


# ── INA219 Power Monitor ────────────────────────────────────────────
class PowerMonitor:
    """INA219 power sensor — pi-ina219 or adafruit backend."""

    def __init__(self):
        self.available = False
        self._backend = "none"
        self._ina = None
        self._samples: List[dict] = []
        self._thread: Optional[Thread] = None
        self._stop = Event()
        self._init()

    def _init(self):
        try:
            from ina219 import INA219
            self._ina = INA219(shunt_ohms=0.1, max_expected_amps=3.0,
                               busnum=1, address=0x40)
            self._ina.configure(self._ina.RANGE_32V, self._ina.GAIN_AUTO)
            self._ina.voltage()
            self.available = True
            self._backend = "pi-ina219"
            return
        except Exception:
            pass
        try:
            import board, busio
            from adafruit_ina219 import INA219 as Ada
            i2c = busio.I2C(board.SCL, board.SDA)
            self._ina = Ada(i2c)
            _ = self._ina.bus_voltage
            self.available = True
            self._backend = "adafruit"
            return
        except Exception:
            pass

    def read_once(self) -> dict:
        if not self.available:
            return {}
        try:
            if self._backend == "pi-ina219":
                v = self._ina.voltage()
                c = abs(self._ina.current())
                p = abs(self._ina.power())
            else:
                v = self._ina.bus_voltage + self._ina.shunt_voltage / 1000.0
                c = abs(self._ina.current)
                p = v * c if c else 0
            return {"voltage_v": v, "current_ma": c, "power_mw": p,
                    "ts_ns": time.time_ns()}
        except Exception:
            return {}

    def start_continuous(self):
        if not self.available:
            return
        self._samples = []
        self._stop.clear()
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        interval = 1.0 / INA219_HZ
        while not self._stop.is_set():
            s = self.read_once()
            if s.get("power_mw") is not None:
                self._samples.append(s)
            time.sleep(interval)

    def stop_continuous(self) -> List[dict]:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        out = self._samples[:]
        self._samples = []
        return out


# ── CPU Monitor ──────────────────────────────────────────────────────
class CpuMonitor:
    def __init__(self, interval: float = 0.5):
        self._interval = interval
        self._readings: List[float] = []
        self._thread: Optional[Thread] = None
        self._stop = Event()

    def _read(self):
        try:
            with open("/proc/stat") as f:
                parts = f.readline().split()
            idle = int(parts[4])
            total = sum(int(x) for x in parts[1:])
            return idle, total
        except Exception:
            return None

    def start(self):
        self._readings = []
        self._stop.clear()
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        prev = self._read()
        while not self._stop.is_set():
            time.sleep(self._interval)
            cur = self._read()
            if prev and cur:
                di = cur[0] - prev[0]
                dt = cur[1] - prev[1]
                if dt > 0:
                    self._readings.append(100.0 * (1.0 - di / dt))
            prev = cur

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if not self._readings:
            return 0.0, 0.0
        return statistics.mean(self._readings), max(self._readings)


# ── System helpers ───────────────────────────────────────────────────
def cpu_temp():
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None


def cpu_freq():
    try:
        with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return 0.0


def mem_rss():
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) / 1024.0
        return 0.0
    except Exception:
        return 0.0


def perf_governor():
    try:
        import glob
        for p in glob.glob(
                "/sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"):
            try:
                with open(p, "w") as f:
                    f.write("performance")
            except PermissionError:
                pass
        with open(
                "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") as f:
            return f.read().strip()
    except Exception:
        return "unknown"


def collect_env() -> dict:
    import platform
    env = {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "cpu_temp_c": cpu_temp(),
        "cpu_freq_mhz": cpu_freq(),
    }
    for mod in ("lightgbm", "xgboost", "sklearn"):
        try:
            env[f"{mod}_version"] = __import__(mod).__version__
        except ImportError:
            pass
    return env


# ── Phase result ─────────────────────────────────────────────────────
@dataclass
class PhaseResult:
    phase: str
    model_name: str
    duration_s: float
    iterations: int

    # Latency (ms)
    mean_ms: float = 0.0
    median_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    stdev_ms: float = 0.0
    throughput_hz: float = 0.0

    # Power
    avg_power_mw: Optional[float] = None
    avg_voltage_v: Optional[float] = None
    avg_current_ma: Optional[float] = None
    power_delta_mw: Optional[float] = None
    energy_per_inference_mj: Optional[float] = None
    total_energy_mj: Optional[float] = None
    power_samples: int = 0

    # CPU / system
    cpu_avg_pct: float = 0.0
    cpu_peak_pct: float = 0.0
    temp_c: Optional[float] = None
    cpu_freq_mhz: float = 0.0
    mem_rss_mb: float = 0.0

    # Model metadata
    model_size_mb: float = 0.0
    load_time_s: float = 0.0
    n_features: int = 54
    n_classes: int = 15


# ── Baseline phase ───────────────────────────────────────────────────
def run_baseline(dur: float, pwr: PowerMonitor, cpu: CpuMonitor) -> PhaseResult:
    print(f"\n{'=' * 60}")
    print(f"  PHASE: BASELINE (idle, {dur}s)")
    print(f"{'=' * 60}")

    pwr.start_continuous()
    cpu.start()
    t0 = time.monotonic()
    while time.monotonic() - t0 < dur:
        time.sleep(0.1)
    elapsed = time.monotonic() - t0
    samples = pwr.stop_continuous()
    ca, cp = cpu.stop()

    ap = av = ac = None
    if samples:
        pw = [s["power_mw"] for s in samples if s.get("power_mw") is not None]
        vv = [s["voltage_v"] for s in samples if s.get("voltage_v") is not None]
        cc = [s["current_ma"] for s in samples if s.get("current_ma") is not None]
        if pw: ap = statistics.mean(pw)
        if vv: av = statistics.mean(vv)
        if cc: ac = statistics.mean(cc)

    r = PhaseResult(
        phase="BASELINE", model_name="idle",
        duration_s=round(elapsed, 2), iterations=0,
        avg_power_mw=round(ap, 2) if ap else None,
        avg_voltage_v=round(av, 3) if av else None,
        avg_current_ma=round(ac, 2) if ac else None,
        power_samples=len(samples),
        cpu_avg_pct=round(ca, 1), cpu_peak_pct=round(cp, 1),
        temp_c=cpu_temp(), cpu_freq_mhz=cpu_freq(),
        mem_rss_mb=round(mem_rss(), 1),
    )
    ps = f"{ap:.0f} mW" if ap else "N/A"
    print(f"  Power : {ps}  ({len(samples)} samples)")
    print(f"  CPU   : {ca:.1f}% avg  {cp:.1f}% peak")
    t = r.temp_c
    print(f"  Temp  : {t:.1f} C" if t else "  Temp  : N/A")
    return r


# ── Inference phase ──────────────────────────────────────────────────
def run_inference(name: str, path: Path, dur: float, warmup: int,
                  pwr: PowerMonitor, cpu: CpuMonitor,
                  baseline_mw: Optional[float]) -> PhaseResult:
    print(f"\n{'=' * 60}")
    print(f"  PHASE: {name} ({dur}s)")
    print(f"{'=' * 60}")

    # Load
    print(f"  Loading...", end=" ", flush=True)
    tl = time.monotonic()
    with open(path, "rb") as f:
        bundle = pickle.load(f)
    load_s = time.monotonic() - tl
    model = bundle["model"]
    scaler = bundle["scaler"]
    sz = path.stat().st_size / (1024 * 1024)
    print(f"{load_s:.2f}s  ({sz:.1f} MB)")

    # Prepare input
    feat = generate_synthetic_features(n=1, attack=False)[0]
    df = pd.DataFrame([feat]).reindex(columns=FEATURE_NAMES, fill_value=0)
    X = scaler.transform(df)

    # Warmup
    print(f"  Warmup ({warmup})...", end=" ", flush=True)
    for _ in range(warmup):
        raw = model.predict_proba(X)[0]
        logits = np.log(raw + 1e-10)
        scaled = np.exp(logits / TEMPERATURE)
        _ = scaled / scaled.sum()
    print("done")

    # Timed run
    print(f"  Inference...", end=" ", flush=True)
    pwr.start_continuous()
    cpu.start()
    latencies = []
    t0 = time.monotonic()
    while time.monotonic() - t0 < dur:
        ti = time.perf_counter_ns()
        raw = model.predict_proba(X)[0]
        logits = np.log(raw + 1e-10)
        scaled = np.exp(logits / TEMPERATURE)
        _ = scaled / scaled.sum()
        tf = time.perf_counter_ns()
        latencies.append((tf - ti) / 1e6)
    elapsed = time.monotonic() - t0
    samples = pwr.stop_continuous()
    ca, cp = cpu.stop()
    n = len(latencies)
    print(f"{n} iterations")

    arr = np.array(latencies)
    ap = av = ac = te = pd_mw = epi = None
    if samples:
        pw = [s["power_mw"] for s in samples if s.get("power_mw") is not None]
        vv = [s["voltage_v"] for s in samples if s.get("voltage_v") is not None]
        cc = [s["current_ma"] for s in samples if s.get("current_ma") is not None]
        if pw:
            ap = statistics.mean(pw)
            te = ap * elapsed           # mW * s = mJ
            if baseline_mw is not None:
                pd_mw = ap - baseline_mw
            if n > 0:
                epi = te / n            # mJ per inference
        if vv: av = statistics.mean(vv)
        if cc: ac = statistics.mean(cc)

    r = PhaseResult(
        phase=name, model_name=name,
        duration_s=round(elapsed, 2), iterations=n,
        mean_ms=round(float(arr.mean()), 3),
        median_ms=round(float(np.median(arr)), 3),
        p95_ms=round(float(np.percentile(arr, 95)), 3),
        p99_ms=round(float(np.percentile(arr, 99)), 3),
        min_ms=round(float(arr.min()), 3),
        max_ms=round(float(arr.max()), 3),
        stdev_ms=round(float(arr.std()), 3),
        throughput_hz=round(n / elapsed, 1),
        avg_power_mw=round(ap, 2) if ap else None,
        avg_voltage_v=round(av, 3) if av else None,
        avg_current_ma=round(ac, 2) if ac else None,
        power_delta_mw=round(pd_mw, 2) if pd_mw is not None else None,
        energy_per_inference_mj=round(epi, 6) if epi else None,
        total_energy_mj=round(te, 2) if te else None,
        power_samples=len(samples),
        cpu_avg_pct=round(ca, 1), cpu_peak_pct=round(cp, 1),
        temp_c=cpu_temp(), cpu_freq_mhz=cpu_freq(),
        mem_rss_mb=round(mem_rss(), 1),
        model_size_mb=round(sz, 1), load_time_s=round(load_s, 2),
    )

    ps = f"{ap:.0f} mW" if ap else "N/A"
    ds = f"+{pd_mw:.0f} mW" if pd_mw is not None else "N/A"
    es = f"{epi:.4f} mJ" if epi else "N/A"
    print(f"  Latency : {r.mean_ms:.3f} ms mean  {r.median_ms:.3f} ms median")
    print(f"  P95/P99 : {r.p95_ms:.3f} / {r.p99_ms:.3f} ms")
    print(f"  Power   : {ps}  (delta: {ds})")
    print(f"  E/infer : {es}")
    print(f"  CPU     : {ca:.1f}% avg  {cp:.1f}% peak")
    t = r.temp_c
    print(f"  Temp    : {t:.1f} C" if t else "  Temp    : N/A")
    return r


# ── TST Inference phase ──────────────────────────────────────────────
def run_inference_tst(name: str, path: Path, dur: float, warmup: int,
                     pwr: PowerMonitor, cpu: CpuMonitor,
                     baseline_mw: Optional[float]) -> PhaseResult:
    """Run inference benchmark for PyTorch Transformer model."""
    import torch
    from tst import TransformerIDS, TST_FEATURE_NAMES

    print(f"\n{'=' * 60}")
    print(f"  PHASE: {name} ({dur}s)")
    print(f"{'=' * 60}")

    # Load
    print(f"  Loading...", end=" ", flush=True)
    tl = time.monotonic()
    checkpoint = torch.load(str(path), map_location="cpu", weights_only=False)
    model = TransformerIDS(
        input_dim=46, num_classes=checkpoint["num_classes"],
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    scaler = checkpoint["scaler"]
    load_s = time.monotonic() - tl
    sz = path.stat().st_size / (1024 * 1024)
    n_classes = checkpoint["num_classes"]
    print(f"{load_s:.2f}s  ({sz:.1f} MB)")

    # Prepare input — 46 features (no MQTT)
    feat = generate_synthetic_features(n=1, attack=False)[0]
    df = pd.DataFrame([feat]).reindex(columns=TST_FEATURE_NAMES, fill_value=0)
    X = scaler.transform(df)
    X_tensor = torch.FloatTensor(X)

    # Warmup
    print(f"  Warmup ({warmup})...", end=" ", flush=True)
    with torch.no_grad():
        for _ in range(warmup):
            logits = model(X_tensor)
            _ = torch.softmax(logits, dim=1)
    print("done")

    # Timed run
    print(f"  Inference...", end=" ", flush=True)
    pwr.start_continuous()
    cpu.start()
    latencies = []
    t0 = time.monotonic()
    with torch.no_grad():
        while time.monotonic() - t0 < dur:
            ti = time.perf_counter_ns()
            logits = model(X_tensor)
            _ = torch.softmax(logits, dim=1)
            tf = time.perf_counter_ns()
            latencies.append((tf - ti) / 1e6)
    elapsed = time.monotonic() - t0
    samples = pwr.stop_continuous()
    ca, cp = cpu.stop()
    n = len(latencies)
    print(f"{n} iterations")

    arr = np.array(latencies)
    ap = av = ac = te = pd_mw = epi = None
    if samples:
        pw = [s["power_mw"] for s in samples if s.get("power_mw") is not None]
        vv = [s["voltage_v"] for s in samples if s.get("voltage_v") is not None]
        cc = [s["current_ma"] for s in samples if s.get("current_ma") is not None]
        if pw:
            ap = statistics.mean(pw)
            te = ap * elapsed
            if baseline_mw is not None:
                pd_mw = ap - baseline_mw
            if n > 0:
                epi = te / n
        if vv: av = statistics.mean(vv)
        if cc: ac = statistics.mean(cc)

    r = PhaseResult(
        phase=name, model_name=name,
        duration_s=round(elapsed, 2), iterations=n,
        mean_ms=round(float(arr.mean()), 3),
        median_ms=round(float(np.median(arr)), 3),
        p95_ms=round(float(np.percentile(arr, 95)), 3),
        p99_ms=round(float(np.percentile(arr, 99)), 3),
        min_ms=round(float(arr.min()), 3),
        max_ms=round(float(arr.max()), 3),
        stdev_ms=round(float(arr.std()), 3),
        throughput_hz=round(n / elapsed, 1),
        avg_power_mw=round(ap, 2) if ap else None,
        avg_voltage_v=round(av, 3) if av else None,
        avg_current_ma=round(ac, 2) if ac else None,
        power_delta_mw=round(pd_mw, 2) if pd_mw is not None else None,
        energy_per_inference_mj=round(epi, 6) if epi else None,
        total_energy_mj=round(te, 2) if te else None,
        power_samples=len(samples),
        cpu_avg_pct=round(ca, 1), cpu_peak_pct=round(cp, 1),
        temp_c=cpu_temp(), cpu_freq_mhz=cpu_freq(),
        mem_rss_mb=round(mem_rss(), 1),
        model_size_mb=round(sz, 1), load_time_s=round(load_s, 2),
        n_features=46, n_classes=n_classes,
    )

    ps = f"{ap:.0f} mW" if ap else "N/A"
    ds = f"+{pd_mw:.0f} mW" if pd_mw is not None else "N/A"
    es = f"{epi:.4f} mJ" if epi else "N/A"
    print(f"  Latency : {r.mean_ms:.3f} ms mean  {r.median_ms:.3f} ms median")
    print(f"  P95/P99 : {r.p95_ms:.3f} / {r.p99_ms:.3f} ms")
    print(f"  Power   : {ps}  (delta: {ds})")
    print(f"  E/infer : {es}")
    print(f"  CPU     : {ca:.1f}% avg  {cp:.1f}% peak")
    t = r.temp_c
    print(f"  Temp    : {t:.1f} C" if t else "  Temp    : N/A")
    return r


# ── Comparison table ─────────────────────────────────────────────────
def print_comparison(base: PhaseResult, results: List[PhaseResult]):
    W = 78
    print(f"\n{'=' * W}")
    print("  COMPREHENSIVE MODEL COMPARISON")
    print(f"{'=' * W}")

    # Latency
    print(f"\n  LATENCY (ms)")
    print(f"  {'Model':<15} {'Mean':>8} {'Median':>8} {'P95':>8} "
          f"{'P99':>8} {'Tput':>9}")
    print(f"  {'-' * 15} {'-' * 8} {'-' * 8} {'-' * 8} "
          f"{'-' * 8} {'-' * 9}")
    for r in results:
        print(f"  {r.model_name:<15} {r.mean_ms:>8.3f} {r.median_ms:>8.3f} "
              f"{r.p95_ms:>8.3f} {r.p99_ms:>8.3f} {r.throughput_hz:>7.1f}/s")

    # Power
    print(f"\n  POWER (INA219)")
    print(f"  {'Model':<15} {'Avg mW':>8} {'Delta':>8} "
          f"{'E/inf mJ':>10} {'Total mJ':>10}")
    print(f"  {'-' * 15} {'-' * 8} {'-' * 8} {'-' * 10} {'-' * 10}")
    if base.avg_power_mw:
        print(f"  {'BASELINE':<15} {base.avg_power_mw:>7.0f}  "
              f"{'---':>8} {'---':>10} {'---':>10}")
    for r in results:
        pw = f"{r.avg_power_mw:.0f}" if r.avg_power_mw else "N/A"
        dl = f"+{r.power_delta_mw:.0f}" if r.power_delta_mw is not None else "N/A"
        ei = f"{r.energy_per_inference_mj:.4f}" if r.energy_per_inference_mj else "N/A"
        et = f"{r.total_energy_mj:.0f}" if r.total_energy_mj else "N/A"
        print(f"  {r.model_name:<15} {pw:>8} {dl:>8} {ei:>10} {et:>10}")

    # CPU / system
    print(f"\n  SYSTEM")
    print(f"  {'Model':<15} {'CPU%':>6} {'Peak%':>6} "
          f"{'Temp C':>7} {'RSS MB':>7}")
    print(f"  {'-' * 15} {'-' * 6} {'-' * 6} {'-' * 7} {'-' * 7}")
    print(f"  {'BASELINE':<15} {base.cpu_avg_pct:>5.1f}  {base.cpu_peak_pct:>5.1f}  "
          f"{(base.temp_c or 0):>6.1f}  {base.mem_rss_mb:>6.1f}")
    for r in results:
        print(f"  {r.model_name:<15} {r.cpu_avg_pct:>5.1f}  {r.cpu_peak_pct:>5.1f}  "
              f"{(r.temp_c or 0):>6.1f}  {r.mem_rss_mb:>6.1f}")

    # Speedup
    if len(results) >= 2:
        fastest = min(r.mean_ms for r in results)
        print(f"\n  SPEEDUP (vs fastest)")
        for r in results:
            ratio = r.mean_ms / max(fastest, 1e-6)
            print(f"    {r.model_name}: {ratio:.1f}x")

    # Model info
    print(f"\n  MODEL INFO")
    print(f"  {'Model':<15} {'Size MB':>8} {'Load s':>7} "
          f"{'Features':>9} {'Classes':>8}")
    print(f"  {'-' * 15} {'-' * 8} {'-' * 7} {'-' * 9} {'-' * 8}")
    for r in results:
        print(f"  {r.model_name:<15} {r.model_size_mb:>7.1f}  {r.load_time_s:>6.2f}  "
              f"{r.n_features:>9} {r.n_classes:>8}")

    print(f"\n{'=' * W}")


# ── Main ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="DDoS Model Power & Inference Benchmark")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION,
                        help=f"Seconds per phase (default {DEFAULT_DURATION})")
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP,
                        help=f"Warmup iterations (default {DEFAULT_WARMUP})")
    parser.add_argument("--models", nargs="+",
                        choices=list(MODEL_PATHS.keys()),
                        default=list(MODEL_PATHS.keys()),
                        help="Models to benchmark")
    args = parser.parse_args()

    print(f"\n-- Setting CPU governor --")
    gov = perf_governor()
    print(f"  Governor : {gov}")
    print(f"  CPU freq : {cpu_freq():.0f} MHz")

    pm = PowerMonitor()
    print(f"  INA219   : "
          f"{'available (' + pm._backend + ')' if pm.available else 'NOT detected'}")
    if pm.available:
        snap = pm.read_once()
        print(f"  Snapshot : {snap.get('voltage_v', 0):.2f} V  "
              f"{snap.get('current_ma', 0):.0f} mA  "
              f"{snap.get('power_mw', 0):.0f} mW")

    cm = CpuMonitor()

    models = [(n, MODEL_PATHS[n]) for n in args.models
              if MODEL_PATHS[n].exists()]
    missing = [n for n in args.models if not MODEL_PATHS[n].exists()]
    for m in missing:
        print(f"  SKIP {m}: model not found")
    if not models:
        print("ERROR: no models available")
        sys.exit(1)

    est = args.duration * (1 + len(models))
    print(f"\n{'=' * 60}")
    print(f"  DDoS MODEL POWER & INFERENCE BENCHMARK")
    print(f"{'=' * 60}")
    print(f"  Models   : {', '.join(n for n, _ in models)}")
    print(f"  Duration : {args.duration}s / phase")
    print(f"  Warmup   : {args.warmup} iterations")
    print(f"  Phases   : 1 baseline + {len(models)} inference")
    print(f"  Est.     : ~{est}s")

    env = collect_env()

    # Baseline
    baseline = run_baseline(args.duration, pm, cm)

    # Inference phases
    results = []
    for name, path in models:
        if name == "TST":
            r = run_inference_tst(name, path, args.duration, args.warmup,
                                 pm, cm, baseline.avg_power_mw)
        else:
            r = run_inference(name, path, args.duration, args.warmup,
                              pm, cm, baseline.avg_power_mw)
        results.append(r)

    print_comparison(baseline, results)

    # Save JSON
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = _DIR.parent / "bench_ddos_results" / f"power_{ts}"
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": env,
        "config": {
            "duration_s": args.duration,
            "warmup": args.warmup,
            "models": [n for n, _ in models],
            "power_sensor": pm.available,
            "power_backend": pm._backend,
        },
        "baseline": asdict(baseline),
        "results": [asdict(r) for r in results],
    }
    out_file = out_dir / "results.json"
    out_file.write_text(json.dumps(payload, indent=2, default=str))
    print(f"\n  Results -> {out_file}")
    print("DONE.")


if __name__ == "__main__":
    main()
