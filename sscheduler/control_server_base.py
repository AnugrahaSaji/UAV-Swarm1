from __future__ import annotations

import json
import os
import socket
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .common import log
from .control_security import get_control_auth_key, verify_request_mac


class ControlServerBase:
    """Small TCP JSON-RPC control server used by sscheduler.

    Security posture:
    - Optional sender allowlist (recommended: DRONE_HOST only)
    - Optional HMAC authentication with nonce replay protection
    - Request size and concurrency caps to reduce DoS risk

    Protocol:
    - One JSON request per connection
    - Server replies with one JSON response (newline terminated)

    Authenticated request fields:
      {
        "cmd": "start_proxy",
        ...params...,
        "nonce": "<hex>",
        "mac": "<hmac-hex>"
      }

    MAC is computed over (cmd, nonce, canonical JSON of params).
    """

    def __init__(
        self,
        proxy,
        host: str,
        port: int,
        suites: List[Dict[str, Any]],
        *,
        default_rate_mbps: float = 110.0,
        default_duration_s: float = 10.0,
        role: str = "gcs_follower",
        allowed_senders: Optional[List[str]] = None,
        auth_key: Optional[bytes] = None,
        require_auth: Optional[bool] = None,
        allow_unauth_ping: bool = True,
        max_request_bytes: int = 64 * 1024,
        max_clients: int = 32,
        max_clients_per_ip: int = 4,
        nonce_ttl_s: float = 120.0,
    ):
        self.proxy = proxy
        self.host = host
        self.port = int(port)
        self.suites = suites
        self.role = role

        self.rate_mbps = float(default_rate_mbps)
        self.duration = float(default_duration_s)

        self.allowed_senders = [s.strip() for s in (allowed_senders or []) if str(s).strip()]
        self._auth_key = auth_key if auth_key is not None else get_control_auth_key()
        allow_unsigned_control = os.getenv("ALLOW_UNSIGNED_SCHEDULER_CONTROL", "").strip().lower() in {"1", "true", "yes", "on"}
        if allow_unsigned_control:
            self.require_auth = False
        else:
            self.require_auth = bool(self._auth_key) if require_auth is None else bool(require_auth)
        self.allow_unauth_ping = bool(allow_unauth_ping)

        self.max_request_bytes = int(max_request_bytes)
        self.max_clients = int(max_clients)
        self.max_clients_per_ip = int(max_clients_per_ip)
        self.nonce_ttl_s = float(nonce_ttl_s)

        self.server_sock: Optional[socket.socket] = None
        self.running = False
        self._server_thread: Optional[threading.Thread] = None

        self.bound_host: Optional[str] = None
        self.bound_port: Optional[int] = None

        self._client_sem = threading.Semaphore(self.max_clients)
        self._active_lock = threading.Lock()
        self._active_by_ip: Dict[str, int] = {}

        self._nonce_lock = threading.Lock()
        self._seen_nonces_expiry: Dict[str, float] = {}

    def start(self):
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(5)
        self.server_sock.settimeout(1.0)

        try:
            sockname = self.server_sock.getsockname()
            if isinstance(sockname, tuple) and len(sockname) >= 2:
                self.bound_host = str(sockname[0])
                self.bound_port = int(sockname[1])
        except Exception:
            self.bound_host = None
            self.bound_port = None

        self.running = True
        self._server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self._server_thread.start()

        self.on_start()
        log(f"Control server listening on {self.host}:{self.port}")
        if self.allowed_senders:
            log(f"Control server allowed senders: {self.allowed_senders}")
        if self.require_auth and not self._auth_key:
            log("WARNING: control auth required but no auth key configured")

    def stop(self):
        self.running = False

        if self._server_thread:
            self._server_thread.join(timeout=2.0)

        if self.server_sock:
            try:
                self.server_sock.close()
            except Exception:
                pass

        self.on_stop()

    def on_start(self):
        pass

    def on_stop(self):
        pass

    def _server_loop(self):
        while self.running:
            try:
                assert self.server_sock is not None
                client, addr = self.server_sock.accept()
                peer_ip = str(addr[0]) if isinstance(addr, tuple) and addr else ""

                if self.allowed_senders and peer_ip not in self.allowed_senders:
                    self._reject_client(client, {"status": "error", "message": "sender_not_allowed"})
                    continue

                threading.Thread(
                    target=self._handle_client,
                    args=(client, addr),
                    daemon=True,
                ).start()
            except socket.timeout:
                continue
            except Exception as exc:
                if self.running:
                    log(f"Server error: {exc}")

    def _reject_client(self, client: socket.socket, response: dict):
        try:
            client.settimeout(2.0)
            client.sendall(json.dumps(response).encode("utf-8") + b"\n")
            try:
                client.shutdown(socket.SHUT_WR)
            except Exception:
                pass
            time.sleep(0.01)
        except Exception:
            pass
        finally:
            try:
                client.close()
            except Exception:
                pass

    def _inc_active(self, peer_ip: str) -> bool:
        with self._active_lock:
            current = int(self._active_by_ip.get(peer_ip, 0))
            if current >= self.max_clients_per_ip:
                return False
            self._active_by_ip[peer_ip] = current + 1
            return True

    def _dec_active(self, peer_ip: str):
        with self._active_lock:
            current = int(self._active_by_ip.get(peer_ip, 0))
            if current <= 1:
                self._active_by_ip.pop(peer_ip, None)
            else:
                self._active_by_ip[peer_ip] = current - 1

    def _nonce_check_and_store(self, nonce_hex: str) -> bool:
        """Return True if nonce is fresh and stored, False if replay."""
        now = time.monotonic()
        expiry = now + self.nonce_ttl_s

        with self._nonce_lock:
            # Opportunistic cleanup
            if self._seen_nonces_expiry:
                stale = [n for n, exp in self._seen_nonces_expiry.items() if exp <= now]
                for n in stale:
                    self._seen_nonces_expiry.pop(n, None)

            if nonce_hex in self._seen_nonces_expiry:
                return False

            self._seen_nonces_expiry[nonce_hex] = expiry
            return True

    def _handle_client(self, client: socket.socket, addr: Tuple[Any, ...]):
        peer_ip = str(addr[0]) if isinstance(addr, tuple) and addr else ""

        if not self._client_sem.acquire(blocking=False):
            self._reject_client(client, {"status": "error", "message": "busy"})
            return

        if peer_ip and not self._inc_active(peer_ip):
            self._client_sem.release()
            self._reject_client(client, {"status": "error", "message": "too_many_connections"})
            return

        try:
            client.settimeout(30.0)

            data = b""
            while b"\n" not in data:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk

                if len(data) > self.max_request_bytes:
                    self._reject_client(client, {"status": "error", "message": "request_too_large"})
                    return

                stripped = data.strip()
                if stripped.endswith(b"}"):
                    break

            if not data:
                return

            try:
                request_obj = json.loads(data.decode("utf-8").strip())
            except json.JSONDecodeError:
                self._reject_client(client, {"status": "error", "message": "invalid_json"})
                return

            if not isinstance(request_obj, dict):
                self._reject_client(client, {"status": "error", "message": "invalid_request"})
                return

            response = self._handle_command(request_obj)
            client.sendall(json.dumps(response).encode("utf-8") + b"\n")
        except Exception as exc:
            log(f"Client error ({addr}): {exc}")
        finally:
            try:
                client.close()
            except Exception:
                pass

            if peer_ip:
                try:
                    self._dec_active(peer_ip)
                except Exception:
                    pass

            try:
                self._client_sem.release()
            except Exception:
                pass

    def _auth_ok(self, request: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """Return (ok, error_code)."""

        cmd = str(request.get("cmd", "") or "")
        if cmd == "ping" and self.allow_unauth_ping:
            return True, None

        if not self.require_auth or not self._auth_key:
            return True, None

        nonce_hex = str(request.get("nonce", "") or "").strip()
        mac_hex = str(request.get("mac", "") or "").strip()
        if not nonce_hex or not mac_hex:
            return False, "auth_required"

        params = {
            k: v
            for k, v in request.items()
            if k not in {"cmd", "nonce", "mac"}
        }

        if not verify_request_mac(cmd=cmd, params=params, nonce_hex=nonce_hex, mac_hex=mac_hex, key=self._auth_key):
            return False, "auth_failed"

        if not self._nonce_check_and_store(nonce_hex):
            return False, "replay"

        return True, None

    def _handle_command(self, request: dict) -> dict:
        ok, err = self._auth_ok(request)
        if not ok:
            return {"status": "error", "message": err or "auth_failed"}

        cmd = str(request.get("cmd", "") or "")

        if cmd == "ping":
            return {"status": "ok", "message": "pong", "role": self.role}

        if cmd == "status":
            payload = {
                "status": "ok",
                "proxy_running": bool(self.proxy.is_running()),
                "current_suite": getattr(self.proxy, "current_suite", None),
            }
            current_aead = getattr(self.proxy, "current_aead", None)
            if current_aead:
                payload["current_aead"] = current_aead
            payload.update(self._status_payload())
            return payload

        if cmd == "configure":
            self.rate_mbps = float(request.get("rate_mbps", self.rate_mbps))
            self.duration = float(request.get("duration", self.duration))
            self.on_configure(request)
            return {"status": "ok", "message": "configured"}

        if cmd == "start_proxy":
            suite = request.get("suite")
            aead_token = request.get("aead")
            if not suite:
                return {"status": "error", "message": "missing_suite"}

            if aead_token:
                log(f"Start proxy requested for suite: {suite} (aead={aead_token})")
            else:
                log(f"Start proxy requested for suite: {suite}")

            if not self.proxy.start(suite, aead_token=aead_token):
                return {"status": "error", "message": "proxy_start_failed"}

            readiness_error = self.after_proxy_started(request)
            if readiness_error:
                return {"status": "error", "message": readiness_error}

            return {"status": "ok", "message": "proxy_started"}

        if cmd == "prepare_rekey":
            self.proxy.stop()
            self.on_prepare_rekey(request)
            return {"status": "ok", "message": "ready_for_rekey"}

        if cmd == "stop":
            self.proxy.stop()
            self.on_stop_command(request)
            return {"status": "ok", "message": "stopped"}

        if cmd == "get_suites":
            return {
                "status": "ok",
                "suites": [s.get("name") for s in self.suites if isinstance(s, dict) and s.get("name")],
            }

        custom = self.handle_custom_command(request)
        if custom is not None:
            return custom

        return {"status": "error", "message": f"unknown_command:{cmd}"}

    def _status_payload(self) -> Dict[str, Any]:
        return {}

    def on_configure(self, request: dict):
        log(f"Configured: rate={self.rate_mbps} Mbps, duration={self.duration}s")

    def after_proxy_started(self, request: dict) -> Optional[str]:
        return None

    def on_prepare_rekey(self, request: dict):
        pass

    def on_stop_command(self, request: dict):
        pass

    def handle_custom_command(self, request: dict) -> Optional[dict]:
        return None
