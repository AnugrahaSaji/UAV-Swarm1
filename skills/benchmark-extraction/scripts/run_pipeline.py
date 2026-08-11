#!/usr/bin/env python3
"""Master pipeline: benchmarks → datasets → tables → figures → paper.

Orchestrates the full reproducible result pipeline.

Usage:
    python skills/benchmark-extraction/scripts/run_pipeline.py [--stage STAGE]

Stages:
    extract   — Parse raw benchmarks into canonical CSVs
    validate  — Validate dataset integrity
    tables    — Generate LaTeX tables
    all       — Run all stages (default)
"""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PYTHON = sys.executable


def run_script(script_path: Path, label: str) -> bool:
    """Run a Python script and report status."""
    print(f"\n{'='*60}")
    print(f"  STAGE: {label}")
    print(f"  Script: {script_path.relative_to(ROOT)}")
    print(f"{'='*60}\n")

    if not script_path.exists():
        print(f"  ERROR: Script not found: {script_path}")
        return False

    result = subprocess.run(
        [PYTHON, str(script_path)],
        cwd=str(ROOT),
        capture_output=False,
    )
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Research data pipeline")
    parser.add_argument("--stage", default="all",
                        choices=["extract", "validate", "tables", "all"])
    args = parser.parse_args()

    skills = ROOT / "skills"
    stages = {
        "extract": [
            (skills / "benchmark-extraction/scripts/extract_aead.py", "AEAD Extraction"),
            (skills / "benchmark-extraction/scripts/extract_kem_sig.py", "KEM/SIG Extraction"),
            (skills / "benchmark-extraction/scripts/extract_ddos_overhead.py", "DDoS Overhead Extraction"),
        ],
        "validate": [
            (skills / "benchmark-extraction/scripts/validate_datasets.py", "Dataset Validation"),
        ],
        "tables": [
            (skills / "latex-tables/scripts/generate_tables.py", "LaTeX Table Generation"),
        ],
    }

    if args.stage == "all":
        run_stages = ["extract", "validate", "tables"]
    else:
        run_stages = [args.stage]

    ok = True
    for stage_name in run_stages:
        for script, label in stages[stage_name]:
            if not run_script(script, label):
                print(f"\n  FAILED: {label}")
                ok = False

    print(f"\n{'='*60}")
    if ok:
        print("  PIPELINE COMPLETE — all stages passed")
    else:
        print("  PIPELINE INCOMPLETE — some stages failed")
    print(f"{'='*60}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
