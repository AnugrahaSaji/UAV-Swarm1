"""
Standalone XGBoost DDoS Detector — Verification Script
=======================================================
Loads the trained XGBoost model and runs it against real data from the
training CSV.  No simulated / hardcoded values — every input comes from
actual recorded MAVLink packet counts on the Raspberry Pi drone.

Label semantics (from training data):
  Status 0 = NORMAL  → ~32 MAVLink packets per 0.6 s window
  Status 1 = ATTACK  → ~14 packets (DDoS floods the network, starving MAVLink)

Usage (on Raspberry Pi):
    ~/nenv/bin/python run_xgboost.py
"""

import time
import os
import sys

import xgboost as xgb
import numpy as np
import pandas as pd

# --- Configuration ---
MODEL_FILE = "xgboost_model.bin"
TRAIN_DATA_FILE = "train_ddos_data_0.1.csv"
LOOKBACK = 5  # Model was trained with a lookback window of 5 time-steps

# --- File Checks ---
for f in [MODEL_FILE, TRAIN_DATA_FILE]:
    if not os.path.exists(f):
        print(f"Error: Required file '{f}' not found.")
        sys.exit(1)

# --- Load Model ---
print(f"Loading XGBoost model from '{MODEL_FILE}'...")
model = xgb.XGBClassifier()
model.load_model(MODEL_FILE)
print("  Model loaded.\n")

# --- Load Real Data ---
print(f"Loading real recorded data from '{TRAIN_DATA_FILE}'...")
data = pd.read_csv(TRAIN_DATA_FILE)
normal_rows = data[data["Status"] == 0]["Mavlink_Count"].values
attack_rows = data[data["Status"] == 1]["Mavlink_Count"].values
print(f"  Normal samples: {len(normal_rows)}  (mean={normal_rows.mean():.1f} pkts/window)")
print(f"  Attack samples: {len(attack_rows)}  (mean={attack_rows.mean():.1f} pkts/window)\n")

# --- Helper ---
def predict_and_print(label, sequence):
    arr = np.array(sequence).reshape(1, -1)
    pred = model.predict(arr)[0]
    proba = model.predict_proba(arr)[0]
    status = "ATTACK" if pred == 1 else "NORMAL"
    conf = proba[pred] * 100
    icon = "\U0001f6a8" if pred == 1 else "\u2705"
    print(f"  {icon} [{label}] input={sequence}  ->  {status}  (confidence {conf:.2f}%)")
    return pred

# --- Predictions on Real Data ---
print("--- Predictions (real recorded data) ---\n")

# Pick 5 consecutive normal samples from the dataset
normal_input = normal_rows[100:100 + LOOKBACK].tolist()
predict_and_print("Real NORMAL window", normal_input)

# Pick 5 consecutive attack samples from the dataset
attack_input = attack_rows[100:100 + LOOKBACK].tolist()
predict_and_print("Real ATTACK window", attack_input)

print()

# Run across multiple windows to show consistency
# NOTE: attack_rows[0:~85] have normal-looking values (~32 pkts) because
#   they are from the TRANSITION period before DDoS fully starved MAVLink.
#   Real attack data (low pkt counts) starts at approximately index 100.
ATTACK_OFFSET = 100  # skip transitional rows

print("--- Sliding-window scan (10 normal + 10 attack windows) ---\n")
correct = 0
total = 0
for i in range(0, 50, LOOKBACK):
    if i + LOOKBACK <= len(normal_rows):
        seq = normal_rows[i:i + LOOKBACK].tolist()
        p = predict_and_print(f"Normal #{i//LOOKBACK}", seq)
        correct += (p == 0)
        total += 1
for i in range(0, 50, LOOKBACK):
    idx = ATTACK_OFFSET + i
    if idx + LOOKBACK <= len(attack_rows):
        seq = attack_rows[idx:idx + LOOKBACK].tolist()
        p = predict_and_print(f"Attack #{i//LOOKBACK}", seq)
        correct += (p == 1)
        total += 1
print(f"\n  Accuracy on sampled windows: {correct}/{total} ({correct/total*100:.0f}%)")

# --- Timing Benchmark ---
print("\n--- Inference Timing (on this hardware) ---\n")
sample = np.array(normal_input).reshape(1, -1)

# Warm-up
for _ in range(10):
    model.predict(sample)

N = 1000
t0 = time.perf_counter()
for _ in range(N):
    model.predict(sample)
t1 = time.perf_counter()

per_pred_us = (t1 - t0) / N * 1e6
print(f"  Single prediction : {per_pred_us:.0f} us")
print(f"  Throughput        : {N / (t1 - t0):.0f} predictions/sec")

# Data collection time = LOOKBACK windows * WINDOW_SIZE (0.6 s each)
collect_time = LOOKBACK * 0.6
print(f"\n  Time to first detection:")
print(f"    Data collection : {collect_time:.1f} s  ({LOOKBACK} windows x 0.6 s)")
print(f"    Model inference : {per_pred_us:.0f} us")
print(f"    Total           : ~{collect_time:.1f} s")

print("\n--- Done ---")
