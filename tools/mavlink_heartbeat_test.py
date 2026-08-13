#!/usr/bin/env python3
"""MAVLink Heartbeat Generator and Monitor with pure Python fallback."""

import argparse
import socket
import struct
import sys
import time

try:
    from pymavlink import mavutil
    HAS_PYMAVLINK = True
except ImportError:
    HAS_PYMAVLINK = False


def _crc_accumulate(data: bytes, crc: int = 0xFFFF) -> int:
    for b in data:
        tmp = b ^ (crc & 0xFF)
        tmp = (tmp ^ (tmp << 4)) & 0xFF
        crc = (crc >> 8) ^ (tmp << 8) ^ (tmp << 3) ^ (tmp >> 4)
    return crc & 0xFFFF


def _build_raw_mavlink1_heartbeat(seq: int = 0, sys_id: int = 1, comp_id: int = 1) -> bytes:
    # MAVLink v1 HEARTBEAT (msg_id = 0, len = 9 bytes)
    # Payload struct: <I (custom_mode), B (type), B (autopilot), B (base_mode), B (system_status), B (mavlink_version)
    custom_mode = 4  # GUIDED
    mav_type = 2     # MAV_TYPE_QUADROTOR
    autopilot = 3    # MAV_AUTOPILOT_ARDUPILOTMEGA
    base_mode = 89   # MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
    system_status = 4 # MAV_STATE_ACTIVE
    mavlink_version = 3

    payload = struct.pack("<IBBBBB", custom_mode, mav_type, autopilot, base_mode, system_status, mavlink_version)
    header = struct.pack("<BBBBBB", 0xFE, len(payload), seq & 0xFF, sys_id, comp_id, 0)
    
    # Calculate CRC over header[1:] + payload + CRC_EXTRA(50)
    crc = _crc_accumulate(header[1:] + payload)
    crc = _crc_accumulate(bytes([50]), crc)  # MAVLINK_MESSAGE_CRCS[0] = 50
    
    checksum = struct.pack("<H", crc)
    return header + payload + checksum


def _parse_raw_mavlink1_heartbeat(data: bytes):
    if len(data) < 17 or data[0] != 0xFE or data[5] != 0:
        return None
    seq = data[2]
    sys_id = data[3]
    comp_id = data[4]
    payload = data[6:15]
    custom_mode, mav_type, autopilot, base_mode, system_status, mavlink_version = struct.unpack("<IBBBBB", payload)
    return {
        "sys_id": sys_id,
        "comp_id": comp_id,
        "seq": seq,
        "type": mav_type,
        "autopilot": autopilot,
        "custom_mode": custom_mode,
        "system_status": system_status,
    }


def main():
    parser = argparse.ArgumentParser(description="MAVLink Heartbeat Test over PQC Tunnel")
    parser.add_argument("--role", choices=["sender", "receiver"], required=True, help="Sender or Receiver role")
    parser.add_argument("--side", choices=["drone", "gcs"], default=None, help="Target side (drone or gcs)")
    parser.add_argument("--count", type=int, default=10, help="Number of MAVLink heartbeats to send/receive")
    parser.add_argument("--rate", type=float, default=1.0, help="Heartbeat rate in Hz")
    args = parser.parse_args()

    if HAS_PYMAVLINK:
        print("Using pymavlink library for MAVLink protocol encoding/decoding.")
    else:
        print("pymavlink not found — using built-in pure Python MAVLink v1 protocol engine.")

    if args.role == "sender":
        side = args.side if args.side else "drone"
        target_port = 47001 if side == "gcs" else 47003
        target_host = "127.0.0.1"

        print(f"--- Starting MAVLink Heartbeat Sender on {side.upper()} (target: {target_host}:{target_port}) ---")
        interval = 1.0 / max(0.1, args.rate)

        if HAS_PYMAVLINK:
            mav_conn = mavutil.mavlink_connection(f"udpout:{target_host}:{target_port}", source_system=1, source_component=1)
            for i in range(1, args.count + 1):
                mav_conn.mav.heartbeat_send(
                    type=mavutil.mavlink.MAV_TYPE_QUADROTOR,
                    autopilot=mavutil.mavlink.MAV_AUTOPILOT_ARDUPILOTMEGA,
                    base_mode=mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
                    custom_mode=4,
                    system_status=mavutil.mavlink.MAV_STATE_ACTIVE
                )
                print(f"[{i}/{args.count}] Sent MAVLink HEARTBEAT (SysID: 1, CompID: 1, Type: QUADROTOR)")
                time.sleep(interval)
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            for i in range(1, args.count + 1):
                packet = _build_raw_mavlink1_heartbeat(seq=i, sys_id=1, comp_id=1)
                sock.sendto(packet, (target_host, target_port))
                print(f"[{i}/{args.count}] Sent raw MAVLink v1 HEARTBEAT packet ({len(packet)} bytes)")
                time.sleep(interval)

        print("\nMAVLink Heartbeat Sender complete!")

    elif args.role == "receiver":
        side = args.side if args.side else "gcs"
        bind_port = 47004 if side == "drone" else 47002
        bind_host = "127.0.0.1"

        print(f"--- Listening for decrypted MAVLink Heartbeats on {side.upper()} (bind: {bind_host}:{bind_port}) ---")
        received = 0
        timeout = 20.0
        start_time = time.monotonic()

        if HAS_PYMAVLINK:
            mav_conn = mavutil.mavlink_connection(f"udpin:{bind_host}:{bind_port}")
            while received < args.count:
                msg = mav_conn.recv_match(type="HEARTBEAT", blocking=True, timeout=5.0)
                if msg is None:
                    if time.monotonic() - start_time >= timeout:
                        print(f"\nTimed out waiting for MAVLink HEARTBEAT after {timeout}s. (Received {received}/{args.count})")
                        break
                    continue
                received += 1
                print(f"[{received}/{args.count}] Received decrypted MAVLink HEARTBEAT -> SysID: {msg.get_srcSystem()}, CompID: {msg.get_srcComponent()}, Type: {msg.type}, Autopilot: {msg.autopilot}")
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((bind_host, bind_port))
            sock.settimeout(5.0)
            while received < args.count:
                try:
                    data, addr = sock.recvfrom(4096)
                    parsed = _parse_raw_mavlink1_heartbeat(data)
                    if parsed:
                        received += 1
                        print(f"[{received}/{args.count}] Received decrypted MAVLink HEARTBEAT -> SysID: {parsed['sys_id']}, CompID: {parsed['comp_id']}, Type: QUADROTOR ({parsed['type']}), Autopilot: ARDUPILOT ({parsed['autopilot']})")
                except socket.timeout:
                    if time.monotonic() - start_time >= timeout:
                        print(f"\nTimed out waiting for MAVLink HEARTBEAT after {timeout}s. (Received {received}/{args.count})")
                        break

        print(f"\nDone receiving! Total MAVLink Heartbeats received: {received}/{args.count}")


if __name__ == "__main__":
    main()
