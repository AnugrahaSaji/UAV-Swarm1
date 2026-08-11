#!/usr/bin/env python3
"""tools/wait_for_comprehensive_metrics.py

Wait until comprehensive A–R metrics files exist and look complete.

Default behavior:
- Watches `logs/benchmarks/comprehensive` (sscheduler/sdrone_bench.py output)
- Requires at least one `*_drone.json` and one `*_gcs.json` for the same run_id
- Validates that each file contains all A–R category keys with the expected
  number of fields (exact count by dataclass fields), and that handshake/data-plane
  look non-empty.

Usage:
  python tools/wait_for_comprehensive_metrics.py
  python tools/wait_for_comprehensive_metrics.py --dir logs/benchmarks/comprehensive --timeout 600
  python tools/wait_for_comprehensive_metrics.py --run-id 20260113_120000

Exit codes:
  0 success
  2 timeout
  3 validation failed (files found but incomplete)
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import fields
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.metrics_schema import (
    RunContextMetrics,
    SuiteCryptoIdentity,
    SuiteLifecycleTimeline,
    HandshakeMetrics,
    CryptoPrimitiveBreakdown,
    RekeyMetrics,
    DataPlaneMetrics,
    MavProxyDroneMetrics,
    MavProxyGcsMetrics,
    MavLinkIntegrityMetrics,
    FlightControllerTelemetry,
    ControlPlaneMetrics,
    SystemResourcesDrone,
    PowerEnergyMetrics,
    ObservabilityMetrics,
    ValidationMetrics,
)


CATEGORY_SPECS = {
    "run_context": RunContextMetrics,
    "crypto_identity": SuiteCryptoIdentity,
    "lifecycle": SuiteLifecycleTimeline,
    "handshake": HandshakeMetrics,
    "crypto_primitives": CryptoPrimitiveBreakdown,
    "rekey": RekeyMetrics,
    "data_plane": DataPlaneMetrics,
    "mavproxy_drone": MavProxyDroneMetrics,
    "mavproxy_gcs": MavProxyGcsMetrics,
    "mavlink_integrity": MavLinkIntegrityMetrics,
    "fc_telemetry": FlightControllerTelemetry,
    "control_plane": ControlPlaneMetrics,
    "system_drone": SystemResourcesDrone,
    "power_energy": PowerEnergyMetrics,
    "observability": ObservabilityMetrics,
    "validation": ValidationMetrics,
}


def _expected_field_counts() -> Dict[str, int]:
    return {k: len(fields(cls)) for k, cls in CATEGORY_SPECS.items()}


def parse_filename(p: Path) -> Optional[Tuple[str, str, str]]:
    """Return (suite_id, run_id, role) from `suite_runid_role.json`.

    run_id is assumed to be `YYYYMMDD_HHMMSS` (two underscore-separated tokens).
    suite_id may contain underscores.
    """
    if p.suffix.lower() != ".json":
        return None
    base = p.stem
    parts = base.split("_")
    if len(parts) < 4:
        return None
    role = parts[-1]
    time_part = parts[-2]
    date_part = parts[-3]
    run_id = f"{date_part}_{time_part}"
    suite_id = "_".join(parts[:-3])
    if role not in {"gcs", "drone"}:
        return None
    return suite_id, run_id, role


def validate_metrics_dict(d: Dict[str, Any]) -> Tuple[bool, str]:
    expected = _expected_field_counts()

    for key, exp_count in expected.items():
        if key not in d:
            return False, f"missing category: {key}"
        if not isinstance(d[key], dict):
            return False, f"category not a dict: {key}"
        found = len(d[key])
        if found != exp_count:
            return False, f"category field count mismatch: {key} expected={exp_count} found={found}"

    hs = d.get("handshake", {})
    if not hs.get("handshake_success"):
        return False, "handshake_success is false"

    dp = d.get("data_plane", {})
    # These should be non-zero for a real run.
    if (dp.get("packets_sent", 0) or 0) <= 0 and (dp.get("enc_out", 0) or 0) <= 0:
        return False, "data_plane looks empty (packets_sent/enc_out are 0)"

    return True, "ok"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "logs" / "benchmarks" / "comprehensive"), help="Directory to watch")
    ap.add_argument("--timeout", type=float, default=600.0, help="Seconds to wait")
    ap.add_argument("--poll", type=float, default=1.0, help="Poll interval seconds")
    ap.add_argument("--run-id", default=None, help="Specific run_id to wait for (YYYYMMDD_HHMMSS)")
    ap.add_argument("--require-both", action="store_true", default=True, help="Require both *_gcs.json and *_drone.json")
    ap.add_argument("--no-require-both", dest="require_both", action="store_false")
    args = ap.parse_args()

    watch_dir = Path(args.dir)
    watch_dir.mkdir(parents=True, exist_ok=True)

    deadline = time.time() + args.timeout
    last_status = ""

    while time.time() < deadline:
        files = sorted(watch_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        groups: Dict[str, Dict[str, Path]] = {}

        for f in files:
            parsed = parse_filename(f)
            if not parsed:
                continue
            suite_id, run_id, role = parsed
            if args.run_id and run_id != args.run_id:
                continue
            groups.setdefault(run_id, {})[role] = f

        # Prefer newest run_id that has required roles
        for run_id in sorted(groups.keys(), reverse=True):
            roles = groups[run_id]
            if args.require_both and not ("gcs" in roles and "drone" in roles):
                continue

            # Validate each required file
            for role in (["drone", "gcs"] if args.require_both else sorted(roles.keys())):
                if role not in roles:
                    continue
                path = roles[role]
                try:
                    payload = load_json(path)
                    ok, msg = validate_metrics_dict(payload)
                    if not ok:
                        last_status = f"{run_id} {role} invalid: {msg} ({path.name})"
                        break
                except Exception as e:
                    last_status = f"{run_id} {role} failed to read/parse: {e} ({path.name})"
                    break
            else:
                print(f"OK: comprehensive metrics present and valid for run_id={run_id} in {watch_dir}")
                print(f"  drone: {roles.get('drone').name if roles.get('drone') else 'n/a'}")
                print(f"  gcs:   {roles.get('gcs').name if roles.get('gcs') else 'n/a'}")
                return 0

        if last_status:
            print(f"Waiting: {last_status}")
            last_status = ""
        time.sleep(args.poll)

    print("TIMEOUT: comprehensive metrics not complete")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
