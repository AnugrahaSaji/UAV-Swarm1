"""
Standalone Benchmark Runner for Sparse Merkle Tree (SMT).

Executes SMT empirical microbenchmarks and exports:
- benchmark/smt/smt_results.json
- benchmark/smt/smt_results.csv
- benchmark/smt/smt_summary.md
"""

import os
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from benchmark.smt.smt_benchmark import run_smt_benchmark, export_smt_reports


def main():
    output_dir = os.path.join(os.path.dirname(__file__), "smt")
    print("==========================================================")
    print("      SPARSE MERKLE TREE (SMT) BENCHMARK RUNNER           ")
    print("==========================================================")
    
    data = run_smt_benchmark(iterations=100, num_drones=8)
    export_smt_reports(data, output_dir)

    print("==========================================================")
    print("      SMT BENCHMARK COMPLETED SUCCESSFULLY                 ")
    print("==========================================================")


if __name__ == "__main__":
    main()
