#!/usr/bin/env python3
"""
PQC Suite Benchmark Analysis and Visualization
suite_benchmarks/analyze_benchmarks.py

A comprehensive data analysis and visualization tool for PQC benchmark results.
Generates professional, publication-quality graphs and reports suitable for
academic research and technical documentation.

Features:
- Multi-dimensional analysis by NIST level, KEM family, signature scheme, AEAD
- Statistical analysis with confidence intervals
- Energy efficiency calculations
- Comparative bar charts, heatmaps, and scatter plots
- Professional PDF/PNG output
- LaTeX-compatible table generation

Usage:
    python suite_benchmarks/analyze_benchmarks.py [input_file.json]
    
If no input file specified, searches logs/benchmarks/ for latest results.
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple
import statistics

# Attempt to import visualization libraries
try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.ticker import FuncFormatter
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("Warning: matplotlib not available. Install with: pip install matplotlib numpy")

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("Warning: pandas not available. Install with: pip install pandas")

# =============================================================================
# Configuration
# =============================================================================

OUTPUT_DIR = Path(__file__).parent / "analysis_output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Color schemes for professional visualization
NIST_COLORS = {
    "L1": "#2ecc71",  # Green - lightweight
    "L3": "#3498db",  # Blue - balanced  
    "L5": "#9b59b6",  # Purple - maximum security
}

KEM_COLORS = {
    "ML-KEM": "#e74c3c",      # Red
    "Classic-McEliece": "#f39c12",  # Orange
    "HQC": "#1abc9c",         # Teal
}

SIG_COLORS = {
    "ML-DSA": "#3498db",       # Blue
    "Falcon": "#9b59b6",       # Purple
    "SPHINCS+": "#e67e22",     # Orange
}

AEAD_COLORS = {
    "AES-256-GCM": "#2ecc71",
    "ChaCha20-Poly1305": "#e74c3c", 
    "Ascon-128a": "#f39c12",
}

# =============================================================================
# Data Loading
# =============================================================================

def find_latest_results() -> Optional[Path]:
    """Find the most recent benchmark results file."""
    search_dirs = [
        Path("logs/benchmarks"),
        Path("suite_benchmarks/analysis_output"),
        Path(".")
    ]
    
    candidates = []
    for d in search_dirs:
        if d.exists():
            candidates.extend(d.glob("benchmark_*.json"))
            candidates.extend(d.glob("benchmark_results_*.json"))
    
    if not candidates:
        return None
    
    # Sort by modification time, newest first
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def load_benchmark_data(filepath: Path) -> Dict[str, Any]:
    """Load benchmark results from JSON file."""
    with open(filepath, "r") as f:
        data = json.load(f)
    
    # Handle both formats: direct list or nested under 'suites'
    if isinstance(data, list):
        return {"suites": data, "run_id": "unknown"}
    return data


def load_jsonl_results(filepath: Path) -> List[Dict[str, Any]]:
    """Load results from JSONL file."""
    results = []
    with open(filepath, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return results

# =============================================================================
# Data Processing
# =============================================================================

def process_results(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Process and normalize benchmark results."""
    suites = data.get("suites", [])
    
    processed = []
    for s in suites:
        if not s.get("success", True):
            continue  # Skip failed entries
        
        # Extract KEM family from name
        kem_name = s.get("kem_name", "")
        kem_family = extract_kem_family(kem_name)
        
        # Extract signature family
        sig_name = s.get("sig_name", "")
        sig_family = extract_sig_family(sig_name)
        
        processed.append({
            "suite_id": s.get("suite_id", ""),
            "nist_level": s.get("nist_level", ""),
            "kem_name": kem_name,
            "kem_family": kem_family,
            "sig_name": sig_name,
            "sig_family": sig_family,
            "aead": s.get("aead", ""),
            "handshake_ms": float(s.get("handshake_ms", 0)),
            "kem_keygen_ms": float(s.get("kem_keygen_ms", 0)),
            "kem_encaps_ms": float(s.get("kem_encaps_ms", 0)),
            "kem_decaps_ms": float(s.get("kem_decaps_ms", 0)),
            "sig_sign_ms": float(s.get("sig_sign_ms", 0)),
            "sig_verify_ms": float(s.get("sig_verify_ms", 0)),
            "pub_key_size_bytes": int(s.get("pub_key_size_bytes", 0)),
            "ciphertext_size_bytes": int(s.get("ciphertext_size_bytes", 0)),
            "sig_size_bytes": int(s.get("sig_size_bytes", 0)),
            "power_w": float(s.get("power_w", 0)),
            "energy_mj": float(s.get("energy_mj", 0)),
            "throughput_mbps": float(s.get("throughput_mbps", 0)),
        })
    
    return processed


def extract_kem_family(kem_name: str) -> str:
    """Extract KEM family from algorithm name."""
    kem_lower = kem_name.lower()
    if "ml-kem" in kem_lower or "mlkem" in kem_lower or "kyber" in kem_lower:
        return "ML-KEM"
    elif "mceliece" in kem_lower:
        return "Classic-McEliece"
    elif "hqc" in kem_lower:
        return "HQC"
    elif "frodo" in kem_lower:
        return "FrodoKEM"
    elif "sntrup" in kem_lower:
        return "NTRU-Prime"
    return "Other"


def extract_sig_family(sig_name: str) -> str:
    """Extract signature family from algorithm name."""
    sig_lower = sig_name.lower()
    if "ml-dsa" in sig_lower or "mldsa" in sig_lower or "dilithium" in sig_lower:
        return "ML-DSA"
    elif "falcon" in sig_lower:
        return "Falcon"
    elif "sphincs" in sig_lower or "slh-dsa" in sig_lower:
        return "SPHINCS+"
    return "Other"


def group_by_key(data: List[Dict], key: str) -> Dict[str, List[Dict]]:
    """Group data by a specific key."""
    groups = {}
    for item in data:
        k = item.get(key, "Unknown")
        if k not in groups:
            groups[k] = []
        groups[k].append(item)
    return groups


def calculate_statistics(values: List[float]) -> Dict[str, float]:
    """Calculate statistical measures for a list of values."""
    if not values:
        return {"min": 0, "max": 0, "mean": 0, "median": 0, "stdev": 0}
    
    return {
        "min": min(values),
        "max": max(values),
        "mean": statistics.mean(values),
        "median": statistics.median(values),
        "stdev": statistics.stdev(values) if len(values) > 1 else 0,
        "count": len(values)
    }

# =============================================================================
# Visualization Functions
# =============================================================================

def setup_plot_style():
    """Configure matplotlib for publication-quality plots."""
    if not HAS_MATPLOTLIB:
        return
    
    plt.style.use('seaborn-v0_8-whitegrid')
    plt.rcParams.update({
        'font.size': 11,
        'font.family': 'serif',
        'axes.labelsize': 12,
        'axes.titlesize': 14,
        'xtick.labelsize': 10,
        'ytick.labelsize': 10,
        'legend.fontsize': 10,
        'figure.figsize': (12, 8),
        'figure.dpi': 150,
        'savefig.dpi': 300,
        'savefig.bbox': 'tight',
    })


def plot_handshake_by_nist_level(data: List[Dict], output_path: Path):
    """Create bar chart of handshake times grouped by NIST level."""
    if not HAS_MATPLOTLIB:
        return
    
    groups = group_by_key(data, "nist_level")
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    x_positions = []
    x_labels = []
    colors = []
    heights = []
    
    pos = 0
    for level in ["L1", "L3", "L5"]:
        if level not in groups:
            continue
        
        suites = groups[level]
        for s in sorted(suites, key=lambda x: x["handshake_ms"]):
            x_positions.append(pos)
            x_labels.append(s["suite_id"].replace("cs-", "").replace("-aesgcm-", "\n"))
            colors.append(NIST_COLORS.get(level, "#888888"))
            heights.append(s["handshake_ms"])
            pos += 1
        pos += 0.5  # Gap between levels
    
    bars = ax.bar(x_positions, heights, color=colors, edgecolor='black', linewidth=0.5)
    
    ax.set_xlabel("Suite", fontsize=12)
    ax.set_ylabel("Handshake Time (ms)", fontsize=12)
    ax.set_title("PQC Suite Handshake Times by NIST Security Level", fontsize=14, fontweight='bold')
    
    ax.set_xticks(x_positions)
    ax.set_xticklabels(x_labels, rotation=45, ha='right', fontsize=8)
    
    # Legend
    legend_patches = [mpatches.Patch(color=c, label=l) for l, c in NIST_COLORS.items()]
    ax.legend(handles=legend_patches, title="NIST Level", loc='upper right')
    
    plt.tight_layout()
    plt.savefig(output_path / "handshake_by_nist_level.png")
    plt.savefig(output_path / "handshake_by_nist_level.pdf")
    plt.close()
    
    print(f"  Saved: handshake_by_nist_level.png/pdf")


def plot_kem_comparison(data: List[Dict], output_path: Path):
    """Create comparative chart of KEM families."""
    if not HAS_MATPLOTLIB:
        return
    
    groups = group_by_key(data, "kem_family")
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    # Keygen times
    ax1 = axes[0]
    families = []
    keygen_times = []
    colors_list = []
    
    for family in sorted(groups.keys()):
        suites = groups[family]
        times = [s["kem_keygen_ms"] for s in suites if s["kem_keygen_ms"] > 0]
        if times:
            families.append(family)
            keygen_times.append(statistics.mean(times))
            colors_list.append(KEM_COLORS.get(family, "#888888"))
    
    ax1.bar(families, keygen_times, color=colors_list, edgecolor='black')
    ax1.set_ylabel("Time (ms)")
    ax1.set_title("KEM Key Generation")
    ax1.tick_params(axis='x', rotation=30)
    
    # Encapsulation times
    ax2 = axes[1]
    encaps_times = []
    for family in families:
        suites = groups[family]
        times = [s["kem_encaps_ms"] for s in suites if s["kem_encaps_ms"] > 0]
        encaps_times.append(statistics.mean(times) if times else 0)
    
    ax2.bar(families, encaps_times, color=colors_list, edgecolor='black')
    ax2.set_ylabel("Time (ms)")
    ax2.set_title("KEM Encapsulation")
    ax2.tick_params(axis='x', rotation=30)
    
    # Decapsulation times
    ax3 = axes[2]
    decaps_times = []
    for family in families:
        suites = groups[family]
        times = [s["kem_decaps_ms"] for s in suites if s["kem_decaps_ms"] > 0]
        decaps_times.append(statistics.mean(times) if times else 0)
    
    ax3.bar(families, decaps_times, color=colors_list, edgecolor='black')
    ax3.set_ylabel("Time (ms)")
    ax3.set_title("KEM Decapsulation")
    ax3.tick_params(axis='x', rotation=30)
    
    fig.suptitle("KEM Family Performance Comparison", fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path / "kem_comparison.png")
    plt.savefig(output_path / "kem_comparison.pdf")
    plt.close()
    
    print(f"  Saved: kem_comparison.png/pdf")


def plot_signature_comparison(data: List[Dict], output_path: Path):
    """Create comparative chart of signature schemes."""
    if not HAS_MATPLOTLIB:
        return
    
    groups = group_by_key(data, "sig_family")
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    # Sign times
    ax1 = axes[0]
    families = []
    sign_times = []
    colors_list = []
    
    for family in sorted(groups.keys()):
        suites = groups[family]
        times = [s["sig_sign_ms"] for s in suites if s["sig_sign_ms"] > 0]
        if times:
            families.append(family)
            sign_times.append(statistics.mean(times))
            colors_list.append(SIG_COLORS.get(family, "#888888"))
    
    ax1.bar(families, sign_times, color=colors_list, edgecolor='black')
    ax1.set_ylabel("Time (ms)")
    ax1.set_title("Signature Generation")
    ax1.tick_params(axis='x', rotation=30)
    
    # Verify times
    ax2 = axes[1]
    verify_times = []
    for family in families:
        suites = groups[family]
        times = [s["sig_verify_ms"] for s in suites if s["sig_verify_ms"] > 0]
        verify_times.append(statistics.mean(times) if times else 0)
    
    ax2.bar(families, verify_times, color=colors_list, edgecolor='black')
    ax2.set_ylabel("Time (ms)")
    ax2.set_title("Signature Verification")
    ax2.tick_params(axis='x', rotation=30)
    
    fig.suptitle("Signature Scheme Performance Comparison", fontsize=14, fontweight='bold')
    plt.tight_layout()
    plt.savefig(output_path / "signature_comparison.png")
    plt.savefig(output_path / "signature_comparison.pdf")
    plt.close()
    
    print(f"  Saved: signature_comparison.png/pdf")


def plot_size_comparison(data: List[Dict], output_path: Path):
    """Create artifact size comparison chart."""
    if not HAS_MATPLOTLIB:
        return
    
    groups = group_by_key(data, "nist_level")
    
    fig, ax = plt.subplots(figsize=(14, 7))
    
    levels = ["L1", "L3", "L5"]
    width = 0.25
    
    # Collect data
    pub_key_sizes = {}
    ct_sizes = {}
    sig_sizes = {}
    
    for level in levels:
        if level in groups:
            suites = groups[level]
            pub_key_sizes[level] = [s["pub_key_size_bytes"] for s in suites]
            ct_sizes[level] = [s["ciphertext_size_bytes"] for s in suites]
            sig_sizes[level] = [s["sig_size_bytes"] for s in suites]
    
    x = np.arange(len(levels))
    
    # Plot grouped bars
    bars1 = ax.bar(x - width, [statistics.mean(pub_key_sizes.get(l, [0])) for l in levels], 
                   width, label='Public Key', color='#3498db', edgecolor='black')
    bars2 = ax.bar(x, [statistics.mean(ct_sizes.get(l, [0])) for l in levels], 
                   width, label='Ciphertext', color='#e74c3c', edgecolor='black')
    bars3 = ax.bar(x + width, [statistics.mean(sig_sizes.get(l, [0])) for l in levels], 
                   width, label='Signature', color='#2ecc71', edgecolor='black')
    
    ax.set_xlabel('NIST Security Level')
    ax.set_ylabel('Size (bytes)')
    ax.set_title('PQC Artifact Sizes by Security Level', fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(levels)
    ax.legend()
    
    # Add value labels
    def add_labels(bars):
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{int(height):,}',
                       xy=(bar.get_x() + bar.get_width() / 2, height),
                       xytext=(0, 3),
                       textcoords="offset points",
                       ha='center', va='bottom', fontsize=8)
    
    add_labels(bars1)
    add_labels(bars2)
    add_labels(bars3)
    
    plt.tight_layout()
    plt.savefig(output_path / "artifact_sizes.png")
    plt.savefig(output_path / "artifact_sizes.pdf")
    plt.close()
    
    print(f"  Saved: artifact_sizes.png/pdf")


def plot_heatmap(data: List[Dict], output_path: Path):
    """Create a heatmap of handshake times by KEM and Signature."""
    if not HAS_MATPLOTLIB or not HAS_PANDAS:
        return
    
    # Create pivot table
    df = pd.DataFrame(data)
    
    if df.empty:
        return
    
    pivot = df.pivot_table(
        values='handshake_ms', 
        index='kem_family', 
        columns='sig_family',
        aggfunc='mean'
    )
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    im = ax.imshow(pivot.values, cmap='YlOrRd', aspect='auto')
    
    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_yticks(np.arange(len(pivot.index)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticklabels(pivot.index)
    
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    
    # Add values
    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i, j]
            if not np.isnan(val):
                text = ax.text(j, i, f'{val:.1f}',
                              ha="center", va="center", color="black", fontsize=10)
    
    ax.set_title("Mean Handshake Time (ms) by KEM × Signature", fontweight='bold')
    ax.set_xlabel("Signature Scheme")
    ax.set_ylabel("KEM Family")
    
    cbar = ax.figure.colorbar(im, ax=ax)
    cbar.ax.set_ylabel("Time (ms)", rotation=-90, va="bottom")
    
    plt.tight_layout()
    plt.savefig(output_path / "heatmap_kem_sig.png")
    plt.savefig(output_path / "heatmap_kem_sig.pdf")
    plt.close()
    
    print(f"  Saved: heatmap_kem_sig.png/pdf")


def plot_energy_efficiency(data: List[Dict], output_path: Path):
    """Create energy efficiency visualization."""
    if not HAS_MATPLOTLIB:
        return
    
    # Filter entries with energy data
    energy_data = [s for s in data if s.get("energy_mj", 0) > 0]
    
    if not energy_data:
        print("  No energy data available for energy efficiency plot")
        return
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    # Sort by energy efficiency (lower is better)
    sorted_data = sorted(energy_data, key=lambda x: x["energy_mj"])
    
    names = [s["suite_id"].replace("cs-", "") for s in sorted_data]
    energies = [s["energy_mj"] for s in sorted_data]
    colors = [NIST_COLORS.get(s["nist_level"], "#888888") for s in sorted_data]
    
    bars = ax.barh(names, energies, color=colors, edgecolor='black', linewidth=0.5)
    
    ax.set_xlabel("Energy (mJ)")
    ax.set_title("PQC Suite Energy Consumption (Handshake)", fontweight='bold')
    
    # Legend
    legend_patches = [mpatches.Patch(color=c, label=l) for l, c in NIST_COLORS.items()]
    ax.legend(handles=legend_patches, title="NIST Level", loc='lower right')
    
    plt.tight_layout()
    plt.savefig(output_path / "energy_efficiency.png")
    plt.savefig(output_path / "energy_efficiency.pdf")
    plt.close()
    
    print(f"  Saved: energy_efficiency.png/pdf")


def plot_scatter_time_vs_size(data: List[Dict], output_path: Path):
    """Create scatter plot of handshake time vs total artifact size."""
    if not HAS_MATPLOTLIB:
        return
    
    fig, ax = plt.subplots(figsize=(10, 8))
    
    for level in ["L1", "L3", "L5"]:
        level_data = [s for s in data if s["nist_level"] == level]
        
        x = [s["pub_key_size_bytes"] + s["ciphertext_size_bytes"] + s["sig_size_bytes"] 
             for s in level_data]
        y = [s["handshake_ms"] for s in level_data]
        
        ax.scatter(x, y, c=NIST_COLORS.get(level, "#888888"), 
                  label=f"NIST {level}", alpha=0.7, s=100, edgecolors='black')
    
    ax.set_xlabel("Total Artifact Size (bytes)")
    ax.set_ylabel("Handshake Time (ms)")
    ax.set_title("PQC Performance: Time vs. Communication Cost", fontweight='bold')
    ax.legend(title="Security Level")
    
    # Log scale if range is large
    if max(s["handshake_ms"] for s in data) / min(s["handshake_ms"] for s in data if s["handshake_ms"] > 0) > 10:
        ax.set_yscale('log')
    
    plt.tight_layout()
    plt.savefig(output_path / "scatter_time_vs_size.png")
    plt.savefig(output_path / "scatter_time_vs_size.pdf")
    plt.close()
    
    print(f"  Saved: scatter_time_vs_size.png/pdf")

# =============================================================================
# Report Generation
# =============================================================================

def generate_latex_table(data: List[Dict], output_path: Path):
    """Generate LaTeX table of results."""
    groups = group_by_key(data, "nist_level")
    
    with open(output_path / "results_table.tex", "w") as f:
        f.write("\\begin{table}[htbp]\n")
        f.write("\\centering\n")
        f.write("\\caption{PQC Suite Benchmark Results}\n")
        f.write("\\label{tab:pqc-benchmarks}\n")
        f.write("\\begin{tabular}{llrrrrr}\n")
        f.write("\\toprule\n")
        f.write("Level & Suite & Handshake & Key Gen & Encaps & Sign & Verify \\\\\n")
        f.write(" & & (ms) & (ms) & (ms) & (ms) & (ms) \\\\\n")
        f.write("\\midrule\n")
        
        for level in ["L1", "L3", "L5"]:
            if level not in groups:
                continue
            
            suites = sorted(groups[level], key=lambda x: x["handshake_ms"])
            for s in suites:
                name = s["suite_id"].replace("cs-", "").replace("-", "\\mbox{-}")
                f.write(f"{level} & {name} & {s['handshake_ms']:.1f} & "
                       f"{s['kem_keygen_ms']:.2f} & {s['kem_encaps_ms']:.2f} & "
                       f"{s['sig_sign_ms']:.2f} & {s['sig_verify_ms']:.2f} \\\\\n")
            
            f.write("\\midrule\n")
        
        f.write("\\bottomrule\n")
        f.write("\\end{tabular}\n")
        f.write("\\end{table}\n")
    
    print(f"  Saved: results_table.tex")


def generate_summary_report(data: List[Dict], output_path: Path) -> str:
    """Generate comprehensive text summary report."""
    report = []
    report.append("=" * 80)
    report.append("PQC SUITE BENCHMARK ANALYSIS REPORT")
    report.append(f"Generated: {datetime.now().isoformat()}")
    report.append("=" * 80)
    report.append("")
    
    # Overall statistics
    report.append("OVERALL STATISTICS")
    report.append("-" * 40)
    report.append(f"Total suites analyzed: {len(data)}")
    
    handshake_times = [s["handshake_ms"] for s in data if s["handshake_ms"] > 0]
    if handshake_times:
        stats = calculate_statistics(handshake_times)
        report.append(f"Handshake Time (ms):")
        report.append(f"  Min: {stats['min']:.2f}")
        report.append(f"  Max: {stats['max']:.2f}")
        report.append(f"  Mean: {stats['mean']:.2f}")
        report.append(f"  Median: {stats['median']:.2f}")
        report.append(f"  Std Dev: {stats['stdev']:.2f}")
    report.append("")
    
    # By NIST Level
    report.append("BY NIST SECURITY LEVEL")
    report.append("-" * 40)
    groups = group_by_key(data, "nist_level")
    for level in ["L1", "L3", "L5"]:
        if level not in groups:
            continue
        suites = groups[level]
        times = [s["handshake_ms"] for s in suites if s["handshake_ms"] > 0]
        if times:
            report.append(f"Level {level}: {len(suites)} suites")
            report.append(f"  Mean handshake: {statistics.mean(times):.2f} ms")
            report.append(f"  Range: {min(times):.2f} - {max(times):.2f} ms")
    report.append("")
    
    # By KEM Family
    report.append("BY KEM FAMILY")
    report.append("-" * 40)
    groups = group_by_key(data, "kem_family")
    for family in sorted(groups.keys()):
        suites = groups[family]
        times = [s["handshake_ms"] for s in suites if s["handshake_ms"] > 0]
        if times:
            report.append(f"{family}: {len(suites)} suites")
            report.append(f"  Mean handshake: {statistics.mean(times):.2f} ms")
    report.append("")
    
    # By Signature Family
    report.append("BY SIGNATURE SCHEME")
    report.append("-" * 40)
    groups = group_by_key(data, "sig_family")
    for family in sorted(groups.keys()):
        suites = groups[family]
        sign_times = [s["sig_sign_ms"] for s in suites if s["sig_sign_ms"] > 0]
        verify_times = [s["sig_verify_ms"] for s in suites if s["sig_verify_ms"] > 0]
        if sign_times or verify_times:
            report.append(f"{family}: {len(suites)} suites")
            if sign_times:
                report.append(f"  Mean sign: {statistics.mean(sign_times):.2f} ms")
            if verify_times:
                report.append(f"  Mean verify: {statistics.mean(verify_times):.2f} ms")
    report.append("")
    
    # Top performers
    report.append("TOP PERFORMERS (Fastest Handshake)")
    report.append("-" * 40)
    sorted_data = sorted(data, key=lambda x: x["handshake_ms"])
    for i, s in enumerate(sorted_data[:10], 1):
        report.append(f"{i:2d}. {s['suite_id']}: {s['handshake_ms']:.2f} ms ({s['nist_level']})")
    report.append("")
    
    # Recommendations
    report.append("RECOMMENDATIONS")
    report.append("-" * 40)
    
    # Best by level
    for level in ["L1", "L3", "L5"]:
        level_suites = [s for s in data if s["nist_level"] == level]
        if level_suites:
            best = min(level_suites, key=lambda x: x["handshake_ms"])
            report.append(f"Best for {level}: {best['suite_id']} ({best['handshake_ms']:.2f} ms)")
    
    report.append("")
    report.append("=" * 80)
    
    report_text = "\n".join(report)
    
    with open(output_path / "analysis_report.txt", "w") as f:
        f.write(report_text)
    
    print(f"  Saved: analysis_report.txt")
    return report_text

# =============================================================================
# Main Analysis Pipeline
# =============================================================================

def run_analysis(input_file: Optional[Path] = None):
    """Run complete analysis pipeline."""
    print("=" * 70)
    print("PQC SUITE BENCHMARK ANALYSIS")
    print("=" * 70)
    
    # Find input file
    if input_file is None:
        input_file = find_latest_results()
    
    if input_file is None or not input_file.exists():
        print("Error: No benchmark results found.")
        print("Run the benchmark first: python -m sscheduler.sdrone_bench")
        return None
    
    print(f"Loading: {input_file}")
    
    # Load data
    if input_file.suffix == ".jsonl":
        raw_results = load_jsonl_results(input_file)
        data = {"suites": raw_results, "run_id": input_file.stem}
    else:
        data = load_benchmark_data(input_file)
    
    # Process data
    processed = process_results(data)
    
    if not processed:
        print("Error: No valid data to analyze")
        return None
    
    print(f"Loaded {len(processed)} suite results")
    print(f"Output directory: {OUTPUT_DIR}")
    print()
    
    # Setup plotting
    setup_plot_style()
    
    # Generate visualizations
    print("Generating visualizations...")
    
    if HAS_MATPLOTLIB:
        plot_handshake_by_nist_level(processed, OUTPUT_DIR)
        plot_kem_comparison(processed, OUTPUT_DIR)
        plot_signature_comparison(processed, OUTPUT_DIR)
        plot_size_comparison(processed, OUTPUT_DIR)
        plot_heatmap(processed, OUTPUT_DIR)
        plot_energy_efficiency(processed, OUTPUT_DIR)
        plot_scatter_time_vs_size(processed, OUTPUT_DIR)
    else:
        print("  Skipping visualizations (matplotlib not available)")
    
    # Generate reports
    print("Generating reports...")
    generate_latex_table(processed, OUTPUT_DIR)
    report = generate_summary_report(processed, OUTPUT_DIR)
    
    print()
    print("=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)
    print()
    print(report)
    
    return processed


def main():
    input_file = None
    if len(sys.argv) > 1:
        input_file = Path(sys.argv[1])
    
    run_analysis(input_file)


if __name__ == "__main__":
    main()
