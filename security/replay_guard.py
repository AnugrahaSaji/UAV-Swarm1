"""Replay protection helpers for swarm and SMT extension messages."""

from __future__ import annotations

from typing import Dict, Set


class ReplayGuard:
    def __init__(self) -> None:
        self._seen: Set[tuple[str, str, int]] = set()

    def is_replay(self, *, drone_id: str, nonce: str, epoch: int) -> bool:
        key = (drone_id, nonce, epoch)
        if key in self._seen:
            return True
        self._seen.add(key)
        return False
