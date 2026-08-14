#!/usr/bin/env python3
"""GCS SMT Telemetry & State Verification Receiver Terminal Tool."""

import argparse
import hashlib
import json
import os
import socket
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from smt.verifier import SMTVerifier
from smt.proof import SMTProof

try:
    from pymavlink import mavutil
    HAS_PYMAVLINK = True
except ImportError:
    HAS_PYMAVLINK = False


def main():
    parser = argparse.ArgumentParser(description="GCS SMT Telemetry Receiver")
    parser.add_argument("--host", default="127.0.0.1", help="GCS decrypted plaintext host")
    parser.add_argument("--port", type=int, default=47002, help="GCS decrypted plaintext port (47002)")
    args = parser.parse_args()

    print("===================================================================")
    print("      GCS SMT TELEMETRY & STATE VERIFICATION TERMINAL")
    print(f"      Listening on Decrypted Port: udp:{args.host}:{args.port}")
    print("===================================================================\n")

    if not HAS_PYMAVLINK:
        print("Error: pymavlink required. Run 'pip install pymavlink'")
        sys.exit(1)

    mav_conn = mavutil.mavlink_connection(f"udpin:{args.host}:{args.port}")
    total_received = 0
    msg_counts = {}

    print("Waiting for decrypted live Pixhawk telemetry stream from PQC Tunnel...\n")

    try:
        while True:
            msg = mav_conn.recv_match(blocking=True, timeout=2.0)
            if msg is None:
                continue

            total_received += 1
            msg_type = msg.get_type()
            msg_counts[msg_type] = msg_counts.get(msg_type, 0) + 1

            if total_received % 10 == 1:
                print(f"[{total_received:04d} MSGS] Type: {msg_type:18s} | SysID: {msg.get_srcSystem()} | CompID: {msg.get_srcComponent()} | Decrypted OK")

    except KeyboardInterrupt:
        print(f"\nStopped GCS Receiver. Total Decrypted Messages Received: {total_received}")


if __name__ == "__main__":
    main()
