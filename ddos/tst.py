#!/usr/bin/env python3
"""Live Transformer IDS with reproducible warm-up and inference timing."""

import argparse
import json
import os
import sys
import tempfile
import time

import numpy as np
import pandas as pd
import torch
import torch.nn as nn

from features import FEATURE_NAMES, FlowFeatureExtractor, generate_synthetic_features
from severity import SeverityReporter

_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_DIR, "models", "tst_model.pth")
TST_FEATURE_NAMES = FEATURE_NAMES[:46]

DEFAULT_IFACE = "wlan0"
DEFAULT_WINDOW = 100
DEFAULT_THRESHOLD = 0.50
DEFAULT_WARMUP_ITERATIONS = 200
DEFAULT_METRICS_PATH = "/tmp/tst_metrics.json"
DEFAULT_INFERENCE_LOG = "/tmp/tst_inference.jsonl"


class TransformerIDS(nn.Module):
    """Transformer architecture matching the stored CIC-IoT-2023 checkpoint."""

    def __init__(
        self,
        input_dim=46,
        num_classes=6,
        heads=4,
        hidden_dim=512,
        layers=1,
    ):
        super().__init__()
        self.input_fc = nn.Linear(input_dim, hidden_dim)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=hidden_dim,
            nhead=heads,
            dim_feedforward=hidden_dim,
            batch_first=True,
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=layers)
        self.classifier = nn.Linear(hidden_dim, num_classes)

    def forward(self, x):
        if x.dim() == 1:
            x = x.unsqueeze(0)
        x = self.input_fc(x).unsqueeze(1)
        x = self.encoder(x)
        x = x.mean(dim=1)
        return self.classifier(x)


def load_model(path=None):
    """Load the Transformer model, fitted scaler, and label encoder."""
    path = path or MODEL_PATH
    if not os.path.exists(path):
        print(f"Error: model not found: {path}", file=sys.stderr)
        sys.exit(1)

    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    model = TransformerIDS(
        input_dim=46,
        num_classes=checkpoint["num_classes"],
    )
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    scaler = checkpoint["scaler"]
    label_encoder = checkpoint["label_encoder"]
    id_to_label = {i: c for i, c in enumerate(label_encoder.classes_)}
    return model, scaler, id_to_label


def _classify(proba, id_to_label):
    pred_id = int(np.argmax(proba))
    confidence = float(proba[pred_id])
    label = id_to_label.get(pred_id, f"class_{pred_id}")
    is_attack = label not in ("Unknown",)
    severity = SeverityReporter.severity_from_confidence(confidence, is_attack)
    return label, confidence, severity


def predict(model, scaler, id_to_label, features):
    """Compatibility helper returning label, confidence, and severity."""
    result = predict_timed(model, scaler, id_to_label, features)
    return result[0], result[1], result[2]


def predict_timed(model, scaler, id_to_label, features):
    """Return prediction plus preprocessing, model, and total latency in ms."""
    total_start_ns = time.perf_counter_ns()
    df = pd.DataFrame([features])
    df = df.reindex(columns=TST_FEATURE_NAMES, fill_value=0)
    x_values = scaler.transform(df)
    preprocess_end_ns = time.perf_counter_ns()

    with torch.inference_mode():
        logits = model(torch.as_tensor(x_values, dtype=torch.float32))
        proba = torch.softmax(logits, dim=1).numpy()[0]
    model_end_ns = time.perf_counter_ns()

    label, confidence, severity = _classify(proba, id_to_label)
    return (
        label,
        confidence,
        severity,
        (preprocess_end_ns - total_start_ns) / 1e6,
        (model_end_ns - preprocess_end_ns) / 1e6,
        (model_end_ns - total_start_ns) / 1e6,
    )


def _percentile(values, q):
    if not values:
        return None
    return round(float(np.percentile(np.asarray(values, dtype=np.float64), q)), 6)


def latency_summary(values):
    """Summarize a latency series without retaining it in the status JSON."""
    if not values:
        return {
            "count": 0,
            "mean_ms": None,
            "median_ms": None,
            "p95_ms": None,
            "p99_ms": None,
            "min_ms": None,
            "max_ms": None,
        }
    arr = np.asarray(values, dtype=np.float64)
    return {
        "count": int(arr.size),
        "mean_ms": round(float(arr.mean()), 6),
        "median_ms": _percentile(values, 50),
        "p95_ms": _percentile(values, 95),
        "p99_ms": _percentile(values, 99),
        "min_ms": round(float(arr.min()), 6),
        "max_ms": round(float(arr.max()), 6),
    }


def atomic_write_json(path, payload):
    target = os.path.abspath(path)
    directory = os.path.dirname(target) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(temp_path, target)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def append_jsonl(path, payload):
    target = os.path.abspath(path)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    with open(target, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Live Transformer DDoS detector with timing telemetry"
    )
    parser.add_argument("--iface", default=DEFAULT_IFACE)
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument(
        "--warmup-iterations",
        type=int,
        default=DEFAULT_WARMUP_ITERATIONS,
    )
    parser.add_argument("--metrics-path", default=DEFAULT_METRICS_PATH)
    parser.add_argument("--inference-log", default=DEFAULT_INFERENCE_LOG)
    args = parser.parse_args()

    startup_wall_ns = time.time_ns()
    startup_mono_ns = time.monotonic_ns()
    loading_metrics = {
        "schema": "tst_runtime_metrics.v1",
        "status": "loading",
        "startup_wall_ns": startup_wall_ns,
        "startup_mono_ns": startup_mono_ns,
        "model_path": MODEL_PATH,
        "interface": args.iface,
        "window_packets": args.window,
        "threshold": args.threshold,
        "warmup_iterations_requested": args.warmup_iterations,
    }
    atomic_write_json(args.metrics_path, loading_metrics)

    print(f"[TST] Loading model from {MODEL_PATH}")
    load_start_ns = time.perf_counter_ns()
    model, scaler, id_to_label = load_model()
    model_load_ms = (time.perf_counter_ns() - load_start_ns) / 1e6
    model_parameters = int(sum(parameter.numel() for parameter in model.parameters()))
    print(
        f"[TST] Model loaded: {len(id_to_label)} classes, "
        f"{model_parameters:,} params, load={model_load_ms:.3f} ms"
    )

    warmup_features = generate_synthetic_features(n=1, attack=False)[0]
    warmup_latencies = []
    warmup_start_ns = time.perf_counter_ns()
    for _ in range(max(0, args.warmup_iterations)):
        warmup_latencies.append(
            predict_timed(model, scaler, id_to_label, warmup_features)[-1]
        )
    warmup_total_ms = (time.perf_counter_ns() - warmup_start_ns) / 1e6
    ready_wall_ns = time.time_ns()
    ready_mono_ns = time.monotonic_ns()

    base_metrics = {
        **loading_metrics,
        "status": "ready",
        "ready_wall_ns": ready_wall_ns,
        "ready_mono_ns": ready_mono_ns,
        "startup_to_ready_ms": round(
            (ready_mono_ns - startup_mono_ns) / 1e6, 6
        ),
        "model_load_ms": round(model_load_ms, 6),
        "model_parameters": model_parameters,
        "classes": id_to_label,
        "warmup_iterations_completed": len(warmup_latencies),
        "warmup_total_ms": round(warmup_total_ms, 6),
        "warmup_latency": latency_summary(warmup_latencies),
        "live_inference_count": 0,
        "preprocess_latency": latency_summary([]),
        "model_latency": latency_summary([]),
        "total_inference_latency": latency_summary([]),
    }
    atomic_write_json(args.metrics_path, base_metrics)
    with open(args.inference_log, "w", encoding="utf-8"):
        pass
    print(
        f"[TST] Warm-up complete: {len(warmup_latencies)} iterations "
        f"in {warmup_total_ms:.3f} ms; detector READY"
    )

    reporter = SeverityReporter()
    extractor = FlowFeatureExtractor(window_size=args.window)
    extractor.start(args.iface)
    print(
        f"[TST] Sniffing on '{args.iface}' "
        f"({args.window} packets per inference window)"
    )

    preprocess_latencies = []
    model_latencies = []
    total_latencies = []
    window_num = 0
    try:
        while True:
            batch = extractor.harvest()
            if not batch:
                time.sleep(0.01)
                continue

            for features in batch:
                window_num += 1
                (
                    label,
                    confidence,
                    severity,
                    preprocess_ms,
                    model_ms,
                    total_ms,
                ) = predict_timed(model, scaler, id_to_label, features)
                preprocess_latencies.append(preprocess_ms)
                model_latencies.append(model_ms)
                total_latencies.append(total_ms)

                record = {
                    "schema": "tst_inference.v1",
                    "window": window_num,
                    "wall_time_ns": time.time_ns(),
                    "monotonic_ns": time.monotonic_ns(),
                    "label": label,
                    "confidence": round(confidence, 6),
                    "severity": severity,
                    "n_packets": int(features.get("Number", 0)),
                    "rate": round(float(features.get("Rate", 0)), 6),
                    "preprocess_ms": round(preprocess_ms, 6),
                    "model_ms": round(model_ms, 6),
                    "total_ms": round(total_ms, 6),
                }
                append_jsonl(args.inference_log, record)

                reporter.report(
                    severity=severity,
                    tier="tst",
                    attack_type=label,
                    confidence=confidence,
                    details={
                        "window": window_num,
                        "n_packets": record["n_packets"],
                        "rate": round(record["rate"], 1),
                        "preprocess_ms": round(preprocess_ms, 3),
                        "model_ms": round(model_ms, 3),
                        "inference_total_ms": round(total_ms, 3),
                    },
                )

                metrics = dict(base_metrics)
                metrics.update(
                    {
                        "status": "running",
                        "last_update_wall_ns": time.time_ns(),
                        "live_inference_count": window_num,
                        "preprocess_latency": latency_summary(
                            preprocess_latencies
                        ),
                        "model_latency": latency_summary(model_latencies),
                        "total_inference_latency": latency_summary(total_latencies),
                        "last_prediction": record,
                    }
                )
                atomic_write_json(args.metrics_path, metrics)

                print(
                    f"[TST] window={window_num} label={label} "
                    f"confidence={confidence:.4f} severity={severity} "
                    f"packets={record['n_packets']} total_ms={total_ms:.3f}"
                )
    except KeyboardInterrupt:
        print(f"[TST] Stopped after {window_num} windows")


if __name__ == "__main__":
    main()
