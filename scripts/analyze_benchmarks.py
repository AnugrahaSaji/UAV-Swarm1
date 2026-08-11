#!/usr/bin/env python3
"""
Benchmark Analysis Script - scripts/analyze_benchmarks.py

Analyzes comprehensive benchmark data collected by sdrone_bench.py and sgcs_bench.py.

Usage:
    python -m scripts.analyze_benchmarks [--input PATH] [--output PATH]

Outputs:
    - Summary statistics per suite
    - Performance rankings
    - Policy recommendations
    - Visualization-ready CSV
"""

import os
import sys
import json
import argparse
import statistics
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.suites import get_all_suites

class BenchmarkAnalyzer:
    """Analyzes comprehensive benchmark data."""
    
    def __init__(self, data_path: Path):
        self.data_path = data_path
        self.records: List[Dict] = []
        self.suite_stats: Dict[str, Dict] = {}
        
    def load_data(self):
        """Load all JSONL files from data path."""
        if self.data_path.is_file():
            files = [self.data_path]
        else:
            files = list(self.data_path.glob("*.jsonl"))
        
        for f in files:
            print(f"Loading: {f}")
            with open(f, 'r') as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        try:
                            record = json.loads(line)
                            self.records.append(record)
                        except json.JSONDecodeError as e:
                            print(f"  Warning: Invalid JSON line: {e}")
        
        print(f"Loaded {len(self.records)} records")
        
    def analyze(self):
        """Perform comprehensive analysis."""
        if not self.records:
            print("No records to analyze!")
            return
        
        # Group by suite
        by_suite = defaultdict(list)
        for r in self.records:
            suite_id = r.get("suite_id", r.get("crypto_identity", {}).get("kem_algorithm", "unknown"))
            by_suite[suite_id].append(r)
        
        print(f"\nFound {len(by_suite)} unique suites")
        
        # Analyze each suite
        for suite_id, records in by_suite.items():
            self.suite_stats[suite_id] = self._analyze_suite(suite_id, records)
    
    def _analyze_suite(self, suite_id: str, records: List[Dict]) -> Dict:
        """Analyze metrics for a single suite."""
        stats = {
            "suite_id": suite_id,
            "sample_count": len(records),
            "handshake": {},
            "latency": {},
            "throughput": {},
            "power": {},
            "cpu": {},
            "memory": {},
        }
        
        # Extract metrics across all records
        hs_times = []
        rtt_means = []
        jitter_means = []
        throughputs = []
        power_means = []
        cpu_means = []
        mem_means = []
        
        for r in records:
            # Handshake
            hs = r.get("handshake", {})
            if "handshake_total_duration_ms" in hs:
                hs_times.append(hs["handshake_total_duration_ms"])
            
            # Latency & Jitter
            lj = r.get("latency_jitter", {})
            if "rtt_avg_ms" in lj:
                rtt_means.append(lj["rtt_avg_ms"])
            if "jitter_avg_ms" in lj:
                jitter_means.append(lj["jitter_avg_ms"])
            
            # Data Plane / Throughput
            dp = r.get("data_plane", {})
            if "goodput_mbps" in dp:
                throughputs.append(dp["goodput_mbps"])
            
            # Power & Energy
            pe = r.get("power_energy", {})
            if "power_avg_w" in pe:
                power_means.append(pe["power_avg_w"])
            
            # System Resources (Drone)
            sd = r.get("system_drone", {})
            if "cpu_usage_avg_percent" in sd:
                cpu_means.append(sd["cpu_usage_avg_percent"])
            if "memory_rss_mb" in sd:
                mem_means.append(sd["memory_rss_mb"])
        
        # Calculate statistics
        if hs_times:
            stats["handshake"] = self._calc_stats(hs_times, "ms")
        if rtt_means:
            stats["latency"]["rtt"] = self._calc_stats(rtt_means, "us")
        if jitter_means:
            stats["latency"]["jitter"] = self._calc_stats(jitter_means, "us")
        if throughputs:
            stats["throughput"] = self._calc_stats(throughputs, "kbps")
        if power_means:
            stats["power"] = self._calc_stats(power_means, "mW")
        if cpu_means:
            stats["cpu"] = self._calc_stats(cpu_means, "%")
        if mem_means:
            stats["memory"] = self._calc_stats(mem_means, "%")
        
        return stats
    
    def _calc_stats(self, values: List[float], unit: str) -> Dict:
        """Calculate statistics for a list of values."""
        if not values:
            return {}
        return {
            "unit": unit,
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0,
        }
    
    def rank_suites(self) -> Dict[str, List[str]]:
        """Rank suites by different criteria."""
        rankings = {}
        
        # By handshake time (lower is better)
        with_hs = [(s, stats["handshake"].get("mean", float('inf'))) 
                   for s, stats in self.suite_stats.items() if stats.get("handshake")]
        rankings["fastest_handshake"] = [s for s, _ in sorted(with_hs, key=lambda x: x[1])]
        
        # By latency (lower is better)
        with_lat = [(s, stats["latency"].get("rtt", {}).get("mean", float('inf')))
                    for s, stats in self.suite_stats.items() if stats.get("latency", {}).get("rtt")]
        rankings["lowest_latency"] = [s for s, _ in sorted(with_lat, key=lambda x: x[1])]
        
        # By power (lower is better)
        with_pow = [(s, stats["power"].get("mean", float('inf')))
                    for s, stats in self.suite_stats.items() if stats.get("power")]
        rankings["lowest_power"] = [s for s, _ in sorted(with_pow, key=lambda x: x[1])]
        
        # By throughput (higher is better)
        with_tput = [(s, stats["throughput"].get("mean", 0))
                     for s, stats in self.suite_stats.items() if stats.get("throughput")]
        rankings["highest_throughput"] = [s for s, _ in sorted(with_tput, key=lambda x: -x[1])]
        
        return rankings
    
    def generate_policy_recommendations(self) -> List[Dict]:
        """Generate policy recommendations based on analysis."""
        recommendations = []
        rankings = self.rank_suites()
        
        # Best overall (weighted score)
        scores = {}
        for suite_id, stats in self.suite_stats.items():
            # Normalize and weight different factors
            hs = stats.get("handshake", {}).get("mean", 500)  # Default high
            rtt = stats.get("latency", {}).get("rtt", {}).get("mean", 5000)
            power = stats.get("power", {}).get("mean", 3000)
            
            # Score: lower is better (weighted)
            scores[suite_id] = (hs * 0.3) + (rtt * 0.00005) + (power * 0.01)
        
        best_overall = sorted(scores.keys(), key=lambda s: scores[s])[:10]
        
        recommendations.append({
            "scenario": "general_purpose",
            "description": "Balanced performance for typical operations",
            "recommended_suites": best_overall[:5],
            "rationale": "Best weighted score across handshake, latency, and power"
        })
        
        # Low power scenarios
        if rankings.get("lowest_power"):
            recommendations.append({
                "scenario": "low_power",
                "description": "Battery-constrained operations",
                "recommended_suites": rankings["lowest_power"][:5],
                "rationale": "Lowest average power consumption"
            })
        
        # Low latency scenarios
        if rankings.get("lowest_latency"):
            recommendations.append({
                "scenario": "low_latency",
                "description": "Real-time control requirements",
                "recommended_suites": rankings["lowest_latency"][:5],
                "rationale": "Lowest RTT for time-critical operations"
            })
        
        # Fast handshake (frequent reconnects)
        if rankings.get("fastest_handshake"):
            recommendations.append({
                "scenario": "fast_reconnect",
                "description": "Frequent connection resets or handovers",
                "recommended_suites": rankings["fastest_handshake"][:5],
                "rationale": "Fastest handshake completion"
            })
        
        return recommendations
    
    def export_csv(self, output_path: Path):
        """Export analysis to CSV for visualization."""
        import csv
        
        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            
            # Header
            writer.writerow([
                "suite_id", "sample_count",
                "handshake_mean_ms", "handshake_stdev_ms",
                "rtt_mean_us", "rtt_stdev_us",
                "jitter_mean_us",
                "throughput_mean_kbps",
                "power_mean_mw", "power_stdev_mw",
                "cpu_mean_pct", "memory_mean_pct"
            ])
            
            # Data rows
            for suite_id, stats in sorted(self.suite_stats.items()):
                writer.writerow([
                    suite_id,
                    stats.get("sample_count", 0),
                    stats.get("handshake", {}).get("mean", ""),
                    stats.get("handshake", {}).get("stdev", ""),
                    stats.get("latency", {}).get("rtt", {}).get("mean", ""),
                    stats.get("latency", {}).get("rtt", {}).get("stdev", ""),
                    stats.get("latency", {}).get("jitter", {}).get("mean", ""),
                    stats.get("throughput", {}).get("mean", ""),
                    stats.get("power", {}).get("mean", ""),
                    stats.get("power", {}).get("stdev", ""),
                    stats.get("cpu", {}).get("mean", ""),
                    stats.get("memory", {}).get("mean", ""),
                ])
        
        print(f"Exported CSV: {output_path}")
    
    def print_summary(self):
        """Print analysis summary to console."""
        print("\n" + "=" * 70)
        print("BENCHMARK ANALYSIS SUMMARY")
        print("=" * 70)
        
        print(f"\nTotal records: {len(self.records)}")
        print(f"Suites analyzed: {len(self.suite_stats)}")
        
        # Rankings
        rankings = self.rank_suites()
        
        print("\n--- TOP 5 FASTEST HANDSHAKE ---")
        for i, s in enumerate(rankings.get("fastest_handshake", [])[:5], 1):
            stats = self.suite_stats[s]
            hs = stats.get("handshake", {}).get("mean", 0)
            print(f"  {i}. {s}: {hs:.2f} ms")
        
        print("\n--- TOP 5 LOWEST LATENCY ---")
        for i, s in enumerate(rankings.get("lowest_latency", [])[:5], 1):
            stats = self.suite_stats[s]
            rtt = stats.get("latency", {}).get("rtt", {}).get("mean", 0)
            print(f"  {i}. {s}: {rtt:.1f} us")
        
        print("\n--- TOP 5 LOWEST POWER ---")
        for i, s in enumerate(rankings.get("lowest_power", [])[:5], 1):
            stats = self.suite_stats[s]
            power = stats.get("power", {}).get("mean", 0)
            print(f"  {i}. {s}: {power:.1f} mW")
        
        # Policy recommendations
        print("\n--- POLICY RECOMMENDATIONS ---")
        for rec in self.generate_policy_recommendations():
            print(f"\n[{rec['scenario'].upper()}] {rec['description']}")
            print(f"  Recommended: {', '.join(rec['recommended_suites'][:3])}")
            print(f"  Rationale: {rec['rationale']}")
        
        print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Analyze benchmark data")
    parser.add_argument("--input", "-i", type=str, required=True,
                        help="Input JSONL file or directory")
    parser.add_argument("--output", "-o", type=str, default=None,
                        help="Output CSV file (optional)")
    parser.add_argument("--json", type=str, default=None,
                        help="Output JSON summary (optional)")
    args = parser.parse_args()
    
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: Input path not found: {input_path}")
        sys.exit(1)
    
    analyzer = BenchmarkAnalyzer(input_path)
    analyzer.load_data()
    analyzer.analyze()
    analyzer.print_summary()
    
    if args.output:
        analyzer.export_csv(Path(args.output))
    
    if args.json:
        output_data = {
            "generated_at": datetime.now().isoformat(),
            "record_count": len(analyzer.records),
            "suite_stats": analyzer.suite_stats,
            "rankings": analyzer.rank_suites(),
            "recommendations": analyzer.generate_policy_recommendations(),
        }
        with open(args.json, 'w') as f:
            json.dump(output_data, f, indent=2, default=str)
        print(f"Exported JSON: {args.json}")


if __name__ == "__main__":
    main()
