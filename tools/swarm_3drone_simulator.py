#!/usr/bin/env python3
"""Hybrid 3-Drone Swarm Engine: 1 Physical Pixhawk + 2 Simulated Drone Nodes."""

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
from hierarchical_swarm.topology import SwarmTopology
from hierarchical_swarm.node import SwarmNode
from hierarchical_swarm.utils import SwarmRole, ClusterId

try:
    import serial
    from pymavlink import mavutil
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def main():
    parser = argparse.ArgumentParser(description="Hybrid 3-Drone Swarm Engine")
    parser.add_argument("--device", default="/dev/ttyACM0", help="Physical Pixhawk serial port")
    parser.add_argument("--baud", type=int, default=115200, help="Serial baud rate")
    parser.add_argument("--tx-host", default="127.0.0.1", help="Drone Proxy input host")
    parser.add_argument("--tx-port", type=int, default=47003, help="Drone Proxy input port (47003)")
    args = parser.parse_args()

    print("===================================================================")
    print("      HYBRID 3-DRONE SWARM ENGINE (PQC + SMT + HIERARCHY)")
    print("      • Drone 1 : PHYSICAL Pixhawk FC (/dev/ttyACM0) [Root Leader]")
    print("      • Drone 2 : SIMULATED Autonomous Drone      [Follower 1]")
    print("      • Drone 3 : SIMULATED Autonomous Drone      [Follower 2]")
    print("===================================================================\n")

    if not HAS_DEPS:
        print("Error: pyserial & pymavlink required. Run 'pip install pyserial pymavlink'")
        sys.exit(1)

    # Initialize Physical Serial for Drone 1
    has_physical = True
    try:
        ser = serial.Serial(args.device, args.baud, timeout=0.001)
        mav_parser = mavutil.mavlink_connection(args.device, baud=args.baud)
        print(f"[DRONE 1] Physical Pixhawk Connected on {args.device}")
    except Exception as e:
        print(f"[DRONE 1] Note: Physical serial {args.device} not found ({e}). Running in 3-Simulated Mode.")
        has_physical = False

    udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # Initialize Sparse Merkle Tree & Swarm Topology
    tree = SparseMerkleTree()
    topology = SwarmTopology()

    topology.add_node(SwarmNode(drone_id="drone-1", role=SwarmRole.ROOT_LEADER, cluster_id=ClusterId("cluster-1")))
    topology.add_node(SwarmNode(drone_id="drone-2", role=SwarmRole.FOLLOWER, cluster_id=ClusterId("cluster-1"), parent_id="drone-1"))
    topology.add_node(SwarmNode(drone_id="drone-3", role=SwarmRole.FOLLOWER, cluster_id=ClusterId("cluster-1"), parent_id="drone-1"))

    print("[TOPOLOGY] Established 3-Drone Cluster Tree (Root: Drone-1, Followers: Drone-2, Drone-3)\n")

    epoch = 0
    t0 = time.time()

    try:
        while True:
            epoch += 1
            dt = time.time() - t0

            # --- DRONE 1: Physical Pixhawk Data ---
            if has_physical:
                raw_bytes = ser.read(4096)
                if raw_bytes:
                    udp_sock.sendto(raw_bytes, (args.tx_host, args.tx_port))

            d1_state = {"id": "drone-1", "mode": "PHYSICAL", "epoch": epoch, "status": "ACTIVE"}
            d1_key = hashlib.sha256(b"drone-1").digest()
            d1_val = hashlib.sha256(json.dumps(d1_state, sort_keys=True).encode("utf-8")).digest()
            tree.update(d1_key, d1_val)

            # --- DRONE 2: Simulated Drone Data ---
            d2_state = {
                "id": "drone-2",
                "lat": 17.44550 + 0.0001 * (dt % 10),
                "lon": 78.34910 + 0.0001 * (dt % 10),
                "alt": 12.5 + (dt % 3),
                "status": "ACTIVE"
            }
            d2_key = hashlib.sha256(b"drone-2").digest()
            d2_val = hashlib.sha256(json.dumps(d2_state, sort_keys=True).encode("utf-8")).digest()
            tree.update(d2_key, d2_val)

            # --- DRONE 3: Simulated Drone Data ---
            d3_state = {
                "id": "drone-3",
                "lat": 17.44580 - 0.0001 * (dt % 10),
                "lon": 78.34940 - 0.0001 * (dt % 10),
                "alt": 15.0 + (dt % 5),
                "status": "ACTIVE"
            }
            d3_key = hashlib.sha256(b"drone-3").digest()
            d3_val = hashlib.sha256(json.dumps(d3_state, sort_keys=True).encode("utf-8")).digest()
            tree.update(d3_key, d3_val)

            # --- GLOBAL SMT SWARM ROOT & VERIFICATION ---
            root_hash = tree.root

            # Verify Inclusion Proofs for all 3 Drones
            proof_d1 = tree.create_proof(d1_key, epoch=epoch)
            proof_d2 = tree.create_proof(d2_key, epoch=epoch)
            proof_d3 = tree.create_proof(d3_key, epoch=epoch)

            v1 = SMTVerifier.verify_membership(root_hash, proof_d1)
            v2 = SMTVerifier.verify_membership(root_hash, proof_d2)
            v3 = SMTVerifier.verify_membership(root_hash, proof_d3)

            all_verified = v1 and v2 and v3

            if epoch % 20 == 1:
                print(f"[SWARM Epoch #{epoch:05d}] Active Drones: 3 | Global SMT Root: 0x{root_hash.hex()[:16]}... | 3-Node Auth: {'[ALL 3 AUTH PASSED]' if all_verified else '[FAILED]'}")

            time.sleep(0.05)

    except KeyboardInterrupt:
        print(f"\nStopped 3-Drone Engine. Total Swarm SMT Epochs: {epoch}")
    finally:
        if has_physical:
            ser.close()
        udp_sock.close()


if __name__ == "__main__":
    main()
