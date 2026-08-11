"""Root Hash and Epoch State Management for SMT.

Manages root versioning, historical root tracking in a memory-capped ring buffer,
and epoch shift validations across the UAV swarm.
"""

from __future__ import annotations

import hmac
from collections import deque
from dataclasses import dataclass
from typing import Deque

from smt.hash_engine import HASH_SIZE, get_zero_hash


class SMTRootError(Exception):
    """Base exception for root management errors."""

    pass


class SMTStaleRootError(SMTRootError):
    """Raised when an un-recognized or expired root hash is presented."""

    pass


class SMTInvalidEpochError(SMTRootError):
    """Raised when an invalid epoch transition is attempted."""

    pass


@dataclass(slots=True, frozen=True)
class RootRecord:
    """Historical record of an SMT root state.

    Attributes:
        root_hash: 32-byte root hash.
        epoch: Epoch timestamp or number.
        nonce: Replay protection nonce.
    """

    root_hash: bytes
    epoch: int
    nonce: str = ""


class SMTRootManager:
    """Tracks active and historical SMT roots to manage epoch transition windows across the swarm."""

    def __init__(self, history_capacity: int = 50) -> None:
        """Initializes SMTRootManager with a fixed-capacity ring buffer for history.

        Args:
            history_capacity: Maximum number of historical roots to retain (default 50).
        """
        self.capacity: int = history_capacity
        self._current_root: bytes = get_zero_hash(256)
        self._current_epoch: int = 0
        self._history: Deque[RootRecord] = deque(maxlen=self.capacity)

    @property
    def current_root(self) -> bytes:
        """Returns the active 32-byte SMT root hash."""
        return self._current_root

    @property
    def current_epoch(self) -> int:
        """Returns the current epoch number."""
        return self._current_epoch

    def commit_root(self, root_hash: bytes, epoch: int, nonce: str = "") -> None:
        """Commits a new root hash and advances the state epoch.

        Args:
            root_hash: 32-byte new root hash.
            epoch: Epoch number.
            nonce: Cryptographic nonce.

        Raises:
            ValueError: If root_hash format is invalid.
            SMTInvalidEpochError: If epoch goes backwards.
        """
        if len(root_hash) != HASH_SIZE:
            raise ValueError(f"Root hash must be {HASH_SIZE} bytes, got {len(root_hash)}")

        if epoch < self._current_epoch:
            raise SMTInvalidEpochError(
                f"Cannot regress epoch from {self._current_epoch} to {epoch}"
            )

        record = RootRecord(root_hash=root_hash, epoch=epoch, nonce=nonce)
        self._history.append(record)
        self._current_root = root_hash
        self._current_epoch = epoch

    def is_known_root(self, root_hash: bytes) -> bool:
        """Checks if a root hash matches the current root or any active historical root in the ring buffer.

        Args:
            root_hash: 32-byte root hash to query.

        Returns:
            True if recognized, False otherwise.
        """
        if len(root_hash) != HASH_SIZE:
            return False

        if hmac.compare_digest(self._current_root, root_hash):
            return True

        for rec in self._history:
            if hmac.compare_digest(rec.root_hash, root_hash):
                return True

        return False

    def verify_epoch_transition(
        self, old_root: bytes, new_root: bytes, expected_epoch: int
    ) -> bool:
        """Verifies if a transition from old_root to new_root is valid for the expected epoch.

        Args:
            old_root: 32-byte previous root hash.
            new_root: 32-byte proposed root hash.
            expected_epoch: Expected target epoch.

        Returns:
            True if transition is authorized, False otherwise.
        """
        if not self.is_known_root(old_root):
            return False
        return expected_epoch >= self._current_epoch
