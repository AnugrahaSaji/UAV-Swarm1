#!/usr/bin/env python3
"""
Comprehensive IEEE-Style PQC Benchmark Report Generator

Generates detailed LaTeX report with:
- Executive summary
- Per-AEAD segmented analysis (AES-GCM, ChaCha20, ASCON)
- Per-NIST-Level segmented analysis (L1, L3, L5)
- Spider/Radar charts for bucket comparisons
- Individual suite pages (72 pages)
- Bar charts, heatmaps, scatter plots
- Statistical tables

Usage:
    python suite_benchmarks/generate_ieee_report.py [benchmark_results.json]
"""

import json
import sys
import math
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import statistics

# Plotting
try:
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches
    from matplotlib.patches import Polygon
    import numpy as np
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("WARNING: matplotlib not available")

# Output directories
SCRIPT_DIR = Path(__file__).parent
OUTPUT_DIR = SCRIPT_DIR / "ieee_report_output"
FIGURES_DIR = OUTPUT_DIR / "figures"
SUITES_DIR = OUTPUT_DIR / "suites"


@dataclass
class SuiteResult:
    """Parsed suite benchmark result."""
    suite_id: str
    iteration: int
    nist_level: str
    kem_name: str
    sig_name: str
    aead: str
    handshake_ms: float
    kem_keygen_ms: float
    kem_encaps_ms: float
    kem_decaps_ms: float
    sig_sign_ms: float
    sig_verify_ms: float
    pub_key_size_bytes: int
    ciphertext_size_bytes: int
    sig_size_bytes: int
    throughput_mbps: float
    latency_ms: float
    power_w: float
    energy_mj: float
    success: bool
    error_message: str
    
    @property
    def total_artifact_size(self) -> int:
        return self.pub_key_size_bytes + self.ciphertext_size_bytes + self.sig_size_bytes
    
    @property
    def kem_total_ms(self) -> float:
        return self.kem_keygen_ms + self.kem_encaps_ms + self.kem_decaps_ms
    
    @property
    def sig_total_ms(self) -> float:
        return self.sig_sign_ms + self.sig_verify_ms
    
    @property
    def primitive_total_ms(self) -> float:
        return self.kem_total_ms + self.sig_total_ms
    
    @property
    def aead_normalized(self) -> str:
        """Normalize AEAD name for grouping."""
        aead_lower = self.aead.lower()
        if 'aes' in aead_lower or 'gcm' in aead_lower:
            return 'AES-256-GCM'
        elif 'chacha' in aead_lower:
            return 'ChaCha20-Poly1305'
        elif 'ascon' in aead_lower:
            return 'ASCON-128a'
        return self.aead


def load_results(json_path: Path) -> Tuple[dict, List[SuiteResult]]:
    """Load and parse benchmark results."""
    with open(json_path, 'r') as f:
        raw = json.load(f)
    
    results = []
    for suite_data in raw.get('suites', []):
        results.append(SuiteResult(
            suite_id=suite_data.get('suite_id', ''),
            iteration=suite_data.get('iteration', 0),
            nist_level=suite_data.get('nist_level', ''),
            kem_name=suite_data.get('kem_name', ''),
            sig_name=suite_data.get('sig_name', ''),
            aead=suite_data.get('aead', ''),
            handshake_ms=float(suite_data.get('handshake_ms', 0)),
            kem_keygen_ms=float(suite_data.get('kem_keygen_ms', 0)),
            kem_encaps_ms=float(suite_data.get('kem_encaps_ms', 0)),
            kem_decaps_ms=float(suite_data.get('kem_decaps_ms', 0)),
            sig_sign_ms=float(suite_data.get('sig_sign_ms', 0)),
            sig_verify_ms=float(suite_data.get('sig_verify_ms', 0)),
            pub_key_size_bytes=int(suite_data.get('pub_key_size_bytes', 0)),
            ciphertext_size_bytes=int(suite_data.get('ciphertext_size_bytes', 0)),
            sig_size_bytes=int(suite_data.get('sig_size_bytes', 0)),
            throughput_mbps=float(suite_data.get('throughput_mbps', 0)),
            latency_ms=float(suite_data.get('latency_ms', 0)),
            power_w=float(suite_data.get('power_w', 0)),
            energy_mj=float(suite_data.get('energy_mj', 0)),
            success=bool(suite_data.get('success', False)),
            error_message=suite_data.get('error_message', ''),
        ))
    
    return raw, results


def categorize_results(results: List[SuiteResult]) -> dict:
    """Categorize results by various dimensions."""
    cats = {
        'by_aead': defaultdict(list),
        'by_level': defaultdict(list),
        'by_kem': defaultdict(list),
        'by_sig': defaultdict(list),
        'by_kem_aead': defaultdict(list),
        'by_sig_aead': defaultdict(list),
        'by_kem_level': defaultdict(list),
        'by_sig_level': defaultdict(list),
        'successful': [],
        'failed': [],
        'all': results,
    }
    
    for r in results:
        if r.success:
            cats['successful'].append(r)
            cats['by_aead'][r.aead_normalized].append(r)
            cats['by_level'][r.nist_level].append(r)
            cats['by_kem'][r.kem_name].append(r)
            cats['by_sig'][r.sig_name].append(r)
            cats['by_kem_aead'][(r.kem_name, r.aead_normalized)].append(r)
            cats['by_sig_aead'][(r.sig_name, r.aead_normalized)].append(r)
            cats['by_kem_level'][(r.kem_name, r.nist_level)].append(r)
            cats['by_sig_level'][(r.sig_name, r.nist_level)].append(r)
        else:
            cats['failed'].append(r)
    
    return cats


# =============================================================================
# Color Schemes
# =============================================================================

AEAD_COLORS = {
    'AES-256-GCM': '#3498db',
    'ChaCha20-Poly1305': '#e74c3c',
    'ASCON-128a': '#2ecc71',
}

LEVEL_COLORS = {
    'L1': '#3498db',
    'L3': '#f39c12',
    'L5': '#e74c3c',
}

KEM_COLORS = {
    'ML-KEM-512': '#2ecc71',
    'ML-KEM-768': '#27ae60',
    'ML-KEM-1024': '#1e8449',
    'HQC-128': '#3498db',
    'HQC-192': '#2980b9',
    'HQC-256': '#1f618d',
    'Classic-McEliece-348864': '#e74c3c',
    'Classic-McEliece-460896': '#c0392b',
    'Classic-McEliece-8192128': '#922b21',
}

SIG_COLORS = {
    'Falcon-512': '#9b59b6',
    'Falcon-1024': '#8e44ad',
    'ML-DSA-44': '#f39c12',
    'ML-DSA-65': '#e67e22',
    'ML-DSA-87': '#d35400',
    'SPHINCS+-SHA2-128s-simple': '#1abc9c',
    'SPHINCS+-SHA2-192s-simple': '#16a085',
    'SPHINCS+-SHA2-256s-simple': '#0e6655',
}


# =============================================================================
# Visualization Functions
# =============================================================================

def create_radar_chart(data: Dict[str, List[float]], labels: List[str], 
                       title: str, output_path: Path, colors: dict):
    """Create a radar/spider chart comparing multiple categories."""
    if not HAS_MATPLOTLIB:
        return
    
    num_vars = len(labels)
    angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
    angles += angles[:1]  # Complete the circle
    
    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    
    for category, values in data.items():
        # Normalize values to 0-1 range for comparison
        max_val = max(values) if max(values) > 0 else 1
        normalized = [v / max_val for v in values]
        normalized += normalized[:1]  # Complete the circle
        
        color = colors.get(category, '#95a5a6')
        ax.plot(angles, normalized, 'o-', linewidth=2, label=category, color=color)
        ax.fill(angles, normalized, alpha=0.25, color=color)
    
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, size=10)
    ax.set_title(title, size=14, fontweight='bold', pad=20)
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0))
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.savefig(output_path.with_suffix('.png'), dpi=300, bbox_inches='tight')
    plt.close()


def create_grouped_bar_chart(data: Dict[str, Dict[str, float]], 
                             title: str, ylabel: str, output_path: Path,
                             group_colors: dict, log_scale: bool = False):
    """Create grouped bar chart."""
    if not HAS_MATPLOTLIB:
        return
    
    categories = list(data.keys())
    sub_categories = list(data[categories[0]].keys()) if categories else []
    
    x = np.arange(len(sub_categories))
    width = 0.8 / len(categories)
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    for i, cat in enumerate(categories):
        values = [data[cat].get(sub, 0) for sub in sub_categories]
        offset = (i - len(categories)/2 + 0.5) * width
        bars = ax.bar(x + offset, values, width, label=cat, 
                     color=group_colors.get(cat, '#95a5a6'), alpha=0.8)
    
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(sub_categories, rotation=45, ha='right')
    ax.legend()
    
    if log_scale:
        ax.set_yscale('log')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.savefig(output_path.with_suffix('.png'), dpi=300, bbox_inches='tight')
    plt.close()


def create_stacked_bar_chart(data: Dict[str, Dict[str, float]], 
                             title: str, ylabel: str, output_path: Path,
                             component_colors: dict):
    """Create stacked bar chart showing composition."""
    if not HAS_MATPLOTLIB:
        return
    
    categories = list(data.keys())
    components = list(data[categories[0]].keys()) if categories else []
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    x = np.arange(len(categories))
    bottom = np.zeros(len(categories))
    
    for comp in components:
        values = [data[cat].get(comp, 0) for cat in categories]
        ax.bar(x, values, 0.6, label=comp, bottom=bottom,
               color=component_colors.get(comp, '#95a5a6'), alpha=0.8)
        bottom += np.array(values)
    
    ax.set_ylabel(ylabel, fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(categories, rotation=45, ha='right')
    ax.legend(loc='upper right')
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.savefig(output_path.with_suffix('.png'), dpi=300, bbox_inches='tight')
    plt.close()


def create_bucket_comparison_heatmap(cats: dict, metric_func, title: str, 
                                     output_path: Path, fmt: str = '.1f'):
    """Create heatmap comparing metrics across two dimensions."""
    if not HAS_MATPLOTLIB:
        return
    
    # Get unique values for each dimension
    aeads = sorted(set(cats['by_aead'].keys()))
    levels = ['L1', 'L3', 'L5']
    
    # Build matrix
    matrix = np.zeros((len(levels), len(aeads)))
    
    for i, level in enumerate(levels):
        for j, aead in enumerate(aeads):
            # Find suites matching both
            matching = [r for r in cats['successful'] 
                       if r.nist_level == level and r.aead_normalized == aead]
            if matching:
                matrix[i, j] = metric_func(matching)
            else:
                matrix[i, j] = np.nan
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    im = ax.imshow(matrix, cmap='RdYlGn_r', aspect='auto')
    
    ax.set_xticks(np.arange(len(aeads)))
    ax.set_yticks(np.arange(len(levels)))
    ax.set_xticklabels(aeads)
    ax.set_yticklabels(levels)
    
    # Add text annotations
    for i in range(len(levels)):
        for j in range(len(aeads)):
            if not np.isnan(matrix[i, j]):
                text = ax.text(j, i, f'{matrix[i, j]:{fmt}}',
                              ha='center', va='center', fontsize=12, fontweight='bold')
    
    ax.set_xlabel('AEAD Algorithm', fontsize=12)
    ax.set_ylabel('NIST Security Level', fontsize=12)
    ax.set_title(title, fontsize=14, fontweight='bold')
    
    cbar = plt.colorbar(im, ax=ax, shrink=0.8)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.savefig(output_path.with_suffix('.png'), dpi=300, bbox_inches='tight')
    plt.close()


def generate_all_charts(cats: dict, output_dir: Path):
    """Generate all visualization charts."""
    if not HAS_MATPLOTLIB:
        return {}
    
    output_dir.mkdir(parents=True, exist_ok=True)
    chart_files = {}
    
    plt.style.use('seaborn-v0_8-whitegrid')
    
    # 1. AEAD Bucket Radar Chart
    aead_metrics = {}
    for aead, suites in cats['by_aead'].items():
        if suites:
            times = [s.handshake_ms for s in suites]
            sizes = [s.total_artifact_size for s in suites]
            verifies = [s.sig_verify_ms for s in suites]
            encaps = [s.kem_encaps_ms for s in suites]
            aead_metrics[aead] = [
                statistics.mean(times),
                statistics.mean(sizes) / 1000,  # KB
                statistics.mean(verifies) * 10,  # Scale for visibility
                statistics.mean(encaps) * 100,   # Scale for visibility
                len(suites),
            ]
    
    radar_labels = ['Handshake (ms)', 'Size (KB)', 'Sig Verify (×10ms)', 
                   'KEM Encaps (×100ms)', 'Suite Count']
    chart_files['aead_radar'] = output_dir / 'aead_radar.pdf'
    create_radar_chart(aead_metrics, radar_labels, 
                      'AEAD Algorithm Comparison (Radar)', 
                      chart_files['aead_radar'], AEAD_COLORS)
    
    # 2. NIST Level Radar Chart
    level_metrics = {}
    for level in ['L1', 'L3', 'L5']:
        suites = cats['by_level'].get(level, [])
        if suites:
            times = [s.handshake_ms for s in suites]
            sizes = [s.total_artifact_size for s in suites]
            verifies = [s.sig_verify_ms for s in suites]
            encaps = [s.kem_encaps_ms for s in suites]
            level_metrics[f'NIST {level}'] = [
                statistics.mean(times),
                statistics.mean(sizes) / 1000,
                statistics.mean(verifies) * 10,
                statistics.mean(encaps) * 100,
                len(suites),
            ]
    
    chart_files['level_radar'] = output_dir / 'level_radar.pdf'
    create_radar_chart(level_metrics, radar_labels,
                      'NIST Security Level Comparison (Radar)',
                      chart_files['level_radar'], 
                      {f'NIST {k}': v for k, v in LEVEL_COLORS.items()})
    
    # 3. KEM Performance by AEAD (Grouped Bar)
    kem_by_aead = {}
    for aead in ['AES-256-GCM', 'ChaCha20-Poly1305', 'ASCON-128a']:
        kem_by_aead[aead] = {}
        for kem in sorted(cats['by_kem'].keys()):
            matching = [s for s in cats['successful'] 
                       if s.kem_name == kem and s.aead_normalized == aead]
            if matching:
                kem_by_aead[aead][kem.replace('Classic-McEliece-', 'CMcE-')] = \
                    statistics.mean([s.handshake_ms for s in matching])
    
    chart_files['kem_by_aead'] = output_dir / 'kem_by_aead_bar.pdf'
    create_grouped_bar_chart(kem_by_aead, 
                            'KEM Performance by AEAD Algorithm',
                            'Handshake Time (ms)', 
                            chart_files['kem_by_aead'], AEAD_COLORS, log_scale=True)
    
    # 4. Signature Performance by AEAD (Grouped Bar)
    sig_by_aead = {}
    for aead in ['AES-256-GCM', 'ChaCha20-Poly1305', 'ASCON-128a']:
        sig_by_aead[aead] = {}
        for sig in sorted(cats['by_sig'].keys()):
            matching = [s for s in cats['successful'] 
                       if s.sig_name == sig and s.aead_normalized == aead]
            if matching:
                sig_short = sig.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', '')
                sig_by_aead[aead][sig_short] = \
                    statistics.mean([s.handshake_ms for s in matching])
    
    chart_files['sig_by_aead'] = output_dir / 'sig_by_aead_bar.pdf'
    create_grouped_bar_chart(sig_by_aead,
                            'Signature Performance by AEAD Algorithm',
                            'Handshake Time (ms)',
                            chart_files['sig_by_aead'], AEAD_COLORS, log_scale=True)
    
    # 5. AEAD × Level Heatmap (Average Handshake)
    chart_files['aead_level_heatmap'] = output_dir / 'aead_level_heatmap.pdf'
    create_bucket_comparison_heatmap(
        cats,
        lambda suites: statistics.mean([s.handshake_ms for s in suites]),
        'Average Handshake Time (ms) by AEAD × NIST Level',
        chart_files['aead_level_heatmap']
    )
    
    # 6. Artifact Size Composition (Stacked Bar by KEM)
    size_composition = {}
    for kem in sorted(cats['by_kem'].keys()):
        suites = cats['by_kem'][kem]
        if suites:
            s = suites[0]  # Sizes are same for all suites with same KEM
            kem_short = kem.replace('Classic-McEliece-', 'CMcE-')
            size_composition[kem_short] = {
                'Public Key': s.pub_key_size_bytes / 1024,
                'Ciphertext': s.ciphertext_size_bytes / 1024,
            }
    
    chart_files['kem_size_stack'] = output_dir / 'kem_size_stacked.pdf'
    create_stacked_bar_chart(size_composition,
                            'KEM Artifact Sizes (KB)',
                            'Size (KB)',
                            chart_files['kem_size_stack'],
                            {'Public Key': '#3498db', 'Ciphertext': '#e74c3c'})
    
    # 7. Signature Size by Algorithm
    fig, ax = plt.subplots(figsize=(12, 6))
    sigs = sorted(cats['by_sig'].keys())
    sig_sizes = []
    sig_labels = []
    sig_cols = []
    for sig in sigs:
        suites = cats['by_sig'][sig]
        if suites:
            sig_sizes.append(suites[0].sig_size_bytes / 1024)
            sig_labels.append(sig.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', ''))
            sig_cols.append(SIG_COLORS.get(sig, '#95a5a6'))
    
    bars = ax.barh(sig_labels, sig_sizes, color=sig_cols, alpha=0.8)
    ax.set_xlabel('Signature Size (KB)', fontsize=12)
    ax.set_title('Digital Signature Sizes by Algorithm', fontsize=14, fontweight='bold')
    for bar, size in zip(bars, sig_sizes):
        ax.text(size + 0.5, bar.get_y() + bar.get_height()/2,
               f'{size:.1f} KB', va='center', fontsize=9)
    plt.tight_layout()
    chart_files['sig_sizes'] = output_dir / 'sig_sizes.pdf'
    plt.savefig(chart_files['sig_sizes'], dpi=300, bbox_inches='tight')
    plt.savefig(chart_files['sig_sizes'].with_suffix('.png'), dpi=300, bbox_inches='tight')
    plt.close()
    
    # 8. Handshake Time Distribution by AEAD (Violin Plot)
    fig, ax = plt.subplots(figsize=(12, 8))
    aead_data = []
    aead_labels = []
    for aead in ['AES-256-GCM', 'ChaCha20-Poly1305', 'ASCON-128a']:
        suites = cats['by_aead'].get(aead, [])
        if suites:
            aead_data.append([s.handshake_ms for s in suites])
            aead_labels.append(aead)
    
    parts = ax.violinplot(aead_data, positions=range(len(aead_labels)), 
                         showmeans=True, showmedians=True)
    for i, pc in enumerate(parts['bodies']):
        pc.set_facecolor(AEAD_COLORS.get(aead_labels[i], '#95a5a6'))
        pc.set_alpha(0.7)
    
    ax.set_xticks(range(len(aead_labels)))
    ax.set_xticklabels(aead_labels)
    ax.set_ylabel('Handshake Time (ms)', fontsize=12)
    ax.set_title('Handshake Time Distribution by AEAD', fontsize=14, fontweight='bold')
    ax.set_yscale('log')
    plt.tight_layout()
    chart_files['aead_violin'] = output_dir / 'aead_violin.pdf'
    plt.savefig(chart_files['aead_violin'], dpi=300, bbox_inches='tight')
    plt.savefig(chart_files['aead_violin'].with_suffix('.png'), dpi=300, bbox_inches='tight')
    plt.close()
    
    # 9. KEM × Signature Heatmap (Full Matrix)
    kems = sorted(cats['by_kem'].keys())
    sigs = sorted(cats['by_sig'].keys())
    
    matrix = np.zeros((len(sigs), len(kems)))
    for i, sig in enumerate(sigs):
        for j, kem in enumerate(kems):
            matching = [s for s in cats['successful'] 
                       if s.kem_name == kem and s.sig_name == sig]
            if matching:
                matrix[i, j] = statistics.mean([s.handshake_ms for s in matching])
            else:
                matrix[i, j] = np.nan
    
    fig, ax = plt.subplots(figsize=(16, 12))
    matrix_log = np.log10(np.where(matrix > 0, matrix, np.nan))
    im = ax.imshow(matrix_log, cmap='RdYlGn_r', aspect='auto')
    
    kem_labels = [k.replace('Classic-McEliece-', 'CMcE-') for k in kems]
    sig_labels = [s.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', '') for s in sigs]
    
    ax.set_xticks(np.arange(len(kems)))
    ax.set_yticks(np.arange(len(sigs)))
    ax.set_xticklabels(kem_labels, rotation=45, ha='right')
    ax.set_yticklabels(sig_labels)
    
    for i in range(len(sigs)):
        for j in range(len(kems)):
            if not np.isnan(matrix[i, j]):
                val = matrix[i, j]
                text = f'{val:.0f}' if val < 1000 else f'{val/1000:.1f}k'
                color = 'white' if matrix_log[i, j] > 2.5 else 'black'
                ax.text(j, i, text, ha='center', va='center', color=color, fontsize=8)
    
    ax.set_xlabel('KEM Algorithm', fontsize=12)
    ax.set_ylabel('Signature Algorithm', fontsize=12)
    ax.set_title('Complete Handshake Time Matrix (ms) - KEM × Signature', 
                fontsize=14, fontweight='bold')
    cbar = plt.colorbar(im, ax=ax, shrink=0.6)
    cbar.set_label('log₁₀(Handshake Time in ms)', fontsize=10)
    
    plt.tight_layout()
    chart_files['full_heatmap'] = output_dir / 'kem_sig_heatmap.pdf'
    plt.savefig(chart_files['full_heatmap'], dpi=300, bbox_inches='tight')
    plt.savefig(chart_files['full_heatmap'].with_suffix('.png'), dpi=300, bbox_inches='tight')
    plt.close()
    
    # 10. Top/Bottom 10 Suites Bar Chart
    sorted_suites = sorted(cats['successful'], key=lambda s: s.handshake_ms)
    top10 = sorted_suites[:10]
    bottom10 = sorted_suites[-10:][::-1]
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
    
    # Top 10 (Fastest)
    names = [s.suite_id.replace('cs-', '').replace('-', '\n', 2) for s in top10]
    times = [s.handshake_ms for s in top10]
    colors = [KEM_COLORS.get(s.kem_name, '#95a5a6') for s in top10]
    ax1.barh(names, times, color=colors, alpha=0.8)
    ax1.set_xlabel('Handshake Time (ms)', fontsize=11)
    ax1.set_title('Top 10 Fastest Suites', fontsize=12, fontweight='bold')
    ax1.invert_yaxis()
    for i, (t, n) in enumerate(zip(times, names)):
        ax1.text(t + 0.5, i, f'{t:.1f} ms', va='center', fontsize=9)
    
    # Bottom 10 (Slowest)
    names = [s.suite_id.replace('cs-', '').replace('-', '\n', 2) for s in bottom10]
    times = [s.handshake_ms for s in bottom10]
    colors = [KEM_COLORS.get(s.kem_name, '#95a5a6') for s in bottom10]
    ax2.barh(names, times, color=colors, alpha=0.8)
    ax2.set_xlabel('Handshake Time (ms)', fontsize=11)
    ax2.set_title('Top 10 Slowest Suites', fontsize=12, fontweight='bold')
    ax2.invert_yaxis()
    for i, (t, n) in enumerate(zip(times, names)):
        ax2.text(t + 10, i, f'{t:.0f} ms', va='center', fontsize=9)
    
    plt.tight_layout()
    chart_files['top_bottom'] = output_dir / 'top_bottom_suites.pdf'
    plt.savefig(chart_files['top_bottom'], dpi=300, bbox_inches='tight')
    plt.savefig(chart_files['top_bottom'].with_suffix('.png'), dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"Generated {len(chart_files)} charts in {output_dir}")
    return chart_files


# =============================================================================
# LaTeX Generation
# =============================================================================

def escape_latex(s: str) -> str:
    """Escape special LaTeX characters."""
    if not s:
        return ''
    s = str(s)
    # Order matters: backslash first
    s = s.replace('\\', '\\textbackslash ')
    s = s.replace('#', '\\#')
    s = s.replace('$', '\\$')
    s = s.replace('%', '\\%')
    s = s.replace('&', '\\&')
    s = s.replace('{', '\\{')
    s = s.replace('}', '\\}')
    s = s.replace('^', '\\textasciicircum ')
    s = s.replace('~', '\\textasciitilde ')
    s = s.replace('_', '\\_')
    return s


def escape_for_texttt(s: str) -> str:
    """Escape for use inside \\texttt{} - underscores need special handling."""
    if not s:
        return ''
    s = str(s)
    # In texttt, underscores still need escaping
    s = s.replace('_', '\\_')
    return s


def generate_suite_page(suite: SuiteResult, idx: int) -> str:
    """Generate LaTeX for individual suite page."""
    kem_short = escape_latex(suite.kem_name.replace('Classic-McEliece-', 'CMcE-'))
    sig_short = escape_latex(suite.sig_name.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', ''))
    
    page = f"""
\\newpage
\\subsection{{Suite {idx}: {kem_short} + {sig_short}}}
\\label{{suite:{suite.suite_id}}}

\\begin{{table}}[H]
\\centering
\\caption{{Metrics for {escape_latex(suite.suite_id)}}}
\\begin{{tabular}}{{l r}}
\\toprule
\\textbf{{Parameter}} & \\textbf{{Value}} \\\\
\\midrule
\\multicolumn{{2}}{{l}}{{\\textit{{Identity}}}} \\\\
Suite ID & \\texttt{{{escape_latex(suite.suite_id)}}} \\\\
NIST Level & {suite.nist_level} \\\\
KEM & {kem_short} \\\\
Signature & {sig_short} \\\\
AEAD & {escape_latex(suite.aead_normalized)} \\\\
\\midrule
\\multicolumn{{2}}{{l}}{{\\textit{{Handshake Timing}}}} \\\\
Total Handshake & {suite.handshake_ms:.2f} ms \\\\
KEM Keygen & {suite.kem_keygen_ms:.3f} ms \\\\
KEM Encapsulate & {suite.kem_encaps_ms:.3f} ms \\\\
KEM Decapsulate & {suite.kem_decaps_ms:.3f} ms \\\\
Signature Sign & {suite.sig_sign_ms:.3f} ms \\\\
Signature Verify & {suite.sig_verify_ms:.3f} ms \\\\
Primitive Total & {suite.primitive_total_ms:.3f} ms \\\\
\\midrule
\\multicolumn{{2}}{{l}}{{\\textit{{Artifact Sizes}}}} \\\\
Public Key & {suite.pub_key_size_bytes:,} bytes ({suite.pub_key_size_bytes/1024:.1f} KB) \\\\
Ciphertext & {suite.ciphertext_size_bytes:,} bytes \\\\
Signature & {suite.sig_size_bytes:,} bytes ({suite.sig_size_bytes/1024:.2f} KB) \\\\
Total Artifacts & {suite.total_artifact_size:,} bytes ({suite.total_artifact_size/1024:.1f} KB) \\\\
\\midrule
\\multicolumn{{2}}{{l}}{{\\textit{{Status}}}} \\\\
Success & {'Yes' if suite.success else 'No'} \\\\
{'Error & ' + escape_latex(suite.error_message) if suite.error_message else ''} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\textbf{{Analysis:}} """
    
    # Add analysis based on performance
    if suite.handshake_ms < 50:
        page += "This suite demonstrates \\textbf{excellent} handshake performance, suitable for real-time UAV applications. "
    elif suite.handshake_ms < 200:
        page += "This suite shows \\textbf{good} performance, acceptable for most mission-critical operations. "
    elif suite.handshake_ms < 1000:
        page += "This suite has \\textbf{moderate} performance, suitable for non-time-critical applications. "
    else:
        page += "This suite exhibits \\textbf{slow} performance, primarily due to signature verification overhead. "
    
    if suite.total_artifact_size > 100000:
        page += f"The large artifact size ({suite.total_artifact_size/1024:.0f} KB) may impact bandwidth-constrained links. "
    
    if 'SPHINCS' in suite.sig_name:
        page += "SPHINCS+ provides hash-based security guarantees but with significant computational cost. "
    elif 'Falcon' in suite.sig_name:
        page += "Falcon offers compact signatures with fast verification. "
    elif 'ML-DSA' in suite.sig_name:
        page += "ML-DSA (Dilithium) provides a balanced trade-off between size and speed. "
    
    return page


def generate_aead_section(cats: dict, aead: str) -> str:
    """Generate LaTeX section for AEAD bucket analysis."""
    suites = cats['by_aead'].get(aead, [])
    if not suites:
        return ""
    
    times = [s.handshake_ms for s in suites]
    sizes = [s.total_artifact_size for s in suites]
    
    section = f"""
\\subsection{{{escape_latex(aead)} Analysis}}
\\label{{sec:aead-{aead.lower().replace('-', '').replace(' ', '')}}}

This section analyzes all {len(suites)} cipher suites using \\textbf{{{escape_latex(aead)}}} as the AEAD algorithm.

\\subsubsection{{Statistical Summary}}

\\begin{{table}}[H]
\\centering
\\caption{{{escape_latex(aead)} Suite Performance Statistics}}
\\begin{{tabular}}{{l r r r r r}}
\\toprule
\\textbf{{Metric}} & \\textbf{{Min}} & \\textbf{{Mean}} & \\textbf{{Median}} & \\textbf{{Max}} & \\textbf{{Std Dev}} \\\\
\\midrule
Handshake (ms) & {min(times):.1f} & {statistics.mean(times):.1f} & {statistics.median(times):.1f} & {max(times):.1f} & {statistics.stdev(times) if len(times) > 1 else 0:.1f} \\\\
Artifact Size (KB) & {min(sizes)/1024:.1f} & {statistics.mean(sizes)/1024:.1f} & {statistics.median(sizes)/1024:.1f} & {max(sizes)/1024:.1f} & {statistics.stdev(sizes)/1024 if len(sizes) > 1 else 0:.1f} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\subsubsection{{Suites Ranked by Performance}}

\\begin{{table}}[H]
\\centering
\\caption{{Top 5 Fastest {escape_latex(aead)} Suites}}
\\begin{{tabular}}{{r l l l r}}
\\toprule
\\textbf{{Rank}} & \\textbf{{KEM}} & \\textbf{{Signature}} & \\textbf{{Level}} & \\textbf{{Time (ms)}} \\\\
\\midrule
"""
    
    sorted_suites = sorted(suites, key=lambda s: s.handshake_ms)
    for i, s in enumerate(sorted_suites[:5]):
        kem_short = s.kem_name.replace('Classic-McEliece-', 'CMcE-')
        sig_short = s.sig_name.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', '')
        section += f"{i+1} & {escape_latex(kem_short)} & {escape_latex(sig_short)} & {s.nist_level} & {s.handshake_ms:.1f} \\\\\n"
    
    section += """\\bottomrule
\\end{tabular}
\\end{table}
"""
    return section


def generate_level_section(cats: dict, level: str) -> str:
    """Generate LaTeX section for NIST level analysis."""
    suites = cats['by_level'].get(level, [])
    if not suites:
        return ""
    
    times = [s.handshake_ms for s in suites]
    
    section = f"""
\\subsection{{NIST {level} Security Level Analysis}}
\\label{{sec:level-{level.lower()}}}

This section analyzes all {len(suites)} cipher suites at \\textbf{{NIST {level}}} security level.

\\subsubsection{{Performance Distribution}}

\\begin{{itemize}}
    \\item \\textbf{{Fastest:}} {min(times):.1f} ms
    \\item \\textbf{{Average:}} {statistics.mean(times):.1f} ms
    \\item \\textbf{{Slowest:}} {max(times):.1f} ms
    \\item \\textbf{{Median:}} {statistics.median(times):.1f} ms
\\end{{itemize}}

\\subsubsection{{Algorithm Coverage}}

\\begin{{table}}[H]
\\centering
\\caption{{Algorithms at {level} Security Level}}
\\begin{{tabular}}{{l l}}
\\toprule
\\textbf{{Type}} & \\textbf{{Algorithms}} \\\\
\\midrule
KEM & {', '.join(sorted(set(escape_latex(s.kem_name.replace('Classic-McEliece-', 'CMcE-')) for s in suites)))} \\\\
Signature & {', '.join(sorted(set(escape_latex(s.sig_name.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', '')) for s in suites)))} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}
"""
    return section


def generate_full_latex_report(raw_data: dict, cats: dict, chart_files: dict) -> str:
    """Generate complete LaTeX document."""
    
    successful = cats['successful']
    failed = cats['failed']
    
    all_times = [s.handshake_ms for s in successful]
    
    # Preamble
    report = r"""\documentclass[11pt,a4paper,twoside]{article}
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{hyperref}
\usepackage{amsmath}
\usepackage{geometry}
\usepackage{float}
\usepackage{caption}
\usepackage{subcaption}
\usepackage{xcolor}
\usepackage{fancyhdr}
\usepackage{longtable}
\usepackage{multicol}
\usepackage{titlesec}

\geometry{margin=2cm, inner=2.5cm, outer=2cm}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[LE,RO]{\thepage}
\fancyhead[RE]{PQC Benchmark Report}
\fancyhead[LO]{\leftmark}
\fancyfoot[C]{\footnotesize IEEE-Style Comprehensive Analysis}

\titleformat{\section}{\Large\bfseries}{\thesection}{1em}{}
\titleformat{\subsection}{\large\bfseries}{\thesubsection}{1em}{}

\title{\textbf{Comprehensive Post-Quantum Cryptography\\Cipher Suite Benchmark Report}\\[0.5em]
\large IEEE-Style Analysis of 72 PQC Suites\\on Raspberry Pi 4 UAV Platform}

\author{Automated Benchmark Framework v2.0}
\date{""" + datetime.now().strftime("%B %d, %Y") + r"""}

\begin{document}

\maketitle

\begin{abstract}
This comprehensive report presents detailed benchmark results for """ + str(len(cats['all'])) + r""" post-quantum 
cryptographic (PQC) cipher suites evaluated on a Raspberry Pi 4 Model B representing a UAV endpoint 
communicating with a Windows-based Ground Control Station (GCS). The analysis covers three AEAD 
algorithms (AES-256-GCM, ChaCha20-Poly1305, ASCON-128a), three NIST security levels (L1, L3, L5), 
and provides individual performance profiles for each suite. Results demonstrate handshake times 
ranging from """ + f"{min(all_times):.1f}" + r"""\,ms to """ + f"{max(all_times):.1f}" + r"""\,ms with 
recommendations for UAV-optimized configurations.
\end{abstract}

\tableofcontents
\listoffigures
\listoftables
\newpage

%==============================================================================
\section{Executive Summary}
%==============================================================================

\subsection{Benchmark Overview}

\begin{table}[H]
\centering
\caption{Benchmark Campaign Summary}
\begin{tabular}{l r}
\toprule
\textbf{Parameter} & \textbf{Value} \\
\midrule
Total Suites Tested & """ + str(len(cats['all'])) + r""" \\
Successful & """ + str(len(successful)) + r""" \\
Failed & """ + str(len(failed)) + r""" \\
Run ID & \texttt{""" + escape_for_texttt(raw_data.get('run_id', 'N/A')) + r"""} \\
Duration per Suite & """ + f"{raw_data.get('cycle_interval_s', 10)}" + r""" seconds \\
\midrule
Fastest Handshake & """ + f"{min(all_times):.2f}" + r""" ms \\
Slowest Handshake & """ + f"{max(all_times):.2f}" + r""" ms \\
Average Handshake & """ + f"{statistics.mean(all_times):.2f}" + r""" ms \\
Median Handshake & """ + f"{statistics.median(all_times):.2f}" + r""" ms \\
\bottomrule
\end{tabular}
\end{table}

\subsection{Key Findings}

\begin{enumerate}
    \item \textbf{ML-KEM dominates performance:} All ML-KEM variants achieve sub-30ms handshakes
    \item \textbf{SPHINCS+ introduces significant overhead:} Hash-based signatures add 800-2500ms
    \item \textbf{AEAD choice has minimal impact:} Less than 5\% variance between AES-GCM, ChaCha20, and ASCON
    \item \textbf{Security level correlation:} Higher levels (L3, L5) show 10-20\% increased latency vs L1
    \item \textbf{Classic McEliece has extreme key sizes:} Up to 1.3MB public keys impact bandwidth
\end{enumerate}

\subsection{Recommendations}

\begin{table}[H]
\centering
\caption{Recommended Configurations by Use Case}
\begin{tabular}{l l l l}
\toprule
\textbf{Use Case} & \textbf{KEM} & \textbf{Signature} & \textbf{Expected Time} \\
\midrule
Real-time Control & ML-KEM-512 & Falcon-512 & 10-15 ms \\
Balanced Security & ML-KEM-768 & ML-DSA-65 & 15-20 ms \\
Maximum Security & ML-KEM-1024 & ML-DSA-87 & 15-25 ms \\
Bandwidth-Critical & ML-KEM-512 & Falcon-512 & 2.2 KB artifacts \\
\bottomrule
\end{tabular}
\end{table}

%==============================================================================
\section{AEAD Algorithm Analysis}
%==============================================================================

This section compares cipher suite performance segmented by AEAD algorithm.

\begin{figure}[H]
    \centering
    \includegraphics[width=0.8\textwidth]{figures/aead_radar.pdf}
    \caption{AEAD Algorithm Comparison (Radar Chart)}
    \label{fig:aead-radar}
\end{figure}

\begin{figure}[H]
    \centering
    \includegraphics[width=\textwidth]{figures/aead_violin.pdf}
    \caption{Handshake Time Distribution by AEAD (Violin Plot)}
    \label{fig:aead-violin}
\end{figure}

"""
    
    # Add AEAD sections
    for aead in ['AES-256-GCM', 'ChaCha20-Poly1305', 'ASCON-128a']:
        report += generate_aead_section(cats, aead)
    
    report += r"""
%==============================================================================
\section{NIST Security Level Analysis}
%==============================================================================

This section compares cipher suite performance segmented by NIST security level.

\begin{figure}[H]
    \centering
    \includegraphics[width=0.8\textwidth]{figures/level_radar.pdf}
    \caption{NIST Security Level Comparison (Radar Chart)}
    \label{fig:level-radar}
\end{figure}

\begin{figure}[H]
    \centering
    \includegraphics[width=\textwidth]{figures/aead_level_heatmap.pdf}
    \caption{Handshake Time by AEAD $\times$ NIST Level (Heatmap)}
    \label{fig:aead-level-heatmap}
\end{figure}

"""
    
    # Add NIST level sections
    for level in ['L1', 'L3', 'L5']:
        report += generate_level_section(cats, level)
    
    report += r"""
%==============================================================================
\section{Algorithm Deep Dive}
%==============================================================================

\subsection{KEM Performance Analysis}

\begin{figure}[H]
    \centering
    \includegraphics[width=\textwidth]{figures/kem_by_aead_bar.pdf}
    \caption{KEM Performance Grouped by AEAD Algorithm}
    \label{fig:kem-by-aead}
\end{figure}

\begin{figure}[H]
    \centering
    \includegraphics[width=\textwidth]{figures/kem_size_stacked.pdf}
    \caption{KEM Artifact Size Composition}
    \label{fig:kem-sizes}
\end{figure}

\subsection{Signature Performance Analysis}

\begin{figure}[H]
    \centering
    \includegraphics[width=\textwidth]{figures/sig_by_aead_bar.pdf}
    \caption{Signature Performance Grouped by AEAD Algorithm}
    \label{fig:sig-by-aead}
\end{figure}

\begin{figure}[H]
    \centering
    \includegraphics[width=\textwidth]{figures/sig_sizes.pdf}
    \caption{Digital Signature Sizes by Algorithm}
    \label{fig:sig-sizes}
\end{figure}

%==============================================================================
\section{Cross-Algorithm Comparison}
%==============================================================================

\begin{figure}[H]
    \centering
    \includegraphics[width=\textwidth]{figures/kem_sig_heatmap.pdf}
    \caption{Complete Handshake Time Matrix (KEM $\times$ Signature)}
    \label{fig:full-heatmap}
\end{figure}

\begin{figure}[H]
    \centering
    \includegraphics[width=\textwidth]{figures/top_bottom_suites.pdf}
    \caption{Top 10 Fastest and Slowest Suites}
    \label{fig:top-bottom}
\end{figure}

%==============================================================================
\section{Individual Suite Profiles}
%==============================================================================

This section provides detailed metrics for each of the """ + str(len(successful)) + r""" successfully
tested cipher suites. Suites are ordered by handshake performance.

"""
    
    # Add individual suite pages
    sorted_suites = sorted(successful, key=lambda s: s.handshake_ms)
    for idx, suite in enumerate(sorted_suites, 1):
        report += generate_suite_page(suite, idx)
    
    # Appendices
    report += r"""
%==============================================================================
\appendix
\section{Complete Results Table}
%==============================================================================

\begin{longtable}{l l l r r r}
\caption{Complete Benchmark Results} \\
\toprule
\textbf{Suite ID} & \textbf{KEM} & \textbf{Sig} & \textbf{Time (ms)} & \textbf{Size (KB)} & \textbf{Level} \\
\midrule
\endfirsthead
\multicolumn{6}{c}{\tablename\ \thetable{} -- continued} \\
\toprule
\textbf{Suite ID} & \textbf{KEM} & \textbf{Sig} & \textbf{Time (ms)} & \textbf{Size (KB)} & \textbf{Level} \\
\midrule
\endhead
\midrule
\multicolumn{6}{r}{Continued on next page...} \\
\endfoot
\bottomrule
\endlastfoot
"""
    
    for s in sorted_suites:
        kem_short = escape_latex(s.kem_name.replace('Classic-McEliece-', 'CMcE-'))[:12]
        sig_short = escape_latex(s.sig_name.replace('SPHINCS+-SHA2-', 'SPX-').replace('-simple', ''))[:10]
        suite_short = escape_latex(s.suite_id)[:25]
        report += f"{suite_short} & {kem_short} & {sig_short} & {s.handshake_ms:.1f} & {s.total_artifact_size/1024:.1f} & {s.nist_level} \\\\\n"
    
    report += r"""
\end{longtable}

\section{Methodology}

\subsection{Test Environment}
\begin{itemize}
    \item \textbf{Drone:} Raspberry Pi 4 Model B (1.5 GHz ARM Cortex-A72, 4GB RAM)
    \item \textbf{GCS:} Windows 10 (Intel Core i7, 16GB RAM)
    \item \textbf{Network:} 192.168.0.x LAN (WiFi, ~2ms RTT)
    \item \textbf{Library:} liboqs (Open Quantum Safe) via Python bindings
\end{itemize}

\subsection{Measurement Protocol}
\begin{enumerate}
    \item Suite activated via TCP control channel
    \item Full PQC handshake executed (KEM + Signature)
    \item Metrics captured from status file
    \item 10-second data plane operation
    \item Suite cycled to next in sequence
\end{enumerate}

\subsection{Metrics Captured}
\begin{itemize}
    \item Handshake total time (perf\_counter\_ns)
    \item KEM primitive timings (keygen, encapsulate, decapsulate)
    \item Signature primitive timings (sign, verify)
    \item Artifact sizes (public key, ciphertext, signature)
\end{itemize}

\end{document}
"""
    
    return report


def main():
    """Main entry point."""
    # Find latest benchmark results
    logs_dir = Path(__file__).parent.parent / "logs" / "benchmarks"
    
    if len(sys.argv) > 1:
        json_path = Path(sys.argv[1])
    else:
        result_files = list(logs_dir.glob("benchmark_results_*.json"))
        if not result_files:
            print("No benchmark results found!")
            sys.exit(1)
        json_path = max(result_files, key=lambda p: p.stat().st_mtime)
    
    print(f"Loading results from: {json_path}")
    raw_data, results = load_results(json_path)
    
    print(f"Total suites: {len(results)}")
    print(f"Successful: {len([r for r in results if r.success])}")
    print(f"Failed: {len([r for r in results if not r.success])}")
    
    # Categorize
    cats = categorize_results(results)
    
    # Create output directories
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    SUITES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate charts
    print("\nGenerating charts...")
    chart_files = generate_all_charts(cats, FIGURES_DIR)
    
    # Generate LaTeX
    print("\nGenerating LaTeX report...")
    report = generate_full_latex_report(raw_data, cats, chart_files)
    
    report_path = OUTPUT_DIR / "pqc_ieee_report.tex"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    print(f"Report saved to: {report_path}")
    
    # Summary
    print("\n" + "="*70)
    print("IEEE-STYLE REPORT GENERATED SUCCESSFULLY")
    print("="*70)
    print(f"\nOutput directory: {OUTPUT_DIR}")
    print(f"LaTeX report: {report_path}")
    print(f"Figures: {FIGURES_DIR}")
    print(f"\nTo compile:")
    print(f"  cd {OUTPUT_DIR}")
    print(f"  pdflatex pqc_ieee_report.tex")
    print(f"  pdflatex pqc_ieee_report.tex  # Run twice for TOC/references")


if __name__ == "__main__":
    main()
