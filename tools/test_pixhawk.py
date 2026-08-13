#!/usr/bin/env python3
"""Test reading real MAVLink heartbeat from Pixhawk on /dev/ttyACM0."""

import sys
import time

try:
    from pymavlink import mavutil
except ImportError:
    print("Error: pymavlink not installed. Run 'pip install pymavlink'")
    sys.exit(1)

def main():
    device = "/dev/ttyACM0"
    for baud in [115200, 57600]:
        print(f"--- Listening for real Pixhawk HEARTBEAT on {device} (baud={baud}) ---")
        try:
            m = mavutil.mavlink_connection(device, baud=baud)
            hb = m.recv_match(type="HEARTBEAT", blocking=True, timeout=5.0)
            if hb:
                print("\nSUCCESS! Real Pixhawk Heartbeat Received:")
                print(f"  System ID: {hb.get_srcSystem()}")
                print(f"  Component ID: {hb.get_srcComponent()}")
                print(f"  Type: {hb.type}")
                print(f"  Autopilot: {hb.autopilot}\n")
                return 0
        except Exception as e:
            print(f"Error on baud {baud}: {e}")
    print("\nNo heartbeat received on 115200 or 57600 baud. Check USB cable and Pixhawk power.")
    return 1

if __name__ == "__main__":
    sys.exit(main())
