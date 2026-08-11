#!/usr/bin/env python3
"""Extract and normalize AEAD benchmark data into canonical CSV datasets.

Reads from root-level benchmark CSVs and produces normalized datasets
in paper/vtc_fall/datasets/.

Usage:
    python skills/benchmark-extraction/scripts/extract_aead.py
"""

import csv
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATASETS = ROOT / "paper" / "vtc_fall" / "datasets"
DATASETS.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict]:
    """Read a CSV file and return list of row dicts."""
    if not path.exists():
        print(f"WARN: {path} not found, skipping")
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def extract_aead_latency():
    """Produce aead_latency.csv from aead_benchmark.csv."""
    # Try power benchmark first (has more data), fall back to basic
    rows = read_csv(ROOT / "power_aead_benchmark.csv")
    if not rows:
        rows = read_csv(ROOT / "aead_benchmark.csv")
    if not rows:
        print("ERROR: No AEAD benchmark CSV found")
        return

    out_path = DATASETS / "aead_latency.csv"
    fieldnames = [
        "cipher", "payload_bytes", "operation", "iterations",
        "mean_us", "median_us", "stdev_us", "p95_us", "p99_us",
        "min_us", "max_us", "throughput_mbps"
    ]

    # Normalize field mapping (handle both CSV schemas)
    written = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            cipher = row.get("algo_display") or row.get("display_name") or row.get("algo", "")
            out_row = {
                "cipher": cipher,
                "payload_bytes": row.get("payload_bytes", ""),
                "operation": row.get("operation", ""),
                "iterations": row.get("iterations", ""),
                "mean_us": row.get("mean_us", ""),
                "median_us": row.get("median_us", ""),
                "stdev_us": row.get("stdev_us", ""),
                "p95_us": row.get("p95_us", ""),
                "p99_us": row.get("p99_us", ""),
                "min_us": row.get("min_us", ""),
                "max_us": row.get("max_us", ""),
                "throughput_mbps": row.get("throughput_mbps", ""),
            }
            writer.writerow(out_row)
            written += 1

    print(f"  aead_latency.csv: {written} rows")


def extract_aead_power():
    """Produce aead_power.csv from power_aead_benchmark.csv."""
    rows = read_csv(ROOT / "power_aead_benchmark.csv")
    if not rows:
        print("WARN: No power AEAD benchmark, skipping aead_power.csv")
        return

    out_path = DATASETS / "aead_power.csv"
    fieldnames = [
        "cipher", "operation", "payload_bytes", "iterations",
        "mean_us", "power_avg_w", "power_peak_w",
        "voltage_avg_v", "current_avg_a",
        "energy_per_op_uj", "energy_total_j"
    ]

    written = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            cipher = row.get("algo_display") or row.get("algo", "")
            out_row = {
                "cipher": cipher,
                "operation": row.get("operation", ""),
                "payload_bytes": row.get("payload_bytes", ""),
                "iterations": row.get("iterations", ""),
                "mean_us": row.get("mean_us", ""),
                "power_avg_w": row.get("power_avg_w", ""),
                "power_peak_w": row.get("power_peak_w", ""),
                "voltage_avg_v": row.get("voltage_avg_v", ""),
                "current_avg_a": row.get("current_avg_a", ""),
                "energy_per_op_uj": row.get("energy_per_op_uj", ""),
                "energy_total_j": row.get("energy_total_j", ""),
            }
            writer.writerow(out_row)
            written += 1

    print(f"  aead_power.csv: {written} rows")


def extract_aead_throughput():
    """Produce aead_throughput.csv — cipher × payload → throughput + efficiency."""
    rows = read_csv(ROOT / "power_aead_benchmark.csv")
    if not rows:
        rows = read_csv(ROOT / "aead_benchmark.csv")
    if not rows:
        return

    out_path = DATASETS / "aead_throughput.csv"
    fieldnames = [
        "cipher", "payload_bytes", "operation",
        "throughput_mbps", "mean_us"
    ]

    written = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            cipher = row.get("algo_display") or row.get("display_name") or row.get("algo", "")
            out_row = {
                "cipher": cipher,
                "payload_bytes": row.get("payload_bytes", ""),
                "operation": row.get("operation", ""),
                "throughput_mbps": row.get("throughput_mbps", ""),
                "mean_us": row.get("mean_us", ""),
            }
            writer.writerow(out_row)
            written += 1

    print(f"  aead_throughput.csv: {written} rows")


def main():
    print("=== AEAD Benchmark Extraction ===")
    print(f"Root: {ROOT}")
    print(f"Output: {DATASETS}")
    print()
    extract_aead_latency()
    extract_aead_power()
    extract_aead_throughput()
    print("\nDone.")


if __name__ == "__main__":
    main()
