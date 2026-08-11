#!/usr/bin/env python3
"""
PQC Benchmark Data Analysis Script

This script performs data ingestion, statistical analysis, and visualization
of benchmark results. It does NOT make recommendations or draw conclusions.

All computed values are derived directly from benchmark JSON files.
"""

import json
import csv
import statistics
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

# =============================================================================
# NIST Level Mapping (derived from algorithm names and core/suites.py registry)
# =============================================================================

NIST_LEVEL_MAP = {
    # KEMs
    "ML-KEM-512": "L1",
    "ML-KEM-768": "L3",
    "ML-KEM-1024": "L5",
    "Classic-McEliece-348864": "L1",
    "Classic-McEliece-460896": "L3",
    "Classic-McEliece-8192128": "L5",
    "HQC-128": "L1",
    "HQC-192": "L3",
    "HQC-256": "L5",
    # Signatures
    "ML-DSA-44": "L1",
    "ML-DSA-65": "L3",
    "ML-DSA-87": "L5",
    "Falcon-512": "L1",
    "Falcon-1024": "L5",
    "SPHINCS+-SHA2-128s-simple": "L1",
    "SPHINCS+-SHA2-192s-simple": "L3",
    "SPHINCS+-SHA2-256s-simple": "L5",
    # AEADs (no NIST PQC level - classical)
    "AES-256-GCM": "Classical",
    "ChaCha20-Poly1305": "Classical",
    "Ascon-128a": "Classical",
    "Ascon-AEAD128": "Classical",
}

ALGORITHM_FAMILY_MAP = {
    # KEMs
    "ML-KEM-512": "ML-KEM",
    "ML-KEM-768": "ML-KEM",
    "ML-KEM-1024": "ML-KEM",
    "Classic-McEliece-348864": "Classic-McEliece",
    "Classic-McEliece-460896": "Classic-McEliece",
    "Classic-McEliece-8192128": "Classic-McEliece",
    "HQC-128": "HQC",
    "HQC-192": "HQC",
    "HQC-256": "HQC",
    # Signatures
    "ML-DSA-44": "ML-DSA",
    "ML-DSA-65": "ML-DSA",
    "ML-DSA-87": "ML-DSA",
    "Falcon-512": "Falcon",
    "Falcon-1024": "Falcon",
    "SPHINCS+-SHA2-128s-simple": "SPHINCS+",
    "SPHINCS+-SHA2-192s-simple": "SPHINCS+",
    "SPHINCS+-SHA2-256s-simple": "SPHINCS+",
    # AEADs
    "AES-256-GCM": "AES-GCM",
    "ChaCha20-Poly1305": "ChaCha20",
    "Ascon-128a": "Ascon",
    "Ascon-AEAD128": "Ascon",
}


@dataclass
class BenchmarkRecord:
    """Single benchmark measurement record."""
    algorithm: str
    algorithm_type: str  # KEM, SIG, AEAD, SUITE
    operation: str
    nist_level: str
    family: str
    iteration: int
    wall_time_ns: int
    perf_time_ns: int
    success: bool
    payload_size: Optional[int] = None
    public_key_bytes: Optional[int] = None
    secret_key_bytes: Optional[int] = None
    ciphertext_bytes: Optional[int] = None
    signature_bytes: Optional[int] = None
    shared_secret_bytes: Optional[int] = None
    source_file: str = ""


@dataclass
class AggregateStats:
    """Aggregate statistics for a group of measurements."""
    count: int
    mean_ns: float
    median_ns: float
    stdev_ns: float
    min_ns: float
    max_ns: float
    p95_ns: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "mean_ns": self.mean_ns,
            "median_ns": self.median_ns,
            "stdev_ns": self.stdev_ns,
            "min_ns": self.min_ns,
            "max_ns": self.max_ns,
            "p95_ns": self.p95_ns,
            "mean_ms": self.mean_ns / 1_000_000,
            "median_ms": self.median_ns / 1_000_000,
            "p95_ms": self.p95_ns / 1_000_000,
        }


def compute_stats(timings: List[int]) -> AggregateStats:
    """Compute aggregate statistics from a list of timing values (ns)."""
    if not timings:
        return AggregateStats(0, 0, 0, 0, 0, 0, 0)
    
    timings_sorted = sorted(timings)
    count = len(timings)
    mean_val = statistics.mean(timings)
    median_val = statistics.median(timings)
    stdev_val = statistics.stdev(timings) if count > 1 else 0
    min_val = min(timings)
    max_val = max(timings)
    p95_idx = int(count * 0.95)
    p95_val = timings_sorted[min(p95_idx, count - 1)]
    
    return AggregateStats(
        count=count,
        mean_ns=mean_val,
        median_ns=median_val,
        stdev_ns=stdev_val,
        min_ns=min_val,
        max_ns=max_val,
        p95_ns=p95_val,
    )


def get_suite_nist_level(suite_name: str) -> str:
    """Extract NIST level from suite name based on KEM component."""
    suite_lower = suite_name.lower()
    if "classicmceliece348864" in suite_lower:
        return "L1"
    elif "classicmceliece460896" in suite_lower:
        return "L3"
    elif "classicmceliece8192128" in suite_lower:
        return "L5"
    return "Unknown"


def parse_benchmark_file(filepath: Path) -> List[BenchmarkRecord]:
    """Parse a single benchmark JSON file and extract records."""
    records = []
    
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    algorithm = data.get("algorithm_name", "Unknown")
    algorithm_type = data.get("algorithm_type", "Unknown")
    operation = data.get("operation", "Unknown")
    payload_size = data.get("payload_size")
    
    # Determine NIST level
    if algorithm_type == "SUITE":
        nist_level = get_suite_nist_level(algorithm)
        family = "Suite"
    else:
        nist_level = NIST_LEVEL_MAP.get(algorithm, "Unknown")
        family = ALGORITHM_FAMILY_MAP.get(algorithm, "Unknown")
    
    # Size metrics (file-level)
    public_key_bytes = data.get("public_key_bytes")
    secret_key_bytes = data.get("secret_key_bytes")
    ciphertext_bytes = data.get("ciphertext_bytes")
    signature_bytes = data.get("signature_bytes")
    shared_secret_bytes = data.get("shared_secret_bytes")
    
    iterations = data.get("iterations", [])
    
    for it in iterations:
        if not it.get("success", False):
            continue
        
        record = BenchmarkRecord(
            algorithm=algorithm,
            algorithm_type=algorithm_type,
            operation=operation,
            nist_level=nist_level,
            family=family,
            iteration=it.get("iteration", 0),
            wall_time_ns=it.get("wall_time_ns", 0),
            perf_time_ns=it.get("perf_time_ns", 0),
            success=True,
            payload_size=payload_size,
            public_key_bytes=public_key_bytes,
            secret_key_bytes=secret_key_bytes,
            ciphertext_bytes=ciphertext_bytes,
            signature_bytes=signature_bytes,
            shared_secret_bytes=shared_secret_bytes,
            source_file=str(filepath.name),
        )
        records.append(record)
    
    return records


def ingest_all_benchmarks(bench_dir: Path) -> List[BenchmarkRecord]:
    """Ingest all benchmark files from the raw directory."""
    all_records = []
    raw_dir = bench_dir / "raw"
    
    categories = ["kem", "sig", "aead", "suites"]
    
    for category in categories:
        cat_dir = raw_dir / category
        if not cat_dir.exists():
            print(f"[WARN] Directory not found: {cat_dir}")
            continue
        
        for json_file in sorted(cat_dir.glob("*.json")):
            try:
                records = parse_benchmark_file(json_file)
                all_records.extend(records)
                print(f"[OK] Parsed {json_file.name}: {len(records)} records")
            except Exception as e:
                print(f"[ERR] Failed to parse {json_file}: {e}")
    
    return all_records


def export_to_csv(records: List[BenchmarkRecord], output_dir: Path):
    """Export records to CSV files, one per category."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Group by algorithm_type
    by_type: Dict[str, List[BenchmarkRecord]] = {}
    for r in records:
        key = r.algorithm_type.lower()
        if key not in by_type:
            by_type[key] = []
        by_type[key].append(r)
    
    fieldnames = [
        "algorithm", "algorithm_type", "operation", "nist_level", "family",
        "iteration", "wall_time_ns", "perf_time_ns", "payload_size",
        "public_key_bytes", "secret_key_bytes", "ciphertext_bytes",
        "signature_bytes", "shared_secret_bytes", "source_file"
    ]
    
    for algo_type, type_records in by_type.items():
        csv_path = output_dir / f"raw_{algo_type}.csv"
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in type_records:
                writer.writerow({
                    "algorithm": r.algorithm,
                    "algorithm_type": r.algorithm_type,
                    "operation": r.operation,
                    "nist_level": r.nist_level,
                    "family": r.family,
                    "iteration": r.iteration,
                    "wall_time_ns": r.wall_time_ns,
                    "perf_time_ns": r.perf_time_ns,
                    "payload_size": r.payload_size or "",
                    "public_key_bytes": r.public_key_bytes or "",
                    "secret_key_bytes": r.secret_key_bytes or "",
                    "ciphertext_bytes": r.ciphertext_bytes or "",
                    "signature_bytes": r.signature_bytes or "",
                    "shared_secret_bytes": r.shared_secret_bytes or "",
                    "source_file": r.source_file,
                })
        print(f"[CSV] Exported {len(type_records)} records to {csv_path}")
    
    # Also export all records
    all_csv = output_dir / "raw_all.csv"
    with open(all_csv, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in records:
            writer.writerow({
                "algorithm": r.algorithm,
                "algorithm_type": r.algorithm_type,
                "operation": r.operation,
                "nist_level": r.nist_level,
                "family": r.family,
                "iteration": r.iteration,
                "wall_time_ns": r.wall_time_ns,
                "perf_time_ns": r.perf_time_ns,
                "payload_size": r.payload_size or "",
                "public_key_bytes": r.public_key_bytes or "",
                "secret_key_bytes": r.secret_key_bytes or "",
                "ciphertext_bytes": r.ciphertext_bytes or "",
                "signature_bytes": r.signature_bytes or "",
                "shared_secret_bytes": r.shared_secret_bytes or "",
                "source_file": r.source_file,
            })
    print(f"[CSV] Exported {len(records)} total records to {all_csv}")


def compute_grouped_stats(
    records: List[BenchmarkRecord],
    group_keys: List[str]
) -> Dict[Tuple, AggregateStats]:
    """Compute statistics grouped by specified keys."""
    groups: Dict[Tuple, List[int]] = {}
    
    for r in records:
        key_parts = []
        for k in group_keys:
            key_parts.append(getattr(r, k, "Unknown"))
        key = tuple(key_parts)
        
        if key not in groups:
            groups[key] = []
        groups[key].append(r.wall_time_ns)
    
    stats = {}
    for key, timings in groups.items():
        stats[key] = compute_stats(timings)
    
    return stats


def export_stats_csv(
    stats: Dict[Tuple, AggregateStats],
    group_keys: List[str],
    output_path: Path,
    extra_info: Dict[Tuple, Dict] = None
):
    """Export grouped statistics to CSV."""
    fieldnames = group_keys + [
        "count", "mean_ns", "median_ns", "stdev_ns", "min_ns", "max_ns", "p95_ns",
        "mean_ms", "median_ms", "p95_ms"
    ]
    
    if extra_info:
        # Add extra columns from first entry
        sample_extra = next(iter(extra_info.values()), {})
        fieldnames.extend(sample_extra.keys())
    
    with open(output_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for key, stat in sorted(stats.items()):
            row = dict(zip(group_keys, key))
            row.update(stat.to_dict())
            if extra_info and key in extra_info:
                row.update(extra_info[key])
            writer.writerow(row)
    
    print(f"[STATS] Exported to {output_path}")


def analyze_by_nist_level(records: List[BenchmarkRecord], output_dir: Path):
    """Task 2.1: Statistics grouped by NIST level."""
    # Filter out classical (AEAD) and unknown
    pqc_records = [r for r in records if r.nist_level in ("L1", "L3", "L5")]
    
    stats = compute_grouped_stats(pqc_records, ["nist_level", "algorithm_type", "operation"])
    export_stats_csv(stats, ["nist_level", "algorithm_type", "operation"],
                     output_dir / "stats_by_nist_level.csv")
    return stats


def analyze_by_family(records: List[BenchmarkRecord], output_dir: Path):
    """Task 2.2: Statistics grouped by algorithm family."""
    stats = compute_grouped_stats(records, ["family", "operation"])
    export_stats_csv(stats, ["family", "operation"],
                     output_dir / "stats_by_family.csv")
    return stats


def analyze_same_level_different_kem(records: List[BenchmarkRecord], output_dir: Path):
    """Task 2.3: Compare KEMs at same NIST level."""
    kem_records = [r for r in records if r.algorithm_type == "KEM"]
    
    stats = compute_grouped_stats(kem_records, ["nist_level", "algorithm", "operation"])
    export_stats_csv(stats, ["nist_level", "algorithm", "operation"],
                     output_dir / "stats_kem_by_level.csv")
    return stats


def analyze_same_family_different_level(records: List[BenchmarkRecord], output_dir: Path):
    """Task 2.4: Compare same family across NIST levels."""
    pqc_records = [r for r in records if r.nist_level in ("L1", "L3", "L5")]
    
    stats = compute_grouped_stats(pqc_records, ["family", "nist_level", "operation"])
    export_stats_csv(stats, ["family", "nist_level", "operation"],
                     output_dir / "stats_family_by_level.csv")
    return stats


def analyze_operations(records: List[BenchmarkRecord], output_dir: Path):
    """Task 2.5: Operation-wise comparison."""
    # KEM operations
    kem_records = [r for r in records if r.algorithm_type == "KEM"]
    kem_stats = compute_grouped_stats(kem_records, ["algorithm", "operation"])
    export_stats_csv(kem_stats, ["algorithm", "operation"],
                     output_dir / "stats_kem_operations.csv")
    
    # SIG operations
    sig_records = [r for r in records if r.algorithm_type == "SIG"]
    sig_stats = compute_grouped_stats(sig_records, ["algorithm", "operation"])
    export_stats_csv(sig_stats, ["algorithm", "operation"],
                     output_dir / "stats_sig_operations.csv")
    
    # AEAD operations
    aead_records = [r for r in records if r.algorithm_type == "AEAD"]
    aead_stats = compute_grouped_stats(aead_records, ["algorithm", "operation", "payload_size"])
    export_stats_csv(aead_stats, ["algorithm", "operation", "payload_size"],
                     output_dir / "stats_aead_operations.csv")
    
    return kem_stats, sig_stats, aead_stats


def analyze_suite_vs_primitives(records: List[BenchmarkRecord], output_dir: Path):
    """Task 2.6: Full handshake vs sum of primitives (numeric only)."""
    suite_records = [r for r in records if r.algorithm_type == "SUITE"]
    kem_records = [r for r in records if r.algorithm_type == "KEM"]
    sig_records = [r for r in records if r.algorithm_type == "SIG"]
    
    suite_stats = compute_grouped_stats(suite_records, ["algorithm"])
    
    # Build primitive lookup
    kem_by_algo = {}
    for r in kem_records:
        key = (r.algorithm, r.operation)
        if key not in kem_by_algo:
            kem_by_algo[key] = []
        kem_by_algo[key].append(r.wall_time_ns)
    
    sig_by_algo = {}
    for r in sig_records:
        key = (r.algorithm, r.operation)
        if key not in sig_by_algo:
            sig_by_algo[key] = []
        sig_by_algo[key].append(r.wall_time_ns)
    
    # Output comparison
    rows = []
    for (suite_name,), suite_stat in suite_stats.items():
        row = {
            "suite": suite_name,
            "suite_mean_ms": suite_stat.mean_ns / 1_000_000,
            "suite_median_ms": suite_stat.median_ns / 1_000_000,
            "suite_p95_ms": suite_stat.p95_ns / 1_000_000,
            "iterations": suite_stat.count,
        }
        rows.append(row)
    
    csv_path = output_dir / "stats_suite_comparison.csv"
    if rows:
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"[STATS] Suite comparison exported to {csv_path}")
    
    return suite_stats


def load_environment(bench_dir: Path) -> Dict[str, Any]:
    """Load environment.json."""
    env_path = bench_dir / "environment.json"
    if env_path.exists():
        with open(env_path) as f:
            return json.load(f)
    return {}


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="PQC Benchmark Analysis")
    parser.add_argument("--bench-dir", type=str, default="bench_results",
                        help="Path to benchmark results directory")
    parser.add_argument("--output-dir", type=str, default="benchmarks/bench_analysis",
                        help="Path to output directory")
    args = parser.parse_args()
    
    bench_dir = Path(args.bench_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 60)
    print("PQC BENCHMARK DATA ANALYSIS")
    print("=" * 60)
    
    # Load environment
    env = load_environment(bench_dir)
    print(f"\nEnvironment: {env.get('hostname', 'Unknown')}")
    print(f"Git commit: {env.get('git_commit', 'Unknown')[:12]}...")
    print(f"Timestamp: {env.get('timestamp_iso', 'Unknown')}")
    
    # Task 1: Data Ingestion
    print("\n" + "=" * 60)
    print("TASK 1: DATA INGESTION")
    print("=" * 60)
    
    records = ingest_all_benchmarks(bench_dir)
    print(f"\nTotal records ingested: {len(records)}")
    
    csv_dir = output_dir / "csv"
    export_to_csv(records, csv_dir)
    
    # Task 2: Statistical Summaries
    print("\n" + "=" * 60)
    print("TASK 2: STATISTICAL SUMMARIES")
    print("=" * 60)
    
    stats_dir = output_dir / "stats"
    stats_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n2.1 By NIST Level:")
    analyze_by_nist_level(records, stats_dir)
    
    print("\n2.2 By Algorithm Family:")
    analyze_by_family(records, stats_dir)
    
    print("\n2.3 Same NIST Level, Different KEM:")
    analyze_same_level_different_kem(records, stats_dir)
    
    print("\n2.4 Same Family, Different NIST Level:")
    analyze_same_family_different_level(records, stats_dir)
    
    print("\n2.5 Operation-wise Comparison:")
    analyze_operations(records, stats_dir)
    
    print("\n2.6 Suite vs Primitives:")
    analyze_suite_vs_primitives(records, stats_dir)
    
    # Save environment for reference
    env_out = output_dir / "environment_copy.json"
    with open(env_out, 'w') as f:
        json.dump(env, f, indent=2)
    
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"Output directory: {output_dir}")


if __name__ == "__main__":
    main()
