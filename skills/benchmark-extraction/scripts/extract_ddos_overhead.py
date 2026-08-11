#!/usr/bin/env python3
"""Extract DDoS detection overhead data from bench_ddos_results.

Scans bench_ddos_results/ for comparison.json and results files,
normalizes into ddos_overhead.csv.

Usage:
    python skills/benchmark-extraction/scripts/extract_ddos_overhead.py
"""

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATASETS = ROOT / "paper" / "vtc_fall" / "datasets"
DATASETS.mkdir(parents=True, exist_ok=True)


def find_json_files(base: Path, pattern: str) -> list[Path]:
    """Recursively find JSON files matching pattern."""
    return sorted(base.rglob(pattern))


def extract_ddos_overhead():
    """Extract detector overhead comparison data."""
    # Look for comparison.json in bench_ddos_results/
    ddos_dir = ROOT / "bench_ddos_results"
    comparison_files = find_json_files(ddos_dir, "comparison.json") if ddos_dir.exists() else []
    results_files = find_json_files(ddos_dir, "results.json") if ddos_dir.exists() else []

    # Also check root-level DDoS comparison files
    root_comparison = ROOT / "bench_ddos_results"

    all_data = []

    for jf in comparison_files:
        try:
            with open(jf, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                for model_name, metrics in data.items():
                    if isinstance(metrics, dict):
                        all_data.append({
                            "model": model_name,
                            "source": str(jf.relative_to(ROOT)),
                            **{k: v for k, v in metrics.items()
                               if isinstance(v, (int, float, str))}
                        })
            elif isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict):
                        all_data.append({
                            "source": str(jf.relative_to(ROOT)),
                            **entry
                        })
        except (json.JSONDecodeError, OSError) as e:
            print(f"  WARN: Could not parse {jf}: {e}")

    for jf in results_files:
        try:
            with open(jf, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                # Single result file
                all_data.append({
                    "source": str(jf.relative_to(ROOT)),
                    **{k: v for k, v in data.items()
                       if isinstance(v, (int, float, str))}
                })
            elif isinstance(data, list):
                for entry in data:
                    if isinstance(entry, dict):
                        all_data.append({
                            "source": str(jf.relative_to(ROOT)),
                            **entry
                        })
        except (json.JSONDecodeError, OSError) as e:
            print(f"  WARN: Could not parse {jf}: {e}")

    if not all_data:
        print("  WARN: No DDoS overhead data found")
        return

    # Determine fieldnames from collected data
    all_keys = set()
    for d in all_data:
        all_keys.update(d.keys())

    # Prioritize important fields
    priority = ["model", "accuracy", "f1", "precision", "recall",
                "inference_ms", "power_overhead_w", "cpu_pct",
                "temp_delta_c", "source"]
    fieldnames = [k for k in priority if k in all_keys]
    fieldnames += sorted(all_keys - set(fieldnames))

    out_path = DATASETS / "ddos_overhead.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in all_data:
            writer.writerow(row)

    print(f"  ddos_overhead.csv: {len(all_data)} rows")


def main():
    print("=== DDoS Overhead Extraction ===")
    print(f"Output: {DATASETS}")
    print()
    extract_ddos_overhead()
    print("\nDone.")


if __name__ == "__main__":
    main()
