"""TCP JSON control server for core proxy.

This is intentionally small and dependency-free. It exists to bridge external
controllers/schedulers that speak the legacy TCP JSON protocol:

  {"cmd": "rekey", "suite": "cs-..."}

into the core in-band control plane (policy_engine.request_prepare).

Security model:
- The listener is expected to bind on a trusted interface.
- Commands are accepted only from an allow-list of peer IPs.
- Rekey commands are further restricted: only the drone host may initiate rekey.

This module must never log secrets.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Optional

from core.logging_utils import get_logger
from core.policy_engine import ControlState, coordinator_role_from_config, is_coordinator, request_prepare
from core.suites import (
    get_suite,
    is_runtime_aead_allowed,
    normalize_aead_token,
    normalize_aead_token_for_level,
    select_crypto_profile_for_capabilities,
)

# Maximum concurrent TCP control connections (prevents thread exhaustion DoS).
_MAX_CONTROL_WORKERS = 8
# Maximum simultaneous connections accepted from one peer IP.
_MAX_CONTROL_CONNECTIONS_PER_IP = 2
# Idle read timeout budget for a single control connection.
_CONTROL_READ_TIMEOUT_S = 2.0
_MAX_IDLE_READ_TIMEOUTS = 3
# Minimum interval in seconds between rekey commands from the same peer IP.
_REKEY_RATE_LIMIT_S = 5.0
# Bound untrusted capability offers so TCP handlers stay cheap.
_MAX_NEGOTIATION_ITEMS = 64
_MAX_NEGOTIATION_TOKEN_CHARS = 128

# OOB Hardening: Enforce this module NEVER imports or invokes heavy crypto.
# All PQC computations MUST strictly reside in core.async_proxy runtime workers.
import sys
if "liboqs" in sys.modules:
    # We do not crash the module to avoid global breakage, but we should never be the ones importing it.
    pass

_logger = get_logger("pqc")


def _coerce_str_list(value: object, *, field_name: str) -> list[str]:
    if isinstance(value, str):
        item = value.strip()
        if not item:
            return []
        if len(item) > _MAX_NEGOTIATION_TOKEN_CHARS:
            raise ValueError(f"{field_name}_token_too_long")
        return [item]
    if isinstance(value, (list, tuple)):
        if len(value) > _MAX_NEGOTIATION_ITEMS:
            raise ValueError(f"{field_name}_too_many_items")
        out: list[str] = []
        for entry in value:
            if isinstance(entry, str):
                token = entry.strip()
                if token:
                    if len(token) > _MAX_NEGOTIATION_TOKEN_CHARS:
                        raise ValueError(f"{field_name}_token_too_long")
                    out.append(token)
        return out
    return []


def _resolve_negotiated_profile(msg: dict) -> dict:
    """Select key-handshake suite + AEAD profile from capability offers/preferences."""

    offer = msg.get("offer")
    offer_map = offer if isinstance(offer, dict) else {}
    prefer = msg.get("prefer")
    prefer_map = prefer if isinstance(prefer, dict) else {}

    offered_suites = (
        _coerce_str_list(msg.get("suites"), field_name="suites")
        or _coerce_str_list(offer_map.get("suites"), field_name="offer.suites")
    )

    kem_tokens = (
        _coerce_str_list(msg.get("kem"), field_name="kem")
        or _coerce_str_list(offer_map.get("kem"), field_name="offer.kem")
    )
    sig_tokens = (
        _coerce_str_list(msg.get("sig"), field_name="sig")
        or _coerce_str_list(msg.get("ds"), field_name="ds")
        or _coerce_str_list(offer_map.get("sig"), field_name="offer.sig")
        or _coerce_str_list(offer_map.get("ds"), field_name="offer.ds")
    )
    aead_tokens = (
        _coerce_str_list(msg.get("aead"), field_name="aead")
        or _coerce_str_list(offer_map.get("aead"), field_name="offer.aead")
    )

    prefer_kem = _coerce_str_list(prefer_map.get("kem"), field_name="prefer.kem")
    prefer_sig = (
        _coerce_str_list(prefer_map.get("sig"), field_name="prefer.sig")
        or _coerce_str_list(prefer_map.get("ds"), field_name="prefer.ds")
    )
    prefer_aead = _coerce_str_list(prefer_map.get("aead"), field_name="prefer.aead")

    return select_crypto_profile_for_capabilities(
        offered_suites=offered_suites or None,
        kem_tokens=kem_tokens or None,
        sig_tokens=sig_tokens or None,
        aead_tokens=aead_tokens or None,
        prefer_kem_tokens=prefer_kem or None,
        prefer_sig_tokens=prefer_sig or None,
        prefer_aead_tokens=prefer_aead or None,
    )


@dataclass(frozen=True)
class ControlTcpConfig:
    host: str
    port: int
    allowed_peers: tuple[str, ...]
    rekey_allowed_peers: tuple[str, ...]
    role: str
    coordinator_role: str


class ControlTcpServer:
    """A small threaded TCP server that reads newline-delimited JSON.
    
    Hardening Model:
    This server operates strictly Out-Of-Band (OOB) to the data plane.
    It validates commands, maps them to negotiated cryptographic profiles,
    and enqueues the "intent to rekey" via policy_engine.
    It NEVER executes PQC operations or HKDF schedules itself; that authority
    is strictly deferred to the core.async_proxy worker loop.
    """

    def __init__(
        self,
        config: ControlTcpConfig,
        control_state: ControlState,
        *,
        quiet: bool = False,
    ) -> None:
        self._cfg = config
        self._state = control_state
        self._quiet = quiet
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._sock: Optional[socket.socket] = None
        self._pool: Optional[ThreadPoolExecutor] = None
        # Per-IP rekey rate-limit tracking: {ip: last_rekey_monotonic}
        self._rekey_ts: Dict[str, float] = {}
        self._rekey_ts_lock = threading.Lock()
        self._connection_slots = threading.BoundedSemaphore(_MAX_CONTROL_WORKERS)
        self._peer_conn_counts: Dict[str, int] = {}
        self._peer_conn_lock = threading.Lock()

    def start(self) -> bool:
        if self._thread and self._thread.is_alive():
            return True
        try:
            srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self._cfg.host, self._cfg.port))
            srv.listen(8)
            srv.settimeout(0.5)
            self._sock = srv
        except OSError as exc:
            _logger.warning(
                "TCP control listener failed to start",
                extra={
                    "role": self._cfg.role,
                    "host": self._cfg.host,
                    "port": self._cfg.port,
                    "error": str(exc),
                },
            )
            return False

        self._pool = ThreadPoolExecutor(
            max_workers=_MAX_CONTROL_WORKERS,
            thread_name_prefix="tcp_control",
        )
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()
        if not self._quiet:
            _logger.info(
                "TCP control listener started",
                extra={
                    "role": self._cfg.role,
                    "host": self._cfg.host,
                    "port": self._cfg.port,
                    "allowed_peers": list(self._cfg.allowed_peers),
                },
            )
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._pool is not None:
            self._pool.shutdown(wait=False)

    def _accept_loop(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                conn, addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            except Exception as exc:
                # Defensive: keep listener alive; do not log secrets.
                _logger.debug(
                    "TCP control accept loop error",
                    extra={"role": self._cfg.role, "error": str(exc)},
                )
                continue

            peer_ip = addr[0]
            if not _is_allowed_peer(peer_ip, self._cfg.allowed_peers):
                try:
                    _send_json(conn, {"ok": False, "error": "unauthorized"})
                finally:
                    try:
                        conn.close()
                    except OSError:
                        pass
                continue

            admission_error = self._reserve_connection(peer_ip)
            if admission_error is not None:
                try:
                    _send_json(conn, {"ok": False, "error": admission_error})
                finally:
                    try:
                        conn.close()
                    except OSError:
                        pass
                continue

            if self._pool is not None:
                try:
                    self._pool.submit(self._client_loop, conn, addr)
                except RuntimeError:
                    self._release_connection(peer_ip)
                    # Pool shut down; reject connection
                    try:
                        conn.close()
                    except OSError:
                        pass
            else:
                self._release_connection(peer_ip)
                try:
                    conn.close()
                except OSError:
                    pass

    def _reserve_connection(self, peer_ip: str) -> Optional[str]:
        """Reserve bounded listener capacity before worker handoff."""

        if not self._connection_slots.acquire(blocking=False):
            return "busy"
        with self._peer_conn_lock:
            active = self._peer_conn_counts.get(peer_ip, 0)
            if active >= _MAX_CONTROL_CONNECTIONS_PER_IP:
                self._connection_slots.release()
                return "too_many_connections"
            self._peer_conn_counts[peer_ip] = active + 1
        return None

    def _release_connection(self, peer_ip: str) -> None:
        """Release bounded listener capacity after worker exit."""

        with self._peer_conn_lock:
            active = self._peer_conn_counts.get(peer_ip, 0)
            if active <= 1:
                self._peer_conn_counts.pop(peer_ip, None)
            else:
                self._peer_conn_counts[peer_ip] = active - 1
        try:
            self._connection_slots.release()
        except ValueError:
            pass

    def _client_loop(self, conn: socket.socket, addr: tuple[str, int]) -> None:
        peer_ip = addr[0]
        # F10: Cap per-connection buffer to prevent slow-loris memory exhaustion.
        # WireGuard and production TCP servers enforce per-connection limits.
        _MAX_LINE_BYTES = 64 * 1024  # 64 KiB — generous for JSON control messages
        try:
            conn.settimeout(_CONTROL_READ_TIMEOUT_S)
            with conn:
                # Read line-by-line using raw socket recv to avoid buffering issues
                buf = b""
                idle_timeouts = 0
                while True:
                    if self._stop.is_set():
                        return
                    try:
                        chunk = conn.recv(4096)
                    except socket.timeout:
                        idle_timeouts += 1
                        if idle_timeouts >= _MAX_IDLE_READ_TIMEOUTS:
                            _send_json(conn, {"ok": False, "error": "idle_timeout"})
                            return
                        continue
                    if not chunk:
                        # EOF reached
                        return
                    idle_timeouts = 0
                    buf += chunk
                    # F10: Reject connections sending excessively long lines
                    if len(buf) > _MAX_LINE_BYTES:
                        _send_json(conn, {"ok": False, "error": "message_too_large"})
                        return
                    while b"\n" in buf:
                        line_bytes, buf = buf.split(b"\n", 1)
                        line = line_bytes.decode("utf-8", errors="replace").strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line)
                        except json.JSONDecodeError:
                            _send_json(conn, {"ok": False, "error": "bad_json"})
                            continue
                        if not isinstance(msg, dict):
                            _send_json(conn, {"ok": False, "error": "bad_message"})
                            continue
                        try:
                            resp = self._handle_message(msg, peer_ip)
                        except Exception as exc:
                            _logger.warning(
                                "TCP control _handle_message exception",
                                extra={"role": self._cfg.role, "peer": peer_ip, "error": str(exc), "cmd": msg.get("cmd")},
                            )
                            resp = {"ok": False, "error": f"internal_error:{type(exc).__name__}"}
                        _send_json(conn, resp)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            _logger.debug(
                "TCP control client loop socket/parse error",
                extra={"role": self._cfg.role, "peer": peer_ip, "error": str(exc)},
            )
            return
        except Exception as exc:
            _logger.warning(
                "TCP control client loop error",
                extra={"role": self._cfg.role, "peer": peer_ip, "error": str(exc)},
            )
            return
        finally:
            self._release_connection(peer_ip)

    def _log_control_decision(
        self,
        *,
        peer_ip: str,
        cmd: str,
        decision: str,
        suite_id: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        payload = {
            "role": self._cfg.role,
            "peer": peer_ip,
            "cmd": cmd,
            "decision": decision,
        }
        if suite_id:
            payload["suite"] = suite_id
        if error:
            payload["error"] = error
        _logger.info("TCP control decision", extra=payload)

    def _authorize_rekey_command(self, *, peer_ip: str, cmd_lower: str) -> Optional[dict]:
        if not _is_allowed_rekey_peer(
            peer_ip=peer_ip,
            rekey_allowed_peers=self._cfg.rekey_allowed_peers,
            server_role=self._cfg.role,
        ):
            self._log_control_decision(
                peer_ip=peer_ip,
                cmd=cmd_lower,
                decision="reject",
                error="unauthorized_rekey",
            )
            return {"ok": False, "error": "unauthorized_rekey"}
        if not is_coordinator(role=self._cfg.role, coordinator_role=self._cfg.coordinator_role):
            self._log_control_decision(
                peer_ip=peer_ip,
                cmd=cmd_lower,
                decision="reject",
                error="coordinator_only",
            )
            return {"ok": False, "error": "coordinator_only", "coordinator_role": self._cfg.coordinator_role}
        return None

    def _check_rekey_rate_limit(self, *, peer_ip: str, cmd_lower: str) -> Optional[dict]:
        now = time.monotonic()
        with self._rekey_ts_lock:
            last = self._rekey_ts.get(peer_ip, 0.0)
            if now - last < _REKEY_RATE_LIMIT_S:
                self._log_control_decision(
                    peer_ip=peer_ip,
                    cmd=cmd_lower,
                    decision="reject",
                    error="rekey_rate_limited",
                )
                return {"ok": False, "error": "rekey_rate_limited"}
            self._rekey_ts[peer_ip] = now
        return None

    def _resolve_direct_profile(self, msg: dict) -> dict:
        suite = msg.get("suite")
        if not isinstance(suite, str) or not suite.strip():
            raise ValueError("missing_suite")
        if len(suite.strip()) > _MAX_NEGOTIATION_TOKEN_CHARS:
            raise ValueError("suite_token_too_long")
        suite_dict = get_suite(suite)
        suite_id = suite_dict.get("suite_id") if isinstance(suite_dict, dict) else None
        if not isinstance(suite_id, str) or not suite_id.strip():
            raise ValueError("invalid_suite")
        profile = {"suite_id": suite_id}
        requested_aead = msg.get("aead")
        if requested_aead is not None:
            if not isinstance(requested_aead, str) or not requested_aead.strip():
                raise ValueError("invalid_aead")
            normalized_aead = normalize_aead_token_for_level(
                requested_aead.strip(),
                str(suite_dict.get("nist_level", "")),
            )
            if not is_runtime_aead_allowed(normalized_aead):
                raise ValueError("aead_not_runtime_allowed")
            profile["aead_token"] = normalized_aead
        return profile

    def _queue_rekey_intent(
        self,
        *,
        suite_id: str,
        aead_token: Optional[str],
        peer_ip: str,
        cmd_lower: str,
    ) -> dict:
        rid = request_prepare(self._state, suite_id, aead_token=aead_token)
        self._log_control_decision(
            peer_ip=peer_ip,
            cmd=cmd_lower,
            decision="intent_queued",
            suite_id=suite_id,
        )
        response = {"ok": True, "rid": rid, "suite": suite_id}
        if aead_token:
            response["aead"] = aead_token
        return response

    def _handle_message(self, msg: dict, peer_ip: str) -> dict:
        cmd = msg.get("cmd")
        if not isinstance(cmd, str):
            return {"ok": False, "error": "missing_cmd"}

        cmd_lower = cmd.lower().strip()

        # Log command receipt for debugging
        _logger.debug(
            "TCP control received command",
            extra={"role": self._cfg.role, "peer": peer_ip, "cmd": cmd_lower},
        )

        if cmd_lower in {"ping", "health"}:
            return {"ok": True, "role": self._cfg.role, "coordinator_role": self._cfg.coordinator_role}

        if cmd_lower == "status":
            with self._state.lock:
                return {
                    "ok": True,
                    "role": self._cfg.role,
                    "state": self._state.state,
                    "suite": self._state.current_suite,
                    "aead": self._state.current_aead,
                    "pending_suite": self._state.pending_suite,
                    "stats": dict(self._state.stats),
                    "active_rid": self._state.active_rid,
                    "last_rekey_ms": self._state.last_rekey_ms,
                    "last_rekey_suite": self._state.last_rekey_suite,
                    "last_status": self._state.last_status,
                }

        if cmd_lower == "rekey":
            auth_error = self._authorize_rekey_command(peer_ip=peer_ip, cmd_lower=cmd_lower)
            if auth_error is not None:
                return auth_error
            rl_error = self._check_rekey_rate_limit(peer_ip=peer_ip, cmd_lower=cmd_lower)
            if rl_error is not None:
                return rl_error
            try:
                profile = self._resolve_direct_profile(msg)
                return self._queue_rekey_intent(
                    suite_id=profile["suite_id"],
                    aead_token=profile.get("aead_token"),
                    peer_ip=peer_ip,
                    cmd_lower=cmd_lower,
                )
            except ValueError as exc:
                error = str(exc) or "bad_request"
                self._log_control_decision(
                    peer_ip=peer_ip,
                    cmd=cmd_lower,
                    decision="reject",
                    error=error,
                )
                return {"ok": False, "error": error}
            except RuntimeError as exc:
                return {"ok": False, "error": f"busy:{exc}"}
            except Exception as exc:
                _logger.debug(
                    "TCP control rekey failed",
                    extra={
                        "role": self._cfg.role,
                        "peer": peer_ip,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
                return {"ok": False, "error": f"rekey_failed:{type(exc).__name__}"}

        if cmd_lower in {"negotiate_rekey", "rekey_negotiate", "negotiate"}:
            auth_error = self._authorize_rekey_command(peer_ip=peer_ip, cmd_lower=cmd_lower)
            if auth_error is not None:
                return auth_error
            rl_error = self._check_rekey_rate_limit(peer_ip=peer_ip, cmd_lower=cmd_lower)
            if rl_error is not None:
                return rl_error

            try:
                profile = _resolve_negotiated_profile(msg)
                response = self._queue_rekey_intent(
                    suite_id=profile["suite_id"],
                    aead_token=profile.get("aead_token"),
                    peer_ip=peer_ip,
                    cmd_lower=cmd_lower,
                )
                response["selected"] = profile
                return response
            except ValueError as exc:
                error = str(exc) or "bad_request"
                self._log_control_decision(
                    peer_ip=peer_ip,
                    cmd=cmd_lower,
                    decision="reject",
                    error=error,
                )
                return {"ok": False, "error": error}
            except RuntimeError as exc:
                return {"ok": False, "error": f"busy:{exc}"}
            except NotImplementedError as exc:
                return {"ok": False, "error": f"no_matching_suite:{exc}"}
            except Exception as exc:
                _logger.debug(
                    "TCP control negotiate_rekey failed",
                    extra={
                        "role": self._cfg.role,
                        "peer": peer_ip,
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
                return {"ok": False, "error": f"negotiate_failed:{type(exc).__name__}"}

        return {"ok": False, "error": "unknown_cmd"}


def _send_json(conn: socket.socket, payload: dict) -> None:
    try:
        data = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    except (TypeError, ValueError):
        data = "{\"ok\":false,\"error\":\"encode_fail\"}"
    try:
        conn.sendall((data + "\n").encode("utf-8", errors="replace"))
    except OSError:
        pass


def _is_allowed_peer(peer_ip: str, allowed_peers: Iterable[str]) -> bool:
    for allowed in allowed_peers:
        if peer_ip == allowed:
            return True
    # Always allow loopback.
    return peer_ip in {"127.0.0.1", "::1"}


def _is_allowed_rekey_peer(*, peer_ip: str, rekey_allowed_peers: Iterable[str], server_role: str) -> bool:
    """Return True if this peer may request cmd=rekey.

    Policy:
    - Only the drone host(s) may initiate rekey.
    - Additionally allow loopback only when the control listener runs on the drone itself,
      so local drone tooling can drive rekeys without exposing that power to the GCS host.
    """

    for allowed in rekey_allowed_peers:
        if peer_ip == allowed:
            return True

    if server_role == "drone" and peer_ip in {"127.0.0.1", "::1"}:
        return True
    return False


def build_allowed_peers(*, cfg: dict) -> tuple[str, ...]:
    """Build peer allow-list from CONFIG.

    Includes LAN + tailscale endpoints when present.
    """

    peers: list[str] = []
    for key in (
        "DRONE_HOST",
        "GCS_HOST",
        "DRONE_HOST_LAN",
        "GCS_HOST_LAN",
        "DRONE_HOST_TAILSCALE",
        "GCS_HOST_TAILSCALE",
    ):
        value = cfg.get(key)
        if isinstance(value, str) and value and value not in peers:
            peers.append(value)
    return tuple(peers)


def build_rekey_allowed_peers(*, cfg: dict) -> tuple[str, ...]:
    """Build allow-list for cmd=rekey.

    Restrict to drone endpoints only.
    """

    peers: list[str] = []
    for key in (
        "DRONE_HOST",
        "DRONE_HOST_LAN",
        "DRONE_HOST_TAILSCALE",
    ):
        value = cfg.get(key)
        if isinstance(value, str) and value and value not in peers:
            peers.append(value)
    return tuple(peers)


def start_control_server_if_enabled(
    *,
    role: str,
    cfg: dict,
    control_state: ControlState,
    quiet: bool,
    enabled: bool,
) -> Optional[ControlTcpServer]:
    if not enabled:
        return None

    host_key = "GCS_CONTROL_HOST" if role == "gcs" else "DRONE_CONTROL_HOST"
    port_key = "GCS_CONTROL_PORT" if role == "gcs" else "DRONE_CONTROL_PORT"
    host = str(cfg.get(host_key) or "0.0.0.0")
    port = int(cfg.get(port_key) or 48080)

    coordinator_role = coordinator_role_from_config(cfg)

    server = ControlTcpServer(
        ControlTcpConfig(
            host=host,
            port=port,
            allowed_peers=build_allowed_peers(cfg=cfg),
            rekey_allowed_peers=build_rekey_allowed_peers(cfg=cfg),
            role=role,
            coordinator_role=coordinator_role,
        ),
        control_state,
        quiet=quiet,
    )
    if not server.start():
        return None
    return server
