#!/usr/bin/env python3
"""
Full Analysis Pipeline Execution Script
========================================

Run this script on the remote system to:
1. Parse all benchmark JSON files
2. Compute statistical summaries
3. Export structured CSV files
4. Generate visualizations

Usage:
    cd ~/secure-tunnel
    source ~/cenv/bin/activate
    python3 bench/analysis/run_analysis.py

Output directories:
    bench_analysis/csv/       - Raw data exports
    bench_analysis/stats/     - Statistical summaries
    bench_analysis/plots/     - Generated figures
"""

import sys
import os
from pathlib import Path

# Ensure we can import from the analysis package
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

def main():
    print("=" * 70)
    print("PQC BENCHMARK ANALYSIS PIPELINE")
    print("=" * 70)
    
    # Check bench_results exists
    bench_results = Path("bench_results")
    if not bench_results.exists():
        print(f"ERROR: {bench_results} directory not found")
        print("Run this script from the secure-tunnel root directory")
        sys.exit(1)
    
    raw_dir = bench_results / "raw"
    if not raw_dir.exists():
        print(f"ERROR: {raw_dir} directory not found")
        sys.exit(1)
    
    # Count benchmark files
    kem_files = list((raw_dir / "kem").glob("*.json")) if (raw_dir / "kem").exists() else []
    sig_files = list((raw_dir / "sig").glob("*.json")) if (raw_dir / "sig").exists() else []
    aead_files = list((raw_dir / "aead").glob("*.json")) if (raw_dir / "aead").exists() else []
    suite_files = list((raw_dir / "suites").glob("*.json")) if (raw_dir / "suites").exists() else []
    
    total_files = len(kem_files) + len(sig_files) + len(aead_files) + len(suite_files)
    
    print(f"\nBenchmark files found:")
    print(f"  KEM:    {len(kem_files)}")
    print(f"  SIG:    {len(sig_files)}")
    print(f"  AEAD:   {len(aead_files)}")
    print(f"  Suites: {len(suite_files)}")
    print(f"  Total:  {total_files}")
    
    if total_files == 0:
        print("\nERROR: No benchmark files found")
        sys.exit(1)
    
    # Step 1: Run data ingestion and statistical analysis
    print("\n" + "-" * 70)
    print("STEP 1: Data Ingestion and Statistical Analysis")
    print("-" * 70)
    
    try:
        from benchmark_analysis import main as run_analysis
        run_analysis()
        print("✓ Analysis completed successfully")
    except ImportError as e:
        print(f"ERROR: Could not import benchmark_analysis: {e}")
        print("Ensure benchmark_analysis.py is in the same directory")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR during analysis: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    # Step 2: Generate visualizations
    print("\n" + "-" * 70)
    print("STEP 2: Generating Visualizations")
    print("-" * 70)
    
    try:
        # Check for matplotlib
        import matplotlib
        matplotlib.use('Agg')  # Non-interactive backend
        
        from benchmark_plots import main as run_plots
        run_plots()
        print("✓ Plots generated successfully")
    except ImportError as e:
        if 'matplotlib' in str(e):
            print(f"WARNING: matplotlib not available: {e}")
            print("Skipping plot generation")
            print("Install with: pip install matplotlib")
        else:
            print(f"ERROR: Could not import benchmark_plots: {e}")
            sys.exit(1)
    except Exception as e:
        print(f"ERROR during plot generation: {e}")
        import traceback
        traceback.print_exc()
        # Don't exit, plots are optional
    
    # Summary
    print("\n" + "=" * 70)
    print("ANALYSIS COMPLETE")
    print("=" * 70)
    
    output_dir = Path("bench_analysis")
    
    if output_dir.exists():
        csv_dir = output_dir / "csv"
        stats_dir = output_dir / "stats"
        plots_dir = output_dir / "plots"
        
        print("\nOutput files:")
        
        if csv_dir.exists():
            csv_files = list(csv_dir.glob("*.csv"))
            print(f"\n  CSV files ({len(csv_files)}):")
            for f in sorted(csv_files):
                size = f.stat().st_size
                print(f"    - {f.name} ({size:,} bytes)")
        
        if stats_dir.exists():
            stats_files = list(stats_dir.glob("*.csv"))
            print(f"\n  Stats files ({len(stats_files)}):")
            for f in sorted(stats_files):
                size = f.stat().st_size
                print(f"    - {f.name} ({size:,} bytes)")
        
        if plots_dir.exists():
            plot_files = list(plots_dir.glob("*"))
            print(f"\n  Plot files ({len(plot_files)}):")
            for f in sorted(plot_files):
                size = f.stat().st_size
                print(f"    - {f.name} ({size:,} bytes)")
    
    print("\nAll values derived from: bench_results/raw/*.json")
    print("No metrics invented. No conclusions drawn.")


if __name__ == "__main__":
    main()
