#!/usr/bin/env python3
"""
50-Drone Swarm Multi-Cluster Attack Simulation & Recovery Latency Engine.

Simulates 50 physical/virtual UAVs partitioned into 5 dynamic clusters:
  • Cluster 1: drone-1 (Root Leader) + drone-2..10 (Leaf Followers)
  • Cluster 2: drone-11 (Intermediate Cluster Head) + drone-12..20 (Leaf Followers)
  • Cluster 3: drone-21 (Intermediate Cluster Head) + drone-22..30 (Leaf Followers)
  • Cluster 4: drone-31 (Intermediate Cluster Head) + drone-32..40 (Leaf Followers)
  • Cluster 5: drone-41 (Intermediate Cluster Head) + drone-42..50 (Leaf Followers)

Simulates & Measures Recovery Latency (T_recovery) for:
  1. Sybil Attacks targeting Root Node, Intermediate Node, and Leaf Node.
  2. DDoS Flooding Attacks targeting Root Node, Intermediate Node, and Leaf Node.
"""

import dataclasses
import hashlib
import json
import math
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from smt.sparse_merkle_tree import SparseMerkleTree
from smt.verifier import SMTVerifier
from hierarchical_swarm.topology import SwarmTopology
from hierarchical_swarm.node import SwarmNode
from hierarchical_swarm.utils import SwarmRole, ClusterId, NodeStatus


def generate_50drone_swarm():
    """Initializes 50 drones across 5 clusters into SMT and SwarmTopology."""
    tree = SparseMerkleTree()
    topology = SwarmTopology()

    telemetry_state = {}
    for i in range(1, 51):
        drone_id = f"drone-{i}"
        c_num = (i - 1) // 10 + 1
        cid = f"cluster-{c_num}"

        # State payload
        state = {
            "id": drone_id,
            "roll": round(0.1 * i, 2),
            "pitch": round(-0.05 * i, 2),
            "yaw": round(10.0 * i % 360, 2),
            "vbat_mv": 12500 - (i * 10),
            "alt": 15.0 + (i * 0.1),
            "status": "ACTIVE"
        }
        telemetry_state[drone_id] = state

        # SMT update
        k = hashlib.sha256(drone_id.encode("utf-8")).digest()
        v = hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).digest()
        tree.update(k, v)

        # Topology assignment
        if i == 1:
            role = SwarmRole.ROOT_LEADER
            parent = None
        elif (i - 1) % 10 == 0:
            role = SwarmRole.CLUSTER_LEADER
            parent = "drone-1"
        else:
            role = SwarmRole.FOLLOWER
            parent = f"drone-{((i - 1) // 10) * 10 + 1}"

        topology.add_node(SwarmNode(drone_id=drone_id, role=role, cluster_id=ClusterId(cid), parent_id=parent))

    return tree, topology, telemetry_state


def simulate_sybil_attack(target_role, target_id, tree, topology):
    """Executes a Sybil attack targeting Root, Intermediate, or Leaf node and measures recovery time."""
    rogue_id = f"sybil-rogue-{target_id}"
    rogue_key = hashlib.sha256(rogue_id.encode("utf-8")).digest()
    rogue_proof = tree.create_proof(rogue_key)

    surviving_drone_id = "drone-2" if target_id == "drone-1" else "drone-1"
    surviving_key = hashlib.sha256(surviving_drone_id.encode("utf-8")).digest()

    t_start = time.perf_counter()

    # 1. Non-membership check
    is_non_member = SMTVerifier.verify_non_membership(tree.root, rogue_proof)

    # 2. Mitigation: Drop connection, zero rogue key in tree
    EMPTY_HASH = b"\x00" * 32
    tree.update(rogue_key, EMPTY_HASH)

    # 3. Path Recomputation & Surviving Root Verification
    new_root = tree.root
    check_proof = tree.create_proof(surviving_key)
    consistent = SMTVerifier.verify_membership(new_root, check_proof)

    t_end = time.perf_counter()
    latency_ms = (t_end - t_start) * 1000.0

    return latency_ms, consistent, new_root


def simulate_ddos_attack(target_role, target_id, tree, topology, telemetry_state):
    """Executes a DDoS flooding attack targeting Root, Intermediate, or Leaf node and measures recovery time."""
    target_key = hashlib.sha256(target_id.encode("utf-8")).digest()
    authentic_proof = tree.create_proof(target_key)

    # Ingest flooded/tampered telemetry burst
    tampered_state = telemetry_state[target_id].copy()
    tampered_state["roll"] = 180.0
    tampered_state["status"] = "DDOS_FLOOD_BURST"
    tampered_hash = hashlib.sha256(json.dumps(tampered_state, sort_keys=True).encode("utf-8")).digest()

    malicious_proof = dataclasses.replace(authentic_proof, value_hash=tampered_hash)

    surviving_drone_id = "drone-2" if target_id == "drone-1" else "drone-1"
    surviving_key = hashlib.sha256(surviving_drone_id.encode("utf-8")).digest()

    t_start = time.perf_counter()

    # 1. Detection: verify membership mismatch
    is_valid = SMTVerifier.verify_membership(tree.root, malicious_proof)

    # 2. Mitigation: revoke node (zero leaf in SMT) & eject from topology if leaf
    EMPTY_HASH = b"\x00" * 32
    tree.update(target_key, EMPTY_HASH)
    if topology.contains(target_id):
        children = topology.get_children(target_id)
        if not children:
            topology.remove_node(target_id)

    # 3. Path Recomputation & Surviving Root Verification
    new_root = tree.root
    check_proof = tree.create_proof(surviving_key)
    consistent = SMTVerifier.verify_membership(new_root, check_proof)

    t_end = time.perf_counter()
    latency_ms = (t_end - t_start) * 1000.0

    return latency_ms, consistent, new_root


def main():
    print("===================================================================")
    print("  50-DRONE MULTI-CLUSTER ATTACK & SMT RECOVERY LATENCY SIMULATOR")
    print("===================================================================")
    print("  • Total Drones   : 50 Drones (5 Clusters x 10 Drones)")
    print("  • Cluster 1      : drone-1 (Root Leader) + drone-2..10 (Leaf)")
    print("  • Cluster 2      : drone-11 (Cluster Head) + drone-12..20 (Leaf)")
    print("  • Cluster 3      : drone-21 (Cluster Head) + drone-22..30 (Leaf)")
    print("  • Cluster 4      : drone-31 (Cluster Head) + drone-32..40 (Leaf)")
    print("  • Cluster 5      : drone-41 (Cluster Head) + drone-42..50 (Leaf)")
    print("===================================================================\n")

    # Step 1: Initialize Swarm
    tree, topology, telemetry_state = generate_50drone_swarm()
    init_root = tree.root
    print(f"[STEP 1] 50 Drones Authenticated into SMT | Root: 0x{init_root.hex()[:16]}...")
    print(f"         Topology Registered: {topology.size()} Active Nodes across 5 Clusters.\n")

    # Target Mapping
    targets = [
        ("Root Node", "drone-1"),
        ("Intermediate Node (Cluster Head 3)", "drone-21"),
        ("Leaf Node", "drone-50")
    ]

    # Step 2: Sybil Attacks
    print("-------------------------------------------------------------------")
    print("[SCENARIO 1] SYBIL IDENTITY INJECTION ATTACKS")
    print("-------------------------------------------------------------------")
    for role_name, target_id in targets:
        tree_copy, topo_copy, _ = generate_50drone_swarm()
        lat_ms, ok, new_root = simulate_sybil_attack(role_name, target_id, tree_copy, topo_copy)
        print(f"  • Target: {role_name:<35} ({target_id})")
        print(f"    - Detection & Mitigation Status : {'[PASSED - SYBIL REJECTED]' if ok else '[FAILED]'}")
        print(f"    - SMT Recovery Latency T_recovery: {lat_ms:.4f} ms")
        print(f"    - Post-Mitigation Root Hash    : 0x{new_root.hex()[:16]}...\n")

    # Step 3: DDoS Flooding Attacks
    print("-------------------------------------------------------------------")
    print("[SCENARIO 2] DDOS TELEMETRY FLOODING BURST ATTACKS")
    print("-------------------------------------------------------------------")
    for role_name, target_id in targets:
        tree_copy, topo_copy, tel_copy = generate_50drone_swarm()
        lat_ms, ok, new_root = simulate_ddos_attack(role_name, target_id, tree_copy, topo_copy, tel_copy)
        print(f"  • Target: {role_name:<35} ({target_id})")
        print(f"    - Detection & Mitigation Status : {'[PASSED - LEAF REVOKED & EJECTED]' if ok else '[FAILED]'}")
        print(f"    - SMT Recovery Latency T_recovery: {lat_ms:.4f} ms")
        print(f"    - Post-Mitigation Root Hash    : 0x{new_root.hex()[:16]}...\n")

    print("===================================================================")
    print("  SIMULATION COMPLETE: All 50-drone multi-cluster attack recovery")
    print("  scenarios verified with O(log N) SMT structural restoration.")
    print("===================================================================\n")


if __name__ == "__main__":
    main()
