#!/usr/bin/env python3
"""Full-Duplex Bidirectional Bridge: Pixhawk hardware serial (/dev/ttyACM0) <-> Drone PQC Proxy."""

import argparse
import select
import socket
import sys
import threading
import time

try:
    import serial
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False


def main():
    if not HAS_SERIAL:
        print("Error: pyserial is required. Run 'pip install pyserial'")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Bidirectional Pixhawk serial to Drone PQC Proxy Bridge")
    parser.add_argument("--device", default="/dev/ttyACM0", help="Pixhawk serial device path")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate (115200 or 57600)")
    parser.add_argument("--tx-host", default="127.0.0.1", help="Drone Proxy plaintext input host")
    parser.add_argument("--tx-port", type=int, default=47003, help="Drone Proxy plaintext input port (47003)")
    parser.add_argument("--rx-host", default="127.0.0.1", help="Drone Proxy plaintext output bind host")
    parser.add_argument("--rx-port", type=int, default=47004, help="Drone Proxy plaintext output bind port (47004)")
    args = parser.parse_args()

    print("===================================================================")
    print(f" FULL-DUPLEX PIXHAWK PQC BRIDGE")
    print(f" Serial Device : {args.device} @ {args.baud}")
    print(f" Downlink (FC → Proxy) : UDP {args.tx_host}:{args.tx_port}")
    print(f" Uplink   (Proxy → FC) : UDP {args.rx_host}:{args.rx_port}")
    print("===================================================================\n")

    try:
        ser = serial.Serial(args.device, args.baud, timeout=0.01)
    except Exception as e:
        print(f"Failed to open serial port {args.device}: {e}")
        sys.exit(1)

    # UDP socket to send downlink telemetry to proxy
    tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # UDP socket to receive decrypted uplink commands from proxy (e.g., Mission Planner Actions)
    rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx_sock.bind((args.rx_host, args.rx_port))
    rx_sock.setblocking(False)

    stop_event = threading.Event()
    downlink_count = 0
    uplink_count = 0

    # Thread 1: Uplink (Proxy -> Pixhawk serial)
    def uplink_worker():
        nonlocal uplink_count
        while not stop_event.is_set():
            try:
                r, _, _ = select.select([rx_sock], [], [], 0.05)
                if r:
                    data, _addr = rx_sock.recvfrom(4096)
                    if data:
                        ser.write(data)
                        uplink_count += 1
                        print(f"[UPLINK #{uplink_count}] Mission Planner Command -> Pixhawk ({len(data)} bytes)")
            except Exception as e:
                if not stop_event.is_set():
                    time.sleep(0.01)

    uplink_thread = threading.Thread(target=uplink_worker, daemon=True)
    uplink_thread.start()

    # Main Thread: Downlink (Pixhawk serial -> Proxy)
    try:
        while True:
            data = ser.read(2048)
            if data:
                tx_sock.sendto(data, (args.tx_host, args.tx_port))
                downlink_count += 1
                if downlink_count % 50 == 1:
                    print(f"[DOWNLINK #{downlink_count}] Forwarded {len(data)} bytes from Pixhawk → PQC Proxy")
            else:
                time.sleep(0.002)
    except KeyboardInterrupt:
        print(f"\nStopping bridge... Total Downlink: {downlink_count}, Total Uplink: {uplink_count}")
    finally:
        stop_event.set()
        ser.close()
        tx_sock.close()
        rx_sock.close()


if __name__ == "__main__":
    main()
