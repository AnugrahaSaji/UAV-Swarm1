import json
import socket
import time
from typing import Optional

from core.config import CONFIG

from .control_security import create_nonce_hex, compute_request_mac, get_control_auth_key


GCS_CONTROL_HOST = str(CONFIG.get("GCS_CONTROL_HOST", CONFIG.get("GCS_HOST")))
GCS_CONTROL_PORT = int(CONFIG.get("GCS_CONTROL_PORT", 48080))


def resolve_control_host(host: Optional[str]) -> str:
    candidate = str(host or GCS_CONTROL_HOST).strip()
    if candidate in ("0.0.0.0", "::", ""):
        return str(CONFIG.get("GCS_HOST", "127.0.0.1"))
    return candidate


_resolve_control_host = resolve_control_host


def send_gcs_command(cmd: str, host: Optional[str] = None, port: Optional[int] = None, **params) -> dict:
    sock = None
    try:
        target_host = resolve_control_host(host)
        target_port = int(port or GCS_CONTROL_PORT)

        request = {"cmd": cmd, **params}

        # Attach auth if a key is configured. Ping is allowed unauthenticated by server.
        auth_key = get_control_auth_key()
        if auth_key and cmd != "ping":
            nonce_hex = create_nonce_hex()
            mac_hex = compute_request_mac(cmd=cmd, params=params, nonce_hex=nonce_hex, key=auth_key)
            request = {**request, "nonce": nonce_hex, "mac": mac_hex}

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30.0)
        sock.connect((target_host, target_port))
        sock.sendall(json.dumps(request).encode("utf-8") + b"\n")

        buf = b""
        while b"\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk

        return json.loads(buf.decode("utf-8").strip() or "{}")
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
    finally:
        if sock:
            try:
                sock.close()
            except Exception:
                pass


def wait_for_gcs(timeout: float = 120.0, host: Optional[str] = None, port: Optional[int] = None) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if send_gcs_command("ping", host=host, port=port).get("status") == "ok":
            return True
        time.sleep(0.5)
    return False
