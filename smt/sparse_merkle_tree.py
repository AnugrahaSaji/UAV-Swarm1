"""Core Sparse Merkle Tree (SMT) Container.

Provides the primary stateful tree object managing active nodes, root state,
and delegating path mutations to `operations.py` and proof generation to `proof.py`.
Optimized for Raspberry Pi 4 (Python 3.11).
"""

from __future__ import annotations

from typing import Dict

from smt.hash_engine import HASH_SIZE, TREE_HEIGHT, get_zero_hash
from smt.node import SMTNode
from smt.operations import op_collect_path, op_delete, op_get, op_update
from smt.proof import SMTProof


class SMTError(Exception):
    """Base exception for all Sparse Merkle Tree errors."""

    pass


class SMTKeyNotFoundError(SMTError):
    """Raised when a requested key is not present in the SMT."""

    pass


class SMTInvalidNodeError(SMTError):
    """Raised when an invalid node or hash format is encountered."""

    pass


class SparseMerkleTree:
    """Stateful Sparse Merkle Tree implementation storing non-zero nodes and maintaining root state.

    Attributes:
        height: Tree depth (default 256).
        nodes: Dictionary mapping node hashes to SMTNode objects.
    """

    def __init__(self, height: int = TREE_HEIGHT) -> None:
        """Initializes an empty Sparse Merkle Tree at the given height.

        Args:
            height: Tree height depth (default 256).
        """
        if height != TREE_HEIGHT:
            raise ValueError(f"Only height {TREE_HEIGHT} is supported, got {height}")
        self.height: int = height
        self.nodes: Dict[bytes, SMTNode] = {}
        self._root_hash: bytes = get_zero_hash(self.height)

    @property
    def root(self) -> bytes:
        """Returns the current 32-byte root hash of the Sparse Merkle Tree."""
        return self._root_hash

    def get(self, key: bytes) -> bytes:
        """Retrieves the value hash associated with the specified key.

        Args:
            key: 32-byte key location in the tree.

        Returns:
            The 32-byte value hash if found, or 32 bytes of zeros if key does not exist.
        """
        return op_get(self.nodes, self._root_hash, key, self.height)

    def update(self, key: bytes, value_hash: bytes) -> bytes:
        """Inserts or updates a key-value pair in the tree, returning the new root hash.

        Args:
            key: 32-byte leaf key location.
            value_hash: 32-byte leaf value hash.

        Returns:
            The new 32-byte root hash of the tree.
        """
        self._root_hash = op_update(self.nodes, self._root_hash, key, value_hash, self.height)
        return self._root_hash

    def delete(self, key: bytes) -> bytes:
        """Deletes a key from the tree, updating empty branches and returning the new root hash.

        Args:
            key: 32-byte key location to delete.

        Returns:
            The new 32-byte root hash of the tree.
        """
        self._root_hash = op_delete(self.nodes, self._root_hash, key, self.height)
        return self._root_hash

    def create_proof(self, key: bytes, epoch: int = 0, nonce: str = "") -> SMTProof:
        """Generates a compact Merkle inclusion/non-inclusion proof for the specified key.

        Args:
            key: 32-byte key location.
            epoch: Optional epoch number.
            nonce: Optional replay prevention nonce string.

        Returns:
            An SMTProof object containing sibling hashes and path bitmask.
        """
        val_hash, siblings, path_mask = op_collect_path(
            self.nodes, self._root_hash, key, self.height
        )
        return SMTProof(
            key=key,
            value_hash=val_hash,
            siblings=tuple(siblings),
            path_mask=path_mask,
            root_hash=self._root_hash,
            epoch=epoch,
            nonce=nonce,
        )
