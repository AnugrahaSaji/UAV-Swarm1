"""
Standalone TST (Time Series Transformer) DDoS Detector — Verification Script
=============================================================================
Loads the trained TST model and runs it against real recorded test data.
No simulated values — all inputs come from tcp_test_ddos_data_0.1.csv
which contains actual MAVLink packet counts captured on the drone.

IMPORTANT — The TST model has c_out=1 (single output neuron).
  This means it produces ONE logit, interpreted via **sigmoid**:
    sigmoid(logit) > 0.5  →  ATTACK (class 1)
    sigmoid(logit) <= 0.5 →  NORMAL (class 0)
  The original code used softmax on a single value, which ALWAYS
  returns [[1.0]] regardless of the logit — that was a critical bug.

Label semantics (from training data):
  Status 0 = NORMAL  → ~32 MAVLink packets per 0.6 s window
  Status 1 = ATTACK  → ~5-14 packets (DDoS starves MAVLink throughput)

Usage (on Raspberry Pi):
    ~/nenv/bin/python run_tst.py
"""

import time
import os
import sys
from statistics import mode

import torch
import pandas as pd
import numpy as np
from sklearn.preprocessing import StandardScaler

from tstplus import TSTPlus, _TSTBackbone, _TSTEncoder, _TSTEncoderLayer

# --- Configuration ---
MODEL_FILE = "tst_model.pth"
TRAIN_DATA_FILE = "train_ddos_data_0.1.csv"
TEST_DATA_FILE = "tcp_test_ddos_data_0.1.csv"
SEQ_LENGTH = 400  # Must match the model's training sequence length

# --- File Checks ---
for f in [MODEL_FILE, TRAIN_DATA_FILE, TEST_DATA_FILE, "tstplus.py"]:
    if not os.path.exists(f):
        print(f"Error: Required file '{f}' not found.")
        sys.exit(1)

# --- Load Model ---
print(f"Loading TST model from '{MODEL_FILE}'...")
model = torch.load(MODEL_FILE, map_location=torch.device("cpu"), weights_only=False)
model.eval()
print(f"  Model loaded.  c_out={model.c_out}  seq_len={model.seq_len}\n")

# --- Load & Fit Scaler ---
print(f"Fitting scaler on training data '{TRAIN_DATA_FILE}'...")
train_data = pd.read_csv(TRAIN_DATA_FILE)
scaler = StandardScaler()
scaler.fit(train_data[["Mavlink_Count", "Total_length"]])
print("  Scaler ready.\n")

# --- Load Test Data ---
print(f"Loading test data '{TEST_DATA_FILE}'...")
test_data = pd.read_csv(TEST_DATA_FILE)
print(f"  {len(test_data)} rows loaded.\n")


# --- Prediction Helper ---
def predict_sequence(seq):
    """
    Prepare a raw Mavlink_Count sequence and run inference.
    Returns (logit, sigmoid_probability, predicted_class).
    """
    seq_arr = np.array(seq, dtype=np.float64).reshape(-1, 1)
    # Scaler was fitted on 2 columns; we pad with a dummy zero column.
    dummy = np.zeros_like(seq_arr)
    scaled = scaler.transform(np.hstack([seq_arr, dummy]))[:, 0]

    x = torch.tensor(scaled, dtype=torch.float32).unsqueeze(0).unsqueeze(0)
    # Shape: [1, 1, SEQ_LENGTH]

    with torch.no_grad():
        logit = model(x).item()

    # c_out=1 → interpret with sigmoid, NOT softmax
    prob_attack = 1.0 / (1.0 + np.exp(-logit))
    pred = 1 if prob_attack > 0.5 else 0
    return logit, prob_attack, pred


# --- Sliding-Window Scan Over Test Data ---
print("--- Sliding-window scan across test data ---\n")
correct = 0
total = 0
for start in range(0, len(test_data) - SEQ_LENGTH, SEQ_LENGTH):
    end = start + SEQ_LENGTH
    seq = test_data["Mavlink_Count"].iloc[start:end].values
    true_labels = test_data["Status"].iloc[start:end].values
    true_class = int(round(true_labels.mean()))  # majority label
    avg_pkt = seq.mean()

    logit, prob, pred = predict_sequence(seq)
    status = "ATTACK" if pred == 1 else "NORMAL"
    true_str = "ATTACK" if true_class == 1 else "NORMAL"
    match = pred == true_class
    correct += match
    total += 1
    icon = "\u2705" if match else "\u274c"
    print(
        f"  {icon} Window [{start:5d}:{end:5d}]  "
        f"avg_pkt={avg_pkt:5.1f}  true={true_str:6s}  "
        f"pred={status:6s}  logit={logit:8.3f}  P(attack)={prob:.4f}"
    )

print(f"\n  Accuracy: {correct}/{total} ({correct/total*100:.0f}%)\n")

# --- Timing Benchmark ---
print("--- Inference Timing (on this hardware) ---\n")

# Warm-up
warm_seq = test_data["Mavlink_Count"].iloc[0:SEQ_LENGTH].values
for _ in range(3):
    predict_sequence(warm_seq)

N = 50
t0 = time.perf_counter()
for _ in range(N):
    predict_sequence(warm_seq)
t1 = time.perf_counter()

per_pred_ms = (t1 - t0) / N * 1000
print(f"  Single prediction : {per_pred_ms:.1f} ms")
print(f"  Throughput        : {N / (t1 - t0):.1f} predictions/sec")

collect_time = SEQ_LENGTH * 0.6
print(f"\n  Time to first detection:")
print(f"    Data collection : {collect_time:.0f} s  ({SEQ_LENGTH} windows x 0.6 s = {collect_time/60:.1f} min)")
print(f"    Model inference : {per_pred_ms:.1f} ms")
print(f"    Total           : ~{collect_time/60:.1f} min")

print("\n--- Done ---")