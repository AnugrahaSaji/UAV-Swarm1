"""Trust validation helpers for swarm messages."""

from __future__ import annotations

from typing import Dict, Any


class TrustValidator:
    def validate(self, payload: Dict[str, Any], *, trust_score: float) -> bool:
        return trust_score >= 0.5 and bool(payload.get("drone_id"))
