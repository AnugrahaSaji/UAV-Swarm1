#!/usr/bin/env python3
"""Live Pixhawk Hardware SMT State Sync & Verification Engine."""

import argparse
import hashlib
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from smt.sparse_merkle_tree import SparseMerkleTree
from smt.verifier import SMTVerifier
from smt.sync import SMTSyncPatch

try:
    from pymavlink import mavutil
    HAS_PYMAVLINK = True
except ImportError:
    HAS_PYMAVLINK = False


def main():
    parser = argparse.ArgumentParser(description="Live Pixhawk SMT State Sync Engine")
    parser.add_argument("--device", default="/dev/ttyACM0", help="Pixhawk serial device path")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    args = parser.parse_args()

    print("===================================================================")
    print("      LIVE PIXHAWK SMT STATE SYNCHRONIZATION ENGINE")
    print(f"      Reading Hardware Device: {args.device} @ {args.baud}")
    print("===================================================================\n")

    if not HAS_PYMAVLINK:
        print("Error: pymavlink required. Run 'pip install pymavlink'")
        sys.exit(1)

    try:
        mav = mavutil.mavlink_connection(args.device, baud=args.baud)
    except Exception as e:
        print(f"Failed to connect to Pixhawk on {args.device}: {e}")
        sys.exit(1)

    tree = SparseMerkleTree()
    drone_id = b"drone-1-pixhawk"
    drone_key = hashlib.sha256(drone_id).digest()

    print("Listening for live Pixhawk MAVLink telemetry to update Sparse Merkle Tree...\n")
    epoch = 0

    try:
        while True:
            msg = mav.recv_match(blocking=True, timeout=2.0)
            if msg is None:
                continue

            msg_type = msg.get_type()
            if msg_type in ["ATTITUDE", "VFR_HUD", "SYS_STATUS", "HEARTBEAT"]:
                epoch += 1
                
                # Construct state dictionary from live hardware sensor values
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
                elif msg_type == "SYS_STATUS":
                    state_dict["battery_volt"] = msg.voltage_battery / 1000.0
                    state_dict["cpu_load"] = msg.load / 10.0

                state_json = json.dumps(state_dict, sort_keys=True).encode("utf-8")
                val_hash = hashlib.sha256(state_json).digest()

                # Update Sparse Merkle Tree
                tree.update(drone_key, val_hash)
                root_hash = tree.root

                # Generate & Verify SMT Inclusion Proof
                proof = tree.create_proof(drone_key, epoch=epoch)
                is_valid = SMTVerifier.verify_membership(root_hash, proof)

                if epoch % 5 == 1:
                    print(f"[Epoch #{epoch:03d}] Sensor: {msg_type:12s} | SMT Root: 0x{root_hash.hex()[:16]}... | Verification: {'[AUTH PASSED]' if is_valid else '[FAILED]'}")

    except KeyboardInterrupt:
        print(f"\nStopped SMT Live Engine. Total SMT Epochs Processed: {epoch}")


if __name__ == "__main__":
    main()
