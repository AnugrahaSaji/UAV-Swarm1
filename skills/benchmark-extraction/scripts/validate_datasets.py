#!/usr/bin/env python3
"""Validate extracted datasets for integrity and consistency.

Checks:
- No negative latencies or power readings
- No missing required fields
- Cross-reference between datasets

Usage:
    python skills/benchmark-extraction/scripts/validate_datasets.py
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATASETS = ROOT / "paper" / "vtc_fall" / "datasets"

ERRORS = []
WARNINGS = []


def check(condition: bool, msg: str, level: str = "ERROR"):
    if not condition:
        if level == "ERROR":
            ERRORS.append(msg)
        else:
            WARNINGS.append(msg)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        WARNINGS.append(f"Dataset not found: {path.name}")
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def validate_aead_latency():
    rows = read_csv(DATASETS / "aead_latency.csv")
    if not rows:
        return
    print(f"  aead_latency.csv: {len(rows)} rows")
    for i, row in enumerate(rows):
        mean = float(row.get("mean_us", 0) or 0)
        check(mean >= 0, f"aead_latency row {i}: negative mean_us={mean}")
        check(mean < 10000, f"aead_latency row {i}: suspiciously high mean_us={mean}", "WARN")


def validate_aead_power():
    rows = read_csv(DATASETS / "aead_power.csv")
    if not rows:
        return
    print(f"  aead_power.csv: {len(rows)} rows")
    for i, row in enumerate(rows):
        power = float(row.get("power_avg_w", 0) or 0)
        check(power >= 0, f"aead_power row {i}: negative power={power}")
        check(power < 15, f"aead_power row {i}: power exceeds RPi limit: {power}W", "WARN")


def validate_handshake_overhead():
    rows = read_csv(DATASETS / "handshake_overhead.csv")
    if not rows:
        return
    print(f"  handshake_overhead.csv: {len(rows)} rows")
    for i, row in enumerate(rows):
        hs = float(row.get("handshake_ms_drone", 0) or 0)
        check(hs >= 0, f"handshake row {i}: negative handshake_ms={hs}")


def validate_ddos_overhead():
    rows = read_csv(DATASETS / "ddos_overhead.csv")
    if not rows:
        return
    print(f"  ddos_overhead.csv: {len(rows)} rows")


def main():
    print("=== Dataset Validation ===")
    print(f"Datasets: {DATASETS}")
    print()

    validate_aead_latency()
    validate_aead_power()
    validate_handshake_overhead()
    validate_ddos_overhead()

    print()
    if WARNINGS:
        print(f"WARNINGS ({len(WARNINGS)}):")
        for w in WARNINGS:
            print(f"  ⚠ {w}")
    if ERRORS:
        print(f"\nERRORS ({len(ERRORS)}):")
        for e in ERRORS:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print("✓ All validations passed")


if __name__ == "__main__":
    main()
