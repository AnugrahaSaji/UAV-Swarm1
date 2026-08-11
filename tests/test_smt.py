"""Unit & Integration Test Suite for Sparse Merkle Tree (SMT) Module.

Tests hash engine, node representations, tree path operations, inclusion/non-inclusion proofs,
stateless proof verification, binary serialization, domain drone registry, root manager,
integrity diagnostics, and differential state sync.
"""

import sys
import unittest
from pathlib import Path

# Ensure smt package is discoverable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from smt import (
    DroneAlreadyRegisteredError,
    DroneNotFoundError,
    DroneRegistry,
    EmptyNode,
    InternalNode,
    LeafNode,
    SMTBaseRootMismatchError,
    SMTIntegrityChecker,
    SMTProof,
    SMTRootManager,
    SMTSyncManager,
    SMTSyncPatch,
    SMTVerificationError,
    SMTVerifier,
    SparseMerkleTree,
    get_zero_hash,
    hash_key,
    hash_leaf,
    hash_parent,
    verify_leaf_hash,
    verify_parent_hash,
)


class TestSMTHashEngine(unittest.TestCase):
    def test_hash_key_and_zero_hashes(self):
        k1 = hash_key("drone-alpha")
        self.assertEqual(len(k1), 32)
        zero_0 = get_zero_hash(0)
        zero_256 = get_zero_hash(256)
        self.assertEqual(len(zero_0), 32)
        self.assertEqual(len(zero_256), 32)
        self.assertEqual(zero_0, b"\x00" * 32)

    def test_hash_leaf_and_parent_verification(self):
        k = hash_key("drone-1")
        v = hash_key("pubkey-1")
        h_leaf = hash_leaf(k, v)
        self.assertTrue(verify_leaf_hash(h_leaf, k, v))

        h_parent = hash_parent(h_leaf, get_zero_hash(0))
        self.assertTrue(verify_parent_hash(h_parent, h_leaf, get_zero_hash(0)))


class TestSMTNodes(unittest.TestCase):
    def test_slotted_nodes(self):
        k = hash_key("drone-1")
        v = hash_key("pubkey-1")
        leaf = LeafNode(k, v)
        self.assertTrue(leaf.is_leaf)
        self.assertFalse(leaf.is_empty)

        empty = EmptyNode(depth=5)
        self.assertFalse(empty.is_leaf)
        self.assertTrue(empty.is_empty)

        branch = InternalNode(leaf.hash, empty.hash)
        self.assertFalse(branch.is_leaf)
        self.assertFalse(branch.is_empty)


class TestSparseMerkleTreeOperations(unittest.TestCase):
    def test_tree_lifecycle(self):
        tree = SparseMerkleTree()
        empty_root = tree.root
        self.assertEqual(empty_root, get_zero_hash(256))

        k1 = hash_key("drone-1")
        v1 = hash_key("pubkey-1")
        r1 = tree.update(k1, v1)
        self.assertNotEqual(r1, empty_root)
        self.assertEqual(tree.get(k1), v1)

        # Non-existent key
        k2 = hash_key("drone-2")
        self.assertEqual(tree.get(k2), b"\x00" * 32)

        # Delete key
        r2 = tree.delete(k1)
        self.assertEqual(r2, empty_root)
        self.assertEqual(tree.get(k1), b"\x00" * 32)


class TestSMTProofsAndVerification(unittest.TestCase):
    def test_membership_and_non_membership_proofs(self):
        tree = SparseMerkleTree()
        k1 = hash_key("drone-1")
        v1 = hash_key("pubkey-1")
        tree.update(k1, v1)

        # Inclusion proof
        p1 = tree.create_proof(k1, epoch=1, nonce="n1")
        self.assertTrue(p1.is_membership_proof())
        self.assertTrue(SMTVerifier.verify_membership(tree.root, p1))

        # Binary serialization
        p1_bytes = p1.serialize()
        p1_recovered = SMTProof.deserialize(p1_bytes)
        self.assertEqual(p1, p1_recovered)
        self.assertTrue(SMTVerifier.verify_membership(tree.root, p1_recovered))

        # Non-membership proof
        k_unknown = hash_key("drone-unknown")
        p_unknown = tree.create_proof(k_unknown)
        self.assertTrue(p_unknown.is_non_membership_proof())
        self.assertTrue(SMTVerifier.verify_non_membership(tree.root, p_unknown))


class TestDroneRegistry(unittest.TestCase):
    def test_registry_workflow(self):
        reg = DroneRegistry()
        pub1 = b"pubkey_drone_001_bytes_32bit____"

        r1 = reg.register_drone("drone-1", pub1, role="leader", hierarchy_level=0)
        self.assertNotEqual(r1, get_zero_hash(256))

        with self.assertRaises(DroneAlreadyRegisteredError):
            reg.register_drone("drone-1", pub1)

        proof = reg.prove_membership("drone-1")
        self.assertTrue(SMTVerifier.verify_membership(reg.get_root(), proof))

        # Revoke
        r_revoked = reg.revoke_drone("drone-1")
        self.assertEqual(r_revoked, get_zero_hash(256))

        with self.assertRaises(DroneNotFoundError):
            reg.prove_membership("drone-1")


class TestSMTRootManager(unittest.TestCase):
    def test_root_history(self):
        rm = SMTRootManager(history_capacity=5)
        root1 = hash_key("root1")
        root2 = hash_key("root2")

        rm.commit_root(root1, epoch=1)
        self.assertEqual(rm.current_root, root1)
        self.assertTrue(rm.is_known_root(root1))

        rm.commit_root(root2, epoch=2)
        self.assertTrue(rm.is_known_root(root1))
        self.assertTrue(rm.is_known_root(root2))
        self.assertFalse(rm.is_known_root(hash_key("unknown_root")))


class TestSMTIntegrityAndSync(unittest.TestCase):
    def test_integrity_and_sync(self):
        tree1 = SparseMerkleTree()
        k1 = hash_key("drone-1")
        v1 = hash_key("pubkey-1")
        tree1.update(k1, v1)

        self.assertTrue(SMTIntegrityChecker.audit_tree(tree1))
        self.assertTrue(SMTIntegrityChecker.verify_leaf_integrity(tree1, k1))

        # State Sync
        tree2 = SparseMerkleTree()
        patch = SMTSyncManager.compute_diff(tree1, tree2.root)
        patch_bytes = patch.serialize()
        patch_rec = SMTSyncPatch.deserialize(patch_bytes)

        SMTSyncManager.apply_patch(tree2, patch_rec)
        self.assertEqual(tree2.root, tree1.root)


if __name__ == "__main__":
    unittest.main()
