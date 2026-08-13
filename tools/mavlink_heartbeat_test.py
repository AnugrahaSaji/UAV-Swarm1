#!/usr/bin/env python3
"""MAVLink Heartbeat Generator and Monitor for testing MAVLink traffic over PQC tunnel."""

import argparse
import sys
import time

try:
    from pymavlink import mavutil
    HAS_PYMAVLINK = True
except ImportError:
    HAS_PYMAVLINK = False

def main():
    if not HAS_PYMAVLINK:
        print("Error: pymavlink is required for MAVLink heartbeat testing. Run 'pip install pymavlink'.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="MAVLink Heartbeat Test over PQC Tunnel")
    parser.add_argument("--role", choices=["sender", "receiver"], required=True, help="Sender or Receiver role")
    parser.add_argument("--side", choices=["drone", "gcs"], default=None, help="Target side (drone or gcs)")
    parser.add_argument("--count", type=int, default=10, help="Number of MAVLink heartbeats to send/receive")
    parser.add_argument("--rate", type=float, default=1.0, help="Heartbeat rate in Hz (messages per second)")
    args = parser.parse_args()

    if args.role == "sender":
        # Sender sends plaintext MAVLink to local proxy input port
        side = args.side if args.side else "drone"
        target_port = 47001 if side == "gcs" else 47003
        target_uri = f"udpout:127.0.0.1:{target_port}"

        print(f"--- Starting MAVLink Heartbeat Sender on {side.upper()} (target: {target_uri}) ---")
        mav_conn = mavutil.mavlink_connection(target_uri, source_system=1, source_component=1)

        interval = 1.0 / max(0.1, args.rate)
        for i in range(1, args.count + 1):
            # Send standard MAVLink HEARTBEAT message
            mav_conn.mav.heartbeat_send(
                type=mavutil.mavlink.MAV_TYPE_QUADROTOR,
                autopilot=mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                base_mode=mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                custom_mode=4,  # GUIDED mode
                system_status=mavutil.mavlink.MAV_STATE_ACTIVE
            )
            print(f"[{i}/{args.count}] Sent MAVLink HEARTBEAT (Type: QUADROTOR, System ID: 1, Comp ID: 1)")
            time.sleep(interval)
        print("\nMAVLink Heartbeat Sender complete!")

    elif args.role == "receiver":
        # Receiver listens for decrypted MAVLink on local proxy output port
        side = args.side if args.side else "gcs"
        bind_port = 47004 if side == "drone" else 47002
        bind_uri = f"udpin:127.0.0.1:{bind_port}"

        print(f"--- Listening for MAVLink Heartbeats on {side.upper()} (bind: {bind_uri}) ---")
        mav_conn = mavutil.mavlink_connection(bind_uri)

        received = 0
        timeout = 20.0
        start_time = time.monotonic()

        while received < args.count:
            msg = mav_conn.recv_match(type="HEARTBEAT", blocking=True, timeout=5.0)
            if msg is None:
                if time.monotonic() - start_time >= timeout:
                    print(f"\nTimed out waiting for MAVLink HEARTBEAT after {timeout}s. (Received {received}/{args.count})")
                    break
                continue
            
            received += 1
            src_sys = msg.get_srcSystem()
            src_comp = msg.get_srcComponent()
            mav_type = msg.type
            autopilot = msg.autopilot
            print(f"[{received}/{args.count}] Received decrypted MAVLink HEARTBEAT -> SysID: {src_sys}, CompID: {src_comp}, Type: {mav_type}, Autopilot: {autopilot}")

        print(f"\nDone receiving! Total MAVLink Heartbeats received: {received}/{args.count}")

if __name__ == "__main__":
    main()
