"""Compact Merkle Proof Dataclass and Serialization for SMT.

Consolidates inclusion and non-inclusion proof creation, compact binary serialization,
and deserialization logic optimized for low-bandwidth UAV RF transmission.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Tuple

from smt.hash_engine import HASH_SIZE

if TYPE_CHECKING:
    from smt.sparse_merkle_tree import SparseMerkleTree


class SMTProofError(Exception):
    """Base exception for Sparse Merkle Tree proof operations."""

    pass


class SMTProofSerializationError(SMTProofError):
    """Raised when binary serialization or deserialization of an SMTProof fails."""

    pass


class SMTProofValidationError(SMTProofError):
    """Raised when an SMTProof instance fails structural validation."""

    pass


@dataclass(slots=True, frozen=True)
class SMTProof:
    """Compact Sparse Merkle Tree proof object.

    Attributes:
        key: The 32-byte target key being proven.
        value_hash: The 32-byte leaf value hash (or 32 bytes of zeros for non-membership).
        siblings: Tuple of non-zero 32-byte sibling hashes along the Merkle path.
        path_mask: Bitmask encoding which depths contain non-zero sibling hashes.
        root_hash: Expected 32-byte root hash of the tree.
        epoch: Epoch timestamp or counter.
        nonce: Cryptographic nonce for replay protection.
    """

    key: bytes
    value_hash: bytes
    siblings: Tuple[bytes, ...]
    path_mask: int
    root_hash: bytes
    epoch: int = 0
    nonce: str = ""

    def __post_init__(self) -> None:
        if len(self.key) != HASH_SIZE:
            raise ValueError(f"Proof key must be {HASH_SIZE} bytes, got {len(self.key)}")
        if len(self.value_hash) != HASH_SIZE:
            raise ValueError(
                f"Proof value_hash must be {HASH_SIZE} bytes, got {len(self.value_hash)}"
            )
        if len(self.root_hash) != HASH_SIZE:
            raise ValueError(
                f"Proof root_hash must be {HASH_SIZE} bytes, got {len(self.root_hash)}"
            )

    def is_membership_proof(self) -> bool:
        """Returns True if this is a proof of key inclusion (value_hash != zeros)."""
        return self.value_hash != (b"\x00" * HASH_SIZE)

    def is_non_membership_proof(self) -> bool:
        """Returns True if this is a proof of key exclusion (value_hash == zeros)."""
        return self.value_hash == (b"\x00" * HASH_SIZE)

    def serialize(self) -> bytes:
        """Serializes the SMTProof object into a compact binary byte payload for transmission.

        Returns:
            Binary byte string representation of the proof.
        """
        nonce_bytes = self.nonce.encode("utf-8")
        buf = bytearray()
        buf.extend(self.key)
        buf.extend(self.value_hash)
        buf.extend(self.root_hash)
        buf.extend(self.path_mask.to_bytes(HASH_SIZE, byteorder="big"))
        buf.extend(self.epoch.to_bytes(8, byteorder="big"))
        buf.extend(len(nonce_bytes).to_bytes(2, byteorder="big"))
        buf.extend(nonce_bytes)
        buf.extend(len(self.siblings).to_bytes(2, byteorder="big"))
        for sib in self.siblings:
            if len(sib) != HASH_SIZE:
                raise SMTProofSerializationError(f"Sibling hash must be {HASH_SIZE} bytes")
            buf.extend(sib)
        return bytes(buf)

    @classmethod
    def deserialize(cls, data: bytes) -> SMTProof:
        """Deserializes a binary byte payload back into an SMTProof object.

        Args:
            data: Binary byte payload.

        Returns:
            Reconstructed SMTProof object.
        """
        min_size = HASH_SIZE * 4 + 8 + 2 + 2  # 140 bytes minimum
        if len(data) < min_size:
            raise SMTProofSerializationError(
                f"Data buffer too short for SMTProof: {len(data)} < {min_size}"
            )

        offset = 0
        key = data[offset : offset + HASH_SIZE]
        offset += HASH_SIZE

        value_hash = data[offset : offset + HASH_SIZE]
        offset += HASH_SIZE

        root_hash = data[offset : offset + HASH_SIZE]
        offset += HASH_SIZE

        path_mask = int.from_bytes(data[offset : offset + HASH_SIZE], byteorder="big")
        offset += HASH_SIZE

        epoch = int.from_bytes(data[offset : offset + 8], byteorder="big")
        offset += 8

        nonce_len = int.from_bytes(data[offset : offset + 2], byteorder="big")
        offset += 2

        if len(data) < offset + nonce_len + 2:
            raise SMTProofSerializationError("Data buffer truncated reading nonce")

        nonce = data[offset : offset + nonce_len].decode("utf-8")
        offset += nonce_len

        num_siblings = int.from_bytes(data[offset : offset + 2], byteorder="big")
        offset += 2

        expected_remaining = num_siblings * HASH_SIZE
        if len(data) - offset != expected_remaining:
            raise SMTProofSerializationError(
                f"Data length mismatch for siblings: {len(data) - offset} != {expected_remaining}"
            )

        siblings: List[bytes] = []
        for _ in range(num_siblings):
            siblings.append(data[offset : offset + HASH_SIZE])
            offset += HASH_SIZE

        return cls(
            key=key,
            value_hash=value_hash,
            siblings=tuple(siblings),
            path_mask=path_mask,
            root_hash=root_hash,
            epoch=epoch,
            nonce=nonce,
        )


def generate_proof(tree: SparseMerkleTree, key: bytes) -> SMTProof:
    """Generates an SMTProof for a key from an active SparseMerkleTree instance.

    Args:
        tree: The SparseMerkleTree state instance.
        key: The 32-byte key location.

    Returns:
        Generated SMTProof object.
    """
    return tree.create_proof(key)


def generate_membership_proof(
    tree: SparseMerkleTree, key: bytes, epoch: int = 0, nonce: str = ""
) -> SMTProof:
    """Convenience helper to generate an explicit membership proof for an active leaf key."""
    return tree.create_proof(key, epoch=epoch, nonce=nonce)


def generate_non_membership_proof(
    tree: SparseMerkleTree, key: bytes, epoch: int = 0, nonce: str = ""
) -> SMTProof:
    """Convenience helper to generate an explicit non-membership proof for an unassigned key."""
    return tree.create_proof(key, epoch=epoch, nonce=nonce)
