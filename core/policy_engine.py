"""
In-band control-plane state machine for interactive rekey negotiation.

Implements a two-phase commit protocol carried over packet type 0x02 payloads.
"""

from __future__ import annotations

import queue
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from core.suites import get_suite, normalize_aead_token_for_level


def _now_ms() -> int:
    """Return monotonic milliseconds for control timestamps."""

    return time.monotonic_ns() // 1_000_000


def _default_safe() -> bool:
    return True


def _normalize_aead_token(value: object) -> Optional[str]:
    """Normalize optional AEAD token hints carried in control messages."""

    if value is None:
        return None
    if not isinstance(value, str):
        return None
    token = value.strip().lower()
    if not token:
        return None
    return token


@dataclass
class HandshakeState:
    """Tracks the state of the KEM and Signature (PQC Asymmetric)."""
    active_profile: str
    pending_profile: Optional[str] = None
    last_rekey_ms: Optional[int] = None
    epoch: int = 0  # Monotonically increasing epoch to prevent protocol downgrade

@dataclass
class CipherState:
    """Tracks the state of the AEAD Data Plane (Symmetric Shift)."""
    active_profile: str
    pending_profile: Optional[str] = None
    last_shift_ms: Optional[int] = None
    epoch: int = 0  # Monotonically increasing epoch to prevent protocol downgrade

@dataclass
class ControlState:
    """Mutable control-plane state shared between proxy threads.
    Acts as a compatibility facade over HandshakeState and CipherState.
    """

    role: str
    coordinator_role: str
    
    # Internal split state backend
    handshake: HandshakeState = field(init=False)
    cipher: CipherState = field(init=False)

    # Legacy monolithic attribute maintained for facade compatibility
    current_suite: str
    current_aead: str = "aesgcm"
    safe_guard: Callable[[], bool] = field(default_factory=_default_safe)
    epoch: int = 0  # Active transport epoch
    pending_epoch: Optional[int] = None

    def __post_init__(self):
        self.handshake = HandshakeState(active_profile=getattr(self, 'current_suite', ''), epoch=getattr(self, 'epoch', 0))
        self.cipher = CipherState(active_profile=getattr(self, 'current_aead', 'aesgcm'), epoch=getattr(self, 'epoch', 0))

    def __setattr__(self, name: str, value: object) -> None:
        """Keep legacy facade fields synchronized with split state backends."""

        object.__setattr__(self, name, value)

        handshake = self.__dict__.get("handshake")
        cipher = self.__dict__.get("cipher")
        if not isinstance(handshake, HandshakeState) or not isinstance(cipher, CipherState):
            return

        if name == "current_suite":
            handshake.active_profile = str(value)
        elif name == "current_aead":
            cipher.active_profile = str(value)
        elif name == "epoch":
            try:
                epoch_value = int(value)
            except (TypeError, ValueError):
                return
            handshake.epoch = epoch_value
            cipher.epoch = epoch_value

    @property
    def pending_suite(self) -> Optional[str]:
        """Legacy-style facade for the currently negotiated suite, if any."""

        rid = self.active_rid
        if rid:
            pending = self.pending.get(rid)
            if pending:
                return pending
        return self.handshake.pending_profile or self.cipher.pending_profile

    @pending_suite.setter
    def pending_suite(self, suite_id: Optional[str]) -> None:
        rid = self.active_rid
        if suite_id is None:
            self.handshake.pending_profile = None
            self.cipher.pending_profile = None
            if rid:
                self.pending.pop(rid, None)
                self.pending_crypto.pop(rid, None)
            return

        suite_norm = str(suite_id)
        self.handshake.pending_profile = suite_norm
        self.cipher.pending_profile = suite_norm
        if rid:
            self.pending[rid] = suite_norm

    lock: threading.Lock = field(default_factory=threading.Lock)
    outbox: "queue.Queue[dict]" = field(default_factory=queue.Queue)
    pending: Dict[str, str] = field(default_factory=dict)
    pending_crypto: Dict[str, Dict[str, str]] = field(default_factory=dict)
    state: str = "RUNNING"
    state_since_ms: Optional[int] = None
    active_rid: Optional[str] = None
    local_rekey_ready: bool = False
    peer_rekey_ready: bool = False
    activation_sent: bool = False
    last_rekey_ms: Optional[int] = None
    last_rekey_suite: Optional[str] = None
    last_status: Optional[Dict[str, object]] = None
    stats: Dict[str, int] = field(default_factory=lambda: {
        "prepare_sent": 0,
        "prepare_received": 0,
        "rekeys_ok": 0,
        "rekeys_fail": 0,
    })
    seen_rids: deque[str] = field(default_factory=lambda: deque(maxlen=256))


@dataclass
class ControlResult:
    """Outcome of processing a control message."""

    send: List[dict] = field(default_factory=list)
    start_handshake: Optional[Tuple[str, str]] = None  # (suite_id, rid)
    activate_rekey: Optional[Tuple[str, str]] = None  # (suite_id, rid)
    notes: List[str] = field(default_factory=list)


def create_control_state(
    role: str,
    suite_id: str,
    *,
    safe_guard: Callable[[], bool] | None = None,
    aead_token: str = "aesgcm",
) -> ControlState:
    """Initialise ControlState with the provided role and suite."""

    guard = safe_guard or _default_safe
    return ControlState(
        role=role,
        coordinator_role="gcs",
        current_suite=suite_id,
        current_aead=aead_token,
        safe_guard=guard,
    )


def set_coordinator_role(state: ControlState, coordinator_role: str) -> None:
    """Set the coordinator role for the in-band rekey control-plane.

    coordinator_role must be either "gcs" or "drone".
    """

    role_norm = str(coordinator_role).strip().lower()
    if role_norm not in {"gcs", "drone"}:
        raise ValueError("invalid coordinator_role")
    with state.lock:
        state.coordinator_role = role_norm


def normalize_coordinator_role(value: object, *, default: str = "gcs") -> str:
    """Normalize coordinator roles to a safe value.

    Accepts arbitrary inputs and returns either "gcs" or "drone".
    """

    try:
        role_norm = str(value).strip().lower()
    except Exception:
        role_norm = ""

    if role_norm in {"gcs", "drone"}:
        return role_norm
    return "gcs" if default not in {"gcs", "drone"} else default


def coordinator_role_from_config(cfg: dict, *, default: str = "gcs") -> str:
    """Fetch and normalize CONTROL_COORDINATOR_ROLE from a config mapping."""

    if not isinstance(cfg, dict):
        return normalize_coordinator_role(default, default="gcs")
    return normalize_coordinator_role(cfg.get("CONTROL_COORDINATOR_ROLE", default), default=default)


def is_coordinator(*, role: str, coordinator_role: str) -> bool:
    """Return True if this proxy role is the coordinator role."""

    return normalize_coordinator_role(role) == normalize_coordinator_role(coordinator_role)


def generate_rid() -> str:
    """Generate a random 64-bit hex request identifier."""

    return secrets.token_hex(8)


def enqueue_json(state: ControlState, payload: dict) -> None:
    """Place an outbound JSON payload onto the control outbox."""

    state.outbox.put(payload)


def get_pending_profile(state: ControlState, rid: str) -> Dict[str, str]:
    """Return pending crypto profile for rid (always includes suite_id)."""

    with state.lock:
        profile = dict(state.pending_crypto.get(rid, {}))
        suite_id = state.pending.get(rid)
    if not profile and suite_id:
        profile = {"suite_id": suite_id}
    elif suite_id:
        profile.setdefault("suite_id", suite_id)
    return profile


def request_prepare(state: ControlState, suite_id: str, *, aead_token: Optional[str] = None) -> str:
    """Queue a prepare_rekey message and transition to NEGOTIATING."""

    rid = generate_rid()
    now = _now_ms()
    normalized_aead = _normalize_aead_token(aead_token)
    if normalized_aead:
        try:
            normalized_aead = normalize_aead_token_for_level(
                normalized_aead,
                str(get_suite(suite_id).get("nist_level", "")),
            )
        except Exception:
            normalized_aead = _normalize_aead_token(aead_token)
    with state.lock:
        if state.state != "RUNNING":
            raise RuntimeError("control-plane already negotiating")

        # Stage the next transport epoch, but keep the active epoch unchanged
        # until the rekey is fully activated on both sides.
        new_epoch = state.epoch + 1
        state.pending_epoch = new_epoch

        state.pending[rid] = suite_id
        pending_profile: Dict[str, str] = {"suite_id": suite_id}
        if normalized_aead:
            pending_profile["aead_token"] = normalized_aead
        state.pending_crypto[rid] = pending_profile
        state.active_rid = rid
        state.local_rekey_ready = False
        state.peer_rekey_ready = False
        state.activation_sent = False
        state.pending_suite = suite_id
        state.state = "NEGOTIATING"
        state.state_since_ms = now
        state.stats["prepare_sent"] += 1
        current_aead = state.current_aead

    msg_aead = normalized_aead if normalized_aead else current_aead
    enqueue_json(
        state,
        {
            "type": "prepare_rekey",
            "suite": suite_id,
            "aead": msg_aead,
            "rid": rid,
            "t_ms": now,
            "epoch": new_epoch,
        },
    )
    return rid


def note_local_rekey_ready(state: ControlState, rid: str) -> bool:
    """Mark the local side as having staged the next rekey context.

    Returns True when the peer is already ready and activation may proceed.
    """

    with state.lock:
        if rid != state.active_rid or rid not in state.pending:
            raise RuntimeError("unknown_rid")
        state.local_rekey_ready = True
        state.state = "SWAPPING"
        state.state_since_ms = _now_ms()
        return state.peer_rekey_ready and not state.activation_sent


def note_peer_rekey_ready(state: ControlState, rid: str) -> bool:
    """Mark the peer side as having staged the next rekey context.

    Returns True when the local side is already ready and activation may proceed.
    """

    with state.lock:
        if rid != state.active_rid or rid not in state.pending:
            raise RuntimeError("unknown_rid")
        state.peer_rekey_ready = True
        state.state = "SWAPPING"
        state.state_since_ms = _now_ms()
        return state.local_rekey_ready and not state.activation_sent


def mark_activation_sent(state: ControlState, rid: str) -> Dict[str, str]:
    """Latch activation for the active rid and return its pending profile."""

    with state.lock:
        if rid != state.active_rid or rid not in state.pending:
            raise RuntimeError("unknown_rid")
        if state.activation_sent:
            raise RuntimeError("activation_already_sent")
        state.activation_sent = True
        profile = dict(state.pending_crypto.get(rid, {}))
        suite_id = state.pending.get(rid)
    if suite_id:
        profile.setdefault("suite_id", suite_id)
    return profile


def record_rekey_result(
    state: ControlState,
    rid: str,
    suite_id: str,
    *,
    success: bool,
    aead_token: Optional[str] = None,
) -> None:
    """Record outcome of a rekey attempt and enqueue status update."""

    now = _now_ms()
    normalized_aead = _normalize_aead_token(aead_token)
    status_payload = {
        "type": "status",
        "state": "RUNNING",
        "suite": suite_id if success else state.current_suite,
        "aead": normalized_aead if success and normalized_aead else state.current_aead,
        "rid": rid,
        "result": "ok" if success else "fail",
        "t_ms": now,
    }
    with state.lock:
        if success:
            if state.pending_epoch is not None:
                state.epoch = state.pending_epoch
            state.current_suite = suite_id
            if normalized_aead:
                state.current_aead = normalized_aead
            state.last_rekey_suite = suite_id
            state.handshake.last_rekey_ms = now
            state.cipher.last_shift_ms = now
            state.last_rekey_ms = now
            state.stats["rekeys_ok"] += 1
        else:
            state.stats["rekeys_fail"] += 1
        state.pending.pop(rid, None)
        state.pending_crypto.pop(rid, None)
        state.pending_epoch = None
        state.pending_suite = None
        state.active_rid = None
        state.local_rekey_ready = False
        state.peer_rekey_ready = False
        state.activation_sent = False
        state.state = "RUNNING"
        state.state_since_ms = None
    enqueue_json(state, status_payload)


def tick_state_timeouts(
    state: ControlState,
    *,
    negotiating_timeout_ms: int,
    swapping_timeout_ms: int,
    now_ms: Optional[int] = None,
) -> Optional[dict]:
    """Recover from stale NEGOTIATING/SWAPPING state and emit fail status payload."""

    now = _now_ms() if now_ms is None else int(now_ms)
    with state.lock:
        phase = state.state
        if phase not in {"NEGOTIATING", "SWAPPING"}:
            return None
        started_ms = state.state_since_ms
        if started_ms is None:
            state.state_since_ms = now
            return None

        timeout_ms = int(negotiating_timeout_ms if phase == "NEGOTIATING" else swapping_timeout_ms)
        if timeout_ms <= 0:
            timeout_ms = 1
        if now - started_ms < timeout_ms:
            return None

        rid = state.active_rid or "unknown"
        timed_out_profile = dict(state.pending_crypto.get(rid, {}))
        suite = timed_out_profile.get("suite_id") or state.pending.get(rid) or state.current_suite
        aead = timed_out_profile.get("aead_token") or state.current_aead

        state.pending.pop(rid, None)
        state.pending_crypto.pop(rid, None)
        state.pending_epoch = None
        state.pending_suite = None
        state.active_rid = None
        state.local_rekey_ready = False
        state.peer_rekey_ready = False
        state.activation_sent = False
        state.state = "RUNNING"
        state.state_since_ms = None
        state.stats["rekeys_fail"] += 1
        state.seen_rids.append(rid)

    return {
        "type": "status",
        "state": "RUNNING",
        "suite": suite,
        "aead": aead,
        "rid": rid,
        "result": "fail",
        "reason": f"timeout_{phase.lower()}",
        "t_ms": now,
    }


def handle_control(msg: dict, role: str, state: ControlState) -> ControlResult:
    """Process inbound control JSON and return actions for the proxy."""

    result = ControlResult()
    msg_type = msg.get("type")
    if not isinstance(msg_type, str):
        result.notes.append("missing_type")
        return result

    rid = msg.get("rid")
    now = _now_ms()

    coordinator_role = state.coordinator_role
    is_coordinator = role == coordinator_role

    if is_coordinator:
        if msg_type == "prepare_ok" and isinstance(rid, str):
            with state.lock:
                suite = state.pending.get(rid)
                profile = dict(state.pending_crypto.get(rid, {}))
                current_aead = state.current_aead
                if not suite:
                    result.notes.append("unknown_rid")
                    return result
                state.state = "SWAPPING"
                state.state_since_ms = now
                state.seen_rids.append(rid)
            aead_token = _normalize_aead_token(profile.get("aead_token")) if profile else None
            result.send.append({
                "type": "commit_rekey",
                "suite": suite,
                "aead": aead_token if aead_token else current_aead,
                "rid": rid,
                "t_ms": now,
            })
            result.start_handshake = (suite, rid)
        elif msg_type == "activate_ok" and isinstance(rid, str):
            try:
                ready_to_activate = note_peer_rekey_ready(state, rid)
            except RuntimeError:
                result.notes.append("unknown_activate_rid")
                return result
            if ready_to_activate:
                try:
                    profile = mark_activation_sent(state, rid)
                except RuntimeError as exc:
                    result.notes.append(str(exc))
                    return result
                suite = profile.get("suite_id", "")
                aead_token = _normalize_aead_token(profile.get("aead_token"))
                result.send.append({
                    "type": "activate_rekey",
                    "suite": suite,
                    "aead": aead_token,
                    "rid": rid,
                    "t_ms": now,
                })
        elif msg_type == "activate_fail" and isinstance(rid, str):
            reason = msg.get("reason", "unknown")
            with state.lock:
                state.pending.pop(rid, None)
                state.pending_crypto.pop(rid, None)
                state.pending_epoch = None
                state.pending_suite = None
                state.active_rid = None
                state.local_rekey_ready = False
                state.peer_rekey_ready = False
                state.activation_sent = False
                state.state = "RUNNING"
                state.state_since_ms = None
                state.stats["rekeys_fail"] += 1
                state.seen_rids.append(rid)
                state.last_status = dict(msg)
            result.notes.append(f"activate_fail:{reason}")
        elif msg_type == "prepare_fail" and isinstance(rid, str):
            reason = msg.get("reason", "unknown")
            with state.lock:
                state.pending.pop(rid, None)
                state.pending_crypto.pop(rid, None)
                state.pending_epoch = None
                state.pending_suite = None
                state.active_rid = None
                state.local_rekey_ready = False
                state.peer_rekey_ready = False
                state.activation_sent = False
                state.state = "RUNNING"
                state.state_since_ms = None
                state.stats["rekeys_fail"] += 1
                state.seen_rids.append(rid)
            result.notes.append(f"prepare_fail:{reason}")
        elif msg_type == "status":
            with state.lock:
                state.last_status = msg
        else:
            result.notes.append(f"ignored:{msg_type}")
        return result

    if msg_type == "prepare_rekey":
        suite = msg.get("suite")
        incoming_aead = _normalize_aead_token(msg.get("aead"))
        incoming_epoch = msg.get("epoch", -1)
        
        if not isinstance(rid, str) or not isinstance(suite, str) or not isinstance(incoming_epoch, int):
            result.notes.append("invalid_prepare")
            return result

        with state.lock:
            reason = "unsafe"
            known_epoch = state.epoch
            if state.pending_epoch is not None:
                known_epoch = max(known_epoch, state.pending_epoch)
            if incoming_epoch <= known_epoch and incoming_epoch != -1:
                # Monotonic epoch guard: reject rollback or replay unless it's legacy without epoch
                allow = False
                reason = "downgrade_rejected"
            elif rid in state.seen_rids:
                allow = False
                reason = "duplicate_rid"
            else:
                allow = state.state == "RUNNING" and state.safe_guard()

            if allow:
                state.active_rid = rid
                if incoming_epoch >= 0:
                    state.pending_epoch = incoming_epoch

                state.pending[rid] = suite
                profile: Dict[str, str] = {"suite_id": suite}
                if incoming_aead:
                    profile["aead_token"] = incoming_aead
                state.pending_crypto[rid] = profile
                state.local_rekey_ready = False
                state.peer_rekey_ready = False
                state.activation_sent = False
                state.pending_suite = suite
                state.state = "NEGOTIATING"
                state.state_since_ms = now
                state.stats["prepare_received"] += 1
                state.seen_rids.append(rid)
        if allow:
            result.send.append({
                "type": "prepare_ok",
                "rid": rid,
                "t_ms": now,
            })
        else:
            result.send.append({
                "type": "prepare_fail",
                "rid": rid,
                "reason": reason,
                "t_ms": now,
            })
    elif msg_type == "commit_rekey" and isinstance(rid, str):
        with state.lock:
            suite = state.pending.get(rid)
            incoming_aead = _normalize_aead_token(msg.get("aead"))
            if not suite:
                result.notes.append("unknown_commit_rid")
                return result
            if incoming_aead:
                profile = dict(state.pending_crypto.get(rid, {}))
                profile["suite_id"] = suite
                profile["aead_token"] = incoming_aead
                state.pending_crypto[rid] = profile
            state.state = "SWAPPING"
            state.state_since_ms = now
        result.start_handshake = (suite, rid)
    elif msg_type == "activate_rekey" and isinstance(rid, str):
        with state.lock:
            suite = state.pending.get(rid)
            if not suite:
                result.notes.append("unknown_activate_rid")
                return result
            state.activation_sent = True
            state.state = "SWAPPING"
            state.state_since_ms = now
        result.activate_rekey = (suite, rid)
    elif msg_type == "activate_fail" and isinstance(rid, str):
        reason = msg.get("reason", "unknown")
        with state.lock:
            state.pending.pop(rid, None)
            state.pending_crypto.pop(rid, None)
            state.pending_epoch = None
            state.pending_suite = None
            state.active_rid = None
            state.local_rekey_ready = False
            state.peer_rekey_ready = False
            state.activation_sent = False
            state.state = "RUNNING"
            state.state_since_ms = None
            state.stats["rekeys_fail"] += 1
            state.seen_rids.append(rid)
            state.last_status = dict(msg)
        result.notes.append(f"activate_fail:{reason}")
    elif msg_type == "status":
        with state.lock:
            state.last_status = msg
    else:
        result.notes.append(f"ignored:{msg_type}")

    return result
