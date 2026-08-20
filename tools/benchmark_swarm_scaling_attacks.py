#!/usr/bin/env python3
"""
Automated Swarm Scaling Attack Benchmark Engine (N = 5 to 50).
Measures and plots Latency vs Swarm Size under Sybil Attacks and DDoS Flooding Attacks
evaluated across Root, Intermediate, and Leaf node roles.
"""

import hashlib
import json
import os
import sys
import time
from dataclasses import replace

try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from smt.sparse_merkle_tree import SparseMerkleTree
from smt.verifier import SMTVerifier
from hierarchical_swarm.topology import SwarmTopology
from hierarchical_swarm.node import SwarmNode
from hierarchical_swarm.utils import SwarmRole, ClusterId


def run_benchmark():
    swarm_sizes = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
    
    results = {
        "swarm_sizes": swarm_sizes,
        "sybil": {"root": [], "intermediate": [], "leaf": []},
        "ddos": {"root": [], "intermediate": [], "leaf": []}
    }

    print("===================================================================")
    print("   SWARM SCALING ATTACK BENCHMARK ENGINE (N = 5 TO 50 DRONES)")
    print("   • Attack Types : Sybil Non-Membership vs DDoS Tampering Burst")
    print("   • Node Roles   : Root Node, Intermediate Cluster Leader, Leaf Follower")
    print("===================================================================\n")

    for N in swarm_sizes:
        print(f"[*] Benchmarking Swarm Size N = {N:02d} Drones...")
        tree = SparseMerkleTree()
        topology = SwarmTopology()

        # Build N-drone SMT Tree & Cluster Topology
        root_id = "drone-1"
        inter_id = f"drone-{max(2, N // 2)}"
        leaf_id = f"drone-{N}"

        topology.add_node(SwarmNode(drone_id=root_id, role=SwarmRole.ROOT_LEADER, cluster_id=ClusterId("cluster-1")))
        
        for i in range(1, N + 1):
            drone_id = f"drone-{i}"
            key = hashlib.sha256(drone_id.encode("utf-8")).digest()
            state = {
                "id": drone_id,
                "cluster": "cluster-1" if i <= N // 2 else "cluster-2",
                "roll": 0.0,
                "pitch": 0.0,
                "vbat": 12600,
                "status": "ACTIVE"
            }
            val_hash = hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).digest()
            tree.update(key, val_hash)

            if i > 1:
                role = SwarmRole.CLUSTER_LEADER if drone_id == inter_id else SwarmRole.FOLLOWER
                cluster = "cluster-2" if i > N // 2 else "cluster-1"
                parent = root_id if cluster == "cluster-1" else inter_id
                topology.add_node(SwarmNode(drone_id=drone_id, role=role, cluster_id=ClusterId(cluster), parent_id=parent))

        # --- 1. SYBIL ATTACK BENCHMARK (Non-Membership Audit Latency) ---
        for role_name, target_id in [("root", root_id), ("intermediate", inter_id), ("leaf", leaf_id)]:
            rogue_id = f"sybil-rogue-{target_id}"
            rogue_key = hashlib.sha256(rogue_id.encode("utf-8")).digest()
            rogue_proof = tree.create_proof(rogue_key)

            iterations = 500
            t_start = time.perf_counter()
            for _ in range(iterations):
                SMTVerifier.verify_non_membership(tree.root, rogue_proof)
            t_total_ms = (time.perf_counter() - t_start) * 1000.0
            avg_sybil_lat_ms = t_total_ms / iterations
            results["sybil"][role_name].append(avg_sybil_lat_ms)

        # --- 2. DDOS FLOODING ATTACK BENCHMARK (Detection + Leaf Zeroing Isolation Latency) ---
        for role_name, target_id in [("root", root_id), ("intermediate", inter_id), ("leaf", leaf_id)]:
            target_key = hashlib.sha256(target_id.encode("utf-8")).digest()
            authentic_proof = tree.create_proof(target_key)

            tampered_state = {"id": target_id, "roll": 180.0, "status": "TAMPERED"}
            tampered_hash = hashlib.sha256(json.dumps(tampered_state, sort_keys=True).encode("utf-8")).digest()
            malicious_proof = replace(authentic_proof, value_hash=tampered_hash)

            iterations = 500
            t_start = time.perf_counter()
            for _ in range(iterations):
                is_valid = SMTVerifier.verify_membership(tree.root, malicious_proof)
                if not is_valid:
                    tree.update(target_key, b"\x00" * 32)
            t_total_ms = (time.perf_counter() - t_start) * 1000.0
            avg_ddos_lat_ms = t_total_ms / iterations
            results["ddos"][role_name].append(avg_ddos_lat_ms)

        print(f"   [OK] N = {N:02d} Benchmarked | Sybil Latency: {results['sybil']['leaf'][-1]:.4f} ms | DDoS Latency: {results['ddos']['leaf'][-1]:.4f} ms")

    # --- SAVE BENCHMARK DATA JSON ---
    out_dir = os.path.join(ROOT, "logs", "benchmarks")
    os.makedirs(out_dir, exist_ok=True)
    json_path = os.path.join(out_dir, "swarm_scaling_attack_metrics.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n[DATA] Benchmark JSON saved to: {json_path}")

    # --- GENERATE MATPLOTLIB CHARTS IF INSTALLED ---
    if HAS_MATPLOTLIB:
        fig_dir = os.path.join(ROOT, "suite_benchmarks", "ieee_report_output", "figures")
        os.makedirs(fig_dir, exist_ok=True)

        plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

        # CHART 1: Sybil Attack Latency vs Swarm Size
        plt.figure(figsize=(9, 5), dpi=300)
        plt.plot(swarm_sizes, results["sybil"]["root"], "o-", color="#1f77b4", linewidth=2.5, label="Root Node (Leader)")
        plt.plot(swarm_sizes, results["sybil"]["intermediate"], "s--", color="#ff7f0e", linewidth=2.5, label="Intermediate Node (Cluster Head)")
        plt.plot(swarm_sizes, results["sybil"]["leaf"], "^-.", color="#2ca02c", linewidth=2.5, label="Leaf Node (Follower)")
        plt.title("Sybil Attack Non-Membership Detection Latency vs. Swarm Size (N = 5 to 50)", fontsize=12, fontweight="bold", pad=12)
        plt.xlabel("Swarm Size (Number of Drones N)", fontsize=11, fontweight="bold")
        plt.ylabel("Detection Latency (ms)", fontsize=11, fontweight="bold")
        plt.xticks(swarm_sizes)
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend(fontsize=10, loc="upper left")
        plt.tight_layout()

        sybil_chart_path = os.path.join(fig_dir, "latency_vs_swarm_size_sybil.png")
        plt.savefig(sybil_chart_path)
        plt.close()
        print(f"[CHART] Sybil Attack Chart saved to: {sybil_chart_path}")

        # CHART 2: DDoS Flooding Latency vs Swarm Size
        plt.figure(figsize=(9, 5), dpi=300)
        plt.plot(swarm_sizes, results["ddos"]["root"], "o-", color="#d62728", linewidth=2.5, label="Root Node (Leader)")
        plt.plot(swarm_sizes, results["ddos"]["intermediate"], "s--", color="#9467bd", linewidth=2.5, label="Intermediate Node (Cluster Head)")
        plt.plot(swarm_sizes, results["ddos"]["leaf"], "^-.", color="#8c564b", linewidth=2.5, label="Leaf Node (Follower)")
        plt.title("DDoS Flooding Detection & Isolation Latency vs. Swarm Size (N = 5 to 50)", fontsize=12, fontweight="bold", pad=12)
        plt.xlabel("Swarm Size (Number of Drones N)", fontsize=11, fontweight="bold")
        plt.ylabel("Detection & Isolation Latency (ms)", fontsize=11, fontweight="bold")
        plt.xticks(swarm_sizes)
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend(fontsize=10, loc="upper left")
        plt.tight_layout()

        ddos_chart_path = os.path.join(fig_dir, "latency_vs_swarm_size_ddos.png")
        plt.savefig(ddos_chart_path)
        plt.close()
        print(f"[CHART] DDoS Flooding Chart saved to: {ddos_chart_path}")

        # CHART 3: Combined Comparison Chart
        plt.figure(figsize=(10, 6), dpi=300)
        plt.plot(swarm_sizes, results["sybil"]["root"], "o-", color="#1f77b4", linewidth=2, label="Sybil — Root Node")
        plt.plot(swarm_sizes, results["sybil"]["intermediate"], "s-", color="#ff7f0e", linewidth=2, label="Sybil — Intermediate Node")
        plt.plot(swarm_sizes, results["sybil"]["leaf"], "^-", color="#2ca02c", linewidth=2, label="Sybil — Leaf Node")
        plt.plot(swarm_sizes, results["ddos"]["root"], "o--", color="#d62728", linewidth=2, label="DDoS — Root Node")
        plt.plot(swarm_sizes, results["ddos"]["intermediate"], "s--", color="#9467bd", linewidth=2, label="DDoS — Intermediate Node")
        plt.plot(swarm_sizes, results["ddos"]["leaf"], "^--", color="#8c564b", linewidth=2, label="DDoS — Leaf Node")
        plt.title("SMT Security Latency vs. Growing Swarm Size (N = 5 to 50) across Roles & Attacks", fontsize=12, fontweight="bold", pad=12)
        plt.xlabel("Swarm Size (Number of Drones N)", fontsize=11, fontweight="bold")
        plt.ylabel("Latency (ms)", fontsize=11, fontweight="bold")
        plt.xticks(swarm_sizes)
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend(fontsize=9, loc="upper left", ncol=2)
        plt.tight_layout()

        combined_chart_path = os.path.join(fig_dir, "latency_vs_swarm_size_combined.png")
        plt.savefig(combined_chart_path)
        plt.close()
        print(f"[CHART] Combined Comparison Chart saved to: {combined_chart_path}")
    else:
        print("\n[NOTE] Matplotlib not installed on this device. Data saved to JSON. Install matplotlib via 'pip install matplotlib' to render PNG charts.")

    print("\n===================================================================")
    print("   BENCHMARK & DATA EXPORT COMPLETE SUCCESS!")
    print("===================================================================")


if __name__ == "__main__":
    run_benchmark()
