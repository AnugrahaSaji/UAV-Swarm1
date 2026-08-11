"""Stateless Sparse Merkle Tree (SMT) Path Traversal, Mutation, and Bitwise Algorithms.

Provides pure functional routines for searching, inserting, updating, deleting nodes,
and generating compressed proofs in the node store of a Sparse Merkle Tree (Nervos SMT inspired).
Optimized for low RAM consumption and fast ARM bitwise operations (Raspberry Pi 4).
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from smt.hash_engine import (
    HASH_SIZE,
    TREE_HEIGHT,
    get_zero_hash,
)
from smt.node import InternalNode, LeafNode, SMTNode


class SMTOperationError(Exception):
    """Raised when an error occurs during an SMT path mutation or traversal operation."""

    pass


def get_bit(key: bytes, bit_index: int) -> int:
    """Extracts a single bit (0 or 1) at bit_index (0 to 255) from a 32-byte key.

    Bit index 0 corresponds to the Most Significant Bit (MSB) of key[0].
    Bit index 255 corresponds to the Least Significant Bit (LSB) of key[31].

    Args:
        key: 32-byte key string.
        bit_index: Bit position from 0 to 255.

    Returns:
        0 or 1.
    """
    byte_idx = bit_index // 8
    bit_offset = 7 - (bit_index % 8)
    return (key[byte_idx] >> bit_offset) & 1


def op_get(
    store: Dict[bytes, SMTNode], root_hash: bytes, key: bytes, height: int = TREE_HEIGHT
) -> bytes:
    """Traverses the SMT from root to leaf to retrieve the value hash for a given key.

    Args:
        store: Dictionary mapping node hashes to SMTNode instances.
        root_hash: Current 32-byte root hash of the tree.
        key: 32-byte target key location.
        height: Tree depth (default 256).

    Returns:
        The 32-byte value hash if key exists, or 32 bytes of zeros if non-existent.

    Raises:
        ValueError: If key format is invalid.
    """
    if len(key) != HASH_SIZE:
        raise ValueError(f"Key must be exactly {HASH_SIZE} bytes, got {len(key)}")

    curr_hash = root_hash
    for depth in range(height, 0, -1):
        if curr_hash == get_zero_hash(depth):
            return b"\x00" * HASH_SIZE

        node = store.get(curr_hash)
        if node is None or node.is_empty:
            return b"\x00" * HASH_SIZE

        if node.is_leaf:
            assert isinstance(node, LeafNode)
            return node.value_hash if node.key == key else b"\x00" * HASH_SIZE

        assert isinstance(node, InternalNode)
        bit = get_bit(key, height - depth)
        curr_hash = node.right_hash if bit else node.left_hash

    if curr_hash == get_zero_hash(0):
        return b"\x00" * HASH_SIZE

    node = store.get(curr_hash)
    if isinstance(node, LeafNode) and node.key == key:
        return node.value_hash

    return b"\x00" * HASH_SIZE


def op_update(
    store: Dict[bytes, SMTNode],
    root_hash: bytes,
    key: bytes,
    value_hash: bytes,
    height: int = TREE_HEIGHT,
) -> bytes:
    """Inserts or updates a key-value hash pair along the tree path, updating parent hashes.

    If value_hash is 32 bytes of zeros, delegates to `op_delete`.

    Args:
        store: Dictionary mapping node hashes to SMTNode instances.
        root_hash: Current 32-byte root hash of the tree.
        key: 32-byte target key location.
        value_hash: 32-byte value hash payload.
        height: Tree depth (default 256).

    Returns:
        The new 32-byte root hash after update.
    """
    if len(key) != HASH_SIZE:
        raise ValueError(f"Key must be exactly {HASH_SIZE} bytes, got {len(key)}")
    if len(value_hash) != HASH_SIZE:
        raise ValueError(f"Value hash must be exactly {HASH_SIZE} bytes, got {len(value_hash)}")

    if value_hash == (b"\x00" * HASH_SIZE):
        return op_delete(store, root_hash, key, height)

    # 1. Collect siblings along path from depth height down to 1
    siblings: List[bytes] = []
    curr_hash = root_hash

    for depth in range(height, 0, -1):
        bit = get_bit(key, height - depth)
        if curr_hash == get_zero_hash(depth):
            siblings.append(get_zero_hash(depth - 1))
        else:
            node = store.get(curr_hash)
            if isinstance(node, InternalNode):
                if bit == 0:
                    siblings.append(node.right_hash)
                    curr_hash = node.left_hash
                else:
                    siblings.append(node.left_hash)
                    curr_hash = node.right_hash
            else:
                siblings.append(get_zero_hash(depth - 1))
                curr_hash = get_zero_hash(depth - 1)

    # 2. Create LeafNode at depth 0
    leaf = LeafNode(key, value_hash)
    curr_hash = leaf.hash
    store[curr_hash] = leaf

    # 3. Rebuild tree path bottom-up from depth 1 to height
    for i, sib in enumerate(reversed(siblings)):
        depth = i + 1
        bit = get_bit(key, height - depth)
        if bit == 0:
            left_h, right_h = curr_hash, sib
        else:
            left_h, right_h = sib, curr_hash

        branch = InternalNode(left_h, right_h)
        curr_hash = branch.hash
        if curr_hash != get_zero_hash(depth):
            store[curr_hash] = branch

    return curr_hash


def op_delete(
    store: Dict[bytes, SMTNode], root_hash: bytes, key: bytes, height: int = TREE_HEIGHT
) -> bytes:
    """Deletes a key from the node store and prunes empty branch nodes up to the root.

    Args:
        store: Dictionary mapping node hashes to SMTNode instances.
        root_hash: Current 32-byte root hash of the tree.
        key: 32-byte key location to delete.
        height: Tree depth (default 256).

    Returns:
        The new 32-byte root hash after deletion.
    """
    if len(key) != HASH_SIZE:
        raise ValueError(f"Key must be exactly {HASH_SIZE} bytes, got {len(key)}")

    siblings: List[bytes] = []
    curr_hash = root_hash

    for depth in range(height, 0, -1):
        bit = get_bit(key, height - depth)
        if curr_hash == get_zero_hash(depth):
            siblings.append(get_zero_hash(depth - 1))
        else:
            node = store.get(curr_hash)
            if isinstance(node, InternalNode):
                if bit == 0:
                    siblings.append(node.right_hash)
                    curr_hash = node.left_hash
                else:
                    siblings.append(node.left_hash)
                    curr_hash = node.right_hash
            else:
                siblings.append(get_zero_hash(depth - 1))
                curr_hash = get_zero_hash(depth - 1)

    curr_hash = get_zero_hash(0)

    for i, sib in enumerate(reversed(siblings)):
        depth = i + 1
        bit = get_bit(key, height - depth)
        if bit == 0:
            left_h, right_h = curr_hash, sib
        else:
            left_h, right_h = sib, curr_hash

        if left_h == get_zero_hash(depth - 1) and right_h == get_zero_hash(depth - 1):
            curr_hash = get_zero_hash(depth)
        else:
            branch = InternalNode(left_h, right_h)
            curr_hash = branch.hash
            store[curr_hash] = branch

    return curr_hash


def op_collect_path(
    store: Dict[bytes, SMTNode], root_hash: bytes, key: bytes, height: int = TREE_HEIGHT
) -> Tuple[bytes, List[bytes], int]:
    """Collects path information for proof generation.

    Args:
        store: Node store dictionary.
        root_hash: Current root hash.
        key: Target key.
        height: Tree depth.

    Returns:
        Tuple of (value_hash, siblings_list, path_mask).
    """
    value_hash = op_get(store, root_hash, key, height)
    siblings: List[bytes] = []
    non_zero_siblings: List[bytes] = []
    path_mask = 0

    curr_hash = root_hash
    for depth in range(height, 0, -1):
        bit = get_bit(key, height - depth)
        sib_hash = get_zero_hash(depth - 1)

        if curr_hash != get_zero_hash(depth):
            node = store.get(curr_hash)
            if isinstance(node, InternalNode):
                if bit == 0:
                    sib_hash = node.right_hash
                    curr_hash = node.left_hash
                else:
                    sib_hash = node.left_hash
                    curr_hash = node.right_hash
            else:
                curr_hash = get_zero_hash(depth - 1)

        level_idx = height - depth  # 0 to 255
        if sib_hash != get_zero_hash(depth - 1):
            non_zero_siblings.append(sib_hash)
            path_mask |= 1 << level_idx

    return value_hash, non_zero_siblings, path_mask
