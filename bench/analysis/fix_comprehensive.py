#!/usr/bin/env python3
"""
Fix and generate remaining comprehensive plots (comprehensive comparison, heatmaps, statistical summaries).
"""

import json
import numpy as np
import matplotlib.pyplot as plt
from pathlib import Path
import warnings

warnings.filterwarnings('ignore')

# Paths
BENCH_RESULTS = Path("bench_results")
OUTPUT_DIR = Path("bench_analysis/plots_comprehensive")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# IEEE-style settings
plt.rcParams.update({
    'font.family': 'serif',
    'font.size': 10,
    'axes.labelsize': 11,
    'axes.titlesize': 12,
    'legend.fontsize': 9,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'figure.dpi': 150,
    'savefig.dpi': 300,
    'savefig.bbox': 'tight',
    'savefig.pad_inches': 0.1,
})

# Colors
NIST_COLORS = {'L1': '#2ecc71', 'L3': '#3498db', 'L5': '#e74c3c'}
FAMILY_COLORS = {
    'ML-KEM': '#3498db', 'Classic-McEliece': '#e74c3c', 'HQC': '#2ecc71',
    'ML-DSA': '#9b59b6', 'Falcon': '#f39c12', 'SPHINCS+': '#1abc9c'
}

def detect_nist_level(name):
    name = name.upper()
    if '512' in name or '128' in name or '44' in name or '348864' in name:
        return 'L1'
    elif '768' in name or '192' in name or '65' in name or '460896' in name:
        return 'L3'
    elif '1024' in name or '256' in name or '87' in name or '8192128' in name:
        return 'L5'
    return 'L1'

def detect_family(name):
    name_upper = name.upper()
    if 'ML-KEM' in name_upper or 'MLKEM' in name_upper:
        return 'ML-KEM'
    elif 'MCELIECE' in name_upper or 'CLASSIC' in name_upper:
        return 'Classic-McEliece'
    elif 'HQC' in name_upper:
        return 'HQC'
    elif 'ML-DSA' in name_upper or 'MLDSA' in name_upper or 'DILITHIUM' in name_upper:
        return 'ML-DSA'
    elif 'FALCON' in name_upper:
        return 'Falcon'
    elif 'SPHINCS' in name_upper:
        return 'SPHINCS+'
    return 'Other'

def load_all_benchmarks():
    """Load all raw benchmark files."""
    kem_metrics = []
    sig_metrics = []
    
    # Load KEM
    kem_dir = BENCH_RESULTS / "raw" / "kem"
    if kem_dir.exists():
        for f in sorted(kem_dir.glob("*.json")):
            with open(f) as fp:
                data = json.load(fp)
            name = data.get('algorithm', f.stem)
            family = detect_family(name)
            level = detect_nist_level(name)
            
            metrics = {'name': name, 'family': family, 'nist_level': level}
            
            for op in ['keygen', 'encapsulate', 'decapsulate']:
                if op in data:
                    op_data = data[op]
                    if 'timing' in op_data:
                        timing = op_data['timing']
                        times_ms = [t / 1e6 for t in timing.get('perf_ns', [])]
                        if times_ms:
                            metrics[f'{op}_mean'] = np.mean(times_ms)
                            metrics[f'{op}_median'] = np.median(times_ms)
                            metrics[f'{op}_std'] = np.std(times_ms)
                            metrics[f'{op}_min'] = np.min(times_ms)
                            metrics[f'{op}_max'] = np.max(times_ms)
                            metrics[f'{op}_p95'] = np.percentile(times_ms, 95)
            
            if 'sizes' in data:
                sizes = data['sizes']
                metrics['pubkey_size'] = sizes.get('public_key', 0)
                metrics['seckey_size'] = sizes.get('secret_key', 0)
                metrics['ciphertext_size'] = sizes.get('ciphertext', 0)
            
            kem_metrics.append(metrics)
    
    # Load Signatures
    sig_dir = BENCH_RESULTS / "raw" / "sig"
    if sig_dir.exists():
        for f in sorted(sig_dir.glob("*.json")):
            with open(f) as fp:
                data = json.load(fp)
            name = data.get('algorithm', f.stem)
            family = detect_family(name)
            level = detect_nist_level(name)
            
            metrics = {'name': name, 'family': family, 'nist_level': level}
            
            for op in ['keygen', 'sign', 'verify']:
                if op in data:
                    op_data = data[op]
                    if 'timing' in op_data:
                        timing = op_data['timing']
                        times_ms = [t / 1e6 for t in timing.get('perf_ns', [])]
                        if times_ms:
                            metrics[f'{op}_mean'] = np.mean(times_ms)
                            metrics[f'{op}_median'] = np.median(times_ms)
                            metrics[f'{op}_std'] = np.std(times_ms)
                            metrics[f'{op}_min'] = np.min(times_ms)
                            metrics[f'{op}_max'] = np.max(times_ms)
                            metrics[f'{op}_p95'] = np.percentile(times_ms, 95)
            
            if 'sizes' in data:
                sizes = data['sizes']
                metrics['pubkey_size'] = sizes.get('public_key', 0)
                metrics['seckey_size'] = sizes.get('secret_key', 0)
                metrics['signature_size'] = sizes.get('signature', 0)
            
            sig_metrics.append(metrics)
    
    return kem_metrics, sig_metrics

def save_figure(fig, name):
    """Save figure as both PDF and PNG."""
    fig.savefig(OUTPUT_DIR / f"{name}.pdf", format='pdf')
    fig.savefig(OUTPUT_DIR / f"{name}.png", format='png')
    plt.close(fig)
    print(f"[SAVED] {name}")

def create_comprehensive_comparison(kem_metrics, sig_metrics, filename):
    """Create a comprehensive multi-panel comparison figure."""
    fig, axes = plt.subplots(2, 4, figsize=(20, 10))
    fig.suptitle('Comprehensive PQC Algorithm Comparison', fontsize=16, fontweight='bold')
    
    # Sort metrics
    kem_sorted = sorted(kem_metrics, key=lambda x: x.get('keygen_mean', 0))
    sig_sorted = sorted(sig_metrics, key=lambda x: x.get('keygen_mean', 0))
    
    def safe_bar_plot(ax, data, metric, title, ylabel, is_kem=True):
        names = [d['name'][-15:] for d in data]  # Truncate long names
        values = [d.get(metric, 0) for d in data]
        colors = [FAMILY_COLORS.get(d['family'], '#888888') for d in data]
        
        if not any(v > 0 for v in values):
            ax.set_title(f"{title}\n(No data)")
            return
        
        bars = ax.barh(names, values, color=colors, edgecolor='black', linewidth=0.5)
        ax.set_xlabel(ylabel)
        ax.set_title(title)
        
        # Use log scale if range is large
        if max(values) > 0 and min([v for v in values if v > 0]) > 0:
            ratio = max(values) / min([v for v in values if v > 0])
            if ratio > 100:
                ax.set_xscale('log')
        
        ax.grid(axis='x', alpha=0.3, linestyle='--')
    
    # Row 1: KEM metrics
    safe_bar_plot(axes[0, 0], kem_sorted, 'keygen_mean', 'KEM Key Generation', 'Time (ms)', True)
    safe_bar_plot(axes[0, 1], kem_sorted, 'encapsulate_mean', 'KEM Encapsulation', 'Time (ms)', True)
    safe_bar_plot(axes[0, 2], kem_sorted, 'decapsulate_mean', 'KEM Decapsulation', 'Time (ms)', True)
    safe_bar_plot(axes[0, 3], kem_sorted, 'pubkey_size', 'KEM Public Key Size', 'Bytes', True)
    
    # Row 2: Signature metrics
    safe_bar_plot(axes[1, 0], sig_sorted, 'keygen_mean', 'Sig Key Generation', 'Time (ms)', False)
    safe_bar_plot(axes[1, 1], sig_sorted, 'sign_mean', 'Signing', 'Time (ms)', False)
    safe_bar_plot(axes[1, 2], sig_sorted, 'verify_mean', 'Verification', 'Time (ms)', False)
    safe_bar_plot(axes[1, 3], sig_sorted, 'signature_size', 'Signature Size', 'Bytes', False)
    
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, edgecolor='black', label=f) 
                       for f, c in FAMILY_COLORS.items()]
    fig.legend(handles=legend_elements, loc='lower center', ncol=6, 
               bbox_to_anchor=(0.5, -0.02), fontsize=9)
    
    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    save_figure(fig, filename)

def create_heatmap(data, metrics_keys, metric_labels, title, filename):
    """Create a heatmap comparison."""
    if not data:
        print(f"[SKIP] No data for {filename}")
        return
    
    names = [d['name'] for d in data]
    
    # Build matrix
    values_matrix = []
    for m in metrics_keys:
        row = [d.get(m, 0) for d in data]
        # Normalize row to 0-1 for visualization
        if max(row) > 0:
            row = [v / max(row) for v in row]
        values_matrix.append(row)
    
    values_matrix = np.array(values_matrix)
    
    fig, ax = plt.subplots(figsize=(max(10, len(names) * 0.8), len(metrics_keys) * 0.8 + 2))
    
    im = ax.imshow(values_matrix, cmap='RdYlGn_r', aspect='auto')
    
    ax.set_xticks(range(len(names)))
    ax.set_xticklabels([n[-12:] for n in names], rotation=45, ha='right')
    ax.set_yticks(range(len(metric_labels)))
    ax.set_yticklabels(metric_labels)
    
    ax.set_title(title)
    
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    cbar.set_label('Normalized Value (Lower is Better)', rotation=270, labelpad=15)
    
    plt.tight_layout()
    save_figure(fig, filename)

def create_statistical_summary(data, op_prefix, title, filename):
    """Create a multi-panel statistical summary for an operation."""
    if not data:
        print(f"[SKIP] No data for {filename}")
        return
    
    # Check if data exists
    valid_data = [d for d in data if f'{op_prefix}_mean' in d]
    if not valid_data:
        print(f"[SKIP] No {op_prefix} data for {filename}")
        return
    
    fig, axes = plt.subplots(2, 3, figsize=(15, 10))
    fig.suptitle(title, fontsize=14, fontweight='bold')
    
    names = [d['name'][-12:] for d in valid_data]
    colors = [FAMILY_COLORS.get(d['family'], '#888888') for d in valid_data]
    
    metrics = [
        (f'{op_prefix}_mean', 'Mean (ms)'),
        (f'{op_prefix}_median', 'Median (ms)'),
        (f'{op_prefix}_std', 'Std Dev (ms)'),
        (f'{op_prefix}_min', 'Minimum (ms)'),
        (f'{op_prefix}_max', 'Maximum (ms)'),
        (f'{op_prefix}_p95', '95th Percentile (ms)')
    ]
    
    for idx, (metric, label) in enumerate(metrics):
        ax = axes[idx // 3, idx % 3]
        values = [d.get(metric, 0) for d in valid_data]
        
        bars = ax.bar(range(len(names)), values, color=colors, edgecolor='black', linewidth=0.5)
        ax.set_xticks(range(len(names)))
        ax.set_xticklabels(names, rotation=45, ha='right')
        ax.set_ylabel(label)
        ax.set_title(label)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        
        # Use log scale if needed
        if max(values) > 0 and min([v for v in values if v > 0]) > 0:
            if max(values) / min([v for v in values if v > 0]) > 100:
                ax.set_yscale('log')
    
    plt.tight_layout()
    save_figure(fig, filename)

def main():
    print("=" * 70)
    print("  GENERATING REMAINING COMPREHENSIVE PLOTS")
    print("=" * 70)
    
    kem_metrics, sig_metrics = load_all_benchmarks()
    print(f"Loaded {len(kem_metrics)} KEM algorithms")
    print(f"Loaded {len(sig_metrics)} Signature algorithms")
    
    # Comprehensive comparison
    print("\n--- Comprehensive Comparison ---")
    create_comprehensive_comparison(kem_metrics, sig_metrics, 'comprehensive_all_metrics')
    
    # Heatmaps
    print("\n--- Heatmaps ---")
    kem_metrics_keys = ['keygen_mean', 'encapsulate_mean', 'decapsulate_mean', 
                        'pubkey_size', 'seckey_size', 'ciphertext_size']
    kem_labels = ['KeyGen', 'Encaps', 'Decaps', 'PubKey', 'SecKey', 'Ciphertext']
    create_heatmap(kem_metrics, kem_metrics_keys, kem_labels, 
                   'KEM Performance Heatmap (Normalized)', 'heatmap_kem')
    
    sig_metrics_keys = ['keygen_mean', 'sign_mean', 'verify_mean',
                        'pubkey_size', 'seckey_size', 'signature_size']
    sig_labels = ['KeyGen', 'Sign', 'Verify', 'PubKey', 'SecKey', 'Signature']
    create_heatmap(sig_metrics, sig_metrics_keys, sig_labels,
                   'Signature Performance Heatmap (Normalized)', 'heatmap_sig')
    
    # Statistical summaries
    print("\n--- Statistical Summaries ---")
    create_statistical_summary(kem_metrics, 'keygen', 'KEM Key Generation Statistics', 'stats_kem_keygen')
    create_statistical_summary(kem_metrics, 'encapsulate', 'KEM Encapsulation Statistics', 'stats_kem_encaps')
    create_statistical_summary(kem_metrics, 'decapsulate', 'KEM Decapsulation Statistics', 'stats_kem_decaps')
    create_statistical_summary(sig_metrics, 'keygen', 'Signature Key Generation Statistics', 'stats_sig_keygen')
    create_statistical_summary(sig_metrics, 'sign', 'Signing Statistics', 'stats_sig_sign')
    create_statistical_summary(sig_metrics, 'verify', 'Verification Statistics', 'stats_sig_verify')
    
    print("\n" + "=" * 70)
    print("  COMPLETE - Remaining plots generated!")
    print("=" * 70)

if __name__ == "__main__":
    main()
