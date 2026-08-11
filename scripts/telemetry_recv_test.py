#!/usr/bin/env python3
"""
Telemetry Receiver Doctor (Drone Side)
Receives and validates scheduler telemetry packets from GCS.

Mirrors the safety gates in `sscheduler/sdrone.py`:
- Sender allowlist
- Optional nonce+HMAC authentication (fail-closed when key configured)
- Supports batched envelopes: `uav.pqc.telemetry.batch.v1`
"""

import socket
import time
import json
import sys
from pathlib import Path
from typing import Dict

# Add parent to path to load config
sys.path.insert(0, str(Path(__file__).parent.parent))
from core.config import CONFIG
from sscheduler.control_security import get_control_auth_key, verify_telemetry_mac

# Configuration mirroring sdrone.py
GCS_HOST = CONFIG.get("GCS_HOST")
PORT = int(CONFIG.get("GCS_TELEMETRY_PORT", 52080))
MAX_PACKET_SIZE = 65535
BATCH_SCHEMA = "uav.pqc.telemetry.batch.v1"

def main():
    print(f"--- Telemetry Receiver Doctor ---")
    print(f"Listening on 0.0.0.0:{PORT}")
    print(f"Allow-list IP: {GCS_HOST}")
    print(f"Max Packet Size: {MAX_PACKET_SIZE}")

    auth_key = get_control_auth_key()
    require_auth = bool(auth_key)
    if require_auth:
        print("Auth: enabled (nonce+HMAC)")
    else:
        print("Auth: disabled (no key configured) — UNSAFE")
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", PORT))

    last_seq = -1

    nonce_ttl_s = 120.0
    seen_nonces_expiry: Dict[str, float] = {}
    
    try:
        while True:
            data, addr = sock.recvfrom(65535)
            sender_ip = addr[0]
            
            # 1. IP Safety Gate
            if sender_ip != GCS_HOST:
                print(f"DROP: Packet from unauthorized IP {sender_ip}")
                continue
                
            # 2. Size Safety Gate
            if len(data) > MAX_PACKET_SIZE:
                print(f"DROP: Packet too large ({len(data)} bytes)")
                continue
                
            try:
                packet = json.loads(data.decode('utf-8'))
            except json.JSONDecodeError:
                print(f"INVALID: JSON decode failed")
                continue

            if not isinstance(packet, dict):
                print("INVALID: JSON payload is not an object")
                continue

            if require_auth:
                nonce_hex = str(packet.get("nonce", "") or "").strip()
                mac_hex = str(packet.get("mac", "") or "").strip()
                if not nonce_hex or not mac_hex or not auth_key:
                    print("DROP: missing auth fields")
                    continue
                envelope = {k: v for k, v in packet.items() if k not in {"nonce", "mac"}}
                if not verify_telemetry_mac(
                    envelope=envelope,
                    nonce_hex=nonce_hex,
                    mac_hex=mac_hex,
                    key=auth_key,
                ):
                    print("DROP: bad mac")
                    continue

                now = time.monotonic()
                if seen_nonces_expiry:
                    stale = [n for n, exp in seen_nonces_expiry.items() if exp <= now]
                    for n in stale:
                        seen_nonces_expiry.pop(n, None)
                if nonce_hex in seen_nonces_expiry:
                    print("DROP: replay")
                    continue
                seen_nonces_expiry[nonce_hex] = now + nonce_ttl_s
                
            # 3. Schema Safety Gate
            schema = str(packet.get("schema", "") or "")
            if schema != BATCH_SCHEMA:
                print(f"INVALID: Wrong schema {schema!r}")
                continue

            # Metrics (best-effort; envelope contents are not strictly defined)
            seq = packet.get("batch_seq", packet.get("seq", 0))
            batch_wall_ns = packet.get("batch_wall_ns", 0)
            try:
                age_ms = ((time.time_ns() - int(batch_wall_ns)) / 1_000_000.0) if batch_wall_ns else -1.0
            except Exception:
                age_ms = -1.0
            active_suite = None
            
            status = "OK"
            if last_seq != -1 and seq != last_seq + 1:
                status = "SEQ_JUMP"

            print(f"RX {status}: seq={seq:<6} age={age_ms:>5.1f}ms size={len(data):<5} suite={active_suite}")
            
            last_seq = seq
            
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
        print("Done.")

if __name__ == "__main__":
    main()
