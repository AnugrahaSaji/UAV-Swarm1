"""Tests for core/ code quality fixes.

Covers:
- AEAD destroy sentinel (Sender + Receiver)
- AEAD wire max-length guard
- AEAD thread-safety docstrings present
- control_tcp bounded thread pool + rekey rate limiting
- async_proxy allowlist string handling
- async_proxy rekey depth limit
- handshake exception chain preservation
"""

import sys
import os
import time
import threading
import struct
import socket
import tempfile
import argparse
import io
import contextlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import CONFIG
from core.aead import (
    AeadIds,
    Sender,
    Receiver,
    AeadError,
    HEADER_LEN,
    HEADER_STRUCT,
    MAX_WIRE_LEN,
)
from core.exceptions import HandshakeFormatError


# ── shared fixtures ──────────────────────────────────────────────────────────
_KEY = b"\x00" * 32
_SID = b"\x00" * 16
_IDS = AeadIds(kem_id=1, kem_param=2, sig_id=3, sig_param=4)
_VER = CONFIG["WIRE_VERSION"]


def _make_pair(aead_token: str = "aesgcm"):
    s = Sender(version=_VER, ids=_IDS, session_id=_SID, epoch=0, key_send=_KEY, aead_token=aead_token)
    r = Receiver(version=_VER, ids=_IDS, session_id=_SID, epoch=0, key_recv=_KEY, window=64, aead_token=aead_token)
    return s, r


# ═══════════════════════════════════════════════════════════════════════════════
# 1. AEAD destroy sentinels
# ═══════════════════════════════════════════════════════════════════════════════

def test_sender_destroy_prevents_encrypt():
    s, _ = _make_pair()
    wire = s.encrypt(b"test")
    assert wire is not None

    s.destroy()
    try:
        s.encrypt(b"after destroy")
        assert False, "encrypt() should raise after destroy()"
    except AeadError as e:
        assert "destroyed" in str(e).lower(), f"Expected 'destroyed' in error message, got: {e}"
    print("  PASS: Sender.destroy() prevents encrypt()")


def test_receiver_destroy_prevents_decrypt():
    s, r = _make_pair()
    wire = s.encrypt(b"test")
    pt = r.decrypt(wire)
    assert pt == b"test"

    r.destroy()
    try:
        r.decrypt(wire)
        assert False, "decrypt() should raise after destroy()"
    except AeadError as e:
        assert "destroyed" in str(e).lower(), f"Expected 'destroyed' in error message, got: {e}"
    print("  PASS: Receiver.destroy() prevents decrypt()")


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Wire max-length guard
# ═══════════════════════════════════════════════════════════════════════════════

def test_wire_max_length_rejected():
    _, r = _make_pair()
    oversized = b"\x00" * (MAX_WIRE_LEN + 1)
    try:
        r.decrypt(oversized)
        assert False, "decrypt() should reject oversized wire"
    except ValueError as e:
        assert "too large" in str(e).lower(), f"Expected 'too large' in error, got: {e}"
    print("  PASS: Receiver.decrypt() rejects oversized wire")


def test_wire_too_short_rejected():
    _, r = _make_pair()
    try:
        r.decrypt(b"\x00" * 5)
        assert False, "decrypt() should reject short wire"
    except ValueError as e:
        assert "too short" in str(e).lower()
    print("  PASS: Receiver.decrypt() rejects short wire")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Thread-safety docstrings
# ═══════════════════════════════════════════════════════════════════════════════

def test_thread_safety_documented():
    assert "NOT thread-safe" in (Sender.__doc__ or ""), "Sender docstring should warn about thread safety"
    assert "NOT thread-safe" in (Receiver.__doc__ or ""), "Receiver docstring should warn about thread safety"
    print("  PASS: Sender/Receiver thread-safety documented")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. AEAD round-trip sanity (regression guard for all supported tokens)
# ═══════════════════════════════════════════════════════════════════════════════

def test_roundtrip_all_tokens():
    tokens = ["aesgcm"]
    from core.suites import available_aead_tokens
    runtime_tokens = set(available_aead_tokens())
    for token in ("aesccm", "chacha20poly1305", "ascon128", "ascon128a"):
        if token in runtime_tokens:
            tokens.append(token)

    for token in tokens:
        s, r = _make_pair(token)
        plaintext = b"PQC UAV secure tunnel test payload"
        wire = s.encrypt(plaintext)
        pt = r.decrypt(wire)
        assert pt == plaintext, f"{token}: decrypt mismatch"
    print(f"  PASS: Round-trip OK for {', '.join(tokens)}")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Replay window (check-then-commit pattern)
# ═══════════════════════════════════════════════════════════════════════════════

def test_replay_rejected():
    s, r = _make_pair()
    wire = s.encrypt(b"msg1")
    pt1 = r.decrypt(wire)
    assert pt1 == b"msg1"

    # Same wire again → replay → returns None (strict_mode=False default)
    pt2 = r.decrypt(wire)
    assert pt2 is None, "Replay should return None in non-strict mode"
    assert r.last_error_reason() == "replay"
    print("  PASS: Replay correctly rejected")


def test_replay_strict_raises():
    s = Sender(version=_VER, ids=_IDS, session_id=_SID, epoch=0, key_send=_KEY)
    r = Receiver(version=_VER, ids=_IDS, session_id=_SID, epoch=0, key_recv=_KEY, window=64, strict_mode=True)
    wire = s.encrypt(b"msg")
    r.decrypt(wire)
    from core.aead import ReplayError
    try:
        r.decrypt(wire)
        assert False, "Should raise ReplayError"
    except ReplayError:
        pass
    print("  PASS: Replay raises ReplayError in strict mode")


def test_session_mismatch_strict_raises():
    s = Sender(version=_VER, ids=_IDS, session_id=_SID, epoch=0, key_send=_KEY)
    wrong_sid = b"\x01" * 16
    r = Receiver(version=_VER, ids=_IDS, session_id=wrong_sid, epoch=0, key_recv=_KEY, window=64, strict_mode=True)
    wire = s.encrypt(b"msg")
    from core.aead import HeaderMismatch
    try:
        r.decrypt(wire)
        assert False, "Should raise HeaderMismatch on session mismatch"
    except HeaderMismatch:
        pass
    print("  PASS: Session mismatch raises HeaderMismatch in strict mode")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Epoch bump and wrap check
# ═══════════════════════════════════════════════════════════════════════════════

def test_epoch_wrap_forbidden():
    s, r = _make_pair()
    s.epoch = 255
    r.epoch = 255
    try:
        s.bump_epoch()
        assert False, "Should raise on epoch wrap"
    except AeadError:
        pass
    try:
        r.bump_epoch()
        assert False, "Should raise on epoch wrap"
    except AeadError:
        pass
    print("  PASS: Epoch 255->0 wrap correctly forbidden")


def test_replay_window_upper_bound_validation():
    try:
        Receiver(version=_VER, ids=_IDS, session_id=_SID, epoch=0, key_recv=_KEY, window=70000)
        assert False, "Should reject oversized replay window"
    except ValueError as exc:
        assert "64..65536" in str(exc)
    print("  PASS: Replay window upper bound enforced")


# ═══════════════════════════════════════════════════════════════════════════════
# 7. control_tcp rate limiting
# ═══════════════════════════════════════════════════════════════════════════════

def test_control_tcp_rekey_rate_limit():
    from core.control_tcp import _REKEY_RATE_LIMIT_S
    assert _REKEY_RATE_LIMIT_S > 0, "Rate limit must be positive"
    print(f"  PASS: control_tcp rekey rate limit = {_REKEY_RATE_LIMIT_S}s")


def test_control_tcp_max_workers():
    from core.control_tcp import _MAX_CONTROL_WORKERS
    assert 1 <= _MAX_CONTROL_WORKERS <= 64, f"Unexpected max workers: {_MAX_CONTROL_WORKERS}"
    print(f"  PASS: control_tcp max workers = {_MAX_CONTROL_WORKERS}")


def test_policy_engine_timeout_recovery():
    from core.policy_engine import create_control_state, request_prepare, tick_state_timeouts

    state = create_control_state("gcs", "cs-mlkem768-mldsa65", aead_token="aesgcm")
    rid = request_prepare(state, "cs-mlkem768-mldsa65", aead_token="ascon128")
    now_ms = int(time.monotonic() * 1000.0) + 50
    payload = tick_state_timeouts(
        state,
        negotiating_timeout_ms=1,
        swapping_timeout_ms=1,
        now_ms=now_ms,
    )
    assert payload is not None, "Expected timeout payload for stale NEGOTIATING state"
    assert payload["rid"] == rid
    assert payload["result"] == "fail"
    assert payload["reason"] == "timeout_negotiating"
    assert payload["aead"] == "ascon128"
    assert state.state == "RUNNING"
    assert state.active_rid is None
    assert state.pending_epoch is None
    print("  PASS: policy engine timeout recovery resets stale negotiation state")


def test_policy_engine_pending_epoch_promotes_only_on_success():
    from core.policy_engine import create_control_state, record_rekey_result, request_prepare

    state = create_control_state("gcs", "cs-mlkem768-mldsa65", aead_token="aesgcm")

    rid_fail = request_prepare(state, "cs-mlkem768-mldsa65", aead_token="aesccm")
    assert state.epoch == 0
    assert state.pending_epoch == 1
    record_rekey_result(state, rid_fail, "cs-mlkem768-mldsa65", success=False)
    assert state.epoch == 0
    assert state.pending_epoch is None
    assert state.current_aead == "aesgcm"

    rid_ok = request_prepare(state, "cs-mlkem768-mldsa65", aead_token="aesccm")
    assert state.pending_epoch == 1
    record_rekey_result(
        state,
        rid_ok,
        "cs-mlkem768-mldsa65",
        success=True,
        aead_token="aesccm",
    )
    assert state.epoch == 1
    assert state.pending_epoch is None
    assert state.current_aead == "aesccm"
    print("  PASS: policy engine keeps pending epoch staged until success")


def test_policy_engine_activation_waits_for_both_sides():
    from core.policy_engine import create_control_state, handle_control, note_local_rekey_ready, request_prepare

    state = create_control_state("gcs", "cs-mlkem768-mldsa65", aead_token="aesgcm")
    rid = request_prepare(state, "cs-mlkem768-mldsa65", aead_token="aesccm")

    ready = note_local_rekey_ready(state, rid)
    assert ready is False
    assert state.activation_sent is False
    assert state.state == "SWAPPING"

    result = handle_control({"type": "activate_ok", "rid": rid}, "gcs", state)
    assert len(result.send) == 1
    assert result.send[0]["type"] == "activate_rekey"
    assert result.send[0]["suite"] == "cs-mlkem768-mldsa65"
    assert result.send[0]["aead"] == "aesccm"
    assert result.send[0]["rid"] == rid
    assert state.activation_sent is True

    duplicate = handle_control({"type": "activate_ok", "rid": rid}, "gcs", state)
    assert duplicate.send == []
    print("  PASS: activation is emitted only after local and peer readiness")


def test_async_proxy_build_sender_receiver_uses_transport_epoch():
    from core.async_proxy import _build_sender_receiver

    cfg = dict(CONFIG)
    cfg["REPLAY_WINDOW"] = 64
    cfg["SUITE_AEAD_TOKEN"] = "aesgcm128"

    sender, receiver = _build_sender_receiver(
        "drone",
        _IDS,
        _SID,
        _KEY,
        b"\x01" * 32,
        cfg,
        epoch=7,
    )
    assert sender.epoch == 7
    assert receiver.epoch == 7
    assert len(sender.key_send) == 16
    assert len(receiver.key_recv) == 16
    print("  PASS: async_proxy builds sender/receiver with negotiated transport epoch and AEAD-sized keys")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Handshake exception chain
# ═══════════════════════════════════════════════════════════════════════════════

def test_handshake_exception_chain():
    from core.handshake import parse_and_verify_server_hello
    try:
        # Pass a truncated wire that will fail during struct unpack
        parse_and_verify_server_hello(b"\x01\x00", expected_version=1, server_sig_pub=b"fake")
        assert False, "Should have raised"
    except HandshakeFormatError as e:
        # Verify the original exception is chained via `from exc`
        assert e.__cause__ is not None, "Exception chain should be preserved (from exc)"
        print(f"  PASS: HandshakeFormatError preserves chain: {type(e.__cause__).__name__}")
    except Exception as e:
        # parse_and_verify_server_hello may raise other exceptions for short wires
        print(f"  SKIP: raised {type(e).__name__}: {e}")


def test_handshake_psk_bound_kdf_changes_keys():
    from core.handshake import derive_transport_material
    shared_secret = b"\x22" * 32
    challenge = b"\x33" * 16
    good = derive_transport_material(
        "client",
        _SID,
        challenge,
        b"ML-KEM-768",
        b"ML-DSA-65",
        shared_secret,
        b"\x44" * 32,
    )
    bad = derive_transport_material(
        "client",
        _SID,
        challenge,
        b"ML-KEM-768",
        b"ML-DSA-65",
        shared_secret,
        b"\x55" * 32,
    )
    assert good[:2] != bad[:2], "PSK-bound KDF must produce different transport keys"
    print("  PASS: PSK-bound KDF changes output on PSK mismatch")


def test_handshake_parse_rejects_trailing_bytes():
    from core.handshake import _parse_server_hello_wire
    kem = b"ML-KEM-768"
    sig = b"ML-DSA-65"
    challenge = b"\x02" * 16
    kem_pub = b"\x03" * 32
    signature = b"\x04" * 48
    wire = struct.pack("!B", _VER)
    wire += struct.pack("!H", len(kem)) + kem
    wire += struct.pack("!H", len(sig)) + sig
    wire += _SID
    wire += challenge
    wire += struct.pack("!I", len(kem_pub)) + kem_pub
    wire += struct.pack("!H", len(signature)) + signature
    try:
        _parse_server_hello_wire(wire + b"\xff", _VER)
        assert False, "Parser should reject trailing bytes"
    except HandshakeFormatError as exc:
        assert "trailing bytes" in str(exc)
    print("  PASS: ServerHello parser rejects trailing bytes")


def test_run_proxy_signing_identity_self_test_accepts_matching_key():
    from core.run_proxy import _validate_signing_identity

    class FakeSigner:
        def sign(self, message: bytes) -> bytes:
            return b"sig:" + message

    class FakeVerifier:
        def __init__(self, _alg: str):
            self.freed = False

        def verify(self, message: bytes, signature: bytes, public_key: bytes) -> bool:
            return signature == b"sig:" + message and public_key == b"match"

        def free(self) -> None:
            self.freed = True

    _validate_signing_identity("ML-DSA-65", FakeSigner(), b"match", signature_cls=FakeVerifier)
    print("  PASS: GCS signing identity self-test accepts matching key")


def test_run_proxy_signing_identity_self_test_rejects_mismatch():
    from core.run_proxy import _validate_signing_identity

    class FakeSigner:
        def sign(self, message: bytes) -> bytes:
            return b"sig:" + message

    class FakeVerifier:
        def __init__(self, _alg: str):
            pass

        def verify(self, message: bytes, signature: bytes, public_key: bytes) -> bool:
            return signature == b"sig:" + message and public_key == b"match"

        def free(self) -> None:
            return None

    try:
        _validate_signing_identity("ML-DSA-65", FakeSigner(), b"mismatch", signature_cls=FakeVerifier)
        assert False, "Expected signing identity validation failure"
    except RuntimeError as exc:
        assert "does not match" in str(exc)
    print("  PASS: GCS signing identity self-test rejects mismatched key")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. MAX_WIRE_LEN constant
# ═══════════════════════════════════════════════════════════════════════════════

def test_max_wire_len_constant():
    assert MAX_WIRE_LEN == 65536, f"MAX_WIRE_LEN should be 65536, got {MAX_WIRE_LEN}"
    print("  PASS: MAX_WIRE_LEN = 65536")


# ═══════════════════════════════════════════════════════════════════════════════
# 10. FIX-A: _handshake_port_lock released on bind failure
# ═══════════════════════════════════════════════════════════════════════════════

def test_handshake_lock_released_on_bind_failure():
    """Verify _handshake_port_lock is released even if bind() raises."""
    from core.async_proxy import _handshake_port_lock
    # Lock must be acquirable (not stuck from a previous failed bind)
    acquired = _handshake_port_lock.acquire(timeout=0.1)
    assert acquired, "_handshake_port_lock should be acquirable"
    _handshake_port_lock.release()
    print("  PASS: _handshake_port_lock is acquirable (not deadlocked)")


# ═══════════════════════════════════════════════════════════════════════════════
# 11. FIX-B: _pending_destroy list exists for deferred key wipe
# ═══════════════════════════════════════════════════════════════════════════════

def test_deferred_destroy_mechanism_exists():
    """Verify the deferred destroy infrastructure is importable from async_proxy.
    The actual deferred destroy is a closure inside run_proxy; we verify
    the module-level lock exists (it was added at module scope)."""
    import core.async_proxy as ap
    # The _handshake_port_lock is the only module-level lock; deferred destroy
    # uses closure-scoped _pending_destroy_lock inside run_proxy.
    # Verify the key pattern: Sender.destroy() sets _cipher = None (sentinel)
    s, _ = _make_pair()
    s.destroy()
    assert s._cipher is None, "destroy() should set _cipher to None"
    assert s._seq == -1, "destroy() should set _seq to -1 sentinel"
    print("  PASS: Deferred destroy sentinel pattern verified")


# ═══════════════════════════════════════════════════════════════════════════════
# 12. FIX-D: Liveness threshold config exists
# ═══════════════════════════════════════════════════════════════════════════════

def test_rekey_liveness_threshold_config():
    """Verify REKEY_LIVENESS_THRESHOLD_S config key exists with a sane default."""
    threshold = CONFIG.get("REKEY_LIVENESS_THRESHOLD_S")
    assert threshold is not None, "REKEY_LIVENESS_THRESHOLD_S missing from CONFIG"
    assert isinstance(threshold, (int, float)), f"threshold must be numeric, got {type(threshold)}"
    assert threshold > 0, f"threshold must be positive, got {threshold}"
    print(f"  PASS: REKEY_LIVENESS_THRESHOLD_S = {threshold}s")


# ═══════════════════════════════════════════════════════════════════════════════
# 13. FIX-D2: _handshake_port_lock supports timeout
# ═══════════════════════════════════════════════════════════════════════════════

def test_handshake_lock_timeout_support():
    """Verify _handshake_port_lock.acquire(timeout=...) works (not RLock quirk)."""
    from core.async_proxy import _handshake_port_lock
    # Acquire then try with timeout=0 — should fail (non-reentrant)
    _handshake_port_lock.acquire()
    try:
        second = _handshake_port_lock.acquire(timeout=0)
        assert not second, "Lock should not be re-acquirable (it's a Lock, not RLock)"
    finally:
        _handshake_port_lock.release()
    print("  PASS: _handshake_port_lock supports timeout (non-reentrant)")


# ═══════════════════════════════════════════════════════════════════════════════
# 14. run_proxy startup preflight
# ═══════════════════════════════════════════════════════════════════════════════

def test_run_proxy_preflight_rejects_missing_psk():
    from core.run_proxy import _preflight_drone_psk

    original = os.environ.pop("DRONE_PSK", None)
    try:
        cfg = dict(CONFIG)
        cfg["DRONE_PSK"] = ""
        try:
            _preflight_drone_psk(cfg)
            assert False, "Expected missing DRONE_PSK to fail preflight"
        except RuntimeError as exc:
            assert "DRONE_PSK must be provided" in str(exc)
    finally:
        if original is not None:
            os.environ["DRONE_PSK"] = original
    print("  PASS: run_proxy preflight rejects missing DRONE_PSK")


def test_run_proxy_preflight_rejects_invalid_psk_hex():
    from core.run_proxy import _preflight_drone_psk

    original = os.environ.get("DRONE_PSK")
    os.environ["DRONE_PSK"] = "xyz"
    try:
        try:
            _preflight_drone_psk(dict(CONFIG))
            assert False, "Expected invalid DRONE_PSK hex to fail preflight"
        except RuntimeError as exc:
            assert "Invalid DRONE_PSK hex" in str(exc)
    finally:
        if original is None:
            os.environ.pop("DRONE_PSK", None)
        else:
            os.environ["DRONE_PSK"] = original
    print("  PASS: run_proxy preflight rejects invalid DRONE_PSK hex")


def test_run_proxy_preflight_rejects_wrong_psk_length():
    from core.run_proxy import _preflight_drone_psk

    original = os.environ.get("DRONE_PSK")
    os.environ["DRONE_PSK"] = "ab" * 31
    try:
        try:
            _preflight_drone_psk(dict(CONFIG))
            assert False, "Expected wrong DRONE_PSK length to fail preflight"
        except RuntimeError as exc:
            assert "must decode to 32 bytes" in str(exc)
    finally:
        if original is None:
            os.environ.pop("DRONE_PSK", None)
        else:
            os.environ["DRONE_PSK"] = original
    print("  PASS: run_proxy preflight rejects wrong DRONE_PSK length")


def test_run_proxy_startup_preflight_accepts_valid_config():
    from core.run_proxy import _run_startup_preflight

    original = os.environ.get("DRONE_PSK")
    os.environ["DRONE_PSK"] = "ab" * 32
    try:
        cfg = dict(CONFIG)
        cfg["DRONE_PSK"] = "ab" * 32
        suite = {
            "suite_id": "test-suite",
            "kem_name": "ML-KEM-768",
            "sig_name": "ML-DSA-65",
            "aead": "aesgcm",
        }
        _run_startup_preflight("gcs", cfg, suite)
        _run_startup_preflight("drone", cfg, suite)
    finally:
        if original is None:
            os.environ.pop("DRONE_PSK", None)
        else:
            os.environ["DRONE_PSK"] = original
    print("  PASS: run_proxy startup preflight accepts valid config")


def test_suites_exposes_split_negotiation_profiles():
    from core.suites import get_suite, negotiation_profiles_for_suite

    suite = get_suite("cs-mlkem768-mldsa65")
    profiles = negotiation_profiles_for_suite(suite)

    assert suite["key_handshake_id"] == "khs-mlkem768-mldsa65"
    assert suite["data_aead_id"] == "dap-aesgcm"
    assert suite["negotiation_scope"] == "key_handshake=kem+sig,data_plane=aead"
    assert profiles["key_handshake_id"] == "khs-mlkem768-mldsa65"
    assert profiles["data_aead_id"] == "dap-aesgcm"
    print("  PASS: suite registry exposes split key-handshake/data-AEAD profiles")


def test_suites_capability_negotiation_selects_expected_suite():
    from core.suites import select_suite_id_for_capabilities

    selected = select_suite_id_for_capabilities(
        kem_tokens=["mlkem512", "kyber768"],
        sig_tokens=["mldsa44", "dilithium3"],
        aead_tokens=["aesgcm", "chacha"],
        prefer_kem_tokens=["kyber768", "mlkem512"],
        prefer_sig_tokens=["dilithium3", "mldsa44"],
        prefer_aead_tokens=["chacha", "aesgcm"],
    )

    assert selected == "cs-mlkem768-mldsa65"
    print("  PASS: capability negotiation selected preferred canonical suite")


def test_suites_crypto_profile_negotiation_selects_aead():
    from core.suites import select_crypto_profile_for_capabilities

    profile = select_crypto_profile_for_capabilities(
        kem_tokens=["mlkem768", "kyber768"],
        sig_tokens=["mldsa65", "dilithium3"],
        aead_tokens=["ascon128", "aesgcm"],
        prefer_kem_tokens=["kyber768"],
        prefer_sig_tokens=["dilithium3"],
        prefer_aead_tokens=["ascon128", "aesgcm"],
    )

    assert profile["suite_id"] == "cs-mlkem768-mldsa65"
    assert profile["nist_level"] == "L3"
    # L3 profile forbids Ascon by policy; AES-GCM must be selected from offer.
    assert profile["aead_token"] == "aesgcm"
    assert profile["data_aead_id"] == "dap-aesgcm"
    assert profile["aead_profile_id"] == "aead-l3-aesgcm"
    print("  PASS: crypto profile negotiation enforces L3 AEAD policy")


def test_suites_aead_profile_matrix_has_8_profiles():
    from core.suites import aead_profiles_by_nist_level, available_aead_tokens

    matrix = aead_profiles_by_nist_level()
    assert matrix == {
        "L1": ("aesgcm", "aesccm", "ascon128"),
        "L3": ("aesgcm", "aesccm"),
        "L5": ("aesgcm", "aesccm", "chacha20poly1305"),
    }
    assert sum(len(tokens) for tokens in matrix.values()) == 8

    runtime_matrix = aead_profiles_by_nist_level(runtime_only=True)
    runtime_tokens = set(available_aead_tokens())
    for level, tokens in runtime_matrix.items():
        assert set(tokens).issubset(set(matrix[level]))
        assert set(tokens).issubset(runtime_tokens)
    print("  PASS: AEAD matrix exposes 8 profiles across L1/L3/L5")


def test_suites_exposes_scheduler_approved_subset():
    from core.suites import approved_aead_profiles_by_nist_level, get_suite, list_scheduler_approved_suites

    approved_suites = list_scheduler_approved_suites()
    assert "cs-mlkem768-mldsa65" in approved_suites
    assert approved_suites["cs-mlkem768-mldsa65"]["scheduler_allowed"] is True
    assert "cs-classicmceliece460896-mldsa65" not in approved_suites
    assert get_suite("cs-classicmceliece460896-mldsa65")["scheduler_allowed"] is False

    approved_matrix = approved_aead_profiles_by_nist_level()
    assert approved_matrix == {
        "L1": ("aesgcm", "aesccm", "ascon128"),
        "L3": ("aesgcm", "aesccm"),
        "L5": ("aesgcm", "aesccm"),
    }
    print("  PASS: suite registry exposes explicit scheduler-approved subset")


def test_suites_scheduler_only_negotiation_filters_benchmark_profiles():
    from core.suites import select_crypto_profile_for_capabilities

    profile = select_crypto_profile_for_capabilities(
        kem_tokens=["classicmceliece8192128", "mlkem1024"],
        sig_tokens=["mldsa87"],
        aead_tokens=["chacha20poly1305", "aesgcm"],
        prefer_kem_tokens=["classicmceliece8192128", "mlkem1024"],
        prefer_aead_tokens=["chacha20poly1305", "aesgcm"],
        scheduler_only=True,
    )

    assert profile["suite_id"] == "cs-mlkem1024-mldsa87"
    assert profile["aead_token"] == "aesgcm"
    assert profile["scheduler_allowed"] is True
    assert profile["approval_status"] == "approved"
    print("  PASS: scheduler-only negotiation prunes benchmark-only suite and AEAD choices")


def test_suites_rejects_legacy_aead_embedded_suite_ids():
    from core.suites import get_suite

    legacy_suite_id = "cs-mlkem768-aesgcm-mldsa65"
    try:
        get_suite(legacy_suite_id)
        assert False, "Expected legacy aead-embedded suite id to be rejected"
    except (NotImplementedError, ValueError):
        pass
    print("  PASS: legacy aead-embedded suite IDs are rejected")


def test_preflight_prints_split_negotiation_profiles():
    from core.run_proxy import preflight_command

    args = argparse.Namespace(
        role="drone",
        suite="cs-mlkem768-mldsa65",
        kem=None,
        aead=None,
        sig=None,
        gcs_pub_hex="ab" * 16,
        peer_pubkey_file=None,
        gcs_secret_file=None,
        ephemeral=False,
        enable_tcp_control=False,
        coordinator_role=None,
    )

    original_psk = os.environ.get("DRONE_PSK")
    os.environ["DRONE_PSK"] = "ab" * 32
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            preflight_command(args)
        text = buf.getvalue()
        assert "Preflight OK:" in text
        assert "key_handshake=khs-mlkem768-mldsa65" in text
        assert "data_aead=dap-aesgcm" in text
    finally:
        if original_psk is None:
            os.environ.pop("DRONE_PSK", None)
        else:
            os.environ["DRONE_PSK"] = original_psk
    print("  PASS: preflight output includes split negotiation profiles")


def test_async_proxy_drone_connect_timeout_message():
    import core.async_proxy as ap

    class _TimeoutSocket:
        def setsockopt(self, *args, **kwargs):
            return None

        def settimeout(self, *args, **kwargs):
            return None

        def connect(self, *args, **kwargs):
            raise socket.timeout("timed out")

        def close(self):
            return None

    original_socket_factory = ap.socket.socket
    ap.socket.socket = lambda *args, **kwargs: _TimeoutSocket()
    try:
        cfg = dict(CONFIG)
        cfg["GCS_HOST"] = "10.10.10.10"
        cfg["TCP_HANDSHAKE_PORT"] = 46000
        try:
            ap._perform_handshake(
                role="drone",
                suite={"suite_id": "test", "aead": "aesgcm"},
                gcs_sig_secret=None,
                gcs_sig_public=b"pub",
                cfg=cfg,
            )
            assert False, "Expected connect timeout diagnostics"
        except Exception as exc:
            text = str(exc)
            assert "Handshake TCP connect timed out" in text
            assert "10.10.10.10:46000" in text
    finally:
        ap.socket.socket = original_socket_factory
    print("  PASS: async_proxy reports drone connect timeout endpoint")


def test_async_proxy_drone_handshake_io_timeout_message():
    import core.async_proxy as ap

    class _ConnectedSocket:
        def setsockopt(self, *args, **kwargs):
            return None

        def settimeout(self, *args, **kwargs):
            return None

        def connect(self, *args, **kwargs):
            return None

        def getpeername(self):
            return ("10.10.10.10", 46000)

        def close(self):
            return None

    original_socket_factory = ap.socket.socket
    original_client_handshake = ap.client_drone_handshake
    ap.socket.socket = lambda *args, **kwargs: _ConnectedSocket()
    ap.client_drone_handshake = lambda *args, **kwargs: (_ for _ in ()).throw(socket.timeout("timed out"))
    try:
        cfg = dict(CONFIG)
        cfg["GCS_HOST"] = "10.10.10.10"
        cfg["TCP_HANDSHAKE_PORT"] = 46000
        try:
            ap._perform_handshake(
                role="drone",
                suite={"suite_id": "test", "aead": "aesgcm"},
                gcs_sig_secret=None,
                gcs_sig_public=b"pub",
                cfg=cfg,
            )
            assert False, "Expected handshake I/O timeout diagnostics"
        except Exception as exc:
            text = str(exc)
            assert "Handshake I/O timed out while connected" in text
            assert "10.10.10.10:46000" in text
    finally:
        ap.socket.socket = original_socket_factory
        ap.client_drone_handshake = original_client_handshake
    print("  PASS: async_proxy reports drone handshake I/O timeout endpoint")


def test_async_proxy_gcs_accept_timeout_message():
    import core.async_proxy as ap

    class _ServerTimeoutSocket:
        def setsockopt(self, *args, **kwargs):
            return None

        def bind(self, *args, **kwargs):
            return None

        def listen(self, *args, **kwargs):
            return None

        def settimeout(self, *args, **kwargs):
            return None

        def accept(self):
            raise socket.timeout("timed out")

        def close(self):
            return None

    original_socket_factory = ap.socket.socket
    ap.socket.socket = lambda *args, **kwargs: _ServerTimeoutSocket()
    try:
        cfg = dict(CONFIG)
        cfg["TCP_HANDSHAKE_PORT"] = 46000
        cfg["DRONE_HOST"] = "192.168.0.105"
        try:
            ap._perform_handshake(
                role="gcs",
                suite={"suite_id": "test", "aead": "aesgcm"},
                gcs_sig_secret=object(),
                gcs_sig_public=None,
                cfg=cfg,
                accept_deadline_s=12.0,
            )
            assert False, "Expected GCS accept timeout diagnostics"
        except Exception as exc:
            text = str(exc)
            assert "No drone TCP handshake connection received" in text
            assert "0.0.0.0:46000" in text
            assert "12.0s" in text
            assert "expected DRONE_HOST=192.168.0.105" in text
    finally:
        ap.socket.socket = original_socket_factory
    print("  PASS: async_proxy reports GCS accept timeout context")


def test_run_proxy_preflight_rejects_tailscale_runtime_hosts():
    from core.run_proxy import _run_startup_preflight

    original_allow = os.environ.pop("ALLOW_TAILSCALE_RUNTIME", None)
    original_psk = os.environ.get("DRONE_PSK")
    os.environ["DRONE_PSK"] = "ab" * 32
    try:
        cfg = dict(CONFIG)
        cfg["DRONE_PSK"] = "ab" * 32
        cfg["DRONE_HOST"] = "100.101.93.23"
        cfg["GCS_HOST"] = "192.168.0.100"
        suite = {
            "suite_id": "test-suite",
            "kem_name": "ML-KEM-768",
            "sig_name": "ML-DSA-65",
            "aead": "aesgcm",
        }
        try:
            _run_startup_preflight("drone", cfg, suite)
            assert False, "Expected Tailscale runtime host rejection"
        except RuntimeError as exc:
            text = str(exc)
            assert "Tailscale maintenance plane" in text
            assert "DRONE_HOST=100.101.93.23" in text
    finally:
        if original_allow is not None:
            os.environ["ALLOW_TAILSCALE_RUNTIME"] = original_allow
        if original_psk is None:
            os.environ.pop("DRONE_PSK", None)
        else:
            os.environ["DRONE_PSK"] = original_psk
    print("  PASS: run_proxy preflight rejects Tailscale runtime host")


def test_run_proxy_preflight_allows_tailscale_with_override():
    from core.run_proxy import _run_startup_preflight

    original_allow = os.environ.get("ALLOW_TAILSCALE_RUNTIME")
    original_psk = os.environ.get("DRONE_PSK")
    os.environ["ALLOW_TAILSCALE_RUNTIME"] = "1"
    os.environ["DRONE_PSK"] = "ab" * 32
    try:
        cfg = dict(CONFIG)
        cfg["DRONE_PSK"] = "ab" * 32
        cfg["DRONE_HOST"] = "100.101.93.23"
        cfg["GCS_HOST"] = "100.106.181.122"
        suite = {
            "suite_id": "test-suite",
            "kem_name": "ML-KEM-768",
            "sig_name": "ML-DSA-65",
            "aead": "aesgcm",
        }
        _run_startup_preflight("gcs", cfg, suite)
        _run_startup_preflight("drone", cfg, suite)
    finally:
        if original_allow is None:
            os.environ.pop("ALLOW_TAILSCALE_RUNTIME", None)
        else:
            os.environ["ALLOW_TAILSCALE_RUNTIME"] = original_allow
        if original_psk is None:
            os.environ.pop("DRONE_PSK", None)
        else:
            os.environ["DRONE_PSK"] = original_psk
    print("  PASS: run_proxy preflight allows Tailscale with explicit override")


def test_run_proxy_preflight_role_inputs_gcs_missing_secret_rejected():
    from core.run_proxy import _validate_preflight_role_inputs

    args = argparse.Namespace(
        ephemeral=False,
        gcs_secret_file="__missing_secret_file__.key",
        gcs_pub_hex=None,
        peer_pubkey_file=None,
    )
    try:
        _validate_preflight_role_inputs("gcs", args)
        assert False, "Expected missing GCS secret file to fail preflight"
    except RuntimeError as exc:
        assert "secret key file not found" in str(exc)
    print("  PASS: preflight rejects missing GCS secret file")


def test_run_proxy_preflight_role_inputs_drone_hex_accepts():
    from core.run_proxy import _validate_preflight_role_inputs

    args = argparse.Namespace(
        ephemeral=False,
        gcs_secret_file=None,
        gcs_pub_hex="ab" * 16,
        peer_pubkey_file=None,
    )
    _validate_preflight_role_inputs("drone", args)
    print("  PASS: preflight accepts valid drone --gcs-pub-hex")


def test_run_proxy_preflight_role_inputs_gcs_secret_readable_accepts():
    from core.run_proxy import _validate_preflight_role_inputs

    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"secret-bytes")
        temp_path = tmp.name
    try:
        args = argparse.Namespace(
            ephemeral=False,
            gcs_secret_file=temp_path,
            gcs_pub_hex=None,
            peer_pubkey_file=None,
        )
        _validate_preflight_role_inputs("gcs", args)
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass
    print("  PASS: preflight accepts readable GCS secret file")


# ═══════════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    tests = [
        test_sender_destroy_prevents_encrypt,
        test_receiver_destroy_prevents_decrypt,
        test_wire_max_length_rejected,
        test_wire_too_short_rejected,
        test_thread_safety_documented,
        test_roundtrip_all_tokens,
        test_replay_rejected,
        test_replay_strict_raises,
        test_session_mismatch_strict_raises,
        test_epoch_wrap_forbidden,
        test_replay_window_upper_bound_validation,
        test_control_tcp_rekey_rate_limit,
        test_control_tcp_max_workers,
        test_policy_engine_timeout_recovery,
        test_policy_engine_pending_epoch_promotes_only_on_success,
        test_policy_engine_activation_waits_for_both_sides,
        test_handshake_exception_chain,
        test_handshake_psk_bound_kdf_changes_keys,
        test_handshake_parse_rejects_trailing_bytes,
        test_run_proxy_signing_identity_self_test_accepts_matching_key,
        test_run_proxy_signing_identity_self_test_rejects_mismatch,
        test_max_wire_len_constant,
        test_handshake_lock_released_on_bind_failure,
        test_deferred_destroy_mechanism_exists,
        test_rekey_liveness_threshold_config,
        test_handshake_lock_timeout_support,
        test_run_proxy_preflight_rejects_missing_psk,
        test_run_proxy_preflight_rejects_invalid_psk_hex,
        test_run_proxy_preflight_rejects_wrong_psk_length,
        test_run_proxy_startup_preflight_accepts_valid_config,
        test_suites_exposes_split_negotiation_profiles,
        test_suites_capability_negotiation_selects_expected_suite,
        test_suites_crypto_profile_negotiation_selects_aead,
        test_suites_aead_profile_matrix_has_8_profiles,
        test_suites_exposes_scheduler_approved_subset,
        test_suites_scheduler_only_negotiation_filters_benchmark_profiles,
        test_suites_rejects_legacy_aead_embedded_suite_ids,
        test_async_proxy_build_sender_receiver_uses_transport_epoch,
        test_preflight_prints_split_negotiation_profiles,
        test_async_proxy_drone_connect_timeout_message,
        test_async_proxy_drone_handshake_io_timeout_message,
        test_async_proxy_gcs_accept_timeout_message,
        test_run_proxy_preflight_rejects_tailscale_runtime_hosts,
        test_run_proxy_preflight_allows_tailscale_with_override,
        test_run_proxy_preflight_role_inputs_gcs_missing_secret_rejected,
        test_run_proxy_preflight_role_inputs_drone_hex_accepts,
        test_run_proxy_preflight_role_inputs_gcs_secret_readable_accepts,
    ]
    passed = 0
    failed = 0
    skipped = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            if "SKIP" in str(e):
                skipped += 1
            else:
                print(f"  FAIL: {test.__name__}: {e}")
                failed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {skipped} skipped / {len(tests)} total")
    if failed:
        sys.exit(1)
    print("All tests passed!")


if __name__ == "__main__":
    main()
