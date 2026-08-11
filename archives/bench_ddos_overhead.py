#!/usr/bin/env python3
"""
DDoS Detector Overhead Benchmark
=================================
Measures the performance overhead of running XGBoost / TST DDoS detectors
alongside PQC suite-handshake benchmarking on the Raspberry Pi.

Three phases:
  1. BASELINE — 72 suites × 10 s handshake benchmark, no detector
  2. + XGB    — xgb.py running in background + same benchmark
  3. + TST    — tst.py running in background (5 min warm-up) + same benchmark

Each suite is benchmarked for --duration seconds of continuous handshaking.
CPU / memory / temperature are sampled during each suite.

Output:
  bench_ddos_results/<timestamp>/
    baseline.json
    xgb.json
    tst.json
    comparison.json          ← delta summary

Usage (on Raspberry Pi, requires root for scapy in detectors):
    sudo ~/nenv/bin/python bench_ddos_overhead.py
    sudo ~/nenv/bin/python bench_ddos_overhead.py --duration 5
    sudo ~/nenv/bin/python bench_ddos_overhead.py --suites 10  # first N suites
"""

import argparse
import json
import os
import signal
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# ── OQS imports (same compat as benchmark_pqc.py) ────────────────────
# liboqs-python may be installed in a non-standard location.  Add it to
# sys.path BEFORE importing anything that needs oqs.
_LIBOQS_PYTHON_DIR = os.environ.get(
    "LIBOQS_PYTHON_DIR",
    os.path.expanduser("~/quantum-safe/liboqs-python"),
)
if os.path.isdir(_LIBOQS_PYTHON_DIR) and _LIBOQS_PYTHON_DIR not in sys.path:
    sys.path.insert(0, _LIBOQS_PYTHON_DIR)

def _init_oqs():
    """Return (KeyEncapsulation, Signature) classes."""
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

# ── Configuration ─────────────────────────────────────────────────────
DDOS_DIR = ROOT / "ddos"
XGB_SCRIPT = DDOS_DIR / "xgb.py"
TST_SCRIPT = DDOS_DIR / "tst.py"
PYTHON = sys.executable
# Detectors need torch/scapy from nenv; fall back to current interpreter
# Use absolute path – expanduser("~") returns /root under sudo
DETECTOR_PYTHON = os.environ.get(
    "DETECTOR_PYTHON",
    "/home/dev/nenv/bin/python",
)
if not os.path.isfile(DETECTOR_PYTHON):
    DETECTOR_PYTHON = PYTHON
TST_WARMUP_S = 300  # 5 minutes
DEFAULT_DURATION = 10  # seconds per suite


# =====================================================================
# System metrics helpers
# =====================================================================

def read_cpu_temp() -> Optional[float]:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            return int(f.read().strip()) / 1000.0
    except Exception:
        return None


def read_cpu_percent() -> float:
    """Quick ~0.1 s CPU sample via /proc/stat."""
    try:
        def _read():
            with open("/proc/stat") as f:
                parts = f.readline().split()
            idle = int(parts[4])
            total = sum(int(p) for p in parts[1:])
            return idle, total
        idle0, total0 = _read()
        time.sleep(0.1)
        idle1, total1 = _read()
        d_idle = idle1 - idle0
        d_total = total1 - total0
        return (1.0 - d_idle / max(d_total, 1)) * 100.0
    except Exception:
        return 0.0


def read_mem_rss_mb() -> float:
    try:
        import resource
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0
    except Exception:
        return 0.0


def read_load_avg() -> float:
    try:
        return os.getloadavg()[0]
    except Exception:
        return 0.0


# =====================================================================
# Single-suite handshake benchmark (time-based)
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
    handshake_times_us: List[float]  # each iteration wall-time in µs
    mean_us: float = 0.0
    median_us: float = 0.0
    p95_us: float = 0.0
    p99_us: float = 0.0
    stdev_us: float = 0.0
    min_us: float = 0.0
    max_us: float = 0.0
    throughput_hz: float = 0.0
    cpu_avg: float = 0.0
    temp_c: float = 0.0
    load_avg: float = 0.0
    error: Optional[str] = None


def benchmark_suite(suite_id: str, duration_s: float) -> SuiteResult:
    """Run handshake loop for *duration_s* seconds and return statistics."""
    suite_cfg = get_suite(suite_id)
    sig_name = suite_cfg["sig_name"]

    # One-time: generate GCS signing keypair
    gcs_sig = Signature(sig_name)
    gcs_sig_pub = gcs_sig.generate_keypair()

    times_us: List[float] = []
    errors = 0
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
                "client", hello.session_id, hello.kem_name,
                hello.sig_name, drone_shared)
            derive_transport_keys(
                "server", eph.session_id, eph.kem_name.encode(),
                eph.sig_name.encode(), gcs_shared)
        except Exception:
            errors += 1
            continue
        t1 = time.perf_counter_ns()
        times_us.append((t1 - t0) / 1_000)

    elapsed = time.monotonic() - t_start

    if not times_us:
        return SuiteResult(
            suite_id=suite_id,
            kem=suite_cfg.get("kem_name", ""),
            sig=suite_cfg.get("sig_name", ""),
            aead=suite_cfg.get("aead_name", ""),
            nist_level=suite_cfg.get("nist_level", ""),
            duration_s=elapsed,
            iterations=0,
            handshake_times_us=[],
            error=f"{errors} errors, 0 successful",
        )

    sorted_t = sorted(times_us)
    n = len(sorted_t)

    return SuiteResult(
        suite_id=suite_id,
        kem=suite_cfg.get("kem_name", ""),
        sig=suite_cfg.get("sig_name", ""),
        aead=suite_cfg.get("aead_name", ""),
        nist_level=suite_cfg.get("nist_level", ""),
        duration_s=elapsed,
        iterations=n,
        handshake_times_us=[],  # omit raw times from JSON (large)
        mean_us=statistics.mean(sorted_t),
        median_us=sorted_t[n // 2],
        p95_us=sorted_t[int(n * 0.95)],
        p99_us=sorted_t[int(n * 0.99)],
        stdev_us=statistics.stdev(sorted_t) if n > 1 else 0.0,
        min_us=sorted_t[0],
        max_us=sorted_t[-1],
        throughput_hz=n / elapsed,
        cpu_avg=read_cpu_percent(),
        temp_c=read_cpu_temp() or 0.0,
        load_avg=read_load_avg(),
    )


# =====================================================================
# Phase runner
# =====================================================================

def run_phase(phase_name: str, suites: List[str], duration: float,
              out_dir: Path) -> Dict[str, Any]:
    """Benchmark every suite for *duration* seconds each."""
    print(f"\n{'=' * 70}")
    print(f"  PHASE: {phase_name}")
    print(f"  Suites: {len(suites)}  |  Duration/suite: {duration}s")
    print(f"  Estimated: {len(suites) * duration / 60:.1f} min")
    print(f"{'=' * 70}\n")

    phase_start = time.monotonic()
    results: List[Dict[str, Any]] = []

    for i, sid in enumerate(suites, 1):
        print(f"  [{i:3d}/{len(suites)}]  {sid:<55s} ", end="", flush=True)
        try:
            r = benchmark_suite(sid, duration)
            results.append(asdict(r))
            if r.error:
                print(f"ERROR: {r.error}")
            else:
                print(f"{r.mean_us/1000:8.1f} ms  ({r.iterations:4d} iters)  "
                      f"CPU {r.cpu_avg:4.1f}%  {r.temp_c:.0f}°C")
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
# Detector management
# =====================================================================

def start_detector(script: Path, label: str) -> subprocess.Popen:
    """Start a detector script as a background subprocess."""
    print(f"  Starting {label} ({script.name}) via {DETECTOR_PYTHON}...",
          end="", flush=True)
    err_path = Path(f"/tmp/detector_{label.lower().replace(' ','_')}.err")
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
        print(f" FAILED (exit code {proc.returncode})")
        if err_text:
            for line in err_text.splitlines()[-5:]:
                print(f"    {line}")
        return None
    print(f" PID {proc.pid}")
    # keep err_fh open – will be closed when process terminates
    return proc


def stop_detector(proc: Optional[subprocess.Popen], label: str):
    """Terminate a detector subprocess."""
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
# Comparison
# =====================================================================

def build_comparison(baseline: Dict, xgb_data: Dict, tst_data: Dict,
                     out_dir: Path):
    """Compute per-suite deltas and aggregate overhead."""

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
        }
        if x and x.get("mean_us"):
            row["xgb_mean_ms"] = round(x["mean_us"] / 1000, 2)
            row["xgb_overhead_pct"] = round(
                (x["mean_us"] - b["mean_us"]) / b["mean_us"] * 100, 2)
            row["xgb_throughput"] = round(x["throughput_hz"], 2)
        if t and t.get("mean_us"):
            row["tst_mean_ms"] = round(t["mean_us"] / 1000, 2)
            row["tst_overhead_pct"] = round(
                (t["mean_us"] - b["mean_us"]) / b["mean_us"] * 100, 2)
            row["tst_throughput"] = round(t["throughput_hz"], 2)
        rows.append(row)

    # Aggregate
    xgb_overheads = [r["xgb_overhead_pct"] for r in rows if "xgb_overhead_pct" in r]
    tst_overheads = [r["tst_overhead_pct"] for r in rows if "tst_overhead_pct" in r]

    summary = {
        "total_suites": len(rows),
        "xgb_overhead_mean_pct": round(statistics.mean(xgb_overheads), 2) if xgb_overheads else None,
        "xgb_overhead_median_pct": round(statistics.median(xgb_overheads), 2) if xgb_overheads else None,
        "xgb_overhead_max_pct": round(max(xgb_overheads), 2) if xgb_overheads else None,
        "tst_overhead_mean_pct": round(statistics.mean(tst_overheads), 2) if tst_overheads else None,
        "tst_overhead_median_pct": round(statistics.median(tst_overheads), 2) if tst_overheads else None,
        "tst_overhead_max_pct": round(max(tst_overheads), 2) if tst_overheads else None,
    }

    comparison = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "per_suite": rows,
    }

    out_file = out_dir / "comparison.json"
    out_file.write_text(json.dumps(comparison, indent=2))

    # Pretty-print table
    print(f"\n{'=' * 90}")
    print("  COMPARISON SUMMARY")
    print(f"{'=' * 90}")
    print(f"  {'':55s} {'Baseline':>10s}  {'+ XGB':>10s}  {'+ TST':>10s}")
    print(f"  {'-' * 55} {'-' * 10}  {'-' * 10}  {'-' * 10}")

    for r in rows[:20]:  # first 20 for display
        bl = f"{r['baseline_mean_ms']:8.1f}ms"
        xg = f"{r.get('xgb_mean_ms', 0):8.1f}ms" if "xgb_mean_ms" in r else "       N/A"
        ts = f"{r.get('tst_mean_ms', 0):8.1f}ms" if "tst_mean_ms" in r else "       N/A"
        print(f"  {r['suite_id'][:55]:55s} {bl}  {xg}  {ts}")

    if len(rows) > 20:
        print(f"  ... ({len(rows) - 20} more suites)")

    print(f"\n  OVERHEAD (mean across all suites):")
    print(f"    XGBoost : {summary.get('xgb_overhead_mean_pct', 'N/A')}%  "
          f"(median {summary.get('xgb_overhead_median_pct', 'N/A')}%, "
          f"max {summary.get('xgb_overhead_max_pct', 'N/A')}%)")
    print(f"    TST     : {summary.get('tst_overhead_mean_pct', 'N/A')}%  "
          f"(median {summary.get('tst_overhead_median_pct', 'N/A')}%, "
          f"max {summary.get('tst_overhead_max_pct', 'N/A')}%)")
    print(f"\n  Results saved → {out_dir}/")
    print(f"{'=' * 90}\n")

    return comparison


# =====================================================================
# Main
# =====================================================================

def main():
    parser = argparse.ArgumentParser(
        description="DDoS Detector Overhead Benchmark")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION,
                        help="Seconds per suite (default: 10)")
    parser.add_argument("--suites", type=int, default=0,
                        help="Limit to first N suites (0 = all)")
    parser.add_argument("--skip-baseline", action="store_true",
                        help="Skip baseline phase (reuse existing)")
    parser.add_argument("--skip-xgb", action="store_true",
                        help="Skip XGBoost phase")
    parser.add_argument("--skip-tst", action="store_true",
                        help="Skip TST phase")
    parser.add_argument("--tst-warmup", type=int, default=TST_WARMUP_S,
                        help=f"TST warm-up seconds (default: {TST_WARMUP_S})")
    args = parser.parse_args()

    # Discover suites
    all_suites = sorted(list_suites().keys())
    if args.suites > 0:
        all_suites = all_suites[:args.suites]

    total_per_phase = len(all_suites) * args.duration
    tst_warmup_str = f"{args.tst_warmup}s ({args.tst_warmup / 60:.0f}min)"

    print("=" * 70)
    print("  DDoS DETECTOR OVERHEAD BENCHMARK")
    print("=" * 70)
    print(f"  Suites       : {len(all_suites)}")
    print(f"  Duration/suite: {args.duration}s")
    print(f"  Per phase    : {total_per_phase / 60:.1f} min")
    print(f"  TST warm-up  : {tst_warmup_str}")
    phases = 3 - args.skip_baseline - args.skip_xgb - args.skip_tst
    est_total = phases * total_per_phase + (args.tst_warmup if not args.skip_tst else 0)
    print(f"  Est. total   : {est_total / 60:.0f} min")
    print()

    # Verify detector scripts exist
    for script in [XGB_SCRIPT, TST_SCRIPT]:
        if not script.exists():
            print(f"ERROR: {script} not found")
            sys.exit(1)

    # Output directory
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "bench_ddos_results" / ts
    out_dir.mkdir(parents=True, exist_ok=True)

    # Save config
    config = {
        "suites": len(all_suites),
        "duration_per_suite_s": args.duration,
        "tst_warmup_s": args.tst_warmup,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": sys.executable,
        "suite_list": all_suites,
    }
    (out_dir / "config.json").write_text(json.dumps(config, indent=2))

    # ── Phase 1: Baseline ────────────────────────────────────────────
    baseline_data = None
    if not args.skip_baseline:
        baseline_data = run_phase("baseline", all_suites, args.duration, out_dir)
    else:
        # Try to load from existing
        bf = out_dir / "baseline.json"
        if bf.exists():
            baseline_data = json.loads(bf.read_text())
            print("  [baseline] Loaded from existing file")

    # ── Phase 2: + XGBoost ───────────────────────────────────────────
    xgb_data = None
    if not args.skip_xgb:
        print("\n── Starting XGBoost detector in background ──")
        xgb_proc = start_detector(XGB_SCRIPT, "XGBoost")
        if xgb_proc:
            # XGB needs 5 windows × 0.6s = 3s warmup
            print(f"  Waiting 5s for XGB warm-up...")
            time.sleep(5)
            xgb_data = run_phase("xgb", all_suites, args.duration, out_dir)
            stop_detector(xgb_proc, "XGBoost")
        else:
            print("  WARNING: XGBoost detector failed to start, skipping phase")

    # ── Phase 3: + TST ───────────────────────────────────────────────
    tst_data = None
    if not args.skip_tst:
        print("\n── Starting TST detector in background ──")
        tst_proc = start_detector(TST_SCRIPT, "TST")
        if tst_proc:
            print(f"  TST warm-up: collecting 400 windows ({tst_warmup_str})...")
            # Progress updates during warmup
            warmup_start = time.monotonic()
            while time.monotonic() - warmup_start < args.tst_warmup:
                remaining = args.tst_warmup - (time.monotonic() - warmup_start)
                print(f"\r  TST warm-up: {remaining:.0f}s remaining...  ",
                      end="", flush=True)
                time.sleep(10)
            print(f"\r  TST warm-up complete.{'':40s}")

            tst_data = run_phase("tst", all_suites, args.duration, out_dir)
            stop_detector(tst_proc, "TST")
        else:
            print("  WARNING: TST detector failed to start, skipping phase")

    # ── Comparison ───────────────────────────────────────────────────
    if baseline_data and (xgb_data or tst_data):
        build_comparison(
            baseline_data,
            xgb_data or {"results": []},
            tst_data or {"results": []},
            out_dir,
        )
    else:
        print("\n  Not enough data for comparison (need baseline + at least one detector)")

    print("DONE.")


if __name__ == "__main__":
    main()
