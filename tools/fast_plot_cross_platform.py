#!/usr/bin/env python3
"""
Fast Cross-Platform Chart Renderer.
Loads JSON benchmark datasets for rpi4_arm and windows_gcs_x86 and renders 300 DPI comparative plots in < 1 second.
"""

import json
import os
import sys

try:
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out_dir = os.path.join(ROOT, "logs", "benchmarks")

def render_charts():
    if not HAS_MATPLOTLIB:
        print("[ERROR] matplotlib not installed")
        return

    rpi_path = os.path.join(out_dir, "smt_recovery_latency_rpi4_arm.json")
    gcs_path = os.path.join(out_dir, "smt_recovery_latency_windows_gcs_x86.json")

    rpi_data = None
    gcs_data = None

    if os.path.exists(rpi_path):
        with open(rpi_path, "r", encoding="utf-8") as f:
            rpi_data = json.load(f)
    if os.path.exists(gcs_path):
        with open(gcs_path, "r", encoding="utf-8") as f:
            gcs_data = json.load(f)

    swarm_sizes = [5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
    mode_label = "Controlled MAVLink Telemetry Trace Replay"

    fig_dir = os.path.join(ROOT, "suite_benchmarks", "ieee_report_output", "figures")
    os.makedirs(fig_dir, exist_ok=True)
    plt.style.use("seaborn-v0_8-whitegrid" if "seaborn-v0_8-whitegrid" in plt.style.available else "default")

    def plot_single_graph(attack, role, title, filename):
        plt.figure(figsize=(8, 4.8), dpi=300)
        
        if rpi_data:
            rpi_medians = [rpi_data["stats"][attack][role][str(N)]["median"] for N in swarm_sizes]
            plt.plot(swarm_sizes, rpi_medians, 'o--', color='#d62728', linewidth=2.2, markersize=7, label="Raspberry Pi 4 (ARM Cortex-A72 @ 1.5 GHz)")
        else:
            plt.plot([], [], 'o--', color='#d62728', label="Raspberry Pi 4 (Pending Run)")

        if gcs_data:
            gcs_medians = [gcs_data["stats"][attack][role][str(N)]["median"] for N in swarm_sizes]
            plt.plot(swarm_sizes, gcs_medians, 's-', color='#1f77b4', linewidth=2.2, markersize=7, label="Windows GCS Workstation (x86_64 CPU)")
        else:
            plt.plot([], [], 's-', color='#1f77b4', label="Windows GCS (Pending Run)")

        plt.title(title, fontsize=11, fontweight="bold", pad=10)
        plt.xlabel("Swarm Size (Number of Drones N)", fontsize=10, fontweight="bold")
        plt.ylabel("SMT Recovery Latency T_recovery (ms)", fontsize=10, fontweight="bold")
        plt.xticks(swarm_sizes)
        plt.grid(True, linestyle="--", alpha=0.6)
        plt.legend(fontsize=9, loc="upper left")
        plt.tight_layout()

        out_path = os.path.join(fig_dir, filename)
        plt.savefig(out_path)
        plt.close()
        print(f"[CHART] Saved: {out_path}")

    # GENERATE 6 INDIVIDUAL 300 DPI GRAPHS
    plot_single_graph("sybil", "root", "GRAPH 1: Sybil Identity Rejection & SMT Recovery Latency — Leader/Root", "graph1_sybil_leader.png")
    plot_single_graph("sybil", "intermediate", "GRAPH 2: Sybil Identity Rejection & SMT Recovery Latency — Intermediate/Cluster Head", "graph2_sybil_intermediate.png")
    plot_single_graph("sybil", "leaf", "GRAPH 3: Sybil Identity Rejection & SMT Recovery Latency — Leaf/Follower", "graph3_sybil_leaf.png")

    plot_single_graph("ddos", "root", "GRAPH 4: Malicious Telemetry Burst SMT Recovery Latency — Leader/Root", "graph4_ddos_leader.png")
    plot_single_graph("ddos", "intermediate", "GRAPH 5: Malicious Telemetry Burst SMT Recovery Latency — Intermediate/Cluster Head", "graph5_ddos_intermediate.png")
    plot_single_graph("ddos", "leaf", "GRAPH 6: Malicious Telemetry Burst SMT Recovery Latency — Leaf/Follower", "graph6_ddos_leaf.png")

    # GENERATE COMBINED 6-PANEL FIGURE AT 300 DPI
    fig, axes = plt.subplots(2, 3, figsize=(18, 10), dpi=300)
    fig.suptitle(f"Empirical SMT Recovery Latency Benchmark ({mode_label})\nRaspberry Pi 4 (ARM Edge) vs. Windows GCS (x86 Workstation)", fontsize=14, fontweight="bold", y=0.98)

    configs = [
        ("sybil", "root", "GRAPH 1: Sybil — Leader/Root", axes[0, 0]),
        ("sybil", "intermediate", "GRAPH 2: Sybil — Intermediate/Cluster Head", axes[0, 1]),
        ("sybil", "leaf", "GRAPH 3: Sybil — Leaf/Follower", axes[0, 2]),
        ("ddos", "root", "GRAPH 4: DDoS — Leader/Root", axes[1, 0]),
        ("ddos", "intermediate", "GRAPH 5: DDoS — Intermediate/Cluster Head", axes[1, 1]),
        ("ddos", "leaf", "GRAPH 6: DDoS — Leaf/Follower", axes[1, 2]),
    ]

    for attack, role, title, ax in configs:
        if rpi_data:
            rpi_m = [rpi_data["stats"][attack][role][str(N)]["median"] for N in swarm_sizes]
            ax.plot(swarm_sizes, rpi_m, 'o--', color='#d62728', linewidth=2.0, markersize=6, label="RPi 4 (ARM)")
        else:
            ax.plot([], [], 'o--', color='#d62728', label="RPi 4 (Pending)")

        if gcs_data:
            gcs_m = [gcs_data["stats"][attack][role][str(N)]["median"] for N in swarm_sizes]
            ax.plot(swarm_sizes, gcs_m, 's-', color='#1f77b4', linewidth=2.0, markersize=6, label="Windows GCS (x86)")
        else:
            ax.plot([], [], 's-', color='#1f77b4', label="GCS (Pending)")

        ax.set_title(title, fontsize=10, fontweight="bold", pad=8)
        ax.set_xlabel("Swarm Size N", fontsize=9, fontweight="bold")
        ax.set_ylabel("Latency T_recovery (ms)", fontsize=9, fontweight="bold")
        ax.set_xticks(swarm_sizes)
        ax.grid(True, linestyle="--", alpha=0.6)
        ax.legend(fontsize=8, loc="upper left")

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    combined_path = os.path.join(fig_dir, "combined_6panel_latency_benchmark.png")
    plt.savefig(combined_path)
    plt.close()
    print(f"[CHART] Combined 6-Panel Figure saved to: {combined_path}")


if __name__ == "__main__":
    render_charts()
