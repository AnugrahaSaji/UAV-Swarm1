#!/usr/bin/env python3
"""
Professional PQC Benchmark Book Generator

Creates a comprehensive PDF report with detailed statistical analysis,
visualizations, and explanations for post-quantum cryptographic benchmarks.
"""

import json
import math
import statistics
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.ticker import FuncFormatter
import numpy as np
from scipy import stats

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm, mm
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle,
    PageBreak, KeepTogether, ListFlowable, ListItem, NextPageTemplate,
    PageTemplate, Frame, BaseDocTemplate
)
from reportlab.platypus.tableofcontents import TableOfContents
from reportlab.graphics.shapes import Drawing, Line, Rect
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.pdfgen import canvas


# =============================================================================
# Constants
# =============================================================================

COLORS = {
    "primary": "#1a1a2e",
    "secondary": "#16213e", 
    "accent": "#0f3460",
    "highlight": "#e94560",
    "success": "#27ae60",
    "warning": "#f39c12",
    "info": "#3498db",
    "ml_kem": "#1f77b4",
    "mceliece": "#ff7f0e",
    "hqc": "#2ca02c",
    "ml_dsa": "#d62728",
    "falcon": "#9467bd",
    "sphincs": "#8c564b",
    "aes": "#e377c2",
    "chacha": "#7f7f7f",
    "ascon": "#bcbd22",
}

NIST_LEVELS = {
    1: {"name": "Level 1", "equiv": "AES-128", "color": "#27ae60"},
    3: {"name": "Level 3", "equiv": "AES-192", "color": "#3498db"},
    5: {"name": "Level 5", "equiv": "AES-256", "color": "#e74c3c"},
}


# =============================================================================
# Data Loading & Processing
# =============================================================================

def load_all_benchmarks(input_dir: Path) -> Tuple[List[Dict], Dict]:
    """Load all benchmark JSON files and environment."""
    benchmarks = []
    
    for category in ["kem", "sig", "aead"]:
        cat_dir = input_dir / "raw" / category
        if not cat_dir.exists():
            continue
        for f in cat_dir.glob("*.json"):
            with open(f) as fp:
                data = json.load(fp)
                data["_category"] = category
                benchmarks.append(data)
    
    env = {}
    env_file = input_dir / "environment.json"
    if env_file.exists():
        with open(env_file) as fp:
            env = json.load(fp)
    
    return benchmarks, env


def compute_statistics(values: List[float]) -> Dict[str, float]:
    """Compute comprehensive statistics for a dataset."""
    if not values:
        return {}
    
    n = len(values)
    mean = statistics.mean(values)
    
    result = {
        "n": n,
        "mean": mean,
        "median": statistics.median(values),
        "min": min(values),
        "max": max(values),
        "range": max(values) - min(values),
    }
    
    if n > 1:
        result["std"] = statistics.stdev(values)
        result["var"] = statistics.variance(values)
        result["cv"] = (result["std"] / mean * 100) if mean > 0 else 0
        result["sem"] = result["std"] / math.sqrt(n)
        
        # Confidence interval (95%)
        t_val = stats.t.ppf(0.975, n - 1)
        result["ci_95_lower"] = mean - t_val * result["sem"]
        result["ci_95_upper"] = mean + t_val * result["sem"]
        
        # Percentiles
        sorted_vals = sorted(values)
        result["p5"] = np.percentile(values, 5)
        result["p25"] = np.percentile(values, 25)
        result["p75"] = np.percentile(values, 75)
        result["p95"] = np.percentile(values, 95)
        result["iqr"] = result["p75"] - result["p25"]
    
    return result


def get_nist_level(algorithm: str) -> int:
    """Determine NIST security level from algorithm name."""
    alg = algorithm.upper()
    if "512" in alg or "44" in alg or "128" in alg or "348864" in alg:
        return 1
    if "768" in alg or "65" in alg or "192" in alg or "460896" in alg:
        return 3
    if "1024" in alg or "87" in alg or "256" in alg or "8192128" in alg:
        return 5
    return 1


def get_algorithm_color(alg: str) -> str:
    """Get color for algorithm visualization."""
    alg_lower = alg.lower()
    if "ml-kem" in alg_lower: return COLORS["ml_kem"]
    if "mceliece" in alg_lower: return COLORS["mceliece"]
    if "hqc" in alg_lower: return COLORS["hqc"]
    if "ml-dsa" in alg_lower: return COLORS["ml_dsa"]
    if "falcon" in alg_lower: return COLORS["falcon"]
    if "sphincs" in alg_lower: return COLORS["sphincs"]
    if "aes" in alg_lower: return COLORS["aes"]
    if "chacha" in alg_lower: return COLORS["chacha"]
    if "ascon" in alg_lower: return COLORS["ascon"]
    return "#333333"


# =============================================================================
# Visualization Generation
# =============================================================================

def create_timing_distribution(benchmark: Dict, output_dir: Path) -> str:
    """Create timing distribution histogram with statistics overlay."""
    times_us = [t / 1000 for t in benchmark["timing"]["perf_ns"]]
    stats_data = compute_statistics(times_us)
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    color = get_algorithm_color(benchmark["algorithm"])
    n, bins, patches = ax.hist(times_us, bins=30, color=color, alpha=0.7, 
                                edgecolor='white', linewidth=0.5)
    
    # Add statistical markers
    ax.axvline(stats_data["mean"], color='red', linestyle='--', linewidth=2, 
               label=f'Mean: {stats_data["mean"]:.2f} µs')
    ax.axvline(stats_data["median"], color='green', linestyle=':', linewidth=2,
               label=f'Median: {stats_data["median"]:.2f} µs')
    
    if "ci_95_lower" in stats_data:
        ax.axvspan(stats_data["ci_95_lower"], stats_data["ci_95_upper"], 
                   alpha=0.2, color='red', label='95% CI')
    
    ax.set_xlabel("Time (µs)", fontsize=12, fontweight='bold')
    ax.set_ylabel("Frequency", fontsize=12, fontweight='bold')
    ax.set_title(f"{benchmark['algorithm']} - {benchmark['operation'].capitalize()}\n"
                 f"Timing Distribution (n={stats_data['n']})", fontsize=14, fontweight='bold')
    ax.legend(loc='upper right')
    ax.grid(axis='y', alpha=0.3)
    
    # Stats box
    stats_text = (f"σ = {stats_data.get('std', 0):.2f} µs\n"
                  f"CV = {stats_data.get('cv', 0):.1f}%\n"
                  f"Range: {stats_data['min']:.2f} - {stats_data['max']:.2f}")
    ax.text(0.98, 0.72, stats_text, transform=ax.transAxes, fontsize=9,
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
    
    plt.tight_layout()
    
    name = f"{benchmark['algorithm']}_{benchmark['operation']}_timing_dist.png"
    name = name.replace("-", "_").replace("+", "_").replace(" ", "_")
    filepath = output_dir / name
    plt.savefig(filepath, dpi=200, bbox_inches='tight')
    plt.close()
    
    return str(filepath)


def create_power_profile(benchmark: Dict, output_dir: Path) -> str:
    """Create power consumption profile visualization."""
    powers = benchmark["power"]["power_mean_w"]
    voltages = benchmark["power"]["voltage_mean_v"]
    currents = [c * 1000 for c in benchmark["power"]["current_mean_a"]]  # mA
    
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))
    
    color = get_algorithm_color(benchmark["algorithm"])
    
    # Power distribution
    ax = axes[0]
    ax.hist(powers, bins=25, color=color, alpha=0.7, edgecolor='white')
    ax.axvline(statistics.mean(powers), color='red', linestyle='--', linewidth=2)
    ax.set_xlabel("Power (W)", fontsize=11, fontweight='bold')
    ax.set_ylabel("Frequency", fontsize=11, fontweight='bold')
    ax.set_title("Power Distribution", fontsize=12, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    
    # Voltage stability
    ax = axes[1]
    ax.plot(voltages, color='#3498db', linewidth=1)
    ax.fill_between(range(len(voltages)), voltages, alpha=0.3, color='#3498db')
    ax.set_xlabel("Iteration", fontsize=11, fontweight='bold')
    ax.set_ylabel("Voltage (V)", fontsize=11, fontweight='bold')
    ax.set_title("Voltage Stability", fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)
    
    # Current draw
    ax = axes[2]
    ax.plot(currents, color='#e74c3c', linewidth=1)
    ax.fill_between(range(len(currents)), currents, alpha=0.3, color='#e74c3c')
    ax.set_xlabel("Iteration", fontsize=11, fontweight='bold')
    ax.set_ylabel("Current (mA)", fontsize=11, fontweight='bold')
    ax.set_title("Current Profile", fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)
    
    plt.suptitle(f"{benchmark['algorithm']} - {benchmark['operation'].capitalize()}\n"
                 f"Power Characteristics", fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    name = f"{benchmark['algorithm']}_{benchmark['operation']}_power_profile.png"
    name = name.replace("-", "_").replace("+", "_").replace(" ", "_")
    filepath = output_dir / name
    plt.savefig(filepath, dpi=200, bbox_inches='tight')
    plt.close()
    
    return str(filepath)


def create_energy_analysis(benchmark: Dict, output_dir: Path) -> str:
    """Create energy consumption analysis."""
    energies_uj = [e * 1e6 for e in benchmark["power"]["energy_j"]]
    times_ms = [t / 1e6 for t in benchmark["timing"]["perf_ns"]]
    powers = benchmark["power"]["power_mean_w"]
    
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    
    color = get_algorithm_color(benchmark["algorithm"])
    
    # Energy distribution
    ax = axes[0]
    ax.hist(energies_uj, bins=25, color=color, alpha=0.7, edgecolor='white')
    mean_energy = statistics.mean(energies_uj)
    ax.axvline(mean_energy, color='red', linestyle='--', linewidth=2,
               label=f'Mean: {mean_energy:.2f} µJ')
    ax.set_xlabel("Energy (µJ)", fontsize=11, fontweight='bold')
    ax.set_ylabel("Frequency", fontsize=11, fontweight='bold')
    ax.set_title("Energy per Operation", fontsize=12, fontweight='bold')
    ax.legend()
    ax.grid(axis='y', alpha=0.3)
    
    # Time vs Energy scatter
    ax = axes[1]
    ax.scatter(times_ms, energies_uj, c=powers, cmap='RdYlGn_r', 
               alpha=0.6, s=50, edgecolor='white')
    ax.set_xlabel("Time (ms)", fontsize=11, fontweight='bold')
    ax.set_ylabel("Energy (µJ)", fontsize=11, fontweight='bold')
    ax.set_title("Time-Energy Correlation", fontsize=12, fontweight='bold')
    ax.grid(True, alpha=0.3)
    
    # Add colorbar
    sm = plt.cm.ScalarMappable(cmap='RdYlGn_r', 
                                norm=plt.Normalize(min(powers), max(powers)))
    cbar = plt.colorbar(sm, ax=ax)
    cbar.set_label('Power (W)', fontsize=10)
    
    plt.suptitle(f"{benchmark['algorithm']} - {benchmark['operation'].capitalize()}\n"
                 f"Energy Analysis", fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    name = f"{benchmark['algorithm']}_{benchmark['operation']}_energy.png"
    name = name.replace("-", "_").replace("+", "_").replace(" ", "_")
    filepath = output_dir / name
    plt.savefig(filepath, dpi=200, bbox_inches='tight')
    plt.close()
    
    return str(filepath)


def create_comparison_chart(benchmarks: List[Dict], category: str, 
                           metric: str, output_dir: Path) -> str:
    """Create comparison bar chart for algorithms."""
    
    # Filter and group
    filtered = [b for b in benchmarks if b["_category"] == category]
    if not filtered:
        return ""
    
    alg_ops = {}
    for b in filtered:
        alg = b["algorithm"]
        op = b["operation"]
        
        if metric == "timing":
            vals = [t / 1e6 for t in b["timing"]["perf_ns"]]  # ms
        elif metric == "power":
            vals = b["power"]["power_mean_w"]
        elif metric == "energy":
            vals = [e * 1e6 for e in b["power"]["energy_j"]]  # µJ
        else:
            continue
        
        if alg not in alg_ops:
            alg_ops[alg] = {}
        alg_ops[alg][op] = {
            "mean": statistics.mean(vals),
            "std": statistics.stdev(vals) if len(vals) > 1 else 0
        }
    
    algorithms = sorted(alg_ops.keys())
    operations = sorted(set(op for ops in alg_ops.values() for op in ops))
    
    fig, ax = plt.subplots(figsize=(14, 8))
    
    x = np.arange(len(algorithms))
    width = 0.8 / len(operations)
    
    op_colors = {
        "keygen": "#2ecc71", "encapsulate": "#3498db", "decapsulate": "#9b59b6",
        "sign": "#e74c3c", "verify": "#f39c12",
        "encrypt": "#1abc9c", "decrypt": "#e67e22"
    }
    
    for i, op in enumerate(operations):
        means = [alg_ops.get(alg, {}).get(op, {}).get("mean", 0) for alg in algorithms]
        stds = [alg_ops.get(alg, {}).get(op, {}).get("std", 0) for alg in algorithms]
        
        color = op_colors.get(op, "#333333")
        bars = ax.bar(x + i * width - (len(operations) - 1) * width / 2, 
                     means, width, label=op.capitalize(),
                     color=color, edgecolor='white', yerr=stds, capsize=2)
    
    units = {"timing": "ms", "power": "W", "energy": "µJ"}
    titles = {"timing": "Execution Time", "power": "Power Consumption", "energy": "Energy per Operation"}
    
    ax.set_xlabel("Algorithm", fontsize=12, fontweight='bold')
    ax.set_ylabel(f"{titles[metric]} ({units[metric]})", fontsize=12, fontweight='bold')
    ax.set_title(f"{category.upper()} {titles[metric]} Comparison\n(100 iterations, error bars = ±1σ)",
                fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(algorithms, rotation=45, ha='right', fontsize=9)
    ax.legend(loc='upper right')
    ax.grid(axis='y', alpha=0.3)
    
    if metric in ["timing", "energy"]:
        ax.set_yscale('log')
    
    plt.tight_layout()
    
    filename = f"{category}_{metric}_comparison.png"
    filepath = output_dir / filename
    plt.savefig(filepath, dpi=200, bbox_inches='tight')
    plt.close()
    
    return str(filepath)


def create_nist_level_analysis(benchmarks: List[Dict], output_dir: Path) -> str:
    """Create NIST security level comparison."""
    
    level_data = {1: [], 3: [], 5: []}
    
    for b in benchmarks:
        if b["_category"] not in ["kem", "sig"]:
            continue
        level = get_nist_level(b["algorithm"])
        times = [t / 1e6 for t in b["timing"]["perf_ns"]]
        energies = [e * 1e6 for e in b["power"]["energy_j"]]
        
        level_data[level].append({
            "algorithm": b["algorithm"],
            "operation": b["operation"],
            "time_mean": statistics.mean(times),
            "energy_mean": statistics.mean(energies),
        })
    
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    
    # Time by level
    ax = axes[0]
    for level in [1, 3, 5]:
        times = [d["time_mean"] for d in level_data[level]]
        if times:
            bp = ax.boxplot([times], positions=[level], widths=0.6, patch_artist=True)
            bp['boxes'][0].set_facecolor(NIST_LEVELS[level]["color"])
            bp['boxes'][0].set_alpha(0.6)
    ax.set_xlabel("NIST Level", fontsize=11, fontweight='bold')
    ax.set_ylabel("Time (ms)", fontsize=11, fontweight='bold')
    ax.set_title("Timing by Security Level", fontsize=12, fontweight='bold')
    ax.set_yscale('log')
    ax.grid(axis='y', alpha=0.3)
    
    # Energy by level
    ax = axes[1]
    for level in [1, 3, 5]:
        energies = [d["energy_mean"] for d in level_data[level]]
        if energies:
            bp = ax.boxplot([energies], positions=[level], widths=0.6, patch_artist=True)
            bp['boxes'][0].set_facecolor(NIST_LEVELS[level]["color"])
            bp['boxes'][0].set_alpha(0.6)
    ax.set_xlabel("NIST Level", fontsize=11, fontweight='bold')
    ax.set_ylabel("Energy (µJ)", fontsize=11, fontweight='bold')
    ax.set_title("Energy by Security Level", fontsize=12, fontweight='bold')
    ax.set_yscale('log')
    ax.grid(axis='y', alpha=0.3)
    
    # Algorithm count
    ax = axes[2]
    counts = {l: len(set(d["algorithm"] for d in level_data[l])) for l in [1, 3, 5]}
    bars = ax.bar([1, 3, 5], [counts[1], counts[3], counts[5]],
                  color=[NIST_LEVELS[l]["color"] for l in [1, 3, 5]], 
                  edgecolor='white', alpha=0.8)
    ax.set_xlabel("NIST Level", fontsize=11, fontweight='bold')
    ax.set_ylabel("Algorithm Count", fontsize=11, fontweight='bold')
    ax.set_title("Algorithms per Level", fontsize=12, fontweight='bold')
    ax.grid(axis='y', alpha=0.3)
    
    for bar, count in zip(bars, [counts[1], counts[3], counts[5]]):
        ax.annotate(str(count), xy=(bar.get_x() + bar.get_width()/2, bar.get_height()),
                   xytext=(0, 3), textcoords='offset points', ha='center', fontsize=12)
    
    plt.suptitle("NIST Security Level Analysis", fontsize=14, fontweight='bold')
    plt.tight_layout()
    
    filepath = output_dir / "nist_level_analysis.png"
    plt.savefig(filepath, dpi=200, bbox_inches='tight')
    plt.close()
    
    return str(filepath)


# =============================================================================
# PDF Generation
# =============================================================================

class BenchmarkBookGenerator:
    """Generate professional PDF benchmark book."""
    
    def __init__(self, input_dir: Path, output_dir: Path):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.plots_dir = output_dir / "plots"
        self.plots_dir.mkdir(exist_ok=True)
        
        self.benchmarks, self.env = load_all_benchmarks(input_dir)
        self.styles = self._create_styles()
        
    def _create_styles(self):
        """Create document styles."""
        styles = getSampleStyleSheet()
        
        styles.add(ParagraphStyle('BookTitle', parent=styles['Title'],
            fontSize=28, spaceAfter=30, alignment=TA_CENTER,
            textColor=colors.HexColor(COLORS["primary"])))
        
        styles.add(ParagraphStyle('ChapterTitle', parent=styles['Heading1'],
            fontSize=22, spaceBefore=20, spaceAfter=15,
            textColor=colors.HexColor(COLORS["primary"])))
        
        styles.add(ParagraphStyle('SectionTitle', parent=styles['Heading2'],
            fontSize=16, spaceBefore=15, spaceAfter=10,
            textColor=colors.HexColor(COLORS["secondary"])))
        
        styles.add(ParagraphStyle('SubSection', parent=styles['Heading3'],
            fontSize=13, spaceBefore=12, spaceAfter=8,
            textColor=colors.HexColor(COLORS["accent"])))
        
        styles.add(ParagraphStyle('BookBody', parent=styles['Normal'],
            fontSize=10, spaceBefore=6, spaceAfter=6,
            alignment=TA_JUSTIFY, leading=14))
        
        styles.add(ParagraphStyle('BookCaption', parent=styles['Italic'],
            fontSize=9, spaceBefore=5, spaceAfter=10,
            alignment=TA_CENTER, textColor=colors.HexColor("#555555")))
        
        styles.add(ParagraphStyle('BookCode', parent=styles['Normal'],
            fontName='Courier', fontSize=9, leftIndent=20,
            backColor=colors.HexColor("#f5f5f5")))
        
        styles.add(ParagraphStyle('TableHeader',
            fontName='Helvetica-Bold', fontSize=9, alignment=TA_CENTER))
        
        styles.add(ParagraphStyle('Metadata', parent=styles['Normal'],
            fontSize=10, alignment=TA_CENTER, textColor=colors.gray))
        
        return styles
    
    def _add_cover_page(self, story: List):
        """Add cover page."""
        story.append(Spacer(1, 2*inch))
        story.append(Paragraph("Post-Quantum Cryptography", self.styles['BookTitle']))
        story.append(Paragraph("Performance Benchmark Report", self.styles['ChapterTitle']))
        story.append(Spacer(1, 0.5*inch))
        
        story.append(Paragraph(
            f"<b>Platform:</b> Raspberry Pi 4 Model B<br/>"
            f"<b>Power Monitoring:</b> INA219 @ 1kHz<br/>"
            f"<b>Iterations:</b> 100 per operation<br/>"
            f"<b>Date:</b> {datetime.now().strftime('%B %d, %Y')}",
            self.styles['Metadata']
        ))
        
        story.append(Spacer(1, 1*inch))
        story.append(Paragraph(
            "<i>Comprehensive analysis of NIST-standardized post-quantum "
            "cryptographic algorithms including timing, power consumption, "
            "and energy efficiency metrics.</i>",
            self.styles['BookBody']
        ))
        story.append(PageBreak())
    
    def _add_executive_summary(self, story: List):
        """Add executive summary."""
        story.append(Paragraph("Executive Summary", self.styles['ChapterTitle']))
        
        total_measurements = sum(len(b["timing"]["perf_ns"]) for b in self.benchmarks)
        total_algorithms = len(set(b["algorithm"] for b in self.benchmarks))
        
        story.append(Paragraph(
            f"This report presents comprehensive benchmarking results for <b>{total_algorithms}</b> "
            f"post-quantum cryptographic algorithms across <b>{total_measurements:,}</b> individual "
            f"measurements. Each algorithm was tested with <b>100 iterations</b> for statistical "
            f"reliability, with real-time power monitoring at <b>1 kHz</b> sampling rate using "
            f"an INA219 current sensor.",
            self.styles['BookBody']
        ))
        
        story.append(Spacer(1, 0.2*inch))
        
        # Key findings table
        story.append(Paragraph("Key Findings", self.styles['SectionTitle']))
        
        # Find fastest/slowest
        kem_times = [(b["algorithm"], statistics.mean([t/1e6 for t in b["timing"]["perf_ns"]]))
                     for b in self.benchmarks if b["_category"] == "kem" and b["operation"] == "keygen"]
        sig_times = [(b["algorithm"], statistics.mean([t/1e6 for t in b["timing"]["perf_ns"]]))
                     for b in self.benchmarks if b["_category"] == "sig" and b["operation"] == "sign"]
        
        findings = [
            ["Metric", "Algorithm", "Value"],
            ["Fastest KEM Keygen", min(kem_times, key=lambda x: x[1])[0] if kem_times else "N/A",
             f"{min(kem_times, key=lambda x: x[1])[1]:.3f} ms" if kem_times else "N/A"],
            ["Slowest KEM Keygen", max(kem_times, key=lambda x: x[1])[0] if kem_times else "N/A",
             f"{max(kem_times, key=lambda x: x[1])[1]:.1f} ms" if kem_times else "N/A"],
            ["Fastest Signature", min(sig_times, key=lambda x: x[1])[0] if sig_times else "N/A",
             f"{min(sig_times, key=lambda x: x[1])[1]:.3f} ms" if sig_times else "N/A"],
        ]
        
        table = Table(findings, colWidths=[2*inch, 2.5*inch, 1.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLORS["primary"])),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(table)
        story.append(PageBreak())
    
    def _add_methodology(self, story: List):
        """Add methodology section."""
        story.append(Paragraph("Methodology", self.styles['ChapterTitle']))
        
        story.append(Paragraph("Test Environment", self.styles['SectionTitle']))
        
        env_data = [
            ["Parameter", "Value"],
            ["Platform", self.env.get("hostname", "Raspberry Pi 4")],
            ["CPU Cores", str(self.env.get("cpu_cores", 4))],
            ["CPU Governor", self.env.get("cpu_freq_governor", "ondemand")],
            ["Memory", f"{self.env.get('memory_total_mb', 0)} MB"],
            ["Kernel", self.env.get("kernel_version", "6.x")],
            ["Python", self.env.get("python_version", "3.11")],
            ["Power Sensor", "INA219 @ I2C 0x40"],
            ["Sample Rate", "1000 Hz"],
        ]
        
        table = Table(env_data, colWidths=[2.5*inch, 3.5*inch])
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(COLORS["secondary"])),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('ALIGN', (0, 0), (0, -1), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'LEFT'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ]))
        story.append(table)
        
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph("Measurement Protocol", self.styles['SectionTitle']))
        
        story.append(Paragraph(
            "Each cryptographic operation was measured using the following protocol:<br/><br/>"
            "• <b>Timing:</b> High-resolution timing via <font name='Courier'>time.perf_counter_ns()</font> "
            "providing nanosecond precision<br/>"
            "• <b>Power:</b> Continuous sampling at 1 kHz using INA219 bidirectional current/power monitor<br/>"
            "• <b>Warmup:</b> 50ms stabilization period before each measurement<br/>"
            "• <b>Cooldown:</b> 50ms settling period after each measurement<br/>"
            "• <b>Iterations:</b> 100 repetitions per operation for statistical validity<br/>"
            "• <b>Energy:</b> Calculated as E = P × t from mean power and execution time",
            self.styles['BookBody']
        ))
        
        story.append(PageBreak())
    
    def _add_algorithm_chapter(self, story: List, category: str, title: str):
        """Add chapter for algorithm category."""
        story.append(Paragraph(title, self.styles['ChapterTitle']))
        
        cat_benchmarks = [b for b in self.benchmarks if b["_category"] == category]
        algorithms = sorted(set(b["algorithm"] for b in cat_benchmarks))
        
        # Category overview
        story.append(Paragraph("Category Overview", self.styles['SectionTitle']))
        
        # Create comparison charts
        for metric in ["timing", "power", "energy"]:
            chart_path = create_comparison_chart(self.benchmarks, category, metric, self.plots_dir)
            if chart_path and Path(chart_path).exists():
                img = Image(chart_path, width=6*inch, height=4*inch)
                story.append(img)
                
                metric_desc = {
                    "timing": "Execution time comparison showing mean values with standard deviation error bars. "
                              "Lower values indicate faster performance. Log scale used for visibility across "
                              "the wide performance range of different algorithm families.",
                    "power": "Average power consumption during cryptographic operations. Values typically range "
                             "from 3.3W to 4.5W on the Raspberry Pi 4 platform, representing the computational "
                             "overhead above idle power draw (~2.5W).",
                    "energy": "Energy consumed per operation, calculated from power and timing data. This metric "
                              "is critical for battery-powered deployments where total energy budget determines "
                              "operational lifetime."
                }
                story.append(Paragraph(f"<i>Figure: {metric_desc[metric]}</i>", self.styles['BookCaption']))
                story.append(Spacer(1, 0.2*inch))
        
        story.append(PageBreak())
        
        # Individual algorithm analysis
        for alg in algorithms:
            alg_benchmarks = [b for b in cat_benchmarks if b["algorithm"] == alg]
            
            story.append(Paragraph(alg, self.styles['SectionTitle']))
            
            nist_level = get_nist_level(alg)
            story.append(Paragraph(
                f"<b>NIST Security Level:</b> {nist_level} (equivalent to {NIST_LEVELS[nist_level]['equiv']})<br/>"
                f"<b>Operations Benchmarked:</b> {', '.join(b['operation'] for b in alg_benchmarks)}",
                self.styles['BookBody']
            ))
            
            # Performance summary table
            perf_data = [["Operation", "Mean Time", "Std Dev", "Mean Power", "Mean Energy"]]
            
            for b in alg_benchmarks:
                times = [t / 1e6 for t in b["timing"]["perf_ns"]]
                powers = b["power"]["power_mean_w"]
                energies = [e * 1e6 for e in b["power"]["energy_j"]]
                
                mean_time = statistics.mean(times)
                std_time = statistics.stdev(times) if len(times) > 1 else 0
                
                time_str = f"{mean_time:.3f} ms" if mean_time < 1000 else f"{mean_time/1000:.2f} s"
                std_str = f"±{std_time:.3f} ms" if std_time < 1000 else f"±{std_time/1000:.2f} s"
                
                perf_data.append([
                    b["operation"].capitalize(),
                    time_str,
                    std_str,
                    f"{statistics.mean(powers):.3f} W",
                    f"{statistics.mean(energies):.1f} µJ" if statistics.mean(energies) < 1e6 
                        else f"{statistics.mean(energies)/1e6:.2f} J"
                ])
            
            table = Table(perf_data, colWidths=[1.3*inch, 1.2*inch, 1.2*inch, 1.2*inch, 1.2*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor(get_algorithm_color(alg))),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 9),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.gray),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8f9fa")]),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            story.append(table)
            story.append(Spacer(1, 0.2*inch))
            
            # Add detailed plots for first operation
            if alg_benchmarks:
                b = alg_benchmarks[0]
                
                # Timing distribution
                timing_plot = create_timing_distribution(b, self.plots_dir)
                if Path(timing_plot).exists():
                    img = Image(timing_plot, width=5.5*inch, height=3.5*inch)
                    story.append(img)
                    story.append(Paragraph(
                        f"<i>Timing distribution for {b['operation']} operation showing "
                        f"histogram, mean (red dashed), median (green dotted), and 95% confidence interval.</i>",
                        self.styles['BookCaption']
                    ))
                
                # Power profile
                power_plot = create_power_profile(b, self.plots_dir)
                if Path(power_plot).exists():
                    img = Image(power_plot, width=6*inch, height=3*inch)
                    story.append(img)
                    story.append(Paragraph(
                        f"<i>Power characteristics showing power distribution, voltage stability, "
                        f"and current profile across all iterations.</i>",
                        self.styles['BookCaption']
                    ))
            
            story.append(PageBreak())
    
    def _add_conclusions(self, story: List):
        """Add conclusions chapter."""
        story.append(Paragraph("Conclusions & Recommendations", self.styles['ChapterTitle']))
        
        story.append(Paragraph("Performance Summary", self.styles['SectionTitle']))
        story.append(Paragraph(
            "The benchmark results reveal significant performance differences across post-quantum "
            "algorithm families. Lattice-based schemes (ML-KEM, ML-DSA, Falcon) demonstrate "
            "excellent performance characteristics suitable for most applications. Code-based "
            "schemes (McEliece, HQC) show varying trade-offs between security assumptions and "
            "computational cost. Hash-based signatures (SPHINCS+) provide conservative security "
            "at the cost of significantly longer signing times.",
            self.styles['BookBody']
        ))
        
        story.append(Paragraph("Recommendations", self.styles['SectionTitle']))
        
        recs = [
            ("<b>Latency-Critical Applications:</b> ML-KEM-512/768 and ML-DSA-44/65 provide "
             "sub-millisecond operations suitable for real-time systems."),
            ("<b>Energy-Constrained Deployments:</b> Prefer ML-KEM for key exchange and Falcon "
             "for signatures to minimize battery consumption."),
            ("<b>Maximum Security:</b> Classic-McEliece-8192128 and SPHINCS+-SHA2-256s offer "
             "conservative security assumptions for high-value, long-term protection."),
            ("<b>Balanced Choice:</b> ML-KEM-768 + ML-DSA-65 provide NIST Level 3 security "
             "with excellent performance characteristics."),
        ]
        
        for rec in recs:
            story.append(Paragraph(f"• {rec}", self.styles['BookBody']))
        
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph(
            f"<i>Report generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} with "
            f"{sum(len(b['timing']['perf_ns']) for b in self.benchmarks):,} total measurements.</i>",
            self.styles['Metadata']
        ))
    
    def generate(self) -> Path:
        """Generate the complete benchmark book."""
        print("Generating PQC Benchmark Book...")
        
        output_path = self.output_dir / "PQC_BENCHMARK_BOOK.pdf"
        
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            rightMargin=2*cm,
            leftMargin=2*cm,
            topMargin=2*cm,
            bottomMargin=2*cm,
        )
        
        story = []
        
        print("  - Adding cover page...")
        self._add_cover_page(story)
        
        print("  - Adding executive summary...")
        self._add_executive_summary(story)
        
        print("  - Adding methodology...")
        self._add_methodology(story)
        
        print("  - Adding KEM chapter...")
        self._add_algorithm_chapter(story, "kem", "Key Encapsulation Mechanisms (KEM)")
        
        print("  - Adding Signature chapter...")
        self._add_algorithm_chapter(story, "sig", "Digital Signature Algorithms")
        
        print("  - Adding AEAD chapter...")
        self._add_algorithm_chapter(story, "aead", "Authenticated Encryption (AEAD)")
        
        print("  - Adding conclusions...")
        self._add_conclusions(story)
        
        print("  - Building PDF...")
        doc.build(story)
        
        print(f"\nBenchmark book saved to: {output_path}")
        return output_path


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate PQC Benchmark Book")
    parser.add_argument("-i", "--input", type=str, default="benchmarks/bench_results_100iter")
    parser.add_argument("-o", "--output", type=str, default="benchmark_book")
    args = parser.parse_args()
    
    generator = BenchmarkBookGenerator(Path(args.input), Path(args.output))
    generator.generate()


if __name__ == "__main__":
    main()
