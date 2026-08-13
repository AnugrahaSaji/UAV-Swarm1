#!/usr/bin/env python3
"""Ping-pong test across the PQC encrypted tunnel data-plane."""

import argparse
import socket
import sys
import time

def main():
    parser = argparse.ArgumentParser(description="PQC Tunnel Traffic Tester")
    parser.add_argument("--role", choices=["sender", "receiver"], required=True, help="Sender (Drone side) or Receiver (GCS side)")
    parser.add_argument("--count", type=int, default=10, help="Number of test packets")
    args = parser.parse_args()

    if args.role == "sender":
        # Drone app sends plaintext to local proxy port 47003
        target_host = "127.0.0.1"
        target_port = 47003
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        print(f"--- Sending {args.count} test packets to local proxy (127.0.0.1:{target_port}) ---")
        for i in range(1, args.count + 1):
            msg = f"PQC-TUNNEL-TEST-PACKET-#{i} [{time.time()}]"
            sock.sendto(msg.encode("utf-8"), (target_host, target_port))
            print(f"[{i}/{args.count}] Sent plaintext: '{msg}'")
            time.sleep(0.5)
        print("Done sending!")

    elif args.role == "receiver":
        # GCS app receives decrypted plaintext from local proxy port 47002
        bind_host = "127.0.0.1"
        bind_port = 47002
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((bind_host, bind_port))
        print(f"--- Listening for decrypted packets on local proxy (127.0.0.1:{bind_port}) ---")
        received = 0
        sock.settimeout(15.0)
        try:
            while received < args.count:
                data, addr = sock.recvfrom(4096)
                msg = data.decode("utf-8", errors="replace")
                received += 1
                print(f"[{received}/{args.count}] Received decrypted payload: '{msg}'")
        except socket.timeout:
            print(f"\nTimed out waiting for packets after 15s. (Received {received}/{args.count})")
        print(f"Done receiving! Total received: {received}/{args.count}")

if __name__ == "__main__":
    main()
