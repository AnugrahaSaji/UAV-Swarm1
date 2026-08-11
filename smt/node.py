"""Node Data Structures for Sparse Merkle Tree (SMT).

Provides memory-compact, slotted node implementations for LeafNode, InternalNode (BranchNode),
and EmptyNode adhering to a common SMTNode abstract interface.
Optimized for low RAM consumption on Raspberry Pi 4 using Python 3.11 dataclass slots.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from smt.hash_engine import (
    HASH_SIZE,
    get_zero_hash,
    hash_leaf,
    hash_parent,
)


class SMTNode(ABC):
    """Abstract Base Class defining the common interface for all Sparse Merkle Tree nodes."""

    @property
    @abstractmethod
    def hash(self) -> bytes:
        """Returns the 32-byte cryptographic hash of this node."""
        ...

    @property
    @abstractmethod
    def is_leaf(self) -> bool:
        """Returns True if this node is a LeafNode, False otherwise."""
        ...

    @property
    @abstractmethod
    def is_empty(self) -> bool:
        """Returns True if this node represents an empty subtree (EmptyNode), False otherwise."""
        ...


@dataclass(slots=True, frozen=True)
class LeafNode(SMTNode):
    """Represents a non-empty leaf node in the Sparse Merkle Tree.

    Attributes:
        key: The 32-byte key indicating the leaf position.
        value_hash: The 32-byte hash of the leaf value payload (e.g. drone identity/pubkey hash).
    """

    key: bytes
    value_hash: bytes

    def __post_init__(self) -> None:
        if len(self.key) != HASH_SIZE:
            raise ValueError(f"LeafNode key must be exactly {HASH_SIZE} bytes, got {len(self.key)}")
        if len(self.value_hash) != HASH_SIZE:
            raise ValueError(
                f"LeafNode value_hash must be exactly {HASH_SIZE} bytes, got {len(self.value_hash)}"
            )

    @property
    def hash(self) -> bytes:
        """Computes and returns the domain-separated leaf hash for this node."""
        return hash_leaf(self.key, self.value_hash)

    @property
    def is_leaf(self) -> bool:
        """Returns True since this is a LeafNode."""
        return True

    @property
    def is_empty(self) -> bool:
        """Returns False since this node contains active leaf data."""
        return False


@dataclass(slots=True, frozen=True)
class InternalNode(SMTNode):
    """Represents an internal branch node in the Sparse Merkle Tree connecting left and right subtrees.

    Attributes:
        left_hash: 32-byte hash of the left child node.
        right_hash: 32-byte hash of the right child node.
        left_child: Optional reference to the left child node object.
        right_child: Optional reference to the right child node object.
    """

    left_hash: bytes
    right_hash: bytes
    left_child: Optional[SMTNode] = None
    right_child: Optional[SMTNode] = None

    def __post_init__(self) -> None:
        if len(self.left_hash) != HASH_SIZE:
            raise ValueError(
                f"InternalNode left_hash must be exactly {HASH_SIZE} bytes, got {len(self.left_hash)}"
            )
        if len(self.right_hash) != HASH_SIZE:
            raise ValueError(
                f"InternalNode right_hash must be exactly {HASH_SIZE} bytes, got {len(self.right_hash)}"
            )

    @property
    def hash(self) -> bytes:
        """Computes and returns the parent branch hash combining left_hash and right_hash."""
        return hash_parent(self.left_hash, self.right_hash)

    @property
    def is_leaf(self) -> bool:
        """Returns False since this is an internal branch node."""
        return False

    @property
    def is_empty(self) -> bool:
        """Returns False since this branch contains non-zero child subtrees."""
        return False


@dataclass(slots=True, frozen=True)
class EmptyNode(SMTNode):
    """Represents an empty subtree at a specific depth in the Sparse Merkle Tree.

    Zero-memory node abstraction that references precomputed default zero-hashes.

    Attributes:
        depth: The depth level in the tree (0 = leaf level, 256 = root level).
    """

    depth: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.depth <= 256:
            raise ValueError(f"EmptyNode depth must be between 0 and 256, got {self.depth}")

    @property
    def hash(self) -> bytes:
        """Returns the precomputed zero hash corresponding to this node's depth."""
        return get_zero_hash(self.depth)

    @property
    def is_leaf(self) -> bool:
        """Returns False since this represents an empty subtree."""
        return False

    @property
    def is_empty(self) -> bool:
        """Returns True since this represents an empty node."""
        return True
