"""Differential State Synchronization Subsystem for Sparse Merkle Tree (SMT).

Computes lightweight delta patches (SMTSyncPatch) between swarm state roots
and applies state diffs for bandwidth-constrained UAV RF communications.
"""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from typing import List, Tuple

from smt.hash_engine import HASH_SIZE
from smt.node import LeafNode
from smt.sparse_merkle_tree import SparseMerkleTree


class SMTSyncError(Exception):
    """Base exception for SMT state synchronization errors."""

    pass


class SMTBaseRootMismatchError(SMTSyncError):
    """Raised when attempting to apply a patch whose base_root does not match the local tree root."""

    pass


@dataclass(slots=True, frozen=True)
class SMTSyncPatch:
    """Represents a compact differential state update patch between two SMT root hashes.

    Attributes:
        base_root: 32-byte root hash of the baseline state.
        target_root: 32-byte root hash after applying updates.
        mutated_leaves: Tuple of (key, value_hash) pairs representing modified or deleted leaves.
        epoch: Epoch timestamp or number.
    """

    base_root: bytes
    target_root: bytes
    mutated_leaves: Tuple[Tuple[bytes, bytes], ...]
    epoch: int = 0

    def serialize(self) -> bytes:
        """Serializes the SMTSyncPatch object into a compact binary byte string.

        Returns:
            Serialized patch binary byte string.
        """
        buf = bytearray()
        buf.extend(self.base_root)
        buf.extend(self.target_root)
        buf.extend(self.epoch.to_bytes(8, byteorder="big"))
        buf.extend(len(self.mutated_leaves).to_bytes(2, byteorder="big"))

        for key, val_hash in self.mutated_leaves:
            if len(key) != HASH_SIZE or len(val_hash) != HASH_SIZE:
                raise SMTSyncError(f"Mutated leaf key and value_hash must be {HASH_SIZE} bytes")
            buf.extend(key)
            buf.extend(val_hash)

        return bytes(buf)

    @classmethod
    def deserialize(cls, data: bytes) -> SMTSyncPatch:
        """Deserializes a binary byte string back into an SMTSyncPatch object.

        Args:
            data: Binary byte string.

        Returns:
            SMTSyncPatch instance.
        """
        min_size = HASH_SIZE * 2 + 8 + 2  # 74 bytes minimum
        if len(data) < min_size:
            raise SMTSyncError(f"Patch buffer too short: {len(data)} < {min_size}")

        offset = 0
        base_root = data[offset : offset + HASH_SIZE]
        offset += HASH_SIZE

        target_root = data[offset : offset + HASH_SIZE]
        offset += HASH_SIZE

        epoch = int.from_bytes(data[offset : offset + 8], byteorder="big")
        offset += 8

        num_leaves = int.from_bytes(data[offset : offset + 2], byteorder="big")
        offset += 2

        expected_rem = num_leaves * (HASH_SIZE * 2)
        if len(data) - offset != expected_rem:
            raise SMTSyncError(
                f"Patch payload length mismatch: {len(data) - offset} != {expected_rem}"
            )

        mutated: List[Tuple[bytes, bytes]] = []
        for _ in range(num_leaves):
            k = data[offset : offset + HASH_SIZE]
            offset += HASH_SIZE
            v = data[offset : offset + HASH_SIZE]
            offset += HASH_SIZE
            mutated.append((k, v))

        return cls(
            base_root=base_root,
            target_root=target_root,
            mutated_leaves=tuple(mutated),
            epoch=epoch,
        )


class SMTSyncManager:
    """Manages delta state calculation and patch application across swarm drones."""

    @staticmethod
    def compute_diff(tree: SparseMerkleTree, base_root: bytes) -> SMTSyncPatch:
        """Computes a differential state patch between a base root and the tree's current root.

        Args:
            tree: Local SparseMerkleTree instance.
            base_root: Target peer baseline 32-byte root hash.

        Returns:
            An SMTSyncPatch containing modified leaf key-value pairs.
        """
        mutated: List[Tuple[bytes, bytes]] = []

        for node in tree.nodes.values():
            if isinstance(node, LeafNode):
                mutated.append((node.key, node.value_hash))

        return SMTSyncPatch(
            base_root=base_root,
            target_root=tree.root,
            mutated_leaves=tuple(mutated),
            epoch=0,
        )

    @staticmethod
    def apply_patch(tree: SparseMerkleTree, patch: SMTSyncPatch) -> bytes:
        """Applies a differential SMTSyncPatch to the local SparseMerkleTree instance.

        Args:
            tree: Local SparseMerkleTree instance.
            patch: SMTSyncPatch object to apply.

        Returns:
            The new 32-byte root hash after patch application.

        Raises:
            SMTBaseRootMismatchError: If base_root does not match local tree root.
        """
        if not hmac.compare_digest(tree.root, patch.base_root):
            raise SMTBaseRootMismatchError(
                f"Local root {tree.root.hex()} does not match patch base root {patch.base_root.hex()}"
            )

        for key, val_hash in patch.mutated_leaves:
            if val_hash == (b"\x00" * HASH_SIZE):
                tree.delete(key)
            else:
                tree.update(key, val_hash)

        if not hmac.compare_digest(tree.root, patch.target_root):
            raise SMTSyncError(
                f"Post-patch root {tree.root.hex()} does not match target root {patch.target_root.hex()}"
            )

        return tree.root
