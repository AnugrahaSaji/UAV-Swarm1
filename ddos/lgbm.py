#!/usr/bin/env python3
"""
Live LightGBM DDoS Detector — Tier 1 Sentinel
==============================================
Sniffs network traffic, extracts CIC-IoT-2023 flow features, and
runs the pre-trained LightGBM model for fast binary/multi-class
DDoS detection.

Designed as the always-on first tier in the 3-tier cascade:
  Tier 1 (LightGBM) → Tier 2 (RF) → Tier 3 (TST)

The model classifies 15 classes (14 attack types + BenignTraffic)
from the CIC-IoT-2023 dataset.

Usage (requires root for packet capture):
    sudo python lgbm.py
    sudo python lgbm.py --iface eth0 --window 100 --threshold 0.5
"""

import argparse
import os
import pickle
import sys
import time

import numpy as np
import pandas as pd

from features import FEATURE_NAMES, FlowFeatureExtractor
from severity import SeverityReporter

# ── Paths ────────────────────────────────────────────────────────────
_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(_DIR, "models", "lgbm_model.pkl")

# ── Temperature scaling ─────────────────────────────────────────────
TEMPERATURE = 1.5

# ── Defaults ─────────────────────────────────────────────────────────
DEFAULT_IFACE = "wlan0"
DEFAULT_WINDOW = 100      # packets per window
DEFAULT_THRESHOLD = 0.50  # confidence threshold for attack alert


def load_model():
    """Load LightGBM model, scaler, and label mapping from bundled pickle.

    The pickle is a dict with keys: 'model', 'scaler', 'features', 'mapping'.
    """
    if not os.path.exists(MODEL_PATH):
        print(f"Error: model not found: {MODEL_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(MODEL_PATH, "rb") as f:
        bundle = pickle.load(f)

    model = bundle["model"]
    scaler = bundle["scaler"]
    label_mapping = bundle["mapping"]

    # Invert: {class_name: id} → {id: class_name}
    id_to_label = {v: k for k, v in label_mapping.items()}
    return model, scaler, id_to_label


def predict(model, scaler, id_to_label, features: dict) -> tuple:
    """Run single-window inference.

    Returns (label, confidence, severity).
    """
    df = pd.DataFrame([features])
    df = df.reindex(columns=FEATURE_NAMES, fill_value=0)
    X = scaler.transform(df)

    raw_proba = model.predict_proba(X)[0]

    # Temperature scaling — softens overconfident predictions
    logits = np.log(raw_proba + 1e-10)
    scaled = np.exp(logits / TEMPERATURE)
    proba = scaled / scaled.sum()

    pred_id = int(np.argmax(proba))
    confidence = float(proba[pred_id])
    label = id_to_label.get(pred_id, f"class_{pred_id}")

    is_attack = label != "BenignTraffic"
    severity = SeverityReporter.severity_from_confidence(confidence, is_attack)

    return label, confidence, severity


def main():
    parser = argparse.ArgumentParser(description="Live LightGBM DDoS detector (Tier 1)")
    parser.add_argument("--iface", default=DEFAULT_IFACE,
                        help=f"Network interface (default: {DEFAULT_IFACE})")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW,
                        help=f"Packets per window (default: {DEFAULT_WINDOW})")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD,
                        help=f"Confidence threshold (default: {DEFAULT_THRESHOLD})")
    args = parser.parse_args()

    print(f"[LGBM] Loading model from {MODEL_PATH}")
    model, scaler, id_to_label = load_model()
    print(f"[LGBM] Model loaded — {len(id_to_label)} classes, "
          f"window={args.window} pkts, threshold={args.threshold}")

    reporter = SeverityReporter()
    extractor = FlowFeatureExtractor(window_size=args.window)
    extractor.start(args.iface)

    print(f"[LGBM] Sniffing on '{args.iface}'... "
          f"(waiting for {args.window} packets per window)\n")

    window_num = 0
    try:
        while True:
            batch = extractor.harvest()
            if not batch:
                time.sleep(0.01)  # 10ms idle poll — no packets yet
                continue

            for features in batch:
                window_num += 1
                label, confidence, severity = predict(
                    model, scaler, id_to_label, features
                )

                is_attack = label != "BenignTraffic"

                # Report severity for scheduler
                reporter.report(
                    severity=severity,
                    tier="lgbm",
                    attack_type=label,
                    confidence=confidence,
                    details={
                        "window": window_num,
                        "n_packets": int(features.get("Number", 0)),
                        "rate": round(features.get("Rate", 0), 1),
                    },
                )

                # Console output
                if is_attack and confidence >= args.threshold:
                    print(
                        f"  [#{window_num}]  "
                        f"\033[91m>>> {label}  "
                        f"({confidence:.1%})  "
                        f"severity={severity}\033[0m"
                    )
                elif is_attack:
                    print(
                        f"  [#{window_num}]  "
                        f"\033[93m? {label}  "
                        f"({confidence:.1%})  "
                        f"below threshold\033[0m"
                    )
                else:
                    print(
                        f"  [#{window_num}]  "
                        f"\033[92mNORMAL  "
                        f"({confidence:.1%})\033[0m"
                    )

    except KeyboardInterrupt:
        print(f"\n[LGBM] Stopped after {window_num} windows.")


if __name__ == "__main__":
    main()
