"""Stateless Verification Engine for Sparse Merkle Tree (SMT) Proofs.

Verifies inclusion and non-inclusion cryptographic proofs against target root hashes
in constant time O(depth) without needing access to full tree memory state.
"""

from __future__ import annotations

import hmac
import logging

try:
    from core.logging_utils import METRICS, get_logger
    logger = get_logger("smt.verifier")
except ImportError:
    logger = logging.getLogger("smt.verifier")
    METRICS = None

from smt.hash_engine import HASH_SIZE, TREE_HEIGHT, get_zero_hash, hash_leaf, hash_parent
from smt.operations import get_bit
from smt.proof import SMTProof


class SMTVerificationError(Exception):
    """Raised when an error occurs during proof verification execution."""

    pass


class SMTVerifier:
    """Stateless verifier for SMT proofs."""

    @staticmethod
    def verify(root_hash: bytes, proof: SMTProof, height: int = TREE_HEIGHT) -> bool:
        """Verifies whether an SMTProof correctly reconstructs the expected root hash.

        Args:
            root_hash: The 32-byte expected Merkle root hash.
            proof: The SMTProof object containing key, value_hash, siblings, and path_mask.
            height: Tree height depth (default 256).

        Returns:
            True if the computed root hash matches expected root_hash, False otherwise.
        """
        if (
            len(root_hash) != HASH_SIZE
            or len(proof.key) != HASH_SIZE
            or len(proof.value_hash) != HASH_SIZE
        ):
            return False

        if proof.value_hash != (b"\x00" * HASH_SIZE):
            curr_hash = hash_leaf(proof.key, proof.value_hash)
        else:
            curr_hash = get_zero_hash(0)

        sib_idx = 0
        # Reconstruct path bottom-up from depth 1 to height (level_idx 255 down to 0)
        for level_idx in reversed(range(height)):
            depth = height - level_idx
            bit = get_bit(proof.key, level_idx)

            has_sibling = (proof.path_mask >> level_idx) & 1
            if has_sibling:
                if sib_idx >= len(proof.siblings):
                    return False
                sib_hash = proof.siblings[sib_idx]
                sib_idx += 1
            else:
                sib_hash = get_zero_hash(depth - 1)

            if bit == 0:
                curr_hash = hash_parent(curr_hash, sib_hash)
            else:
                curr_hash = hash_parent(sib_hash, curr_hash)

        if METRICS:
            METRICS.counter("smt_verifications").inc()

        return hmac.compare_digest(curr_hash, root_hash)

    @staticmethod
    def verify_membership(root_hash: bytes, proof: SMTProof) -> bool:
        """Verifies a membership proof against the target root hash.

        Args:
            root_hash: Expected 32-byte root hash.
            proof: SMTProof object.

        Returns:
            True if valid membership proof, False otherwise.
        """
        if not proof.is_membership_proof():
            return False
        return SMTVerifier.verify(root_hash, proof)

    @staticmethod
    def verify_non_membership(root_hash: bytes, proof: SMTProof) -> bool:
        """Verifies a non-membership (exclusion) proof against the target root hash.

        Args:
            root_hash: Expected 32-byte root hash.
            proof: SMTProof object.

        Returns:
            True if valid non-membership proof, False otherwise.
        """
        if not proof.is_non_membership_proof():
            return False
        return SMTVerifier.verify(root_hash, proof)
