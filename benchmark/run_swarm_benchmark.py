"""
Standalone Benchmark Runner for Hierarchical Swarm Architecture.

Executes Swarm empirical microbenchmarks and exports:
- benchmark/swarm/swarm_results.json
- benchmark/swarm/swarm_results.csv
- benchmark/swarm/swarm_summary.md
"""

import os
import sys

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from benchmark.swarm.swarm_benchmark import run_swarm_benchmark, export_swarm_reports


def main():
    output_dir = os.path.join(os.path.dirname(__file__), "swarm")
    print("==========================================================")
    print("   HIERARCHICAL SWARM ARCHITECTURE BENCHMARK RUNNER       ")
    print("==========================================================")

    data = run_swarm_benchmark(iterations=100)
    export_swarm_reports(data, output_dir)

    print("==========================================================")
    print("   SWARM BENCHMARK COMPLETED SUCCESSFULLY                 ")
    print("==========================================================")


if __name__ == "__main__":
    main()
