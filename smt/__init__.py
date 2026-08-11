"""Sparse Merkle Tree (SMT) Module for UAV Swarm Authentication & Integrity.

Provides lightweight, production-grade SMT identity management, compact proof generation,
stateless verification, state epoch tracking, and delta sync optimized for Raspberry Pi 4.
"""

from __future__ import annotations

from smt.hash_engine import (
    HASH_SIZE,
    TREE_HEIGHT,
    get_zero_hash,
    hash_key,
    hash_leaf,
    hash_parent,
    verify_leaf_hash,
    verify_parent_hash,
)
from smt.integrity import (
    SMTCorruptedNodeError,
    SMTIntegrityChecker,
    SMTIntegrityError,
)
from smt.node import (
    EmptyNode,
    InternalNode,
    LeafNode,
    SMTNode,
)
from smt.operations import (
    SMTOperationError,
    op_delete,
    op_get,
    op_update,
)
from smt.proof import (
    SMTProof,
    SMTProofError,
    SMTProofSerializationError,
    SMTProofValidationError,
    generate_membership_proof,
    generate_non_membership_proof,
    generate_proof,
)
from smt.registry import (
    DroneAlreadyRegisteredError,
    DroneLeaf,
    DroneNotFoundError,
    DroneRegistry,
    SMTRegistryError,
)
from smt.root_manager import (
    RootRecord,
    SMTInvalidEpochError,
    SMTRootError,
    SMTRootManager,
    SMTStaleRootError,
)
from smt.sparse_merkle_tree import (
    SMTError,
    SMTInvalidNodeError,
    SMTKeyNotFoundError,
    SparseMerkleTree,
)
from smt.sync import (
    SMTBaseRootMismatchError,
    SMTSyncError,
    SMTSyncManager,
    SMTSyncPatch,
)
from smt.verifier import (
    SMTVerificationError,
    SMTVerifier,
)

__all__ = [
    # Constants
    "HASH_SIZE",
    "TREE_HEIGHT",
    # Core Tree Container & Exceptions
    "SparseMerkleTree",
    "SMTError",
    "SMTKeyNotFoundError",
    "SMTInvalidNodeError",
    # Hash Engine
    "hash_key",
    "hash_leaf",
    "hash_parent",
    "get_zero_hash",
    "verify_leaf_hash",
    "verify_parent_hash",
    # Node Structures
    "SMTNode",
    "LeafNode",
    "InternalNode",
    "EmptyNode",
    # Operations
    "op_get",
    "op_update",
    "op_delete",
    "SMTOperationError",
    # Proofs
    "SMTProof",
    "SMTProofError",
    "SMTProofSerializationError",
    "SMTProofValidationError",
    "generate_proof",
    "generate_membership_proof",
    "generate_non_membership_proof",
    # Verifier
    "SMTVerifier",
    "SMTVerificationError",
    # Domain Registry
    "DroneRegistry",
    "DroneLeaf",
    "SMTRegistryError",
    "DroneAlreadyRegisteredError",
    "DroneNotFoundError",
    # Root Manager
    "SMTRootManager",
    "RootRecord",
    "SMTRootError",
    "SMTStaleRootError",
    "SMTInvalidEpochError",
    # Integrity Auditor
    "SMTIntegrityChecker",
    "SMTIntegrityError",
    "SMTCorruptedNodeError",
    # Sync Subsystem
    "SMTSyncManager",
    "SMTSyncPatch",
    "SMTSyncError",
    "SMTBaseRootMismatchError",
]
