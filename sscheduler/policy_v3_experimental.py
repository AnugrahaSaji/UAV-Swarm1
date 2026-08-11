"""Benchmark-driven experimental scheduler policy (v3).

This module is intentionally independent from sscheduler/policy.py.
It derives decisions from measured artifacts only:
- drone-e2e-report/raw-results.json
- gcs-e2e-report/raw-results.json
- mavlink-benchmark-report/aead-metrics-extracted.json
- mavlink-benchmark-report/rekey-events.md

Design notes:
- No fabricated benchmark values are introduced.
- If a metric is missing, the candidate is either penalized or excluded.
- Candidate space is constrained to repository-supported scheduler suites and
  AEAD profiles available for each NIST level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.suites import (
    approved_aead_profiles_by_nist_level,
    get_suite,
    list_scheduler_approved_suites,
)


_NIST_RANK = {"L1": 1, "L3": 3, "L5": 5}


@dataclass(frozen=True)
class DecisionInput:
    """Runtime telemetry and mission constraints consumed by the scheduler."""

    battery_mv: int
    cpu_pct: float
    temp_c: float
    packet_loss_percent: float
    rtt_us: float
    current_suite: str
    current_aead: str
    mission_min_nist_level: str = "L3"
    mission_mode: str = "balanced"  # one of: performance, balanced, security
    rekey_interval_s: float = 300.0
    seconds_since_last_rekey: float = 0.0
    force_rekey: bool = False
    telemetry_valid: bool = True


@dataclass(frozen=True)
class SuiteCandidate:
    """A concrete (suite, AEAD) option with measured/derived costs."""

    suite_id: str
    aead_token: str
    nist_level: str
    kem_name: str
    sig_name: str
    aead_encrypt_ns: float
    aead_decrypt_ns: float
    rtt_us: float
    packet_loss_percent: float
    rekey_interrupt_ms: float
    handshake_cost_ms: Optional[float]
    setup_proxy_cost_ms: float
    post_rekey_delivery_percent: Optional[float]


@dataclass(frozen=True)
class RankedCandidate:
    candidate: SuiteCandidate
    score: float
    crypto_cost: float
    latency_cost_ms: float
    loss_cost: float
    security_penalty: float


@dataclass(frozen=True)
class SchedulerDecision:
    selected_suite: str
    selected_aead: str
    target_nist_level: str
    rekey_required: bool
    recommended_rekey_interval_s: float
    score: float
    rationale: Tuple[str, ...] = field(default_factory=tuple)


@dataclass
class BenchmarkCostProfile:
    """Measured benchmark profile loaded from repository artifacts."""

    kem_encap_ns: Dict[str, float]
    kem_decap_ns: Dict[str, float]
    sig_sign_ns: Dict[str, float]
    sig_verify_ns: Dict[str, float]
    aead_encrypt_ns: Dict[str, float]
    aead_decrypt_ns: Dict[str, float]
    rtt_us_by_aead: Dict[str, float]
    packet_loss_by_aead: Dict[str, float]
    rekey_interrupt_ms_by_aead: Dict[str, float]
    post_rekey_delivery_percent_by_aead: Dict[str, float]
    handshake_ms_by_suite: Dict[str, float]
    source_notes: Dict[str, str]

    @staticmethod
    def _repo_root() -> Path:
        return Path(__file__).resolve().parents[1]

    @staticmethod
    def _read_json(path: Path) -> Any:
        """Read JSON with BOM-tolerant decoding for artifact compatibility."""
        return json.loads(path.read_text(encoding="utf-8-sig"))

    @classmethod
    def from_artifacts(cls, root: Optional[Path] = None) -> "BenchmarkCostProfile":
        base = root or cls._repo_root()

        drone_raw_path = base / "drone-e2e-report" / "raw-results.json"
        gcs_raw_path = base / "gcs-e2e-report" / "raw-results.json"
        aead_metrics_path = base / "mavlink-benchmark-report" / "aead-metrics-extracted.json"
        rekey_md_path = base / "mavlink-benchmark-report" / "rekey-events.md"

        drone_raw = cls._read_json(drone_raw_path)
        gcs_raw = cls._read_json(gcs_raw_path)
        aead_metrics = cls._read_json(aead_metrics_path)
        rekey_md = rekey_md_path.read_text(encoding="utf-8")

        kem_encap: Dict[str, float] = {}
        kem_decap: Dict[str, float] = {}
        for row in drone_raw.get("kem", []):
            alg = str(row.get("algorithm", "")).strip()
            if not alg:
                continue
            kem_encap[alg] = float(row.get("encap", {}).get("mean_ns", 0.0) or 0.0)
            kem_decap[alg] = float(row.get("decap", {}).get("mean_ns", 0.0) or 0.0)

        sig_sign: Dict[str, float] = {}
        sig_verify: Dict[str, float] = {}
        for row in drone_raw.get("signature", []):
            alg = str(row.get("algorithm", "")).strip()
            if not alg:
                continue
            sig_sign[alg] = float(row.get("sign", {}).get("mean_ns", 0.0) or 0.0)
            sig_verify[alg] = float(row.get("verify", {}).get("mean_ns", 0.0) or 0.0)

        # Prefer drone-side AEAD timings when available, then fill from GCS.
        aead_encrypt: Dict[str, float] = {}
        aead_decrypt: Dict[str, float] = {}

        def _ingest_aead_rows(rows: Iterable[Dict[str, Any]], *, overwrite: bool) -> None:
            for row in rows:
                token = str(row.get("algorithm", "")).strip().lower()
                if not token:
                    continue
                if int(row.get("payload_bytes", -1) or -1) != 1024:
                    continue
                if row.get("error"):
                    continue
                enc = float(row.get("encrypt", {}).get("mean_ns", 0.0) or 0.0)
                dec = float(row.get("decrypt", {}).get("mean_ns", 0.0) or 0.0)
                if enc <= 0.0 or dec <= 0.0:
                    continue
                if overwrite or token not in aead_encrypt:
                    aead_encrypt[token] = enc
                    aead_decrypt[token] = dec

        _ingest_aead_rows(drone_raw.get("aead", []), overwrite=True)
        _ingest_aead_rows(gcs_raw.get("aead", []), overwrite=False)

        rtt_by_aead: Dict[str, float] = {}
        loss_by_aead: Dict[str, float] = {}
        rekey_interrupt_by_aead: Dict[str, float] = {}
        for row in aead_metrics:
            token = str(row.get("aead_algorithm", "")).strip().lower()
            if not token:
                continue
            rtt_by_aead[token] = float(row.get("mean_rtt_us", 0.0) or 0.0)
            loss_by_aead[token] = float(row.get("packet_loss_percent", 0.0) or 0.0)
            rekey_interrupt_by_aead[token] = float(row.get("rekey_interruption_duration_ms", 0.0) or 0.0)

        # Parse post-rekey delivery from markdown summary table.
        post_rekey_delivery: Dict[str, float] = {}
        row_re = re.compile(r"\|\s*([a-z0-9]+)\s*\|\s*Yes\s*\|\s*Yes\s*\|\s*([0-9.]+)%\s*\|\s*([0-9.]+)%\s*\|\s*([0-9.]+)%")
        for line in rekey_md.splitlines():
            m = row_re.search(line.lower())
            if not m:
                continue
            token = m.group(1).strip().lower()
            post_rekey_delivery[token] = float(m.group(4))

        # Aggregate directly measured handshake values from both artifacts.
        handshake_samples: Dict[str, List[float]] = {}

        def _collect_handshake(doc: Dict[str, Any]) -> None:
            e2e = doc.get("e2e", {})
            suite = str(e2e.get("suite", "")).strip()
            if not suite:
                return
            vals: List[float] = []
            for key in ("gcs_handshake_ms", "drone_handshake_ms"):
                raw = float(e2e.get(key, 0.0) or 0.0)
                if raw > 0.0:
                    vals.append(raw)
            if vals:
                handshake_samples.setdefault(suite, []).extend(vals)

        _collect_handshake(drone_raw)
        _collect_handshake(gcs_raw)

        handshake_ms_by_suite = {suite: mean(vals) for suite, vals in handshake_samples.items() if vals}

        notes = {
            "handshake_ms": "Direct suite handshake is only available where e2e.suite appears in raw-results.json.",
            "aead_latency_ns": "AEAD 1024-byte means use drone artifact first, then GCS artifact fallback for missing tokens.",
            "rekey_interval_basis": "Observed benchmark trigger in artifacts is 300 seconds.",
        }

        return cls(
            kem_encap_ns=kem_encap,
            kem_decap_ns=kem_decap,
            sig_sign_ns=sig_sign,
            sig_verify_ns=sig_verify,
            aead_encrypt_ns=aead_encrypt,
            aead_decrypt_ns=aead_decrypt,
            rtt_us_by_aead=rtt_by_aead,
            packet_loss_by_aead=loss_by_aead,
            rekey_interrupt_ms_by_aead=rekey_interrupt_by_aead,
            post_rekey_delivery_percent_by_aead=post_rekey_delivery,
            handshake_ms_by_suite=handshake_ms_by_suite,
            source_notes=notes,
        )

    def setup_proxy_cost_ms_for_suite(self, suite_id: str) -> Optional[float]:
        """Derived setup proxy from measured primitive means: encap+decap+sign+verify."""
        suite = get_suite(suite_id)
        kem_name = str(suite.get("kem_name", ""))
        sig_name = str(suite.get("sig_name", ""))

        enc = self.kem_encap_ns.get(kem_name)
        dec = self.kem_decap_ns.get(kem_name)
        sign = self.sig_sign_ns.get(sig_name)
        verify = self.sig_verify_ns.get(sig_name)
        if None in (enc, dec, sign, verify):
            return None
        total_ns = float(enc or 0.0) + float(dec or 0.0) + float(sign or 0.0) + float(verify or 0.0)
        return total_ns / 1_000_000.0


class BenchmarkDrivenSchedulerV3:
    """Deterministic benchmark-driven scheduler with explicit cost model."""

    def __init__(self, profile: Optional[BenchmarkCostProfile] = None):
        self.profile = profile or BenchmarkCostProfile.from_artifacts()
        self._approved_suites = list_scheduler_approved_suites()
        self._approved_aead_by_level = approved_aead_profiles_by_nist_level(runtime_only=False)

    @staticmethod
    def _normalize(values: List[float]) -> List[float]:
        if not values:
            return []
        lo = min(values)
        hi = max(values)
        if hi <= lo:
            return [0.0 for _ in values]
        return [(v - lo) / (hi - lo) for v in values]

    @staticmethod
    def _mode_weights(mode: str) -> Tuple[float, float, float]:
        # (latency_weight, crypto_weight, loss_weight)
        mode_key = (mode or "balanced").strip().lower()
        if mode_key == "performance":
            return (0.45, 0.40, 0.15)
        if mode_key == "security":
            return (0.20, 0.30, 0.50)
        return (0.35, 0.40, 0.25)

    def _build_candidates(self, inp: DecisionInput) -> List[SuiteCandidate]:
        required_rank = _NIST_RANK.get(inp.mission_min_nist_level, 3)
        candidates: List[SuiteCandidate] = []

        for suite_id, suite_cfg in sorted(self._approved_suites.items()):
            nist_level = str(suite_cfg.get("nist_level", "L1"))
            if _NIST_RANK.get(nist_level, 0) < required_rank:
                continue

            level_aeads = self._approved_aead_by_level.get(nist_level, ())
            if not level_aeads:
                continue

            setup_proxy_ms = self.profile.setup_proxy_cost_ms_for_suite(suite_id)
            if setup_proxy_ms is None:
                continue

            direct_handshake_ms = self.profile.handshake_ms_by_suite.get(suite_id)
            kem_name = str(suite_cfg.get("kem_name", ""))
            sig_name = str(suite_cfg.get("sig_name", ""))

            for aead in sorted(level_aeads):
                enc_ns = self.profile.aead_encrypt_ns.get(aead)
                dec_ns = self.profile.aead_decrypt_ns.get(aead)
                rtt_us = self.profile.rtt_us_by_aead.get(aead)
                loss_pct = self.profile.packet_loss_by_aead.get(aead)
                rekey_interrupt_ms = self.profile.rekey_interrupt_ms_by_aead.get(aead)

                # Only evaluate candidates where RTT/loss/rekey interruption are measured.
                if None in (rtt_us, loss_pct, rekey_interrupt_ms):
                    continue
                # AEAD latency must be measurable from artifacts.
                if None in (enc_ns, dec_ns):
                    continue

                post_rekey_delivery = self.profile.post_rekey_delivery_percent_by_aead.get(aead)

                candidates.append(
                    SuiteCandidate(
                        suite_id=suite_id,
                        aead_token=aead,
                        nist_level=nist_level,
                        kem_name=kem_name,
                        sig_name=sig_name,
                        aead_encrypt_ns=float(enc_ns),
                        aead_decrypt_ns=float(dec_ns),
                        rtt_us=float(rtt_us),
                        packet_loss_percent=float(loss_pct),
                        rekey_interrupt_ms=float(rekey_interrupt_ms),
                        handshake_cost_ms=(float(direct_handshake_ms) if direct_handshake_ms is not None else None),
                        setup_proxy_cost_ms=float(setup_proxy_ms),
                        post_rekey_delivery_percent=(float(post_rekey_delivery) if post_rekey_delivery is not None else None),
                    )
                )

        return candidates

    @staticmethod
    def _security_penalty(candidate_level: str, required_level: str) -> float:
        cand = _NIST_RANK.get(candidate_level, 0)
        req = _NIST_RANK.get(required_level, 0)
        if cand >= req:
            return 0.0
        return float(req - cand)

    def _rank_candidates(self, inp: DecisionInput, candidates: List[SuiteCandidate]) -> List[RankedCandidate]:
        if not candidates:
            return []

        interval_s = max(1.0, float(inp.rekey_interval_s))
        latency_w, crypto_w, loss_w = self._mode_weights(inp.mission_mode)

        raw_crypto: List[float] = []
        raw_latency: List[float] = []
        raw_loss: List[float] = []
        sec_penalties: List[float] = []

        for c in candidates:
            # Cost model derived from measured values:
            # crypto_cost = AEAD_cost + setup_cost / rekey_interval
            aead_cost_ms = (c.aead_encrypt_ns + c.aead_decrypt_ns) / 1_000_000.0
            setup_for_interval_ms = c.setup_proxy_cost_ms / interval_s
            raw_crypto.append(aead_cost_ms + setup_for_interval_ms)
            raw_latency.append(c.rtt_us / 1000.0)
            raw_loss.append(c.packet_loss_percent)
            sec_penalties.append(self._security_penalty(c.nist_level, inp.mission_min_nist_level))

        n_crypto = self._normalize(raw_crypto)
        n_latency = self._normalize(raw_latency)
        n_loss = self._normalize(raw_loss)

        ranked: List[RankedCandidate] = []
        for idx, c in enumerate(candidates):
            score = (
                latency_w * n_latency[idx]
                + crypto_w * n_crypto[idx]
                + loss_w * n_loss[idx]
                + 0.75 * sec_penalties[idx]
            )

            # Hard reliability penalty when measured post-rekey delivery is below 95%.
            if c.post_rekey_delivery_percent is not None and c.post_rekey_delivery_percent < 95.0:
                score += 1.0

            ranked.append(
                RankedCandidate(
                    candidate=c,
                    score=score,
                    crypto_cost=raw_crypto[idx],
                    latency_cost_ms=raw_latency[idx],
                    loss_cost=raw_loss[idx],
                    security_penalty=sec_penalties[idx],
                )
            )

        ranked.sort(
            key=lambda r: (
                round(r.score, 12),
                -_NIST_RANK.get(r.candidate.nist_level, 0),
                r.candidate.suite_id,
                r.candidate.aead_token,
            )
        )
        return ranked

    @staticmethod
    def _recommended_rekey_interval_s(inp: DecisionInput) -> float:
        # Artifact-backed benchmark trigger is 300s. No alternate measured trigger
        # is available in provided artifacts, so keep this deterministic.
        _ = inp
        return 300.0

    @staticmethod
    def _should_rekey(inp: DecisionInput, selected: SuiteCandidate, interval_s: float) -> bool:
        if inp.force_rekey:
            return True
        if selected.post_rekey_delivery_percent is not None and selected.post_rekey_delivery_percent < 95.0:
            return False
        return float(inp.seconds_since_last_rekey) >= interval_s

    def decide(self, inp: DecisionInput) -> SchedulerDecision:
        if not inp.telemetry_valid:
            # Deterministic fail-safe: keep current suite/aead, no forced rekey.
            current_suite_cfg = get_suite(inp.current_suite)
            return SchedulerDecision(
                selected_suite=inp.current_suite,
                selected_aead=inp.current_aead,
                target_nist_level=str(current_suite_cfg.get("nist_level", "L1")),
                rekey_required=False,
                recommended_rekey_interval_s=self._recommended_rekey_interval_s(inp),
                score=0.0,
                rationale=("telemetry_invalid_hold",),
            )

        candidates = self._build_candidates(inp)
        ranked = self._rank_candidates(inp, candidates)
        if not ranked:
            current_suite_cfg = get_suite(inp.current_suite)
            return SchedulerDecision(
                selected_suite=inp.current_suite,
                selected_aead=inp.current_aead,
                target_nist_level=str(current_suite_cfg.get("nist_level", "L1")),
                rekey_required=False,
                recommended_rekey_interval_s=self._recommended_rekey_interval_s(inp),
                score=999.0,
                rationale=("no_measured_candidates_available",),
            )

        best = ranked[0]
        rec_interval = self._recommended_rekey_interval_s(inp)
        rekey_required = self._should_rekey(inp, best.candidate, rec_interval)

        handshake_note = "direct_handshake_measured" if best.candidate.handshake_cost_ms is not None else "handshake_proxy_from_primitives"
        post_rekey_note = (
            f"post_rekey_delivery={best.candidate.post_rekey_delivery_percent:.2f}%"
            if best.candidate.post_rekey_delivery_percent is not None
            else "post_rekey_delivery=missing"
        )

        return SchedulerDecision(
            selected_suite=best.candidate.suite_id,
            selected_aead=best.candidate.aead_token,
            target_nist_level=best.candidate.nist_level,
            rekey_required=rekey_required,
            recommended_rekey_interval_s=rec_interval,
            score=best.score,
            rationale=(
                f"mode={inp.mission_mode}",
                f"crypto_cost={best.crypto_cost:.6f}",
                f"latency_ms={best.latency_cost_ms:.3f}",
                f"loss_pct={best.loss_cost:.3f}",
                handshake_note,
                post_rekey_note,
            ),
        )


def build_default_scheduler() -> BenchmarkDrivenSchedulerV3:
    """Factory helper for callers."""
    return BenchmarkDrivenSchedulerV3(BenchmarkCostProfile.from_artifacts())
