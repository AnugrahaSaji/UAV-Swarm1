#!/usr/bin/env python3
"""GCS MAVLink Forwarder: Bridges decrypted proxy output (47002) to standard GCS port (14550)."""

import socket
import sys
import time

def main():
    listen_host = "127.0.0.1"
    listen_port = 47002
    target_host = "127.0.0.1"
    target_port = 14550

    print("===================================================================")
    print(f" PQC GCS MAVLink Bridge: 127.0.0.1:{listen_port} → 127.0.0.1:{target_port}")
    print(" Connect Mission Planner / QGroundControl via UDP port 14550")
    print("===================================================================\n")

    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx_sock.bind((listen_host, listen_port))

    tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    count = 0
    try:
        while True:
            data, _addr = rx_sock.recvfrom(4096)
            if data:
                tx_sock.sendto(data, (target_host, target_port))
                count += 1
                if count % 50 == 1:
                    print(f"[{count}] Forwarding decrypted MAVLink to Mission Planner / QGC (127.0.0.1:{target_port})...")
    except KeyboardInterrupt:
        print(f"\nStopped bridge. Total packets forwarded: {count}")
    finally:
        rx_sock.close()
        tx_sock.close()

if __name__ == "__main__":
    main()
