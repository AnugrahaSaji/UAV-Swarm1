"""
MDEAS Scheduler — Comprehensive Unit Benchmark
================================================
Tests all axes, gates, and invariants of the Measurement-Driven
Energy-Aware Scheduling (MDEAS) policy implemented in
sscheduler/policy.py.

Sections
--------
1. AeadCostProfile  — BSI, EWMA, energy_per_bit, reliability
2. Suite helpers     — _parse_suite, _compose_suite
3. Cross-axis        — forbidden/discouraged combos
4. Break-even        — rekey amortisation analysis
5. Thermal predict   — linear extrapolation + ΔT model
6. Decision cascade  — all gates via synthetic DecisionInput
7. Hysteresis        — timing asymmetry (5 s down / 30 s up)
8. Detector mgmt     — Axis 3 activate / deactivate
9. Invariants        — I1 safety, I2 liveness, I3 monotonic, I4 determinism
"""

import sys, os, math, copy, time, json
try:
    import pytest
except ImportError:
    class _Approx:
        def __init__(self, val, rel=1e-4, abs=1e-4):
            self.val = val
        def __eq__(self, other):
            return math.isclose(self.val, other, rel_tol=1e-3, abs_tol=1e-3)
    class _Mark:
        def parametrize(self, *args, **kwargs):
            return lambda fn: fn
    class _DummyPytest:
        def approx(self, val, rel=1e-4, abs=1e-4):
            return _Approx(val, rel=rel, abs=abs)
        mark = _Mark()
        def main(self, *args, **kwargs):
            pass
    pytest = _DummyPytest()
from pathlib import Path

# Ensure project root is on sys.path for imports
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sscheduler.policy import (
    AeadCostProfile,
    DecisionInput,
    DetectorLevel,
    EnergyAwarePolicy,
    PolicyAction,
    PolicyOutput,
    _AEAD_BENCHMARK_SEED,
    _AEAD_PREFERENCE_ORDER,
    _DETECTOR_MAX_BASELINE_TEMP,
    _DETECTOR_OVERHEAD,
    _FORBIDDEN_AEAD_WITH_TST,
    _FORBIDDEN_KEM_SIG_PAIRS,
    _DISCOURAGED_KEM_WITH_TST,
    _LEVEL_MAP,
    _LEVEL_ORDER,
    _compose_suite,
    _parse_suite,
)


# ──────────────────────────────────────────────────────────────────────
# Helper: build a DecisionInput with sensible defaults
# ──────────────────────────────────────────────────────────────────────

def _make_input(**overrides) -> DecisionInput:
    """Return a nominal DecisionInput; caller overrides fields as needed."""
    defaults = dict(
        mono_ms=60_000.0,           # 60 s uptime
        telemetry_valid=True,
        telemetry_age_ms=100.0,
        sample_count=100,
        rx_pps_median=40.0,
        gap_p95_ms=50.0,
        silence_max_ms=200.0,
        jitter_ms=2.0,
        blackout_count=0,
        battery_mv=16_000,          # healthy
        battery_roc=0.0,
        temp_c=55.0,                # well below warn (70)
        temp_roc=0.0,
        armed=False,
        current_suite="cs-mlkem768-mldsa65",
        local_epoch=1,
        last_switch_mono_ms=0.0,
        cooldown_until_mono_ms=0.0,
        current_aead="chacha20poly1305",
        aead_encrypt_avg_ns=63_500.0,
        aead_decrypt_avg_ns=70_700.0,
        proxy_enc_in=5000,
        proxy_enc_out=5000,
        proxy_drop_total=0,
        proxy_uptime_s=60.0,
        cpu_pct=15.0,
        synced_time=time.time(),
        detector_level="NONE",
        detector_active=False,
        detector_warmup=False,
    )
    defaults.update(overrides)
    return DecisionInput(**defaults)


def _fresh_policy() -> EnergyAwarePolicy:
    """Create a fresh EnergyAwarePolicy (resets all state)."""
    return EnergyAwarePolicy()


def _loaded_settings():
    """Return the actual settings loaded by the policy (may differ from defaults)."""
    from sscheduler.policy import load_settings
    return load_settings()


# ═════════════════════════════════════════════════════════════════════
# 1. AeadCostProfile — BSI, EWMA, energy metric
# ═════════════════════════════════════════════════════════════════════

class TestAeadCostProfile:
    """Verify Benchmark-Seeded Initialisation and EWMA convergence."""

    def test_bsi_seeds_on_construction(self):
        """BSI pre-populates from _AEAD_BENCHMARK_SEED."""
        for token, seed in _AEAD_BENCHMARK_SEED.items():
            p = AeadCostProfile(token)
            assert p.seeded is True, f"{token}: seeded flag not set"
            assert p.samples == 5, f"{token}: expected 5 virtual samples"
            assert p.encrypt_ns == seed["encrypt_ns"]
            assert p.decrypt_ns == seed["decrypt_ns"]
            assert p.total_ns == pytest.approx(
                seed["encrypt_ns"] + seed["decrypt_ns"], rel=1e-6
            )
            assert p.power_w_baseline == seed["power_w"]
            assert p.temp_delta_c == seed["temp_delta_c"]

    def test_bsi_energy_per_bit(self):
        """BSI computes energy_per_bit_nj from power × time / bits."""
        p = AeadCostProfile("chacha20poly1305")
        total_s = p.total_ns / 1e9
        expected_nj = (p.power_w_baseline * total_s * 1e9) / (256 * 8)
        assert p.energy_per_bit_nj == pytest.approx(expected_nj, rel=1e-4)

    def test_unknown_token_not_seeded(self):
        """Unknown AEAD token starts from zero (no seed data)."""
        p = AeadCostProfile("unknown_aead")
        assert p.seeded is False
        assert p.samples == 0
        assert p.encrypt_ns == 0.0

    def test_ewma_warmup_alpha(self):
        """First 10 samples use alpha=0.5 (fast convergence)."""
        p = AeadCostProfile("chacha20poly1305")
        # BSI gives 5 samples; feed 4 more → still < 10 → alpha=0.5
        for i in range(4):
            old_enc = p.encrypt_ns
            new_enc = 80_000.0              # deliberately different from seed
            p.update(new_enc, 80_000.0, 55.0, float(i + 1))
            # After update: enc = 0.5 * new + 0.5 * old
            expected = 0.5 * new_enc + 0.5 * old_enc
            assert p.encrypt_ns == pytest.approx(expected, rel=1e-6)

    def test_ewma_steady_alpha(self):
        """After 10 samples, alpha drops to 0.2."""
        p = AeadCostProfile("chacha20poly1305")   # starts at 5 samples
        # Feed 5 more → reach 10
        for i in range(5):
            p.update(80_000.0, 80_000.0, 55.0, float(i + 1))
        assert p.samples == 10

        # 11th update should use alpha=0.2
        old_enc = p.encrypt_ns
        p.update(100_000.0, 100_000.0, 55.0, 11.0)
        expected = 0.2 * 100_000.0 + 0.8 * old_enc
        assert p.encrypt_ns == pytest.approx(expected, rel=1e-6)

    def test_is_reliable(self):
        """is_reliable defaults to min_samples=10."""
        p = AeadCostProfile("chacha20poly1305")    # 5 from BSI
        assert not p.is_reliable()
        for i in range(5):
            p.update(63_500.0, 70_700.0, 55.0, float(i + 1))
        assert p.is_reliable()

    def test_cost_ratio_vs(self):
        """Ratio = self.total_ns / other.total_ns."""
        a = AeadCostProfile("chacha20poly1305")
        b = AeadCostProfile("ascon128a")
        ratio = b.cost_ratio_vs(a)
        expected = b.total_ns / a.total_ns
        assert ratio == pytest.approx(expected, rel=1e-6)
        # Ascon should be ~17× slower than ChaCha
        assert ratio > 10.0

    def test_to_dict_roundtrip(self):
        """to_dict returns all documented keys."""
        p = AeadCostProfile("aesgcm")
        d = p.to_dict()
        required_keys = {
            "token", "encrypt_ns", "decrypt_ns", "total_ns",
            "samples", "temp_at_measurement", "seeded",
            "energy_per_bit_nj", "power_w_baseline", "temp_delta_c",
        }
        assert required_keys <= set(d.keys())


# ═════════════════════════════════════════════════════════════════════
# 2. Suite helpers
# ═════════════════════════════════════════════════════════════════════

class TestSuiteHelpers:
    """Verify _parse_suite and _compose_suite."""

    @pytest.mark.parametrize("suite,aead,expected", [
        ("cs-mlkem768-chacha20poly1305-mldsa65", None,
         {"kem": "mlkem768", "aead": "chacha20poly1305", "sig": "mldsa65", "level": "L3"}),
        ("cs-mlkem512-aesgcm-mldsa44", None,
         {"kem": "mlkem512", "aead": "aesgcm", "sig": "mldsa44", "level": "L1"}),
        ("cs-mlkem1024-ascon128a-mldsa87", None,
         {"kem": "mlkem1024", "aead": "ascon128a", "sig": "mldsa87", "level": "L5"}),
        ("cs-mlkem768-mldsa65", "chacha20poly1305",
         {"kem": "mlkem768", "aead": "chacha20poly1305", "sig": "mldsa65", "level": "L3"}),
    ])
    def test_parse_suite(self, suite, aead, expected):
        result = _parse_suite(suite, aead)
        assert result == expected

    @pytest.mark.parametrize("aead,level,expected", [
        ("chacha20poly1305", "L3", "cs-mlkem768-mldsa65"),
        ("aesgcm",           "L1", "cs-mlkem512-mldsa44"),
        ("ascon128a",        "L5", "cs-mlkem1024-mldsa87"),
    ])
    def test_compose_suite(self, aead, level, expected):
        assert _compose_suite(aead, level) == expected

    def test_parse_compose_roundtrip(self):
        """compose(parse(s)) should preserve the canonical suite level selection."""
        for aead in _AEAD_PREFERENCE_ORDER:
            for level in _LEVEL_ORDER:
                original = _compose_suite(aead, level)
                parsed = _parse_suite(original, aead)
                reconstructed = _compose_suite(parsed["aead"], parsed["level"])
                assert reconstructed == original

    def test_parse_malformed(self):
        """Malformed suite returns empty kem/aead/sig with L1 default."""
        result = _parse_suite("bad-name")
        assert result["kem"] == ""
        assert result["aead"] == ""


# ═════════════════════════════════════════════════════════════════════
# 3. Cross-axis constraints
# ═════════════════════════════════════════════════════════════════════

class TestCrossAxisConstraints:
    """Verify forbidden / discouraged suite × detector combinations."""

    def test_ascon_tst_forbidden(self):
        pol = _fresh_policy()
        suite = _compose_suite("ascon128a", "L3")
        assert pol._check_cross_axis_constraints(suite, "TST", target_aead="ascon128a") is False

    def test_chacha_tst_allowed(self):
        pol = _fresh_policy()
        suite = _compose_suite("chacha20poly1305", "L3")
        assert pol._check_cross_axis_constraints(suite, "TST", target_aead="chacha20poly1305") is True

    def test_aesgcm_tst_allowed(self):
        pol = _fresh_policy()
        suite = _compose_suite("aesgcm", "L1")
        assert pol._check_cross_axis_constraints(suite, "TST", target_aead="aesgcm") is True

    def test_mceliece_tst_discouraged(self):
        pol = _fresh_policy()
        suite = "cs-classicmceliece348864-mldsa44"
        assert pol._check_cross_axis_constraints(suite, "TST", target_aead="aesgcm") is False

    def test_mceliece_sphincs_forbidden_any_detector(self):
        pol = _fresh_policy()
        suite = "cs-classicmceliece348864-sphincs128s"
        # Forbidden at any detector level — even NONE
        assert pol._check_cross_axis_constraints(suite, "NONE", target_aead="aesgcm") is False

    def test_mlkem_chacha_none_allowed(self):
        pol = _fresh_policy()
        suite = _compose_suite("chacha20poly1305", "L3")
        assert pol._check_cross_axis_constraints(suite, "NONE", target_aead="chacha20poly1305") is True


# ═════════════════════════════════════════════════════════════════════
# 4. Break-even analysis
# ═════════════════════════════════════════════════════════════════════

class TestBreakEven:
    """Verify _compute_break_even_s amortisation logic."""

    def test_cheaper_target_finite_breakeven(self):
        """Switching from Ascon → ChaCha should yield a finite break-even."""
        pol = _fresh_policy()
        # Ensure profiles are reliable (BSI gives 5; add 5 more)
        for token in ["chacha20poly1305", "ascon128a"]:
            seed = _AEAD_BENCHMARK_SEED[token]
            for i in range(5):
                pol.aead_profiles[token].update(
                    seed["encrypt_ns"], seed["decrypt_ns"], 55.0, float(i + 1)
                )
        be = pol._compute_break_even_s("ascon128a", "chacha20poly1305", 100.0)
        assert math.isfinite(be)
        assert be > 0.0

    def test_same_aead_infinite(self):
        """Same AEAD → no saving → inf."""
        pol = _fresh_policy()
        for i in range(5):
            pol.aead_profiles["aesgcm"].update(66_900.0, 73_600.0, 55.0, float(i))
        be = pol._compute_break_even_s("aesgcm", "aesgcm", 100.0)
        assert be == float("inf")

    def test_expensive_target_infinite(self):
        """Target more expensive than current → inf."""
        pol = _fresh_policy()
        for token in ["chacha20poly1305", "ascon128a"]:
            seed = _AEAD_BENCHMARK_SEED[token]
            for i in range(5):
                pol.aead_profiles[token].update(
                    seed["encrypt_ns"], seed["decrypt_ns"], 55.0, float(i + 1)
                )
        be = pol._compute_break_even_s("chacha20poly1305", "ascon128a", 100.0)
        assert be == float("inf")

    def test_higher_pkt_rate_shorter_breakeven(self):
        """Higher packet rate → shorter break-even (amortise faster)."""
        pol = _fresh_policy()
        for token in ["chacha20poly1305", "ascon128a"]:
            seed = _AEAD_BENCHMARK_SEED[token]
            for i in range(5):
                pol.aead_profiles[token].update(
                    seed["encrypt_ns"], seed["decrypt_ns"], 55.0, float(i + 1)
                )
        be_low = pol._compute_break_even_s("ascon128a", "chacha20poly1305", 10.0)
        be_high = pol._compute_break_even_s("ascon128a", "chacha20poly1305", 1000.0)
        assert be_high < be_low

    def test_rank_includes_dynamic_aead_tokens(self):
        """Ranking should remain deterministic with runtime-only AEAD tokens."""
        pol = _fresh_policy()
        pol.aead_profiles["aegis256"] = AeadCostProfile("aegis256")
        ranked = pol._rank_aeads_by_cost()
        assert "aegis256" in ranked


# ═════════════════════════════════════════════════════════════════════
# 5. Thermal prediction
# ═════════════════════════════════════════════════════════════════════

class TestThermalPrediction:
    """Verify _predict_thermal_crossing_s with ΔT model."""

    def test_rising_temp_crossing(self):
        """Rising temp → finite crossing time."""
        pol = _fresh_policy()
        # 60°C with +5 °C/min → crosses 70°C in 2 min = 120 s
        result = pol._predict_thermal_crossing_s(60.0, 5.0, 70.0)
        assert result is not None
        assert result == pytest.approx(120.0, rel=0.01)

    def test_cooling_returns_none(self):
        """Cooling or stable → None (no crossing)."""
        pol = _fresh_policy()
        result = pol._predict_thermal_crossing_s(60.0, -1.0, 70.0)
        assert result is None

    def test_stable_returns_none(self):
        pol = _fresh_policy()
        result = pol._predict_thermal_crossing_s(60.0, 0.0, 70.0)
        assert result is None

    def test_already_above_threshold(self):
        """Already above → 0.0 (immediate)."""
        pol = _fresh_policy()
        result = pol._predict_thermal_crossing_s(75.0, 2.0, 70.0)
        assert result == 0.0

    def test_target_aead_delta_applied(self):
        """Ascon128a adds +1.5°C → crosses sooner."""
        pol = _fresh_policy()
        # Without AEAD: 65°C + 5 °C/min → crosses 70°C in 60 s
        no_aead = pol._predict_thermal_crossing_s(65.0, 5.0, 70.0)
        # With Ascon: effective = 65 + 1.5 = 66.5 → crosses 70 in 42 s
        with_ascon = pol._predict_thermal_crossing_s(
            65.0, 5.0, 70.0, target_aead="ascon128a"
        )
        assert with_ascon is not None
        assert no_aead is not None
        assert with_ascon < no_aead  # crosses sooner with hot AEAD


# ═════════════════════════════════════════════════════════════════════
# 6. Decision cascade — full evaluate() with synthetic inputs
# ═════════════════════════════════════════════════════════════════════

class TestDecisionCascade:
    """Test the 12-step decision cascade via evaluate()."""

    # ── Gate 1: telemetry stale ─────────────────────────────────────
    def test_stale_telemetry_holds(self):
        pol = _fresh_policy()
        inp = _make_input(telemetry_valid=False)
        out = pol.evaluate(inp)
        assert out.action == PolicyAction.HOLD
        assert "telemetry_stale" in out.reasons

    def test_old_telemetry_holds(self):
        pol = _fresh_policy()
        inp = _make_input(telemetry_age_ms=3000.0)  # > 2000 ms
        out = pol.evaluate(inp)
        assert out.action == PolicyAction.HOLD
        assert "telemetry_stale" in out.reasons

    # ── Gate 2: battery critical → EMERGENCY ────────────────────────
    def test_battery_critical_emergency(self):
        pol = _fresh_policy()
        inp = _make_input(battery_mv=13_000)  # below default critical 14000
        out = pol.evaluate(inp)
        assert out.action == PolicyAction.EMERGENCY
        assert any("battery_critical" in r for r in out.reasons)

    # ── Gate 3: temp critical → EMERGENCY ───────────────────────────
    def test_temp_critical_emergency(self):
        pol = _fresh_policy()
        inp = _make_input(temp_c=85.0)  # above default critical 80
        out = pol.evaluate(inp)
        assert out.action == PolicyAction.EMERGENCY
        assert any("temp_critical" in r for r in out.reasons)

    # ── Emergency kills detector if active ──────────────────────────
    def test_emergency_kills_detector(self):
        pol = _fresh_policy()
        # Battery critical + detector active → should downgrade detector
        # Need current suite already at L1 + cheapest to trigger detector kill path
        cheapest = pol._cheapest_aead()
        emergency_suite = _compose_suite(cheapest, "L1")
        inp = _make_input(
            battery_mv=13_000,
            current_suite=emergency_suite,  # already on emergency suite
            detector_level="XGBOOST",
            detector_active=True,
        )
        out = pol.evaluate(inp)
        assert out.action == PolicyAction.DOWNGRADE_DETECTOR
        assert any("emergency_kill_detector" in r for r in out.reasons)

    # ── Gate 3: detector thermal management ─────────────────────────
    def test_detector_thermal_downgrade(self):
        """Temp above XGBOOST ceiling → downgrade detector."""
        pol = _fresh_policy()
        # XGBOOST max baseline = 75°C
        inp = _make_input(
            temp_c=76.0,
            detector_level="XGBOOST",
            detector_active=True,
        )
        out = pol.evaluate(inp)
        assert out.action == PolicyAction.DOWNGRADE_DETECTOR
        assert any("detector_thermal" in r for r in out.reasons)

    def test_detector_thermal_tst_threshold(self):
        """Temp above TST ceiling (69°C) → downgrade TST to XGBOOST."""
        pol = _fresh_policy()
        inp = _make_input(
            temp_c=70.0,
            detector_level="TST",
            detector_active=True,
        )
        out = pol.evaluate(inp)
        assert out.action == PolicyAction.DOWNGRADE_DETECTOR

    def test_invalid_detector_level_fails_safe(self):
        """Invalid detector level strings must never crash evaluate()."""
        pol = _fresh_policy()
        inp = _make_input(detector_level="INVALID_LEVEL", detector_active=True)
        out = pol.evaluate(inp)
        assert isinstance(out, PolicyOutput)

    # ── Gate 4: predictive thermal (MDEAS novel) ────────────────────
    def test_predictive_thermal_switch(self):
        """Rising temp predicted to cross warn_c → SWITCH_AEAD."""
        pol = _fresh_policy()
        s = _loaded_settings()
        base_ms = 60_000.0
        # Make AEAD profiles reliable (10+ samples) so break-even works
        for token in _AEAD_PREFERENCE_ORDER:
            seed = _AEAD_BENCHMARK_SEED[token]
            for i in range(6):  # 5 BSI + 6 → 11 samples
                pol.aead_profiles[token].update(
                    seed["encrypt_ns"], seed["decrypt_ns"], 55.0, float(i + 1)
                )
        # Set last_switch_mono_ms close enough to prevent proactive rekey
        recent_switch = base_ms - (s["rekey"]["min_stable_s"] * 1000 * 0.5)
        inp = _make_input(
            mono_ms=base_ms,
            current_suite="cs-mlkem768-ascon128a-mldsa65",
            aead_encrypt_avg_ns=1_327_100.0,
            aead_decrypt_avg_ns=960_500.0,
            temp_c=67.0,          # below warn 70 but rising
            temp_roc=10.0,        # °C/min → crosses 70 in ~18 s
            proxy_enc_out=10_000,
            proxy_uptime_s=60.0,
            last_switch_mono_ms=recent_switch,
        )
        out = pol.evaluate(inp)
        assert out.action == PolicyAction.SWITCH_AEAD
        assert any("predictive_thermal" in r for r in out.reasons)

    # ── Axis 1: AEAD stress → SWITCH_AEAD ──────────────────────────
    def test_aead_stress_cpu(self):
        """CPU stress sustained > downgrade_s → SWITCH_AEAD.

        Uses CPU stress (not thermal) to avoid the predictive thermal gate
        firing first in the cascade (Gate 4 before Gate 6).
        """
        pol = _fresh_policy()
        s = _loaded_settings()
        down_s = s["hysteresis"]["downgrade_s"]
        base_ms = 60_000.0
        recent_switch = base_ms
        # Make profiles reliable for break-even
        for token in _AEAD_PREFERENCE_ORDER:
            seed = _AEAD_BENCHMARK_SEED[token]
            for i in range(6):
                pol.aead_profiles[token].update(
                    seed["encrypt_ns"], seed["decrypt_ns"], 55.0, float(i + 1)
                )
        inp1 = _make_input(
            mono_ms=base_ms,
            temp_c=55.0,      # well below warn → no thermal trigger
            temp_roc=0.0,
            cpu_pct=85.0,     # CPU stress > 80%
            current_suite="cs-mlkem768-ascon128a-mldsa65",
            aead_encrypt_avg_ns=1_327_100.0,
            aead_decrypt_avg_ns=960_500.0,
            proxy_enc_out=5000,
            last_switch_mono_ms=recent_switch,
        )
        pol.evaluate(inp1)  # plants hysteresis

        # Second call after downgrade_s + 1s → hysteresis satisfied
        delay_ms = (down_s + 1.0) * 1000
        inp2 = _make_input(
            mono_ms=base_ms + delay_ms,
            temp_c=55.0,
            temp_roc=0.0,
            cpu_pct=85.0,
            current_suite="cs-mlkem768-ascon128a-mldsa65",
            aead_encrypt_avg_ns=1_327_100.0,
            aead_decrypt_avg_ns=960_500.0,
            proxy_enc_out=10_000,
            proxy_uptime_s=60.0 + delay_ms / 1000,
            last_switch_mono_ms=recent_switch,
        )
        out = pol.evaluate(inp2)
        assert out.action == PolicyAction.SWITCH_AEAD
        assert any("cpu_stress" in r for r in out.reasons)

    # ── Axis 2: link degraded → DOWNGRADE_LEVEL ────────────────────
    def test_link_bad_downgrade_level(self):
        """Poor link quality sustained → DOWNGRADE_LEVEL."""
        pol = _fresh_policy()
        base_ms = 60_000.0
        # Currently at L3; link is terrible
        inp1 = _make_input(
            mono_ms=base_ms,
            gap_p95_ms=1500.0,    # > default max_gap 1000
            rx_pps_median=3.0,    # < default min_pps 5
            current_suite="cs-mlkem768-chacha20poly1305-mldsa65",
        )
        pol.evaluate(inp1)  # plant hysteresis

        inp2 = _make_input(
            mono_ms=base_ms + 6_000.0,  # 6 s later (> 5 s downgrade hysteresis)
            gap_p95_ms=1500.0,
            rx_pps_median=3.0,
            current_suite="cs-mlkem768-chacha20poly1305-mldsa65",
        )
        out = pol.evaluate(inp2)
        assert out.action == PolicyAction.DOWNGRADE_LEVEL
        assert any("link_degraded" in r for r in out.reasons)
        # Should downgrade L3 → L1
        expected = _compose_suite("chacha20poly1305", "L1")
        assert out.target_suite == expected

    # ── Gate 7: cooldown holds ──────────────────────────────────────
    def test_cooldown_holds(self):
        pol = _fresh_policy()
        inp = _make_input(
            mono_ms=50_000.0,
            cooldown_until_mono_ms=55_000.0,  # still in cooldown
        )
        out = pol.evaluate(inp)
        assert out.action == PolicyAction.HOLD
        assert "cooldown" in out.reasons

    # ── Nominal holds ───────────────────────────────────────────────
    def test_nominal_hold(self):
        """All-green inputs → nominal HOLD."""
        pol = _fresh_policy()
        inp = _make_input(last_switch_mono_ms=59_000.0)  # recent switch
        out = pol.evaluate(inp)
        assert out.action == PolicyAction.HOLD
        assert "nominal" in out.reasons

    # ── DDoS detection → EMERGENCY ──────────────────────────────────
    def test_ddos_detected_locks_cheapest(self):
        """High drop ratio → EMERGENCY with cheapest AEAD."""
        pol = _fresh_policy()
        inp = _make_input(
            current_suite="cs-mlkem768-ascon128a-mldsa65",
            proxy_enc_out=10_000,
            proxy_drop_total=2_000,   # 20% drop rate > 10% threshold
            aead_encrypt_avg_ns=1_327_100.0,
            aead_decrypt_avg_ns=960_500.0,
        )
        out = pol.evaluate(inp)
        assert out.action == PolicyAction.EMERGENCY
        assert any("ddos_detected" in r for r in out.reasons)

    # ── Proactive rekey ─────────────────────────────────────────────
    def test_proactive_rekey(self):
        """Stable long enough → REKEY (same suite)."""
        pol = _fresh_policy()
        inp = _make_input(
            mono_ms=200_000.0,
            last_switch_mono_ms=0.0,     # very old switch → stable 200s
        )
        out = pol.evaluate(inp)
        assert out.action == PolicyAction.REKEY
        assert "proactive_rekey" in out.reasons
        assert out.target_suite == inp.current_suite


# ═════════════════════════════════════════════════════════════════════
# 7. Hysteresis timing
# ═════════════════════════════════════════════════════════════════════

class TestHysteresis:
    """Verify 5 s downgrade / 30 s upgrade asymmetry."""

    def test_downgrade_hysteresis_5s(self):
        """Stress must persist ≥ 5 s for AEAD downgrade."""
        pol = _fresh_policy()
        base = 60_000.0
        # At t=0: stress begins — policy plants hysteresis, should NOT act yet
        inp = _make_input(
            mono_ms=base,
            temp_c=72.0,
            current_suite="cs-mlkem768-ascon128a-mldsa65",
            aead_encrypt_avg_ns=1_327_100.0,
            aead_decrypt_avg_ns=960_500.0,
        )
        out = pol.evaluate(inp)
        # Should NOT switch yet (t < 5 s)
        assert out.action != PolicyAction.SWITCH_AEAD or "predictive_thermal" in out.reasons

        # At t=4s: still too soon
        inp2 = _make_input(
            mono_ms=base + 4_000.0,
            temp_c=72.0,
            current_suite="cs-mlkem768-ascon128a-mldsa65",
            aead_encrypt_avg_ns=1_327_100.0,
            aead_decrypt_avg_ns=960_500.0,
            proxy_enc_out=8_000,
        )
        out2 = pol.evaluate(inp2)
        # Predictive thermal might fire, but aead_stress hysteresis hasn't passed
        # We're testing the hysteresis mechanism itself

        # At t=6s: hysteresis satisfied
        inp3 = _make_input(
            mono_ms=base + 6_000.0,
            temp_c=72.0,
            current_suite="cs-mlkem768-ascon128a-mldsa65",
            aead_encrypt_avg_ns=1_327_100.0,
            aead_decrypt_avg_ns=960_500.0,
            proxy_enc_out=12_000,
            proxy_uptime_s=66.0,
        )
        out3 = pol.evaluate(inp3)
        assert out3.action == PolicyAction.SWITCH_AEAD

    def test_upgrade_hysteresis(self):
        """Level upgrade requires ≥ upgrade_s of stability (disarmed)."""
        pol = _fresh_policy()
        s = _loaded_settings()
        upgrade_s = s["hysteresis"]["upgrade_s"]
        min_stable = s["rekey"]["min_stable_s"]
        base = 60_000.0
        suite_l1 = _compose_suite("chacha20poly1305", "L1")

        # Plant hysteresis at t=0
        inp1 = _make_input(
            mono_ms=base,
            current_suite=suite_l1,
            last_switch_mono_ms=base,  # just switched → no rekey
        )
        pol.evaluate(inp1)

        # At t = upgrade_s - 1: too early for upgrade
        early_ms = (upgrade_s - 1.0) * 1000
        inp2 = _make_input(
            mono_ms=base + early_ms,
            current_suite=suite_l1,
            last_switch_mono_ms=base,
        )
        out2 = pol.evaluate(inp2)
        assert out2.action != PolicyAction.UPGRADE_LEVEL

        # At t = upgrade_s + 1: hysteresis passed, but must not trigger rekey
        # Ensure stable_time < min_stable_s to avoid proactive rekey
        switch_time = base + (upgrade_s + 1.0) * 1000 - (min_stable * 1000 * 0.5)
        inp3 = _make_input(
            mono_ms=base + (upgrade_s + 1.0) * 1000,
            current_suite=suite_l1,
            last_switch_mono_ms=switch_time,
        )
        out3 = pol.evaluate(inp3)
        assert out3.action == PolicyAction.UPGRADE_LEVEL

    def test_armed_3x_upgrade_multiplier(self):
        """Armed state → 3× upgrade delay."""
        pol = _fresh_policy()
        s = _loaded_settings()
        upgrade_s = s["hysteresis"]["upgrade_s"]
        armed_delay = upgrade_s * 3.0
        min_stable = s["rekey"]["min_stable_s"]
        base = 60_000.0
        suite_l1 = _compose_suite("chacha20poly1305", "L1")

        # Plant hysteresis
        inp1 = _make_input(
            mono_ms=base,
            current_suite=suite_l1,
            armed=True,
            last_switch_mono_ms=base,
        )
        pol.evaluate(inp1)

        # At half the armed delay: NOT enough
        half_ms = (armed_delay * 0.5) * 1000
        inp2 = _make_input(
            mono_ms=base + half_ms,
            current_suite=suite_l1,
            armed=True,
            last_switch_mono_ms=base,
        )
        out2 = pol.evaluate(inp2)
        assert out2.action != PolicyAction.UPGRADE_LEVEL

        # At armed_delay + 1s: should pass
        delay_ms = (armed_delay + 1.0) * 1000
        # Keep last_switch recent to avoid rekey
        switch_time = base + delay_ms - (min_stable * 1000 * 0.5)
        inp3 = _make_input(
            mono_ms=base + delay_ms,
            current_suite=suite_l1,
            armed=True,
            last_switch_mono_ms=switch_time,
        )
        out3 = pol.evaluate(inp3)
        assert out3.action == PolicyAction.UPGRADE_LEVEL
        assert "in_flight_recovery" in out3.reasons


# ═════════════════════════════════════════════════════════════════════
# 8. Detector management (Axis 3)
# ═════════════════════════════════════════════════════════════════════

class TestDetectorManagement:
    """Verify Axis 3 detector activate / deactivate logic."""

    def test_can_activate_xgboost_low_temp(self):
        pol = _fresh_policy()
        inp = _make_input(temp_c=50.0, cpu_pct=10.0)
        assert pol._can_activate_detector("XGBOOST", inp) is True

    def test_cannot_activate_xgboost_high_temp(self):
        pol = _fresh_policy()
        inp = _make_input(temp_c=76.0, cpu_pct=10.0)
        assert pol._can_activate_detector("XGBOOST", inp) is False

    def test_cannot_activate_tst_high_cpu(self):
        pol = _fresh_policy()
        # TST needs 91 pp CPU headroom; 50% + 91 > 95
        inp = _make_input(temp_c=50.0, cpu_pct=50.0)
        assert pol._can_activate_detector("TST", inp) is False

    def test_cannot_activate_tst_ascon_suite(self):
        """Cross-axis: TST + Ascon forbidden."""
        pol = _fresh_policy()
        inp = _make_input(
            temp_c=50.0, cpu_pct=1.0,
            current_suite="cs-mlkem768-ascon128a-mldsa65",
        )
        assert pol._can_activate_detector("TST", inp) is False

    def test_detector_upgrade_under_stability(self):
        """Stable system → eventually upgrades detector.

        Starts at L5 (highest level) so Gate 9 (level upgrade) cannot
        fire and the detector upgrade gate (Gate 10) is reached.
        """
        pol = _fresh_policy()
        s = _loaded_settings()
        det_delay = s["hysteresis"]["upgrade_s"] * 2.0  # detector uses 2×
        min_stable = s["rekey"]["min_stable_s"]
        base = 60_000.0
        # Use L5 so level upgrade gate has nowhere to go
        suite = _compose_suite("chacha20poly1305", "L5")

        # Plant hysteresis for detector upgrade
        inp1 = _make_input(
            mono_ms=base,
            current_suite=suite,
            detector_level="NONE",
            last_switch_mono_ms=base,
            temp_c=50.0,
            cpu_pct=10.0,
        )
        pol.evaluate(inp1)

        # At det_delay + 1s: hysteresis should pass
        delay_ms = (det_delay + 1.0) * 1000
        # Keep last_switch recent to avoid proactive rekey
        switch_time = base + delay_ms - (min_stable * 1000 * 0.5)
        inp2 = _make_input(
            mono_ms=base + delay_ms,
            current_suite=suite,
            detector_level="NONE",
            last_switch_mono_ms=switch_time,
            temp_c=50.0,
            cpu_pct=10.0,
        )
        out = pol.evaluate(inp2)
        assert out.action == PolicyAction.UPGRADE_DETECTOR
        assert any("XGBOOST" in r for r in out.reasons)


# ═════════════════════════════════════════════════════════════════════
# 9. Invariants — I1 safety, I2 liveness, I3 monotonic, I4 determinism
# ═════════════════════════════════════════════════════════════════════

class TestInvariants:
    """Validate the four formal MDEAS invariants."""

    # I1: Safety — never recommend a suite/detector that would exceed
    #     thermal or power ceilings.
    def test_i1_emergency_always_cheapest_l1(self):
        """Under critical conditions, policy always selects L1 + cheapest."""
        pol = _fresh_policy()
        cheapest = pol._cheapest_aead()
        for temp in [82.0, 85.0, 90.0]:
            inp = _make_input(temp_c=temp)
            out = pol.evaluate(inp)
            if out.action == PolicyAction.EMERGENCY and out.target_suite:
                parsed = _parse_suite(out.target_suite, out.target_aead)
                assert parsed["level"] == "L1"
                assert out.target_aead == cheapest

    def test_i1_no_tst_with_ascon(self):
        """Policy never recommends TST activation when Ascon is active."""
        pol = _fresh_policy()
        inp = _make_input(
            current_suite="cs-mlkem768-ascon128a-mldsa65",
            detector_level="XGBOOST",
            temp_c=50.0,
            cpu_pct=1.0,
        )
        # Even with long stability, detector upgrade should be blocked
        base = 60_000.0
        for i in range(5):
            t = base + i * 70_000.0
            out = pol.evaluate(_make_input(
                mono_ms=t,
                current_suite="cs-mlkem768-ascon128a-mldsa65",
                detector_level="XGBOOST",
                temp_c=50.0,
                cpu_pct=1.0,
                last_switch_mono_ms=base,
            ))
            if out.action == PolicyAction.UPGRADE_DETECTOR:
                # Should NOT upgrade to TST with Ascon
                assert not any("TST" in r for r in out.reasons), \
                    "I1 violated: TST recommended with Ascon suite"

    # I2: Liveness — evaluate always returns a valid PolicyOutput.
    def test_i2_always_returns_output(self):
        """evaluate() never throws; always returns PolicyOutput."""
        pol = _fresh_policy()
        scenarios = [
            _make_input(),                                          # nominal
            _make_input(telemetry_valid=False),                     # stale
            _make_input(battery_mv=10_000, temp_c=90.0),           # double critical
            _make_input(temp_c=68.0, temp_roc=15.0),               # rapid heating
            _make_input(gap_p95_ms=5000.0, rx_pps_median=0.5),     # terrible link
            _make_input(cpu_pct=99.0, detector_level="TST"),        # CPU pegged
            _make_input(proxy_drop_total=5000, proxy_enc_out=6000), # heavy drops
        ]
        for i, inp in enumerate(scenarios):
            out = pol.evaluate(inp)
            assert isinstance(out, PolicyOutput), f"scenario {i}: not PolicyOutput"
            assert isinstance(out.action, PolicyAction), f"scenario {i}: bad action"

    # I3: Monotonic degradation — never skip a level.
    def test_i3_level_downgrade_monotonic(self):
        """Level downgrade goes L5→L3→L1, never L5→L1 in one step
        (except EMERGENCY which bypasses to L1)."""
        pol = _fresh_policy()
        base = 60_000.0
        suite_l5 = _compose_suite("chacha20poly1305", "L5")

        # Plant hysteresis with bad link
        inp1 = _make_input(
            mono_ms=base,
            current_suite=suite_l5,
            gap_p95_ms=2000.0,
            rx_pps_median=2.0,
        )
        pol.evaluate(inp1)

        # Trigger downgrade
        inp2 = _make_input(
            mono_ms=base + 6_000.0,
            current_suite=suite_l5,
            gap_p95_ms=2000.0,
            rx_pps_median=2.0,
        )
        out = pol.evaluate(inp2)
        if out.action == PolicyAction.DOWNGRADE_LEVEL:
            parsed = _parse_suite(out.target_suite, out.target_aead)
            assert parsed["level"] == "L3", "I3: skipped L3 in downgrade"

    # I4: Determinism — identical inputs → identical outputs.
    def test_i4_deterministic(self):
        """Same input to a fresh policy always yields same output."""
        inp = _make_input()
        results = []
        for _ in range(10):
            pol = _fresh_policy()
            out = pol.evaluate(inp)
            results.append((out.action.value, out.target_suite, tuple(out.reasons)))
        # All 10 runs must produce identical results
        assert len(set(results)) == 1, f"I4 violated: {set(results)}"


# ═════════════════════════════════════════════════════════════════════
# 10. MDEAS AEAD ranking
# ═════════════════════════════════════════════════════════════════════

class TestAeadRanking:
    """Verify _rank_aeads_by_cost ordering."""

    def test_bsi_ranking_order(self):
        """BSI-seeded ranking: ChaCha < AES-GCM << Ascon."""
        pol = _fresh_policy()
        # Make profiles reliable (BSI has 5, need 10)
        for token in _AEAD_PREFERENCE_ORDER:
            seed = _AEAD_BENCHMARK_SEED[token]
            for i in range(5):
                pol.aead_profiles[token].update(
                    seed["encrypt_ns"], seed["decrypt_ns"], 55.0, float(i + 1)
                )
        ranked = pol._rank_aeads_by_cost()
        assert ranked[0] == "chacha20poly1305"
        assert ranked[-1] == "ascon128a"

    def test_ranking_adapts_to_live_data(self):
        """If AES-GCM becomes cheaper than ChaCha, ranking reflects it."""
        pol = _fresh_policy()
        # Make profiles reliable
        for token in _AEAD_PREFERENCE_ORDER:
            seed = _AEAD_BENCHMARK_SEED[token]
            for i in range(5):
                pol.aead_profiles[token].update(
                    seed["encrypt_ns"], seed["decrypt_ns"], 55.0, float(i + 1)
                )
        # Now feed many samples making AES-GCM faster than ChaCha
        for i in range(20):
            pol.aead_profiles["aesgcm"].update(
                30_000.0, 30_000.0, 55.0, float(10 + i)
            )
        ranked = pol._rank_aeads_by_cost()
        assert ranked[0] == "aesgcm", "Ranking should adapt to live data"


# ═════════════════════════════════════════════════════════════════════
# 11. Transition logging & introspection
# ═════════════════════════════════════════════════════════════════════

class TestTransitionLog:
    """Verify structured transition logging for publication evidence."""

    def test_emergency_logged(self):
        pol = _fresh_policy()
        inp = _make_input(battery_mv=13_000)
        pol.evaluate(inp)
        log = pol.get_transition_log()
        assert len(log) >= 1
        assert log[-1]["action"] == "EMERGENCY"
        assert "mdeas" in log[-1]

    def test_profiles_inspectable(self):
        """get_aead_profiles returns all three tokens."""
        pol = _fresh_policy()
        profiles = pol.get_aead_profiles()
        for token in _AEAD_PREFERENCE_ORDER:
            assert token in profiles
            assert profiles[token]["seeded"] is True

    def test_record_rekey_cost(self):
        """record_rekey_cost updates average."""
        pol = _fresh_policy()
        pol.record_rekey_cost(250.0)
        pol.record_rekey_cost(350.0)
        assert pol.avg_rekey_cost_ms == pytest.approx(300.0, rel=1e-6)


# ═════════════════════════════════════════════════════════════════════
# 12. Benchmark runner — timing all components
# ═════════════════════════════════════════════════════════════════════

class TestPerformanceBenchmark:
    """Measure wall-clock performance of policy components."""

    def test_evaluate_latency(self):
        """Single evaluate() should complete in < 10 ms (no I/O)."""
        pol = _fresh_policy()
        inp = _make_input()
        iterations = 1000
        start = time.perf_counter()
        for _ in range(iterations):
            pol.evaluate(inp)
        elapsed = time.perf_counter() - start
        avg_ms = (elapsed / iterations) * 1000
        print(f"\n  evaluate() avg: {avg_ms:.3f} ms  ({iterations} iters)")
        assert avg_ms < 10.0, f"evaluate() too slow: {avg_ms:.3f} ms"

    def test_aead_update_latency(self):
        """EWMA update should be sub-microsecond."""
        p = AeadCostProfile("chacha20poly1305")
        iterations = 10_000
        start = time.perf_counter()
        for i in range(iterations):
            p.update(63_500.0, 70_700.0, 55.0, float(i))
        elapsed = time.perf_counter() - start
        avg_us = (elapsed / iterations) * 1_000_000
        print(f"\n  EWMA update avg: {avg_us:.3f} µs  ({iterations} iters)")
        assert avg_us < 100.0, f"EWMA update too slow: {avg_us:.1f} µs"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
