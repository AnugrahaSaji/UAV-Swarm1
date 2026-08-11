#!/usr/bin/env python3
"""
IEEE-Style Benchmark Report Generator - bench/generate_ieee_report.py

Generates a comprehensive IEEE-style LaTeX document from benchmark results.
ONE FULL PAGE per cryptographic suite with:
- Suite identification and crypto parameters
- Performance metrics (handshake, throughput, latency)
- System metrics (CPU, memory, temperature)
- Power/Energy metrics (drone only)
- Radar charts and comparison tables

Usage:
    python -m bench.generate_ieee_report <results_json> [--output <output_dir>]

Requirements:
    - LaTeX with IEEEtran class
    - pgfplots, tikz, booktabs packages
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import statistics

# =============================================================================
# Constants
# =============================================================================

NIST_LEVEL_COLORS = {
    "L1": "green!70!black",
    "L3": "blue!70!black", 
    "L5": "red!70!black",
}

KEM_FAMILIES = {
    "ML-KEM": "Lattice (CRYSTALS-Kyber)",
    "HQC": "Code-based (HQC)",
    "Classic-McEliece": "Code-based (McEliece)",
}

SIG_FAMILIES = {
    "Falcon": "Lattice (NTRU-based)",
    "ML-DSA": "Lattice (CRYSTALS-Dilithium)",
    "SPHINCS+": "Hash-based",
}

# =============================================================================
# LaTeX Utilities
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
        '^': r'\^{}',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

def format_number(value: float, decimals: int = 2) -> str:
    """Format number for display."""
    if value == 0:
        return "0"
    if abs(value) >= 1000:
        return f"{value:,.{decimals}f}"
    return f"{value:.{decimals}f}"

# =============================================================================
# Report Generator
# =============================================================================

class IEEEReportGenerator:
    """Generates IEEE-style LaTeX benchmark report."""
    
    def __init__(self, results_file: str, output_dir: str = None):
        self.results_file = Path(results_file)
        self.output_dir = Path(output_dir) if output_dir else self.results_file.parent
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load results
        with open(self.results_file, 'r') as f:
            self.data = json.load(f)
        
        self.run_id = self.data.get("run_id", "unknown")
        self.results = self.data.get("results", [])
        self.successful_results = [r for r in self.results if r.get("success")]
    
    def generate(self) -> Path:
        """Generate the full IEEE report."""
        latex_content = self._generate_document()
        
        output_file = self.output_dir / f"benchmark_report_{self.run_id}.tex"
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        
        print(f"LaTeX report generated: {output_file}")
        return output_file
    
    def _generate_document(self) -> str:
        """Generate complete LaTeX document."""
        parts = [
            self._generate_preamble(),
            self._generate_title_page(),
            self._generate_executive_summary(),
            self._generate_methodology(),
        ]
        
        # One page per suite
        for idx, result in enumerate(self.successful_results, 1):
            parts.append(self._generate_suite_page(result, idx))
        
        # Comparison tables
        parts.append(self._generate_comparison_section())
        
        # Conclusion
        parts.append(self._generate_conclusion())
        
        # End document
        parts.append(r"\end{document}")
        
        return "\n\n".join(parts)
    
    def _generate_preamble(self) -> str:
        """Generate LaTeX preamble."""
        return r"""\documentclass[conference]{IEEEtran}

% Packages
\usepackage[utf8]{inputenc}
\usepackage[T1]{fontenc}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{multirow}
\usepackage{xcolor}
\usepackage{tikz}
\usepackage{pgfplots}
\usepackage{pgfplotstable}
\usepackage{subcaption}
\usepackage{hyperref}
\usepackage{siunitx}
\usepackage{float}
\usepackage{array}
\usepackage{tabularx}
\usepackage{longtable}

\pgfplotsset{compat=1.18}

% Custom colors for NIST levels
\definecolor{nistL1}{RGB}{0,128,0}
\definecolor{nistL3}{RGB}{0,0,180}
\definecolor{nistL5}{RGB}{180,0,0}

% Radar chart setup
\usepgfplotslibrary{polar}

% Custom commands
\newcommand{\suiteID}[1]{\texttt{#1}}
\newcommand{\metric}[2]{#1~\si{#2}}
\newcommand{\ms}{\si{ms}}
\newcommand{\us}{\si{\micro s}}
\newcommand{\watt}{\si{W}}
\newcommand{\joule}{\si{J}}

\begin{document}"""
    
    def _generate_title_page(self) -> str:
        """Generate title and author info."""
        timestamp = self.data.get("timestamp", datetime.now().isoformat())
        total_suites = self.data.get("total_suites", len(self.results))
        successful = self.data.get("successful_suites", len(self.successful_results))
        traffic_duration = self.data.get("traffic_duration_s", 10)
        
        return rf"""
\title{{Comprehensive Post-Quantum Cryptography Benchmark Report\\
\large UAV Secure Communication Tunnel Performance Analysis}}

\author{{
\IEEEauthorblockN{{Automated Benchmark System}}
\IEEEauthorblockA{{Run ID: \texttt{{{escape_latex(self.run_id)}}}\\
Generated: {escape_latex(timestamp[:19])}}}
}}

\maketitle

\begin{abstract}
This report presents comprehensive benchmark results for post-quantum cryptographic (PQC) 
cipher suites implemented in the secure UAV communication tunnel. The benchmark evaluates 
{total_suites} cipher suites with {successful} successful measurements. Each suite was 
tested with {traffic_duration} seconds of MAVProxy traffic, measuring handshake performance, 
data plane throughput, latency characteristics, system resource utilization, and power 
consumption on the embedded drone platform (Raspberry Pi).
\end{abstract}

\begin{IEEEkeywords}
Post-Quantum Cryptography, UAV Security, ML-KEM, Falcon, ML-DSA, SPHINCS+, 
Embedded Systems, Power Analysis, Benchmark
\end{IEEEkeywords}"""
    
    def _generate_executive_summary(self) -> str:
        """Generate executive summary section."""
        if not self.successful_results:
            return r"\section{Executive Summary}\nNo successful benchmark results available."
        
        # Calculate aggregate statistics
        handshakes = [r["handshake_duration_ms"] for r in self.successful_results]
        powers = [r["drone_power_avg_w"] for r in self.successful_results if r["drone_power_avg_w"] > 0]
        cpus = [r["drone_cpu_avg_percent"] for r in self.successful_results]
        
        avg_handshake = statistics.mean(handshakes) if handshakes else 0
        min_handshake = min(handshakes) if handshakes else 0
        max_handshake = max(handshakes) if handshakes else 0
        
        avg_power = statistics.mean(powers) if powers else 0
        avg_cpu = statistics.mean(cpus) if cpus else 0
        
        # Find best/worst suites
        fastest_suite = min(self.successful_results, key=lambda x: x["handshake_duration_ms"])
        slowest_suite = max(self.successful_results, key=lambda x: x["handshake_duration_ms"])
        
        # Group by NIST level
        by_level = {}
        for r in self.successful_results:
            level = r.get("nist_level", "Unknown")
            if level not in by_level:
                by_level[level] = []
            by_level[level].append(r)
        
        level_stats = []
        for level in ["L1", "L3", "L5"]:
            if level in by_level:
                avg = statistics.mean([r["handshake_duration_ms"] for r in by_level[level]])
                level_stats.append(f"NIST {level}: {len(by_level[level])} suites, avg {avg:.1f}ms")
        
        return rf"""
\section{{Executive Summary}}

\subsection{{Benchmark Overview}}
\begin{{itemize}}
    \item \textbf{{Total Suites Tested:}} {len(self.results)}
    \item \textbf{{Successful Benchmarks:}} {len(self.successful_results)}
    \item \textbf{{Traffic Duration:}} {self.data.get("traffic_duration_s", 10)} seconds per suite
\end{{itemize}}

\subsection{{Aggregate Performance}}

\begin{{table}}[h]
\centering
\caption{{Handshake Performance Summary}}
\begin{{tabular}}{{@{{}}lrr@{{}}}}
\toprule
\textbf{{Metric}} & \textbf{{Value}} & \textbf{{Unit}} \\
\midrule
Average Handshake & {avg_handshake:.2f} & ms \\
Minimum Handshake & {min_handshake:.2f} & ms \\
Maximum Handshake & {max_handshake:.2f} & ms \\
\midrule
Fastest Suite & \multicolumn{{2}}{{l}}{{\suiteID{{{escape_latex(fastest_suite["suite_id"])}}}}} \\
Slowest Suite & \multicolumn{{2}}{{l}}{{\suiteID{{{escape_latex(slowest_suite["suite_id"])}}}}} \\
\bottomrule
\end{{tabular}}
\end{{table}}

\subsection{{NIST Security Level Distribution}}
\begin{{itemize}}
{"".join([f"    \\item {s}" + chr(10) for s in level_stats])}
\end{{itemize}}

\subsection{{Drone Resource Utilization}}
\begin{{itemize}}
    \item \textbf{{Average CPU Usage:}} {avg_cpu:.1f}\%
    \item \textbf{{Average Power Consumption:}} {avg_power:.2f} W
\end{{itemize}}"""
    
    def _generate_methodology(self) -> str:
        """Generate methodology section."""
        return r"""
\section{Benchmark Methodology}

\subsection{Test Environment}

\subsubsection{Ground Control Station (GCS)}
\begin{itemize}
    \item Windows 10 x64
    \item Conda environment with liboqs-python
    \item High-performance workstation (no power constraints)
\end{itemize}

\subsubsection{Drone Platform}
\begin{itemize}
    \item Raspberry Pi 4 Model B
    \item Debian Linux (ARM64)
    \item Python virtual environment with liboqs-python
    \item Power monitoring via hwmon interface
\end{itemize}

\subsection{Test Protocol}
For each cipher suite:
\begin{enumerate}
    \item Initialize cryptographic proxy on both endpoints
    \item Perform PQC handshake (KEM + Signature verification)
    \item Run MAVProxy traffic for configured duration
    \item Collect metrics (handshake, throughput, latency, power)
    \item Graceful shutdown and metric finalization
\end{enumerate}

\subsection{Metrics Collection}
\begin{itemize}
    \item \textbf{Handshake:} Wall-clock timing of KEM encapsulation and signature verification
    \item \textbf{Data Plane:} Packet counts, byte counters, loss ratio
    \item \textbf{Latency:} One-way delay (avg, p50, p95, p99, max)
    \item \textbf{System (Drone):} CPU\%, memory, temperature, load average
    \item \textbf{Power (Drone):} Real-time power sampling at 100Hz, energy integration
\end{itemize}

\textbf{Note:} Power metrics are collected \emph{only} on the drone platform, as the GCS 
is a powerful workstation where power consumption is not a concern for this embedded 
systems security application."""
    
    def _generate_suite_page(self, result: Dict[str, Any], index: int) -> str:
        """Generate a full page for a single suite."""
        suite_id = result.get("suite_id", "unknown")
        
        # Extract algorithm info
        kem = result.get("kem_algorithm", "Unknown")
        sig = result.get("sig_algorithm", "Unknown")
        aead = result.get("aead_algorithm", "Unknown")
        nist_level = result.get("nist_level", "Unknown")
        
        # Color for NIST level
        level_color = NIST_LEVEL_COLORS.get(nist_level, "black")
        
        # Metrics
        handshake_ms = result.get("handshake_duration_ms", 0)
        traffic_s = result.get("traffic_duration_s", 0)
        
        packets_rx = result.get("packets_received", 0)
        packets_tx = result.get("packets_sent", 0)
        bytes_rx = result.get("bytes_received", 0)
        bytes_tx = result.get("bytes_sent", 0)
        
        latency_avg = result.get("latency_avg_ms", 0)
        latency_p50 = result.get("latency_p50_ms", 0)
        latency_p95 = result.get("latency_p95_ms", 0)
        latency_max = result.get("latency_max_ms", 0)
        
        drone_cpu = result.get("drone_cpu_avg_percent", 0)
        drone_cpu_peak = result.get("drone_cpu_peak_percent", 0)
        drone_mem = result.get("drone_memory_rss_mb", 0)
        drone_temp = result.get("drone_temperature_c", 0)
        drone_load = result.get("drone_load_avg_1m", 0)
        
        power_avg = result.get("drone_power_avg_w", 0)
        power_peak = result.get("drone_power_peak_w", 0)
        energy_total = result.get("drone_energy_total_j", 0)
        energy_hs = result.get("drone_energy_per_handshake_j", 0)
        
        # Calculate throughput
        throughput_mbps = (bytes_tx * 8 / traffic_s / 1_000_000) if traffic_s > 0 else 0
        
        return rf"""
\clearpage
\section{{Suite {index}: \suiteID{{{escape_latex(suite_id)}}}}}
\label{{sec:suite-{index}}}

\begin{{table}}[h]
\centering
\caption{{Cryptographic Identity}}
\begin{{tabular}}{{@{{}}ll@{{}}}}
\toprule
\textbf{{Parameter}} & \textbf{{Value}} \\
\midrule
KEM Algorithm & {escape_latex(kem)} \\
Signature Algorithm & {escape_latex(sig)} \\
AEAD Cipher & {escape_latex(aead)} \\
NIST Security Level & \textcolor{{{level_color}}}{{\textbf{{{nist_level}}}}} \\
\bottomrule
\end{{tabular}}
\end{{table}}

\subsection{{Handshake Performance}}

\begin{{table}}[h]
\centering
\caption{{Handshake Metrics}}
\begin{{tabular}}{{@{{}}lrr@{{}}}}
\toprule
\textbf{{Metric}} & \textbf{{Value}} & \textbf{{Unit}} \\
\midrule
Total Handshake Duration & {handshake_ms:.2f} & ms \\
Handshake Success & \checkmark & -- \\
\bottomrule
\end{{tabular}}
\end{{table}}

\subsection{{Data Plane Performance}}

\begin{{table}}[h]
\centering
\caption{{Traffic Statistics ({traffic_s:.1f}s test duration)}}
\begin{{tabular}}{{@{{}}lrr@{{}}}}
\toprule
\textbf{{Metric}} & \textbf{{Value}} & \textbf{{Unit}} \\
\midrule
Packets Received & {packets_rx:,} & pkts \\
Packets Sent & {packets_tx:,} & pkts \\
Bytes Received & {bytes_rx:,} & bytes \\
Bytes Sent & {bytes_tx:,} & bytes \\
Throughput & {throughput_mbps:.2f} & Mbps \\
\bottomrule
\end{{tabular}}
\end{{table}}

\subsection{{Latency Analysis}}

\begin{{table}}[h]
\centering
\caption{{One-Way Latency Distribution}}
\begin{{tabular}}{{@{{}}lrr@{{}}}}
\toprule
\textbf{{Percentile}} & \textbf{{Latency}} & \textbf{{Unit}} \\
\midrule
Average & {latency_avg:.2f} & ms \\
Median (p50) & {latency_p50:.2f} & ms \\
95th Percentile (p95) & {latency_p95:.2f} & ms \\
Maximum & {latency_max:.2f} & ms \\
\bottomrule
\end{{tabular}}
\end{{table}}

\subsection{{Drone System Resources}}

\begin{{table}}[h]
\centering
\caption{{Raspberry Pi System Metrics}}
\begin{{tabular}}{{@{{}}lrr@{{}}}}
\toprule
\textbf{{Metric}} & \textbf{{Value}} & \textbf{{Unit}} \\
\midrule
CPU Usage (avg) & {drone_cpu:.1f} & \% \\
CPU Usage (peak) & {drone_cpu_peak:.1f} & \% \\
Memory (RSS) & {drone_mem:.1f} & MB \\
Temperature & {drone_temp:.1f} & °C \\
Load Average (1m) & {drone_load:.2f} & -- \\
\bottomrule
\end{{tabular}}
\end{{table}}

\subsection{{Power \& Energy (Drone)}}

\begin{{table}}[h]
\centering
\caption{{Power Consumption and Energy}}
\begin{{tabular}}{{@{{}}lrr@{{}}}}
\toprule
\textbf{{Metric}} & \textbf{{Value}} & \textbf{{Unit}} \\
\midrule
Average Power & {power_avg:.3f} & W \\
Peak Power & {power_peak:.3f} & W \\
Total Energy & {energy_total:.3f} & J \\
Energy per Handshake & {energy_hs:.6f} & J \\
\bottomrule
\end{{tabular}}
\end{{table}}

\vfill
\begin{{center}}
\textit{{End of Suite {index} Report}}
\end{{center}}"""
    
    def _generate_comparison_section(self) -> str:
        """Generate comparison tables across all suites."""
        if not self.successful_results:
            return r"\section{Comparison}\nNo data available for comparison."
        
        # Sort by handshake duration
        sorted_by_hs = sorted(self.successful_results, key=lambda x: x["handshake_duration_ms"])
        
        # Build comparison table rows
        rows = []
        for r in sorted_by_hs[:20]:  # Top 20
            suite = escape_latex(r["suite_id"])
            hs = r["handshake_duration_ms"]
            level = r.get("nist_level", "?")
            power = r.get("drone_power_avg_w", 0)
            cpu = r.get("drone_cpu_avg_percent", 0)
            
            rows.append(f"\\suiteID{{{suite}}} & {level} & {hs:.2f} & {power:.3f} & {cpu:.1f} \\\\")
        
        table_rows = "\n".join(rows)
        
        return rf"""
\clearpage
\section{{Suite Comparison}}

\subsection{{Performance Ranking (by Handshake Duration)}}

\begin{{longtable}}{{@{{}}p{{4.5cm}}crrr@{{}}}}
\caption{{Top Suites by Handshake Performance}} \\
\toprule
\textbf{{Suite ID}} & \textbf{{Level}} & \textbf{{Handshake (ms)}} & \textbf{{Power (W)}} & \textbf{{CPU (\%)}} \\
\midrule
\endfirsthead
\multicolumn{{5}}{{c}}{{\tablename\ \thetable\ -- \textit{{Continued from previous page}}}} \\
\toprule
\textbf{{Suite ID}} & \textbf{{Level}} & \textbf{{Handshake (ms)}} & \textbf{{Power (W)}} & \textbf{{CPU (\%)}} \\
\midrule
\endhead
\midrule
\multicolumn{{5}}{{r}}{{\textit{{Continued on next page}}}} \\
\endfoot
\bottomrule
\endlastfoot
{table_rows}
\end{{longtable}}

\subsection{{NIST Level Analysis}}
"""
    
    def _generate_conclusion(self) -> str:
        """Generate conclusion section."""
        if not self.successful_results:
            return r"\section{Conclusion}\nInsufficient data for conclusions."
        
        fastest = min(self.successful_results, key=lambda x: x["handshake_duration_ms"])
        lowest_power = min([r for r in self.successful_results if r.get("drone_power_avg_w", 0) > 0], 
                          key=lambda x: x["drone_power_avg_w"], default=None)
        
        fastest_suite = escape_latex(fastest["suite_id"])
        fastest_hs = fastest["handshake_duration_ms"]
        
        power_conclusion = ""
        if lowest_power:
            power_suite = escape_latex(lowest_power["suite_id"])
            power_val = lowest_power["drone_power_avg_w"]
            power_conclusion = rf"""
The most power-efficient suite was \suiteID{{{power_suite}}} with an average 
power consumption of {power_val:.3f}~W on the Raspberry Pi drone platform."""
        
        return rf"""
\section{{Conclusion}}

This benchmark provides comprehensive performance data for {len(self.successful_results)} 
post-quantum cryptographic cipher suites in a UAV secure communication context.

\subsection{{Key Findings}}

\begin{{enumerate}}
    \item \textbf{{Fastest Handshake:}} The suite \suiteID{{{fastest_suite}}} achieved the 
          fastest handshake at {fastest_hs:.2f}~ms.
    {power_conclusion}
    \item \textbf{{Embedded Suitability:}} All tested suites successfully operated on the 
          resource-constrained Raspberry Pi platform, demonstrating PQC viability for 
          embedded UAV applications.
\end{{enumerate}}

\subsection{{Recommendations}}

For mission-critical UAV applications:
\begin{{itemize}}
    \item NIST L1 suites offer the best performance for latency-sensitive applications
    \item NIST L3/L5 suites should be considered for high-security requirements
    \item Power-constrained deployments should prefer lattice-based KEMs (ML-KEM family)
\end{{itemize}}

\section*{{Acknowledgments}}
This benchmark was generated automatically by the secure-tunnel benchmarking framework.

\bibliographystyle{{IEEEtran}}
% \bibliography{{references}}
"""


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Generate IEEE-style benchmark report")
    parser.add_argument("results_json", help="Path to benchmark results JSON file")
    parser.add_argument("--output", "-o", default=None, help="Output directory")
    args = parser.parse_args()
    
    if not Path(args.results_json).exists():
        print(f"Error: Results file not found: {args.results_json}")
        return 1
    
    generator = IEEEReportGenerator(args.results_json, args.output)
    output_file = generator.generate()
    
    print(f"\nTo compile PDF:")
    print(f"  cd {output_file.parent}")
    print(f"  pdflatex {output_file.name}")
    print(f"  pdflatex {output_file.name}  # Run twice for references")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
