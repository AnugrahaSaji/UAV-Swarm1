#!/usr/bin/env python3
"""Core-only Phase 3 validator for suite/AEAD rekey combinations.

This script does not depend on sscheduler. It validates:
1) Runtime suite inventory after pruning.
2) Level-aware AEAD profile availability.
3) Handshake success for every runtime suite (localhost socketpair).
4) Rekey transition state-space classification across all suite+AEAD states.
5) AEAD-only ratchet correctness for every same-suite AEAD shift.
6) Negotiation guard: selected AEAD always belongs to target suite level profile.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.aead import required_key_length_for_aead
from core.handshake import client_drone_handshake, derive_aead_ratchet, server_gcs_handshake
from core.suites import (
    aead_profiles_by_nist_level,
    available_aead_tokens,
    get_suite,
    list_suites,
    select_crypto_profile_for_capabilities,
)


@dataclass(frozen=True)
class SuiteState:
    suite_id: str
    nist_level: str
    aead_token: str


def _now_utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _load_signature_class():
    try:
        from oqs.oqs import Signature  # type: ignore
    except Exception:  # pragma: no cover - environment dependent
        from oqs import Signature  # type: ignore
    return Signature


def _run_suite_handshake_check(*, suite_id: str, psk_hex: str, timeout_s: float = 10.0) -> Tuple[bool, str]:
    """Run one in-memory handshake pair (gcs/server + drone/client)."""

    suite = get_suite(suite_id)
    sig_name = str(suite["sig_name"])
    Signature = _load_signature_class()

    server = Signature(sig_name)
    server_pub = server.generate_keypair()

    sock_gcs, sock_drone = socket.socketpair()
    os.environ["DRONE_PSK"] = psk_hex

    result: Dict[str, object] = {"ok": False, "error": ""}

    def _server_worker() -> None:
        try:
            srv = server_gcs_handshake(sock_gcs, suite, server, timeout=timeout_s, epoch=0)
            result["server"] = srv
        except Exception as exc:  # pragma: no cover - runtime path
            result["error"] = f"server: {type(exc).__name__}: {exc}"

    thread = threading.Thread(target=_server_worker, daemon=True)
    thread.start()
    try:
        cli = client_drone_handshake(sock_drone, suite, server_pub, timeout=timeout_s, epoch=0)
        result["client"] = cli
    except Exception as exc:  # pragma: no cover - runtime path
        result["error"] = f"client: {type(exc).__name__}: {exc}"
    finally:
        try:
            sock_drone.close()
        except Exception:
            pass

    thread.join(timeout=timeout_s + 2.0)
    try:
        sock_gcs.close()
    except Exception:
        pass
    try:
        if hasattr(server, "free"):
            server.free()
    except Exception:
        pass

    err = str(result.get("error") or "")
    if err:
        return False, err

    server_tuple = result.get("server")
    client_tuple = result.get("client")
    if not isinstance(server_tuple, tuple) or not isinstance(client_tuple, tuple):
        return False, "missing_handshake_tuple"
    if len(server_tuple) < 5 or len(client_tuple) < 5:
        return False, "unexpected_handshake_tuple_len"

    # Both sides expose (k_d2g, k_g2d, ..., session_id, ...)
    s_k_d2g, s_k_g2d, _, _, s_session = server_tuple[:5]
    c_k_d2g, c_k_g2d, _, _, c_session = client_tuple[:5]
    if s_k_d2g != c_k_d2g or s_k_g2d != c_k_g2d:
        return False, "key_mismatch_between_roles"
    if s_session != c_session:
        return False, "session_id_mismatch_between_roles"
    if not isinstance(c_k_d2g, (bytes, bytearray)) or len(c_k_d2g) == 0:
        return False, "invalid_derived_key_material"
    return True, ""


def _build_states(
    *,
    suites: Dict[str, Dict],
    runtime_aead_by_level: Dict[str, Tuple[str, ...]],
) -> List[SuiteState]:
    states: List[SuiteState] = []
    for suite_id, suite in sorted(suites.items()):
        level = str(suite.get("nist_level", "")).upper()
        for token in runtime_aead_by_level.get(level, ()):
            states.append(SuiteState(suite_id=suite_id, nist_level=level, aead_token=token))
    return states


def _classify_transition(source: SuiteState, target: SuiteState) -> str:
    if source.suite_id == target.suite_id and source.aead_token == target.aead_token:
        return "same_suite_same_aead"
    if source.suite_id == target.suite_id and source.aead_token != target.aead_token:
        return "aead_only_same_suite"
    if source.nist_level == target.nist_level:
        return "full_handshake_same_level"
    return "full_handshake_cross_level"


def run_phase3_matrix(*, out_dir: Path) -> Dict[str, object]:
    started = time.time()
    suites = list_suites()  # runtime-pruned registry
    suite_ids = sorted(suites.keys())
    runtime_aead_tokens = tuple(available_aead_tokens())
    runtime_aead_by_level = aead_profiles_by_nist_level(runtime_only=True)
    canonical_aead_by_level = aead_profiles_by_nist_level(runtime_only=False)

    if not suite_ids:
        raise RuntimeError("No runtime suites available")

    # Ensure each runtime suite level has at least one runtime AEAD profile.
    missing_levels: List[str] = []
    for sid in suite_ids:
        level = str(suites[sid].get("nist_level", "")).upper()
        if not runtime_aead_by_level.get(level):
            missing_levels.append(level)
    if missing_levels:
        uniq = sorted(set(missing_levels))
        raise RuntimeError(f"No runtime AEAD profile for levels: {uniq}")

    # Handshake check across all runtime suites.
    psk_hex = "ab" * 32
    handshake_results: List[Dict[str, object]] = []
    for sid in suite_ids:
        ok, error = _run_suite_handshake_check(suite_id=sid, psk_hex=psk_hex)
        handshake_results.append({"suite_id": sid, "ok": ok, "error": error})

    states = _build_states(suites=suites, runtime_aead_by_level=runtime_aead_by_level)
    if not states:
        raise RuntimeError("No runtime suite+AEAD states available")

    category_counts = {
        "same_suite_same_aead": 0,
        "aead_only_same_suite": 0,
        "full_handshake_same_level": 0,
        "full_handshake_cross_level": 0,
    }

    ratchet_checks = {
        "checked": 0,
        "passed": 0,
        "failed": 0,
        "errors": [],
    }
    negotiation_checks = {
        "checked": 0,
        "passed": 0,
        "failed": 0,
        "errors": [],
    }

    # Exhaustive transition space over runtime states.
    for source in states:
        src_len = required_key_length_for_aead(source.aead_token)
        base_d2g = bytes([0x11]) * src_len
        base_g2d = bytes([0x22]) * src_len
        session_id = bytes([0x33]) * 16

        for target in states:
            category = _classify_transition(source, target)
            category_counts[category] += 1

            # Validate AEAD-only ratchet transitions.
            if category == "aead_only_same_suite":
                ratchet_checks["checked"] += 1
                try:
                    new_d2g, new_g2d = derive_aead_ratchet(
                        base_d2g,
                        base_g2d,
                        session_id,
                        target.aead_token,
                        epoch=1,
                    )
                    exp_len = required_key_length_for_aead(target.aead_token)
                    if len(new_d2g) == exp_len and len(new_g2d) == exp_len:
                        ratchet_checks["passed"] += 1
                    else:
                        ratchet_checks["failed"] += 1
                        ratchet_checks["errors"].append(
                            {
                                "source": source.__dict__,
                                "target": target.__dict__,
                                "error": f"derived_len=({len(new_d2g)},{len(new_g2d)}) expected={exp_len}",
                            }
                        )
                except Exception as exc:
                    ratchet_checks["failed"] += 1
                    ratchet_checks["errors"].append(
                        {
                            "source": source.__dict__,
                            "target": target.__dict__,
                            "error": f"{type(exc).__name__}: {exc}",
                        }
                    )

            # Validate negotiation guard: AEAD selected for target suite respects target level profile.
            negotiation_checks["checked"] += 1
            target_level = target.nist_level
            offered_for_level = list(runtime_aead_by_level.get(target_level, ()))
            if not offered_for_level:
                negotiation_checks["failed"] += 1
                negotiation_checks["errors"].append(
                    {
                        "source": source.__dict__,
                        "target": target.__dict__,
                        "error": f"no_runtime_aead_for_level:{target_level}",
                    }
                )
                continue

            try:
                profile = select_crypto_profile_for_capabilities(
                    offered_suites=[target.suite_id],
                    aead_tokens=offered_for_level,
                    prefer_aead_tokens=[target.aead_token],
                )
                selected = str(profile.get("aead_token", ""))
                allowed = set(runtime_aead_by_level.get(target_level, ()))
                if selected in allowed:
                    negotiation_checks["passed"] += 1
                else:
                    negotiation_checks["failed"] += 1
                    negotiation_checks["errors"].append(
                        {
                            "source": source.__dict__,
                            "target": target.__dict__,
                            "selected": selected,
                            "allowed": sorted(allowed),
                            "error": "selected_aead_outside_level_profile",
                        }
                    )
            except Exception as exc:
                negotiation_checks["failed"] += 1
                negotiation_checks["errors"].append(
                    {
                        "source": source.__dict__,
                        "target": target.__dict__,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

    elapsed_s = round(time.time() - started, 3)

    handshake_pass = sum(1 for item in handshake_results if item["ok"])
    handshake_fail = len(handshake_results) - handshake_pass

    report: Dict[str, object] = {
        "generated_at_utc": _now_utc(),
        "elapsed_s": elapsed_s,
        "runtime_suite_count": len(suite_ids),
        "runtime_suite_ids": suite_ids,
        "runtime_aead_tokens": list(runtime_aead_tokens),
        "canonical_aead_profiles_by_level": {
            key: list(value) for key, value in canonical_aead_by_level.items()
        },
        "runtime_aead_profiles_by_level": {
            key: list(value) for key, value in runtime_aead_by_level.items()
        },
        "state_space": {
            "runtime_state_count": len(states),
            "runtime_states": [state.__dict__ for state in states],
            "transition_count_total": len(states) * len(states),
            "category_counts": category_counts,
        },
        "handshake_validation": {
            "checked": len(handshake_results),
            "passed": handshake_pass,
            "failed": handshake_fail,
            "results": handshake_results,
        },
        "aead_only_ratchet_validation": ratchet_checks,
        "negotiation_validation": negotiation_checks,
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "phase3_rekey_matrix_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["json_report_path"] = str(out_path)
    return report


def _print_summary(report: Dict[str, object]) -> None:
    state_space = report["state_space"]
    handshake = report["handshake_validation"]
    ratchet = report["aead_only_ratchet_validation"]
    negotiation = report["negotiation_validation"]
    print("Phase 3 core matrix validation")
    print(f"- runtime suites: {report['runtime_suite_count']}")
    print(f"- runtime states: {state_space['runtime_state_count']}")
    print(f"- transitions: {state_space['transition_count_total']}")
    print(f"- handshake: {handshake['passed']}/{handshake['checked']} passed")
    print(f"- ratchet: {ratchet['passed']}/{ratchet['checked']} passed")
    print(f"- negotiation: {negotiation['passed']}/{negotiation['checked']} passed")
    print(f"- report: {report['json_report_path']}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 3 core rekey matrix validation")
    parser.add_argument(
        "--out-dir",
        default=str(Path("logs") / "phase3_core"),
        help="Directory for JSON report output",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir).expanduser().resolve()
    report = run_phase3_matrix(out_dir=out_dir)
    _print_summary(report)

    handshake_failed = int(report["handshake_validation"]["failed"])
    ratchet_failed = int(report["aead_only_ratchet_validation"]["failed"])
    negotiation_failed = int(report["negotiation_validation"]["failed"])
    return 0 if (handshake_failed == 0 and ratchet_failed == 0 and negotiation_failed == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
