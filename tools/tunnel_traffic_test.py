#!/usr/bin/env python3
"""Bidirectional Ping-pong test across the PQC encrypted tunnel data-plane."""

import argparse
import socket
import sys
import time

def main():
    parser = argparse.ArgumentParser(description="PQC Tunnel Traffic Tester")
    parser.add_argument("--role", choices=["sender", "receiver"], required=True, help="Sender or Receiver role")
    parser.add_argument("--side", choices=["drone", "gcs"], default=None, help="Target side (drone or gcs). Defaults: sender=drone (47003), receiver=gcs (47002)")
    parser.add_argument("--count", type=int, default=10, help="Number of test packets")
    args = parser.parse_args()

    if args.role == "sender":
        # If sending from Drone -> target 47003 (DRONE_PLAINTEXT_TX)
        # If sending from GCS -> target 47001 (GCS_PLAINTEXT_TX)
        side = args.side if args.side else "drone"
        target_port = 47001 if side == "gcs" else 47003
        target_host = "127.0.0.1"

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"--- Sending {args.count} test packets to {side.upper()} local proxy (127.0.0.1:{target_port}) ---")
        for i in range(1, args.count + 1):
            msg = f"PQC-TUNNEL-TEST-PACKET-#{i}"
            sock.sendto(msg.encode("utf-8"), (target_host, target_port))
            print(f"[{i}/{args.count}] Sent plaintext: '{msg}'")
            time.sleep(0.5)
        print("Done sending!")

    elif args.role == "receiver":
        # If receiving on GCS -> bind 47002 (GCS_PLAINTEXT_RX)
        # If receiving on Drone -> bind 47004 (DRONE_PLAINTEXT_RX)
        side = args.side if args.side else "drone"
        bind_port = 47004 if side == "drone" else 47002
        bind_host = "127.0.0.1"

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((bind_host, bind_port))
        print(f"--- Listening for decrypted packets on {side.upper()} local proxy (127.0.0.1:{bind_port}) ---")
        received = 0
        sock.settimeout(15.0)
        try:
            while received < args.count:
                data, addr = sock.recvfrom(4096)
                msg = data.decode("utf-8", errors="replace")
                # Format to match expected test output: strip timestamp if present or format clean
                clean_msg = msg.split(" [")[0] if " [" in msg else msg
                received += 1
                print(f"Received decrypted payload: '{clean_msg}'")
        except socket.timeout:
            print(f"\nTimed out waiting for packets after 15s. (Received {received}/{args.count})")
        print(f"\nDone receiving! Total received: {received}/{args.count}")

if __name__ == "__main__":
    main()
