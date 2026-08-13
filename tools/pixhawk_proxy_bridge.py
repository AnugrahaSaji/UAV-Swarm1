#!/usr/bin/env python3
"""Bridge live Pixhawk hardware serial (/dev/ttyACM0) to Drone PQC Proxy plaintext input (47003)."""

import argparse
import socket
import sys
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

    parser = argparse.ArgumentParser(description="Bridge Pixhawk serial to Drone PQC Proxy")
    parser.add_argument("--device", default="/dev/ttyACM0", help="Pixhawk serial device path")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate (115200 or 57600)")
    parser.add_argument("--target-host", default="127.0.0.1", help="Drone Proxy host")
    parser.add_argument("--target-port", type=int, default=47003, help="Drone Proxy plaintext input port (47003)")
    args = parser.parse_args()

    print(f"--- Bridging Pixhawk ({args.device} @ {args.baud}) → Drone Proxy ({args.target_host}:{args.target_port}) ---")
    
    try:
        ser = serial.Serial(args.device, args.baud, timeout=0.1)
    except Exception as e:
        print(f"Failed to open serial port {args.device}: {e}")
        sys.exit(1)

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    packet_count = 0

    try:
        while True:
            data = ser.read(1024)
            if data:
                udp_sock.sendto(data, (args.target_host, args.target_port))
                packet_count += 1
                if packet_count % 10 == 1:
                    print(f"[{packet_count}] Forwarded {len(data)} bytes from Pixhawk to Drone Proxy...")
            time.sleep(0.005)
    except KeyboardInterrupt:
        print(f"\nStopped bridge. Total packets forwarded: {packet_count}")
    finally:
        ser.close()


if __name__ == "__main__":
    main()
