"""Benchmark control-plane smoke test.

Validates the persistent newline-delimited TCP protocol used by:
- sscheduler/sdrone_bench.py (client)
- sscheduler/sgcs_bench.py (server)

It exercises:
1) unauthenticated ping
2) authenticated get_info
3) authenticated shutdown

No secrets are embedded; it relies on your configured MAV_AUTH_KEY / DRONE_PSK.
"""

import json
import socket
import sys
from pathlib import Path

# Ensure `secure-tunnel/` is on sys.path when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.config import CONFIG
from sscheduler.control_security import create_nonce_hex, compute_request_mac, get_control_auth_key


def _resolve_host(raw: str) -> str:
    raw = (raw or "").strip()
    if raw in {"0.0.0.0", "::", ""}:
        return "127.0.0.1"
    return raw


def _recv_line(sock: socket.socket, *, max_bytes: int = 64 * 1024) -> bytes:
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise RuntimeError("server closed connection")
        buf += chunk
        if len(buf) > max_bytes:
            raise RuntimeError("response too large")
    line, _, _rest = buf.partition(b"\n")
    return line


def _send_cmd(sock: socket.socket, *, cmd: str, key: bytes | None) -> dict:
    if cmd == "ping":
        payload = {"cmd": cmd}
    else:
        if not key:
            raise RuntimeError("auth key missing (set MAV_AUTH_KEY or DRONE_PSK)")
        nonce = create_nonce_hex()
        mac = compute_request_mac(cmd=cmd, params={}, nonce_hex=nonce, key=key)
        payload = {"cmd": cmd, "nonce": nonce, "mac": mac}

    sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))
    line = _recv_line(sock)
    return json.loads(line.decode("utf-8", errors="replace") or "{}")


def main() -> int:
    host = _resolve_host(str(CONFIG.get("GCS_CONTROL_HOST", "127.0.0.1")))
    port = int(CONFIG.get("GCS_CONTROL_PORT", 48080))
    key = get_control_auth_key()

    with socket.create_connection((host, port), timeout=5) as sock:
        print("ping", _send_cmd(sock, cmd="ping", key=key))
        print("get_info", _send_cmd(sock, cmd="get_info", key=key))
        print("shutdown", _send_cmd(sock, cmd="shutdown", key=key))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
