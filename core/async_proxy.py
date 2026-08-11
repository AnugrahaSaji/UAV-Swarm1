"""
Selectors-based network transport proxy.

Responsibilities:
1. Perform authenticated TCP handshake (PQC KEM + signature) using `core.handshake`.
2. Bridge plaintext UDP <-> encrypted UDP (AEAD framing) both directions.
3. Enforce replay window and per-direction sequence via `core.aead`.

Note: This module uses the low-level `selectors` stdlib facility—not `asyncio`—to
remain dependency-light and fully deterministic for test harnesses. The filename
is retained for backward compatibility; a future refactor may rename it to
`selector_proxy.py` and/or introduce an asyncio variant.
"""

from __future__ import annotations

import hashlib
import json
import queue
import socket
import selectors
import struct
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

from core.config import CONFIG
from core.suites import (
    SUITES,
    get_suite,
    header_ids_for_suite,
    list_suites,
    negotiation_profiles_for_suite,
)
try:
    # Optional helper (if you implemented it)
    from core.suites import header_ids_from_names  # type: ignore
except Exception:
    header_ids_from_names = None  # type: ignore

from core.handshake import client_drone_handshake, server_gcs_handshake, derive_aead_ratchet
from core.exceptions import HandshakeVerifyError, HandshakeError, HandshakeFormatError, AeadError
from core.logging_utils import get_logger

from core.aead import (
    AeadAuthError,
    AeadIds,
    HeaderMismatch,
    Receiver,
    ReplayError,
    Sender,
)
from core.aead import HEADER_STRUCT as AEAD_HEADER_STRUCT, HEADER_LEN as AEAD_HEADER_LEN
from core.exceptions import ConfigError, SequenceOverflow

from core.policy_engine import (
    ControlResult,
    ControlState,
    coordinator_role_from_config,
    create_control_state,
    get_pending_profile,
    handle_control,
    is_coordinator,
    mark_activation_sent,
    note_local_rekey_ready,
    record_rekey_result,
    request_prepare,
    set_coordinator_role,
    tick_state_timeouts,
)

from core.control_tcp import start_control_server_if_enabled

logger = get_logger("pqc")


def _is_windows_udp_reset(exc: BaseException) -> bool:
    """Return True for Windows UDP ICMP port-unreachable feedback."""

    if not sys.platform.startswith("win"):
        return False
    if isinstance(exc, ConnectionResetError):
        return True
    return getattr(exc, "winerror", None) == 10054


class ProxyCounters:
    """Simple counters for proxy statistics."""

    def __init__(self) -> None:
        self.ptx_out = 0      # plaintext packets sent out to app
        self.ptx_in = 0       # plaintext packets received from app
        self.enc_out = 0      # encrypted packets sent to peer
        self.enc_in = 0       # encrypted packets received from peer
        self.ptx_bytes_out = 0  # plaintext bytes sent out to app
        self.ptx_bytes_in = 0   # plaintext bytes received from app
        self.enc_bytes_out = 0  # encrypted bytes sent to peer
        self.enc_bytes_in = 0   # encrypted bytes received from peer
        self.drops = 0        # total drops
        # Granular drop reasons
        self.drop_replay = 0
        self.drop_auth = 0
        self.drop_header = 0
        self.drop_session_epoch = 0
        self.drop_other = 0
        self.drop_src_addr = 0
        self.sniff_drop = 0      # sniff copy sendto failures (invisible to collector)
        self.rekeys_ok = 0
        self.rekeys_fail = 0
        self.last_rekey_ms = 0
        self.last_rekey_suite: Optional[str] = None
        self.rekey_interval_ms = 0.0
        self.rekey_duration_ms = 0.0
        self.rekey_blackout_duration_ms = 0.0
        self.rekey_trigger_reason: Optional[str] = None
        self._last_rekey_start_mono: Optional[float] = None
        self._last_rekey_end_mono: Optional[float] = None
        self._last_packet_mono: Optional[float] = None
        # Last time we *received* any datagram from the authorized encrypted peer.
        # This must not be updated by local sends (plaintext uploads, keepalives),
        # otherwise liveness checks become meaningless.
        self._last_peer_rx_mono: Optional[float] = None
        self._rekey_active = False
        self._rekey_blackout_start_mono: Optional[float] = None
        self._rekey_blackout_end_mono: Optional[float] = None
        self.handshake_metrics: Dict[str, object] = {}
        self._primitive_templates = {
            "count": 0,
            "total_ns": 0,
            "min_ns": None,
            "max_ns": 0,
            "total_in_bytes": 0,
            "total_out_bytes": 0,
        }
        self.primitive_metrics: Dict[str, Dict[str, object]] = {
            "aead_encrypt": dict(self._primitive_templates),
            "aead_decrypt_ok": dict(self._primitive_templates),
            "aead_decrypt_fail": dict(self._primitive_templates),
        }

    @staticmethod
    def _ns_to_ms(value: object) -> float:
        try:
            ns = float(value)
        except (TypeError, ValueError):
            return 0.0
        if ns <= 0.0:
            return 0.0
        return round(ns / 1_000_000.0, 6)

    def _part_b_metrics(self) -> Dict[str, object]:
        handshake = self.handshake_metrics
        if not isinstance(handshake, dict) or not handshake:
            return {}

        primitives = handshake.get("primitives") or {}
        if not isinstance(primitives, dict):
            primitives = {}

        kem = primitives.get("kem") if isinstance(primitives.get("kem"), dict) else {}
        sig = primitives.get("signature") if isinstance(primitives.get("signature"), dict) else {}
        artifacts = handshake.get("artifacts") if isinstance(handshake.get("artifacts"), dict) else {}

        summary: Dict[str, object] = {}

        def _emit(prefix: str, source: Dict[str, object], key: str, legacy_key: Optional[str] = None) -> None:
            ns_value = source.get(key)
            ms_value = self._ns_to_ms(ns_value)
            summary[f"{prefix}_max_ms"] = ms_value
            summary[f"{prefix}_avg_ms"] = ms_value
            if legacy_key:
                summary[legacy_key] = ms_value

        _emit("kem_keygen", kem, "keygen_ns", "kem_keygen_ms")
        _emit("kem_encaps", kem, "encap_ns", "kem_encaps_ms")
        _emit("kem_decaps", kem, "decap_ns", "kem_decap_ms")
        _emit("sig_sign", sig, "sign_ns", "sig_sign_ms")
        _emit("sig_verify", sig, "verify_ns", "sig_verify_ms")

        summary["pub_key_size_bytes"] = int(
            kem.get("public_key_bytes")
            or artifacts.get("public_key_bytes")
            or 0
        )
        summary["ciphertext_size_bytes"] = int(kem.get("ciphertext_bytes", 0) or 0)
        summary["sig_size_bytes"] = int(
            sig.get("signature_bytes")
            or artifacts.get("signature_bytes")
            or 0
        )
        summary["shared_secret_size_bytes"] = int(kem.get("shared_secret_bytes", 0) or 0)

        def _avg_ns_for(key: str) -> float:
            stats = self.primitive_metrics.get(key)
            if not isinstance(stats, dict):
                return 0.0
            count = int(stats.get("count", 0) or 0)
            total_ns = int(stats.get("total_ns", 0) or 0)
            if count <= 0 or total_ns <= 0:
                return 0.0
            return total_ns / max(count, 1)

        summary["aead_encrypt_avg_ms"] = self._ns_to_ms(_avg_ns_for("aead_encrypt"))
        summary["aead_decrypt_avg_ms"] = self._ns_to_ms(_avg_ns_for("aead_decrypt_ok"))
        summary["aead_encrypt_ms"] = summary["aead_encrypt_avg_ms"]
        summary["aead_decrypt_ms"] = summary["aead_decrypt_avg_ms"]

        summary["rekey_ms"] = self._ns_to_ms(handshake.get("handshake_total_ns"))

        total_ns = 0
        for key in ("keygen_ns", "encap_ns", "decap_ns"):
            value = kem.get(key)
            if isinstance(value, (int, float)) and value > 0:
                total_ns += int(value)
        for key in ("sign_ns", "verify_ns"):
            value = sig.get(key)
            if isinstance(value, (int, float)) and value > 0:
                total_ns += int(value)
        summary["primitive_total_ms"] = self._ns_to_ms(total_ns)

        return summary

    def to_dict(self) -> Dict[str, object]:
        def _serialize(stats: Dict[str, object]) -> Dict[str, object]:
            return {
                "count": int(stats.get("count", 0) or 0),
                "total_ns": int(stats.get("total_ns", 0) or 0),
                "min_ns": int(stats.get("min_ns") or 0),
                "max_ns": int(stats.get("max_ns", 0) or 0),
                "total_in_bytes": int(stats.get("total_in_bytes", 0) or 0),
                "total_out_bytes": int(stats.get("total_out_bytes", 0) or 0),
            }

        result = {
            "ptx_out": self.ptx_out,
            "ptx_in": self.ptx_in,
            "enc_out": self.enc_out,
            "enc_in": self.enc_in,
            "ptx_bytes_out": self.ptx_bytes_out,
            "ptx_bytes_in": self.ptx_bytes_in,
            "enc_bytes_out": self.enc_bytes_out,
            "enc_bytes_in": self.enc_bytes_in,
            "bytes_out": self.enc_bytes_out,
            "bytes_in": self.enc_bytes_in,
            "drops": self.drops,
            "drop_replay": self.drop_replay,
            "drop_auth": self.drop_auth,
            "drop_header": self.drop_header,
            "drop_session_epoch": self.drop_session_epoch,
            "drop_other": self.drop_other,
            "drop_src_addr": self.drop_src_addr,
            "sniff_drop": self.sniff_drop,
            "rekeys_ok": self.rekeys_ok,
            "rekeys_fail": self.rekeys_fail,
            "last_rekey_ms": self.last_rekey_ms,
            "last_rekey_suite": self.last_rekey_suite or "",
            "rekey_interval_ms": self.rekey_interval_ms,
            "rekey_duration_ms": self.rekey_duration_ms,
            "rekey_blackout_duration_ms": self.rekey_blackout_duration_ms,
            "rekey_trigger_reason": self.rekey_trigger_reason or "",
            "handshake_metrics": self.handshake_metrics,
            "primitive_metrics": {name: _serialize(stats) for name, stats in self.primitive_metrics.items()},
        }

        part_b = self._part_b_metrics()
        if part_b:
            result["part_b_metrics"] = part_b
            for key, value in part_b.items():
                result.setdefault(key, value)

        return result

    def _update_primitive(self, key: str, duration_ns: int, in_bytes: int, out_bytes: int) -> None:
        stats = self.primitive_metrics.setdefault(key, dict(self._primitive_templates))
        stats["count"] = int(stats.get("count", 0) or 0) + 1
        stats["total_ns"] = int(stats.get("total_ns", 0) or 0) + max(0, int(duration_ns))
        current_min = stats.get("min_ns")
        if current_min in (None, 0) or (isinstance(current_min, int) and duration_ns < current_min):
            stats["min_ns"] = max(0, int(duration_ns))
        current_max = stats.get("max_ns", 0) or 0
        if duration_ns > current_max:
            stats["max_ns"] = max(0, int(duration_ns))
        stats["total_in_bytes"] = int(stats.get("total_in_bytes", 0) or 0) + max(0, int(in_bytes))
        stats["total_out_bytes"] = int(stats.get("total_out_bytes", 0) or 0) + max(0, int(out_bytes))

    def record_encrypt(self, duration_ns: int, plaintext_bytes: int, ciphertext_bytes: int) -> None:
        self._update_primitive("aead_encrypt", duration_ns, plaintext_bytes, ciphertext_bytes)

    def record_decrypt_ok(self, duration_ns: int, ciphertext_bytes: int, plaintext_bytes: int) -> None:
        self._update_primitive("aead_decrypt_ok", duration_ns, ciphertext_bytes, plaintext_bytes)

    def record_decrypt_fail(self, duration_ns: int, ciphertext_bytes: int) -> None:
        self._update_primitive("aead_decrypt_fail", duration_ns, ciphertext_bytes, 0)


def _dscp_to_tos(dscp: Optional[int]) -> Optional[int]:
    """Convert DSCP value to TOS byte for socket options."""
    if dscp is None:
        return None
    try:
        d = int(dscp)
        if 0 <= d <= 63:
            return d << 2  # DSCP occupies high 6 bits of TOS/Traffic Class
    except (TypeError, ValueError):
        return None
    return None


def _parse_header_fields(
    expected_version: int,
    aead_ids: AeadIds,
    session_id: bytes,
    wire: bytes,
) -> Tuple[str, Optional[int]]:
    """
    Try to unpack the header and classify the most likely drop reason *without* AEAD work.
    Returns (reason, seq_if_available).
    """
    HEADER_STRUCT = AEAD_HEADER_STRUCT
    HEADER_LEN = AEAD_HEADER_LEN
    if len(wire) < HEADER_LEN:
        return ("header_too_short", None)
    try:
        (version, kem_id, kem_param, sig_id, sig_param, sess, seq, epoch) = struct.unpack(
            HEADER_STRUCT, wire[:HEADER_LEN]
        )
    except struct.error:
        return ("header_unpack_error", None)
    if version != expected_version:
        return ("version_mismatch", seq)
    if (kem_id, kem_param, sig_id, sig_param) != (
        aead_ids.kem_id,
        aead_ids.kem_param,
        aead_ids.sig_id,
        aead_ids.sig_param,
    ):
        return ("crypto_id_mismatch", seq)
    if sess != session_id:
        return ("session_mismatch", seq)
    # If we got here, header matches; any decrypt failure that returns None is auth/tag failure.
    return ("auth_fail_or_replay", seq)


def _peer_matches_expected(
    addr: Tuple[str, int],
    expected_peer: Optional[Tuple[str, int]],
    strict: bool,
) -> bool:
    """Return True if addr matches the expected encrypted peer."""

    if expected_peer is None:
        return True
    src_ip, src_port = addr
    exp_ip, exp_port = expected_peer
    if strict:
        return src_ip == exp_ip and src_port == exp_port
    return src_ip == exp_ip


def _soft_transition_active(
    prev_receiver: Optional[Receiver],
    deadline_mono: object,
    *,
    now_mono: Optional[float] = None,
) -> bool:
    """Return True when the previous receiver remains valid for soft rekey."""

    if prev_receiver is None:
        return False
    try:
        deadline = float(deadline_mono)
    except (TypeError, ValueError):
        return False
    if now_mono is None:
        now_mono = time.monotonic()
    return now_mono < deadline


def _decrypt_with_transition(
    *,
    wire: bytes,
    receiver: Receiver,
    prev_receiver: Optional[Receiver],
    current_peer_ok: bool,
    prev_peer_ok: bool,
    prev_deadline_mono: object,
    now_mono: float,
) -> Tuple[Optional[bytes], Receiver]:
    """Decrypt using the current receiver, with bounded fallback to prev receiver.

    Rules:
    - If only the previous peer matches during the active grace window, decrypt
      only with the previous receiver.
    - If the current peer matches, try the current receiver first.
    - If current receiver returns None and the grace window is active for the
      previous peer, try the previous receiver before classifying a drop.
    - Exceptions from the current receiver are preserved; the previous receiver
      is a continuity fallback for old-session packets, not a retry loop for
      current-session crypto errors.
    """

    transition_active = _soft_transition_active(prev_receiver, prev_deadline_mono, now_mono=now_mono)

    if not current_peer_ok and transition_active and prev_peer_ok and prev_receiver is not None:
        return prev_receiver.decrypt(wire), prev_receiver

    plaintext = receiver.decrypt(wire)
    if plaintext is not None:
        return plaintext, receiver

    if transition_active and prev_peer_ok and prev_receiver is not None:
        prev_plaintext = prev_receiver.decrypt(wire)
        if prev_plaintext is not None:
            return prev_plaintext, prev_receiver

    return None, receiver


class _TokenBucket:
    """Per-IP rate limiter using token bucket algorithm."""
    def __init__(self, capacity: int, refill_per_sec: float) -> None:
        self.capacity = max(1, capacity)
        self.refill = max(0.01, float(refill_per_sec))
        self.tokens: Dict[str, float] = {}      # ip -> tokens
        self.last: Dict[str, float] = {}        # ip -> last timestamp
        # Track last-seen to allow TTL-based pruning of state for long-running servers
        self._seen_ts: Dict[str, float] = {}

    def allow(self, ip: str) -> bool:
        """Check if request from IP should be allowed."""
        now = time.monotonic()
        t = self.tokens.get(ip, self.capacity)
        last = self.last.get(ip, now)
        # refill
        t = min(self.capacity, t + (now - last) * self.refill)
        self.last[ip] = now
        self._seen_ts[ip] = now
        if t >= 1.0:
            t -= 1.0
            self.tokens[ip] = t
            return True
        self.tokens[ip] = t
        return False

    def prune(self, idle_seconds: float) -> None:
        """Remove entries not seen within idle_seconds to prevent unbounded growth."""
        cutoff = time.monotonic() - float(idle_seconds)
        for ip in list(self._seen_ts.keys()):
            if self._seen_ts.get(ip, 0) < cutoff:
                self._seen_ts.pop(ip, None)
                self.tokens.pop(ip, None)
                self.last.pop(ip, None)


def _validate_config(cfg: dict) -> None:
    """Validate required configuration keys are present."""
    required_keys = [
        "TCP_HANDSHAKE_PORT", "UDP_DRONE_RX", "UDP_GCS_RX",
        "DRONE_PLAINTEXT_TX", "DRONE_PLAINTEXT_RX",
        "GCS_PLAINTEXT_TX", "GCS_PLAINTEXT_RX",
        "DRONE_HOST", "GCS_HOST", "REPLAY_WINDOW",
    ]
    for key in required_keys:
        if key not in cfg:
            raise ConfigError(f"CONFIG missing: {key}")


# F8-GUARD: serialize TCP handshake port binding across concurrent rekey threads.
# On Windows, SO_REUSEADDR allows two sockets to bind to the same port, so the
# policy_engine state-machine guard alone is insufficient at the socket level.
_handshake_port_lock = threading.Lock()


def _perform_handshake(
    role: str,
    suite: dict,
    gcs_sig_secret: Optional[object],
    gcs_sig_public: Optional[bytes],
    cfg: dict,
    stop_after_seconds: Optional[float] = None,
    ready_event: Optional[threading.Event] = None,
    *,
    accept_deadline_s: Optional[float] = None,
    io_timeout_s: Optional[float] = None,
    epoch: int = 0,
) -> Tuple[
    bytes,
    bytes,
    bytes,
    bytes,
    bytes,
    Optional[str],
    Optional[str],
    Tuple[str, int],
    Dict[str, object],
]:
    """Perform TCP handshake and return keys, session details, and authenticated peer address.

    accept_deadline_s limits how long the GCS waits for an inbound TCP connect.
    io_timeout_s controls per-socket I/O timeouts for handshake reads/writes.

    Backward compatibility: stop_after_seconds is treated as accept_deadline_s
    when accept_deadline_s is not explicitly provided.
    """

    if accept_deadline_s is None and stop_after_seconds is not None:
        accept_deadline_s = stop_after_seconds

    if io_timeout_s is None:
        try:
            io_timeout = float(cfg.get("REKEY_HANDSHAKE_TIMEOUT", 20.0))
        except (TypeError, ValueError):
            io_timeout = 20.0
    else:
        try:
            io_timeout = float(io_timeout_s)
        except (TypeError, ValueError):
            io_timeout = float(cfg.get("REKEY_HANDSHAKE_TIMEOUT", 20.0))
    if io_timeout < 10.0:
        io_timeout = 10.0

    if role == "gcs":
        if gcs_sig_secret is None:
            raise ConfigError("GCS signature secret not provided")

        # F8-GUARD: hold lock while TCP listener is alive to prevent
        # concurrent rekey from double-binding on Windows (SO_REUSEADDR).
        # FIX-D2: Use bounded timeout so a queued rekey thread doesn't block
        # indefinitely while another rekey holds the lock.  The timeout is
        # the handshake I/O timeout + 10 s headroom.  If we can't acquire
        # the lock, the peer is already in a handshake — fail fast.
        _lock_timeout = io_timeout + 10.0
        if not _handshake_port_lock.acquire(timeout=_lock_timeout):
            raise ConfigError(
                f"handshake port lock held by another rekey for "
                f">{_lock_timeout:.0f}s; aborting"
            )
        server_sock = None
        try:
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind(("0.0.0.0", cfg["TCP_HANDSHAKE_PORT"]))
            server_sock.listen(32)
        except Exception:
            # FIX-A: Release lock on bind/listen failure to prevent permanent
            # deadlock of all future rekey handshakes.
            if server_sock is not None:
                try:
                    server_sock.close()
                except OSError:
                    pass
            _handshake_port_lock.release()
            raise

        try:
            if ready_event:
                ready_event.set()

            timeout = accept_deadline_s if accept_deadline_s is not None else 30.0
            deadline: Optional[float] = None
            if accept_deadline_s is not None:
                deadline = time.monotonic() + accept_deadline_s

            gate = _TokenBucket(
                cfg.get("HANDSHAKE_RL_BURST", 5),
                cfg.get("HANDSHAKE_RL_REFILL_PER_SEC", 1),
            )
            prune_interval = max(5.0, float(cfg.get("HANDSHAKE_RL_PRUNE_INTERVAL_S", 60.0)))
            prune_idle_s = max(prune_interval, float(cfg.get("HANDSHAKE_RL_IDLE_TTL_S", 600.0)))
            next_prune = time.monotonic() + prune_interval

            try:
                while True:
                    if deadline is not None:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise socket.timeout
                        server_sock.settimeout(max(0.01, remaining))
                    else:
                        server_sock.settimeout(timeout)

                    now_monotonic = time.monotonic()
                    if now_monotonic >= next_prune:
                        gate.prune(prune_idle_s)
                        next_prune = now_monotonic + prune_interval

                    try:
                        conn, addr = server_sock.accept()
                    except socket.timeout:
                        # If an explicit accept deadline is configured, treat expiry as a
                        # legacy-style config/runtime error (keeps older harnesses stable).
                        # Otherwise, continue waiting indefinitely for the initial drone connect.
                        if accept_deadline_s is not None:
                            raise ConfigError(
                                "No drone TCP handshake connection received on "
                                f"0.0.0.0:{cfg['TCP_HANDSHAKE_PORT']} within "
                                f"{float(accept_deadline_s):.1f}s "
                                f"(expected DRONE_HOST={cfg['DRONE_HOST']})"
                            )
                        continue
                    try:
                        ip, _port = addr
                        allowed_ips = {str(cfg["DRONE_HOST"])}
                        allowlist = cfg.get("DRONE_HOST_ALLOWLIST", []) or []
                        if isinstance(allowlist, str):
                            for entry in allowlist.split(","):
                                entry = entry.strip()
                                if entry:
                                    allowed_ips.add(entry)
                        elif isinstance(allowlist, (list, tuple, set)):
                            for entry in allowlist:
                                allowed_ips.add(str(entry))
                        else:
                            allowed_ips.add(str(allowlist))
                        strict_ip = bool(cfg.get("STRICT_HANDSHAKE_IP", True))
                        if strict_ip:
                            if ip not in allowed_ips:
                                logger.warning(
                                    "Rejected handshake from unauthorized IP",
                                    extra={"role": role, "expected": sorted(allowed_ips), "received": ip},
                                )
                                conn.close()
                                continue
                        else:
                            # Accept connection but log and record received IP for diagnostics
                            if ip not in allowed_ips:
                                logger.warning(
                                    "Handshake IP allowlist disabled; accepting connection from unexpected IP",
                                    extra={"role": role, "expected": sorted(allowed_ips), "received": ip},
                                )

                        if not gate.allow(ip):
                            try:
                                conn.settimeout(0.2)
                                conn.sendall(b"\x00")
                            except OSError:
                                pass
                            finally:
                                conn.close()
                            logger.warning(
                                "Handshake rate-limit drop",
                                extra={"role": role, "ip": ip},
                            )
                            continue

                        try:
                            result = server_gcs_handshake(conn, suite, gcs_sig_secret, timeout=io_timeout, epoch=epoch)
                        except HandshakeVerifyError:
                            logger.warning(
                                "Rejected drone handshake with failed authentication",
                                extra={"role": role, "expected": cfg["DRONE_HOST"], "received": ip},
                            )
                            continue
                        except (HandshakeError, HandshakeFormatError, OSError, socket.timeout, ConnectionResetError) as exc:
                            logger.warning(
                                "Handshake failed (non-auth): %s",
                                exc,
                                extra={"role": role, "ip": ip},
                            )
                            try:
                                conn.close()
                            except OSError:
                                pass
                            continue
                        # Support either 5-tuple or 7-tuple
                        metrics_payload: Dict[str, object] = {}
                        if len(result) >= 7:
                            k_d2g, k_g2d, nseed_d2g, nseed_g2d, session_id, kem_name, sig_name = result[:7]
                            if len(result) >= 8 and isinstance(result[7], dict):
                                metrics_payload = result[7]
                        else:
                            k_d2g, k_g2d, nseed_d2g, nseed_g2d, session_id = result
                            kem_name = sig_name = None
                        if not metrics_payload:
                            metrics_payload = {}
                        peer_addr = (ip, cfg["UDP_DRONE_RX"])
                        return (
                            k_d2g,
                            k_g2d,
                            nseed_d2g,
                            nseed_g2d,
                            session_id,
                            kem_name,
                            sig_name,
                            peer_addr,
                            metrics_payload,
                        )
                    finally:
                        try:
                            conn.close()
                        except OSError:
                            pass
            finally:
                pass
        finally:
            if server_sock is not None:
                server_sock.close()
            _handshake_port_lock.release()  # F8-GUARD: release after socket close

    elif role == "drone":
        if gcs_sig_public is None:
            raise ValueError("GCS signature public key not provided")

        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        endpoint_host = str(cfg["GCS_HOST"])
        endpoint_port = int(cfg["TCP_HANDSHAKE_PORT"])
        try:
            try:
                client_sock.settimeout(io_timeout)
            except OSError:
                pass
            try:
                client_sock.connect((endpoint_host, endpoint_port))
            except socket.timeout as exc:
                raise ConfigError(
                    "Handshake TCP connect timed out to "
                    f"{endpoint_host}:{endpoint_port} after {io_timeout:.1f}s"
                ) from exc
            except OSError as exc:
                raise ConfigError(
                    "Handshake TCP connect failed to "
                    f"{endpoint_host}:{endpoint_port}: {exc}"
                ) from exc
            peer_ip, _peer_port = client_sock.getpeername()
            try:
                result = client_drone_handshake(client_sock, suite, gcs_sig_public, timeout=io_timeout, epoch=epoch)
            except socket.timeout as exc:
                raise ConfigError(
                    "Handshake I/O timed out while connected to "
                    f"{endpoint_host}:{endpoint_port} after {io_timeout:.1f}s"
                ) from exc
            except OSError as exc:
                raise ConfigError(
                    "Handshake I/O failed while connected to "
                    f"{endpoint_host}:{endpoint_port}: {exc}"
                ) from exc
            metrics_payload: Dict[str, object] = {}
            if len(result) >= 7:
                k_d2g, k_g2d, nseed_d2g, nseed_g2d, session_id, kem_name, sig_name = result[:7]
                if len(result) >= 8 and isinstance(result[7], dict):
                    metrics_payload = result[7]
            else:
                k_d2g, k_g2d, nseed_d2g, nseed_g2d, session_id = result
                kem_name = sig_name = None
            if not metrics_payload:
                metrics_payload = {}
            peer_addr = (peer_ip, cfg["UDP_GCS_RX"])
            return (
                k_d2g,
                k_g2d,
                nseed_d2g,
                nseed_g2d,
                session_id,
                kem_name,
                sig_name,
                peer_addr,
                metrics_payload,
            )
        finally:
            client_sock.close()
    else:
        raise ValueError(f"Invalid role: {role}")


@contextmanager
def _setup_sockets(role: str, cfg: dict, *, encrypted_peer: Optional[Tuple[str, int]] = None):
    """Setup and cleanup all UDP sockets for the proxy."""
    sockets = {}
    # UDP socket buffer size — generous to prevent kernel drops at high msg rates.
    # Windows default is ~8 KB; at 360 msg/s a 222 ms consumer stall overflows.
    _UDP_BUF = int(cfg.get("UDP_SOCK_BUF_BYTES", 2 * 1024 * 1024))  # 2 MiB default
    try:
        if role == "drone":
            # Encrypted socket - receive from GCS
            enc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            enc_sock.bind(("0.0.0.0", cfg["UDP_DRONE_RX"]))
            enc_sock.setblocking(False)
            try:
                enc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _UDP_BUF)
                enc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, _UDP_BUF)
            except OSError:
                pass
            tos = _dscp_to_tos(cfg.get("ENCRYPTED_DSCP"))
            if tos is not None:
                try:
                    enc_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos)
                except Exception:
                    pass
            sockets["encrypted"] = enc_sock

            # Plaintext ingress - receive from local app
            ptx_in_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            ptx_in_sock.bind((cfg["DRONE_PLAINTEXT_HOST"], cfg["DRONE_PLAINTEXT_TX"]))
            ptx_in_sock.setblocking(False)
            try:
                ptx_in_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _UDP_BUF)
                ptx_in_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, _UDP_BUF)
            except OSError:
                pass
            sockets["plaintext_in"] = ptx_in_sock

            # Plaintext egress - send to local app (reuse ingress socket to ensure correct source port)
            sockets["plaintext_out"] = ptx_in_sock

            # Peer addresses
            sockets["encrypted_peer"] = encrypted_peer or (cfg["GCS_HOST"], cfg["UDP_GCS_RX"])
            sockets["plaintext_peer"] = (cfg["DRONE_PLAINTEXT_HOST"], cfg["DRONE_PLAINTEXT_RX"])

        elif role == "gcs":
            # Encrypted socket - receive from Drone
            enc_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            enc_sock.bind(("0.0.0.0", cfg["UDP_GCS_RX"]))
            enc_sock.setblocking(False)
            try:
                enc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _UDP_BUF)
                enc_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, _UDP_BUF)
            except OSError:
                pass
            tos = _dscp_to_tos(cfg.get("ENCRYPTED_DSCP"))
            if tos is not None:
                try:
                    enc_sock.setsockopt(socket.IPPROTO_IP, socket.IP_TOS, tos)
                except Exception:
                    pass
            sockets["encrypted"] = enc_sock

            # Plaintext ingress - receive from local app
            ptx_in_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            ptx_in_sock.bind((cfg["GCS_PLAINTEXT_HOST"], cfg["GCS_PLAINTEXT_TX"]))
            ptx_in_sock.setblocking(False)
            try:
                ptx_in_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, _UDP_BUF)
                ptx_in_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, _UDP_BUF)
            except OSError:
                pass
            sockets["plaintext_in"] = ptx_in_sock

            # Plaintext egress - send to local app (reuse ingress socket to ensure correct source port)
            sockets["plaintext_out"] = ptx_in_sock

            # Peer addresses
            sockets["encrypted_peer"] = encrypted_peer or (cfg["DRONE_HOST"], cfg["UDP_DRONE_RX"])
            sockets["plaintext_peer"] = (cfg["GCS_PLAINTEXT_HOST"], cfg["GCS_PLAINTEXT_RX"])

            # Direct sniff peer — bypass MAVProxy for lossless measurement.
            # When configured, the proxy sends a second copy of every decrypted
            # packet directly to the collector socket, avoiding MAVProxy's
            # processing bottleneck that causes 40-65 % observation loss.
            _sniff_port = int(cfg.get("GCS_PLAINTEXT_SNIFF_PORT", 0))
            if _sniff_port:
                sockets["sniff_peer"] = (cfg.get("GCS_PLAINTEXT_HOST", "127.0.0.1"), _sniff_port)
        else:
            raise ValueError(f"Invalid role: {role}")

        yield sockets
    finally:
        # Close unique sockets
        closed = set()
        for sock in list(sockets.values()):
            if isinstance(sock, socket.socket) and sock not in closed:
                try:
                    sock.close()
                    closed.add(sock)
                except Exception:
                    pass


def _compute_aead_ids(suite: dict, kem_name: Optional[str], sig_name: Optional[str]) -> AeadIds:
    if kem_name and sig_name and header_ids_from_names:
        ids_tuple = header_ids_from_names(kem_name, sig_name)  # type: ignore
    else:
        ids_tuple = header_ids_for_suite(suite)
    return AeadIds(*ids_tuple)


def _derive_runtime_aead_keys(
    base_k_d2g: bytes,
    base_k_g2d: bytes,
    session_id: bytes,
    aead_token: str,
    *,
    epoch: int,
) -> Tuple[bytes, bytes]:
    """Derive AEAD-profile traffic keys from transport base secrets."""

    return derive_aead_ratchet(
        base_k_d2g,
        base_k_g2d,
        session_id,
        aead_token,
        epoch=epoch,
    )


def _build_sender_receiver(
    role: str,
    ids: AeadIds,
    session_id: bytes,
    base_k_d2g: bytes,
    base_k_g2d: bytes,
    cfg: dict,
    *,
    aead_token: Optional[str] = None,
    epoch: int = 0,
):
    if aead_token is None:
        aead_token = cfg.get("SUITE_AEAD_TOKEN")
    if aead_token is None:
        raise ValueError("SUITE_AEAD_TOKEN missing from proxy config context")

    runtime_k_d2g, runtime_k_g2d = _derive_runtime_aead_keys(
        base_k_d2g,
        base_k_g2d,
        session_id,
        aead_token,
        epoch=epoch,
    )

    if role == "drone":
        sender = Sender(
            CONFIG["WIRE_VERSION"],
            ids,
            session_id,
            epoch,
            runtime_k_d2g,
            aead_token=aead_token,
        )
        receiver = Receiver(
            CONFIG["WIRE_VERSION"],
            ids,
            session_id,
            epoch,
            runtime_k_g2d,
            cfg["REPLAY_WINDOW"],
            aead_token=aead_token,
        )
    else:
        sender = Sender(
            CONFIG["WIRE_VERSION"],
            ids,
            session_id,
            epoch,
            runtime_k_g2d,
            aead_token=aead_token,
        )
        receiver = Receiver(
            CONFIG["WIRE_VERSION"],
            ids,
            session_id,
            epoch,
            runtime_k_d2g,
            cfg["REPLAY_WINDOW"],
            aead_token=aead_token,
        )
    return sender, receiver


def _launch_manual_console(control_state: ControlState, *, quiet: bool) -> Tuple[threading.Event, Tuple[threading.Thread, ...]]:
    suites_catalog = sorted(list_suites().keys())
    stop_event = threading.Event()

    def status_loop() -> None:
        last_line = ""
        while not stop_event.is_set():
            with control_state.lock:
                state = control_state.state
                suite_id = control_state.current_suite
            line = f"[{state}] {suite_id}"
            if line != last_line and not quiet:
                sys.stderr.write(f"\r{line:<80}")
                sys.stderr.flush()
                last_line = line
            time.sleep(0.5)
        if not quiet:
            sys.stderr.write("\r" + " " * 80 + "\r")
            sys.stderr.flush()

    def operator_loop() -> None:
        if not sys.stdin or not hasattr(sys.stdin, "isatty") or not sys.stdin.isatty():
            # Avoid blocking forever in service / redirected-stdin environments.
            if not quiet:
                print("Manual control disabled: stdin is not a TTY.")
            stop_event.set()
            return
        if not quiet:
            print("Manual control ready. Type a suite ID, 'list', 'status', or 'quit'.")
        while not stop_event.is_set():
            try:
                line = input("rekey> ")
            except EOFError:
                break
            if line is None:
                continue
            line = line.strip()
            if not line:
                continue
            lowered = line.lower()
            if lowered in {"quit", "exit"}:
                break
            if lowered == "list":
                if not quiet:
                    print("Available suites:")
                    for sid in suites_catalog:
                        print(f"  {sid}")
                continue
            if lowered == "status":
                with control_state.lock:
                    current_suite_id = control_state.current_suite
                    try:
                        current_suite = get_suite(current_suite_id)
                        profiles = negotiation_profiles_for_suite(current_suite)
                    except Exception:
                        profiles = negotiation_profiles_for_suite({"suite_id": current_suite_id})
                    summary = (
                        f"state={control_state.state} suite={control_state.current_suite} "
                        f"khs={profiles['key_handshake_id']} aead={profiles['data_aead_id']}"
                    )
                    if control_state.last_status:
                        summary += f" last_status={control_state.last_status}"
                if not quiet:
                    print(summary)
                continue
            try:
                target_suite = get_suite(line)
                rid = request_prepare(control_state, target_suite["suite_id"])
                if not quiet:
                    print(f"prepare queued for {target_suite['suite_id']} rid={rid}")
            except RuntimeError as exc:
                if not quiet:
                    print(f"Busy: {exc}")
            except Exception as exc:
                if not quiet:
                    print(f"Invalid suite: {exc}")

        stop_event.set()

    status_thread = threading.Thread(target=status_loop, daemon=True)
    operator_thread = threading.Thread(target=operator_loop, daemon=True)
    status_thread.start()
    operator_thread.start()
    return stop_event, (status_thread, operator_thread)


def run_proxy(
    *,
    role: str,
    suite: dict,
    cfg: dict,
    gcs_sig_secret: Optional[object] = None,
    gcs_sig_public: Optional[bytes] = None,
    stop_after_seconds: Optional[float] = None,
    manual_control: bool = False,
    quiet: bool = False,
    ready_event: Optional[threading.Event] = None,
    status_file: Optional[str] = None,
    load_gcs_secret: Optional[Callable[[Dict[str, object]], object]] = None,
    load_gcs_public: Optional[Callable[[Dict[str, object]], bytes]] = None,
) -> Dict[str, object]:
    """
    Start a blocking proxy process for `role` in {"drone","gcs"}.

    Performs the TCP handshake, bridges plaintext/encrypted UDP, and processes
    in-band control messages for rekey negotiation. Returns counters on clean exit.
    """
    if role not in {"drone", "gcs"}:
        raise ValueError(f"Invalid role: {role}")

    _validate_config(cfg)

    cfg = dict(cfg)
    cfg["SUITE_AEAD_TOKEN"] = suite.get("aead_token", "aesgcm")

    counters = ProxyCounters()
    counters_lock = threading.Lock()
    start_time = time.time()

    suite_id = suite.get("suite_id")
    if not suite_id:
        try:
            suite_id = next((sid for sid, s in SUITES.items() if dict(s) == suite), "unknown")
        except Exception:
            suite_id = "unknown"
    profiles = negotiation_profiles_for_suite({**dict(suite), "suite_id": suite_id})

    status_path: Optional[Path] = None
    if status_file:
        status_path = Path(status_file).expanduser()

    def write_status(payload: Dict[str, object]) -> None:
        if status_path is None:
            return
        import time as _time
        attempts = 2
        status_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = status_path.with_suffix(status_path.suffix + ".tmp")
        data = json.dumps(payload)
        for attempt in range(attempts):
            try:
                tmp_path.write_text(data, encoding="utf-8")
                tmp_path.replace(status_path)
                return
            except PermissionError:
                # Common on Windows when antivirus/indexer holds the file briefly.
                if attempt + 1 < attempts:
                    _time.sleep(0.05)
                    continue
                logger.warning(
                    "Failed to write status file due to PermissionError",
                    extra={"role": role, "path": str(status_path)},
                )
                return
            except Exception as exc:
                logger.warning(
                    "Failed to write status file",
                    extra={"role": role, "error": str(exc), "path": str(status_path)},
                )
                return

    if role == "drone" and gcs_sig_public is None:
        if load_gcs_public is None:
            raise ConfigError("GCS signature public key not provided (provide peer key or loader)")
        gcs_sig_public = load_gcs_public(suite)

    handshake_ready_event: Optional[threading.Event] = None
    if role == "gcs" and status_path is not None:
        handshake_ready_event = threading.Event()

        def _publish_listening_status() -> None:
            if handshake_ready_event is None:
                return
            if handshake_ready_event.wait(timeout=max(float(cfg.get("REKEY_HANDSHAKE_TIMEOUT", 20.0)), 5.0)):
                write_status({
                    "status": "listening",
                    "suite": suite_id,
                    "key_handshake_id": profiles["key_handshake_id"],
                    "data_aead_id": profiles["data_aead_id"],
                    "aead_token": str(suite.get("aead_token", "aesgcm")),
                })

        threading.Thread(target=_publish_listening_status, daemon=True).start()

    handshake_result = _perform_handshake(
        role,
        suite,
        gcs_sig_secret,
        gcs_sig_public,
        cfg,
        accept_deadline_s=stop_after_seconds,
        io_timeout_s=cfg.get("REKEY_HANDSHAKE_TIMEOUT", 20.0),
        ready_event=handshake_ready_event if handshake_ready_event is not None else ready_event,
    )

    if len(handshake_result) >= 9:
        (
            k_d2g,
            k_g2d,
            _nseed_d2g,
            _nseed_g2d,
            session_id,
            kem_name,
            sig_name,
            peer_addr,
            handshake_metrics,
        ) = handshake_result
    else:
        (
            k_d2g,
            k_g2d,
            _nseed_d2g,
            _nseed_g2d,
            session_id,
            kem_name,
            sig_name,
            peer_addr,
        ) = handshake_result
        handshake_metrics = {}

    sess_status_display = (
        session_id.hex()
        if cfg.get("LOG_SESSION_ID", False)
        else hashlib.sha256(session_id).hexdigest()[:8] + "..."
    )
    status_payload = {
        "status": "handshake_ok",
        "suite": suite_id,
        "key_handshake_id": profiles["key_handshake_id"],
        "data_aead_id": profiles["data_aead_id"],
        "aead_token": str(suite.get("aead_token", "aesgcm")),
        "session_id": sess_status_display,
    }
    if handshake_metrics:
        status_payload["handshake_metrics"] = handshake_metrics
    write_status(status_payload)

    sess_display = (
        session_id.hex()
        if cfg.get("LOG_SESSION_ID", False)
        else hashlib.sha256(session_id).hexdigest()[:8] + "..."
    )

    with counters_lock:
        counters.handshake_metrics = dict(handshake_metrics) if handshake_metrics else {}

    logger.info(
        "PQC handshake completed successfully",
        extra={
            "suite_id": suite_id,
            "peer_role": ("drone" if role == "gcs" else "gcs"),
            "session_id": sess_display,
        },
    )

    # Periodically persist counters to the status file while the proxy runs.
    # This allows external automation (scheduler) to observe enc_in/enc_out
    # during long-running experiments without waiting for process exit.
    stop_status_writer = threading.Event()
    # FIX-M2: External callers can set this event to trigger an immediate
    # status file write, minimizing the ~100ms staleness gap between the
    # last periodic write and the scheduler's read.
    flush_status_event = threading.Event()

    def _status_writer() -> None:
        while not stop_status_writer.is_set():
            try:
                with counters_lock:
                    payload = {
                        "status": "running",
                        "suite": suite_id,
                        "key_handshake_id": profiles["key_handshake_id"],
                        "data_aead_id": profiles["data_aead_id"],
                        "aead_token": str(cfg.get("SUITE_AEAD_TOKEN", "aesgcm")),
                        "counters": counters.to_dict(),
                        "ts_ns": time.time_ns(),
                    }
                write_status(payload)
            except Exception:
                logger.debug("status writer failed", extra={"role": role})
            # Sleep with event to allow quick shutdown.
            # 0.1s keeps the status file fresh enough for benchmark
            # finalization to read near-live counters (ptx_in, enc_out, …).
            # The previous 1.0s interval caused ~2.5% staleness gap vs live
            # mavlink_collector counts at 330 msg/s.
            #
            # FIX-M2: Also wake up when flush_status_event is set, allowing
            # the scheduler to force an immediate write before reading.
            stop_status_writer.wait(0.1)
            if flush_status_event.is_set():
                flush_status_event.clear()

    status_thread: Optional[threading.Thread] = None
    try:
        status_thread = threading.Thread(target=_status_writer, daemon=True)
        status_thread.start()
    except Exception:
        status_thread = None

    aead_ids = _compute_aead_ids(suite, kem_name, sig_name)
    sender, receiver = _build_sender_receiver(role, aead_ids, session_id, k_d2g, k_g2d, cfg, epoch=0)

    control_state = create_control_state(
        role,
        suite_id,
        aead_token=str(cfg.get("SUITE_AEAD_TOKEN", "aesgcm")),
    )
    coordinator_role = coordinator_role_from_config(cfg)
    try:
        set_coordinator_role(control_state, coordinator_role)
    except Exception:
        # Fail closed to legacy behaviour (GCS-coordinated) if coordinator setup fails.
        coordinator_role = "gcs"
        try:
            set_coordinator_role(control_state, coordinator_role)
        except Exception:
            pass
    context_lock = threading.RLock()
    active_context: Dict[str, object] = {
        "suite": suite_id,
        "suite_dict": suite,
        "session_id": session_id,
        "epoch": 0,
        "aead_ids": aead_ids,
        "sender": sender,
        "receiver": receiver,
        "transport_base_k_d2g": k_d2g,
        "transport_base_k_g2d": k_g2d,
        "kem_name": kem_name,
        "sig_name": sig_name,
        "peer_addr": peer_addr,
        "peer_match_strict": bool(cfg.get("STRICT_UDP_PEER_MATCH", True)),
        "staged_rekey": None,
    }

    active_rekeys: set[str] = set()
    rekey_guard = threading.Lock()
    # BUG-13 fix: track rekey threads at run_proxy scope for cleanup on shutdown
    _rekey_threads: list[threading.Thread] = []
    # FIX-B: Deferred destroy list — rekey worker enqueues old Sender/Receiver
    # here instead of calling destroy() inline.  The main selector loop drains
    # this list at a safe point (no batch references held) to avoid TOCTOU race
    # where destroy() zeros _cipher while a concurrent batch-drain still holds
    # a reference to the old object.  Follows WireGuard keypair_destroy deferral.
    _pending_destroy: list = []
    _pending_destroy_lock = threading.Lock()

    def _finalize_rekey_timing() -> None:
        with counters_lock:
            end_mono = time.monotonic()
            counters._last_rekey_end_mono = end_mono
            if counters._last_rekey_start_mono is not None:
                counters.rekey_duration_ms = (end_mono - counters._last_rekey_start_mono) * 1000.0
            if counters._rekey_blackout_start_mono is not None:
                if counters._rekey_blackout_end_mono is not None:
                    counters.rekey_blackout_duration_ms = (
                        counters._rekey_blackout_end_mono - counters._rekey_blackout_start_mono
                    ) * 1000.0
                else:
                    counters.rekey_blackout_duration_ms = (
                        end_mono - counters._rekey_blackout_start_mono
                    ) * 1000.0
            counters._rekey_active = False

    def _destroy_key_objects(*objs: object) -> None:
        for obj in objs:
            if obj is None:
                continue
            try:
                obj.destroy()
            except Exception:
                pass

    def _discard_staged_rekey(rid: Optional[str] = None) -> None:
        staged_sender = None
        staged_receiver = None
        with context_lock:
            staged = active_context.get("staged_rekey")
            if not isinstance(staged, dict):
                return
            staged_rid = staged.get("rid")
            if rid is not None and staged_rid != rid:
                return
            staged_sender = staged.get("sender")
            staged_receiver = staged.get("receiver")
            active_context["staged_rekey"] = None
        _destroy_key_objects(staged_sender, staged_receiver)

    def _activate_staged_rekey(rid: str, *, activation_origin: str) -> bool:
        nonlocal gcs_sig_public

        with context_lock:
            staged = active_context.get("staged_rekey")
            if not isinstance(staged, dict) or staged.get("rid") != rid:
                return False

            new_sender = staged.get("sender")
            new_receiver = staged.get("receiver")
            new_suite_id = str(staged.get("suite_id", ""))
            new_suite_dict = dict(staged.get("suite_dict", {}))
            new_session_id = bytes(staged.get("session_id", b""))
            new_ids = staged.get("aead_ids")
            new_transport_base_k_d2g = staged.get("transport_base_k_d2g")
            new_transport_base_k_g2d = staged.get("transport_base_k_g2d")
            new_kem_name = staged.get("kem_name")
            new_sig_name = staged.get("sig_name")
            new_peer_addr = staged.get("peer_addr")
            new_aead_token = str(staged.get("aead_token", cfg.get("SUITE_AEAD_TOKEN", "aesgcm")))
            new_handshake_metrics = dict(staged.get("handshake_metrics", {}))
            new_public = staged.get("gcs_sig_public")
            transport_epoch = int(staged.get("epoch", 0))
            soft_transition_s = float(staged.get("soft_transition_s", 0.0))

            old_sender = active_context.get("sender")
            old_receiver = active_context.get("receiver")
            old_peer_addr = active_context.get("peer_addr")
            transition_deadline = time.monotonic() + soft_transition_s if soft_transition_s > 0.0 else None

            cfg["SUITE_AEAD_TOKEN"] = new_aead_token
            active_context.update(
                {
                    "sender": new_sender,
                    "receiver": new_receiver,
                    "prev_receiver": old_receiver if transition_deadline is not None else None,
                    "prev_peer_addr": old_peer_addr if transition_deadline is not None else None,
                    "prev_receiver_deadline": transition_deadline,
                    "transport_base_k_d2g": new_transport_base_k_d2g,
                    "transport_base_k_g2d": new_transport_base_k_g2d,
                    "kem_name": new_kem_name,
                    "sig_name": new_sig_name,
                    "session_id": new_session_id,
                    "epoch": transport_epoch,
                    "aead_ids": new_ids,
                    "suite": new_suite_id,
                    "suite_dict": new_suite_dict,
                    "peer_addr": new_peer_addr,
                    "staged_rekey": None,
                }
            )
            sockets["encrypted_peer"] = new_peer_addr
            if transition_deadline is None:
                active_context.pop("prev_receiver", None)
                active_context.pop("prev_peer_addr", None)
                active_context.pop("prev_receiver_deadline", None)

        with _pending_destroy_lock:
            sender_destroy_deadline = time.monotonic()
            receiver_destroy_deadline = transition_deadline if transition_deadline is not None else sender_destroy_deadline
            if old_sender is not None:
                _pending_destroy.append((sender_destroy_deadline, old_sender))
            if old_receiver is not None:
                _pending_destroy.append((receiver_destroy_deadline, old_receiver))

        if transition_deadline is not None and old_receiver is not None:
            logger.info(
                "Soft rekey transition armed",
                extra={
                    "role": role,
                    "rid": rid,
                    "suite_id": new_suite_id,
                    "grace_s": soft_transition_s,
                },
            )

        with counters_lock:
            counters.rekeys_ok += 1
            counters.last_rekey_ms = int(time.time() * 1000)
            counters.last_rekey_suite = new_suite_id
            counters.handshake_metrics = dict(new_handshake_metrics) if new_handshake_metrics else {}
        _finalize_rekey_timing()
        _rekey_cb_record_success()
        if role == "drone" and isinstance(new_public, (bytes, bytearray)):
            gcs_sig_public = bytes(new_public)
        record_rekey_result(
            control_state,
            rid,
            new_suite_id,
            success=True,
            aead_token=new_aead_token,
        )
        new_sess_status_display = (
            new_session_id.hex()
            if cfg.get("LOG_SESSION_ID", False)
            else hashlib.sha256(new_session_id).hexdigest()[:8] + "..."
        )
        status_payload = {
            "status": "rekey_ok",
            "new_suite": new_suite_id,
            "aead_token": new_aead_token,
            "session_id": new_sess_status_display,
        }
        if new_handshake_metrics:
            status_payload["handshake_metrics"] = new_handshake_metrics
        write_status(status_payload)
        logger.info(
            "Control rekey activated",
            extra={
                "role": role,
                "suite_id": new_suite_id,
                "rid": rid,
                "epoch": transport_epoch,
                "activation_origin": activation_origin,
            },
        )
        with rekey_guard:
            active_rekeys.discard(rid)
        return True

    if manual_control and is_coordinator(role=role, coordinator_role=coordinator_role) and not cfg.get("ENABLE_PACKET_TYPE"):
        logger.warning("ENABLE_PACKET_TYPE is disabled; control-plane packets may not be processed correctly.")

    manual_stop: Optional[threading.Event] = None
    manual_threads: Tuple[threading.Thread, ...] = ()
    if manual_control and is_coordinator(role=role, coordinator_role=coordinator_role):
        manual_stop, manual_threads = _launch_manual_console(control_state, quiet=quiet)

    # Optional TCP control server (legacy JSON protocol) for external schedulers.
    # Enables commands like {"cmd":"rekey","suite":"cs-..."}.
    # Only the coordinator role accepts 'rekey' (non-coordinator returns coordinator_only).
    tcp_control_enabled = bool(cfg.get("ENABLE_TCP_CONTROL", False))
    control_server = start_control_server_if_enabled(
        role=role,
        cfg=cfg,
        control_state=control_state,
        quiet=quiet,
        enabled=tcp_control_enabled,
    )
    try:
        _control_negotiating_timeout_ms = max(
            1000,
            int(float(cfg.get("CONTROL_NEGOTIATING_TIMEOUT_S", 15.0)) * 1000.0),
        )
    except Exception:
        _control_negotiating_timeout_ms = 15000
    try:
        _control_swapping_timeout_ms = max(
            1000,
            int(float(cfg.get("CONTROL_SWAPPING_TIMEOUT_S", 30.0)) * 1000.0),
        )
    except Exception:
        _control_swapping_timeout_ms = 30000

    # ── Rekey circuit breaker (opt-in via REKEY_CB_ENABLED) ──────────
    # Tracks consecutive failures in a sliding window.  When the failure
    # threshold is reached the breaker trips and suppresses new rekey
    # attempts for a cooldown period.  Disabled by default to preserve
    # legacy behaviour.
    _rekey_cb_enabled = bool(cfg.get("REKEY_CB_ENABLED", False))
    _rekey_cb_threshold = max(1, int(cfg.get("REKEY_CB_FAIL_THRESHOLD", 3)))
    _rekey_cb_window = max(1.0, float(cfg.get("REKEY_CB_WINDOW_S", 60.0)))
    _rekey_cb_cooldown = max(1.0, float(cfg.get("REKEY_CB_COOLDOWN_S", 30.0)))
    _rekey_cb_failures: list = []          # monotonic timestamps of recent failures
    _rekey_cb_tripped_until: float = 0.0   # monotonic deadline while tripped
    _rekey_cb_lock = threading.Lock()

    def _rekey_cb_record_failure() -> None:
        """Record a rekey failure in the circuit-breaker window."""
        if not _rekey_cb_enabled:
            return
        nonlocal _rekey_cb_tripped_until
        now = time.monotonic()
        with _rekey_cb_lock:
            cutoff = now - _rekey_cb_window
            _rekey_cb_failures[:] = [t for t in _rekey_cb_failures if t > cutoff]
            _rekey_cb_failures.append(now)
            if len(_rekey_cb_failures) >= _rekey_cb_threshold:
                _rekey_cb_tripped_until = now + _rekey_cb_cooldown
                logger.warning(
                    "Rekey circuit breaker TRIPPED — suppressing rekeys for %.1fs",
                    _rekey_cb_cooldown,
                    extra={"role": role, "failures_in_window": len(_rekey_cb_failures)},
                )

    def _rekey_cb_allow() -> bool:
        """Return True if the circuit breaker allows a new rekey attempt."""
        if not _rekey_cb_enabled:
            return True
        now = time.monotonic()
        with _rekey_cb_lock:
            if now < _rekey_cb_tripped_until:
                return False
            # If cooldown expired, clear history so the breaker resets
            if _rekey_cb_tripped_until > 0.0 and now >= _rekey_cb_tripped_until:
                _rekey_cb_failures.clear()
            return True

    def _rekey_cb_record_success() -> None:
        """Reset failure window on successful rekey."""
        if not _rekey_cb_enabled:
            return
        nonlocal _rekey_cb_tripped_until
        with _rekey_cb_lock:
            _rekey_cb_failures.clear()
            _rekey_cb_tripped_until = 0.0

    _strict_single_flight = bool(cfg.get("REKEY_STRICT_SINGLE_FLIGHT", True))
    try:
        _cfg_max_concurrent_rekeys = int(cfg.get("REKEY_MAX_CONCURRENT", 3))
    except Exception:
        _cfg_max_concurrent_rekeys = 3
    _cfg_max_concurrent_rekeys = max(1, _cfg_max_concurrent_rekeys)
    _max_concurrent_rekeys = 1 if _strict_single_flight else _cfg_max_concurrent_rekeys

    def _launch_rekey(
        target_suite_id: str,
        rid: str,
        trigger_reason: Optional[str] = None,
        *,
        target_aead_token: Optional[str] = None,
    ) -> None:
        # Circuit-breaker gate: suppress if tripped
        if not _rekey_cb_allow():
            with context_lock:
                current_suite = str(active_context.get("suite", suite_id))
            profile = get_pending_profile(control_state, rid)
            fallback_aead = str(cfg.get("SUITE_AEAD_TOKEN", "aesgcm"))
            resolved_aead = str(profile.get("aead_token") or target_aead_token or fallback_aead)
            with control_state.lock:
                pending_known = rid in control_state.pending
            if pending_known:
                record_rekey_result(
                    control_state,
                    rid,
                    current_suite,
                    success=False,
                    aead_token=resolved_aead,
                )
            with counters_lock:
                counters.rekeys_fail += 1
            logger.info(
                "Rekey suppressed by circuit breaker",
                extra={
                    "role": role,
                    "suite_id": target_suite_id,
                    "rid": rid,
                    "aead_token": resolved_aead,
                },
            )
            return

        reject_overlap = False
        active_count = 0
        with rekey_guard:
            if rid in active_rekeys:
                return
            active_count = len(active_rekeys)
            if active_count >= _max_concurrent_rekeys:
                reject_overlap = True
            else:
                active_rekeys.add(rid)

        if reject_overlap:
            with context_lock:
                current_suite = active_context["suite"]
            with control_state.lock:
                pending_known = rid in control_state.pending
            with counters_lock:
                counters.rekeys_fail += 1
            if pending_known:
                record_rekey_result(control_state, rid, current_suite, success=False)
            logger.warning(
                "Rekey request rejected due to in-flight overlap guard",
                extra={
                    "role": role,
                    "suite_id": target_suite_id,
                    "rid": rid,
                    "active": active_count,
                    "strict_single_flight": _strict_single_flight,
                    "max_concurrent": _max_concurrent_rekeys,
                },
            )
            return

        with counters_lock:
            now_mono = time.monotonic()
            counters._rekey_active = True
            counters._rekey_blackout_start_mono = now_mono
            counters._rekey_blackout_end_mono = None
            counters._last_rekey_start_mono = now_mono
            if counters._last_rekey_end_mono is not None:
                counters.rekey_interval_ms = (now_mono - counters._last_rekey_end_mono) * 1000.0
            if trigger_reason:
                counters.rekey_trigger_reason = trigger_reason

        logger.info(
            "Control rekey negotiation started",
            extra={
                "role": role,
                "suite_id": target_suite_id,
                "rid": rid,
                "target_aead": target_aead_token or "",
            },
        )

        def worker() -> None:
            nonlocal gcs_sig_public
            release_rekey_slot = True
            try:
                new_suite = get_suite(target_suite_id)
                new_secret = None
                new_public: Optional[bytes] = None
                if role == "gcs" and load_gcs_secret is not None:
                    try:
                        new_secret = load_gcs_secret(new_suite)
                    except FileNotFoundError as exc:
                        with context_lock:
                            current_suite = active_context["suite"]
                        with counters_lock:
                            counters.rekeys_fail += 1
                        _finalize_rekey_timing()
                        _rekey_cb_record_failure()
                        record_rekey_result(control_state, rid, current_suite, success=False)
                        logger.warning(
                            "Control rekey rejected: missing signing secret",
                            extra={
                                "role": role,
                                "suite_id": target_suite_id,
                                "rid": rid,
                                "error": str(exc),
                            },
                        )
                        with rekey_guard:
                            active_rekeys.discard(rid)
                        return
                    except Exception as exc:
                        with context_lock:
                            current_suite = active_context["suite"]
                        with counters_lock:
                            counters.rekeys_fail += 1
                        _finalize_rekey_timing()
                        _rekey_cb_record_failure()
                        record_rekey_result(control_state, rid, current_suite, success=False)
                        logger.warning(
                            "Control rekey rejected: signing secret load failed",
                            extra={
                                "role": role,
                                "suite_id": target_suite_id,
                                "rid": rid,
                                "error": str(exc),
                            },
                        )
                        with rekey_guard:
                            active_rekeys.discard(rid)
                        return
            except (ValueError, KeyError) as exc:
                with context_lock:
                    current_suite = active_context["suite"]
                with counters_lock:
                    counters.rekeys_fail += 1
                _finalize_rekey_timing()
                _rekey_cb_record_failure()
                record_rekey_result(control_state, rid, current_suite, success=False)
                logger.warning(
                    "Control rekey rejected: unknown suite",
                    extra={"role": role, "suite_id": target_suite_id, "rid": rid, "error": str(exc)},
                )
                with rekey_guard:
                    active_rekeys.discard(rid)
                return

            if role == "drone" and load_gcs_public is not None:
                try:
                    new_public = load_gcs_public(new_suite)
                except FileNotFoundError as exc:
                    with context_lock:
                        current_suite = active_context["suite"]
                    with counters_lock:
                        counters.rekeys_fail += 1
                    _finalize_rekey_timing()
                    _rekey_cb_record_failure()
                    record_rekey_result(control_state, rid, current_suite, success=False)
                    logger.warning(
                        "Control rekey rejected: missing signing public key",
                        extra={
                            "role": role,
                            "suite_id": target_suite_id,
                            "rid": rid,
                            "error": str(exc),
                        },
                    )
                    with rekey_guard:
                        active_rekeys.discard(rid)
                    return
                except Exception as exc:
                    with context_lock:
                        current_suite = active_context["suite"]
                    with counters_lock:
                        counters.rekeys_fail += 1
                    _finalize_rekey_timing()
                    _rekey_cb_record_failure()
                    record_rekey_result(control_state, rid, current_suite, success=False)
                    logger.warning(
                        "Control rekey rejected: signing public key load failed",
                        extra={
                            "role": role,
                            "suite_id": target_suite_id,
                            "rid": rid,
                            "error": str(exc),
                        },
                    )
                    with rekey_guard:
                        active_rekeys.discard(rid)
                    return

            prev_token: Optional[str] = cfg.get("SUITE_AEAD_TOKEN")
            try:
                timeout = cfg.get("REKEY_HANDSHAKE_TIMEOUT", 20.0)
                _soft_transition_s = max(0.0, float(cfg.get("REKEY_SOFT_TRANSITION_S", 5.0)))
                # F5: Hard deadline guard (WireGuard REKEY_TIMEOUT pattern).
                # Prevent indefinite blocking if peer is unreachable/crashed.
                # WireGuard uses 5s rekey timeout with jitter.  We allow the
                # configured timeout but cap at 120s to bound worst-case

                # FIX-D: Pre-rekey liveness check using data-plane heartbeats.
                # The main loop sends a 0x00 keepalive every 15 s.  If we
                # haven't received ANY packet (data or heartbeat) from the
                # peer in 3× the keepalive interval, the link is likely dead
                # and the handshake TCP-connect will just block until timeout.
                # Skip the rekey early to avoid holding _handshake_port_lock
                # for the full timeout duration while the peer is unreachable.
                _liveness_threshold_s = float(cfg.get(
                    "REKEY_LIVENESS_THRESHOLD_S", 45.0))  # 3 × 15 s keepalive
                with counters_lock:
                    _last_peer_rx = counters._last_peer_rx_mono
                if _last_peer_rx is not None:
                    _peer_idle_s = time.monotonic() - _last_peer_rx
                    if _peer_idle_s > _liveness_threshold_s:
                        logger.warning(
                            "Rekey skipped: peer appears dead (no data/heartbeat "
                            "for %.1f s, threshold %.1f s)",
                            _peer_idle_s, _liveness_threshold_s,
                            extra={"role": role, "suite_id": target_suite_id,
                                   "rid": rid},
                        )
                        raise ConfigError(
                            f"peer liveness check failed: idle {_peer_idle_s:.0f}s"
                        )
                # thread lifetime and prevent thread pool exhaustion.
                timeout = min(float(timeout), 120.0)
                if role == "gcs" and new_secret is not None:
                    base_secret = new_secret
                else:
                    base_secret = gcs_sig_secret
                public_key = new_public if new_public is not None else gcs_sig_public
                if role == "drone" and public_key is None:
                    raise ConfigError("GCS public key not available for rekey")
                with control_state.lock:
                    transport_epoch = (
                        int(control_state.pending_epoch)
                        if control_state.pending_epoch is not None
                        else int(control_state.epoch)
                    )

                # Phase 4 support: Check if this is an AEAD ratchet shift only (no PQC handshake needed)
                is_aead_shift = False
                transport_base_k_d2g, transport_base_k_g2d, base_session_id, old_peer_addr = None, None, None, None
                new_kem_name, new_sig_name = None, None
                current_aead_token: Optional[str] = None
                default_aead_token = str(new_suite.get("aead_token", "aesgcm"))
                new_aead_token = str(target_aead_token or default_aead_token)
                with context_lock:
                    curr_suite = active_context.get("suite_dict", {})
                    curr_profiles = negotiation_profiles_for_suite(curr_suite)
                    new_profiles = negotiation_profiles_for_suite(new_suite)
                    curr_khs = curr_profiles.get("key_handshake_id")
                    new_khs = new_profiles.get("key_handshake_id")
                    current_aead_token = str(curr_suite.get("aead_token", cfg.get("SUITE_AEAD_TOKEN", "aesgcm")))
                    if curr_khs and new_khs and curr_khs == new_khs and current_aead_token != new_aead_token:
                        is_aead_shift = True
                        transport_base_k_d2g = active_context.get("transport_base_k_d2g")
                        transport_base_k_g2d = active_context.get("transport_base_k_g2d")
                        base_session_id = active_context.get("session_id")
                        old_peer_addr = active_context.get("peer_addr")
                        new_kem_name = active_context.get("kem_name")
                        new_sig_name = active_context.get("sig_name")

                if is_aead_shift and transport_base_k_d2g and transport_base_k_g2d and base_session_id:
                    traffic_k_d2g, _traffic_k_g2d = _derive_runtime_aead_keys(
                        transport_base_k_d2g,
                        transport_base_k_g2d,
                        base_session_id,
                        new_aead_token,
                        epoch=transport_epoch,
                    )
                    new_transport_base_k_d2g = transport_base_k_d2g
                    new_transport_base_k_g2d = transport_base_k_g2d
                    new_session_id = base_session_id
                    new_peer_addr = old_peer_addr
                    new_handshake_metrics = {
                        "ratchet_ok": True,
                        "ratchet_mode": "aead_only",
                        "ratchet_from_aead": current_aead_token or "",
                        "ratchet_to_aead": new_aead_token,
                        "ratchet_key_bytes": len(traffic_k_d2g),
                    }
                    logger.info(
                        "AEAD-only rekey ratchet selected",
                        extra={
                            "role": role,
                            "rid": rid,
                            "suite_id": new_suite["suite_id"],
                            "from_aead": current_aead_token,
                            "to_aead": new_aead_token,
                            "key_bytes": len(traffic_k_d2g),
                        },
                    )
                else:
                    rk_result = _perform_handshake(
                        role,
                        new_suite,
                        base_secret,
                        public_key,
                        cfg,
                        accept_deadline_s=float(timeout),
                        io_timeout_s=float(timeout),
                        epoch=transport_epoch,
                    )
                    if len(rk_result) >= 9:
                        (
                            new_transport_base_k_d2g,
                            new_transport_base_k_g2d,
                            _nd1,
                            _nd2,
                            new_session_id,
                            new_kem_name,
                            new_sig_name,
                            new_peer_addr,
                            new_handshake_metrics,
                        ) = rk_result
                    else:
                        (
                            new_transport_base_k_d2g,
                            new_transport_base_k_g2d,
                            _nd1,
                            _nd2,
                            new_session_id,
                            new_kem_name,
                            new_sig_name,
                            new_peer_addr,
                        ) = rk_result
                        new_handshake_metrics = {}
                if new_handshake_metrics:
                    new_handshake_metrics = dict(new_handshake_metrics)

                new_ids = _compute_aead_ids(new_suite, new_kem_name, new_sig_name)
                new_sender, new_receiver = _build_sender_receiver(
                    role,
                    new_ids,
                    new_session_id,
                    new_transport_base_k_d2g,
                    new_transport_base_k_g2d,
                    cfg,
                    aead_token=new_aead_token,
                    epoch=transport_epoch,
                )
                effective_suite = dict(new_suite)
                effective_suite["aead_token"] = new_aead_token
                effective_suite["data_aead_id"] = f"dap-{new_aead_token}"
                _discard_staged_rekey(rid)
                with context_lock:
                    active_context["staged_rekey"] = {
                        "rid": rid,
                        "suite_id": new_suite["suite_id"],
                        "suite_dict": effective_suite,
                        "session_id": new_session_id,
                        "epoch": transport_epoch,
                        "aead_ids": new_ids,
                        "sender": new_sender,
                        "receiver": new_receiver,
                        "transport_base_k_d2g": new_transport_base_k_d2g,
                        "transport_base_k_g2d": new_transport_base_k_g2d,
                        "kem_name": new_kem_name,
                        "sig_name": new_sig_name,
                        "peer_addr": new_peer_addr,
                        "aead_token": new_aead_token,
                        "handshake_metrics": dict(new_handshake_metrics) if new_handshake_metrics else {},
                        "gcs_sig_public": bytes(new_public) if isinstance(new_public, (bytes, bytearray)) else None,
                        "soft_transition_s": _soft_transition_s,
                    }
                ready_to_activate = note_local_rekey_ready(control_state, rid)
                release_rekey_slot = False

                if is_coordinator(role=role, coordinator_role=coordinator_role):
                    if ready_to_activate:
                        profile = mark_activation_sent(control_state, rid)
                        control_state.outbox.put(
                            {
                                "type": "activate_rekey",
                                "suite": profile.get("suite_id", new_suite["suite_id"]),
                                "aead": profile.get("aead_token", new_aead_token),
                                "rid": rid,
                                "t_ms": int(time.monotonic() * 1000.0),
                            }
                        )
                else:
                    control_state.outbox.put(
                        {
                            "type": "activate_ok",
                            "suite": new_suite["suite_id"],
                            "aead": new_aead_token,
                            "rid": rid,
                            "t_ms": int(time.monotonic() * 1000.0),
                        }
                    )

                logger.info(
                    "Control rekey context staged",
                    extra={
                        "role": role,
                        "suite_id": new_suite["suite_id"],
                        "rid": rid,
                        "aead_token": new_aead_token,
                        "epoch": transport_epoch,
                    },
                )
            except Exception as exc:
                if prev_token is not None:
                    cfg["SUITE_AEAD_TOKEN"] = prev_token
                _discard_staged_rekey(rid)
                with context_lock:
                    current_suite = active_context["suite"]
                with counters_lock:
                    counters.rekeys_fail += 1
                _finalize_rekey_timing()
                _rekey_cb_record_failure()
                record_rekey_result(control_state, rid, current_suite, success=False)
                control_state.outbox.put(
                    {
                        "type": "activate_fail",
                        "suite": current_suite,
                        "aead": str(cfg.get("SUITE_AEAD_TOKEN", "aesgcm")),
                        "rid": rid,
                        "reason": type(exc).__name__,
                        "t_ms": int(time.monotonic() * 1000.0),
                    }
                )
                logger.warning(
                    "Control rekey failed",
                    extra={"role": role, "suite_id": target_suite_id, "rid": rid, "error": str(exc)},
                )
            finally:
                if release_rekey_slot:
                    with rekey_guard:
                        active_rekeys.discard(rid)

        _rk_thread = threading.Thread(target=worker, daemon=True)
        _rk_thread.start()
        with rekey_guard:
            _rekey_threads.append(_rk_thread)

    with _setup_sockets(role, cfg, encrypted_peer=peer_addr) as sockets:
        selector = selectors.DefaultSelector()
        selector.register(sockets["encrypted"], selectors.EVENT_READ, data="encrypted")
        selector.register(sockets["plaintext_in"], selectors.EVENT_READ, data="plaintext_in")

        # Dynamic peer address for plaintext app (MAVProxy)
        # Initialize with configured default, but update based on ingress traffic
        # to support MAVProxy's ephemeral ports (when using --out).
        app_peer_addr = sockets["plaintext_peer"]

        def send_control(payload: dict) -> None:
            # F5-GUARD: refuse to send control frames when ENABLE_PACKET_TYPE
            # is disabled – the remote would deliver the 0x02-prefixed JSON
            # to the application as garbage data and never process it.
            if not cfg.get("ENABLE_PACKET_TYPE"):
                logger.warning(
                    "send_control suppressed: ENABLE_PACKET_TYPE is disabled",
                    extra={"role": role, "payload_type": payload.get("type")},
                )
                return
            body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
            frame = b"\x02" + body
            with context_lock:
                current_sender = active_context["sender"]
                encrypted_peer = sockets["encrypted_peer"]  # BUG-18 fix
            try:
                wire = current_sender.encrypt(frame)
            except Exception as exc:
                with counters_lock:
                    counters.drops += 1
                    counters.drop_other += 1
                logger.warning("Failed to encrypt control payload", extra={"role": role, "error": str(exc)})
                return
            try:
                sockets["encrypted"].sendto(wire, encrypted_peer)
                with counters_lock:
                    counters.enc_out += 1
                    counters.enc_bytes_out += len(wire)
                    counters._last_packet_mono = time.monotonic()
                    if counters._rekey_active and counters._rekey_blackout_end_mono is None:
                        counters._rekey_blackout_end_mono = counters._last_packet_mono
            except socket.error as exc:
                with counters_lock:
                    counters.drops += 1
                    counters.drop_other += 1
                logger.warning("Failed to send control payload", extra={"role": role, "error": str(exc)})
                return
            if (
                is_coordinator(role=role, coordinator_role=coordinator_role)
                and payload.get("type") == "activate_rekey"
                and isinstance(payload.get("rid"), str)
            ):
                _activate_staged_rekey(str(payload.get("rid")), activation_origin="coordinator_after_send")

        try:
            while True:
                if stop_after_seconds is not None and (time.time() - start_time) >= stop_after_seconds:
                    break

                timeout_status = tick_state_timeouts(
                    control_state,
                    negotiating_timeout_ms=_control_negotiating_timeout_ms,
                    swapping_timeout_ms=_control_swapping_timeout_ms,
                )
                if timeout_status is not None:
                    _discard_staged_rekey(timeout_status.get("rid") if isinstance(timeout_status.get("rid"), str) else None)
                    with rekey_guard:
                        rid = timeout_status.get("rid")
                        if isinstance(rid, str):
                            active_rekeys.discard(rid)
                    with counters_lock:
                        counters.rekeys_fail += 1
                    control_state.outbox.put(timeout_status)
                    logger.warning(
                        "Control state timeout recovery triggered",
                        extra={
                            "role": role,
                            "rid": timeout_status.get("rid"),
                            "reason": timeout_status.get("reason"),
                            "suite": timeout_status.get("suite"),
                            "aead": timeout_status.get("aead"),
                        },
                    )

                while True:
                    try:
                        control_payload = control_state.outbox.get_nowait()
                    except queue.Empty:
                        break
                    send_control(control_payload)

                # FIX-T3: UDP data-plane keepalive heartbeat.
                # NAT/firewall UDP mapping tables expire after 30-120s of
                # inactivity.  Send a 0x00 (heartbeat) encrypted packet
                # every 15s when no data flows, to keep the path alive
                # and detect dead links early (sendto will fail → FIX-T2 log).
                # FIX-B: Drain deferred destroy list at a safe point between
                # select() batches — no batch references to old objects exist here.
                # Only destroy objects that have passed their 5-second soft transition window.
                with _pending_destroy_lock:
                    _now_mono = time.monotonic()
                    _destroy_batch = [obj for t, obj in _pending_destroy if _now_mono >= t]
                    _pending_destroy[:] = [(t, obj) for t, obj in _pending_destroy if _now_mono < t]
                    
                    # Also clean up prev_receiver gracefully from active_context
                    if _destroy_batch:
                        with context_lock:
                            if active_context.get("prev_receiver") in _destroy_batch:
                                active_context.pop("prev_receiver", None)
                                active_context.pop("prev_peer_addr", None)
                                active_context.pop("prev_receiver_deadline", None)
                                logger.info(
                                    "Soft rekey transition expired",
                                    extra={"role": role},
                                )

                for _old_obj in _destroy_batch:
                    try:
                        _old_obj.destroy()
                    except Exception:
                        pass

                _keepalive_interval = 15.0
                with counters_lock:
                    _last_pkt = counters._last_packet_mono
                if _last_pkt is not None:
                    _idle_s = time.monotonic() - _last_pkt
                    if _idle_s >= _keepalive_interval:
                        try:
                            # FIX-C: Read encrypted_peer inside context_lock alongside sender
                            with context_lock:
                                _ka_sender = active_context["sender"]
                                _ka_peer = sockets["encrypted_peer"]
                            _ka_wire = _ka_sender.encrypt(b"\x00")
                            sockets["encrypted"].sendto(_ka_wire, _ka_peer)
                            with counters_lock:
                                counters.enc_out += 1
                                counters.enc_bytes_out += len(_ka_wire)
                                counters._last_packet_mono = time.monotonic()
                        except Exception:
                            logger.debug("Keepalive send failed", extra={"role": role})

                events = selector.select(timeout=0.1)
                for key, _mask in events:
                    sock = key.fileobj
                    data_type = key.data

                    if data_type == "plaintext_in":
                        # ── Batch-drain: read ALL queued datagrams ──────
                        # Pattern from MAVProxy process_master(), MAVSDK
                        # UdpConnection::receive(), mavlink-router
                        # handle_read(): drain the kernel buffer in a
                        # tight loop instead of one-recv-per-select.
                        # Cuts per-packet overhead from ~5 lock acqs to 1.
                        with context_lock:
                            _bd_sender = active_context["sender"]
                            _bd_enc_peer = sockets["encrypted_peer"]
                        _bd_ptx_in = 0
                        _bd_ptx_bytes = 0
                        _bd_enc_out = 0
                        _bd_enc_bytes = 0
                        _bd_drops = 0
                        _bd_drop_other = 0
                        _bd_enc_records = []  # (duration_ns, pt_len, ct_len)
                        _bd_ptype = cfg.get("ENABLE_PACKET_TYPE")
                        while True:
                            try:
                                payload, addr = sock.recvfrom(65535)
                            except (BlockingIOError, InterruptedError):
                                break
                            except OSError as exc:
                                if _is_windows_udp_reset(exc):
                                    logger.debug(
                                        "Ignoring Windows UDP reset on plaintext socket",
                                        extra={"role": role, "error": str(exc)},
                                    )
                                    continue
                                raise
                            if not payload:
                                continue
                            # FIX-T1: Latch app_peer_addr after first valid packet.
                            # Prevents a rogue local app from redirecting the decrypted
                            # stream to itself by sending a single packet to the proxy's
                            # plaintext port.  In benchmark mode (single MAVProxy) this
                            # latches on the first heartbeat and never changes.
                            if app_peer_addr is None:
                                app_peer_addr = addr
                                logger.info(
                                    "Latched plaintext app peer",
                                    extra={"role": role, "addr": addr},
                                )
                            _bd_ptx_in += 1
                            _bd_ptx_bytes += len(payload)

                            payload_out = (b"\x01" + payload) if _bd_ptype else payload
                            encrypt_start_ns = time.perf_counter_ns()
                            try:
                                wire = _bd_sender.encrypt(payload_out)
                            except SequenceOverflow as exc:
                                _bd_drops += 1
                                _bd_drop_other += 1
                                logger.warning(
                                    "Sequence space exhausted; requesting rekey",
                                    extra={"role": role, "error": str(exc)},
                                )
                                with context_lock:
                                    current_suite = active_context.get("suite")
                                if current_suite:
                                    try:
                                        rid = request_prepare(
                                            control_state,
                                            current_suite,
                                            aead_token=str(cfg.get("SUITE_AEAD_TOKEN", "aesgcm")),
                                        )
                                    except RuntimeError:
                                        logger.debug(
                                            "Rekey already in progress after sequence exhaustion",
                                            extra={"role": role},
                                        )
                                    else:
                                        logger.info(
                                            "Triggered control-plane rekey due to sequence exhaustion",
                                            extra={"role": role, "suite": current_suite, "rid": rid},
                                        )
                                continue
                            except Exception as exc:
                                _bd_drops += 1
                                _bd_drop_other += 1
                                logger.warning(
                                    "Encrypt failed",
                                    extra={
                                        "role": role,
                                        "error": str(exc),
                                        "payload_len": len(payload_out),
                                    },
                                )
                                continue
                            encrypt_elapsed_ns = time.perf_counter_ns() - encrypt_start_ns
                            _bd_enc_records.append(
                                (encrypt_elapsed_ns, len(payload_out), len(wire))
                            )
                            try:
                                sockets["encrypted"].sendto(wire, _bd_enc_peer)
                                _bd_enc_out += 1
                                _bd_enc_bytes += len(wire)
                            except socket.error:
                                _bd_drops += 1
                                _bd_drop_other += 1
                                # FIX-T2: log first occurrence per batch so operator sees LAN failures
                                if _bd_drops == 1:
                                    logger.warning(
                                        "Encrypted sendto failed (LAN down?)",
                                        extra={"role": role},
                                    )
                        # Single lock acquisition for entire batch
                        if _bd_ptx_in or _bd_drops:
                            _bd_now = time.monotonic()
                            with counters_lock:
                                counters.ptx_in += _bd_ptx_in
                                counters.ptx_bytes_in += _bd_ptx_bytes
                                counters.enc_out += _bd_enc_out
                                counters.enc_bytes_out += _bd_enc_bytes
                                counters.drops += _bd_drops
                                counters.drop_other += _bd_drop_other
                                counters._last_packet_mono = _bd_now
                                if counters._rekey_active and counters._rekey_blackout_end_mono is None:
                                    counters._rekey_blackout_end_mono = _bd_now
                                for _ed, _ep, _ec in _bd_enc_records:
                                    counters.record_encrypt(_ed, _ep, _ec)

                    elif data_type == "encrypted":
                        # ── Batch-drain encrypted datagrams ─────────
                        # Same drain pattern as plaintext_in above.
                        # Grab receiver + peer context ONCE per batch.
                        with context_lock:
                            _bd_receiver = active_context["receiver"]
                            _bd_prev_receiver = active_context.get("prev_receiver")
                            _bd_prev_peer = active_context.get("prev_peer_addr")
                            _bd_prev_deadline = active_context.get("prev_receiver_deadline")
                            _bd_expected_peer = active_context.get("peer_addr")
                            _bd_strict = bool(active_context.get("peer_match_strict", True))
                        _bd_sniff = sockets.get("sniff_peer")
                        _bd_ptype_dec = cfg.get("ENABLE_PACKET_TYPE")
                        _bd_enc_in = 0
                        _bd_enc_bytes_in = 0
                        _bd_ptx_out = 0
                        _bd_ptx_bytes_out = 0
                        _bd_dec_ok_records = []
                        _bd_peer_rx_seen = False
                        while True:
                            try:
                                wire, addr = sock.recvfrom(65535)
                            except (BlockingIOError, InterruptedError):
                                break
                            except OSError as exc:
                                if _is_windows_udp_reset(exc):
                                    logger.debug(
                                        "Ignoring Windows UDP reset on encrypted socket",
                                        extra={"role": role, "error": str(exc)},
                                    )
                                    continue
                                raise
                            if not wire:
                                continue

                            src_ip, src_port = addr
                            _bd_now_mono = time.monotonic()
                            _bd_current_peer_ok = _peer_matches_expected(addr, _bd_expected_peer, _bd_strict)
                            _bd_prev_peer_ok = (
                                _soft_transition_active(_bd_prev_receiver, _bd_prev_deadline, now_mono=_bd_now_mono)
                                and _peer_matches_expected(addr, _bd_prev_peer, _bd_strict)
                            )
                            if not _bd_current_peer_ok and not _bd_prev_peer_ok:
                                with counters_lock:
                                    counters.drops += 1
                                    counters.drop_src_addr += 1
                                logger.debug(
                                    "Dropped encrypted packet from unauthorized source",
                                    extra={"role": role, "expected": _bd_expected_peer, "received": addr},
                                )
                                continue

                            # Any traffic from the authorized peer means the peer is alive
                            # (even if decrypt later fails due to replay/auth).
                            _bd_peer_rx_seen = True

                            _bd_enc_in += 1
                            _bd_enc_bytes_in += len(wire)

                            cipher_len = len(wire)
                            decrypt_start_ns = time.perf_counter_ns()
                            _bd_reason_receiver = _bd_receiver
                            try:
                                plaintext, _bd_reason_receiver = _decrypt_with_transition(
                                    wire=wire,
                                    receiver=_bd_receiver,
                                    prev_receiver=_bd_prev_receiver,
                                    current_peer_ok=_bd_current_peer_ok,
                                    prev_peer_ok=_bd_prev_peer_ok,
                                    prev_deadline_mono=_bd_prev_deadline,
                                    now_mono=_bd_now_mono,
                                )
                            except ReplayError:
                                decrypt_elapsed_ns = time.perf_counter_ns() - decrypt_start_ns
                                with counters_lock:
                                    counters.drops += 1
                                    counters.drop_replay += 1
                                    counters.record_decrypt_fail(decrypt_elapsed_ns, cipher_len)
                                continue
                            except HeaderMismatch:
                                decrypt_elapsed_ns = time.perf_counter_ns() - decrypt_start_ns
                                with counters_lock:
                                    counters.drops += 1
                                    counters.drop_header += 1
                                    counters.record_decrypt_fail(decrypt_elapsed_ns, cipher_len)
                                continue
                            except AeadAuthError:
                                decrypt_elapsed_ns = time.perf_counter_ns() - decrypt_start_ns
                                with counters_lock:
                                    counters.drops += 1
                                    counters.drop_auth += 1
                                    counters.record_decrypt_fail(decrypt_elapsed_ns, cipher_len)
                                continue
                            except AeadError as exc:
                                decrypt_elapsed_ns = time.perf_counter_ns() - decrypt_start_ns
                                with counters_lock:
                                    counters.drops += 1
                                    reason, _seq = _parse_header_fields(
                                        CONFIG["WIRE_VERSION"], _bd_reason_receiver.ids, _bd_reason_receiver.session_id, wire
                                    )
                                    if reason in (
                                        "version_mismatch",
                                        "crypto_id_mismatch",
                                        "header_too_short",
                                        "header_unpack_error",
                                    ):
                                        counters.drop_header += 1
                                    elif reason == "session_mismatch":
                                        counters.drop_session_epoch += 1
                                    else:
                                        counters.drop_auth += 1
                                    counters.record_decrypt_fail(decrypt_elapsed_ns, cipher_len)
                                logger.warning(
                                    "Decrypt failed (classified)",
                                    extra={
                                        "role": role,
                                        "reason": reason,
                                        "wire_len": len(wire),
                                        "error": str(exc),
                                    },
                                )
                                continue
                            except Exception as exc:
                                decrypt_elapsed_ns = time.perf_counter_ns() - decrypt_start_ns
                                with counters_lock:
                                    counters.drops += 1
                                    counters.drop_other += 1
                                    counters.record_decrypt_fail(decrypt_elapsed_ns, cipher_len)
                                logger.warning(
                                    "Decrypt failed (other)",
                                    extra={"role": role, "error": str(exc), "wire_len": len(wire)},
                                )
                                continue

                            decrypt_elapsed_ns = time.perf_counter_ns() - decrypt_start_ns
                            if plaintext is None:
                                with counters_lock:
                                    counters.drops += 1
                                    last_reason = _bd_reason_receiver.last_error_reason()
                                    if last_reason == "auth":
                                        counters.drop_auth += 1
                                    elif last_reason == "header":
                                        counters.drop_header += 1
                                    elif last_reason == "replay":
                                        counters.drop_replay += 1
                                    elif last_reason == "session":
                                        counters.drop_session_epoch += 1
                                    elif last_reason is None or last_reason == "unknown":
                                        reason, _seq = _parse_header_fields(
                                            CONFIG["WIRE_VERSION"],
                                            _bd_reason_receiver.ids,
                                            _bd_reason_receiver.session_id,
                                            wire,
                                        )
                                        if reason in (
                                            "version_mismatch",
                                            "crypto_id_mismatch",
                                            "header_too_short",
                                            "header_unpack_error",
                                        ):
                                            counters.drop_header += 1
                                        elif reason == "session_mismatch":
                                            counters.drop_session_epoch += 1
                                        elif reason == "auth_fail_or_replay":
                                            counters.drop_auth += 1
                                        else:
                                            counters.drop_other += 1
                                    else:
                                        counters.drop_other += 1
                                    counters.record_decrypt_fail(decrypt_elapsed_ns, cipher_len)
                                continue

                            plaintext_len = len(plaintext)
                            _bd_dec_ok_records.append((decrypt_elapsed_ns, cipher_len, plaintext_len))

                            # Control-plane handling
                            if _bd_ptype_dec and plaintext and plaintext[0] == 0x02:
                                try:
                                    control_json = json.loads(plaintext[1:].decode("utf-8"))
                                except (UnicodeDecodeError, json.JSONDecodeError):
                                    with counters_lock:
                                        counters.drops += 1
                                        counters.drop_other += 1
                                    continue
                                result = handle_control(control_json, role, control_state)
                                for note in result.notes:
                                    if note.startswith("prepare_fail"):
                                        with counters_lock:
                                            counters.rekeys_fail += 1
                                        _rekey_cb_record_failure()
                                    elif note.startswith("activate_fail"):
                                        rid = control_json.get("rid")
                                        _discard_staged_rekey(rid if isinstance(rid, str) else None)
                                        _finalize_rekey_timing()
                                        with counters_lock:
                                            counters.rekeys_fail += 1
                                        _rekey_cb_record_failure()
                                        if isinstance(rid, str):
                                            with rekey_guard:
                                                active_rekeys.discard(rid)
                                for payload in result.send:
                                    control_state.outbox.put(payload)
                                if result.start_handshake:
                                    suite_next, rid = result.start_handshake
                                    profile = get_pending_profile(control_state, rid)
                                    _launch_rekey(
                                        suite_next,
                                        rid,
                                        trigger_reason=control_json.get("type"),
                                        target_aead_token=profile.get("aead_token"),
                                    )
                                if result.activate_rekey:
                                    suite_next, rid = result.activate_rekey
                                    if not _activate_staged_rekey(rid, activation_origin="remote_activate"):
                                        _discard_staged_rekey(rid)
                                        with context_lock:
                                            current_suite = active_context["suite"]
                                        with counters_lock:
                                            counters.rekeys_fail += 1
                                        _finalize_rekey_timing()
                                        _rekey_cb_record_failure()
                                        record_rekey_result(control_state, rid, current_suite, success=False)
                                        control_state.outbox.put(
                                            {
                                                "type": "activate_fail",
                                                "suite": current_suite,
                                                "aead": str(cfg.get("SUITE_AEAD_TOKEN", "aesgcm")),
                                                "rid": rid,
                                                "reason": "staged_context_missing",
                                                "t_ms": int(time.monotonic() * 1000.0),
                                            }
                                        )
                                        with rekey_guard:
                                            active_rekeys.discard(rid)
                                continue

                            if _bd_ptype_dec and plaintext:
                                ptype = plaintext[0]
                                if ptype == 0x01:
                                    out_bytes = plaintext[1:]
                                else:
                                    with counters_lock:
                                        counters.drops += 1
                                        counters.drop_other += 1
                                    continue
                            else:
                                out_bytes = plaintext

                            try:
                                sockets["plaintext_out"].sendto(out_bytes, app_peer_addr)
                            except socket.error:
                                with counters_lock:
                                    counters.drops += 1
                                    counters.drop_other += 1
                                continue
                            if _bd_sniff:
                                try:
                                    sockets["plaintext_out"].sendto(out_bytes, _bd_sniff)
                                except socket.error:
                                    # FIX-T4: count sniff copy failures so we know when
                                    # MavLinkMetricsCollector is undercounting
                                    with counters_lock:
                                        counters.sniff_drop += 1
                            _bd_ptx_out += 1
                            _bd_ptx_bytes_out += len(out_bytes)
                        # Single lock acquisition for successful-path counters
                        if _bd_enc_in or _bd_ptx_out:
                            _bd_now = time.monotonic()
                            with counters_lock:
                                counters.enc_in += _bd_enc_in
                                counters.enc_bytes_in += _bd_enc_bytes_in
                                counters.ptx_out += _bd_ptx_out
                                counters.ptx_bytes_out += _bd_ptx_bytes_out
                                counters._last_packet_mono = _bd_now
                                if _bd_peer_rx_seen:
                                    counters._last_peer_rx_mono = _bd_now
                                if counters._rekey_active and counters._rekey_blackout_end_mono is None:
                                    counters._rekey_blackout_end_mono = _bd_now
                                for _dd, _dc, _dp in _bd_dec_ok_records:
                                    counters.record_decrypt_ok(_dd, _dc, _dp)
        except KeyboardInterrupt:
            pass
        finally:
            selector.close()
            if manual_stop:
                manual_stop.set()
                for thread in manual_threads:
                    thread.join(timeout=0.5)
            if control_server is not None:
                try:
                    control_server.stop()
                except Exception:
                    pass
            # BUG-13 fix: join rekey threads to avoid mid-rekey teardown
            with rekey_guard:
                _rk_snapshot = list(_rekey_threads)
            for rk_t in _rk_snapshot:
                try:
                    rk_t.join(timeout=2.0)
                except Exception:
                    pass
            # FIX-B: Drain any remaining deferred-destroy objects before final cleanup
            with _pending_destroy_lock:
                _final_destroy_batch = [obj for _, obj in _pending_destroy] if _pending_destroy and isinstance(_pending_destroy[0], tuple) else list(_pending_destroy)
                _pending_destroy.clear()
            for _old_obj in _final_destroy_batch:
                try:
                    _old_obj.destroy()
                except Exception:
                    pass
            # Explicit key zeroization on shutdown (PART 3)
            with context_lock:
                final_sender = active_context.get("sender")
                final_receiver = active_context.get("receiver")
            for _obj in (final_sender, final_receiver):
                if _obj is not None:
                    try:
                        _obj.destroy()
                    except Exception:
                        pass

        # Final status write and stop the status writer thread if running
        try:
            with counters_lock:
                write_status({
                    "status": "stopped",
                    "suite": suite_id,
                    "key_handshake_id": profiles["key_handshake_id"],
                    "data_aead_id": profiles["data_aead_id"],
                    "counters": counters.to_dict(),
                    "ts_ns": time.time_ns(),
                })
        except Exception:
            pass

        # BUG-17 fix: stop_status_writer and status_thread are always defined
        # above (no need for fragile 'in locals()' check)
        try:
            stop_status_writer.set()
        except Exception:
            pass
        if status_thread is not None and status_thread.is_alive():
            try:
                status_thread.join(timeout=1.0)
            except Exception:
                pass

        return counters.to_dict()
