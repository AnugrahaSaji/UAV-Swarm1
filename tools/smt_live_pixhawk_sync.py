#!/usr/bin/env python3
"""Unified High-Speed Pixhawk Hardware SMT State Sync & PQC Bridge Engine."""

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

from smt.sparse_merkle_tree import SparseMerkleTree
from smt.verifier import SMTVerifier
from smt.sync import SMTSyncPatch

try:
    import serial
    from pymavlink import mavutil
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def main():
    parser = argparse.ArgumentParser(description="High-Speed Pixhawk SMT & PQC Bridge Engine")
    parser.add_argument("--device", default="/dev/ttyACM0", help="Pixhawk serial device path")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--tx-host", default="127.0.0.1", help="Drone Proxy input host")
    parser.add_argument("--tx-port", type=int, default=47003, help="Drone Proxy input port (47003)")
    args = parser.parse_args()

    print("===================================================================")
    print("      HIGH-SPEED PIXHAWK SMT ENGINE & PQC TUNNEL BRIDGE")
    print(f"      Hardware Device : {args.device} @ {args.baud}")
    print(f"      PQC Proxy Target: {args.tx_host}:{args.tx_port}")
    print("===================================================================\n")

    if not HAS_DEPS:
        print("Error: pyserial & pymavlink required. Run 'pip install pyserial pymavlink'")
        sys.exit(1)

    try:
        ser = serial.Serial(args.device, args.baud, timeout=0.001)
    except Exception as e:
        print(f"Failed to open serial port {args.device}: {e}")
        sys.exit(1)

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    mav_parser = mavutil.mavlink_connection(args.device, baud=args.baud)

    tree = SparseMerkleTree()
    drone_id = b"drone-1-pixhawk"
    drone_key = hashlib.sha256(drone_id).digest()

    epoch = 0

    try:
        while True:
            # Read all available serial bytes and immediately forward to PQC proxy
            raw_bytes = ser.read(4096)
            if raw_bytes:
                udp_sock.sendto(raw_bytes, (args.tx_host, args.tx_port))

                # Parse all pending MAVLink messages in buffer
                while True:
                    msg = mav_parser.recv_match(blocking=False)
                    if msg is None:
                        break

                    msg_type = msg.get_type()
                    if msg_type in ["ATTITUDE", "VFR_HUD", "SYS_STATUS", "HEARTBEAT", "HIGHRES_IMU"]:
                        epoch += 1
                        state_dict = {
                            "msg_type": msg_type,
                            "sys_id": msg.get_srcSystem(),
                            "comp_id": msg.get_srcComponent(),
                            "timestamp": time.time(),
                        }
                        if msg_type == "ATTITUDE":
                            state_dict["roll"] = round(msg.roll, 4)
                            state_dict["pitch"] = round(msg.pitch, 4)
                            state_dict["yaw"] = round(msg.yaw, 4)

                        state_json = json.dumps(state_dict, sort_keys=True).encode("utf-8")
                        val_hash = hashlib.sha256(state_json).digest()

                        # Update Sparse Merkle Tree & Verify Inclusion Proof
                        tree.update(drone_key, val_hash)
                        root_hash = tree.root

                        proof = tree.create_proof(drone_key, epoch=epoch)
                        is_valid = SMTVerifier.verify_membership(root_hash, proof)

                        if epoch % 10 == 1:
                            print(f"[Epoch #{epoch:05d}] Sensor: {msg_type:12s} | SMT Root: 0x{root_hash.hex()[:16]}... | Verification: {'[AUTH PASSED]' if is_valid else '[FAILED]'}")
            else:
                time.sleep(0.001)

    except KeyboardInterrupt:
        print(f"\nStopped High-Speed Engine. Total SMT Epochs Processed: {epoch}")
    finally:
        ser.close()
        udp_sock.close()


if __name__ == "__main__":
    main()
