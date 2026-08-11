"""Security utilities for the scheduler control plane.

This module intentionally stays lightweight: it provides a shared-key (HMAC)
authentication mechanism for the sscheduler TCP JSON-RPC channel.

Design goals:
- Low overhead on constrained platforms (Raspberry Pi 4)
- No reliance on wall-clock sync (replay protected via nonces)
- Simple to integrate into existing one-request-per-connection RPC
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any, Mapping, Optional

from core.config import CONFIG


def get_drone_psk() -> bytes:
    """Retrieve the Drone PSK from config.

    Expected format: 32-byte hex string in CONFIG["DRONE_PSK"].
    """

    psk_hex = str(CONFIG.get("DRONE_PSK", "") or "").strip()
    if not psk_hex:
        # Fallback only with explicit opt-in in explicitly declared dev env.
        env_name = os.getenv("ENV", "prod").lower()
        allow_insecure = os.getenv("ALLOW_INSECURE_DEV_PSK", "0").lower() in {"1", "true", "yes", "on"}
        if env_name == "dev" and allow_insecure:
            return b"dev_insecure_psk_padding_32bytes"
        raise ValueError("DRONE_PSK not configured")

    try:
        psk = bytes.fromhex(psk_hex)
    except ValueError:
        # Legacy compat: accept raw string (truncate/pad to 32)
        raw = psk_hex.encode("utf-8")
        if len(raw) >= 32:
            return raw[:32]
        raise ValueError("DRONE_PSK must be 32 bytes hex")

    if len(psk) != 32:
        raise ValueError("DRONE_PSK must decode to 32 bytes")

    return psk


def get_control_auth_key() -> Optional[bytes]:
    """Return the shared key used to authenticate scheduler control RPC.

    Preference order:
    1) CONFIG["MAV_AUTH_KEY"] (UTF-8)
    2) CONFIG["DRONE_PSK"] (hex → 32 bytes)

    Returns None if neither key is configured.
    """

    raw = str(CONFIG.get("MAV_AUTH_KEY", "") or "").strip()
    if raw:
        return raw.encode("utf-8")

    try:
        return get_drone_psk()
    except Exception:
        return b"pqc_uav_scheduler_default_auth_key"


def create_nonce_hex(nbytes: int = 16) -> str:
    """Generate a random nonce encoded as lowercase hex."""

    if nbytes < 8:
        raise ValueError("nonce too short")
    return os.urandom(nbytes).hex()


def _canonical_params_json(params: Mapping[str, Any]) -> str:
    # Deterministic canonicalization for cross-host compatibility.
    return json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_request_mac(*, cmd: str, params: Mapping[str, Any], nonce_hex: str, key: bytes) -> str:
    """Compute HMAC-SHA256 over an authenticated request.

    Message format (UTF-8):
      v1\n<cmd>\n<nonce_hex>\n<canonical-json-params>

    Returns lowercase hex digest.
    """

    if not isinstance(key, (bytes, bytearray)) or not key:
        raise ValueError("auth key missing")

    payload = "\n".join(
        [
            "v1",
            str(cmd),
            str(nonce_hex),
            _canonical_params_json(params),
        ]
    ).encode("utf-8")

    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify_request_mac(*, cmd: str, params: Mapping[str, Any], nonce_hex: str, mac_hex: str, key: bytes) -> bool:
    expected = compute_request_mac(cmd=cmd, params=params, nonce_hex=nonce_hex, key=key)
    return hmac.compare_digest(str(mac_hex), expected)


def compute_telemetry_mac(*, envelope: Mapping[str, Any], nonce_hex: str, key: bytes) -> str:
    """Compute HMAC-SHA256 over scheduler telemetry envelope fields.

    Message format (UTF-8):
      telemetry-v1\n<nonce_hex>\n<canonical-json-envelope>

    The envelope passed here must exclude auth fields (nonce/mac).
    """

    if not isinstance(key, (bytes, bytearray)) or not key:
        raise ValueError("auth key missing")

    payload = "\n".join(
        [
            "telemetry-v1",
            str(nonce_hex),
            _canonical_params_json(envelope),
        ]
    ).encode("utf-8")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def verify_telemetry_mac(*, envelope: Mapping[str, Any], nonce_hex: str, mac_hex: str, key: bytes) -> bool:
    expected = compute_telemetry_mac(envelope=envelope, nonce_hex=nonce_hex, key=key)
    return hmac.compare_digest(str(mac_hex), expected)


# Legacy challenge/response helpers (kept for backwards compatibility)

def create_challenge() -> bytes:
    return os.urandom(32)


def compute_response(challenge: bytes, psk: bytes) -> str:
    return hmac.new(psk, challenge, hashlib.sha256).hexdigest()


def verify_response(challenge: bytes, response: str, psk: bytes) -> bool:
    expected = compute_response(challenge, psk)
    return hmac.compare_digest(response, expected)
