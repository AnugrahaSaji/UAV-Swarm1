"""Domain-Specific UAV Identity Registry mapped to Sparse Merkle Tree.

Bridges high-level drone identity lifecycle operations (Drone ID, Public Keys, Roles, Hierarchy)
with low-level 32-byte SMT key-value tree state.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Dict, Optional

try:
    from core.logging_utils import METRICS, get_logger
    logger = get_logger("smt.registry")
except ImportError:
    logger = logging.getLogger("smt.registry")
    METRICS = None

from smt.hash_engine import HASH_SIZE, hash_key
from smt.proof import SMTProof
from smt.sparse_merkle_tree import SparseMerkleTree


class SMTRegistryError(Exception):
    """Base exception for Drone Registry operations."""

    pass


class DroneAlreadyRegisteredError(SMTRegistryError):
    """Raised when attempting to register a Drone ID that is already registered."""

    pass


class DroneNotFoundError(SMTRegistryError):
    """Raised when referencing a Drone ID that is not registered."""

    pass


@dataclass(slots=True, frozen=True)
class DroneLeaf:
    """Domain model representing a registered UAV identity inside the swarm.

    Attributes:
        drone_id: Unique string identifier for the drone.
        pubkey: Cryptographic public key byte string.
        role: Swarm role (e.g. 'leader', 'follower', 'relay').
        hierarchy_level: Swarm hierarchy tier (0 = Root Leader, 1 = Sub-leader, 2 = Member).
        epoch: State epoch number.
    """

    drone_id: str
    pubkey: bytes
    role: str = "follower"
    hierarchy_level: int = 2
    epoch: int = 0

    def compute_value_hash(self) -> bytes:
        """Computes the 32-byte hash of this drone leaf's identity payload."""
        payload = f"{self.drone_id}:{self.pubkey.hex()}:{self.role}:{self.hierarchy_level}:{self.epoch}".encode(
            "utf-8"
        )
        return hashlib.blake2b(payload, digest_size=HASH_SIZE).digest()


class DroneRegistry:
    """High-level identity manager mapping UAV swarm metadata to Sparse Merkle Tree state."""

    def __init__(self, tree: Optional[SparseMerkleTree] = None) -> None:
        """Initializes the DroneRegistry.

        Args:
            tree: Optional SparseMerkleTree instance. If None, a new tree is instantiated.
        """
        self.tree: SparseMerkleTree = tree if tree is not None else SparseMerkleTree()
        self._registered_drones: Dict[str, DroneLeaf] = {}

    def register_drone(
        self, drone_id: str, pubkey: bytes, role: str = "follower", hierarchy_level: int = 2
    ) -> bytes:
        """Registers a new drone identity in the SMT, returning the updated tree root hash.

        Args:
            drone_id: Unique string identifier for the drone.
            pubkey: Public key bytes.
            role: Swarm role string.
            hierarchy_level: Hierarchy tier integer.

        Returns:
            The new 32-byte root hash of the tree.
        """
        if drone_id in self._registered_drones:
            raise DroneAlreadyRegisteredError(f"Drone '{drone_id}' is already registered")

        key = hash_key(drone_id)
        leaf = DroneLeaf(
            drone_id=drone_id, pubkey=pubkey, role=role, hierarchy_level=hierarchy_level
        )
        val_hash = leaf.compute_value_hash()
        self._registered_drones[drone_id] = leaf
        if METRICS:
            METRICS.counter("smt_drone_registrations").inc()
        logger.info("Registered drone %s in SMT registry.", drone_id)
        return self.tree.update(key, val_hash)

    def revoke_drone(self, drone_id: str) -> bytes:
        """Revokes a drone identity from the SMT, resetting its leaf to empty and returning the root hash.

        Args:
            drone_id: Unique string identifier of the drone to revoke.

        Returns:
            The new 32-byte root hash of the tree.
        """
        if drone_id not in self._registered_drones:
            raise DroneNotFoundError(f"Drone '{drone_id}' not found in registry")

        key = hash_key(drone_id)
        del self._registered_drones[drone_id]
        if METRICS:
            METRICS.counter("smt_drone_revocations").inc()
        logger.warning("Revoked drone %s from SMT registry.", drone_id)
        return self.tree.delete(key)

    def update_drone(
        self, drone_id: str, pubkey: bytes, role: str = "follower", hierarchy_level: int = 2
    ) -> bytes:
        """Updates an existing drone's keys or roles in the SMT.

        Args:
            drone_id: Unique string identifier for the drone.
            pubkey: Updated public key bytes.
            role: Updated role string.
            hierarchy_level: Updated hierarchy tier.

        Returns:
            The new 32-byte root hash of the tree.
        """
        if drone_id in self._registered_drones:
            del self._registered_drones[drone_id]
        return self.register_drone(drone_id, pubkey, role, hierarchy_level)

    def get_root(self) -> bytes:
        """Returns the current 32-byte root hash of the underlying SMT."""
        return self.tree.root

    def prove_membership(self, drone_id: str, epoch: int = 0, nonce: str = "") -> SMTProof:
        """Generates an inclusion proof of authorization for a registered drone.

        Args:
            drone_id: Unique string identifier for the drone.
            epoch: Optional epoch timestamp/counter.
            nonce: Optional nonce string.

        Returns:
            An SMTProof object proving drone membership.
        """
        if drone_id not in self._registered_drones:
            raise DroneNotFoundError(f"Drone '{drone_id}' not registered")

        key = hash_key(drone_id)
        return self.tree.create_proof(key, epoch=epoch, nonce=nonce)
