#!/usr/bin/env python3
"""Approved-AEAD-Profile × Detector Matrix (8 × 3)

Runs the *data-plane* Sender/Receiver encrypt/decrypt path for the eight
approved AEAD profiles under three detector scenarios:

  1) Baseline (no detector)
  2) +XGBoost detector
  3) +TST detector (with warm-up)

For each (AEAD, detector) cell, the script reports:
  - enc/dec median latency in ns (Sender.encrypt / Receiver.decrypt)
  - absolute CPU% average during the run (system-wide)
  - CPU die temperature (°C)

Intended to be run on Raspberry Pi Linux (reads /proc/stat and
/sys/class/thermal/thermal_zone0/temp). Detectors are started as background
subprocesses.

Typical usage (RPi4, as root for scapy-based detectors):
  sudo -E /home/dev/cenv/bin/python bench_aead_detector_matrix.py

Outputs:
  /tmp/aead_detector_approved_8x3.json
  /tmp/aead_detector_approved_8x3.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import signal
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


from core.aead import AeadIds, Receiver, Sender, required_key_length_for_aead
from core.config import CONFIG
from core.suites import get_suite


DDOS_DIR = ROOT / "ddos"
DEFAULT_XGB_SCRIPT = DDOS_DIR / "xgb.py"
DEFAULT_TST_SCRIPT = DDOS_DIR / "tst.py"
DEFAULT_XGB_OLD_SCRIPT = DDOS_DIR / "xgb_old.py"
DEFAULT_TST_OLD_SCRIPT = DDOS_DIR / "tst_old.py"

DETECTOR_PYTHON = os.environ.get("DETECTOR_PYTHON", "/home/dev/nenv/bin/python")
if not os.path.isfile(DETECTOR_PYTHON):
    DETECTOR_PYTHON = sys.executable


def read_cpu_temp_c() -> Optional[float]:
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as handle:
            return int(handle.read().strip()) / 1000.0
    except Exception:
        return None


class CpuSampler:
    """Continuous CPU sampler via /proc/stat in a background thread."""

    def __init__(self, interval_s: float = 0.5):
        self._interval_s = float(interval_s)
        self._samples: List[float] = []
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._samples = []
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> Tuple[float, float, List[float]]:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if not self._samples:
            return 0.0, 0.0, []
        avg_cpu = statistics.mean(self._samples)
        peak_cpu = max(self._samples)
        return avg_cpu, peak_cpu, list(self._samples)

    def _loop(self) -> None:
        prev_idle, prev_total = self._read_stat()
        while self._running:
            time.sleep(self._interval_s)
            idle, total = self._read_stat()
            d_idle = idle - prev_idle
            d_total = total - prev_total
            if d_total > 0:
                self._samples.append((1.0 - d_idle / d_total) * 100.0)
            prev_idle, prev_total = idle, total

    @staticmethod
    def _read_stat() -> Tuple[int, int]:
        try:
            with open("/proc/stat") as handle:
                parts = handle.readline().split()
            idle = int(parts[4])
            total = sum(int(p) for p in parts[1:])
            return idle, total
        except Exception:
            return 0, 1


def start_detector(script: Path, label: str) -> Optional[subprocess.Popen]:
    print(f"  Starting {label} ({script.name}) via {DETECTOR_PYTHON}...", end="", flush=True)
    err_path = Path(f"/tmp/detector_{label.lower().replace(' ', '_')}.err")
    err_handle = open(err_path, "w")
    proc = subprocess.Popen(
        [DETECTOR_PYTHON, "-u", str(script)],
        stdout=subprocess.DEVNULL,
        stderr=err_handle,
        preexec_fn=os.setpgrp if hasattr(os, "setpgrp") else None,
    )
    time.sleep(2)
    err_handle.flush()
    if proc.poll() is not None:
        err_handle.close()
        err_text = err_path.read_text(errors="ignore").strip()
        print(f" FAILED (exit {proc.returncode})")
        if err_text:
            for line in err_text.splitlines()[-8:]:
                print(f"    {line}")
        return None
    print(f" PID {proc.pid}")
    return proc


def stop_detector(proc: Optional[subprocess.Popen], label: str) -> None:
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


@dataclass(frozen=True)
class AeadProfile:
    token: str
    display_name: str


APPROVED_AEAD_PROFILES: Tuple[AeadProfile, ...] = (
    AeadProfile("aesgcm128", "AES-128-GCM"),
    AeadProfile("aesccm128", "AES-128-CCM"),
    AeadProfile("ascon128", "Ascon-AEAD128"),
    AeadProfile("aesgcm192", "AES-192-GCM"),
    AeadProfile("aesccm192", "AES-192-CCM"),
    AeadProfile("aesgcm256", "AES-256-GCM"),
    AeadProfile("aesccm256", "AES-256-CCM"),
    AeadProfile("chacha20poly1305", "ChaCha20-Poly1305"),
)


def _build_ids_for_default_suite() -> AeadIds:
    suite = get_suite("cs-mlkem768-mldsa65")
    return AeadIds(
        kem_id=int(suite["kem_id"]),
        kem_param=int(suite["kem_param_id"]),
        sig_id=int(suite["sig_id"]),
        sig_param=int(suite["sig_param_id"]),
    )


def _bench_one_profile(
    profile: AeadProfile,
    payload: bytes,
    warmup: int,
    iterations: int,
    receiver_window: int,
    cpu_sample_interval_s: float,
) -> Dict[str, Any]:
    ids = _build_ids_for_default_suite()
    session_id = os.urandom(int(CONFIG.get("WIRE_SESSION_ID_LEN", 16)))
    epoch = 0
    key_len = required_key_length_for_aead(profile.token)
    key = os.urandom(key_len)

    sender = Sender(
        version=int(CONFIG["WIRE_VERSION"]),
        ids=ids,
        session_id=session_id,
        epoch=epoch,
        key_send=key,
        aead_token=profile.token,
    )
    receiver = Receiver(
        version=int(CONFIG["WIRE_VERSION"]),
        ids=ids,
        session_id=session_id,
        epoch=epoch,
        key_recv=key,
        window=int(receiver_window),
        strict_mode=True,
        aead_token=profile.token,
    )

    # Warmup
    wire = sender.encrypt(payload)
    pt = receiver.decrypt(wire)
    if pt != payload:
        raise RuntimeError(f"warmup roundtrip mismatch for {profile.display_name}")
    for _ in range(max(0, warmup - 1)):
        wire = sender.encrypt(payload)
        _ = receiver.decrypt(wire)

    cpu_sampler = CpuSampler(interval_s=cpu_sample_interval_s)
    temp_before = read_cpu_temp_c()
    cpu_sampler.start()
    time.sleep(cpu_sample_interval_s)  # allow baseline sample

    enc_times: List[int] = []
    dec_times: List[int] = []

    for _ in range(iterations):
        t0 = time.perf_counter_ns()
        wire = sender.encrypt(payload)
        t1 = time.perf_counter_ns()
        pt = receiver.decrypt(wire)
        t2 = time.perf_counter_ns()
        if pt != payload:
            raise RuntimeError(f"decrypt mismatch for {profile.display_name}")
        enc_times.append(t1 - t0)
        dec_times.append(t2 - t1)

    time.sleep(cpu_sample_interval_s)
    cpu_avg, cpu_peak, cpu_samples = cpu_sampler.stop()
    temp_after = read_cpu_temp_c()
    temp_c = temp_after if temp_after is not None else (temp_before if temp_before is not None else 0.0)

    return {
        "aead_token": profile.token,
        "aead": profile.display_name,
        "enc_median_ns": int(round(statistics.median(enc_times))),
        "dec_median_ns": int(round(statistics.median(dec_times))),
        "enc_mean_ns": int(round(statistics.mean(enc_times))),
        "dec_mean_ns": int(round(statistics.mean(dec_times))),
        "enc_p99_ns": int(round(sorted(enc_times)[int(0.99 * len(enc_times))])),
        "dec_p99_ns": int(round(sorted(dec_times)[int(0.99 * len(dec_times))])),
        "cpu_pct": round(cpu_avg, 1),
        "cpu_peak_pct": round(cpu_peak, 1),
        "cpu_samples": len(cpu_samples),
        "temp_c": round(float(temp_c), 1),
    }


def _run_phase(
    label: str,
    profiles: Iterable[AeadProfile],
    payload_bytes: int,
    warmup: int,
    iterations: int,
    receiver_window: int,
    cpu_sample_interval_s: float,
    cooldown_s: float,
) -> List[Dict[str, Any]]:
    profiles_list = list(profiles)
    payload = os.urandom(int(payload_bytes))
    rows: List[Dict[str, Any]] = []

    print(f"\n{'=' * 78}")
    print(f"  PHASE: {label}")
    print(f"  Payload={payload_bytes}B | Warmup={warmup} | Iter={iterations}")
    print(f"{'=' * 78}")

    for i, profile in enumerate(profiles_list, 1):
        print(f"  [{i}/{len(profiles_list)}] {profile.display_name}...", end=" ", flush=True)
        result = _bench_one_profile(
            profile=profile,
            payload=payload,
            warmup=warmup,
            iterations=iterations,
            receiver_window=receiver_window,
            cpu_sample_interval_s=cpu_sample_interval_s,
        )
        result = {"detector": label, **result}
        rows.append(result)
        print(
            f"enc={result['enc_median_ns'] / 1000:.1f}µs  "
            f"dec={result['dec_median_ns'] / 1000:.1f}µs  "
            f"cpu={result['cpu_pct']:.1f}%  temp={result['temp_c']:.1f}°C"
        )
        time.sleep(float(cooldown_s))

    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="8-AEAD × 3-detector matrix (approved AEADs)")
    parser.add_argument("--payload-bytes", type=int, default=256)
    parser.add_argument("--iterations", type=int, default=5000)
    parser.add_argument("--warmup", type=int, default=200)
    parser.add_argument("--cooldown-s", type=float, default=2.0)
    parser.add_argument("--cpu-sample-interval-s", type=float, default=0.5)
    parser.add_argument("--receiver-window", type=int, default=1024)
    parser.add_argument("--skip-xgb", action="store_true")
    parser.add_argument("--skip-tst", action="store_true")
    parser.add_argument("--tst-warmup-s", type=int, default=int(os.environ.get("TST_WARMUP_S", "300")))
    parser.add_argument(
        "--xgb-script",
        type=str,
        default=str(DEFAULT_XGB_OLD_SCRIPT),
        help="Path to XGBoost detector script (default: legacy busy-wait xgb_old.py)",
    )
    parser.add_argument(
        "--tst-script",
        type=str,
        default=str(DEFAULT_TST_OLD_SCRIPT),
        help="Path to TST detector script (default: legacy busy-wait tst_old.py)",
    )
    args = parser.parse_args()

    xgb_script = Path(args.xgb_script).expanduser()
    tst_script = Path(args.tst_script).expanduser()

    print("=" * 78)
    print("PQ-MAVTunnel Approved AEAD × Detector Matrix")
    print(f"Suite IDs: cs-mlkem768-mldsa65 (header IDs are fixed to this suite)")
    print(f"AEAD profiles: {', '.join(p.display_name for p in APPROVED_AEAD_PROFILES)}")
    print(f"Detectors: {DETECTOR_PYTHON}")
    print(f"XGB: {xgb_script}")
    print(f"TST: {tst_script} (warmup: {args.tst_warmup_s}s)")
    print("=" * 78)

    all_rows: List[Dict[str, Any]] = []

    # Phase 1: Baseline
    all_rows.extend(
        _run_phase(
            label="Baseline",
            profiles=APPROVED_AEAD_PROFILES,
            payload_bytes=args.payload_bytes,
            warmup=args.warmup,
            iterations=args.iterations,
            receiver_window=args.receiver_window,
            cpu_sample_interval_s=args.cpu_sample_interval_s,
            cooldown_s=args.cooldown_s,
        )
    )

    # Phase 2: +XGBoost
    if not args.skip_xgb:
        print(f"\n{'─' * 78}")
        print("  Launching XGBoost detector...")
        xgb_proc = start_detector(xgb_script, "XGBoost")
        if xgb_proc:
            print("  XGBoost warm-up: 5s...")
            time.sleep(5)
            all_rows.extend(
                _run_phase(
                    label="XGBoost",
                    profiles=APPROVED_AEAD_PROFILES,
                    payload_bytes=args.payload_bytes,
                    warmup=args.warmup,
                    iterations=args.iterations,
                    receiver_window=args.receiver_window,
                    cpu_sample_interval_s=args.cpu_sample_interval_s,
                    cooldown_s=args.cooldown_s,
                )
            )
            stop_detector(xgb_proc, "XGBoost")
        else:
            print("  XGBoost failed to start — skipping phase")
        time.sleep(args.cooldown_s)

    # Phase 3: +TST
    if not args.skip_tst:
        print(f"\n{'─' * 78}")
        print("  Launching TST detector...")
        tst_proc = start_detector(tst_script, "TST")
        if tst_proc:
            print(f"  TST warm-up: {args.tst_warmup_s}s...")
            time.sleep(args.tst_warmup_s)
            all_rows.extend(
                _run_phase(
                    label="TST",
                    profiles=APPROVED_AEAD_PROFILES,
                    payload_bytes=args.payload_bytes,
                    warmup=args.warmup,
                    iterations=args.iterations,
                    receiver_window=args.receiver_window,
                    cpu_sample_interval_s=args.cpu_sample_interval_s,
                    cooldown_s=args.cooldown_s,
                )
            )
            stop_detector(tst_proc, "TST")
        else:
            print("  TST failed to start — skipping phase")

    # Output summary
    print(f"\n{'=' * 78}")
    print("RESULTS: Approved AEAD × Detector Matrix")
    print(f"{'=' * 78}")
    print(f"{'AEAD':<18} {'Detector':<10} {'Enc(ns)':>10} {'Dec(ns)':>10} {'CPU%':>6} {'Temp':>6}")
    print("-" * 78)
    for row in all_rows:
        print(
            f"{row['aead']:<18} {row['detector']:<10} {row['enc_median_ns']:>10} "
            f"{row['dec_median_ns']:>10} {row['cpu_pct']:>6.1f} {row['temp_c']:>6.1f}"
        )

    out_json = "/tmp/aead_detector_approved_8x3.json"
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "payload_bytes": args.payload_bytes,
        "iterations": args.iterations,
        "warmup": args.warmup,
        "suite_id": "cs-mlkem768-mldsa65",
        "detector_python": DETECTOR_PYTHON,
        "xgb_script": str(xgb_script),
        "tst_script": str(tst_script),
        "tst_warmup_s": args.tst_warmup_s,
        "results": all_rows,
    }
    with open(out_json, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    print(f"\nSaved: {out_json}")

    out_csv = "/tmp/aead_detector_approved_8x3.csv"
    csv_cols = [
        "aead",
        "aead_token",
        "detector",
        "enc_median_ns",
        "dec_median_ns",
        "enc_mean_ns",
        "dec_mean_ns",
        "enc_p99_ns",
        "dec_p99_ns",
        "cpu_pct",
        "cpu_peak_pct",
        "cpu_samples",
        "temp_c",
    ]
    with open(out_csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_cols)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: row.get(k, "") for k in csv_cols})
    print(f"Saved: {out_csv}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
