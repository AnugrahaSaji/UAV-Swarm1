"""
Scheduling policies for drone-side suite management.

Implements a deterministic, safety-critical state machine for PQC suite selection.
Consumes GCS telemetry (link) and Local telemetry (battery/thermal).
"""

import json
import time
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from core.suites import (
    approved_aead_profiles_by_nist_level,
    benchmark_aead_tokens,
    build_suite_id,
    get_suite,
    list_benchmark_suites,
    list_runtime_suites,
    list_scheduler_approved_suites,
    normalize_aead_token,
    runtime_aead_tokens,
)

# =============================================================================
# SUITE TIER MAPPING
# =============================================================================

# Tier 0 = lightest/fastest, higher = heavier/slower
# NIST L1 < L3 < L5; within level: mlkem < hqc < classicmceliece (ARM performance)
def get_suite_tier(suite_name: str) -> int:
    """Map suite name to numeric tier for upgrade/downgrade decisions."""
    # Suite format: cs-{kem}-{sig} (AEAD is runtime config, not in suite ID)
    # Level hints: mlkem512/hqc128/mceliece348864 = L1
    #              mlkem768/hqc192/mceliece460896 = L3
    #              mlkem1024/hqc256/mceliece8192128 = L5
    name_lower = suite_name.lower()

    # NIST level base tier — read from registry to avoid substring false-positives.
    level_tier = 0
    try:
        from core.suites import get_suite
        nl = get_suite(suite_name).get("nist_level", "L1")
    except Exception:
        nl = "L1"  # Unknown suite: treat as lightest to fail safe
    if nl == "L3":
        level_tier = 10
    elif nl == "L5":
        level_tier = 20

    # KEM complexity sub-tier
    kem_tier = 0
    if "mlkem" in name_lower:
        kem_tier = 0
    elif "hqc" in name_lower:
        kem_tier = 3
    elif "frodokem" in name_lower:
        kem_tier = 4
    elif "classicmceliece" in name_lower or "mceliece" in name_lower:
        kem_tier = 5
    elif "sntrup" in name_lower:
        kem_tier = 2

    return level_tier + kem_tier

# =============================================================================
# CONFIGURATION LOADING
# =============================================================================

SETTINGS_PATH = Path(__file__).parent.parent / "settings.json"

def load_settings() -> Dict[str, Any]:
    defaults = {
        "mission_criticality": "medium",
        "max_nist_level": "L5",
        "allowed_aead": "aesgcm",
        "battery": {"critical_mv": 14000, "low_mv": 14800, "warn_mv": 15200, "rate_warn_mv_per_min": 500},
        "thermal": {"critical_c": 80.0, "warn_c": 70.0, "rate_warn_c_per_min": 5.0},
        "link": {"min_pps": 5.0, "max_gap_ms": 1000.0, "max_blackout_count": 3},
        # Rekey window and limits: default to short 5-minute window in dev
        # `window_s` defines the sliding window (seconds) for counting recent
        # successful rekeys. `max_per_window` is the allowed number of
        # successful rekeys within that window.
        "rekey": {
            "min_stable_s": 60.0,
            "max_per_window": 5,
            "window_s": 300,
            "blacklist_ttl_s": 1800,
            # Deterministic transition budgets (per sliding window_s).
            "same_suite_max": 5,
            "different_suite_max": 5,
            "different_level_max": 1,
            # Disabled by default in the core-hardening phase so runtime and
            # benchmark policies keep AEAD fixed unless explicitly configured.
            "aead_shift_interval_s": 0.0,
        },
        "hysteresis": {"downgrade_s": 5.0, "upgrade_s": 30.0, "aead_recovery_s": 10.0},
        "initial_level": "L3",  # Starting security level (L1/L3/L5)
        "preferred_aead": "chacha20poly1305",  # Benchmark-policy nominal AEAD
    }
    try:
        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH, "r") as f:
                user_cfg = json.load(f)
                # Deep merge simple dicts
                for k, v in user_cfg.items():
                    if isinstance(v, dict) and k in defaults:
                        defaults[k].update(v)
                    else:
                        defaults[k] = v
    except Exception as e:
        logging.error(f"Failed to load settings.json: {e}")
    return defaults

SETTINGS = load_settings()

# =============================================================================
# ACTION ENUM
# =============================================================================

class PolicyAction(str, Enum):
    HOLD = "HOLD"
    DOWNGRADE = "DOWNGRADE"
    UPGRADE = "UPGRADE"
    REKEY = "REKEY"
    ROLLBACK = "ROLLBACK"
    # Two-axis actions (EnergyAwarePolicy)
    SWITCH_AEAD = "SWITCH_AEAD"            # Same security level, different AEAD
    UPGRADE_LEVEL = "UPGRADE_LEVEL"        # Same AEAD, higher KEM/SIG level
    DOWNGRADE_LEVEL = "DOWNGRADE_LEVEL"    # Same AEAD, lower KEM/SIG level
    EMERGENCY = "EMERGENCY"                # Force L1 + AES-GCM immediately
    # Axis 3 actions (Detector management)
    DOWNGRADE_DETECTOR = "DOWNGRADE_DETECTOR"  # TST→XGBoost or XGBoost→None
    UPGRADE_DETECTOR = "UPGRADE_DETECTOR"      # None→XGBoost or XGBoost→TST


class DetectorLevel(str, Enum):
    """DDoS detection level (Axis 3).

    Ordered by computational cost: NONE < XGBOOST < TST.
    Overhead values derived from three-phase benchmarks
    (Table: detector-overhead in the paper).
    """
    NONE = "NONE"
    XGBOOST = "XGBOOST"
    TST = "TST"


_DETECTOR_ORDER: list = [DetectorLevel.NONE, DetectorLevel.XGBOOST, DetectorLevel.TST]

# =============================================================================
# DECISION CONTEXT INPUT (immutable snapshot)
# =============================================================================

@dataclass(frozen=True)
class DecisionInput:
    """Immutable snapshot of system state for policy evaluation."""
    mono_ms: float
    
    # Link Telemetry (GCS -> Drone)
    telemetry_valid: bool
    telemetry_age_ms: float
    sample_count: int
    rx_pps_median: float
    gap_p95_ms: float
    silence_max_ms: float
    jitter_ms: float
    blackout_count: int
    
    # Local Telemetry (Drone Sensors)
    battery_mv: int
    battery_roc: float
    temp_c: float
    temp_roc: float
    armed: bool
    
    # State
    current_suite: str
    local_epoch: int
    last_switch_mono_ms: float
    cooldown_until_mono_ms: float
    current_aead: str = "aesgcm"
    
    # Proxy Performance (from drone_status.json)
    aead_encrypt_avg_ns: float = 0.0   # Per-packet encrypt cost (nanoseconds)
    aead_decrypt_avg_ns: float = 0.0   # Per-packet decrypt cost (nanoseconds)
    proxy_enc_in: int = 0              # Total encrypted packets received
    proxy_enc_out: int = 0             # Total encrypted packets sent
    proxy_drop_total: int = 0          # Total drops across all reasons
    proxy_uptime_s: float = 0.0        # Seconds since last suite switch
    
    # System (Drone)
    cpu_pct: float = 0.0               # Drone CPU utilisation
    
    # Chronos Sync
    synced_time: float = 0.0

    # Axis 3: Detector state (from DetectorManager)
    detector_level: str = "NONE"       # Current DetectorLevel value
    detector_active: bool = False      # True if detector subprocess running
    detector_warmup: bool = False      # True if detector still warming up


# =============================================================================
# POLICY OUTPUT
# =============================================================================

@dataclass
class PolicyOutput:
    """Deterministic policy decision."""
    action: PolicyAction
    target_suite: Optional[str] = None
    target_aead: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    confidence: float = 0.0
    cooldown_remaining_ms: float = 0.0

# =============================================================================
# TELEMETRY-AWARE POLICY V2 (Robust)
# =============================================================================

class TelemetryAwarePolicyV2:
    def __init__(self):
        # BUG-8 fix: call load_settings() directly instead of using the module-level
        # SETTINGS singleton frozen at import time.  Operators can now call
        # reload_settings() to pick up changes to settings.json mid-flight without
        # restarting the scheduler process.
        self.settings = load_settings()
        self.all_suites = list_runtime_suites()
        self.runtime_aeads = runtime_aead_tokens()
        self.filtered_suites = self._filter_suites()
        
        # State
        self.blacklist: Dict[str, float] = {} # suite -> expiry_mono
        self.rekey_timestamps: List[float] = [] # mono timestamps
        self.hysteresis_start: Dict[str, float] = {} # condition -> start_mono
        self.previous_suite: Optional[str] = None
        
        logging.info(f"Policy initialized with {len(self.filtered_suites)} suites (AEAD={self.settings['allowed_aead']})")

    def reload_settings(self) -> None:
        """Re-read settings.json and re-compute the filtered suite list.

        Call this from the scheduler loop whenever an operator modifies
        settings.json mid-flight (e.g. adjusting emergency battery threshold).
        Thread-safety: caller is responsible for serialisation if evaluate()
        runs concurrently.
        """
        self.settings = load_settings()
        self.runtime_aeads = runtime_aead_tokens()
        self.filtered_suites = self._filter_suites()
        logging.info(
            f"Policy settings reloaded: {len(self.filtered_suites)} suites "
            f"(AEAD={self.settings['allowed_aead']})"
        )

    def _filter_suites(self) -> List[str]:
        """Filter suites based on settings (NIST level).  AEAD is runtime config."""
        max_nist = self.settings.get("max_nist_level", "L5")

        # Map L1/L3/L5 to comparable ints
        levels = {"L1": 1, "L3": 3, "L5": 5}
        max_level_int = levels.get(max_nist, 5)

        candidates = []
        for sid, cfg in self.all_suites.items():
            if not bool(cfg.get("runtime_allowed", False)):
                continue
            # NIST Level Filter only — AEAD is selected at runtime, all suites support all AEADs
            lvl = cfg.get("nist_level", "L5")
            if levels.get(lvl, 5) > max_level_int:
                continue
            candidates.append(sid)

        # Sort by tier (complexity)
        candidates.sort(key=get_suite_tier)
        return candidates

    def _select_target_aead(self, current_aead: str) -> str:
        """Return a runtime-eligible AEAD token for this policy cycle."""

        allowed = set(self.runtime_aeads or ("aesgcm",))
        current = str(current_aead or "").strip().lower()
        preferred = str(self.settings.get("allowed_aead", "aesgcm")).strip().lower()
        if current in allowed:
            return current
        if preferred in allowed:
            return preferred
        return "aesgcm"

    def _is_blacklisted(self, suite: str, now_mono: float) -> bool:
        if suite in self.blacklist:
            if now_mono < self.blacklist[suite]:
                return True
            del self.blacklist[suite]
        return False

    def _add_blacklist(self, suite: str, now_mono: float):
        ttl = self.settings["rekey"]["blacklist_ttl_s"]
        self.blacklist[suite] = now_mono + ttl
        logging.warning(f"Blacklisted {suite} for {ttl}s")

    def _check_hysteresis(self, condition_key: str, active: bool, now_mono: float, duration_s: float) -> bool:
        """Return True if condition has been active for duration_s."""
        if not active:
            self.hysteresis_start.pop(condition_key, None)
            return False
        
        start = self.hysteresis_start.get(condition_key)
        if start is None:
            self.hysteresis_start[condition_key] = now_mono
            return False
        
        return (now_mono - start) >= duration_s

    def _find_suite(self, current: str, direction: int, now_mono: float) -> Optional[str]:
        """Find adjacent suite in filtered pool, skipping blacklisted."""
        if current not in self.filtered_suites:
            # If current not in pool (e.g. config changed), pick closest valid
            if not self.filtered_suites: return None
            return self.filtered_suites[0] # Fallback to lowest
            
        idx = self.filtered_suites.index(current)
        new_idx = idx + direction
        
        # Bounds check
        if new_idx < 0 or new_idx >= len(self.filtered_suites):
            return None
            
        candidate = self.filtered_suites[new_idx]
        if self._is_blacklisted(candidate, now_mono):
            # Try skipping one more? No, simple adjacent for now to avoid jumps
            return None
            
        return candidate

    def evaluate(self, inp: DecisionInput) -> PolicyOutput:
        now_mono = inp.mono_ms / 1000.0
        reasons = []
        
        # 0. Update previous suite tracking
        if self.previous_suite != inp.current_suite:
            # If we just switched, keep track (unless it was a rekey of same)
            pass 
            
        # 1. Safety Gates (Immediate HOLD)
        if not inp.telemetry_valid or inp.telemetry_age_ms > 2000:
            return PolicyOutput(PolicyAction.HOLD, reasons=["telemetry_stale"])
            
        # 2. Emergency Safety (Battery/Temp) -> FAST DOWNGRADE
        batt_crit = inp.battery_mv < self.settings["battery"]["critical_mv"]
        temp_crit = inp.temp_c > self.settings["thermal"]["critical_c"]
        
        if self.filtered_suites and (batt_crit or temp_crit) and inp.current_suite != self.filtered_suites[0]:
            # Emergency: jump to lowest tier immediately
            target = self.filtered_suites[0]
            return PolicyOutput(
                PolicyAction.DOWNGRADE,
                target,
                target_aead=self._select_target_aead(inp.current_aead),
                reasons=["safety_critical"],
            )

        # 3. Link Failure -> ROLLBACK/BLACKLIST
        # If blackout persists shortly after a switch, assume suite fault
        time_since_switch = (inp.mono_ms - inp.last_switch_mono_ms) / 1000.0
        if time_since_switch < 30.0 and inp.blackout_count > self.settings["link"]["max_blackout_count"]:
            self._add_blacklist(inp.current_suite, now_mono)
            # Try to go back to previous or downgrade
            target = self._find_suite(inp.current_suite, -1, now_mono)
            if target:
                return PolicyOutput(
                    PolicyAction.DOWNGRADE,
                    target,
                    target_aead=self._select_target_aead(inp.current_aead),
                    reasons=["blackout_rollback"],
                )

        # 4. Cooldown Gate
        if inp.cooldown_until_mono_ms > inp.mono_ms:
            return PolicyOutput(PolicyAction.HOLD, reasons=["cooldown"])

        # 5. Link Degradation -> DOWNGRADE (with Hysteresis)
        link_bad = (
            inp.gap_p95_ms > self.settings["link"]["max_gap_ms"] or
            inp.rx_pps_median < self.settings["link"]["min_pps"]
        )
        
        if self._check_hysteresis("link_bad", link_bad, now_mono, self.settings["hysteresis"]["downgrade_s"]):
            target = self._find_suite(inp.current_suite, -1, now_mono)
            if target:
                return PolicyOutput(
                    PolicyAction.DOWNGRADE,
                    target,
                    target_aead=self._select_target_aead(inp.current_aead),
                    reasons=["link_degraded_persistent"],
                )

        # 6. Thermal/Battery Warning -> DOWNGRADE (with Hysteresis)
        # Check rates
        temp_rising = inp.temp_roc > self.settings["thermal"]["rate_warn_c_per_min"]
        batt_falling = inp.battery_roc < -self.settings["battery"]["rate_warn_mv_per_min"] # negative slope
        
        stress = temp_rising or batt_falling or (inp.temp_c > self.settings["thermal"]["warn_c"])
        
        if self._check_hysteresis("stress", stress, now_mono, self.settings["hysteresis"]["downgrade_s"]):
             target = self._find_suite(inp.current_suite, -1, now_mono)
             if target:
                 return PolicyOutput(
                     PolicyAction.DOWNGRADE,
                     target,
                     target_aead=self._select_target_aead(inp.current_aead),
                     reasons=["thermal_battery_stress"],
                 )

        # 7. Proactive Rekey / Upgrade
        # Only if stable for long time
        stable_time = (inp.mono_ms - inp.last_switch_mono_ms) / 1000.0
        if stable_time > self.settings["rekey"]["min_stable_s"]:
            # Check rekey limit (do NOT record the rekey here; record only after
            # successful execution to avoid counting failed attempts)
            window_s = float(self.settings["rekey"].get("window_s", 300))
            window_ago = now_mono - window_s
            self.rekey_timestamps = [t for t in self.rekey_timestamps if t > window_ago]

            max_per = int(self.settings["rekey"].get("max_per_window", 5))
            if len(self.rekey_timestamps) < max_per:
                # Request a rekey; actual recording happens after success
                return PolicyOutput(
                    PolicyAction.REKEY,
                    inp.current_suite,
                    target_aead=self._select_target_aead(inp.current_aead),
                    reasons=["proactive_rekey"],
                )
                
        # 8. Upgrade (Very Conservative)
        # Only if disarmed, very stable, and no stress
        if not inp.armed and not stress and not link_bad:
             if self._check_hysteresis("upgrade_ok", True, now_mono, self.settings["hysteresis"]["upgrade_s"]):
                 target = self._find_suite(inp.current_suite, 1, now_mono)
                 if target:
                     return PolicyOutput(
                         PolicyAction.UPGRADE,
                         target,
                         target_aead=self._select_target_aead(inp.current_aead),
                         reasons=["stable_upgrade"],
                     )

        return PolicyOutput(PolicyAction.HOLD, reasons=["nominal"])

    def record_rekey(self, now_mono: float) -> None:
        """Record a successful rekey timestamp (mono seconds).

        This should be called by the executor after the rekey completed
        successfully to enforce the per-hour limit.
        """
        self.rekey_timestamps.append(now_mono)


# =============================================================================
# SIMPLE POLICIES USED BY MAV SCHEDULER
# =============================================================================

class LinearLoopPolicy:
    """Deterministic round-robin suite policy."""

    def __init__(self, suites: List[str], duration_s: float = 10.0):
        self.suites = list(suites)
        self._idx = 0
        self._duration_s = float(duration_s)

    def next_suite(self) -> str:
        if not self.suites:
            raise RuntimeError("No suites configured")
        suite = self.suites[self._idx % len(self.suites)]
        self._idx += 1
        return suite

    def get_duration(self) -> float:
        return self._duration_s


class RandomPolicy:
    """Random suite selection policy."""

    def __init__(self, suites: List[str], duration_s: float = 10.0):
        import random
        self._rng = random.Random()
        self.suites = list(suites)
        self._duration_s = float(duration_s)

    def next_suite(self) -> str:
        if not self.suites:
            raise RuntimeError("No suites configured")
        return self._rng.choice(self.suites)

    def get_duration(self) -> float:
        return self._duration_s


class ManualOverridePolicy:
    """Manual suite override with fallback to linear loop."""

    def __init__(self, suites: List[str], duration_s: float = 10.0):
        self.suites = list(suites)
        self._duration_s = float(duration_s)
        self._override: Optional[str] = None
        self._idx = 0

    def set_override(self, suite_name: Optional[str]) -> None:
        if suite_name is None:
            self._override = None
            return
        if suite_name not in self.suites:
            raise ValueError("Unknown suite override")
        self._override = suite_name

    def next_suite(self) -> str:
        if not self.suites:
            raise RuntimeError("No suites configured")
        if self._override:
            return self._override
        suite = self.suites[self._idx % len(self.suites)]
        self._idx += 1
        return suite

    def get_duration(self) -> float:
        return self._duration_s


# =============================================================================
# ENERGY-AWARE POLICY (Novel Two-Axis AEAD-Aware Scheduler)
# =============================================================================

# AEAD tokens ordered by *measured* ARM efficiency (RPi4 without AES-NI).
# ChaCha20 is fastest, AES-GCM close second, standardized Ascon is software-only.
# Used ONLY as a fallback when no measurements are available yet.
_AEAD_PREFERENCE_ORDER = ["chacha20poly1305", "aesgcm", "ascon128"]

# Benchmark-seeded AEAD cost profiles (from individual_benchmarks + suite data).
# These eliminate the cold-start problem — EWMA refines from this baseline.
# Source: individual_benchmarks/raw_data/5iter_test + live suite runs 2026-02-19.
_AEAD_BENCHMARK_SEED: Dict[str, Dict[str, float]] = {
    "chacha20poly1305": {
        "encrypt_ns": 63500.0,   # Measured: 63.5 µs avg in actual tunnel
        "decrypt_ns": 70700.0,   # Measured: 70.7 µs avg in actual tunnel
        "power_w":    3.559,     # Measured: 3.559 W from INA219
        "temp_delta_c": 0.0,     # Reference (lowest temp of the three)
    },
    "aesgcm": {
        "encrypt_ns": 66900.0,   # Measured: 66.9 µs avg (5% slower than ChaCha20)
        "decrypt_ns": 73600.0,   # Measured: 73.6 µs avg
        "power_w":    3.595,     # Measured from INA219
        "temp_delta_c": -0.1,    # 61.6°C vs 61.7°C — essentially same
    },
    "ascon128": {
        "encrypt_ns": 1327100.0, # Measured class: software-only Ascon on ARM
        "decrypt_ns": 960500.0,
        "power_w":    3.558,
        "temp_delta_c": 1.5,
    },
}

# KEM/SIG pairings per NIST level (lightest → heaviest)
_LEVEL_MAP = {
    "L1": {"kem": "mlkem512",  "sig": "mldsa44"},
    "L3": {"kem": "mlkem768",  "sig": "mldsa65"},
    "L5": {"kem": "mlkem1024", "sig": "mldsa87"},
}
_LEVEL_ORDER = ["L1", "L3", "L5"]


def _level_suite_id(level: str) -> str:
    """Return the canonical representative suite for a given NIST level."""
    cfg = _LEVEL_MAP.get(level, _LEVEL_MAP["L1"])
    return build_suite_id(str(cfg["kem"]), str(cfg["sig"]))


# ─────────────────────────────────────────────────────────────────────
# AEAD Cost Profile — per-algorithm runtime observation store
# ─────────────────────────────────────────────────────────────────────

class AeadCostProfile:
    """Runtime cost profile for a single AEAD algorithm, learned from live
    proxy counter observations via EWMA (Exponentially Weighted Moving Average).

    The profile tracks encrypt/decrypt nanosecond costs and the environmental
    conditions under which they were measured, enabling platform-adaptive
    AEAD ranking without hardcoded assumptions.

    **Novel: Benchmark-seeded initialisation (BSI)**
    When benchmark data is available (_AEAD_BENCHMARK_SEED), the profile is
    pre-populated with empirical measurements.  EWMA then refines from this
    baseline, eliminating the cold-start problem.  The ``seeded`` flag tracks
    whether the profile was initialised from benchmarks (for publication
    evidence).
    """

    __slots__ = (
        "token", "encrypt_ns", "decrypt_ns", "total_ns",
        "samples", "last_update_mono", "temp_at_measurement",
        "power_w_baseline", "temp_delta_c", "seeded",
        "energy_per_bit_nj",
    )

    def __init__(self, token: str) -> None:
        self.token: str = token
        self.encrypt_ns: float = 0.0
        self.decrypt_ns: float = 0.0
        self.total_ns: float = 0.0
        self.samples: int = 0
        self.last_update_mono: float = 0.0
        self.temp_at_measurement: float = 0.0
        self.power_w_baseline: float = 0.0
        self.temp_delta_c: float = 0.0
        self.seeded: bool = False
        self.energy_per_bit_nj: float = 0.0  # nJ per bit of plaintext

        # Auto-seed from benchmark data if available
        seed = _AEAD_BENCHMARK_SEED.get(token)
        if seed:
            self.encrypt_ns = seed["encrypt_ns"]
            self.decrypt_ns = seed["decrypt_ns"]
            self.total_ns = self.encrypt_ns + self.decrypt_ns
            self.power_w_baseline = seed.get("power_w", 0.0)
            self.temp_delta_c = seed.get("temp_delta_c", 0.0)
            # Seed with 5 "virtual" samples so EWMA begins from benchmark baseline
            # but converges quickly to live data (within ~10 real observations)
            self.samples = 5
            self.seeded = True
            # Compute energy per bit for a typical 256-byte packet:
            # E = P × t;  energy_per_bit = E / (payload_bits)
            if self.power_w_baseline > 0:
                total_s = self.total_ns / 1e9
                energy_j = self.power_w_baseline * total_s
                self.energy_per_bit_nj = (energy_j * 1e9) / (256 * 8)

    def update(self, enc_ns: float, dec_ns: float,
               temp_c: float, mono_now: float) -> None:
        """Update cost profile using EWMA.

        Uses a higher learning rate (alpha=0.5) for the first 10 samples
        to converge quickly during warm-up, then settles to alpha=0.2 for
        steady-state tracking that smooths out measurement noise.
        """
        alpha = 0.5 if self.samples < 10 else 0.2
        if self.samples == 0:
            self.encrypt_ns = enc_ns
            self.decrypt_ns = dec_ns
        else:
            self.encrypt_ns = alpha * enc_ns + (1.0 - alpha) * self.encrypt_ns
            self.decrypt_ns = alpha * dec_ns + (1.0 - alpha) * self.decrypt_ns
        self.total_ns = self.encrypt_ns + self.decrypt_ns
        self.samples += 1
        self.last_update_mono = mono_now
        self.temp_at_measurement = temp_c

        # Update energy-per-bit estimate
        power = self.power_w_baseline if self.power_w_baseline > 0 else 3.5
        total_s = self.total_ns / 1e9
        energy_j = power * total_s
        self.energy_per_bit_nj = (energy_j * 1e9) / (256 * 8)

    def is_reliable(self, min_samples: int = 10) -> bool:
        """Return True if enough samples exist for confident decisions.

        Threshold lowered from 50 to 10 because benchmark seeding provides
        a reliable baseline.  10 live samples are sufficient to confirm or
        adjust the seeded values.
        """
        return self.samples >= min_samples

    def cost_ratio_vs(self, other: "AeadCostProfile") -> float:
        """Compute cost ratio: self.total_ns / other.total_ns."""
        if other.total_ns <= 0:
            return 1.0
        return self.total_ns / other.total_ns

    def to_dict(self) -> Dict[str, Any]:
        return {
            "token": self.token,
            "encrypt_ns": round(self.encrypt_ns, 1),
            "decrypt_ns": round(self.decrypt_ns, 1),
            "total_ns": round(self.total_ns, 1),
            "samples": self.samples,
            "temp_at_measurement": round(self.temp_at_measurement, 1),
            "seeded": self.seeded,
            "energy_per_bit_nj": round(self.energy_per_bit_nj, 3),
            "power_w_baseline": round(self.power_w_baseline, 3),
            "temp_delta_c": round(self.temp_delta_c, 1),
        }


def _parse_legacy_suite(suite_name: str) -> Optional[Dict[str, str]]:
    """Best-effort parser for legacy cs-{kem}-{aead}-{sig} identifiers."""
    parts = suite_name.split("-", 1)
    if len(parts) < 2:
        return None

    remainder = parts[1]
    known_tokens = list(
        dict.fromkeys(
            sorted(
                set(_AEAD_PREFERENCE_ORDER) | set(benchmark_aead_tokens(require_available=False)),
                key=len,
                reverse=True,
            )
        )
    )
    for aead in known_tokens:
        marker = f"-{aead}-"
        if marker not in remainder:
            continue
        idx = remainder.index(marker)
        kem_token = remainder[:idx]
        sig_token = remainder[idx + len(marker):]
        level = "L1"
        try:
            canonical = build_suite_id(kem_token, sig_token)
            level = str(get_suite(canonical).get("nist_level", "L1"))
        except Exception:
            if "768" in kem_token or "460896" in kem_token or kem_token.endswith("192"):
                level = "L3"
            elif "1024" in kem_token or "8192128" in kem_token or kem_token.endswith("256"):
                level = "L5"
        return {"kem": kem_token, "aead": aead, "sig": sig_token, "level": level}
    return None


def _parse_suite(suite_name: str, aead_token: Optional[str] = None) -> Dict[str, str]:
    """Parse scheduler suite metadata from canonical or legacy identifiers."""
    try:
        suite = get_suite(suite_name)
    except Exception:
        legacy = _parse_legacy_suite(suite_name)
        if legacy is not None:
            return legacy
        return {"kem": "", "aead": "", "sig": "", "level": "L1"}

    resolved_aead = str(suite.get("aead_token", "aesgcm"))
    if aead_token:
        try:
            resolved_aead = normalize_aead_token(aead_token)
        except ValueError:
            resolved_aead = str(aead_token).strip().lower()
    return {
        "kem": str(suite.get("kem_token", "")),
        "aead": resolved_aead,
        "sig": str(suite.get("sig_token", "")),
        "level": str(suite.get("nist_level", "L1")),
    }


def _compose_suite(aead: str, level: str) -> str:
    """Return the canonical representative suite ID for a NIST level.

    AEAD remains a separate runtime axis. The ``aead`` argument is retained as
    a compatibility parameter for existing callers/tests.
    """
    _ = aead
    return _level_suite_id(level)


def _build_energy_policy_suite_space() -> tuple[Set[str], Dict[str, Set[str]]]:
    """Build the runtime MDEAS inventory using canonical suite IDs plus AEAD axis."""

    approved_suite_catalog = list_scheduler_approved_suites()
    approved_aeads = approved_aead_profiles_by_nist_level(runtime_only=True)

    suite_ids: Set[str] = set()
    available_by_level: Dict[str, Set[str]] = {}
    for level in _LEVEL_ORDER:
        suite_id = _level_suite_id(level)
        if suite_id in approved_suite_catalog:
            suite_ids.add(suite_id)
        level_tokens = set(approved_aeads.get(level, ()))
        if not level_tokens:
            level_tokens = set(runtime_aead_tokens())
        available_by_level[level] = level_tokens

    return suite_ids, available_by_level


# =============================================================================
# AXIS 3: DETECTOR OVERHEAD & CROSS-AXIS CONSTRAINTS
# =============================================================================

@dataclass(frozen=True)
class DetectorOverhead:
    """Empirical overhead of a DDoS detector (from three-phase benchmarks)."""
    delta_power_w: float
    delta_temp_c: float
    delta_cpu_pp: int


_DETECTOR_OVERHEAD = {
    DetectorLevel.NONE:    DetectorOverhead(0.00, 0.0,  0),
    DetectorLevel.XGBOOST: DetectorOverhead(0.95, 4.8,  35),
    DetectorLevel.TST:     DetectorOverhead(1.97, 10.7, 91),
}

# Maximum baseline temperature for safe activation of each detector
# = 80°C (critical) − detector delta_temp_c
_DETECTOR_MAX_BASELINE_TEMP = {
    DetectorLevel.NONE:    80.0,
    DetectorLevel.XGBOOST: 75.0,   # 80 - 4.8 ≈ 75
    DetectorLevel.TST:     69.0,   # 80 - 10.7 ≈ 69
}

# Warmup durations (seconds) — must match detector_manager._WARMUP_S
_DETECTOR_WARMUP_S = {
    DetectorLevel.NONE:    0.0,
    DetectorLevel.XGBOOST: 10.0,
    DetectorLevel.TST:     5.0,
}

# Cross-axis constraint: AEADs forbidden with TST detector (standardized Ascon)
_FORBIDDEN_AEAD_WITH_TST: Set[str] = {"ascon128"}

# Cross-axis constraint: KEMs discouraged with TST (McEliece)
_DISCOURAGED_KEM_WITH_TST: Set[str] = {
    "classicmceliece348864", "classicmceliece460896", "classicmceliece8192128",
}

# Cross-axis constraint: KEM+SIG pairs that are forbidden at any detector level
# McEliece + SPHINCS+ produces handshake times > 2s at baseline
_FORBIDDEN_KEM_SIG_PAIRS: Set[tuple] = {
    ("classicmceliece348864", "sphincs128s"),
    ("classicmceliece460896", "sphincs192s"),
    ("classicmceliece8192128", "sphincs256s"),
    # Also cross-level pairs if they somehow exist
    ("classicmceliece348864", "sphincs192s"),
    ("classicmceliece348864", "sphincs256s"),
    ("classicmceliece460896", "sphincs128s"),
    ("classicmceliece460896", "sphincs256s"),
    ("classicmceliece8192128", "sphincs128s"),
    ("classicmceliece8192128", "sphincs192s"),
}


class EnergyAwarePolicy:
    """Measurement-Driven Energy-Aware Scheduling (MDEAS).

    Novel three-axis AEAD-aware adaptive policy that decomposes PQC suite
    selection into three independently-optimisable dimensions:

    **Axis 1 — AEAD Selection (data-plane, per-packet)**
      Driven by: *measured* aead_encrypt/decrypt_avg_ns, temp_c, temp_roc,
                 cpu_pct, battery_roc, current packet throughput
    Controls: which AEAD algorithm to use (aesgcm / chacha20 / ascon128)
      Rationale: AEAD accounts for ~99.5% of runtime crypto energy on ARM
                 because it runs on EVERY packet, while KEM/SIG only runs
                 once at handshake time.

    **Axis 2 — Security Level Selection (control-plane, per-handshake)**
      Driven by: armed state, link quality, mission criticality
      Controls: NIST level (L1/L3/L5) → KEM×SIG pairing
      Rationale: KEM/SIG only runs at handshake; level primarily affects
                 key sizes and handshake latency, not continuous cost.

    **Axis 3 — DDoS Detection Level (compute-plane)**
      Driven by: temperature, CPU headroom, battery state, armed state
      Controls: DDoS detector level (NONE / XGBOOST / TST)
      Rationale: Detector overhead is additive-constant (+0.86W XGBoost,
                 +1.65W TST). The scheduler manages this as a discrete
                 third axis with cross-axis constraints.

    **Key innovations over static/heuristic policies:**

    1. *Benchmark-Seeded Initialisation (BSI)* — AeadCostProfile objects
       are pre-populated from empirical INA219 power + timing benchmarks
       (individual_benchmarks + 72-suite live runs).  Eliminates cold-start
       entirely: the policy makes optimal AEAD decisions from cycle 0.
       EWMA refines these baselines with live observations.

    2. *Measurement-driven ranking* — Maintains per-AEAD cost profiles
       updated via EWMA from live proxy counters.  Platform-adaptive:
       if ChaCha20 is faster than AES-GCM on a particular ARM revision,
       the policy discovers and exploits this automatically.

    3. *Energy-per-bit metric* — Computes $E_{bit} = P \\cdot t / n_{bits}$
       normalised energy cost per bit of plaintext.  This enables
       payload-size-aware AEAD comparison (Ascon-128a is 20× worse
       than ChaCha20-Poly1305 on RPi4 ARM Cortex-A72).

    4. *Thermal-energy joint model* — Uses measured $\\Delta T_{AEAD}$
       (temperature differential per AEAD from benchmark data) in the
       thermal prediction.  Switches proactively based on *projected*
       thermal impact of the target AEAD, not just current temperature.

    5. *Break-even analysis* — Before any AEAD switch, computes
       break-even time amortised against remaining battery capacity.
       Only switches when benefit exceeds rekey cost.

    6. *DDoS-responsive AEAD lock* — Under detected DDoS, locks AEAD
       to cheapest measured algorithm.  Prevents adversary from
       triggering costly AEAD exploration through traffic manipulation.

    Decision Cascade
    ~~~~~~~~~~~~~~~~
    1. Telemetry stale       → HOLD
    2. DDoS detected         → EMERGENCY (cheapest AEAD, lock exploration)
    3. Battery critical      → EMERGENCY (L1 + cheapest measured AEAD)
    4. Temp critical         → EMERGENCY (L1 + cheapest measured AEAD)
    5. Predictive thermal    → SWITCH_AEAD (proactive, with ΔT model)
    6. Thermal/CPU stress    → SWITCH_AEAD (reactive, with break-even)
    7. Battery drain stress  → SWITCH_AEAD (with break-even check)
    8. Link degraded         → DOWNGRADE_LEVEL
    9. Cooldown active       → HOLD
    10. AEAD recovery        → SWITCH_AEAD (upgrade to preferred)
    11. Proactive rekey      → REKEY (same suite, rotate keys)
    12. Stable + safe        → UPGRADE_LEVEL (conservative)
    """

    # Default rekey cost estimate (ms) when no history is available.
    # Conservative: typical ML-KEM-768 + ML-DSA-65 handshake on RPi4.
    _DEFAULT_REKEY_COST_MS = 300.0

    # Minimum break-even seconds to justify an AEAD switch.
    # Prevents micro-switching that wastes more energy on rekeys
    # than it saves on AEAD cost reduction.
    _MIN_BREAK_EVEN_S = 30.0

    # Minimum stability seconds before considering AEAD recovery
    # (upgrade back to preferred AEAD after stress subsides).
    _MIN_RECOVERY_STABILITY_S = 60.0

    # Ascon-128a cost ratio threshold — if Ascon is more than this
    # factor slower than the cheapest AEAD, restrict it to PQ-only mode.
    _ASCON_COST_CEILING = 10.0

    def __init__(self):
        self.settings = load_settings()
        self.benchmark_suite_catalog = list_benchmark_suites()
        self.all_suites, self._available = _build_energy_policy_suite_space()
        self.scheduler_suite_catalog = list_scheduler_approved_suites()

        # ── Observation stores (MDEAS novel contribution) ────────────
        # Pre-populate per-AEAD cost profiles from benchmark seed data.
        # This is the BSI (Benchmark-Seeded Initialisation) mechanism.
        self.aead_profiles: Dict[str, AeadCostProfile] = {}
        for aead_token in _AEAD_PREFERENCE_ORDER:
            profile = AeadCostProfile(aead_token)
            self.aead_profiles[aead_token] = profile
            if profile.seeded:
                logging.info(
                    f"MDEAS BSI: {aead_token} seeded enc={profile.encrypt_ns:.0f}ns "
                    f"dec={profile.decrypt_ns:.0f}ns E/bit={profile.energy_per_bit_nj:.3f}nJ"
                )
        for level_tokens in self._available.values():
            for aead_token in sorted(level_tokens):
                self.aead_profiles.setdefault(aead_token, AeadCostProfile(aead_token))

        # Rekey cost history (handshake duration in ms), for break-even
        self.rekey_cost_history: List[float] = []
        self.avg_rekey_cost_ms: float = self._DEFAULT_REKEY_COST_MS

        # ── Standard state ───────────────────────────────────────────
        self.hysteresis_start: Dict[str, float] = {}
        self.rekey_timestamps: List[float] = []
        self.rekey_events: List[Dict[str, Any]] = []
        self.transition_log: List[Dict[str, Any]] = []

        # Previous packet throughput observation for delta computation
        self._prev_enc_out: int = 0
        self._prev_obs_mono: float = 0.0
        self._current_pkt_rate_hz: float = 0.0

        # DDoS detection state
        self._ddos_detected: bool = False
        self._ddos_start_mono: float = 0.0

        avail_summary = {lvl: sorted(aeads) for lvl, aeads in self._available.items()}
        logging.info(f"EnergyAwarePolicy (MDEAS): available={avail_summary}")

    def reload_settings(self) -> None:
        """Re-read settings.json (same interface as TelemetryAwarePolicyV2)."""
        self.settings = load_settings()
        logging.info("EnergyAwarePolicy: settings reloaded")

    # ------------------------------------------------------------------ #
    # MDEAS: Observation & measurement methods
    # ------------------------------------------------------------------ #

    def _update_observations(self, inp: DecisionInput) -> None:
        """Update AEAD cost profiles and packet-rate estimate from live data.

        Called at the beginning of every evaluate() cycle (~1 Hz).
        """
        now_mono = inp.mono_ms / 1000.0

        # ── Update packet rate estimate ──────────────────────────────
        if self._prev_obs_mono > 0.0 and inp.proxy_enc_out > self._prev_enc_out:
            dt = now_mono - self._prev_obs_mono
            if dt > 0.1:
                delta_pkts = inp.proxy_enc_out - self._prev_enc_out
                self._current_pkt_rate_hz = delta_pkts / dt
        elif self._current_pkt_rate_hz <= 0.0 and inp.proxy_uptime_s > 1.0:
            # Bootstrap: use cumulative rate from proxy lifetime
            self._current_pkt_rate_hz = inp.proxy_enc_out / inp.proxy_uptime_s
        self._prev_enc_out = inp.proxy_enc_out
        self._prev_obs_mono = now_mono

        # ── Update AEAD cost profile ─────────────────────────────────
        current = _parse_suite(inp.current_suite, inp.current_aead)
        aead = current.get("aead")
        if not aead:
            return

        enc_ns = inp.aead_encrypt_avg_ns
        dec_ns = inp.aead_decrypt_avg_ns
        if enc_ns <= 0.0 and dec_ns <= 0.0:
            return  # No valid measurement this cycle

        profile = self.aead_profiles.get(aead)
        if profile is None:
            profile = AeadCostProfile(aead)
            self.aead_profiles[aead] = profile
        profile.update(enc_ns, dec_ns, inp.temp_c, now_mono)

    def _rank_aeads_by_cost(self) -> List[str]:
        """Return AEAD tokens ordered by measured cost (cheapest first).

        Reliable profiles are sorted by observed total_ns. Unreliable/missing
        profiles are appended using deterministic fallback order:
        static preference first, then runtime-only tokens lexicographically.
        """
        # Keep deterministic traversal order for ties and unmeasured fallbacks.
        runtime_only = sorted(
            token for token in self.aead_profiles.keys()
            if token not in _AEAD_PREFERENCE_ORDER
        )
        ordered_tokens = list(_AEAD_PREFERENCE_ORDER) + runtime_only

        measured: List[tuple[str, float]] = []
        unmeasured: List[str] = []
        for token in ordered_tokens:
            profile = self.aead_profiles.get(token)
            if profile is not None and profile.is_reliable():
                measured.append((token, profile.total_ns))
            else:
                unmeasured.append(token)

        measured.sort(key=lambda item: item[1])  # cheapest first
        return [token for token, _ in measured] + unmeasured

    def _check_cross_axis_constraints(
        self,
        suite: str,
        target_detector: str,
        *,
        target_aead: Optional[str] = None,
    ) -> bool:
        """Return True if the suite × detector combination is allowed."""
        parsed = _parse_suite(suite, target_aead)
        aead = parsed.get("aead", "")
        kem = parsed.get("kem", "")
        sig = parsed.get("sig", "")

        if target_detector == DetectorLevel.TST.value:
            # Forbidden: Ascon + TST
            if aead in _FORBIDDEN_AEAD_WITH_TST:
                return False
            # Discouraged: McEliece + TST (treat as forbidden for safety)
            if kem in _DISCOURAGED_KEM_WITH_TST:
                return False

        # Forbidden: McEliece + SPHINCS+ (any detector level)
        if (kem, sig) in _FORBIDDEN_KEM_SIG_PAIRS:
            return False

        return True

    def _can_activate_detector(self, target_level: str,
                               inp: "DecisionInput") -> bool:
        """Check if activating/upgrading to target_level is safe."""
        try:
            det = DetectorLevel(target_level)
        except ValueError:
            return False

        # Temperature check: current temp must be below safe ceiling
        max_temp = _DETECTOR_MAX_BASELINE_TEMP.get(det, 80.0)
        if inp.temp_c > max_temp:
            return False

        # CPU headroom check: must have room for detector overhead
        overhead = _DETECTOR_OVERHEAD.get(det, DetectorOverhead(0, 0, 0))
        if inp.cpu_pct + overhead.delta_cpu_pp > 95.0:
            return False

        # Cross-axis: check current suite compatibility
        if not self._check_cross_axis_constraints(
            inp.current_suite,
            target_level,
            target_aead=inp.current_aead,
        ):
            return False

        return True

    def _safe_detector_level(self, raw_level: Any) -> DetectorLevel:
        """Parse detector level defensively; invalid values fail safe to NONE."""
        if isinstance(raw_level, DetectorLevel):
            return raw_level
        text = str(raw_level).strip().upper()
        try:
            return DetectorLevel(text)
        except ValueError:
            logging.warning(f"Invalid detector level '{raw_level}', defaulting to NONE")
            return DetectorLevel.NONE

    def _cheapest_aead(self) -> str:
        """Return the cheapest available AEAD by measurement, or static fallback."""
        ranked = self._rank_aeads_by_cost()
        return ranked[0] if ranked else "aesgcm"

    def _compute_break_even_s(self, cur_aead: str, tgt_aead: str,
                              pkt_rate_hz: float) -> float:
        """Compute the break-even time (seconds) for switching from
        cur_aead to tgt_aead, given the current packet throughput.

        break_even = rekey_cost / savings_per_second

        Where:
          rekey_cost    = handshake time + blackout cost (in equiv. savings units)
          savings/s     = (cur_cost - tgt_cost) per pkt × pkt/s

        Returns float('inf') if the target is actually more expensive,
        or if we lack sufficient measurement data for either AEAD.
        """
        cur_profile = self.aead_profiles.get(cur_aead)
        tgt_profile = self.aead_profiles.get(tgt_aead)

        # Insufficient data — cannot compute, return conservative estimate
        if not cur_profile or not cur_profile.is_reliable():
            static_cur = _AEAD_PREFERENCE_ORDER.index(cur_aead) if cur_aead in _AEAD_PREFERENCE_ORDER else 99
            static_tgt = _AEAD_PREFERENCE_ORDER.index(tgt_aead) if tgt_aead in _AEAD_PREFERENCE_ORDER else 99
            if static_tgt < static_cur:
                return self._MIN_BREAK_EVEN_S
            return float("inf")
        if not tgt_profile or not tgt_profile.is_reliable():
            # We haven't measured the target yet.  Allow the switch if
            # the static order suggests it's cheaper (exploration).
            static_cur = _AEAD_PREFERENCE_ORDER.index(cur_aead) if cur_aead in _AEAD_PREFERENCE_ORDER else 99
            static_tgt = _AEAD_PREFERENCE_ORDER.index(tgt_aead) if tgt_aead in _AEAD_PREFERENCE_ORDER else 99
            if static_tgt < static_cur:
                # Static order says target is cheaper — allow exploration
                return self._MIN_BREAK_EVEN_S
            return float("inf")

        # Per-packet saving (nanoseconds)
        saving_per_pkt_ns = cur_profile.total_ns - tgt_profile.total_ns
        if saving_per_pkt_ns <= 0.0:
            return float("inf")  # Target is same cost or worse

        # Effective packet rate (bidirectional: encrypt + decrypt)
        effective_rate = max(pkt_rate_hz, 1.0) * 2.0

        # Savings per second (nanoseconds)
        savings_per_s_ns = saving_per_pkt_ns * effective_rate

        # Rekey cost in nanoseconds
        rekey_cost_ns = self.avg_rekey_cost_ms * 1_000_000.0

        if savings_per_s_ns <= 0.0:
            return float("inf")
        return rekey_cost_ns / savings_per_s_ns

    def _predict_thermal_crossing_s(self, temp_c: float, temp_roc: float,
                                    threshold_c: float,
                                    target_aead: Optional[str] = None) -> Optional[float]:
        """Predict seconds until temperature crosses threshold.

        **Novel: thermal-energy joint model** — when ``target_aead`` is
        provided, adjusts the prediction using the measured temperature
        differential (``temp_delta_c``) for that AEAD.  This models the
        fact that switching to Ascon-128a adds ~1.5°C of steady-state
        temperature vs ChaCha20-Poly1305, which accelerates crossing.

        Returns None if:
          - Temperature is above threshold (already crossed)
          - Rate of change is ≤ 0 (cooling or stable)
          - Rate of change is too small to be meaningful (< 0.1 °C/min)

        Uses simple linear extrapolation: ΔT / rate = time.
        """
        effective_temp = temp_c
        # Apply thermal delta if switching to a different AEAD
        if target_aead is not None:
            profile = self.aead_profiles.get(target_aead)
            if profile and profile.temp_delta_c != 0.0:
                effective_temp += profile.temp_delta_c

        if effective_temp >= threshold_c:
            return 0.0  # Already crossed (or would cross with target AEAD)
        if temp_roc <= 0.1:
            return None  # Cooling or stable — no crossing predicted

        delta_c = threshold_c - effective_temp
        # temp_roc is in °C/min → convert to °C/s
        rate_per_s = temp_roc / 60.0
        if rate_per_s <= 0.0:
            return None
        return delta_c / rate_per_s

    def _detect_ddos(self, inp: DecisionInput) -> bool:
        """Detect DDoS based on drop counters, link quality, and ML detector alerts.

        Combines:
        1. Local ML/DL JSON alerts written to /tmp/ddos_severity.json by active XGB/TST detectors.
        2. Simple heuristic: if proxy drop rate exceeds 10% of total packets
           OR if rx_pps_median is abnormally high (>2× expected), mark DDoS.
        """
        # 1. Try to read active ML/DL detector reports
        severity_path = Path("/tmp/ddos_severity.json")
        ml_alert = False
        try:
            if severity_path.exists():
                alert = json.loads(severity_path.read_text(encoding="utf-8"))
                age = time.time() - alert.get("timestamp", 0)
                # If alert is fresh (under 10s) and indicates threat
                if age < 10.0 and alert.get("severity") in ("medium", "high", "critical"):
                    if alert.get("attack_type") != "BenignTraffic":
                        ml_alert = True
        except Exception:
            pass

        if ml_alert:
            return True

        # 2. Fall back to standard network stats heuristic
        if inp.proxy_enc_out <= 0:
            return False
        drop_ratio = inp.proxy_drop_total / max(inp.proxy_enc_out, 1)
        high_drops = drop_ratio > 0.10
        # Check if gap_p95 indicates packet flooding
        flooding = inp.gap_p95_ms < 1.0 and inp.rx_pps_median > 200.0
        return high_drops or flooding


    def record_rekey_cost(self, duration_ms: float) -> None:
        """Record a measured rekey duration for break-even calibration.

        Called by the scheduler after a successful rekey completes.
        Maintains a sliding window of the last 10 measurements.
        """
        self.rekey_cost_history.append(duration_ms)
        if len(self.rekey_cost_history) > 10:
            self.rekey_cost_history = self.rekey_cost_history[-10:]
        self.avg_rekey_cost_ms = (
            sum(self.rekey_cost_history) / len(self.rekey_cost_history)
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _check_hysteresis(self, key: str, active: bool, now_mono: float,
                          duration_s: float) -> bool:
        """Return True if condition has been active for duration_s."""
        if not active:
            self.hysteresis_start.pop(key, None)
            return False
        start = self.hysteresis_start.get(key)
        if start is None:
            self.hysteresis_start[key] = now_mono
            return False
        return (now_mono - start) >= duration_s

    def _suite_exists(self, aead: str, level: str) -> bool:
        """Check if the suite for this aead+level combination exists."""
        return aead in self._available.get(level, set()) and _compose_suite(aead, level) in self.all_suites

    def _best_aead_for_level(self, level: str) -> str:
        """Return the most efficient available AEAD for a given level,
        using measured cost ranking when available."""
        level_aeads = self._available.get(level, set())
        ranked = self._rank_aeads_by_cost()
        for aead in ranked:
            if aead in level_aeads:
                return aead
        return "aesgcm"  # fallback

    def _next_aead_for_level(self, current_aead: str, level: str) -> Optional[str]:
        """Return the next AEAD token (cyclic) within the same security level."""
        level_aeads = self._available.get(level, set())
        if not level_aeads:
            return None
        order = [a for a in _AEAD_PREFERENCE_ORDER if a in level_aeads]
        if not order:
            return None
        if current_aead not in order:
            return order[0]
        idx = order.index(current_aead)
        return order[(idx + 1) % len(order)]

    def _prune_rekey_events(self, now_mono: float) -> None:
        window_s = float(self.settings.get("rekey", {}).get("window_s", 300))
        window_ago = now_mono - window_s
        self.rekey_events = [e for e in self.rekey_events if float(e.get("ts", 0.0)) > window_ago]

    def _count_rekey_events(self, event_kind: str, now_mono: float) -> int:
        self._prune_rekey_events(now_mono)
        return sum(1 for e in self.rekey_events if e.get("kind") == event_kind)

    def allow_rekey_transition(
        self,
        action: PolicyAction,
        current_suite: str,
        target_suite: str,
        now_mono: float,
    ) -> tuple[bool, str]:
        """Enforce per-window budgets for same-suite, cross-suite and cross-level rekeys."""
        rk = self.settings.get("rekey", {})

        if target_suite == current_suite:
            same_count = self._count_rekey_events("same_suite", now_mono)
            same_max = int(rk.get("same_suite_max", 5))
            if same_count >= same_max:
                return False, f"same_suite_limit_reached({same_count}/{same_max})"
            return True, "ok"

        # Any suite change consumes different-suite budget.
        diff_count = self._count_rekey_events("different_suite", now_mono)
        diff_max = int(rk.get("different_suite_max", 5))
        if diff_count >= diff_max:
            return False, f"different_suite_limit_reached({diff_count}/{diff_max})"

        cur_meta = _parse_suite(current_suite)
        tgt_meta = _parse_suite(target_suite)
        if cur_meta.get("level") != tgt_meta.get("level"):
            lvl_count = self._count_rekey_events("different_level", now_mono)
            lvl_max = int(rk.get("different_level_max", 1))
            if lvl_count >= lvl_max:
                return False, f"different_level_limit_reached({lvl_count}/{lvl_max})"

        return True, "ok"

    def _log_transition(
        self,
        inp: DecisionInput,
        action: PolicyAction,
        from_suite: str,
        to_suite: str,
        reasons: List[str],
        *,
        from_aead: Optional[str] = None,
        to_aead: Optional[str] = None,
        break_even_s: Optional[float] = None,
        cost_saving_ns: Optional[float] = None,
    ) -> None:
        """Record structured transition for publication evidence."""
        resolved_from_aead = from_aead or inp.current_aead
        resolved_to_aead = to_aead or _parse_suite(to_suite).get("aead", "")
        record: Dict[str, Any] = {
            "ts_mono_ms": inp.mono_ms,
            "synced_time": inp.synced_time,
            "action": action.value,
            "from_suite": from_suite,
            "to_suite": to_suite,
            "from_aead": resolved_from_aead,
            "to_aead": resolved_to_aead,
            "reasons": reasons,
            "inputs": {
                "temp_c": round(inp.temp_c, 1),
                "temp_roc": round(inp.temp_roc, 2),
                "cpu_pct": round(inp.cpu_pct, 1),
                "battery_mv": inp.battery_mv,
                "battery_roc": round(inp.battery_roc, 1),
                "armed": inp.armed,
                "aead_encrypt_avg_ns": round(inp.aead_encrypt_avg_ns, 1),
                "aead_decrypt_avg_ns": round(inp.aead_decrypt_avg_ns, 1),
                "rx_pps_median": round(inp.rx_pps_median, 1),
                "gap_p95_ms": round(inp.gap_p95_ms, 1),
                "proxy_enc_out": inp.proxy_enc_out,
                "proxy_drop_total": inp.proxy_drop_total,
            },
            "mdeas": {
                "pkt_rate_hz": round(self._current_pkt_rate_hz, 1),
                "aead_profiles": {
                    k: v.to_dict() for k, v in self.aead_profiles.items()
                },
                "aead_ranking": self._rank_aeads_by_cost(),
                "avg_rekey_cost_ms": round(self.avg_rekey_cost_ms, 1),
            },
        }
        if break_even_s is not None and break_even_s != float("inf"):
            record["mdeas"]["break_even_s"] = round(break_even_s, 1)
        if cost_saving_ns is not None:
            record["mdeas"]["cost_saving_ns_per_pkt"] = round(cost_saving_ns, 1)
        self.transition_log.append(record)
        logging.info(
            f"POLICY TRANSITION: {action.value} {from_suite}/{resolved_from_aead} "
            f"→ {to_suite}/{resolved_to_aead} "
            f"reasons={reasons} pkt_rate={self._current_pkt_rate_hz:.0f}Hz"
        )

    @staticmethod
    def _transition_required(
        current_suite: str,
        target_suite: str,
        *,
        current_aead: str,
        target_aead: Optional[str],
    ) -> bool:
        if target_suite != current_suite:
            return True
        if not target_aead:
            return False
        try:
            return normalize_aead_token(current_aead) != normalize_aead_token(target_aead)
        except ValueError:
            return str(current_aead).strip().lower() != str(target_aead).strip().lower()

    # ------------------------------------------------------------------ #
    # Main evaluate
    # ------------------------------------------------------------------ #

    def evaluate(self, inp: DecisionInput) -> PolicyOutput:
        """Evaluate two-axis MDEAS policy and return a decision.

        Called at ~1 Hz from the scheduler loop.
        """
        now_mono = inp.mono_ms / 1000.0
        current = _parse_suite(inp.current_suite, inp.current_aead)
        cur_aead = current["aead"] or "aesgcm"
        cur_level = current["level"] or "L1"
        s = self.settings

        # ── Always update observations first ─────────────────────────
        self._update_observations(inp)

        # =================================================================
        # GATE 1: Telemetry freshness
        # =================================================================
        if not inp.telemetry_valid or inp.telemetry_age_ms > 2000:
            return PolicyOutput(PolicyAction.HOLD, reasons=["telemetry_stale"])

        # =================================================================
        # GATE 1.5: DDoS detection — lock to cheapest AEAD
        #
        # Under DDoS, CPU is loaded by the detection model and packet
        # processing.  Lock to cheapest AEAD to minimise crypto overhead.
        # This also prevents adversary-triggered AEAD exploration.
        # =================================================================
        ddos_now = self._detect_ddos(inp)
        if ddos_now and not self._ddos_detected:
            self._ddos_detected = True
            self._ddos_start_mono = now_mono
        elif not ddos_now and self._ddos_detected:
            # Require 30s of no-DDoS before clearing the flag
            if now_mono - self._ddos_start_mono > 30.0:
                self._ddos_detected = False

        if self._ddos_detected:
            cheapest = self._best_aead_for_level(cur_level)
            ddos_suite = _compose_suite(cheapest, cur_level)
            if self._transition_required(
                inp.current_suite,
                ddos_suite,
                current_aead=cur_aead,
                target_aead=cheapest,
            ) and self._suite_exists(cheapest, cur_level):
                reasons = ["ddos_detected", f"locking_aead={cheapest}",
                           f"drop_ratio={inp.proxy_drop_total/max(inp.proxy_enc_out,1):.2f}"]
                self._log_transition(inp, PolicyAction.EMERGENCY,
                                     inp.current_suite, ddos_suite, reasons,
                                     from_aead=cur_aead, to_aead=cheapest)
                return PolicyOutput(PolicyAction.EMERGENCY, ddos_suite,
                                    target_aead=cheapest,
                                    reasons=reasons, confidence=0.95)

        # =================================================================
        # GATE 2–3: Emergency safety (immediate L1 + cheapest AEAD)
        # =================================================================
        batt_crit = inp.battery_mv < s["battery"]["critical_mv"]
        temp_crit = inp.temp_c > s["thermal"]["critical_c"]

        if batt_crit or temp_crit:
            cheapest = self._best_aead_for_level("L1")
            emergency_suite = _compose_suite(cheapest, "L1")
            if self._transition_required(
                inp.current_suite,
                emergency_suite,
                current_aead=cur_aead,
                target_aead=cheapest,
            ) and self._suite_exists(cheapest, "L1"):
                reason = []
                if batt_crit:
                    reason.append("battery_critical")
                if temp_crit:
                    reason.append("temp_critical")
                reason.append(f"cheapest_aead={cheapest}")
                self._log_transition(inp, PolicyAction.EMERGENCY,
                                     inp.current_suite, emergency_suite, reason,
                                     from_aead=cur_aead, to_aead=cheapest)
                return PolicyOutput(PolicyAction.EMERGENCY, emergency_suite,
                                    target_aead=cheapest,
                                    reasons=reason, confidence=1.0)

        # Emergency also kills detector (Axis 3) — free up compute
        if (batt_crit or temp_crit) and inp.detector_level != DetectorLevel.NONE.value:
            return PolicyOutput(PolicyAction.DOWNGRADE_DETECTOR,
                                reasons=["emergency_kill_detector",
                                         "target_level=NONE"],
                                confidence=1.0)

        # =================================================================
        # GATE 3: Detector thermal management (Axis 3)
        #
        # If the current temperature exceeds the safe activation ceiling
        # for the active detector, downgrade the detector one step.
        # TST max baseline = 62°C, XGBoost max baseline = 71°C.
        # =================================================================
        if inp.detector_level != DetectorLevel.NONE.value:
            det_level = self._safe_detector_level(inp.detector_level)
            max_temp = _DETECTOR_MAX_BASELINE_TEMP.get(det_level, 80.0)
            if inp.temp_c > max_temp:
                det_idx = _DETECTOR_ORDER.index(det_level)
                if det_idx > 0:
                    new_det = _DETECTOR_ORDER[det_idx - 1]
                    return PolicyOutput(
                        PolicyAction.DOWNGRADE_DETECTOR,
                        reasons=["detector_thermal",
                                 f"temp={inp.temp_c:.1f}>max={max_temp:.0f}",
                                 f"target_level={new_det.value}"],
                        confidence=0.95)

        # =================================================================
        # GATE 4: Predictive thermal management (MDEAS novel)
        #
        # Uses thermal-energy joint model: predicts threshold crossing
        # accounting for the target AEAD's measured temperature delta.
        # If temp_roc predicts warn_c crossing within 60s, proactively
        # switch to cheapest AEAD NOW rather than waiting for the
        # temperature to actually cross the threshold.
        # =================================================================
        warn_c = s["thermal"]["warn_c"]
        cheapest = self._best_aead_for_level(cur_level)
        thermal_prediction_s = self._predict_thermal_crossing_s(
            inp.temp_c, inp.temp_roc, warn_c, target_aead=cheapest
        )
        if thermal_prediction_s is not None and thermal_prediction_s < 60.0:
            if cur_aead != cheapest and self._suite_exists(cheapest, cur_level):
                # Break-even check: is switching worth it?
                be_s = self._compute_break_even_s(
                    cur_aead, cheapest, self._current_pkt_rate_hz
                )
                # If temperature already crossed threshold (prediction=0),
                # switch aggressively regardless of break-even.
                # If predicted crossing: switch if break-even < 3× time-to-crossing
                should_switch = (
                    thermal_prediction_s <= 0.0  # already above warn_c
                    or be_s < thermal_prediction_s * 3.0
                )
                if should_switch:
                    target_suite = _compose_suite(cheapest, cur_level)
                    reasons = [
                        "predictive_thermal",
                        f"crossing_in_{thermal_prediction_s:.0f}s",
                        f"break_even_{be_s:.0f}s",
                    ]
                    cur_profile = self.aead_profiles.get(cur_aead)
                    tgt_profile = self.aead_profiles.get(cheapest)
                    saving = None
                    if cur_profile and tgt_profile:
                        saving = cur_profile.total_ns - tgt_profile.total_ns
                    self._log_transition(inp, PolicyAction.SWITCH_AEAD,
                                         inp.current_suite, target_suite,
                                         reasons,
                                         from_aead=cur_aead,
                                         to_aead=cheapest,
                                         break_even_s=be_s,
                                         cost_saving_ns=saving)
                    return PolicyOutput(PolicyAction.SWITCH_AEAD, target_suite,
                                        target_aead=cheapest,
                                        reasons=reasons, confidence=0.9)

        # =================================================================
        # AXIS 1: AEAD Selection — measurement-driven (MDEAS core)
        # =================================================================
        thermal_stress = (
            inp.temp_c > warn_c
            or inp.temp_roc > s["thermal"]["rate_warn_c_per_min"]
        )
        cpu_stress = inp.cpu_pct > 80.0
        battery_drain = inp.battery_roc < -s["battery"]["rate_warn_mv_per_min"]

        aead_stress = thermal_stress or cpu_stress or battery_drain

        # If under stress and not already on the cheapest AEAD
        if self._check_hysteresis("aead_stress", aead_stress, now_mono,
                                  s["hysteresis"]["downgrade_s"]):
            cheapest = self._best_aead_for_level(cur_level)
            if cur_aead != cheapest and self._suite_exists(cheapest, cur_level):
                # Break-even check: only switch if the savings justify the rekey
                be_s = self._compute_break_even_s(
                    cur_aead, cheapest, self._current_pkt_rate_hz
                )
                # Under stress we're more aggressive — accept shorter break-even
                effective_threshold = max(self._MIN_BREAK_EVEN_S / 2.0, 10.0)
                if be_s <= effective_threshold or be_s < 120.0:
                    target_suite = _compose_suite(cheapest, cur_level)
                    reasons = []
                    if thermal_stress:
                        reasons.append("thermal_stress")
                    if cpu_stress:
                        reasons.append("cpu_stress")
                    if battery_drain:
                        reasons.append("battery_drain")
                    reasons.append(f"measured_cheapest={cheapest}")
                    reasons.append(f"break_even_{be_s:.0f}s")

                    cur_profile = self.aead_profiles.get(cur_aead)
                    tgt_profile = self.aead_profiles.get(cheapest)
                    saving = None
                    if cur_profile and tgt_profile:
                        saving = cur_profile.total_ns - tgt_profile.total_ns
                    self._log_transition(inp, PolicyAction.SWITCH_AEAD,
                                         inp.current_suite, target_suite,
                                         reasons,
                                         from_aead=cur_aead,
                                         to_aead=cheapest,
                                         break_even_s=be_s,
                                         cost_saving_ns=saving)
                    return PolicyOutput(PolicyAction.SWITCH_AEAD, target_suite,
                                        target_aead=cheapest,
                                        reasons=reasons, confidence=0.85)

        # AEAD Recovery: if stress has subsided, consider restoring preferred AEAD
        preferred_aead = s.get("preferred_aead", "chacha20poly1305")
        aead_recovered = not aead_stress and cur_aead != preferred_aead
        recovery_s = max(
            s["hysteresis"].get("aead_recovery_s", 10.0),
            self._MIN_RECOVERY_STABILITY_S / 6.0,  # at least 10s
        )

        if self._check_hysteresis("aead_recovery", aead_recovered, now_mono,
                                  recovery_s):
            # Step toward preferred AEAD — but only if measured cost allows it
            cur_idx = _AEAD_PREFERENCE_ORDER.index(cur_aead) if cur_aead in _AEAD_PREFERENCE_ORDER else 0
            pref_idx = _AEAD_PREFERENCE_ORDER.index(preferred_aead) if preferred_aead in _AEAD_PREFERENCE_ORDER else 1

            if cur_idx != pref_idx:
                # Determine direction toward preferred
                step = 1 if pref_idx > cur_idx else -1
                next_aead = _AEAD_PREFERENCE_ORDER[cur_idx + step]

                if self._suite_exists(next_aead, cur_level):
                    # Break-even check for recovery (more conservative)
                    be_s = self._compute_break_even_s(
                        cur_aead, next_aead, self._current_pkt_rate_hz
                    )
                    # For recovery, we require a longer break-even window
                    # since we're upgrading to a potentially more expensive AEAD
                    if be_s <= self._MIN_BREAK_EVEN_S or be_s == float("inf"):
                        # inf means target is more expensive — check if it's
                        # within acceptable thermal budget
                        tgt_profile = self.aead_profiles.get(next_aead)
                        if tgt_profile and tgt_profile.is_reliable():
                            # Only recover if the target's cost is within 2x
                            # of the current, AND temperature is well below warn
                            cur_profile = self.aead_profiles.get(cur_aead)
                            if cur_profile and cur_profile.is_reliable():
                                cost_ratio = tgt_profile.total_ns / max(cur_profile.total_ns, 1.0)
                                if cost_ratio <= 2.0 and inp.temp_c < (warn_c - 10.0):
                                    target_suite = _compose_suite(next_aead, cur_level)
                                    reasons = ["aead_recovery",
                                               f"cost_ratio={cost_ratio:.2f}",
                                               f"temp_headroom={warn_c - inp.temp_c:.0f}C"]
                                    self._log_transition(inp, PolicyAction.SWITCH_AEAD,
                                                         inp.current_suite, target_suite,
                                                         reasons,
                                                         from_aead=cur_aead,
                                                         to_aead=next_aead)
                                    return PolicyOutput(PolicyAction.SWITCH_AEAD,
                                                        target_suite,
                                                        target_aead=next_aead,
                                                        reasons=reasons, confidence=0.7)
                        else:
                            # Target not measured yet — allow exploration if temp is safe
                            if inp.temp_c < (warn_c - 15.0):
                                target_suite = _compose_suite(next_aead, cur_level)
                                reasons = ["aead_recovery", "exploration"]
                                self._log_transition(inp, PolicyAction.SWITCH_AEAD,
                                                     inp.current_suite, target_suite,
                                                     reasons,
                                                     from_aead=cur_aead,
                                                     to_aead=next_aead)
                                return PolicyOutput(PolicyAction.SWITCH_AEAD,
                                                    target_suite,
                                                    target_aead=next_aead,
                                                    reasons=reasons, confidence=0.5)

        # =================================================================
        # AXIS 2: Security Level Selection (link + mission)
        # =================================================================
        link_bad = (
            inp.gap_p95_ms > s["link"]["max_gap_ms"]
            or inp.rx_pps_median < s["link"]["min_pps"]
        )

        # Downgrade level if link is bad (with hysteresis)
        if self._check_hysteresis("link_bad", link_bad, now_mono,
                                  s["hysteresis"]["downgrade_s"]):
            cur_idx = _LEVEL_ORDER.index(cur_level) if cur_level in _LEVEL_ORDER else 0
            if cur_idx > 0:
                new_level = _LEVEL_ORDER[cur_idx - 1]
                target_suite = _compose_suite(cur_aead, new_level)
                if self._suite_exists(cur_aead, new_level):
                    reasons = ["link_degraded"]
                    self._log_transition(inp, PolicyAction.DOWNGRADE_LEVEL,
                                         inp.current_suite, target_suite, reasons,
                                         from_aead=cur_aead, to_aead=cur_aead)
                    return PolicyOutput(PolicyAction.DOWNGRADE_LEVEL, target_suite,
                                        target_aead=cur_aead,
                                        reasons=reasons, confidence=0.8)

        # =================================================================
        # GATE 7: Cooldown
        # =================================================================
        if inp.cooldown_until_mono_ms > inp.mono_ms:
            return PolicyOutput(PolicyAction.HOLD, reasons=["cooldown"])

        # =================================================================
        # GATE 7.5: Deterministic AEAD shift cadence (independent axis)
        #
        # Rotate AEAD every configured interval while keeping KEM/SIG level
        # unchanged, so AEAD movement is independent from level transitions.
        # =================================================================
        shift_interval_s = float(s.get("rekey", {}).get("aead_shift_interval_s", 0.0))
        if shift_interval_s > 0.0:
            since_switch_s = (inp.mono_ms - inp.last_switch_mono_ms) / 1000.0
            if since_switch_s >= shift_interval_s:
                next_aead = self._next_aead_for_level(cur_aead, cur_level)
                if next_aead and next_aead != cur_aead and self._suite_exists(next_aead, cur_level):
                    target_suite = _compose_suite(next_aead, cur_level)
                    if self._check_cross_axis_constraints(
                        target_suite,
                        inp.detector_level,
                        target_aead=next_aead,
                    ):
                        reasons = [
                            "periodic_aead_shift",
                            f"interval_s={shift_interval_s:.0f}",
                        ]
                        self._log_transition(inp, PolicyAction.SWITCH_AEAD,
                                             inp.current_suite, target_suite, reasons,
                                             from_aead=cur_aead, to_aead=next_aead)
                        return PolicyOutput(PolicyAction.SWITCH_AEAD, target_suite,
                                            target_aead=next_aead,
                                            reasons=reasons, confidence=0.7)

        # =================================================================
        # GATE 8: Proactive rekey (same suite, rotate keys)
        # =================================================================
        stable_time = (inp.mono_ms - inp.last_switch_mono_ms) / 1000.0
        if stable_time > s["rekey"]["min_stable_s"]:
            window_s = float(s["rekey"].get("window_s", 300))
            window_ago = now_mono - window_s
            self.rekey_timestamps = [t for t in self.rekey_timestamps if t > window_ago]
            max_per = int(s["rekey"].get("max_per_window",
                                         s["rekey"].get("max_per_hour", 5)))
            if len(self.rekey_timestamps) < max_per:
                return PolicyOutput(PolicyAction.REKEY, inp.current_suite,
                                    target_aead=cur_aead,
                                    reasons=["proactive_rekey"], confidence=0.5)

        # =================================================================
        # AXIS 3 (stress path): Detector downgrade under system stress
        #
        # If temperature or CPU is elevated AND a detector is running,
        # downgrade the detector one step before touching Axis 2.
        # This is a cheaper remediation than changing KEM/SIG level.
        # =================================================================
        if aead_stress and inp.detector_level != DetectorLevel.NONE.value:
            det_level = self._safe_detector_level(inp.detector_level)
            det_idx = _DETECTOR_ORDER.index(det_level)
            if det_idx > 0:
                new_det = _DETECTOR_ORDER[det_idx - 1]
                if self._check_hysteresis("detector_stress", True, now_mono,
                                          s["hysteresis"]["downgrade_s"]):
                    return PolicyOutput(
                        PolicyAction.DOWNGRADE_DETECTOR,
                        reasons=["system_stress",
                                 f"target_level={new_det.value}"],
                        confidence=0.85)

        # =================================================================
        # GATE 9: Upgrade level (conservative, armed-compatible recovery)
        #
        # Disarmed : upgrade after upgrade_s (30s) hysteresis
        # Armed    : upgrade after 3× upgrade_s (90s) hysteresis — slower
        #            but ensures recovery from transient degrades in flight
        # =================================================================
        if not aead_stress and not link_bad:
            upgrade_delay = s["hysteresis"]["upgrade_s"]
            if inp.armed:
                upgrade_delay *= 3.0  # 3× more conservative when armed

            if self._check_hysteresis("upgrade_ok", True, now_mono, upgrade_delay):
                cur_idx = _LEVEL_ORDER.index(cur_level) if cur_level in _LEVEL_ORDER else 0
                if cur_idx < len(_LEVEL_ORDER) - 1:
                    new_level = _LEVEL_ORDER[cur_idx + 1]
                    target_suite = _compose_suite(cur_aead, new_level)
                    if self._suite_exists(cur_aead, new_level):
                        reasons = ["stable_upgrade"]
                        if inp.armed:
                            reasons.append("in_flight_recovery")
                        self._log_transition(inp, PolicyAction.UPGRADE_LEVEL,
                                             inp.current_suite, target_suite, reasons,
                                             from_aead=cur_aead, to_aead=cur_aead)
                        return PolicyOutput(PolicyAction.UPGRADE_LEVEL, target_suite,
                                            target_aead=cur_aead,
                                            reasons=reasons, confidence=0.6)

        # =================================================================
        # AXIS 3 (upgrade path): Detector upgrade under stable conditions
        #
        # If system is stable (no stress, no link issues) and the
        # current detector is below the maximum level, try upgrading.
        # More conservative than level upgrade: requires 2× upgrade_delay.
        # =================================================================
        if not aead_stress and not link_bad:
            det_level = self._safe_detector_level(inp.detector_level)
            det_idx = _DETECTOR_ORDER.index(det_level)
            if det_idx < len(_DETECTOR_ORDER) - 1:
                next_det = _DETECTOR_ORDER[det_idx + 1]
                det_upgrade_delay = s["hysteresis"]["upgrade_s"] * 2.0
                if inp.armed:
                    det_upgrade_delay *= 3.0  # Extra conservative in flight

                if self._check_hysteresis("detector_upgrade", True, now_mono,
                                          det_upgrade_delay):
                    if self._can_activate_detector(next_det.value, inp):
                        return PolicyOutput(
                            PolicyAction.UPGRADE_DETECTOR,
                            reasons=["stable_detector_upgrade",
                                     f"target_level={next_det.value}"],
                            confidence=0.5)

        # =================================================================
        # NOMINAL
        # =================================================================
        return PolicyOutput(PolicyAction.HOLD, reasons=["nominal"])

    def record_rekey(
        self,
        now_mono: float,
        *,
        previous_suite: Optional[str] = None,
        target_suite: Optional[str] = None,
        action: Optional[PolicyAction] = None,
    ) -> None:
        """Record a successful rekey timestamp and classify transition kind."""
        self.rekey_timestamps.append(now_mono)

        prev = previous_suite or ""
        tgt = target_suite or prev
        kind = "same_suite" if prev == tgt else "different_suite"
        prev_meta = _parse_suite(prev)
        tgt_meta = _parse_suite(tgt)
        if prev and tgt and prev_meta.get("level") != tgt_meta.get("level"):
            kind = "different_level"

        self.rekey_events.append(
            {
                "ts": now_mono,
                "kind": kind,
                "action": action.value if isinstance(action, PolicyAction) else str(action or ""),
                "from": prev,
                "to": tgt,
            }
        )
        self._prune_rekey_events(now_mono)

    def get_transition_log(self) -> List[Dict[str, Any]]:
        """Return all recorded transitions for publication analysis."""
        return list(self.transition_log)

    def get_aead_profiles(self) -> Dict[str, Dict[str, Any]]:
        """Return current AEAD cost profiles for external inspection."""
        return {k: v.to_dict() for k, v in self.aead_profiles.items()}
