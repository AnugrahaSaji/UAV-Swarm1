#!/usr/bin/env python3
"""
PQC Benchmark Visualization Script

Generates plots from benchmark analysis data.
All values are derived from actual benchmark JSON files.

Plot types:
- Box plots for timing distributions
- Bar charts with error bars
- Log-scale comparisons
"""

import json
import csv
import os
from pathlib import Path
from typing import Dict, List, Any, Tuple
import numpy as np

# Attempt matplotlib import
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    from matplotlib.ticker import LogLocator, LogFormatter
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("[WARN] matplotlib not available, skipping plot generation")


# Color schemes for consistent visualization
NIST_LEVEL_COLORS = {
    "L1": "#2ecc71",  # Green
    "L3": "#f39c12",  # Orange
    "L5": "#e74c3c",  # Red
    "Classical": "#3498db",  # Blue
}

FAMILY_COLORS = {
    "ML-KEM": "#3498db",
    "Classic-McEliece": "#e74c3c",
    "HQC": "#2ecc71",
    "ML-DSA": "#9b59b6",
    "Falcon": "#f39c12",
    "SPHINCS+": "#1abc9c",
    "AES-GCM": "#34495e",
    "ChaCha20": "#7f8c8d",
    "Ascon": "#16a085",
}

OPERATION_COLORS = {
    "keygen": "#3498db",
    "encapsulate": "#2ecc71",
    "decapsulate": "#e74c3c",
    "sign": "#9b59b6",
    "verify": "#f39c12",
    "encrypt": "#1abc9c",
    "decrypt": "#e67e22",
    "full_handshake": "#34495e",
}


def load_csv_data(csv_path: Path) -> List[Dict[str, Any]]:
    """Load CSV file into list of dictionaries."""
    if not csv_path.exists():
        print(f"[WARN] CSV not found: {csv_path}")
        return []
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        return list(reader)


def load_raw_timings(csv_path: Path) -> Dict[Tuple[str, str], List[float]]:
    """Load raw timing data grouped by (algorithm, operation)."""
    data = load_csv_data(csv_path)
    grouped = {}
    
    for row in data:
        algo = row.get("algorithm", "Unknown")
        op = row.get("operation", "Unknown")
        key = (algo, op)
        
        if key not in grouped:
            grouped[key] = []
        
        try:
            # Convert ns to ms
            time_ms = float(row.get("wall_time_ns", 0)) / 1_000_000
            grouped[key].append(time_ms)
        except (ValueError, TypeError):
            pass
    
    return grouped


def plot_kem_boxplots(raw_data: Dict, output_dir: Path, iteration_count: int = 200):
    """Generate box plots for KEM operations."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    # Group by operation
    operations = ["keygen", "encapsulate", "decapsulate"]
    
    for op in operations:
        # Filter data for this operation
        op_data = {k[0]: v for k, v in raw_data.items() if k[1] == op}
        
        if not op_data:
            continue
        
        # Sort by median time
        sorted_algos = sorted(op_data.keys(), 
                              key=lambda x: np.median(op_data[x]) if op_data[x] else 0)
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        positions = range(1, len(sorted_algos) + 1)
        bp = ax.boxplot([op_data[a] for a in sorted_algos],
                        positions=positions,
                        patch_artist=True,
                        showfliers=True,
                        flierprops=dict(marker='o', markersize=3, alpha=0.5))
        
        # Color by family
        for i, (patch, algo) in enumerate(zip(bp['boxes'], sorted_algos)):
            family = None
            if "ML-KEM" in algo:
                family = "ML-KEM"
            elif "McEliece" in algo:
                family = "Classic-McEliece"
            elif "HQC" in algo:
                family = "HQC"
            color = FAMILY_COLORS.get(family, "#cccccc")
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        
        ax.set_xticks(positions)
        ax.set_xticklabels(sorted_algos, rotation=45, ha='right', fontsize=9)
        ax.set_ylabel('Time (ms)')
        ax.set_title(f'KEM {op.capitalize()} Timing Distribution\n'
                     f'(n={iteration_count} iterations per algorithm)')
        ax.grid(True, alpha=0.3, axis='y')
        
        # Log scale if range is large
        all_times = [t for times in op_data.values() for t in times]
        if all_times and max(all_times) / max(min(all_times), 0.001) > 100:
            ax.set_yscale('log')
            ax.set_ylabel('Time (ms, log scale)')
        
        plt.tight_layout()
        
        # Save
        pdf_path = output_dir / f"kem_{op}_boxplot.pdf"
        png_path = output_dir / f"kem_{op}_boxplot.png"
        plt.savefig(pdf_path, format='pdf', dpi=300, bbox_inches='tight')
        plt.savefig(png_path, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"[PLOT] Saved {pdf_path.name}")


def plot_sig_boxplots(raw_data: Dict, output_dir: Path, iteration_count: int = 200):
    """Generate box plots for signature operations."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    operations = ["keygen", "sign", "verify"]
    
    for op in operations:
        op_data = {k[0]: v for k, v in raw_data.items() if k[1] == op}
        
        if not op_data:
            continue
        
        sorted_algos = sorted(op_data.keys(),
                              key=lambda x: np.median(op_data[x]) if op_data[x] else 0)
        
        fig, ax = plt.subplots(figsize=(12, 6))
        
        positions = range(1, len(sorted_algos) + 1)
        bp = ax.boxplot([op_data[a] for a in sorted_algos],
                        positions=positions,
                        patch_artist=True,
                        showfliers=True,
                        flierprops=dict(marker='o', markersize=3, alpha=0.5))
        
        for i, (patch, algo) in enumerate(zip(bp['boxes'], sorted_algos)):
            family = None
            if "ML-DSA" in algo:
                family = "ML-DSA"
            elif "Falcon" in algo:
                family = "Falcon"
            elif "SPHINCS" in algo:
                family = "SPHINCS+"
            color = FAMILY_COLORS.get(family, "#cccccc")
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        
        ax.set_xticks(positions)
        ax.set_xticklabels(sorted_algos, rotation=45, ha='right', fontsize=9)
        ax.set_ylabel('Time (ms)')
        ax.set_title(f'Signature {op.capitalize()} Timing Distribution\n'
                     f'(n={iteration_count} iterations per algorithm)')
        ax.grid(True, alpha=0.3, axis='y')
        
        all_times = [t for times in op_data.values() for t in times]
        if all_times and max(all_times) / max(min(all_times), 0.001) > 100:
            ax.set_yscale('log')
            ax.set_ylabel('Time (ms, log scale)')
        
        plt.tight_layout()
        
        pdf_path = output_dir / f"sig_{op}_boxplot.pdf"
        png_path = output_dir / f"sig_{op}_boxplot.png"
        plt.savefig(pdf_path, format='pdf', dpi=300, bbox_inches='tight')
        plt.savefig(png_path, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"[PLOT] Saved {pdf_path.name}")


def plot_nist_level_comparison(stats_data: List[Dict], output_dir: Path):
    """Generate bar chart comparing NIST levels."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    # Group by level and operation
    by_level = {}
    for row in stats_data:
        level = row.get("nist_level", "Unknown")
        algo_type = row.get("algorithm_type", "Unknown")
        op = row.get("operation", "Unknown")
        
        try:
            mean_ms = float(row.get("mean_ms", 0))
            stdev_ns = float(row.get("stdev_ns", 0))
            stdev_ms = stdev_ns / 1_000_000
        except (ValueError, TypeError):
            continue
        
        key = (level, algo_type, op)
        if key not in by_level:
            by_level[key] = {"mean": mean_ms, "stdev": stdev_ms}
    
    # Create separate plots for KEM and SIG
    for algo_type in ["KEM", "SIG"]:
        type_data = {k: v for k, v in by_level.items() if k[1] == algo_type}
        
        if not type_data:
            continue
        
        levels = ["L1", "L3", "L5"]
        if algo_type == "KEM":
            ops = ["keygen", "encapsulate", "decapsulate"]
        else:
            ops = ["keygen", "sign", "verify"]
        
        fig, ax = plt.subplots(figsize=(10, 6))
        
        x = np.arange(len(levels))
        width = 0.25
        
        for i, op in enumerate(ops):
            means = []
            stds = []
            for level in levels:
                key = (level, algo_type, op)
                if key in type_data:
                    means.append(type_data[key]["mean"])
                    stds.append(type_data[key]["stdev"])
                else:
                    means.append(0)
                    stds.append(0)
            
            offset = (i - 1) * width
            bars = ax.bar(x + offset, means, width, 
                         label=op.capitalize(),
                         color=OPERATION_COLORS.get(op, "#cccccc"),
                         alpha=0.8)
        
        ax.set_xlabel('NIST Security Level')
        ax.set_ylabel('Mean Time (ms)')
        ax.set_title(f'{algo_type} Operations by NIST Level\n(Aggregated across all algorithms)')
        ax.set_xticks(x)
        ax.set_xticklabels(levels)
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        
        # Use log scale if needed
        all_means = [v["mean"] for v in type_data.values()]
        if all_means and max(all_means) / max(min(all_means), 0.001) > 50:
            ax.set_yscale('log')
            ax.set_ylabel('Mean Time (ms, log scale)')
        
        plt.tight_layout()
        
        pdf_path = output_dir / f"{algo_type.lower()}_nist_level_comparison.pdf"
        png_path = output_dir / f"{algo_type.lower()}_nist_level_comparison.png"
        plt.savefig(pdf_path, format='pdf', dpi=300, bbox_inches='tight')
        plt.savefig(png_path, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"[PLOT] Saved {pdf_path.name}")


def plot_family_comparison(stats_data: List[Dict], output_dir: Path):
    """Generate bar chart comparing algorithm families."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    # Aggregate by family and operation
    family_stats = {}
    for row in stats_data:
        family = row.get("family", "Unknown")
        op = row.get("operation", "Unknown")
        
        try:
            mean_ms = float(row.get("mean_ms", 0))
        except (ValueError, TypeError):
            continue
        
        key = (family, op)
        if key not in family_stats:
            family_stats[key] = []
        family_stats[key].append(mean_ms)
    
    # Average across same family+operation
    averaged = {k: np.mean(v) for k, v in family_stats.items()}
    
    # Get unique families and operations
    families = sorted(set(k[0] for k in averaged.keys()))
    operations = sorted(set(k[1] for k in averaged.keys()))
    
    # Filter to common operations
    common_ops = [op for op in ["keygen", "encapsulate", "decapsulate", "sign", "verify"]
                  if any((f, op) in averaged for f in families)]
    
    if not common_ops or not families:
        return
    
    fig, ax = plt.subplots(figsize=(14, 7))
    
    x = np.arange(len(families))
    width = 0.15
    
    for i, op in enumerate(common_ops):
        means = [averaged.get((f, op), 0) for f in families]
        offset = (i - len(common_ops)/2 + 0.5) * width
        bars = ax.bar(x + offset, means, width,
                     label=op.capitalize(),
                     color=OPERATION_COLORS.get(op, "#cccccc"),
                     alpha=0.8)
    
    ax.set_xlabel('Algorithm Family')
    ax.set_ylabel('Mean Time (ms)')
    ax.set_title('Operation Timing by Algorithm Family\n(n=200 iterations)')
    ax.set_xticks(x)
    ax.set_xticklabels(families, rotation=30, ha='right')
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3, axis='y')
    
    all_means = list(averaged.values())
    if all_means and max(all_means) / max(min(all_means), 0.001) > 100:
        ax.set_yscale('log')
        ax.set_ylabel('Mean Time (ms, log scale)')
    
    plt.tight_layout()
    
    pdf_path = output_dir / "family_comparison.pdf"
    png_path = output_dir / "family_comparison.png"
    plt.savefig(pdf_path, format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(png_path, format='png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Saved {pdf_path.name}")


def plot_aead_comparison(stats_data: List[Dict], output_dir: Path):
    """Generate AEAD comparison plots."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    # Group by algorithm, operation, payload_size
    aead_data = {}
    for row in stats_data:
        algo = row.get("algorithm", "Unknown")
        op = row.get("operation", "Unknown")
        payload = row.get("payload_size", "Unknown")
        
        try:
            mean_ms = float(row.get("mean_ms", 0))
            payload_int = int(payload) if payload and payload != "Unknown" else 0
        except (ValueError, TypeError):
            continue
        
        key = (algo, op, payload_int)
        aead_data[key] = mean_ms
    
    if not aead_data:
        return
    
    # Get unique algorithms and payload sizes
    algos = sorted(set(k[0] for k in aead_data.keys()))
    payloads = sorted(set(k[2] for k in aead_data.keys()))
    
    for op in ["encrypt", "decrypt"]:
        fig, ax = plt.subplots(figsize=(10, 6))
        
        x = np.arange(len(payloads))
        width = 0.25
        
        for i, algo in enumerate(algos):
            means = [aead_data.get((algo, op, p), 0) for p in payloads]
            offset = (i - len(algos)/2 + 0.5) * width
            bars = ax.bar(x + offset, means, width,
                         label=algo,
                         color=FAMILY_COLORS.get(algo.split('-')[0], "#cccccc"),
                         alpha=0.8)
        
        ax.set_xlabel('Payload Size (bytes)')
        ax.set_ylabel('Mean Time (ms)')
        ax.set_title(f'AEAD {op.capitalize()} Performance by Payload Size\n(n=200 iterations)')
        ax.set_xticks(x)
        ax.set_xticklabels([str(p) for p in payloads])
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        
        plt.tight_layout()
        
        pdf_path = output_dir / f"aead_{op}_comparison.pdf"
        png_path = output_dir / f"aead_{op}_comparison.png"
        plt.savefig(pdf_path, format='pdf', dpi=300, bbox_inches='tight')
        plt.savefig(png_path, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"[PLOT] Saved {pdf_path.name}")


def plot_suite_handshake(stats_data: List[Dict], output_dir: Path):
    """Generate full handshake timing comparison."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    # Extract suite data
    suites = []
    for row in stats_data:
        suite = row.get("suite", "Unknown")
        try:
            median_ms = float(row.get("suite_median_ms", 0))
        except (ValueError, TypeError):
            continue
        suites.append((suite, median_ms))
    
    if not suites:
        return
    
    # Sort by time
    suites.sort(key=lambda x: x[1])
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    y = np.arange(len(suites))
    times = [s[1] for s in suites]
    labels = [s[0].replace("cs-", "").replace("-full_handshake", "") for s in suites]
    
    # Color by NIST level (derived from KEM in suite name)
    colors = []
    for suite, _ in suites:
        if "348864" in suite:
            colors.append(NIST_LEVEL_COLORS["L1"])
        elif "460896" in suite:
            colors.append(NIST_LEVEL_COLORS["L3"])
        elif "8192128" in suite:
            colors.append(NIST_LEVEL_COLORS["L5"])
        else:
            colors.append("#cccccc")
    
    bars = ax.barh(y, times, color=colors, alpha=0.8)
    
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_xlabel('Median Handshake Time (ms)')
    ax.set_title('Full Handshake Timing by Cipher Suite\n(n=200 iterations)')
    ax.grid(True, alpha=0.3, axis='x')
    
    # Add legend for NIST levels
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor=NIST_LEVEL_COLORS["L1"], label='NIST L1'),
        Patch(facecolor=NIST_LEVEL_COLORS["L3"], label='NIST L3'),
        Patch(facecolor=NIST_LEVEL_COLORS["L5"], label='NIST L5'),
    ]
    ax.legend(handles=legend_elements, loc='lower right')
    
    # Use log scale if range is large
    if times and max(times) / max(min(times), 0.001) > 50:
        ax.set_xscale('log')
        ax.set_xlabel('Median Handshake Time (ms, log scale)')
    
    plt.tight_layout()
    
    pdf_path = output_dir / "suite_handshake_comparison.pdf"
    png_path = output_dir / "suite_handshake_comparison.png"
    plt.savefig(pdf_path, format='pdf', dpi=300, bbox_inches='tight')
    plt.savefig(png_path, format='png', dpi=150, bbox_inches='tight')
    plt.close()
    print(f"[PLOT] Saved {pdf_path.name}")


def plot_key_sizes(csv_path: Path, output_dir: Path):
    """Plot key and signature sizes."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    data = load_csv_data(csv_path)
    if not data:
        return
    
    # Extract unique algorithm sizes
    sizes = {}
    for row in data:
        algo = row.get("algorithm", "Unknown")
        if algo in sizes:
            continue
        
        try:
            pk = int(row.get("public_key_bytes", 0) or 0)
            sk = int(row.get("secret_key_bytes", 0) or 0)
            ct = int(row.get("ciphertext_bytes", 0) or 0)
            sig = int(row.get("signature_bytes", 0) or 0)
        except (ValueError, TypeError):
            continue
        
        if pk > 0 or sk > 0 or ct > 0 or sig > 0:
            sizes[algo] = {"pk": pk, "sk": sk, "ct": ct, "sig": sig}
    
    if not sizes:
        return
    
    # Separate KEM and SIG
    kem_sizes = {k: v for k, v in sizes.items() 
                 if any(x in k for x in ["KEM", "McEliece", "HQC"])}
    sig_sizes = {k: v for k, v in sizes.items()
                 if any(x in k for x in ["DSA", "Falcon", "SPHINCS"])}
    
    # Plot KEM sizes
    if kem_sizes:
        fig, ax = plt.subplots(figsize=(12, 6))
        
        algos = sorted(kem_sizes.keys())
        x = np.arange(len(algos))
        width = 0.25
        
        pk_vals = [kem_sizes[a]["pk"] for a in algos]
        sk_vals = [kem_sizes[a]["sk"] for a in algos]
        ct_vals = [kem_sizes[a]["ct"] for a in algos]
        
        ax.bar(x - width, pk_vals, width, label='Public Key', color='#3498db')
        ax.bar(x, sk_vals, width, label='Secret Key', color='#e74c3c')
        ax.bar(x + width, ct_vals, width, label='Ciphertext', color='#2ecc71')
        
        ax.set_xlabel('Algorithm')
        ax.set_ylabel('Size (bytes)')
        ax.set_title('KEM Key and Ciphertext Sizes')
        ax.set_xticks(x)
        ax.set_xticklabels(algos, rotation=45, ha='right', fontsize=9)
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        ax.set_yscale('log')
        ax.set_ylabel('Size (bytes, log scale)')
        
        plt.tight_layout()
        
        pdf_path = output_dir / "kem_sizes.pdf"
        png_path = output_dir / "kem_sizes.png"
        plt.savefig(pdf_path, format='pdf', dpi=300, bbox_inches='tight')
        plt.savefig(png_path, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"[PLOT] Saved {pdf_path.name}")
    
    # Plot SIG sizes
    if sig_sizes:
        fig, ax = plt.subplots(figsize=(12, 6))
        
        algos = sorted(sig_sizes.keys())
        x = np.arange(len(algos))
        width = 0.3
        
        pk_vals = [sig_sizes[a]["pk"] for a in algos]
        sig_vals = [sig_sizes[a]["sig"] for a in algos]
        
        ax.bar(x - width/2, pk_vals, width, label='Public Key', color='#3498db')
        ax.bar(x + width/2, sig_vals, width, label='Signature', color='#9b59b6')
        
        ax.set_xlabel('Algorithm')
        ax.set_ylabel('Size (bytes)')
        ax.set_title('Signature Key and Signature Sizes')
        ax.set_xticks(x)
        ax.set_xticklabels(algos, rotation=45, ha='right', fontsize=9)
        ax.legend()
        ax.grid(True, alpha=0.3, axis='y')
        ax.set_yscale('log')
        ax.set_ylabel('Size (bytes, log scale)')
        
        plt.tight_layout()
        
        pdf_path = output_dir / "sig_sizes.pdf"
        png_path = output_dir / "sig_sizes.png"
        plt.savefig(pdf_path, format='pdf', dpi=300, bbox_inches='tight')
        plt.savefig(png_path, format='png', dpi=150, bbox_inches='tight')
        plt.close()
        print(f"[PLOT] Saved {pdf_path.name}")


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="PQC Benchmark Visualization")
    parser.add_argument("--analysis-dir", type=str, default="benchmarks/bench_analysis",
                        help="Path to analysis output directory")
    parser.add_argument("--output-dir", type=str, default="benchmarks/bench_analysis/plots",
                        help="Path to plot output directory")
    args = parser.parse_args()
    
    analysis_dir = Path(args.analysis_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("PQC BENCHMARK VISUALIZATION")
    print("=" * 60)
    
    if not MATPLOTLIB_AVAILABLE:
        print("[ERROR] matplotlib not available. Install with: pip install matplotlib")
        return
    
    csv_dir = analysis_dir / "csv"
    stats_dir = analysis_dir / "stats"
    
    # Load raw data for box plots
    print("\nGenerating KEM box plots...")
    kem_raw = load_raw_timings(csv_dir / "raw_kem.csv")
    if kem_raw:
        plot_kem_boxplots(kem_raw, output_dir)
    
    print("\nGenerating SIG box plots...")
    sig_raw = load_raw_timings(csv_dir / "raw_sig.csv")
    if sig_raw:
        plot_sig_boxplots(sig_raw, output_dir)
    
    # Load stats for comparison plots
    print("\nGenerating NIST level comparison...")
    nist_stats = load_csv_data(stats_dir / "stats_by_nist_level.csv")
    if nist_stats:
        plot_nist_level_comparison(nist_stats, output_dir)
    
    print("\nGenerating family comparison...")
    family_stats = load_csv_data(stats_dir / "stats_by_family.csv")
    if family_stats:
        plot_family_comparison(family_stats, output_dir)
    
    print("\nGenerating AEAD comparison...")
    aead_stats = load_csv_data(stats_dir / "stats_aead_operations.csv")
    if aead_stats:
        plot_aead_comparison(aead_stats, output_dir)
    
    print("\nGenerating suite handshake comparison...")
    suite_stats = load_csv_data(stats_dir / "stats_suite_comparison.csv")
    if suite_stats:
        plot_suite_handshake(suite_stats, output_dir)
    
    print("\nGenerating key size plots...")
    plot_key_sizes(csv_dir / "raw_all.csv", output_dir)
    
    print("\n" + "=" * 60)
    print("VISUALIZATION COMPLETE")
    print("=" * 60)
    print(f"Output directory: {output_dir}")


if __name__ == "__main__":
    main()
