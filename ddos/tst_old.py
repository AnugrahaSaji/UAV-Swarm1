#!/usr/bin/env python3
"""
Old-style TST DDoS Detector  (detection-only)
==============================================
Faithful reproduction of the seniors' tst2.py architecture:
  - Continuous DataLoader inference loop (while True, NO sleep)
  - batch_size=4, shuffle=True on every pass
  - Re-creates sequences from CSV data every loop iteration
  - Runs as multiprocessing.Process (same as original)
  - ALSO sniffs real MAVLink packets (adds capture thread)

The key overhead pattern from tst2.py:
  ```
  while True:
      for inputs, _ in dataloader:
          model(inputs)  # no sleep, no pause
  ```
This saturates one CPU core with continuous tensor operations and
DataLoader worker overhead.

Stripped: Speck cipher, memory_profiler (unnecessary for detection).

Usage (requires root for raw packet capture):
    sudo ~/nenv/bin/python tst_old.py
    sudo ~/nenv/bin/python tst_old.py --iface eth0
"""

import argparse
import multiprocessing
import os
import sys
import time
from collections import deque
from threading import Thread
from statistics import mode

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

# TST model classes must be importable for torch.load (pickle)
from tstplus import TSTPlus, _TSTBackbone, _TSTEncoder, _TSTEncoderLayer

try:
    import scapy.all as scapy
except ImportError:
    print("Error: scapy not installed.  pip install scapy")
    sys.exit(1)

# ── Configuration ────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_FILE = os.path.join(SCRIPT_DIR, "tst_model.pth")
TRAIN_DATA_FILE = os.path.join(SCRIPT_DIR, "train_ddos_data_0.1.csv")
TEST_DATA_FILE = os.path.join(SCRIPT_DIR, "tcp_test_ddos_data_0.1.csv")
SEQ_LENGTH = 400
BATCH_SIZE = 4         # same as seniors' code
DEFAULT_IFACE = "wlan0"
WINDOW_SIZE = 0.60


# ======================================================================
# Packet Sniffer (capture thread — runs alongside TST loop)
# ======================================================================
def capture_thread(iface):
    """Sniff MAVLink packets — adds realistic network I/O load."""
    print(f"[Capture] Sniffing on {iface}...")

    packet_count = 0

    def packet_callback(packet):
        nonlocal packet_count
        if scapy.IP in packet and scapy.UDP in packet:
            if scapy.Raw in packet:
                if packet[scapy.Raw].load[:1] == b'\xfd':
                    packet_count += 1

    scapy.sniff(prn=packet_callback, store=0, iface=iface)


# ======================================================================
# Seniors' sequence creation (from tst2.py / tst1.py)
# ======================================================================
def create_sequences(data, seq_length):
    """Create overlapping sequences from DataFrame — same as seniors' code."""
    xs = []
    ys = []
    for i in range(len(data) - seq_length):
        x = data['Mavlink_Count'].iloc[i:(i + seq_length)].values
        y = mode(data['Status'].iloc[i: i + seq_length + 1].values)
        xs.append(x)
        ys.append(y)
    return np.array(xs), np.array(ys)


# ======================================================================
# TST continuous inference (from tst2.py — while True, no sleep)
# ======================================================================
def tst_continuous_inference():
    """
    Seniors' continuous TST inference loop.
    This is the EXACT pattern from tst2.py:
      - Load CSV test data
      - Create DataLoader(batch=4, shuffle=True)
      - while True: for inputs, _ in dataloader: model(inputs)

    No sleep, no pause. Saturates one CPU core.
    """
    print(f"[TST-OLD] Loading model from {MODEL_FILE}...")
    model = torch.load(MODEL_FILE, map_location=torch.device('cpu'),
                       weights_only=False)
    model.eval()
    print(f"[TST-OLD] Model loaded. c_out={model.c_out} seq_len={model.seq_len}")

    # Load and prepare data (same as seniors' code)
    print(f"[TST-OLD] Loading training data for scaler: {TRAIN_DATA_FILE}")
    train_data = pd.read_csv(TRAIN_DATA_FILE)
    scaler = StandardScaler()
    scaler.fit_transform(train_data[['Mavlink_Count', 'Total_length']])

    print(f"[TST-OLD] Loading test data: {TEST_DATA_FILE}")
    test_data = pd.read_csv(TEST_DATA_FILE)
    test_data[['Mavlink_Count', 'Total_length']] = scaler.transform(
        test_data[['Mavlink_Count', 'Total_length']])

    print(f"[TST-OLD] Creating sequences (seq_len={SEQ_LENGTH})...")
    X_test, y_test = create_sequences(test_data, SEQ_LENGTH)
    X_test_tensor = torch.tensor(X_test).float().unsqueeze(1)
    y_test_tensor = torch.tensor(y_test).float()
    test_dataset = TensorDataset(X_test_tensor, y_test_tensor)

    # DataLoader with shuffle=True, batch_size=4 — exactly as seniors had it
    dataloader = DataLoader(test_dataset, batch_size=BATCH_SIZE,
                            shuffle=True, drop_last=True)

    print(f"[TST-OLD] Dataset: {len(test_dataset)} sequences, "
          f"{len(dataloader)} batches of {BATCH_SIZE}")
    print(f"[TST-OLD] Starting continuous inference loop (NO sleep)...\n")

    loop_num = 0
    total_predictions = 0

    # ── THE SENIORS' PATTERN: while True, no sleep, no pause ──
    while True:
        loop_num += 1
        batch_count = 0
        attack_count = 0
        t_loop = time.time()

        with torch.no_grad():
            for inputs, labels in dataloader:
                outputs = model(inputs)
                # Interpret predictions (c_out=1 → sigmoid)
                probs = torch.sigmoid(outputs).squeeze()
                preds = (probs > 0.5).int()
                attack_count += preds.sum().item()
                batch_count += 1
                total_predictions += inputs.size(0)

        loop_time = time.time() - t_loop
        print(f"  [Loop #{loop_num}] {batch_count} batches, "
              f"{attack_count}/{batch_count * BATCH_SIZE} attacks, "
              f"{loop_time:.2f}s, total_preds={total_predictions}")


# ======================================================================
# Main — multiprocessing.Process (same as seniors' tst2.py)
# ======================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Old-style TST DDoS detector (continuous inference)")
    parser.add_argument("--iface", default=DEFAULT_IFACE,
                        help="Network interface (default: wlan0)")
    args = parser.parse_args()

    for f in [MODEL_FILE, TRAIN_DATA_FILE, TEST_DATA_FILE]:
        if not os.path.exists(f):
            print(f"Error: required file not found: {f}")
            sys.exit(1)

    print(f"[TST-OLD] Starting seniors' architecture")
    print(f"[TST-OLD] Model: {MODEL_FILE}")
    print(f"[TST-OLD] Pattern: while True → DataLoader(batch={BATCH_SIZE}, shuffle=True)")
    print(f"[TST-OLD] Interface: {args.iface}\n")

    # Start capture thread (adds network I/O load)
    t_cap = Thread(target=capture_thread, args=(args.iface,), daemon=True)
    t_cap.start()

    # Start TST inference as multiprocessing.Process (same as seniors)
    p_tst = multiprocessing.Process(target=tst_continuous_inference, daemon=True)
    p_tst.start()

    print("[TST-OLD] Capture thread + TST process running.\n")

    try:
        p_tst.join()
    except KeyboardInterrupt:
        print("\n[TST-OLD] Stopped.")
        p_tst.terminate()
        p_tst.join(timeout=3)


if __name__ == "__main__":
    main()
