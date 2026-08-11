#!/usr/bin/env python3
"""Extract KEM/SIG benchmark data and handshake overhead from full benchmark table.

Usage:
    python skills/benchmark-extraction/scripts/extract_kem_sig.py
"""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATASETS = ROOT / "paper" / "vtc_fall" / "datasets"
DATASETS.mkdir(parents=True, exist_ok=True)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        print(f"WARN: {path} not found")
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def extract_handshake_overhead():
    """Extract handshake timing from benchmark_full_table_20260220.csv."""
    rows = read_csv(ROOT / "benchmark_full_table_20260220.csv")
    if not rows:
        return

    out_path = DATASETS / "handshake_overhead.csv"
    fieldnames = [
        "suite", "aead", "handshake_ms_drone", "handshake_ms_gcs",
        "handshake_ok", "throughput_mbps", "packet_loss_ratio",
        "rtt_avg_ms", "rtt_p95_ms"
    ]

    written = 0
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            out_row = {
                "suite": row.get("suite", ""),
                "aead": row.get("aead", ""),
                "handshake_ms_drone": row.get("handshake_ms_drone", ""),
                "handshake_ms_gcs": row.get("handshake_ms_gcs", ""),
                "handshake_ok": row.get("handshake_ok_both", ""),
                "throughput_mbps": row.get("throughput_mbps", ""),
                "packet_loss_ratio": row.get("packet_loss_ratio", ""),
                "rtt_avg_ms": row.get("rtt_avg_ms", ""),
                "rtt_p95_ms": row.get("rtt_p95_ms", ""),
            }
            writer.writerow(out_row)
            written += 1

    print(f"  handshake_overhead.csv: {written} rows")


def main():
    print("=== KEM/SIG/Handshake Extraction ===")
    print(f"Output: {DATASETS}")
    print()
    extract_handshake_overhead()
    print("\nDone.")


if __name__ == "__main__":
    main()
