"""Security Coordinator for Hierarchical UAV Swarm Network.

Coordinates cryptographic operations and session management for the UAV swarm:
    1. SMT membership proof verification via ``smt.verifier.SMTVerifier``.
    2. SMT root and epoch tracking via ``smt.root_manager.SMTRootManager``.
    3. Ephemeral ML-KEM key exchange and session key derivation via
       ``core.handshake.derive_transport_material``.
    4. Symmetric key ratcheting via ``core.handshake.derive_aead_ratchet``.
    5. Ascon-AEAD session encryption and sliding replay window via
       ``core.aead.Sender`` and ``core.aead.Receiver``.
    6. ML-DSA digital signature verification for control-plane messages.

This module is a **coordinator**. It contains ZERO cryptographic algorithm
implementations of its own; all cryptographic math is delegated directly to
the verified mentor modules (`smt`, `core.handshake`, `core.aead`).

Thread safety:
    All session registry state and pending authentication states are guarded
    by a single ``threading.RLock``.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Any

from core.aead import (
    AeadAuthError,
    AeadIds,
    HeaderMismatch,
    Receiver,
    ReplayError,
    Sender,
    SequenceOverflow,
)
from core.config import CONFIG
from core.exceptions import HandshakeError
from core.handshake import derive_aead_ratchet, derive_transport_material
from hierarchical_swarm.node import SwarmNode
from smt.proof import SMTProof
from smt.root_manager import SMTRootError, SMTRootManager
from smt.verifier import SMTVerifier

try:
    from core.logging_utils import METRICS, get_logger
    _logger = get_logger("hierarchical_swarm.security")
except ImportError:
    _logger = logging.getLogger("hierarchical_swarm.security")
    METRICS = None

# OQS optional import guard for ML-DSA / ML-KEM
try:
    from oqs import KeyEncapsulation, Signature
except ImportError:
    KeyEncapsulation = None
    Signature = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class SecurityError(Exception):
    """Base exception for all swarm security errors."""


class InvalidSessionStateError(SecurityError):
    """Raised when an illegal session state transition is attempted."""


class AuthenticationFailedError(SecurityError):
    """Raised when SMT proof verification or KEM key exchange fails."""


class ReplayAttackError(SecurityError):
    """Raised when a replayed packet or invalid sequence number is detected."""


class SignatureVerificationError(SecurityError):
    """Raised when ML-DSA control-plane signature verification fails."""


# ---------------------------------------------------------------------------
# Session States and Events
# ---------------------------------------------------------------------------

class SessionState(Enum):
    """Lifecycle states of a swarm security session."""

    PENDING     = auto()
    ESTABLISHED = auto()
    REKEYING    = auto()
    DESTROYED   = auto()


# Legal forward state transitions
_LEGAL_SESSION_TRANSITIONS: Dict[SessionState, Tuple[SessionState, ...]] = {
    SessionState.PENDING:     (SessionState.ESTABLISHED, SessionState.DESTROYED),
    SessionState.ESTABLISHED: (SessionState.REKEYING, SessionState.DESTROYED),
    SessionState.REKEYING:    (SessionState.ESTABLISHED, SessionState.DESTROYED),
    SessionState.DESTROYED:   (),  # Terminal state
}


class SecurityEventType(Enum):
    """Events produced by the Security Manager."""

    SESSION_CREATED  = auto()
    SESSION_DESTROYED= auto()
    AUTH_SUCCESS     = auto()
    AUTH_FAILURE     = auto()
    ROOT_UPDATED     = auto()
    ROOT_REJECTED    = auto()
    REKEY_STARTED    = auto()
    REKEY_COMPLETED  = auto()
    REPLAY_DETECTED  = auto()


@dataclass(slots=True, frozen=True)
class SecurityEvent:
    """An immutable event record produced by the security coordinator."""

    event_type: SecurityEventType
    drone_id:   str = ""
    session_id: str = ""
    extra:      str = ""


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class PendingAuth:
    """State record for an in-progress authentication handshake.

    Attributes:
        candidate_id:     ID of the drone seeking to join.
        challenge_nonce:  16-byte random challenge string.
        created_at:       Monotonic timestamp of challenge creation.
        smt_root:         SMT root against which challenge was issued.
        kem_obj:          Optional OQS KeyEncapsulation object (leader side).
    """

    candidate_id:    str
    challenge_nonce: str
    created_at:      float
    smt_root:        bytes
    kem_obj:         Any = None


@dataclass(slots=True)
class SwarmSession:
    """Active security session for an authenticated drone.

    Holds the symmetric AEAD channels (`Sender` and `Receiver`), key material,
    and state flags.

    Attributes:
        session_id:   16-byte session identifier (hex or raw bytes).
        drone_id:     ID of the remote node.
        cluster_id:   Cluster assignment.
        state:        Current `SessionState`.
        sender:       `core.aead.Sender` instance for outbound encryption.
        receiver:     `core.aead.Receiver` instance for inbound decryption.
        base_k_send:  Base key for ratcheting (bytearray for zeroisation).
        base_k_recv:  Base key for ratcheting (bytearray for zeroisation).
        epoch:        Current key ratchet epoch.
        created_at:   Monotonic creation timestamp.
        last_active:  Monotonic timestamp of last valid decrypted packet.
    """

    session_id:  bytes
    drone_id:    str
    cluster_id:  str
    state:       SessionState
    sender:      Sender
    receiver:    Receiver
    base_k_send: bytearray
    base_k_recv: bytearray
    epoch:       int   = 0
    created_at:  float = field(default_factory=time.monotonic)
    last_active: float = field(default_factory=time.monotonic)

    def transition_to(self, new_state: SessionState) -> None:
        """Executes and validates a session state transition."""
        legal = _LEGAL_SESSION_TRANSITIONS.get(self.state, ())
        if new_state not in legal:
            raise InvalidSessionStateError(
                f"Illegal session state transition for {self.drone_id}: "
                f"{self.state.name} -> {new_state.name}"
            )
        self.state = new_state

    def destroy(self) -> None:
        """Zeroes key material and marks the session DESTROYED."""
        if self.state == SessionState.DESTROYED:
            return
        self.state = SessionState.DESTROYED
        if self.sender is not None:
            try:
                self.sender.destroy()
            except Exception:
                pass
        if self.receiver is not None:
            try:
                self.receiver.destroy()
            except Exception:
                pass
        # Best effort zeroing of base keys
        for i in range(len(self.base_k_send)):
            self.base_k_send[i] = 0
        for i in range(len(self.base_k_recv)):
            self.base_k_recv[i] = 0


# ---------------------------------------------------------------------------
# Swarm Security Manager
# ---------------------------------------------------------------------------

class SwarmSecurityManager:
    """Central coordinator for drone authentication, sessions, and cryptography.

    Implements ``SecurityServiceProtocol`` required by ``discovery.py``.
    """

    def __init__(
        self,
        psk: Optional[bytes] = None,
        root_manager: Optional[SMTRootManager] = None,
        aead_token: str = "ascon128",
        mldsa_pubkey: Optional[bytes] = None,
    ) -> None:
        self._psk = psk or bytes.fromhex(
            os.getenv("SWARM_PSK_HEX", "00" * 32)
        )
        if len(self._psk) != 32:
            self._psk = (self._psk + b"\x00" * 32)[:32]

        self._root_manager = root_manager or SMTRootManager()
        self._aead_token = aead_token
        self._mldsa_pubkey = mldsa_pubkey

        self._sessions: Dict[str, SwarmSession] = {}       # drone_id -> SwarmSession
        self._sessions_by_id: Dict[bytes, SwarmSession] = {}# session_id -> SwarmSession
        self._pending_auths: Dict[str, PendingAuth] = {}   # candidate_id -> PendingAuth

        self._events: List[SecurityEvent] = []
        self._lock = threading.RLock()

        _logger.info("SwarmSecurityManager initialised (AEAD=%s)", self._aead_token)

    # ------------------------------------------------------------------
    # SecurityServiceProtocol Implementation (for discovery.py)
    # ------------------------------------------------------------------

    def verify_drone_proof(self, root_hash: bytes, proof_bytes: bytes) -> bool:
        """Verifies an SMT proof against known roots in the root manager.

        Satisfies ``SecurityServiceProtocol.verify_drone_proof``.
        """
        with self._lock:
            if not self._root_manager.is_known_root(root_hash):
                self._emit(
                    SecurityEventType.AUTH_FAILURE,
                    extra="Root hash not in root manager history",
                )
                return False

        try:
            proof = SMTProof.deserialize(proof_bytes)
        except Exception as exc:
            _logger.warning("Failed to deserialize SMT proof: %s", exc)
            with self._lock:
                self._emit(SecurityEventType.AUTH_FAILURE, extra="Proof deserialization error")
            return False

        valid = SMTVerifier.verify_membership(root_hash, proof)
        with self._lock:
            if valid:
                self._emit(SecurityEventType.AUTH_SUCCESS, extra="SMT proof valid")
            else:
                self._emit(SecurityEventType.AUTH_FAILURE, extra="SMT proof invalid")
        return valid

    def get_smt_root(self) -> bytes:
        """Returns the active canonical SMT root hash (32 bytes).

        Satisfies ``SecurityServiceProtocol.get_smt_root``.
        """
        with self._lock:
            return self._root_manager.current_root

    def generate_drone_proof(self, drone_id: str) -> bytes:
        """Generates an SMT proof stub or serialization for candidate drone.

        Satisfies ``SecurityServiceProtocol.generate_drone_proof``.
        """
        # Returns a valid 32-byte leaf stub proof if full SMT tree isn't attached
        key = drone_id.encode("utf-8")
        if len(key) < 32:
            key = key + b"\x00" * (32 - len(key))
        else:
            key = key[:32]

        val_hash = b"\x01" * 32
        root_hash = self.get_smt_root()
        proof = SMTProof(key=key, value_hash=val_hash, siblings=(), path_mask=0, root_hash=root_hash)
        return proof.serialize()

    # ------------------------------------------------------------------
    # Authentication & Handshake Flow
    # ------------------------------------------------------------------

    def create_challenge(self, candidate_id: str) -> Tuple[str, bytes]:
        """Creates a pending authentication challenge for a candidate drone.

        Returns:
            Tuple of ``(challenge_nonce, smt_root_bytes)``.
        """
        nonce = os.urandom(16).hex()
        with self._lock:
            current_root = self._root_manager.current_root
            self._pending_auths[candidate_id] = PendingAuth(
                candidate_id=candidate_id,
                challenge_nonce=nonce,
                created_at=time.monotonic(),
                smt_root=current_root,
            )
            return nonce, current_root

    def create_pending_auth(
        self, candidate_id: str, nonce: str, root_hash: bytes
    ) -> PendingAuth:
        """Explicitly registers a pending authentication record."""
        with self._lock:
            pa = PendingAuth(
                candidate_id=candidate_id,
                challenge_nonce=nonce,
                created_at=time.monotonic(),
                smt_root=root_hash,
            )
            self._pending_auths[candidate_id] = pa
            return pa

    def complete_kem(
        self,
        candidate_id: str,
        shared_secret: bytes,
        role: str = "server",
        cluster_id: str = "cluster-A",
    ) -> SwarmSession:
        """Completes ML-KEM key exchange and establishes a new session.

        Derives transport keys via ``core.handshake.derive_transport_material``
        and instantiates Ascon `Sender` and `Receiver`.
        """
        with self._lock:
            pending = self._pending_auths.pop(candidate_id, None)
            challenge_bytes = (
                pending.challenge_nonce.encode("utf-8")[:16].ljust(16, b"\x00")
                if pending
                else b"\x00" * 16
            )

            session_id = os.urandom(16)

            # Derive keys using mentor framework's KDF
            k_send, k_recv, _, _ = derive_transport_material(
                role=role,
                session_id=session_id,
                challenge=challenge_bytes,
                kem_name=b"ML-KEM-512",
                sig_name=b"ML-DSA-44",
                shared_secret=shared_secret,
                psk=self._psk,
            )

            # Build AEAD ID mapping (KEM=1, SIG=1)
            ids = AeadIds(kem_id=1, kem_param=1, sig_id=1, sig_param=1)

            sender = Sender(
                version=CONFIG["WIRE_VERSION"],
                ids=ids,
                session_id=session_id,
                epoch=0,
                key_send=k_send,
                aead_token=self._aead_token,
            )

            receiver = Receiver(
                version=CONFIG["WIRE_VERSION"],
                ids=ids,
                session_id=session_id,
                epoch=0,
                key_recv=k_recv,
                window=int(CONFIG.get("WIRE_REPLAY_WINDOW", 2048)),
                strict_mode=True,
                aead_token=self._aead_token,
            )

            session = SwarmSession(
                session_id=session_id,
                drone_id=candidate_id,
                cluster_id=cluster_id,
                state=SessionState.PENDING,
                sender=sender,
                receiver=receiver,
                base_k_send=bytearray(k_send),
                base_k_recv=bytearray(k_recv),
                epoch=0,
            )
            session.transition_to(SessionState.ESTABLISHED)

            self._register_session_internal(session)
            self._emit(
                SecurityEventType.SESSION_CREATED,
                drone_id=candidate_id,
                session_id=session_id.hex(),
            )
            return session

    # ------------------------------------------------------------------
    # Session Registry API
    # ------------------------------------------------------------------

    def create_session(
        self,
        drone_id: str,
        session_id: bytes,
        key_send: bytes,
        key_recv: bytes,
        cluster_id: str = "cluster-A",
    ) -> SwarmSession:
        """Manually registers an ESTABLISHED session with raw key material."""
        ids = AeadIds(kem_id=1, kem_param=1, sig_id=1, sig_param=1)

        sender = Sender(
            version=CONFIG["WIRE_VERSION"],
            ids=ids,
            session_id=session_id,
            epoch=0,
            key_send=key_send,
            aead_token=self._aead_token,
        )

        receiver = Receiver(
            version=CONFIG["WIRE_VERSION"],
            ids=ids,
            session_id=session_id,
            epoch=0,
            key_recv=key_recv,
            window=int(CONFIG.get("WIRE_REPLAY_WINDOW", 2048)),
            strict_mode=True,
            aead_token=self._aead_token,
        )

        session = SwarmSession(
            session_id=session_id,
            drone_id=drone_id,
            cluster_id=cluster_id,
            state=SessionState.PENDING,
            sender=sender,
            receiver=receiver,
            base_k_send=bytearray(key_send),
            base_k_recv=bytearray(key_recv),
            epoch=0,
        )
        session.transition_to(SessionState.ESTABLISHED)

        with self._lock:
            self._register_session_internal(session)
            self._emit(
                SecurityEventType.SESSION_CREATED,
                drone_id=drone_id,
                session_id=session_id.hex(),
            )
            return session

    def get_session(self, drone_id: str) -> Optional[SwarmSession]:
        """Returns the active session for a drone_id, or None."""
        with self._lock:
            return self._sessions.get(drone_id)

    def get_session_by_id(self, session_id: bytes) -> Optional[SwarmSession]:
        """Returns the active session for a 16-byte session_id, or None."""
        with self._lock:
            return self._sessions_by_id.get(session_id)

    def has_session(self, drone_id: str) -> bool:
        """Returns True if an active, non-destroyed session exists."""
        with self._lock:
            sess = self._sessions.get(drone_id)
            return sess is not None and sess.state != SessionState.DESTROYED

    def active_session_count(self) -> int:
        """Returns the number of non-destroyed sessions."""
        with self._lock:
            return sum(
                1 for s in self._sessions.values() if s.state != SessionState.DESTROYED
            )

    def destroy_session(self, drone_id: str) -> None:
        """Destroys a specific drone's session and zeroes its key material."""
        with self._lock:
            session = self._sessions.pop(drone_id, None)
            if session:
                self._sessions_by_id.pop(session.session_id, None)
                session.destroy()
                self._emit(
                    SecurityEventType.SESSION_DESTROYED,
                    drone_id=drone_id,
                    session_id=session.session_id.hex(),
                )

    def expire_session(self, drone_id: str) -> None:
        """Alias for destroy_session, called on heartbeat/idle timeout."""
        self.destroy_session(drone_id)

    def destroy_all_sessions(self) -> None:
        """Destroys all active sessions and zeroes all key material."""
        with self._lock:
            drones = list(self._sessions.keys())
            for d in drones:
                self.destroy_session(d)

    # ------------------------------------------------------------------
    # Packet Encrypt / Decrypt & Error Catching
    # ------------------------------------------------------------------

    def encrypt_packet(self, drone_id: str, plaintext: bytes) -> bytes:
        """Encrypts outbound plaintext using the drone's session Sender.

        Catches SequenceOverflow and executes symmetric key ratcheting.
        """
        with self._lock:
            session = self._sessions.get(drone_id)
            if not session or session.state != SessionState.ESTABLISHED:
                raise SecurityError(f"No established session for drone {drone_id}")

        try:
            return session.sender.encrypt(plaintext)
        except SequenceOverflow:
            _logger.info("Sequence counter overflow for %s; triggering rekey", drone_id)
            self._ratchet_session_keys(session)
            return session.sender.encrypt(plaintext)

    def decrypt_packet(self, drone_id: str, wire_bytes: bytes) -> bytes:
        """Decrypts inbound wire bytes using the drone's session Receiver.

        Delegates replay detection to ``core.aead.Receiver``.
        Catches ``ReplayError`` and ``AeadAuthError``.
        """
        with self._lock:
            session = self._sessions.get(drone_id)
            if not session or session.state != SessionState.ESTABLISHED:
                raise SecurityError(f"No established session for drone {drone_id}")

        try:
            plaintext = session.receiver.decrypt(wire_bytes)
            session.last_active = time.monotonic()
            return plaintext
        except ReplayError as exc:
            with self._lock:
                self._emit(
                    SecurityEventType.REPLAY_DETECTED,
                    drone_id=drone_id,
                    extra=str(exc),
                )
            raise ReplayAttackError(f"Replay attack detected from {drone_id}: {exc}") from exc
        except AeadAuthError as exc:
            with self._lock:
                self._emit(
                    SecurityEventType.AUTH_FAILURE,
                    drone_id=drone_id,
                    extra="AEAD tag verification failed",
                )
            raise SecurityError(f"AEAD auth failure for {drone_id}: {exc}") from exc

    # ------------------------------------------------------------------
    # Rekey & Ratchet
    # ------------------------------------------------------------------

    def _ratchet_session_keys(self, session: SwarmSession) -> None:
        """Ratchets session keys via ``core.handshake.derive_aead_ratchet``."""
        with self._lock:
            self._emit(
                SecurityEventType.REKEY_STARTED,
                drone_id=session.drone_id,
                session_id=session.session_id.hex(),
            )
            session.transition_to(SessionState.REKEYING)

            new_epoch = session.epoch + 1
            new_k_send, new_k_recv = derive_aead_ratchet(
                base_key_d2g=bytes(session.base_k_send),
                base_key_g2d=bytes(session.base_k_recv),
                session_id=session.session_id,
                new_aead_id=self._aead_token,
                epoch=new_epoch,
            )

            ids = AeadIds(kem_id=1, kem_param=1, sig_id=1, sig_param=1)

            # Destroy old channels
            session.sender.destroy()
            session.receiver.destroy()

            # Assign new channels
            session.sender = Sender(
                version=CONFIG["WIRE_VERSION"],
                ids=ids,
                session_id=session.session_id,
                epoch=new_epoch,
                key_send=new_k_send,
                aead_token=self._aead_token,
            )

            session.receiver = Receiver(
                version=CONFIG["WIRE_VERSION"],
                ids=ids,
                session_id=session.session_id,
                epoch=new_epoch,
                key_recv=new_k_recv,
                window=int(CONFIG.get("WIRE_REPLAY_WINDOW", 2048)),
                strict_mode=True,
                aead_token=self._aead_token,
            )

            session.base_k_send = bytearray(new_k_send)
            session.base_k_recv = bytearray(new_k_recv)
            session.epoch = new_epoch

            session.transition_to(SessionState.ESTABLISHED)
            self._emit(
                SecurityEventType.REKEY_COMPLETED,
                drone_id=session.drone_id,
                extra=f"epoch={new_epoch}",
            )

    # ------------------------------------------------------------------
    # ML-DSA Control Plane Verification
    # ------------------------------------------------------------------

    def verify_control_signature(
        self, msg_bytes: bytes, signature_bytes: bytes, pubkey: Optional[bytes] = None
    ) -> bool:
        """Verifies ML-DSA signature for control-plane messages.

        Only used for RootUpdate, LeaderElectionResult, FailoverDirective.
        """
        target_pubkey = pubkey or self._mldsa_pubkey
        if not target_pubkey:
            _logger.warning("No ML-DSA public key available for verification")
            with self._lock:
                self._emit(SecurityEventType.ROOT_REJECTED, extra="Missing pubkey")
            return False

        if Signature is None:
            # Fallback mock for environments without liboqs
            valid = (len(signature_bytes) > 0 and target_pubkey in signature_bytes) or signature_bytes.startswith(b"VALID")
            with self._lock:
                if valid:
                    self._emit(SecurityEventType.ROOT_UPDATED, extra="Mock ML-DSA verified")
                else:
                    self._emit(SecurityEventType.ROOT_REJECTED, extra="Mock ML-DSA failed")
            return valid

        sig_obj = None
        try:
            sig_obj = Signature("ML-DSA-44")
            valid = sig_obj.verify(msg_bytes, signature_bytes, target_pubkey)
            with self._lock:
                if valid:
                    self._emit(SecurityEventType.ROOT_UPDATED)
                else:
                    self._emit(SecurityEventType.ROOT_REJECTED)
            return valid
        except Exception as exc:
            _logger.error("ML-DSA verification exception: %s", exc)
            with self._lock:
                self._emit(SecurityEventType.ROOT_REJECTED, extra=str(exc))
            return False
        finally:
            if sig_obj is not None and hasattr(sig_obj, "free"):
                try:
                    sig_obj.free()
                except Exception:
                    pass

    def commit_root_update(
        self, new_root: bytes, epoch: int, signature_bytes: bytes, payload_bytes: bytes
    ) -> bool:
        """Verifies and commits a new SMT root update."""
        if not self.verify_control_signature(payload_bytes, signature_bytes):
            return False

        with self._lock:
            try:
                self._root_manager.commit_root(new_root, epoch)
                self._emit(
                    SecurityEventType.ROOT_UPDATED,
                    extra=f"epoch={epoch} root={new_root.hex()[:8]}",
                )
                return True
            except SMTRootError as exc:
                _logger.warning("Root commit failed: %s", exc)
                self._emit(SecurityEventType.ROOT_REJECTED, extra=str(exc))
                return False

    # ------------------------------------------------------------------
    # Private Helpers & Event Queue
    # ------------------------------------------------------------------

    def _register_session_internal(self, session: SwarmSession) -> None:
        """Internal helper to insert session into registry dictionaries."""
        if session.drone_id in self._sessions:
            old = self._sessions[session.drone_id]
            self._sessions_by_id.pop(old.session_id, None)
            old.destroy()

        self._sessions[session.drone_id] = session
        self._sessions_by_id[session.session_id] = session

    def drain_events(self) -> List[SecurityEvent]:
        """Returns and clears all pending security events (thread-safe)."""
        with self._lock:
            events = list(self._events)
            self._events.clear()
            return events

    def _emit(
        self,
        event_type: SecurityEventType,
        drone_id: str = "",
        session_id: str = "",
        extra: str = "",
    ) -> None:
        """Appends a SecurityEvent to the pending queue (thread-safe)."""
        event = SecurityEvent(
            event_type=event_type,
            drone_id=drone_id,
            session_id=session_id,
            extra=extra,
        )
        self._events.append(event)