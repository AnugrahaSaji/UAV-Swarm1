"""Nonce generation and validation helpers."""

from __future__ import annotations

import secrets
from typing import Dict, Set


class NonceManager:
    def __init__(self) -> None:
        self._used: Set[str] = set()

    def generate(self) -> str:
        nonce = secrets.token_hex(8)
        self._used.add(nonce)
        return nonce

    def is_used(self, nonce: str) -> bool:
        return nonce in self._used
