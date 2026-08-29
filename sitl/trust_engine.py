#!/usr/bin/env python3
"""
Multi-Dimensional UAV Trust Engine (Dynamic Trust Scoring & Isolation System).

Evaluates continuous trust index T_i in [0.0, 1.0] by fusing 4 weighted security dimensions:
  T_i = W_auth * S_auth + W_integ * S_integ + W_comm * S_comm + W_hist * S_hist

Where:
1. S_auth  in [0.0, 1.0]: PQC Authentication Status (ML-DSA-65 signature & cert validity)
2. S_integ in [0.0, 1.0]: Telemetry State Integrity (SMT 256-depth root & leaf verification)
3. S_comm  in [0.0, 1.0]: Communications Behavior (sequence continuity & packet jitter)
4. S_hist  in [0.0, 1.0]: History/Reputation score (1.0 - penalty), recovering via exponential decay

Weights: W_auth = 0.30, W_integ = 0.30, W_comm = 0.20, W_hist = 0.20 (sum = 1.0, max score = 1.0).

Triggers real-time security state transitions:
- TRUSTED     (T_i >= 0.80)
- MONITORED   (0.50 <= T_i < 0.80)
- QUARANTINED (0.20 <= T_i < 0.50)
- ISOLATED    (T_i < 0.20)
"""

from __future__ import annotations

import math
import time
from enum import Enum
from typing import Dict, List, Optional, Tuple


class TrustState(Enum):
    TRUSTED = "TRUSTED"          # T_i >= 0.80
    MONITORED = "MONITORED"      # 0.50 <= T_i < 0.80
    QUARANTINED = "QUARANTINED"  # 0.20 <= T_i < 0.50
    ISOLATED = "ISOLATED"        # T_i < 0.20


class MultiDimensionalTrustEngine:
    """Dynamic multi-dimensional trust evaluation engine for UAV swarms."""

    def __init__(
        self,
        w_auth: float = 0.30,
        w_integ: float = 0.30,
        w_comm: float = 0.20,
        w_hist: float = 0.20,
        decay_half_life_sec: float = 10.0,
    ) -> None:
        self.w_auth = w_auth
        self.w_integ = w_integ
        self.w_comm = w_comm
        self.w_hist = w_hist
        self.decay_half_life_sec = decay_half_life_sec

        self._last_update: Dict[str, float] = {}
        self._seq_history: Dict[str, int] = {}
        self._last_arrival: Dict[str, float] = {}
        self._jitter_history: Dict[str, List[float]] = {}
        self._penalty_score: Dict[str, float] = {}
        self._trust_scores: Dict[str, float] = {}
        self._trust_states: Dict[str, TrustState] = {}

    def update_drone_trust(
        self,
        drone_id: str,
        pqc_auth_valid: bool,
        smt_integrity_valid: bool,
        seq: int,
        attack_detected: bool = False,
        tampering_detected: bool = False,
        now: Optional[float] = None,
    ) -> Tuple[float, TrustState]:
        """Update trust parameters and recalculate dynamic Trust Score T_i."""
        t_now = now or time.time()
        t_prev = self._last_update.get(drone_id, t_now)
        dt = max(0.001, t_now - t_prev)
        self._last_update[drone_id] = t_now

        # 1. Authentication Score S_auth
        s_auth = 1.0 if pqc_auth_valid else 0.0

        # 2. Telemetry State Integrity Score S_integ
        s_integ = 1.0 if smt_integrity_valid else 0.0

        # 3. Communications Behavior Score S_comm
        last_seq = self._seq_history.get(drone_id, seq - 1)
        seq_delta = (seq - last_seq) & 0xFF
        self._seq_history[drone_id] = seq
        seq_score = 1.0 if seq_delta == 1 else (0.5 if seq_delta > 1 else 0.0)

        last_arr = self._last_arrival.get(drone_id, t_now - 0.1)
        arrival_delta = t_now - last_arr
        self._last_arrival[drone_id] = t_now

        jitter = abs(arrival_delta - 0.1)
        jitters = self._jitter_history.setdefault(drone_id, [])
        jitters.append(jitter)
        if len(jitters) > 10:
            jitters.pop(0)
        avg_jitter = sum(jitters) / len(jitters)
        jitter_score = max(0.0, 1.0 - (avg_jitter / 0.1))

        s_comm = 0.6 * seq_score + 0.4 * jitter_score

        # 4. History/Reputation Score S_hist = 1.0 - P_penalty (with Exponential Decay)
        current_penalty = self._penalty_score.get(drone_id, 0.0)
        decay_factor = math.pow(0.5, dt / self.decay_half_life_sec)
        current_penalty *= decay_factor

        if attack_detected:
            current_penalty += 0.8
        if tampering_detected:
            current_penalty += 1.0

        current_penalty = min(1.0, current_penalty)
        self._penalty_score[drone_id] = current_penalty
        s_hist = max(0.0, 1.0 - current_penalty)

        # Total Additive Weighted Trust Score T_i in [0.0, 1.0]
        raw_trust = (
            self.w_auth * s_auth
            + self.w_integ * s_integ
            + self.w_comm * s_comm
            + self.w_hist * s_hist
        )
        trust_score = round(max(0.0, min(1.0, raw_trust)), 4)
        self._trust_scores[drone_id] = trust_score

        # State Mapping
        if trust_score >= 0.80:
            state = TrustState.TRUSTED
        elif trust_score >= 0.50:
            state = TrustState.MONITORED
        elif trust_score >= 0.20:
            state = TrustState.QUARANTINED
        else:
            state = TrustState.ISOLATED

        self._trust_states[drone_id] = state
        return trust_score, state

    def get_trust_score(self, drone_id: str) -> float:
        return self._trust_scores.get(drone_id, 1.0)

    def get_trust_state(self, drone_id: str) -> TrustState:
        return self._trust_states.get(drone_id, TrustState.TRUSTED)


if __name__ == "__main__":
    print("Testing Updated Multi-Dimensional Trust Engine...")
    engine = MultiDimensionalTrustEngine()

    score, state = engine.update_drone_trust("drone-1", pqc_auth_valid=True, smt_integrity_valid=True, seq=1)
    print(f"[DRONE-1 Baseline] Score: {score} (Max 1.0), State: {state.value}")

    score, state = engine.update_drone_trust("drone-1", pqc_auth_valid=True, smt_integrity_valid=False, seq=2, tampering_detected=True)
    print(f"[DRONE-1 Tampered] Score: {score}, State: {state.value}")
