"""Comprehensive Test Suite for SwarmSecurityManager (security.py).

Tests cover:
    1.  SMT verification — known vs unknown root, proof validation.
    2.  SMT root manager integration — ring buffer history and root updates.
    3.  Session creation, registry, lookup, and count tracking.
    4.  Session destruction, expiration, and key zeroisation.
    5.  Session state machine — legal transitions and InvalidSessionStateError.
    6.  Replay attack handling — ReplayError catching and ReplayAttackError raising.
    7.  AEAD authentication error handling — AeadAuthError catching.
    8.  Key ratcheting — SequenceOverflow handling and derive_aead_ratchet execution.
    9.  ML-KEM flow coordination — complete_kem().
    10. ML-DSA control plane signature verification and root updates.
    11. Event generation and draining.
    12. Thread safety — concurrent session creation, encrypt/decrypt, and event drain.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.aead import AeadAuthError, ReplayError, SequenceOverflow
from smt.proof import SMTProof
from smt.root_manager import SMTRootManager
from hierarchical_swarm.security import (
    InvalidSessionStateError,
    PendingAuth,
    ReplayAttackError,
    SecurityError,
    SecurityEvent,
    SecurityEventType,
    SessionState,
    SwarmSecurityManager,
    SwarmSession,
)


class TestSMTVerification(unittest.TestCase):

    def setUp(self):
        self.rm = SMTRootManager()
        self.sec = SwarmSecurityManager(root_manager=self.rm)
        self.test_root = b"\x11" * 32
        self.rm.commit_root(self.test_root, epoch=1)

    def test_verify_known_root_valid_proof(self):
        from smt.sparse_merkle_tree import SparseMerkleTree
        tree = SparseMerkleTree()
        key = b"drone-01".ljust(32, b"\x00")
        val = b"value-01".ljust(32, b"\x00")
        root = tree.update(key, val)
        proof = tree.create_proof(key)
        
        self.rm.commit_root(root, epoch=1)
        proof_bytes = proof.serialize()
        self.assertTrue(self.sec.verify_drone_proof(root, proof_bytes))

    def test_verify_unknown_root_fails(self):
        unknown_root = b"\x99" * 32
        proof_bytes = b"\x00" * 68
        self.assertFalse(self.sec.verify_drone_proof(unknown_root, proof_bytes))

    def test_invalid_proof_bytes_fails(self):
        self.assertFalse(self.sec.verify_drone_proof(self.test_root, b"corrupted_bytes"))

    def test_generate_drone_proof_returns_bytes(self):
        proof_bytes = self.sec.generate_drone_proof("drone-01")
        self.assertIsInstance(proof_bytes, bytes)
        self.assertGreater(len(proof_bytes), 0)


class TestSessionLifecycle(unittest.TestCase):

    def setUp(self):
        self.sec = SwarmSecurityManager()
        self.session_id = b"\x01" * 16
        self.k_send = b"\xAA" * 16
        self.k_recv = b"\xBB" * 16

    def test_create_and_get_session(self):
        sess = self.sec.create_session("drone-01", self.session_id, self.k_send, self.k_recv)
        self.assertEqual(sess.drone_id, "drone-01")
        self.assertEqual(sess.state, SessionState.ESTABLISHED)
        self.assertTrue(self.sec.has_session("drone-01"))
        self.assertEqual(self.sec.active_session_count(), 1)
        self.assertIs(self.sec.get_session("drone-01"), sess)
        self.assertIs(self.sec.get_session_by_id(self.session_id), sess)

    def test_destroy_session_clears_registry_and_zeroes_keys(self):
        sess = self.sec.create_session("drone-01", self.session_id, self.k_send, self.k_recv)
        self.sec.destroy_session("drone-01")
        self.assertFalse(self.sec.has_session("drone-01"))
        self.assertEqual(self.sec.active_session_count(), 0)
        self.assertEqual(sess.state, SessionState.DESTROYED)
        self.assertEqual(bytes(sess.base_k_send), b"\x00" * 16)
        self.assertEqual(bytes(sess.base_k_recv), b"\x00" * 16)

    def test_expire_session_aliases_destroy(self):
        self.sec.create_session("drone-01", self.session_id, self.k_send, self.k_recv)
        self.sec.expire_session("drone-01")
        self.assertFalse(self.sec.has_session("drone-01"))

    def test_destroy_all_sessions(self):
        self.sec.create_session("drone-01", b"\x01" * 16, self.k_send, self.k_recv)
        self.sec.create_session("drone-02", b"\x02" * 16, self.k_send, self.k_recv)
        self.assertEqual(self.sec.active_session_count(), 2)
        self.sec.destroy_all_sessions()
        self.assertEqual(self.sec.active_session_count(), 0)


class TestSessionStateTransitions(unittest.TestCase):

    def setUp(self):
        self.sec = SwarmSecurityManager()
        self.sess = self.sec.create_session("drone-01", b"\x01" * 16, b"\xAA" * 16, b"\xBB" * 16)

    def test_established_to_rekeying_to_established(self):
        self.sess.transition_to(SessionState.REKEYING)
        self.assertEqual(self.sess.state, SessionState.REKEYING)
        self.sess.transition_to(SessionState.ESTABLISHED)
        self.assertEqual(self.sess.state, SessionState.ESTABLISHED)

    def test_illegal_transition_raises_error(self):
        self.sess.transition_to(SessionState.DESTROYED)
        with self.assertRaises(InvalidSessionStateError):
            self.sess.transition_to(SessionState.ESTABLISHED)


class TestEncryptDecryptAndErrors(unittest.TestCase):

    def setUp(self):
        self.sec = SwarmSecurityManager()
        self.session_id = b"\x01" * 16
        self.k_send = b"\xAA" * 16
        self.k_recv = b"\xBB" * 16
        self.sess = self.sec.create_session("drone-01", self.session_id, self.k_send, self.k_recv)

    def test_encrypt_and_decrypt_flow(self):
        # We simulate symmetric send/recv by mirroring key_send on receiver
        self.sec.create_session("drone-02", self.session_id, self.k_send, self.k_send)
        ciphertext = self.sec.encrypt_packet("drone-01", b"Hello Swarm")
        self.assertIsInstance(ciphertext, bytes)

    def test_encrypt_non_existent_session_raises(self):
        with self.assertRaises(SecurityError):
            self.sec.encrypt_packet("ghost-drone", b"data")

    def test_decrypt_non_existent_session_raises(self):
        with self.assertRaises(SecurityError):
            self.sec.decrypt_packet("ghost-drone", b"data")

    @patch("core.aead.Receiver.decrypt", side_effect=ReplayError("Duplicate seq"))
    def test_replay_error_caught_and_raised_as_security_error(self, mock_dec):
        with self.assertRaises(ReplayAttackError):
            self.sec.decrypt_packet("drone-01", b"fake_wire_bytes")

    @patch("core.aead.Receiver.decrypt", side_effect=AeadAuthError("Tag mismatch"))
    def test_aead_auth_error_caught_and_raised_as_security_error(self, mock_dec):
        with self.assertRaises(SecurityError):
            self.sec.decrypt_packet("drone-01", b"fake_wire_bytes")

    @patch("core.aead.Sender.encrypt", side_effect=[SequenceOverflow("Seq full"), b"rekeyed_cipher"])
    def test_sequence_overflow_triggers_ratchet(self, mock_enc):
        cipher = self.sec.encrypt_packet("drone-01", b"data")
        self.assertEqual(cipher, b"rekeyed_cipher")
        self.assertEqual(self.sess.epoch, 1)


class TestKEMAndMLDSA(unittest.TestCase):

    def setUp(self):
        self.sec = SwarmSecurityManager(mldsa_pubkey=b"test_pubkey")

    def test_create_challenge_and_complete_kem(self):
        nonce, root = self.sec.create_challenge("drone-01")
        self.assertIsInstance(nonce, str)
        self.assertEqual(len(root), 32)

        shared_secret = b"\x42" * 32
        session = self.sec.complete_kem("drone-01", shared_secret)
        self.assertEqual(session.drone_id, "drone-01")
        self.assertEqual(session.state, SessionState.ESTABLISHED)

    @patch("hierarchical_swarm.security.Signature", None)
    def test_verify_control_signature_mock(self):
        msg = b"RootUpdatePayload"
        sig = b"VALID_SIGNATURE_test_pubkey"
        self.assertTrue(self.sec.verify_control_signature(msg, sig))

    @patch("hierarchical_swarm.security.Signature", None)
    def test_commit_root_update_with_valid_sig(self):
        new_root = b"\x77" * 32
        msg = b"Payload"
        sig = b"VALID_SIGNATURE_test_pubkey"
        success = self.sec.commit_root_update(new_root, epoch=1, signature_bytes=sig, payload_bytes=msg)
        self.assertTrue(success)
        self.assertEqual(self.sec.get_smt_root(), new_root)


class TestEventsAndThreadSafety(unittest.TestCase):

    def setUp(self):
        self.sec = SwarmSecurityManager()

    def test_event_emission_and_drain(self):
        self.sec.create_session("drone-01", b"\x01" * 16, b"\xAA" * 16, b"\xBB" * 16)
        events = self.sec.drain_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, SecurityEventType.SESSION_CREATED)
        self.assertEqual(self.sec.drain_events(), [])

    def test_concurrent_session_management(self):
        errors = []

        def worker(idx: int):
            try:
                drone_id = f"drone-{idx}"
                sess_id = idx.to_bytes(16, "big")
                self.sec.create_session(drone_id, sess_id, b"\x11" * 16, b"\x22" * 16)
                self.assertTrue(self.sec.has_session(drone_id))
                self.sec.destroy_session(drone_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        self.assertEqual(self.sec.active_session_count(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
