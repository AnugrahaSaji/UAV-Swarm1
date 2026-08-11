"""Unit Test Suite for Benchmark Framework (test_benchmark.py).

Tests cover:
    1. Metrics collection across all 11 categories.
    2. Statistical percentile computations (avg, min, max, P95).
    3. BenchmarkRunner full execution pipeline.
    4. BenchmarkReporter JSON generation (benchmark_results.json).
    5. BenchmarkReporter CSV generation (benchmark_results.csv).
    6. BenchmarkReporter Markdown report generation (summary.md).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmark.benchmark_metrics import BenchmarkMetrics, MetricStats, percentile
from benchmark.benchmark_report import BenchmarkReporter
from benchmark.benchmark_runner import BenchmarkRunner


class TestBenchmarkMetrics(unittest.TestCase):

    def test_percentile_calculation(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
        p50 = percentile(data, 50.0)
        p95 = percentile(data, 95.0)
        self.assertAlmostEqual(p50, 5.5, places=1)
        self.assertGreater(p95, 9.0)

    def test_metric_stats_from_samples(self):
        samples = [10.0, 20.0, 30.0, 40.0, 50.0]
        stats = MetricStats.from_samples(samples)
        self.assertEqual(stats.count, 5)
        self.assertEqual(stats.avg_ms, 30.0)
        self.assertEqual(stats.min_ms, 10.0)
        self.assertEqual(stats.max_ms, 50.0)
        self.assertGreater(stats.p95_ms, 40.0)


class TestBenchmarkRunnerAndReport(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_runner_and_report_generation(self):
        runner = BenchmarkRunner(iterations=5)
        metrics = runner.run_all()

        self.assertIsInstance(metrics, BenchmarkMetrics)
        self.assertGreater(metrics.smt_verification.count, 0)
        self.assertGreater(metrics.ascon_packets_per_sec, 0.0)

        reporter = BenchmarkReporter(metrics, output_dir=self.temp_dir.name)
        json_path, csv_path, md_path = reporter.generate_all()

        # 1. Verify JSON file
        self.assertTrue(json_path.exists())
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertIn("category_1_discovery_join", data)
            self.assertIn("category_2_smt_verification", data)
            self.assertIn("category_5_ascon", data)
            self.assertIn("category_11_power_ina219", data)

        # 2. Verify CSV file
        self.assertTrue(csv_path.exists())
        with open(csv_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            self.assertGreater(len(lines), 10)
            self.assertIn("Category,Metric,Value,Unit\n", lines[0])

        # 3. Verify Markdown summary.md
        self.assertTrue(md_path.exists())
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()
            self.assertIn("# Hierarchical UAV Swarm Performance Evaluation Report", text)
            self.assertIn("## 1. Discovery & Join Latency", text)
            self.assertIn("## 2. Cryptographic Performance (SMT, PQC & AEAD)", text)
            self.assertIn("## 5. System Resource Overhead & Power Telemetry", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
