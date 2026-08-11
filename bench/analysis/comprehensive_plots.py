#!/usr/bin/env python3
"""
Comprehensive PQC Benchmark Visualization Suite
================================================

Generates all possible visualizations for benchmark analysis:
- Spider/Radar charts for multi-metric comparison
- NIST level stratified comparisons
- Individual parameter analysis
- Anomaly detection plots
- Cross-algorithm comparisons
- Size vs timing trade-off analysis

All values derived from bench_results/raw/*.json
IEEE compliant labeling and formatting
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
import numpy as np

# Matplotlib setup for publication quality
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import matplotlib.gridspec as gridspec
from math import pi

# Output directory
OUTPUT_DIR = Path("bench_analysis/plots_comprehensive")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# IEEE-style plot settings
plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 10,
    'axes.labelsize': 11,
    'axes.titlesize': 12,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 9,
    'figure.titlesize': 14,
    'axes.grid': True,
    'grid.alpha': 0.3,
    'axes.axisbelow': True,
})

# Color schemes
NIST_COLORS = {
    'L1': '#2ecc71',  # Green
    'L3': '#f39c12',  # Orange  
    'L5': '#e74c3c',  # Red
}

FAMILY_COLORS = {
    'ML-KEM': '#3498db',
    'Classic-McEliece': '#9b59b6',
    'HQC': '#1abc9c',
    'ML-DSA': '#e74c3c',
    'Falcon': '#f39c12',
    'SPHINCS+': '#34495e',
}

# Algorithm metadata
KEM_ALGORITHMS = {
    'ML-KEM-512': {'family': 'ML-KEM', 'nist': 'L1'},
    'ML-KEM-768': {'family': 'ML-KEM', 'nist': 'L3'},
    'ML-KEM-1024': {'family': 'ML-KEM', 'nist': 'L5'},
    'Classic-McEliece-348864': {'family': 'Classic-McEliece', 'nist': 'L1'},
    'Classic-McEliece-460896': {'family': 'Classic-McEliece', 'nist': 'L3'},
    'Classic-McEliece-8192128': {'family': 'Classic-McEliece', 'nist': 'L5'},
    'HQC-128': {'family': 'HQC', 'nist': 'L1'},
    'HQC-192': {'family': 'HQC', 'nist': 'L3'},
    'HQC-256': {'family': 'HQC', 'nist': 'L5'},
}

SIG_ALGORITHMS = {
    'ML-DSA-44': {'family': 'ML-DSA', 'nist': 'L1'},
    'ML-DSA-65': {'family': 'ML-DSA', 'nist': 'L3'},
    'ML-DSA-87': {'family': 'ML-DSA', 'nist': 'L5'},
    'Falcon-512': {'family': 'Falcon', 'nist': 'L1'},
    'Falcon-1024': {'family': 'Falcon', 'nist': 'L5'},
    'SPHINCS+-SHA2-128s-simple': {'family': 'SPHINCS+', 'nist': 'L1'},
    'SPHINCS+-SHA2-192s-simple': {'family': 'SPHINCS+', 'nist': 'L3'},
    'SPHINCS+-SHA2-256s-simple': {'family': 'SPHINCS+', 'nist': 'L5'},
}


@dataclass
class AlgorithmMetrics:
    """Container for all metrics of an algorithm"""
    name: str
    family: str
    nist_level: str
    # Timing metrics (ms)
    keygen_mean: float = 0
    keygen_median: float = 0
    keygen_std: float = 0
    keygen_min: float = 0
    keygen_max: float = 0
    keygen_p95: float = 0
    op1_mean: float = 0  # encapsulate/sign
    op1_median: float = 0
    op1_std: float = 0
    op1_min: float = 0
    op1_max: float = 0
    op1_p95: float = 0
    op2_mean: float = 0  # decapsulate/verify
    op2_median: float = 0
    op2_std: float = 0
    op2_min: float = 0
    op2_max: float = 0
    op2_p95: float = 0
    # Size metrics (bytes)
    public_key_size: int = 0
    secret_key_size: int = 0
    output_size: int = 0  # ciphertext/signature


def load_benchmark_data(bench_dir: Path) -> Tuple[Dict[str, AlgorithmMetrics], Dict[str, AlgorithmMetrics]]:
    """Load all benchmark data from JSON files"""
    kem_metrics = {}
    sig_metrics = {}
    
    raw_dir = bench_dir / "raw"
    
    # Load KEM data
    kem_dir = raw_dir / "kem"
    if kem_dir.exists():
        for alg_name, meta in KEM_ALGORITHMS.items():
            metrics = AlgorithmMetrics(
                name=alg_name,
                family=meta['family'],
                nist_level=meta['nist']
            )
            
            # Convert algorithm name to filename format
            file_prefix = alg_name.replace('-', '_')
            
            for op, attr_prefix in [('keygen', 'keygen'), ('encapsulate', 'op1'), ('decapsulate', 'op2')]:
                filepath = kem_dir / f"{file_prefix}_{op}.json"
                if filepath.exists():
                    with open(filepath) as f:
                        data = json.load(f)
                    
                    timings = np.array(data.get('perf_time_ns', [])) / 1e6  # Convert to ms
                    if len(timings) > 0:
                        setattr(metrics, f'{attr_prefix}_mean', np.mean(timings))
                        setattr(metrics, f'{attr_prefix}_median', np.median(timings))
                        setattr(metrics, f'{attr_prefix}_std', np.std(timings))
                        setattr(metrics, f'{attr_prefix}_min', np.min(timings))
                        setattr(metrics, f'{attr_prefix}_max', np.max(timings))
                        setattr(metrics, f'{attr_prefix}_p95', np.percentile(timings, 95))
                    
                    # Get size metrics from any operation file
                    if op == 'keygen':
                        metrics.public_key_size = data.get('public_key_bytes', 0)
                        metrics.secret_key_size = data.get('secret_key_bytes', 0)
                    elif op == 'encapsulate':
                        metrics.output_size = data.get('ciphertext_bytes', 0)
            
            kem_metrics[alg_name] = metrics
    
    # Load Signature data
    sig_dir = raw_dir / "sig"
    if sig_dir.exists():
        for alg_name, meta in SIG_ALGORITHMS.items():
            metrics = AlgorithmMetrics(
                name=alg_name,
                family=meta['family'],
                nist_level=meta['nist']
            )
            
            file_prefix = alg_name.replace('-', '_').replace('+', '+')
            
            for op, attr_prefix in [('keygen', 'keygen'), ('sign', 'op1'), ('verify', 'op2')]:
                filepath = sig_dir / f"{file_prefix}_{op}.json"
                if filepath.exists():
                    with open(filepath) as f:
                        data = json.load(f)
                    
                    timings = np.array(data.get('perf_time_ns', [])) / 1e6
                    if len(timings) > 0:
                        setattr(metrics, f'{attr_prefix}_mean', np.mean(timings))
                        setattr(metrics, f'{attr_prefix}_median', np.median(timings))
                        setattr(metrics, f'{attr_prefix}_std', np.std(timings))
                        setattr(metrics, f'{attr_prefix}_min', np.min(timings))
                        setattr(metrics, f'{attr_prefix}_max', np.max(timings))
                        setattr(metrics, f'{attr_prefix}_p95', np.percentile(timings, 95))
                    
                    if op == 'keygen':
                        metrics.public_key_size = data.get('public_key_bytes', 0)
                        metrics.secret_key_size = data.get('secret_key_bytes', 0)
                    elif op == 'sign':
                        metrics.output_size = data.get('signature_bytes', 0)
            
            sig_metrics[alg_name] = metrics
    
    return kem_metrics, sig_metrics


def create_spider_chart(metrics_dict: Dict[str, AlgorithmMetrics], 
                        metric_names: List[str],
                        metric_labels: List[str],
                        title: str,
                        filename: str,
                        alg_type: str = 'KEM',
                        normalize: bool = True,
                        log_scale: bool = False):
    """
    Create a spider/radar chart comparing multiple algorithms across metrics
    
    Args:
        metrics_dict: Dictionary of algorithm metrics
        metric_names: List of attribute names to plot
        metric_labels: Human-readable labels for each metric
        title: Chart title
        filename: Output filename
        alg_type: 'KEM' or 'SIG' for operation labels
        normalize: Whether to normalize values to 0-1 range
        log_scale: Whether to use log scale before normalizing
    """
    n_metrics = len(metric_names)
    angles = [n / float(n_metrics) * 2 * pi for n in range(n_metrics)]
    angles += angles[:1]  # Complete the loop
    
    fig, ax = plt.subplots(figsize=(12, 10), subplot_kw=dict(polar=True))
    
    # Get values for each algorithm
    all_values = {}
    for alg_name, metrics in metrics_dict.items():
        values = []
        for metric in metric_names:
            val = getattr(metrics, metric, 0)
            if val is None or val == 0:
                val = 1e-6  # Small value for missing data
            values.append(val)
        all_values[alg_name] = values
    
    # Normalize if requested
    if normalize:
        # Find min/max for each metric
        for i in range(n_metrics):
            vals = [all_values[alg][i] for alg in all_values]
            if log_scale:
                vals = [np.log10(v + 1e-10) for v in vals]
            min_val, max_val = min(vals), max(vals)
            range_val = max_val - min_val if max_val != min_val else 1
            
            for alg in all_values:
                v = all_values[alg][i]
                if log_scale:
                    v = np.log10(v + 1e-10)
                all_values[alg][i] = (v - min_val) / range_val
    
    # Plot each algorithm
    for alg_name, values in all_values.items():
        values_closed = values + values[:1]
        meta = KEM_ALGORITHMS.get(alg_name) or SIG_ALGORITHMS.get(alg_name)
        color = NIST_COLORS.get(meta['nist'], '#333333')
        
        ax.plot(angles, values_closed, 'o-', linewidth=2, label=alg_name, 
                color=color, alpha=0.7)
        ax.fill(angles, values_closed, alpha=0.1, color=color)
    
    # Set labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(metric_labels, size=9)
    
    ax.set_title(title, size=14, fontweight='bold', y=1.08)
    
    # Legend
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0), fontsize=8)
    
    plt.tight_layout()
    
    for ext in ['pdf', 'png']:
        plt.savefig(OUTPUT_DIR / f"{filename}.{ext}", dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[SPIDER] Saved {filename}")


def create_spider_by_nist_level(metrics_dict: Dict[str, AlgorithmMetrics],
                                 metric_names: List[str],
                                 metric_labels: List[str],
                                 nist_level: str,
                                 title: str,
                                 filename: str,
                                 log_scale: bool = False):
    """Create spider chart for algorithms at a specific NIST level"""
    filtered = {k: v for k, v in metrics_dict.items() if v.nist_level == nist_level}
    if filtered:
        create_spider_chart(filtered, metric_names, metric_labels, 
                           f"{title} (NIST {nist_level})", 
                           f"{filename}_{nist_level.lower()}", 
                           log_scale=log_scale)


def create_metric_comparison_bar(metrics_dict: Dict[str, AlgorithmMetrics],
                                  metric_name: str,
                                  ylabel: str,
                                  title: str,
                                  filename: str,
                                  log_scale: bool = False,
                                  show_std: bool = False,
                                  std_metric: str = None):
    """Create grouped bar chart comparing a single metric across algorithms"""
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # Group by NIST level
    levels = ['L1', 'L3', 'L5']
    level_data = {level: [] for level in levels}
    level_names = {level: [] for level in levels}
    level_stds = {level: [] for level in levels}
    
    for alg_name, metrics in sorted(metrics_dict.items()):
        level = metrics.nist_level
        value = getattr(metrics, metric_name, 0)
        level_data[level].append(value)
        level_names[level].append(alg_name.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', ''))
        if show_std and std_metric:
            level_stds[level].append(getattr(metrics, std_metric, 0))
    
    # Calculate bar positions
    x_pos = 0
    positions = []
    all_names = []
    all_values = []
    all_colors = []
    all_stds = []
    
    for level in levels:
        if level_data[level]:
            for i, (name, val) in enumerate(zip(level_names[level], level_data[level])):
                positions.append(x_pos)
                all_names.append(name)
                all_values.append(val)
                all_colors.append(NIST_COLORS[level])
                if show_std:
                    all_stds.append(level_stds[level][i] if i < len(level_stds[level]) else 0)
                x_pos += 1
            x_pos += 0.5  # Gap between NIST levels
    
    # Plot bars
    if show_std and all_stds:
        bars = ax.bar(positions, all_values, color=all_colors, edgecolor='black', 
                      linewidth=0.5, yerr=all_stds, capsize=3)
    else:
        bars = ax.bar(positions, all_values, color=all_colors, edgecolor='black', linewidth=0.5)
    
    if log_scale:
        ax.set_yscale('log')
    
    ax.set_xticks(positions)
    ax.set_xticklabels(all_names, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight='bold')
    
    # Add NIST level legend
    legend_elements = [Patch(facecolor=NIST_COLORS[l], label=f'NIST {l}') for l in levels]
    ax.legend(handles=legend_elements, loc='upper right')
    
    ax.grid(True, alpha=0.3, axis='y')
    
    plt.tight_layout()
    for ext in ['pdf', 'png']:
        plt.savefig(OUTPUT_DIR / f"{filename}.{ext}", dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[BAR] Saved {filename}")


def create_nist_level_progression(metrics_dict: Dict[str, AlgorithmMetrics],
                                   metric_name: str,
                                   ylabel: str,
                                   title: str,
                                   filename: str):
    """Show how a metric changes across NIST levels for each family"""
    fig, ax = plt.subplots(figsize=(10, 6))
    
    # Group by family
    families = {}
    for alg_name, metrics in metrics_dict.items():
        family = metrics.family
        if family not in families:
            families[family] = {'L1': None, 'L3': None, 'L5': None}
        families[family][metrics.nist_level] = getattr(metrics, metric_name, 0)
    
    x = np.arange(3)  # L1, L3, L5
    width = 0.15
    
    for i, (family, levels) in enumerate(families.items()):
        values = [levels.get('L1', 0) or 0, levels.get('L3', 0) or 0, levels.get('L5', 0) or 0]
        offset = (i - len(families)/2) * width
        bars = ax.bar(x + offset, values, width, label=family, 
                      color=FAMILY_COLORS.get(family, '#666666'))
    
    ax.set_xlabel('NIST Security Level')
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(['Level 1', 'Level 3', 'Level 5'])
    ax.legend()
    ax.grid(True, alpha=0.3, axis='y')
    
    # Use log scale if range is large
    values = [getattr(m, metric_name, 0) for m in metrics_dict.values() if getattr(m, metric_name, 0) > 0]
    if values and max(values) / (min(values) + 1e-10) > 100:
        ax.set_yscale('log')
    
    plt.tight_layout()
    for ext in ['pdf', 'png']:
        plt.savefig(OUTPUT_DIR / f"{filename}.{ext}", dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[PROGRESSION] Saved {filename}")


def create_anomaly_detection_plot(metrics_dict: Dict[str, AlgorithmMetrics],
                                   metric_name: str,
                                   ylabel: str,
                                   title: str,
                                   filename: str):
    """Create box plot showing distribution and potential anomalies"""
    fig, ax = plt.subplots(figsize=(14, 6))
    
    # We need raw data for box plots - load from files
    bench_dir = Path("bench_results/raw")
    
    data = []
    labels = []
    colors = []
    
    for alg_name, metrics in sorted(metrics_dict.items()):
        # Determine operation from metric name
        if 'keygen' in metric_name:
            op = 'keygen'
        elif 'op1' in metric_name:
            op = 'encapsulate' if metrics.family in ['ML-KEM', 'Classic-McEliece', 'HQC'] else 'sign'
        else:
            op = 'decapsulate' if metrics.family in ['ML-KEM', 'Classic-McEliece', 'HQC'] else 'verify'
        
        # Determine directory
        if metrics.family in ['ML-KEM', 'Classic-McEliece', 'HQC']:
            subdir = 'kem'
        else:
            subdir = 'sig'
        
        file_prefix = alg_name.replace('-', '_').replace('+', '+')
        filepath = bench_dir / subdir / f"{file_prefix}_{op}.json"
        
        if filepath.exists():
            with open(filepath) as f:
                json_data = json.load(f)
            timings = np.array(json_data.get('perf_time_ns', [])) / 1e6
            if len(timings) > 0:
                data.append(timings)
                labels.append(alg_name.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', ''))
                colors.append(NIST_COLORS[metrics.nist_level])
    
    if not data:
        print(f"[SKIP] No data for {filename}")
        return
    
    bp = ax.boxplot(data, labels=labels, patch_artist=True, showfliers=True)
    
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.7)
    
    # Mark outliers
    for flier in bp['fliers']:
        flier.set(marker='o', markerfacecolor='red', alpha=0.5, markersize=4)
    
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)
    ax.set_ylabel(ylabel)
    ax.set_title(f"{title}\n(Red dots indicate outliers/anomalies)", fontweight='bold')
    
    # Log scale if needed
    all_vals = np.concatenate(data)
    if max(all_vals) / (min(all_vals) + 1e-10) > 100:
        ax.set_yscale('log')
    
    ax.grid(True, alpha=0.3, axis='y')
    
    # Legend
    legend_elements = [Patch(facecolor=NIST_COLORS[l], label=f'NIST {l}') for l in ['L1', 'L3', 'L5']]
    ax.legend(handles=legend_elements, loc='upper right')
    
    plt.tight_layout()
    for ext in ['pdf', 'png']:
        plt.savefig(OUTPUT_DIR / f"{filename}.{ext}", dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[ANOMALY] Saved {filename}")


def create_size_timing_tradeoff(metrics_dict: Dict[str, AlgorithmMetrics],
                                 timing_metric: str,
                                 size_metric: str,
                                 xlabel: str,
                                 ylabel: str,
                                 title: str,
                                 filename: str):
    """Create scatter plot showing size vs timing trade-off"""
    fig, ax = plt.subplots(figsize=(10, 8))
    
    for alg_name, metrics in metrics_dict.items():
        x = getattr(metrics, size_metric, 0)
        y = getattr(metrics, timing_metric, 0)
        
        if x > 0 and y > 0:
            color = NIST_COLORS[metrics.nist_level]
            marker = 'o' if metrics.family in ['ML-KEM', 'ML-DSA'] else 's' if metrics.family in ['Classic-McEliece', 'Falcon'] else '^'
            
            ax.scatter(x, y, c=color, marker=marker, s=150, alpha=0.7, edgecolors='black', linewidth=1)
            
            # Label
            label = alg_name.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', '')
            ax.annotate(label, (x, y), xytext=(5, 5), textcoords='offset points', fontsize=7)
    
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title, fontweight='bold')
    
    # Use log scale
    ax.set_xscale('log')
    ax.set_yscale('log')
    
    # Legend for NIST levels
    legend_elements = [Patch(facecolor=NIST_COLORS[l], label=f'NIST {l}') for l in ['L1', 'L3', 'L5']]
    ax.legend(handles=legend_elements, loc='upper left')
    
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    for ext in ['pdf', 'png']:
        plt.savefig(OUTPUT_DIR / f"{filename}.{ext}", dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[TRADEOFF] Saved {filename}")


def create_comprehensive_comparison_table(kem_metrics: Dict[str, AlgorithmMetrics],
                                          sig_metrics: Dict[str, AlgorithmMetrics],
                                          filename: str):
    """Create a comprehensive comparison figure with multiple subplots"""
    fig = plt.figure(figsize=(20, 24))
    gs = gridspec.GridSpec(4, 2, figure=fig, hspace=0.3, wspace=0.25)
    
    # Helper function to add subplot
    def add_bar_subplot(ax, metrics_dict, metric, ylabel, title, alg_type):
        levels = ['L1', 'L3', 'L5']
        x_pos = 0
        positions = []
        all_names = []
        all_values = []
        all_colors = []
        
        for level in levels:
            filtered = [(k, v) for k, v in sorted(metrics_dict.items()) if v.nist_level == level]
            for name, m in filtered:
                positions.append(x_pos)
                all_names.append(name.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', '').replace('Classic-McEliece-', 'McE-'))
                all_values.append(getattr(m, metric, 0))
                all_colors.append(NIST_COLORS[level])
                x_pos += 1
            x_pos += 0.5
        
        ax.bar(positions, all_values, color=all_colors, edgecolor='black', linewidth=0.5)
        ax.set_xticks(positions)
        ax.set_xticklabels(all_names, rotation=45, ha='right', fontsize=7)
        ax.set_ylabel(ylabel)
        ax.set_title(title, fontweight='bold', fontsize=10)
        
        if max(all_values) / (min([v for v in all_values if v > 0]) + 1e-10) > 100:
            ax.set_yscale('log')
        ax.grid(True, alpha=0.3, axis='y')
    
    # KEM subplots
    ax1 = fig.add_subplot(gs[0, 0])
    add_bar_subplot(ax1, kem_metrics, 'keygen_mean', 'Time (ms)', 'KEM Key Generation', 'KEM')
    
    ax2 = fig.add_subplot(gs[0, 1])
    add_bar_subplot(ax2, kem_metrics, 'op1_mean', 'Time (ms)', 'KEM Encapsulation', 'KEM')
    
    ax3 = fig.add_subplot(gs[1, 0])
    add_bar_subplot(ax3, kem_metrics, 'op2_mean', 'Time (ms)', 'KEM Decapsulation', 'KEM')
    
    ax4 = fig.add_subplot(gs[1, 1])
    add_bar_subplot(ax4, kem_metrics, 'public_key_size', 'Size (bytes)', 'KEM Public Key Size', 'KEM')
    
    # Signature subplots
    ax5 = fig.add_subplot(gs[2, 0])
    add_bar_subplot(ax5, sig_metrics, 'keygen_mean', 'Time (ms)', 'Signature Key Generation', 'SIG')
    
    ax6 = fig.add_subplot(gs[2, 1])
    add_bar_subplot(ax6, sig_metrics, 'op1_mean', 'Time (ms)', 'Signature Generation', 'SIG')
    
    ax7 = fig.add_subplot(gs[3, 0])
    add_bar_subplot(ax7, sig_metrics, 'op2_mean', 'Time (ms)', 'Signature Verification', 'SIG')
    
    ax8 = fig.add_subplot(gs[3, 1])
    add_bar_subplot(ax8, sig_metrics, 'output_size', 'Size (bytes)', 'Signature Size', 'SIG')
    
    # Main title
    fig.suptitle('Comprehensive PQC Algorithm Comparison\nAll Metrics by NIST Security Level', 
                 fontsize=16, fontweight='bold', y=0.98)
    
    # Legend
    legend_elements = [Patch(facecolor=NIST_COLORS[l], label=f'NIST {l}') for l in ['L1', 'L3', 'L5']]
    fig.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(0.98, 0.96))
    
    for ext in ['pdf', 'png']:
        plt.savefig(OUTPUT_DIR / f"{filename}.{ext}", dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[COMPREHENSIVE] Saved {filename}")


def create_heatmap_comparison(metrics_dict: Dict[str, AlgorithmMetrics],
                               metrics_list: List[Tuple[str, str]],
                               title: str,
                               filename: str):
    """Create heatmap comparing all algorithms across all metrics"""
    algorithms = list(metrics_dict.keys())
    n_algs = len(algorithms)
    n_metrics = len(metrics_list)
    
    # Build data matrix
    data = np.zeros((n_algs, n_metrics))
    for i, alg in enumerate(algorithms):
        for j, (metric, _) in enumerate(metrics_list):
            val = getattr(metrics_dict[alg], metric, 0)
            data[i, j] = val if val > 0 else np.nan
    
    # Normalize each column
    for j in range(n_metrics):
        col = data[:, j]
        valid = ~np.isnan(col)
        if np.any(valid):
            col_min, col_max = np.nanmin(col), np.nanmax(col)
            if col_max > col_min:
                data[:, j] = (col - col_min) / (col_max - col_min)
    
    fig, ax = plt.subplots(figsize=(12, 10))
    
    im = ax.imshow(data, cmap='YlOrRd', aspect='auto')
    
    # Labels
    ax.set_xticks(range(n_metrics))
    ax.set_xticklabels([label for _, label in metrics_list], rotation=45, ha='right')
    ax.set_yticks(range(n_algs))
    ax.set_yticklabels([a.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', '') for a in algorithms])
    
    # Add NIST level color strip
    for i, alg in enumerate(algorithms):
        level = metrics_dict[alg].nist_level
        ax.add_patch(plt.Rectangle((-0.8, i-0.5), 0.3, 1, 
                                   facecolor=NIST_COLORS[level], edgecolor='none'))
    
    ax.set_title(title, fontweight='bold', pad=20)
    
    # Colorbar
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Normalized Value (0=best, 1=worst)', rotation=270, labelpad=20)
    
    plt.tight_layout()
    for ext in ['pdf', 'png']:
        plt.savefig(OUTPUT_DIR / f"{filename}.{ext}", dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[HEATMAP] Saved {filename}")


def create_statistical_summary_plot(metrics_dict: Dict[str, AlgorithmMetrics],
                                     metric_prefix: str,
                                     title: str,
                                     filename: str):
    """Create plot showing mean, median, std, min, max, p95 for each algorithm"""
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    axes = axes.flatten()
    
    stats = ['mean', 'median', 'std', 'min', 'max', 'p95']
    stat_labels = ['Mean', 'Median', 'Std Dev', 'Minimum', 'Maximum', '95th Percentile']
    
    for idx, (stat, label) in enumerate(zip(stats, stat_labels)):
        ax = axes[idx]
        metric_name = f"{metric_prefix}_{stat}"
        
        algs = []
        values = []
        colors = []
        
        for alg_name, metrics in sorted(metrics_dict.items()):
            val = getattr(metrics, metric_name, 0)
            if val > 0:
                algs.append(alg_name.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', '').replace('Classic-McEliece-', 'McE-'))
                values.append(val)
                colors.append(NIST_COLORS[metrics.nist_level])
        
        ax.barh(algs, values, color=colors, edgecolor='black', linewidth=0.5)
        ax.set_xlabel('Time (ms)')
        ax.set_title(f'{label}', fontweight='bold')
        
        if values and max(values) / (min(values) + 1e-10) > 100:
            ax.set_xscale('log')
        ax.grid(True, alpha=0.3, axis='x')
    
    fig.suptitle(title, fontsize=14, fontweight='bold', y=1.02)
    
    # Legend
    legend_elements = [Patch(facecolor=NIST_COLORS[l], label=f'NIST {l}') for l in ['L1', 'L3', 'L5']]
    fig.legend(handles=legend_elements, loc='upper right', bbox_to_anchor=(0.98, 0.98))
    
    plt.tight_layout()
    for ext in ['pdf', 'png']:
        plt.savefig(OUTPUT_DIR / f"{filename}.{ext}", dpi=300, bbox_inches='tight')
    plt.close()
    print(f"[STATS] Saved {filename}")


def main():
    print("=" * 70)
    print("COMPREHENSIVE PQC BENCHMARK VISUALIZATION")
    print("=" * 70)
    
    # Load data
    bench_dir = Path("bench_results")
    if not bench_dir.exists():
        print("ERROR: bench_results directory not found")
        return
    
    kem_metrics, sig_metrics = load_benchmark_data(bench_dir)
    
    print(f"\nLoaded {len(kem_metrics)} KEM algorithms")
    print(f"Loaded {len(sig_metrics)} Signature algorithms")
    
    # =========================================================================
    # SPIDER/RADAR CHARTS
    # =========================================================================
    print("\n--- Generating Spider Charts ---")
    
    # KEM Spider - All Timing Metrics
    kem_timing_metrics = ['keygen_mean', 'op1_mean', 'op2_mean', 'keygen_p95', 'op1_p95', 'op2_p95']
    kem_timing_labels = ['KeyGen Mean', 'Encaps Mean', 'Decaps Mean', 'KeyGen P95', 'Encaps P95', 'Decaps P95']
    create_spider_chart(kem_metrics, kem_timing_metrics, kem_timing_labels,
                        'KEM Timing Metrics Comparison', 'spider_kem_timing', log_scale=True)
    
    # KEM Spider - By NIST Level
    for level in ['L1', 'L3', 'L5']:
        create_spider_by_nist_level(kem_metrics, kem_timing_metrics, kem_timing_labels,
                                     level, 'KEM Timing Metrics', 'spider_kem_timing', log_scale=True)
    
    # KEM Spider - All Metrics (Timing + Size)
    kem_all_metrics = ['keygen_mean', 'op1_mean', 'op2_mean', 'public_key_size', 'secret_key_size', 'output_size']
    kem_all_labels = ['KeyGen Time', 'Encaps Time', 'Decaps Time', 'Public Key', 'Secret Key', 'Ciphertext']
    create_spider_chart(kem_metrics, kem_all_metrics, kem_all_labels,
                        'KEM Complete Metrics (Timing + Size)', 'spider_kem_all', log_scale=True)
    
    # Signature Spider - All Timing Metrics
    sig_timing_metrics = ['keygen_mean', 'op1_mean', 'op2_mean', 'keygen_p95', 'op1_p95', 'op2_p95']
    sig_timing_labels = ['KeyGen Mean', 'Sign Mean', 'Verify Mean', 'KeyGen P95', 'Sign P95', 'Verify P95']
    create_spider_chart(sig_metrics, sig_timing_metrics, sig_timing_labels,
                        'Signature Timing Metrics Comparison', 'spider_sig_timing', log_scale=True)
    
    # Signature Spider - By NIST Level
    for level in ['L1', 'L3', 'L5']:
        create_spider_by_nist_level(sig_metrics, sig_timing_metrics, sig_timing_labels,
                                     level, 'Signature Timing Metrics', 'spider_sig_timing', log_scale=True)
    
    # Signature Spider - All Metrics
    sig_all_metrics = ['keygen_mean', 'op1_mean', 'op2_mean', 'public_key_size', 'secret_key_size', 'output_size']
    sig_all_labels = ['KeyGen Time', 'Sign Time', 'Verify Time', 'Public Key', 'Secret Key', 'Signature']
    create_spider_chart(sig_metrics, sig_all_metrics, sig_all_labels,
                        'Signature Complete Metrics (Timing + Size)', 'spider_sig_all', log_scale=True)
    
    # =========================================================================
    # INDIVIDUAL METRIC BAR CHARTS
    # =========================================================================
    print("\n--- Generating Individual Metric Charts ---")
    
    # KEM Timing Metrics
    for metric, label, filename in [
        ('keygen_mean', 'Mean Key Generation Time (ms)', 'kem_keygen_mean'),
        ('keygen_median', 'Median Key Generation Time (ms)', 'kem_keygen_median'),
        ('keygen_std', 'Key Generation Std Dev (ms)', 'kem_keygen_std'),
        ('keygen_p95', '95th Percentile Key Generation (ms)', 'kem_keygen_p95'),
        ('op1_mean', 'Mean Encapsulation Time (ms)', 'kem_encaps_mean'),
        ('op1_median', 'Median Encapsulation Time (ms)', 'kem_encaps_median'),
        ('op1_p95', '95th Percentile Encapsulation (ms)', 'kem_encaps_p95'),
        ('op2_mean', 'Mean Decapsulation Time (ms)', 'kem_decaps_mean'),
        ('op2_median', 'Median Decapsulation Time (ms)', 'kem_decaps_median'),
        ('op2_p95', '95th Percentile Decapsulation (ms)', 'kem_decaps_p95'),
    ]:
        create_metric_comparison_bar(kem_metrics, metric, label, 
                                      f'KEM {label}', f'bar_{filename}', log_scale=True)
    
    # KEM Size Metrics
    for metric, label, filename in [
        ('public_key_size', 'Public Key Size (bytes)', 'kem_pubkey_size'),
        ('secret_key_size', 'Secret Key Size (bytes)', 'kem_seckey_size'),
        ('output_size', 'Ciphertext Size (bytes)', 'kem_ciphertext_size'),
    ]:
        create_metric_comparison_bar(kem_metrics, metric, label,
                                      f'KEM {label}', f'bar_{filename}', log_scale=True)
    
    # Signature Timing Metrics
    for metric, label, filename in [
        ('keygen_mean', 'Mean Key Generation Time (ms)', 'sig_keygen_mean'),
        ('keygen_median', 'Median Key Generation Time (ms)', 'sig_keygen_median'),
        ('keygen_std', 'Key Generation Std Dev (ms)', 'sig_keygen_std'),
        ('keygen_p95', '95th Percentile Key Generation (ms)', 'sig_keygen_p95'),
        ('op1_mean', 'Mean Signing Time (ms)', 'sig_sign_mean'),
        ('op1_median', 'Median Signing Time (ms)', 'sig_sign_median'),
        ('op1_p95', '95th Percentile Signing (ms)', 'sig_sign_p95'),
        ('op2_mean', 'Mean Verification Time (ms)', 'sig_verify_mean'),
        ('op2_median', 'Median Verification Time (ms)', 'sig_verify_median'),
        ('op2_p95', '95th Percentile Verification (ms)', 'sig_verify_p95'),
    ]:
        create_metric_comparison_bar(sig_metrics, metric, label,
                                      f'Signature {label}', f'bar_{filename}', log_scale=True)
    
    # Signature Size Metrics
    for metric, label, filename in [
        ('public_key_size', 'Public Key Size (bytes)', 'sig_pubkey_size'),
        ('secret_key_size', 'Secret Key Size (bytes)', 'sig_seckey_size'),
        ('output_size', 'Signature Size (bytes)', 'sig_signature_size'),
    ]:
        create_metric_comparison_bar(sig_metrics, metric, label,
                                      f'Signature {label}', f'bar_{filename}', log_scale=True)
    
    # =========================================================================
    # NIST LEVEL PROGRESSION
    # =========================================================================
    print("\n--- Generating NIST Level Progression Charts ---")
    
    for metric, label, filename in [
        ('keygen_mean', 'Mean Time (ms)', 'kem_keygen'),
        ('op1_mean', 'Mean Time (ms)', 'kem_encaps'),
        ('op2_mean', 'Mean Time (ms)', 'kem_decaps'),
        ('public_key_size', 'Size (bytes)', 'kem_pubkey'),
        ('output_size', 'Size (bytes)', 'kem_ciphertext'),
    ]:
        create_nist_level_progression(kem_metrics, metric, label,
                                       f'KEM {filename.replace("kem_", "").title()} by NIST Level',
                                       f'progression_{filename}')
    
    for metric, label, filename in [
        ('keygen_mean', 'Mean Time (ms)', 'sig_keygen'),
        ('op1_mean', 'Mean Time (ms)', 'sig_sign'),
        ('op2_mean', 'Mean Time (ms)', 'sig_verify'),
        ('public_key_size', 'Size (bytes)', 'sig_pubkey'),
        ('output_size', 'Size (bytes)', 'sig_signature'),
    ]:
        create_nist_level_progression(sig_metrics, metric, label,
                                       f'Signature {filename.replace("sig_", "").title()} by NIST Level',
                                       f'progression_{filename}')
    
    # =========================================================================
    # ANOMALY DETECTION PLOTS
    # =========================================================================
    print("\n--- Generating Anomaly Detection Plots ---")
    
    create_anomaly_detection_plot(kem_metrics, 'keygen_mean', 'Time (ms)',
                                   'KEM Key Generation Distribution', 'anomaly_kem_keygen')
    create_anomaly_detection_plot(kem_metrics, 'op1_mean', 'Time (ms)',
                                   'KEM Encapsulation Distribution', 'anomaly_kem_encaps')
    create_anomaly_detection_plot(kem_metrics, 'op2_mean', 'Time (ms)',
                                   'KEM Decapsulation Distribution', 'anomaly_kem_decaps')
    
    create_anomaly_detection_plot(sig_metrics, 'keygen_mean', 'Time (ms)',
                                   'Signature Key Generation Distribution', 'anomaly_sig_keygen')
    create_anomaly_detection_plot(sig_metrics, 'op1_mean', 'Time (ms)',
                                   'Signature Generation Distribution', 'anomaly_sig_sign')
    create_anomaly_detection_plot(sig_metrics, 'op2_mean', 'Time (ms)',
                                   'Signature Verification Distribution', 'anomaly_sig_verify')
    
    # =========================================================================
    # SIZE VS TIMING TRADE-OFF PLOTS
    # =========================================================================
    print("\n--- Generating Trade-off Plots ---")
    
    create_size_timing_tradeoff(kem_metrics, 'keygen_mean', 'public_key_size',
                                 'Public Key Size (bytes)', 'Key Generation Time (ms)',
                                 'KEM: Public Key Size vs Key Generation Time', 'tradeoff_kem_keygen_pubkey')
    create_size_timing_tradeoff(kem_metrics, 'op1_mean', 'output_size',
                                 'Ciphertext Size (bytes)', 'Encapsulation Time (ms)',
                                 'KEM: Ciphertext Size vs Encapsulation Time', 'tradeoff_kem_encaps_ct')
    
    create_size_timing_tradeoff(sig_metrics, 'op1_mean', 'output_size',
                                 'Signature Size (bytes)', 'Signing Time (ms)',
                                 'Signature: Signature Size vs Signing Time', 'tradeoff_sig_sign_size')
    create_size_timing_tradeoff(sig_metrics, 'op2_mean', 'output_size',
                                 'Signature Size (bytes)', 'Verification Time (ms)',
                                 'Signature: Signature Size vs Verification Time', 'tradeoff_sig_verify_size')
    
    # =========================================================================
    # COMPREHENSIVE COMPARISON
    # =========================================================================
    print("\n--- Generating Comprehensive Comparison ---")
    
    create_comprehensive_comparison_table(kem_metrics, sig_metrics, 'comprehensive_all_metrics')
    
    # =========================================================================
    # HEATMAPS
    # =========================================================================
    print("\n--- Generating Heatmaps ---")
    
    kem_heat_metrics = [
        ('keygen_mean', 'KeyGen'),
        ('op1_mean', 'Encaps'),
        ('op2_mean', 'Decaps'),
        ('keygen_std', 'KeyGen σ'),
        ('public_key_size', 'PK Size'),
        ('secret_key_size', 'SK Size'),
        ('output_size', 'CT Size'),
    ]
    create_heatmap_comparison(kem_metrics, kem_heat_metrics,
                               'KEM Algorithm Performance Heatmap', 'heatmap_kem')
    
    sig_heat_metrics = [
        ('keygen_mean', 'KeyGen'),
        ('op1_mean', 'Sign'),
        ('op2_mean', 'Verify'),
        ('keygen_std', 'KeyGen σ'),
        ('public_key_size', 'PK Size'),
        ('secret_key_size', 'SK Size'),
        ('output_size', 'Sig Size'),
    ]
    create_heatmap_comparison(sig_metrics, sig_heat_metrics,
                               'Signature Algorithm Performance Heatmap', 'heatmap_sig')
    
    # =========================================================================
    # STATISTICAL SUMMARY PLOTS
    # =========================================================================
    print("\n--- Generating Statistical Summary Plots ---")
    
    create_statistical_summary_plot(kem_metrics, 'keygen', 
                                     'KEM Key Generation: All Statistical Metrics', 'stats_kem_keygen')
    create_statistical_summary_plot(kem_metrics, 'op1',
                                     'KEM Encapsulation: All Statistical Metrics', 'stats_kem_encaps')
    create_statistical_summary_plot(kem_metrics, 'op2',
                                     'KEM Decapsulation: All Statistical Metrics', 'stats_kem_decaps')
    
    create_statistical_summary_plot(sig_metrics, 'keygen',
                                     'Signature Key Generation: All Statistical Metrics', 'stats_sig_keygen')
    create_statistical_summary_plot(sig_metrics, 'op1',
                                     'Signature Generation: All Statistical Metrics', 'stats_sig_sign')
    create_statistical_summary_plot(sig_metrics, 'op2',
                                     'Signature Verification: All Statistical Metrics', 'stats_sig_verify')
    
    # =========================================================================
    # SUMMARY
    # =========================================================================
    print("\n" + "=" * 70)
    print("VISUALIZATION COMPLETE")
    print("=" * 70)
    
    # Count generated files
    pdf_count = len(list(OUTPUT_DIR.glob("*.pdf")))
    png_count = len(list(OUTPUT_DIR.glob("*.png")))
    
    print(f"\nOutput directory: {OUTPUT_DIR}")
    print(f"PDF files: {pdf_count}")
    print(f"PNG files: {png_count}")
    print(f"Total: {pdf_count + png_count} files")


if __name__ == "__main__":
    main()
