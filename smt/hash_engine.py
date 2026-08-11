"""Cryptographic Hash Engine for Sparse Merkle Tree (SMT).

Provides high-performance, domain-separated cryptographic hashing routines,
pre-computed zero-hash lookup tables up to tree height 256, and hash verification
utilities optimized for Python 3.11 on ARM hardware (Raspberry Pi 4).
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Final

# Cryptographic Constants
HASH_SIZE: Final[int] = 32  # 256-bit hash size in bytes
TREE_HEIGHT: Final[int] = 256  # Standard 256-bit key space depth

# Domain Separation Prefixes to prevent second-preimage attacks
PREFIX_LEAF: Final[bytes] = b"\x00"
PREFIX_PARENT: Final[bytes] = b"\x01"
PREFIX_KEY: Final[bytes] = b"\x02"


def _digest(data: bytes) -> bytes:
    """Internal helper to calculate a 32-byte BLAKE2b digest."""
    return hashlib.blake2b(data, digest_size=HASH_SIZE).digest()


def hash_key(identity: str | bytes) -> bytes:
    """Hashes an arbitrary drone identity string or byte payload into a 32-byte SMT key.

    Args:
        identity: The drone ID string or binary identifier to hash.

    Returns:
        A 32-byte hash representing the key in the Sparse Merkle Tree.
    """
    if isinstance(identity, str):
        raw_bytes = identity.encode("utf-8")
    else:
        raw_bytes = identity
    return _digest(PREFIX_KEY + raw_bytes)


def hash_leaf(key: bytes, value_hash: bytes) -> bytes:
    """Generates a domain-separated leaf hash for a key-value pair.

    Args:
        key: The 32-byte key location in the tree.
        value_hash: The 32-byte hash of the leaf value.

    Returns:
        A 32-byte leaf node hash.

    Raises:
        ValueError: If key or value_hash is not exactly 32 bytes.
    """
    if len(key) != HASH_SIZE:
        raise ValueError(f"Key must be exactly {HASH_SIZE} bytes, got {len(key)}")
    if len(value_hash) != HASH_SIZE:
        raise ValueError(f"Value hash must be exactly {HASH_SIZE} bytes, got {len(value_hash)}")
    return _digest(PREFIX_LEAF + key + value_hash)


def hash_parent(left_hash: bytes, right_hash: bytes) -> bytes:
    """Generates a domain-separated parent branch hash from left and right children hashes.

    Args:
        left_hash: The 32-byte hash of the left child node.
        right_hash: The 32-byte hash of the right child node.

    Returns:
        A 32-byte parent branch node hash.

    Raises:
        ValueError: If left_hash or right_hash is not exactly 32 bytes.
    """
    if len(left_hash) != HASH_SIZE:
        raise ValueError(f"Left hash must be exactly {HASH_SIZE} bytes, got {len(left_hash)}")
    if len(right_hash) != HASH_SIZE:
        raise ValueError(f"Right hash must be exactly {HASH_SIZE} bytes, got {len(right_hash)}")
    return _digest(PREFIX_PARENT + left_hash + right_hash)


def _precompute_zero_hashes() -> tuple[bytes, ...]:
    """Precomputes default zero hashes for empty subtrees from depth 0 up to depth 256.

    At depth 0 (empty leaf), the zero-hash is 32 bytes of zeros.
    At depth d > 0, zero_hash[d] = hash_parent(zero_hash[d-1], zero_hash[d-1]).

    Returns:
        A tuple of 257 precomputed zero hash byte strings.
    """
    zero_table: list[bytes] = [b"\x00" * HASH_SIZE]
    for d in range(1, TREE_HEIGHT + 1):
        prev_zero = zero_table[d - 1]
        zero_table.append(hash_parent(prev_zero, prev_zero))
    return tuple(zero_table)


# Immutable precomputed zero-hash array (depth 0 to 256)
ZERO_HASHES: Final[tuple[bytes, ...]] = _precompute_zero_hashes()


def get_zero_hash(depth: int) -> bytes:
    """Retrieves the precomputed default zero-hash for an empty subtree at a given depth.

    Args:
        depth: Tree depth level from 0 (leaf level) to 256 (root level).

    Returns:
        The 32-byte zero hash corresponding to the given depth.

    Raises:
        ValueError: If depth is out of the valid range [0, 256].
    """
    if not 0 <= depth <= TREE_HEIGHT:
        raise ValueError(f"Depth must be between 0 and {TREE_HEIGHT}, got {depth}")
    return ZERO_HASHES[depth]


def verify_leaf_hash(expected_hash: bytes, key: bytes, value_hash: bytes) -> bool:
    """Verifies whether a given leaf hash matches the recomputed leaf hash.

    Args:
        expected_hash: The 32-byte hash to verify against.
        key: The 32-byte leaf key.
        value_hash: The 32-byte leaf value hash.

    Returns:
        True if the recomputed leaf hash matches expected_hash, False otherwise.
    """
    if len(expected_hash) != HASH_SIZE or len(key) != HASH_SIZE or len(value_hash) != HASH_SIZE:
        return False
    computed = hash_leaf(key, value_hash)
    return hmac.compare_digest(computed, expected_hash)


def verify_parent_hash(expected_hash: bytes, left_hash: bytes, right_hash: bytes) -> bool:
    """Verifies whether a given parent hash matches the recomputed parent branch hash.

    Args:
        expected_hash: The 32-byte hash to verify against.
        left_hash: The 32-byte left child hash.
        right_hash: The 32-byte right child hash.

    Returns:
        True if the recomputed parent hash matches expected_hash, False otherwise.
    """
    if len(expected_hash) != HASH_SIZE or len(left_hash) != HASH_SIZE or len(right_hash) != HASH_SIZE:
        return False
    computed = hash_parent(left_hash, right_hash)
    return hmac.compare_digest(computed, expected_hash)


def verify_hash_format(hash_bytes: bytes) -> bool:
    """Checks if a given byte string is a valid 32-byte hash format.

    Args:
        hash_bytes: The byte string to validate.

    Returns:
        True if hash_bytes is instance of bytes and has length 32, False otherwise.
    """
    return isinstance(hash_bytes, (bytes, bytearray)) and len(hash_bytes) == HASH_SIZE
