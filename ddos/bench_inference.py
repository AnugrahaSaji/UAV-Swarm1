#!/usr/bin/env python3
"""
Inference Benchmark — LightGBM vs RandomForest
===============================================
Loads both pre-trained models and measures inference latency
on synthetic CIC-IoT-2023 feature vectors.

Reports per-model: mean, median, p95, p99 latency in milliseconds.
Useful for verifying Tier 1 (LightGBM) is fast enough for always-on
sentinel duty on Raspberry Pi 4.

Usage:
    python bench_inference.py
    python bench_inference.py --iterations 5000
    python bench_inference.py --warmup 200 --iterations 2000
"""

import argparse
import os
import pickle
import sys
import time
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

from features import FEATURE_NAMES, generate_synthetic_features

_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_PATHS = {
    "LightGBM": os.path.join(_DIR, "models", "lgbm_model.pkl"),
    "XGBoost": os.path.join(_DIR, "models", "xgb_model.pkl"),
    "RandomForest": os.path.join(_DIR, "models", "rf_model.pkl"),
}

DEFAULT_ITERATIONS = 1000
DEFAULT_WARMUP = 100
TEMPERATURE = 1.5


def bench_model(name: str, model, scaler, X: np.ndarray,
                warmup: int, iterations: int) -> dict:
    """Benchmark predict_proba + temperature scaling for one model."""

    # Warmup
    for _ in range(warmup):
        raw = model.predict_proba(X)[0]
        logits = np.log(raw + 1e-10)
        scaled = np.exp(logits / TEMPERATURE)
        _ = scaled / scaled.sum()

    # Timed iterations
    latencies = []
    for _ in range(iterations):
        t0 = time.perf_counter_ns()
        raw = model.predict_proba(X)[0]
        logits = np.log(raw + 1e-10)
        scaled = np.exp(logits / TEMPERATURE)
        _ = scaled / scaled.sum()
        t1 = time.perf_counter_ns()
        latencies.append((t1 - t0) / 1e6)  # ns → ms

    arr = np.array(latencies)
    return {
        "model": name,
        "iterations": iterations,
        "mean_ms": round(float(arr.mean()), 3),
        "median_ms": round(float(np.median(arr)), 3),
        "p95_ms": round(float(np.percentile(arr, 95)), 3),
        "p99_ms": round(float(np.percentile(arr, 99)), 3),
        "min_ms": round(float(arr.min()), 3),
        "max_ms": round(float(arr.max()), 3),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Benchmark LightGBM vs XGBoost vs RandomForest inference latency"
    )
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS,
                        help=f"Number of timed iterations (default: {DEFAULT_ITERATIONS})")
    parser.add_argument("--warmup", type=int, default=DEFAULT_WARMUP,
                        help=f"Warmup iterations (default: {DEFAULT_WARMUP})")
    args = parser.parse_args()

    # Generate a single synthetic feature vector (benign)
    feat = generate_synthetic_features(n=1, attack=False)[0]

    print(f"Benchmark: {args.warmup} warmup + {args.iterations} timed iterations")
    print("=" * 60)

    results = []
    for name, path in MODEL_PATHS.items():
        if not os.path.exists(path):
            print(f"  SKIP {name}: model not found at {path}")
            continue

        print(f"\nLoading {name}...", end=" ", flush=True)
        t0 = time.monotonic()
        with open(path, "rb") as f:
            bundle = pickle.load(f)
        load_time = time.monotonic() - t0
        print(f"loaded in {load_time:.2f}s")

        model = bundle["model"]
        scaler = bundle["scaler"]

        # Prepare input with this model's scaler
        df = pd.DataFrame([feat]).reindex(columns=FEATURE_NAMES, fill_value=0)
        X = scaler.transform(df)
        print(f"  Input shape: {X.shape}  (1 sample × {X.shape[1]} features)")

        # Quick sanity: run one prediction
        proba = model.predict_proba(X)[0]
        pred = int(np.argmax(proba))
        print(f"  Sanity check: class={pred}, proba_max={proba[pred]:.4f}")

        print(f"  Benchmarking...", end=" ", flush=True)
        stats = bench_model(name, model, scaler, X, args.warmup, args.iterations)
        results.append(stats)
        print("done")

        print(f"  mean={stats['mean_ms']:.3f} ms  "
              f"median={stats['median_ms']:.3f} ms  "
              f"p95={stats['p95_ms']:.3f} ms  "
              f"p99={stats['p99_ms']:.3f} ms")

    # Summary table
    if results:
        print("\n" + "=" * 60)
        print(f"{'Model':<15} {'Mean':>8} {'Median':>8} {'P95':>8} {'P99':>8} ms")
        print("-" * 60)
        for r in results:
            print(f"{r['model']:<15} {r['mean_ms']:>8.3f} {r['median_ms']:>8.3f} "
                  f"{r['p95_ms']:>8.3f} {r['p99_ms']:>8.3f}")
        print("=" * 60)

        # Speedup ratios relative to fastest (LightGBM)
        if len(results) >= 2:
            fastest = min(r["mean_ms"] for r in results)
            for r in results:
                ratio = r["mean_ms"] / max(fastest, 1e-6)
                print(f"  {r['model']}: {ratio:.1f}x vs fastest")


if __name__ == "__main__":
    main()
