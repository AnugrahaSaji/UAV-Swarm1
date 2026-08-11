#!/usr/bin/env python3
"""
Phase 5: Drone Policy Validation Script

Validates the drone-side scheduler policy logic by:
1. Dry-run policy evaluation with synthetic telemetry
2. Testing threshold edge cases
3. Verifying JSONL log format compliance
4. Testing cooldown and dwell logic

Usage:
    python -m scripts.validate_drone_policy [--verbose]

Expected outputs documented inline.
"""

import sys
import time
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sscheduler.policy import (
    TelemetryAwarePolicyV1,
    DecisionInput,
    PolicyAction,
    PolicyOutput,
    get_suite_tier,
    find_adjacent_suite,
    TH_TELEMETRY_STALE_MS,
    TH_GAP_P95_MS,
    TH_SILENCE_MAX_MS,
    TH_JITTER_MS,
    TH_GCS_CPU_MEDIAN,
    TH_GCS_CPU_P95,
    TH_MIN_SAMPLES,
    TH_CONFIDENCE_LOW,
    COOLDOWN_SWITCH_S,
    COOLDOWN_REKEY_S,
    COOLDOWN_DOWNGRADE_S,
    DWELL_UPGRADE_S,
    DWELL_REKEY_S,
)
from sscheduler.telemetry_window import TelemetryWindow


# Test suites list
TEST_SUITES = [
    "cs-kyber512-aesgcm-dilithium2",  # L1 - tier ~0
    "cs-mlkem768-aesgcm-mldsa65",      # L3 - tier ~10
    "cs-mlkem1024-aesgcm-mldsa87",     # L5 - tier ~20
]


def banner(msg: str):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}")


def test_suite_tier_mapping():
    """Test suite tier calculation."""
    banner("TEST: Suite Tier Mapping")
    
    test_cases = [
        # (suite_name, expected_tier_range)
        ("cs-mlkem768-aesgcm-mldsa65", (10, 15)),  # L3 suite
        ("cs-mlkem1024-aesgcm-mldsa87", (20, 25)),  # L5 suite
        ("cs-kyber512-aesgcm-dilithium2", (0, 5)),  # L1 suite
        ("unknown-suite", (0, 100)),  # Default tier
    ]
    
    passed = 0
    for suite, (min_tier, max_tier) in test_cases:
        tier = get_suite_tier(suite)
        ok = min_tier <= tier <= max_tier
        status = "✓" if ok else "✗"
        print(f"  {status} get_suite_tier('{suite}') = {tier} (expected {min_tier}-{max_tier})")
        if ok:
            passed += 1
    
    print(f"\n  Result: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def test_find_adjacent_suite():
    """Test suite adjacency logic."""
    banner("TEST: Find Adjacent Suite")
    
    test_cases = [
        # (current, direction, expected_is_none)
        ("cs-mlkem1024-aesgcm-mldsa87", -1, False),   # L5 -> L3 (downgrade)
        ("cs-kyber512-aesgcm-dilithium2", -1, True),  # L1 -> None (lowest)
        ("cs-kyber512-aesgcm-dilithium2", +1, False), # L1 -> L3 (upgrade)
        ("cs-mlkem1024-aesgcm-mldsa87", +1, True),    # L5 -> None (highest)
    ]
    
    passed = 0
    for current, direction, expect_none in test_cases:
        result = find_adjacent_suite(current, TEST_SUITES, direction)
        is_none = result is None
        
        if expect_none:
            ok = is_none
        else:
            if direction < 0:
                ok = result is not None and get_suite_tier(result) < get_suite_tier(current)
            else:
                ok = result is not None and get_suite_tier(result) > get_suite_tier(current)
        
        dir_str = "down" if direction < 0 else "up"
        status = "✓" if ok else "✗"
        print(f"  {status} find_adjacent_suite('{current}', {dir_str}) = {result}")
        if ok:
            passed += 1
    
    print(f"\n  Result: {passed}/{len(test_cases)} passed")
    return passed == len(test_cases)


def make_decision_input(
    mono_ms: float = 1000000.0,
    telemetry_valid: bool = True,
    telemetry_age_ms: float = 100.0,
    sample_count: int = 30,
    rx_pps_median: float = 5.0,
    gap_p95_ms: float = 50.0,
    silence_max_ms: float = 80.0,
    jitter_ms: float = 10.0,
    gcs_cpu_median: float = 30.0,
    gcs_cpu_p95: float = 50.0,
    telemetry_last_seq: int = 100,
    mavproxy_alive: bool = True,
    collector_alive: bool = True,
    heartbeat_age_ms: float = 200.0,
    failsafe_active: bool = False,
    armed: bool = False,
    armed_duration_s: float = 0.0,
    remote_suite: str = None,
    remote_epoch: int = 0,
    expected_suite: str = "cs-mlkem768-aesgcm-mldsa65",
    current_tier: int = 10,
    local_epoch: int = 0,
    last_switch_mono_ms: float = 990000.0,  # 10s ago - within dwell time
    cooldown_until_mono_ms: float = 0.0,
) -> DecisionInput:
    """Factory for DecisionInput with defaults representing healthy state."""
    return DecisionInput(
        mono_ms=mono_ms,
        telemetry_valid=telemetry_valid,
        telemetry_age_ms=telemetry_age_ms,
        sample_count=sample_count,
        rx_pps_median=rx_pps_median,
        gap_p95_ms=gap_p95_ms,
        silence_max_ms=silence_max_ms,
        jitter_ms=jitter_ms,
        gcs_cpu_median=gcs_cpu_median,
        gcs_cpu_p95=gcs_cpu_p95,
        telemetry_last_seq=telemetry_last_seq,
        mavproxy_alive=mavproxy_alive,
        collector_alive=collector_alive,
        heartbeat_age_ms=heartbeat_age_ms,
        failsafe_active=failsafe_active,
        armed=armed,
        armed_duration_s=armed_duration_s,
        remote_suite=remote_suite,
        remote_epoch=remote_epoch,
        expected_suite=expected_suite,
        current_tier=current_tier,
        local_epoch=local_epoch,
        last_switch_mono_ms=last_switch_mono_ms,
        cooldown_until_mono_ms=cooldown_until_mono_ms,
    )


def test_policy_hold():
    """Test that healthy telemetry results in HOLD."""
    banner("TEST: Policy HOLD on Healthy Telemetry")
    
    policy = TelemetryAwarePolicyV1(TEST_SUITES)
    inp = make_decision_input()
    out = policy.evaluate(inp)
    
    ok = out.action == PolicyAction.HOLD
    status = "✓" if ok else "✗"
    print(f"  {status} Healthy telemetry -> {out.action.value}")
    print(f"      Confidence: {out.confidence:.2f}")
    print(f"      Reasons: {out.reasons}")
    
    return ok


def test_policy_downgrade_on_stale():
    """Test downgrade when telemetry is stale."""
    banner("TEST: Policy HOLD on Stale Telemetry (telemetry_stale gate)")
    
    policy = TelemetryAwarePolicyV1(TEST_SUITES)
    
    # Telemetry stale (> TH_TELEMETRY_STALE_MS)
    inp = make_decision_input(
        telemetry_age_ms=TH_TELEMETRY_STALE_MS + 500.0,  # Well over threshold
        last_switch_mono_ms=0.0,  # Long ago - no cooldown
    )
    out = policy.evaluate(inp)
    
    # Stale telemetry triggers HOLD (safety gate), not DOWNGRADE
    ok = out.action == PolicyAction.HOLD and "telemetry_stale" in out.reasons
    status = "✓" if ok else "✗"
    print(f"  {status} Stale telemetry ({inp.telemetry_age_ms}ms) -> {out.action.value}")
    print(f"      Reasons: {out.reasons}")
    
    return ok


def test_policy_downgrade_on_severe_stress():
    """Test downgrade when GCS CPU is severely stressed."""
    banner("TEST: Policy DOWNGRADE on Severe CPU Stress")
    
    policy = TelemetryAwarePolicyV1(TEST_SUITES)
    
    inp = make_decision_input(
        gcs_cpu_p95=TH_GCS_CPU_P95 + 5.0,  # Over p95 threshold (severe stress)
        last_switch_mono_ms=0.0,  # No cooldown
    )
    out = policy.evaluate(inp)
    
    ok = out.action == PolicyAction.DOWNGRADE
    status = "✓" if ok else "✗"
    print(f"  {status} Severe CPU stress (p95={inp.gcs_cpu_p95}%) -> {out.action.value}")
    print(f"      Target: {out.target_suite}")
    print(f"      Reasons: {out.reasons}")
    
    return ok


def test_policy_downgrade_on_high_silence():
    """Test downgrade when silence exceeds threshold significantly."""
    banner("TEST: Policy DOWNGRADE on High Silence")
    
    policy = TelemetryAwarePolicyV1(TEST_SUITES)
    
    # Silence > 1.5x threshold triggers immediate downgrade
    inp = make_decision_input(
        silence_max_ms=TH_SILENCE_MAX_MS * 1.6,  # Over 1.5x threshold
        last_switch_mono_ms=0.0,  # No cooldown
    )
    out = policy.evaluate(inp)
    
    ok = out.action == PolicyAction.DOWNGRADE
    status = "✓" if ok else "✗"
    print(f"  {status} High silence ({inp.silence_max_ms}ms) -> {out.action.value}")
    print(f"      Target: {out.target_suite}")
    print(f"      Reasons: {out.reasons}")
    
    return ok


def test_policy_hold_during_cooldown():
    """Test that cooldown blocks action."""
    banner("TEST: Policy HOLD During Cooldown")
    
    policy = TelemetryAwarePolicyV1(TEST_SUITES)
    
    # Severe stress BUT cooldown active
    now_ms = 1000000.0
    inp = make_decision_input(
        mono_ms=now_ms,
        cooldown_until_mono_ms=now_ms + 5000.0,  # Cooldown for 5 more seconds
        gcs_cpu_p95=TH_GCS_CPU_P95 + 5.0,  # Would trigger downgrade
    )
    out = policy.evaluate(inp)
    
    ok = out.action == PolicyAction.HOLD and "cooldown_active" in out.reasons
    status = "✓" if ok else "✗"
    print(f"  {status} Cooldown blocks action -> {out.action.value}")
    print(f"      Cooldown remaining: {out.cooldown_remaining_ms}ms")
    print(f"      Reasons: {out.reasons}")
    
    return ok


def test_policy_hold_on_low_confidence():
    """Test that low confidence (few samples) blocks action."""
    banner("TEST: Policy HOLD on Low Confidence (insufficient samples)")
    
    policy = TelemetryAwarePolicyV1(TEST_SUITES)
    
    inp = make_decision_input(
        sample_count=1,  # Too few samples (< TH_MIN_SAMPLES)
        gcs_cpu_p95=TH_GCS_CPU_P95 + 5.0,  # Would trigger downgrade
    )
    out = policy.evaluate(inp)
    
    ok = out.action == PolicyAction.HOLD and "insufficient_samples" in out.reasons
    status = "✓" if ok else "✗"
    print(f"  {status} Low sample count ({inp.sample_count}) blocks action -> {out.action.value}")
    print(f"      Reasons: {out.reasons}")
    
    return ok


def test_policy_downgrade_at_lowest():
    """Test that HOLD is returned when already at lowest tier."""
    banner("TEST: Policy HOLD at Lowest Tier (no lower suite available)")
    
    policy = TelemetryAwarePolicyV1(TEST_SUITES)
    
    # Already at L1 (lowest), with severe stress
    inp = make_decision_input(
        expected_suite="cs-kyber512-aesgcm-dilithium2",  # L1 - lowest
        current_tier=0,
        gcs_cpu_p95=TH_GCS_CPU_P95 + 5.0,  # Would trigger downgrade
        last_switch_mono_ms=0.0,
    )
    out = policy.evaluate(inp)
    
    # Should HOLD because no lower suite available
    ok = out.action == PolicyAction.HOLD and "degraded_no_lower_tier" in out.reasons
    status = "✓" if ok else "✗"
    print(f"  {status} At lowest tier -> {out.action.value}")
    print(f"      Current suite: {inp.expected_suite} (tier: {get_suite_tier(inp.expected_suite)})")
    print(f"      Reasons: {out.reasons}")
    
    return ok


def test_policy_failsafe_hold():
    """Test that failsafe mode forces HOLD."""
    banner("TEST: Policy HOLD in Failsafe Mode")
    
    policy = TelemetryAwarePolicyV1(TEST_SUITES)
    
    # Failsafe active - should block all actions
    inp = make_decision_input(
        failsafe_active=True,
        gcs_cpu_p95=TH_GCS_CPU_P95 + 5.0,  # Would trigger downgrade
    )
    out = policy.evaluate(inp)
    
    ok = out.action == PolicyAction.HOLD and "failsafe_active" in out.reasons
    status = "✓" if ok else "✗"
    print(f"  {status} Failsafe mode -> {out.action.value}")
    print(f"      Reasons: {out.reasons}")
    
    return ok


def test_telemetry_window():
    """Test TelemetryWindow bounded memory and stats."""
    banner("TEST: TelemetryWindow Bounded Memory")
    
    window = TelemetryWindow(window_s=3.0)
    
    # Add 600 samples (should cap at MAX_SAMPLES=500)
    now = time.monotonic()
    for i in range(600):
        packet = {
            "seq": i,
            "metrics": {
                "sys": {"cpu_pct": 30.0 + (i % 10), "mem_pct": 50.0},
            }
        }
        window.add(now + i * 0.01, packet)
    
    stats = window.summarize(now + 6.0)
    count = stats.get("sample_count", 0)
    
    ok = count <= 500
    status = "✓" if ok else "✗"
    print(f"  {status} Window capped at MAX_SAMPLES: count={count} (max=500)")
    print(f"      Gap P95: {stats.get('gap_p95_ms', 'N/A')}")
    print(f"      CPU Median: {stats.get('gcs_cpu_median', 'N/A')}")
    print(f"      Confidence: {stats.get('confidence', 'N/A')}")
    
    return ok


def test_decision_input_immutable():
    """Test that DecisionInput is frozen/immutable."""
    banner("TEST: DecisionInput Immutability")
    
    inp = make_decision_input()
    
    try:
        inp.mono_ms = 999.0  # Should raise
        ok = False
        print(f"  ✗ DecisionInput is mutable (should be frozen)")
    except Exception:
        ok = True
        print(f"  ✓ DecisionInput is frozen/immutable")
    
    return ok


def test_policy_output_to_dict():
    """Test PolicyOutput serialization."""
    banner("TEST: PolicyOutput Serialization")
    
    policy = TelemetryAwarePolicyV1(TEST_SUITES)
    inp = make_decision_input()
    out = policy.evaluate(inp)
    
    d = out.to_dict()
    
    # Check required keys
    required = ["action", "target_suite", "reasons", "confidence"]
    ok = all(k in d for k in required)
    
    status = "✓" if ok else "✗"
    print(f"  {status} PolicyOutput.to_dict() contains required keys")
    print(f"      Keys: {list(d.keys())}")
    print(f"      JSON: {json.dumps(d)}")
    
    return ok


def test_receiver_health_gate():
    """Test that dead mavproxy triggers HOLD."""
    banner("TEST: Policy HOLD on Dead MAVProxy")
    
    policy = TelemetryAwarePolicyV1(TEST_SUITES)
    
    inp = make_decision_input(
        mavproxy_alive=False,
    )
    out = policy.evaluate(inp)
    
    ok = out.action == PolicyAction.HOLD and "mavproxy_dead" in out.reasons
    status = "✓" if ok else "✗"
    print(f"  {status} MAVProxy dead -> {out.action.value}")
    print(f"      Reasons: {out.reasons}")
    
    return ok


def run_all_tests(verbose: bool = False) -> bool:
    """Run all validation tests."""
    banner("DRONE POLICY VALIDATION SUITE")
    print(f"  Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print(f"  Thresholds:")
    print(f"    TH_TELEMETRY_STALE_MS = {TH_TELEMETRY_STALE_MS}")
    print(f"    TH_GAP_P95_MS = {TH_GAP_P95_MS}")
    print(f"    TH_SILENCE_MAX_MS = {TH_SILENCE_MAX_MS}")
    print(f"    TH_GCS_CPU_P95 = {TH_GCS_CPU_P95}")
    print(f"    TH_MIN_SAMPLES = {TH_MIN_SAMPLES}")
    print(f"    COOLDOWN_SWITCH_S = {COOLDOWN_SWITCH_S}")
    
    tests = [
        test_suite_tier_mapping,
        test_find_adjacent_suite,
        test_policy_hold,
        test_policy_downgrade_on_stale,
        test_policy_downgrade_on_severe_stress,
        test_policy_downgrade_on_high_silence,
        test_policy_hold_during_cooldown,
        test_policy_hold_on_low_confidence,
        test_policy_downgrade_at_lowest,
        test_policy_failsafe_hold,
        test_receiver_health_gate,
        test_telemetry_window,
        test_decision_input_immutable,
        test_policy_output_to_dict,
    ]
    
    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n  ✗ {test.__name__} CRASHED: {e}")
            if verbose:
                import traceback
                traceback.print_exc()
            results.append(False)
    
    passed = sum(results)
    total = len(results)
    
    banner("SUMMARY")
    print(f"  Tests Passed: {passed}/{total}")
    
    if passed == total:
        print(f"  Status: ✓ ALL TESTS PASSED")
        return True
    else:
        print(f"  Status: ✗ SOME TESTS FAILED")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Drone Policy Validation")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    
    success = run_all_tests(verbose=args.verbose)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
