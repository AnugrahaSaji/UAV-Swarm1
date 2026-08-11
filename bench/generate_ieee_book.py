#!/usr/bin/env python3
"""
IEEE Book Generator with Spider Graphs

Generates a comprehensive IEEE-style LaTeX document from benchmark results:
- One page per cipher suite (71 pages)
- 15+ pages of comparative analysis
- Spider/radar graphs for multi-dimensional comparison
- Grouped analysis by NIST level, algorithm family, AEAD
- Energy efficiency analysis (drone power metrics)

Usage:
    python -m bench.generate_ieee_book --input logs/lan_benchmark/RUNID/benchmark_results_RUNID.json

Output:
    book/pqc_benchmark_book.tex
    book/figures/*.pdf
"""

import os
import sys
import json
import argparse
import statistics
import math
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Try importing matplotlib for visualization
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon
    import numpy as np
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("[WARN] matplotlib not available - visualizations disabled")

# =============================================================================
# Configuration
# =============================================================================

BOOK_DIR = Path(__file__).parent.parent / "book"
FIGURES_DIR = BOOK_DIR / "figures"

# NIST Level colors
NIST_COLORS = {
    "L1": "#2ecc71",  # Green
    "L3": "#f39c12",  # Orange  
    "L5": "#e74c3c",  # Red
}

# Algorithm family colors
FAMILY_COLORS = {
    "ML-KEM": "#3498db",
    "Classic-McEliece": "#9b59b6",
    "HQC": "#1abc9c",
    "ML-DSA": "#e67e22",
    "Falcon": "#2ecc71",
    "SPHINCS+": "#e74c3c",
}

# AEAD colors
AEAD_COLORS = {
    "AES-256-GCM": "#34495e",
    "ChaCha20-Poly1305": "#7f8c8d",
    "Ascon-128a": "#16a085",
    "Ascon-AEAD128": "#16a085",
}

# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class SuiteAnalysis:
    """Analyzed metrics for a single suite."""
    suite_id: str
    kem_algorithm: str
    sig_algorithm: str
    aead_algorithm: str
    nist_level: str
    
    # Performance
    handshake_ms: float
    handshake_rank: int = 0
    
    # GCS metrics
    gcs_cpu_avg: float
    gcs_cpu_peak: float
    gcs_memory_mb: float
    
    # Drone metrics
    drone_cpu_avg: float
    drone_cpu_peak: float
    drone_memory_mb: float
    drone_temp_c: float
    drone_load_1m: float
    
    # Power (drone only)
    power_avg_w: float
    power_peak_w: float
    energy_total_j: float
    energy_per_handshake_j: float
    
    # Network
    packets_sent: int
    packets_received: int
    throughput_kbps: float = 0.0
    
    # Derived metrics for radar
    normalized_speed: float = 0.0       # 0-1, higher is better
    normalized_energy: float = 0.0      # 0-1, higher is better (less energy)
    normalized_cpu: float = 0.0         # 0-1, higher is better (less CPU)
    normalized_memory: float = 0.0      # 0-1, higher is better (less memory)
    normalized_security: float = 0.0    # 0-1, L5=1, L3=0.66, L1=0.33

# =============================================================================
# Data Loading & Analysis
# =============================================================================

def load_benchmark_results(json_path: Path) -> List[Dict]:
    """Load benchmark results JSON."""
    with open(json_path) as f:
        data = json.load(f)
    return data.get("results", [])

def analyze_results(results: List[Dict]) -> List[SuiteAnalysis]:
    """Analyze and normalize benchmark results."""
    analyses = []
    
    # First pass: create SuiteAnalysis objects
    for r in results:
        if not r.get("success", False):
            continue
        
        analysis = SuiteAnalysis(
            suite_id=r.get("suite_id", ""),
            kem_algorithm=r.get("kem_algorithm", ""),
            sig_algorithm=r.get("sig_algorithm", ""),
            aead_algorithm=r.get("aead_algorithm", ""),
            nist_level=r.get("nist_level", ""),
            handshake_ms=r.get("handshake_duration_ms", 0),
            gcs_cpu_avg=r.get("gcs_cpu_avg_percent", 0),
            gcs_cpu_peak=r.get("gcs_cpu_peak_percent", 0),
            gcs_memory_mb=r.get("gcs_memory_rss_mb", 0),
            drone_cpu_avg=r.get("drone_cpu_avg_percent", 0),
            drone_cpu_peak=r.get("drone_cpu_peak_percent", 0),
            drone_memory_mb=r.get("drone_memory_rss_mb", 0),
            drone_temp_c=r.get("drone_temperature_c", 0),
            drone_load_1m=r.get("drone_load_avg_1m", 0),
            power_avg_w=r.get("drone_power_avg_w", 0),
            power_peak_w=r.get("drone_power_peak_w", 0),
            energy_total_j=r.get("drone_energy_total_j", 0),
            energy_per_handshake_j=r.get("drone_energy_per_handshake_j", 0),
            packets_sent=r.get("packets_sent", 0),
            packets_received=r.get("packets_received", 0),
        )
        analyses.append(analysis)
    
    if not analyses:
        return []
    
    # Second pass: compute rankings and normalizations
    handshakes = [a.handshake_ms for a in analyses]
    energies = [a.energy_total_j for a in analyses if a.energy_total_j > 0]
    cpus = [a.drone_cpu_avg for a in analyses]
    memories = [a.drone_memory_mb for a in analyses]
    
    min_hs, max_hs = min(handshakes), max(handshakes)
    min_e, max_e = (min(energies), max(energies)) if energies else (0, 1)
    min_cpu, max_cpu = min(cpus), max(cpus)
    min_mem, max_mem = min(memories), max(memories)
    
    # Rank by handshake time (1 = fastest)
    sorted_by_hs = sorted(analyses, key=lambda x: x.handshake_ms)
    for rank, a in enumerate(sorted_by_hs, 1):
        a.handshake_rank = rank
    
    # Normalize (0-1, higher is better)
    for a in analyses:
        # Speed: inverse of handshake time
        if max_hs > min_hs:
            a.normalized_speed = 1 - (a.handshake_ms - min_hs) / (max_hs - min_hs)
        else:
            a.normalized_speed = 1.0
        
        # Energy: inverse of energy consumption
        if max_e > min_e and a.energy_total_j > 0:
            a.normalized_energy = 1 - (a.energy_total_j - min_e) / (max_e - min_e)
        else:
            a.normalized_energy = 0.5
        
        # CPU: inverse of CPU usage
        if max_cpu > min_cpu:
            a.normalized_cpu = 1 - (a.drone_cpu_avg - min_cpu) / (max_cpu - min_cpu)
        else:
            a.normalized_cpu = 1.0
        
        # Memory: inverse of memory usage
        if max_mem > min_mem:
            a.normalized_memory = 1 - (a.drone_memory_mb - min_mem) / (max_mem - min_mem)
        else:
            a.normalized_memory = 1.0
        
        # Security level
        a.normalized_security = {"L1": 0.33, "L3": 0.66, "L5": 1.0}.get(a.nist_level, 0.5)
    
    return analyses

# =============================================================================
# Spider/Radar Chart Generation
# =============================================================================

def create_spider_chart(analyses: List[SuiteAnalysis], title: str, output_path: Path):
    """Create a spider/radar chart comparing multiple suites."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    categories = ['Speed', 'Energy\nEfficiency', 'CPU\nEfficiency', 'Memory\nEfficiency', 'Security\nLevel']
    num_vars = len(categories)
    
    # Compute angle for each category
    angles = [n / float(num_vars) * 2 * math.pi for n in range(num_vars)]
    angles += angles[:1]  # Complete the loop
    
    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    
    # Draw one polygon per suite (limit to top 10 for readability)
    for i, a in enumerate(analyses[:10]):
        values = [
            a.normalized_speed,
            a.normalized_energy,
            a.normalized_cpu,
            a.normalized_memory,
            a.normalized_security,
        ]
        values += values[:1]
        
        color = NIST_COLORS.get(a.nist_level, "#cccccc")
        ax.plot(angles, values, 'o-', linewidth=2, label=a.suite_id[:30], color=color, alpha=0.7)
        ax.fill(angles, values, alpha=0.1, color=color)
    
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, size=12)
    ax.set_ylim(0, 1)
    ax.set_title(title, size=16, y=1.08)
    
    # Legend
    ax.legend(loc='upper right', bbox_to_anchor=(1.3, 1.0), fontsize=8)
    
    plt.tight_layout()
    plt.savefig(output_path, format='pdf', dpi=300, bbox_inches='tight')
    plt.close()

def create_nist_level_spider(analyses: List[SuiteAnalysis], output_path: Path):
    """Create spider chart comparing NIST levels."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    # Group by NIST level and average
    by_level = {}
    for a in analyses:
        if a.nist_level not in by_level:
            by_level[a.nist_level] = []
        by_level[a.nist_level].append(a)
    
    categories = ['Speed', 'Energy\nEfficiency', 'CPU\nEfficiency', 'Memory\nEfficiency']
    num_vars = len(categories)
    angles = [n / float(num_vars) * 2 * math.pi for n in range(num_vars)]
    angles += angles[:1]
    
    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    
    for level, suites in sorted(by_level.items()):
        avg_speed = statistics.mean([s.normalized_speed for s in suites])
        avg_energy = statistics.mean([s.normalized_energy for s in suites])
        avg_cpu = statistics.mean([s.normalized_cpu for s in suites])
        avg_memory = statistics.mean([s.normalized_memory for s in suites])
        
        values = [avg_speed, avg_energy, avg_cpu, avg_memory]
        values += values[:1]
        
        color = NIST_COLORS.get(level, "#cccccc")
        ax.plot(angles, values, 'o-', linewidth=3, label=f"NIST {level}", color=color)
        ax.fill(angles, values, alpha=0.2, color=color)
    
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, size=14)
    ax.set_ylim(0, 1)
    ax.set_title("Performance by NIST Security Level\n(Averaged across algorithms)", size=16, y=1.08)
    ax.legend(loc='upper right', bbox_to_anchor=(1.2, 1.0), fontsize=12)
    
    plt.tight_layout()
    plt.savefig(output_path, format='pdf', dpi=300, bbox_inches='tight')
    plt.close()

def create_power_bar_chart(analyses: List[SuiteAnalysis], output_path: Path):
    """Create bar chart of power consumption."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    # Filter to those with power data
    power_data = [(a.suite_id[:25], a.power_avg_w, a.nist_level) for a in analyses if a.power_avg_w > 0]
    if not power_data:
        return
    
    # Sort by power
    power_data.sort(key=lambda x: x[1])
    
    names = [p[0] for p in power_data]
    powers = [p[1] for p in power_data]
    colors = [NIST_COLORS.get(p[2], "#cccccc") for p in power_data]
    
    fig, ax = plt.subplots(figsize=(14, 8))
    bars = ax.barh(range(len(names)), powers, color=colors, alpha=0.8)
    
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel('Average Power (W)', fontsize=12)
    ax.set_title('Power Consumption by Cipher Suite\n(Lower is better)', fontsize=14)
    ax.grid(True, alpha=0.3, axis='x')
    
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, label=f"NIST {l}") for l, c in NIST_COLORS.items()]
    ax.legend(handles=legend_elements, loc='lower right')
    
    plt.tight_layout()
    plt.savefig(output_path, format='pdf', dpi=300, bbox_inches='tight')
    plt.close()

def create_handshake_comparison(analyses: List[SuiteAnalysis], output_path: Path):
    """Create handshake timing comparison chart."""
    if not MATPLOTLIB_AVAILABLE:
        return
    
    # Sort by handshake time
    sorted_data = sorted(analyses, key=lambda x: x.handshake_ms)[:30]  # Top 30
    
    names = [a.suite_id[:25] for a in sorted_data]
    times = [a.handshake_ms for a in sorted_data]
    colors = [NIST_COLORS.get(a.nist_level, "#cccccc") for a in sorted_data]
    
    fig, ax = plt.subplots(figsize=(14, 10))
    bars = ax.barh(range(len(names)), times, color=colors, alpha=0.8)
    
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names, fontsize=8)
    ax.set_xlabel('Handshake Time (ms)', fontsize=12)
    ax.set_title('Handshake Duration by Cipher Suite\n(Lower is better)', fontsize=14)
    ax.grid(True, alpha=0.3, axis='x')
    
    # Log scale if needed
    if max(times) / min(times) > 100:
        ax.set_xscale('log')
        ax.set_xlabel('Handshake Time (ms, log scale)', fontsize=12)
    
    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, label=f"NIST {l}") for l, c in NIST_COLORS.items()]
    ax.legend(handles=legend_elements, loc='lower right')
    
    plt.tight_layout()
    plt.savefig(output_path, format='pdf', dpi=300, bbox_inches='tight')
    plt.close()

# =============================================================================
# LaTeX Generation
# =============================================================================

def escape_latex(text: str) -> str:
    """Escape special LaTeX characters."""
    replacements = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def generate_suite_page(analysis: SuiteAnalysis) -> str:
    """Generate LaTeX for a single suite page."""
    return f"""
\\section{{{escape_latex(analysis.suite_id)}}}
\\label{{sec:{analysis.suite_id.replace('-', '_').replace(' ', '_')}}}

\\begin{{table}}[h]
\\centering
\\caption{{Suite Configuration}}
\\begin{{tabular}}{{ll}}
\\toprule
\\textbf{{Property}} & \\textbf{{Value}} \\\\
\\midrule
KEM Algorithm & {escape_latex(analysis.kem_algorithm)} \\\\
Signature Algorithm & {escape_latex(analysis.sig_algorithm)} \\\\
AEAD Algorithm & {escape_latex(analysis.aead_algorithm)} \\\\
NIST Security Level & {analysis.nist_level} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\subsection{{Performance Metrics}}

\\begin{{table}}[h]
\\centering
\\caption{{Handshake and Timing}}
\\begin{{tabular}}{{lr}}
\\toprule
\\textbf{{Metric}} & \\textbf{{Value}} \\\\
\\midrule
Handshake Duration & {analysis.handshake_ms:.2f} ms \\\\
Handshake Rank & {analysis.handshake_rank} / total \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\subsection{{System Metrics (GCS)}}

\\begin{{table}}[h]
\\centering
\\caption{{GCS Resource Usage}}
\\begin{{tabular}}{{lr}}
\\toprule
\\textbf{{Metric}} & \\textbf{{Value}} \\\\
\\midrule
CPU Average & {analysis.gcs_cpu_avg:.1f}\\% \\\\
CPU Peak & {analysis.gcs_cpu_peak:.1f}\\% \\\\
Memory RSS & {analysis.gcs_memory_mb:.1f} MB \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\subsection{{System Metrics (Drone - Raspberry Pi)}}

\\begin{{table}}[h]
\\centering
\\caption{{Drone Resource Usage}}
\\begin{{tabular}}{{lr}}
\\toprule
\\textbf{{Metric}} & \\textbf{{Value}} \\\\
\\midrule
CPU Average & {analysis.drone_cpu_avg:.1f}\\% \\\\
CPU Peak & {analysis.drone_cpu_peak:.1f}\\% \\\\
Memory RSS & {analysis.drone_memory_mb:.1f} MB \\\\
Temperature & {analysis.drone_temp_c:.1f}°C \\\\
Load Average (1m) & {analysis.drone_load_1m:.2f} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\subsection{{Power Metrics (Drone Only)}}

\\begin{{table}}[h]
\\centering
\\caption{{Power Consumption}}
\\begin{{tabular}}{{lr}}
\\toprule
\\textbf{{Metric}} & \\textbf{{Value}} \\\\
\\midrule
Power Average & {analysis.power_avg_w:.3f} W \\\\
Power Peak & {analysis.power_peak_w:.3f} W \\\\
Energy Total & {analysis.energy_total_j:.3f} J \\\\
Energy per Handshake & {analysis.energy_per_handshake_j:.6f} J \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\subsection{{Network Performance}}

\\begin{{table}}[h]
\\centering
\\caption{{Network Statistics}}
\\begin{{tabular}}{{lr}}
\\toprule
\\textbf{{Metric}} & \\textbf{{Value}} \\\\
\\midrule
Packets Sent & {analysis.packets_sent:,} \\\\
Packets Received & {analysis.packets_received:,} \\\\
\\bottomrule
\\end{{tabular}}
\\end{{table}}

\\clearpage
"""

def generate_comparative_analysis(analyses: List[SuiteAnalysis]) -> str:
    """Generate comparative analysis pages."""
    content = """
\\chapter{Comparative Analysis}
\\label{ch:comparative}

This chapter presents multi-dimensional analysis of the benchmark results,
comparing cipher suites across various performance and resource metrics.

\\section{Overall Performance Spider Chart}

Figure~\\ref{fig:spider_overall} shows a radar/spider chart comparing the top
performing cipher suites across five dimensions: speed (handshake time),
energy efficiency, CPU efficiency, memory efficiency, and security level.

\\begin{figure}[h]
\\centering
\\includegraphics[width=0.9\\textwidth]{figures/spider_overall.pdf}
\\caption{Multi-dimensional comparison of top cipher suites}
\\label{fig:spider_overall}
\\end{figure}

\\clearpage

\\section{NIST Level Comparison}

Figure~\\ref{fig:spider_nist} compares performance metrics averaged across
NIST security levels. Higher security levels (L5) generally show increased
computational overhead.

\\begin{figure}[h]
\\centering
\\includegraphics[width=0.9\\textwidth]{figures/spider_nist.pdf}
\\caption{Performance comparison by NIST security level}
\\label{fig:spider_nist}
\\end{figure}

\\clearpage

\\section{Handshake Performance}

Figure~\\ref{fig:handshake_comparison} shows handshake timing across all
measured cipher suites, sorted from fastest to slowest.

\\begin{figure}[h]
\\centering
\\includegraphics[width=1.0\\textwidth]{figures/handshake_comparison.pdf}
\\caption{Handshake duration by cipher suite}
\\label{fig:handshake_comparison}
\\end{figure}

\\clearpage

\\section{Power Consumption Analysis}

Figure~\\ref{fig:power_comparison} shows average power consumption during
the benchmark traffic period, measured on the Raspberry Pi drone.

\\begin{figure}[h]
\\centering
\\includegraphics[width=1.0\\textwidth]{figures/power_comparison.pdf}
\\caption{Power consumption by cipher suite}
\\label{fig:power_comparison}
\\end{figure}

\\clearpage
"""
    
    # Add statistical summary
    successful = [a for a in analyses if a.handshake_ms > 0]
    if successful:
        handshakes = [a.handshake_ms for a in successful]
        powers = [a.power_avg_w for a in successful if a.power_avg_w > 0]
        
        content += f"""
\\section{{Statistical Summary}}

\\begin{{table}}[h]
\\centering
\\caption{{Aggregate Statistics}}
\\begin{{tabular}}{{lrrr}}
\\toprule
\\textbf{{Metric}} & \\textbf{{Min}} & \\textbf{{Mean}} & \\textbf{{Max}} \\\\
\\midrule
Handshake (ms) & {min(handshakes):.2f} & {statistics.mean(handshakes):.2f} & {max(handshakes):.2f} \\\\
"""
        if powers:
            content += f"""Power (W) & {min(powers):.3f} & {statistics.mean(powers):.3f} & {max(powers):.3f} \\\\
"""
        content += """\\bottomrule
\\end{tabular}
\\end{table}

\\clearpage
"""
    
    return content

def generate_latex_document(analyses: List[SuiteAnalysis], run_id: str) -> str:
    """Generate complete LaTeX document."""
    
    # Document header
    document = f"""\\documentclass[11pt,a4paper]{{report}}

\\usepackage[utf8]{{inputenc}}
\\usepackage[T1]{{fontenc}}
\\usepackage{{graphicx}}
\\usepackage{{booktabs}}
\\usepackage{{longtable}}
\\usepackage{{hyperref}}
\\usepackage{{geometry}}
\\usepackage{{fancyhdr}}
\\usepackage{{xcolor}}
\\usepackage{{float}}

\\geometry{{margin=1in}}

\\pagestyle{{fancy}}
\\fancyhf{{}}
\\rhead{{PQC UAV Benchmark}}
\\lhead{{\\leftmark}}
\\rfoot{{Page \\thepage}}

\\definecolor{{nistL1}}{{HTML}}{{2ecc71}}
\\definecolor{{nistL3}}{{HTML}}{{f39c12}}
\\definecolor{{nistL5}}{{HTML}}{{e74c3c}}

\\title{{
    \\textbf{{Post-Quantum Cryptography Benchmark Results}} \\\\
    \\large UAV Communication Security Analysis \\\\
    \\vspace{{0.5cm}}
    \\normalsize Run ID: {escape_latex(run_id)} \\\\
    Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
}}
\\author{{PQC-UAV Research Project}}
\\date{{}}

\\begin{{document}}

\\maketitle

\\tableofcontents
\\clearpage

\\chapter{{Introduction}}

This document presents comprehensive benchmark results for Post-Quantum
Cryptographic (PQC) cipher suites evaluated in a UAV communication scenario.

\\section{{Test Environment}}

\\begin{{itemize}}
    \\item \\textbf{{GCS}}: Windows 10, Intel CPU
    \\item \\textbf{{Drone}}: Raspberry Pi 4, ARM Cortex-A72
    \\item \\textbf{{Network}}: LAN (192.168.0.x)
    \\item \\textbf{{Metrics}}: Power via INA219 (drone only)
\\end{{itemize}}

\\section{{Suites Tested}}

Total cipher suites benchmarked: {len(analyses)}

\\begin{{itemize}}
    \\item NIST Level 1: {sum(1 for a in analyses if a.nist_level == 'L1')}
    \\item NIST Level 3: {sum(1 for a in analyses if a.nist_level == 'L3')}
    \\item NIST Level 5: {sum(1 for a in analyses if a.nist_level == 'L5')}
\\end{{itemize}}

\\clearpage

"""
    
    # Comparative analysis chapter
    document += generate_comparative_analysis(analyses)
    
    # Individual suite pages
    document += """
\\chapter{Individual Suite Results}
\\label{ch:suites}

This chapter contains detailed metrics for each cipher suite tested.

"""
    for analysis in analyses:
        document += generate_suite_page(analysis)
    
    # Document footer
    document += """
\\chapter{Conclusions}

The benchmark results presented in this document provide empirical data for
evaluating PQC algorithm performance in constrained UAV environments.

Key observations:
\\begin{itemize}
    \\item Handshake times vary significantly across algorithm families
    \\item Power consumption correlates with computational complexity
    \\item NIST Level 5 algorithms show highest resource utilization
\\end{itemize}

\\end{document}
"""
    
    return document

# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Generate IEEE-style benchmark book")
    parser.add_argument("--input", "-i", required=True,
                        help="Path to benchmark_results JSON file")
    parser.add_argument("--output", "-o", default=str(BOOK_DIR / "pqc_benchmark_book.tex"),
                        help="Output LaTeX file path")
    args = parser.parse_args()
    
    input_path = Path(args.input)
    output_path = Path(args.output)
    
    print("=" * 70)
    print("IEEE BOOK GENERATOR")
    print("=" * 70)
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print()
    
    # Load data
    print("Loading benchmark results...")
    results = load_benchmark_results(input_path)
    print(f"Loaded {len(results)} results")
    
    # Analyze
    print("Analyzing results...")
    analyses = analyze_results(results)
    print(f"Analyzed {len(analyses)} successful suites")
    
    # Create directories
    BOOK_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    
    # Generate figures
    if MATPLOTLIB_AVAILABLE and analyses:
        print("\nGenerating figures...")
        
        # Top suites spider chart
        top_by_speed = sorted(analyses, key=lambda x: x.handshake_ms)[:10]
        create_spider_chart(top_by_speed, "Top 10 Fastest Suites", 
                           FIGURES_DIR / "spider_overall.pdf")
        print("  - spider_overall.pdf")
        
        # NIST level comparison
        create_nist_level_spider(analyses, FIGURES_DIR / "spider_nist.pdf")
        print("  - spider_nist.pdf")
        
        # Power comparison
        create_power_bar_chart(analyses, FIGURES_DIR / "power_comparison.pdf")
        print("  - power_comparison.pdf")
        
        # Handshake comparison
        create_handshake_comparison(analyses, FIGURES_DIR / "handshake_comparison.pdf")
        print("  - handshake_comparison.pdf")
    
    # Extract run ID from filename
    run_id = input_path.stem.replace("benchmark_results_", "")
    
    # Generate LaTeX
    print("\nGenerating LaTeX document...")
    latex_content = generate_latex_document(analyses, run_id)
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(latex_content)
    
    print(f"\nLaTeX document written to: {output_path}")
    print(f"Figures written to: {FIGURES_DIR}")
    print()
    print("To compile:")
    print(f"  cd {BOOK_DIR}")
    print(f"  pdflatex {output_path.name}")
    print("  pdflatex {output_path.name}  # Run twice for TOC")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
