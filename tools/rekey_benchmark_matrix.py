#!/usr/bin/env python3
"""Build and optionally execute rekey benchmark sequences for all 24 suites.

Scenarios:
1) same_suite_rekey: rekey to the same suite repeatedly.
2) same_level_rekey: rekey within the same NIST level.
3) cross_level_rekey: rekey across different NIST levels.

This script generates JSON sequence files compatible with:
  python -m sscheduler.sdrone_bench --benchmark-mode in_band_rekey --suite-sequence-file <file>
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.suites import list_suites


def _ordered_suites() -> List[str]:
    suites = list_suites()
    level_rank = {"L1": 0, "L3": 1, "L5": 2}
    return sorted(
        suites.keys(),
        key=lambda sid: (
            level_rank.get(str(suites[sid].get("nist_level", "L5")), 99),
            str(suites[sid].get("kem_name", "")),
            str(suites[sid].get("sig_name", "")),
            sid,
        ),
    )


def _group_by_level(suites: Sequence[str]) -> Dict[str, List[str]]:
    cfg = list_suites()
    grouped: Dict[str, List[str]] = {"L1": [], "L3": [], "L5": []}
    for sid in suites:
        lvl = str(cfg[sid].get("nist_level", "L5"))
        grouped.setdefault(lvl, []).append(sid)
    for lvl in grouped:
        grouped[lvl].sort()
    return grouped


def build_same_suite_sequence(suites: Sequence[str], rekeys_per_suite: int) -> List[str]:
    sequence: List[str] = []
    repeat = rekeys_per_suite + 1  # initial handshake + N in-band rekeys
    for sid in suites:
        sequence.extend([sid] * repeat)
    return sequence


def build_same_level_sequence(suites: Sequence[str], rekeys_per_suite: int) -> List[str]:
    grouped = _group_by_level(suites)
    sequence: List[str] = []
    for lvl in ("L1", "L3", "L5"):
        level_suites = grouped.get(lvl, [])
        if not level_suites:
            continue
        n = len(level_suites)
        for i, start_sid in enumerate(level_suites):
            sequence.append(start_sid)
            for step in range(1, rekeys_per_suite + 1):
                sequence.append(level_suites[(i + step) % n])
    return sequence


def build_cross_level_sequence(suites: Sequence[str], rekeys_per_suite: int) -> List[str]:
    grouped = _group_by_level(suites)
    l1 = grouped.get("L1", [])
    l3 = grouped.get("L3", [])
    l5 = grouped.get("L5", [])

    if not l1 or not l3 or not l5:
        raise RuntimeError("cross_level_rekey requires non-empty L1/L3/L5 suite groups")

    base: List[str] = []
    max_len = max(len(l1), len(l3), len(l5))
    for i in range(max_len):
        base.append(l1[i % len(l1)])
        base.append(l3[i % len(l3)])
        base.append(l5[i % len(l5)])

    # Trim to exactly the number of canonical suites to keep run length bounded.
    base = base[: len(suites)]

    sequence: List[str] = []
    n = len(base)
    for i in range(n):
        sequence.append(base[i])
        for step in range(1, rekeys_per_suite + 1):
            sequence.append(base[(i + step) % n])
    return sequence


def _count_transitions(sequence: Sequence[str]) -> int:
    if not sequence:
        return 0
    transitions = 0
    for i in range(1, len(sequence)):
        if sequence[i] != sequence[i - 1]:
            transitions += 1
    return transitions


def _write_sequence(path: Path, sequence: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(list(sequence), indent=2), encoding="utf-8")


def _execute_scenario(sequence_file: Path, args: argparse.Namespace) -> int:
    command = [
        sys.executable,
        "-m",
        "sscheduler.sdrone_bench",
        "--benchmark-mode",
        "in_band_rekey",
        "--suite-sequence-file",
        str(sequence_file),
        "--interval",
        str(args.interval),
        "--mode",
        "MAVPROXY",
    ]
    if args.gcs_host:
        command.extend(["--gcs-host", args.gcs_host])
    if args.log_dir:
        command.extend(["--log-dir", str(Path(args.log_dir).expanduser().resolve())])

    print("RUN:", " ".join(command))
    if args.dry_run:
        return 0

    completed = subprocess.run(command, cwd=str(ROOT))
    return int(completed.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 24-suite rekey benchmark sequences")
    parser.add_argument("--rekeys-per-suite", type=int, default=5, help="In-band rekeys per base suite")
    parser.add_argument("--output-dir", type=str, default=str(ROOT / "logs" / "rekey_matrix"), help="Directory for generated sequence files")
    parser.add_argument("--interval", type=float, default=30.0, help="Seconds per sequence entry when executing")
    parser.add_argument("--execute", action="store_true", help="Execute generated scenarios via sscheduler.sdrone_bench")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without running benchmarks")
    parser.add_argument("--gcs-host", type=str, help="Optional GCS control host override")
    parser.add_argument("--log-dir", type=str, help="Optional benchmark log dir passed to sdrone_bench")
    args = parser.parse_args()

    if args.rekeys_per_suite < 1:
        raise SystemExit("--rekeys-per-suite must be >= 1")

    suites = _ordered_suites()
    if len(suites) != 24:
        raise SystemExit(f"Expected 24 suites, found {len(suites)}")

    out_dir = Path(args.output_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    scenarios = {
        "same_suite_rekey": build_same_suite_sequence(suites, args.rekeys_per_suite),
        "same_level_rekey": build_same_level_sequence(suites, args.rekeys_per_suite),
        "cross_level_rekey": build_cross_level_sequence(suites, args.rekeys_per_suite),
    }

    sequence_files: Dict[str, Path] = {}
    for name, seq in scenarios.items():
        path = out_dir / f"{name}.json"
        _write_sequence(path, seq)
        sequence_files[name] = path

    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "suite_count": len(suites),
        "rekeys_per_suite": args.rekeys_per_suite,
        "scenarios": {
            name: {
                "file": str(path),
                "entries": len(scenarios[name]),
                "transitions": _count_transitions(scenarios[name]),
            }
            for name, path in sequence_files.items()
        },
    }
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"Generated sequences in: {out_dir}")
    for name, path in sequence_files.items():
        seq = scenarios[name]
        print(f"  {name}: entries={len(seq)}, transitions={_count_transitions(seq)}, file={path}")

    if not args.execute:
        print("Execution skipped (use --execute).")
        return 0

    for name in ("same_suite_rekey", "same_level_rekey", "cross_level_rekey"):
        print(f"\n=== Scenario: {name} ===")
        code = _execute_scenario(sequence_files[name], args)
        if code != 0:
            print(f"Scenario failed: {name} (exit={code})")
            return code

    print("All scenarios completed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
