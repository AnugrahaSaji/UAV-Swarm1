#!/usr/bin/env python3
"""
Complete Benchmark Runner - Run Full Suite Benchmark
suite_benchmarks/run_full_benchmark.py

This script orchestrates a complete benchmark run across all PQC suites.
It provides clear instructions and can be run on either GCS or Drone side.

Prerequisites:
1. GCS (Windows): Run sscheduler/sgcs.py first
2. Drone (Raspberry Pi): Run this script with --role drone

Usage:
    # On GCS (Windows):
    python -m sscheduler.sgcs
    
    # On Drone (Raspberry Pi):
    python suite_benchmarks/run_full_benchmark.py --role drone --interval 10
    
    # After benchmark completes, analyze results:
    python suite_benchmarks/analyze_benchmarks.py
"""

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime, timezone

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def print_banner():
    print("=" * 70)
    print("  PQC COMPREHENSIVE SUITE BENCHMARK")
    print("  Post-Quantum Cryptography Performance Evaluation")
    print("=" * 70)
    print()

def print_instructions():
    print("""
BENCHMARK SETUP INSTRUCTIONS
============================

This benchmark tests ALL PQC cryptographic suites by cycling through each
suite every 10 seconds, collecting detailed metrics including:
- Handshake time (total and per-primitive)
- Artifact sizes (public keys, ciphertexts, signatures)
- Power consumption (if INA219 available)
- Throughput and latency

STEP 1: Start GCS (Windows side)
--------------------------------
In a terminal on your Windows GCS machine:

    cd c:\\Users\\burak\\ptojects\\secure-tunnel
    conda activate oqs-dev
    python -m sscheduler.sgcs

This starts the GCS control server and MAVProxy.

STEP 2: Start Drone Benchmark (Raspberry Pi)
--------------------------------------------
SSH into your Raspberry Pi and run:

    cd ~/secure-tunnel
    source ~/cenv/bin/activate
    python -m sscheduler.sdrone_bench --interval 10 --filter-aead aesgcm

This will:
- Cycle through all 24 AESGCM suites (L1, L3, L5)
- Spend 10 seconds on each suite
- Collect handshake metrics for each
- Save results to logs/benchmarks/

For ALL 72 suites (including ChaCha and Ascon):

    python -m sscheduler.sdrone_bench --interval 10

STEP 3: Analyze Results
-----------------------
After benchmark completes, run analysis:

    python suite_benchmarks/analyze_benchmarks.py

This generates:
- Professional visualization charts (PNG/PDF)
- LaTeX tables for academic papers
- Comprehensive text report
- CSV export for further analysis

Output is saved to: suite_benchmarks/analysis_output/

TIMING ESTIMATES
----------------
- 24 suites (aesgcm only): ~4 minutes
- 72 suites (all AEADs): ~12 minutes
- Add warmup: +2 minutes
""")

def check_prerequisites():
    """Check that required modules are available."""
    errors = []
    
    try:
        from core.suites import list_suites
        suites = list_suites()
        print(f"✓ Found {len(suites)} registered suites")
    except ImportError as e:
        errors.append(f"✗ Cannot import core.suites: {e}")
    
    try:
        from sscheduler.benchmark_policy import BenchmarkPolicy
        print("✓ Benchmark policy module available")
    except ImportError as e:
        errors.append(f"✗ Cannot import benchmark_policy: {e}")
    
    # Check secrets directory
    secrets_dir = Path(__file__).parent.parent / "secrets" / "matrix"
    if secrets_dir.exists():
        key_count = len(list(secrets_dir.glob("cs-*")))
        print(f"✓ Found {key_count} suite key directories")
    else:
        errors.append(f"✗ Secrets directory not found: {secrets_dir}")
    
    if errors:
        print()
        print("ERRORS:")
        for e in errors:
            print(f"  {e}")
        return False
    
    return True

def show_suite_plan(filter_aead: str = None, max_suites: int = None):
    """Show the suites that will be benchmarked."""
    from sscheduler.benchmark_policy import BenchmarkPolicy
    
    policy = BenchmarkPolicy(cycle_interval_s=10.0, filter_aead=filter_aead)
    suite_list = policy.suite_list
    
    if max_suites:
        suite_list = suite_list[:max_suites]
    
    print()
    print(f"BENCHMARK PLAN: {len(suite_list)} suites")
    print("-" * 50)
    
    # Group by NIST level
    by_level = {"L1": [], "L3": [], "L5": []}
    for sid in suite_list:
        cfg = policy.all_suites.get(sid, {})
        level = cfg.get("nist_level", "?")
        if level in by_level:
            by_level[level].append(sid)
    
    for level in ["L1", "L3", "L5"]:
        suites = by_level[level]
        if suites:
            print(f"\nNIST Level {level} ({len(suites)} suites):")
            for sid in suites:
                print(f"  • {sid}")
    
    print()
    print(f"Total time estimate: {len(suite_list) * 10 / 60:.1f} minutes")
    print()

def main():
    parser = argparse.ArgumentParser(description="PQC Suite Benchmark Runner")
    parser.add_argument("--role", choices=["gcs", "drone"], 
                       help="Role to run (gcs or drone)")
    parser.add_argument("--interval", type=float, default=10.0,
                       help="Seconds per suite (default: 10)")
    parser.add_argument("--filter-aead", choices=["aesgcm", "chacha", "ascon"],
                       help="Only benchmark suites with this AEAD")
    parser.add_argument("--max-suites", type=int,
                       help="Maximum number of suites to test")
    parser.add_argument("--plan", action="store_true",
                       help="Show benchmark plan without running")
    parser.add_argument("--check", action="store_true",
                       help="Check prerequisites only")
    args = parser.parse_args()
    
    print_banner()
    
    if args.check:
        check_prerequisites()
        return
    
    if args.plan:
        check_prerequisites()
        show_suite_plan(args.filter_aead, args.max_suites)
        return
    
    if not args.role:
        print_instructions()
        print()
        print("Run with --plan to see benchmark suite list")
        print("Run with --check to verify prerequisites")
        print("Run with --role drone to start benchmark")
        return
    
    # Run actual benchmark
    if args.role == "gcs":
        print("Starting GCS scheduler...")
        print("This should be run as: python -m sscheduler.sgcs")
        return
    
    if args.role == "drone":
        check_prerequisites()
        show_suite_plan(args.filter_aead, args.max_suites)
        
        print("Starting benchmark in 5 seconds...")
        print("(Press Ctrl+C to cancel)")
        time.sleep(5)
        
        # Import and run benchmark
        from sscheduler.sdrone_bench import BenchmarkScheduler
        
        class Args:
            mav_master = "/dev/ttyACM0"
            interval = args.interval
            filter_aead = args.filter_aead
            max_suites = args.max_suites
            dry_run = False
        
        scheduler = BenchmarkScheduler(Args())
        scheduler.run()

if __name__ == "__main__":
    main()
