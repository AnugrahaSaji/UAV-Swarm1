#!/usr/bin/env python3
"""
Old-style XGBoost DDoS Detector  (detection-only)
==================================================
Faithful reproduction of the seniors' ddos_pipeline.py architecture:
  - 3 threads: capture → preprocess → detect (queue-coupled)
  - Busy-wait preprocessing (no sleep, polls queue in tight loop)
  - GIL contention from multiple threads sharing the interpreter
  - Same 0.6 s window, lookback-5 sliding window

Stripped: HTTP server, SQLite storage, mitigation (conntrack/MAC).
These added even more overhead but are not needed for detection-only
benchmarking.

Usage (requires root for raw packet capture):
    sudo ~/nenv/bin/python xgb_old.py
    sudo ~/nenv/bin/python xgb_old.py --iface eth0
"""

import argparse
import os
import sys
from time import time, sleep
from queue import Queue
from threading import Thread

import numpy as np
import xgboost as xgb

from severity import SeverityReporter

try:
    import scapy.all as scapy
except ImportError:
    print("Error: scapy not installed.  pip install scapy")
    sys.exit(1)

# ── Configuration ────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_FILE = os.path.join(SCRIPT_DIR, "xgboost_model.bin")
LOOKBACK = 5
WINDOW_SIZE = 0.60
DEFAULT_IFACE = "wlan0"


# ======================================================================
# Thread 1: Capture  (from ddos_pipeline.py, unchanged logic)
# ======================================================================
def capture_thread(capture_queue, iface):
    """Sniff MAVLink v2 packets (0xFD magic) and enqueue timestamps."""
    print(f"[Capture] Sniffing on {iface}...")

    def packet_callback(packet):
        if scapy.IP in packet and scapy.UDP in packet:
            if scapy.Raw in packet:
                raw_payload = packet[scapy.Raw].load
                if raw_payload[:1] == b'\xfd':  # MAVLink v2
                    capture_queue.put(float(time()))

    scapy.sniff(prn=packet_callback, store=0, iface=iface)


# ======================================================================
# Thread 2: Preprocess  (from ddos_pipeline.py — busy-wait loop)
# ======================================================================
def preprocess_thread(capture_queue, detection_queue):
    """
    Seniors' busy-wait preprocessor.
    Counts packets per window by tight-looping on queue.empty().
    This is intentionally CPU-heavy — it's how the original code worked.
    """
    print("[Preprocess] Starting busy-wait preprocessor...")
    previous_processed_time = time()
    initial_run = True
    data = []

    while True:
        if initial_run:
            # Fill initial lookback windows
            data = [0] * LOOKBACK
            for i in range(LOOKBACK):
                while (time() - previous_processed_time) < WINDOW_SIZE:
                    if not capture_queue.empty():
                        capture_queue.get()
                        data[i] += 1
                previous_processed_time = time()
            initial_run = False
            print(f"[Preprocess] Initial window: {data}")
        else:
            # Slide window: drop oldest, count new
            data = data[1:]
            count = 0
            while (time() - previous_processed_time) < WINDOW_SIZE:
                if not capture_queue.empty():
                    capture_queue.get()
                    count += 1
            data.append(count)
            previous_processed_time = time()

        detection_queue.put(list(data))


# ======================================================================
# Thread 3: Detection  (from ddos_pipeline.py — blocking queue read)
# ======================================================================
def detection_thread(detection_queue):
    """
    Seniors' detection loop.
    Blocks on queue, predicts every window.
    """
    print(f"[Detect] Loading model from {MODEL_FILE}...")
    model = xgb.XGBClassifier()
    model.load_model(MODEL_FILE)
    print("[Detect] Model loaded. Waiting for data...")
    reporter = SeverityReporter()

    window_num = 0
    while True:
        data_point = detection_queue.get()
        window_num += 1

        x = np.array(data_point).reshape(1, -1)
        start_t = time()
        output = model.predict(x)[0]
        pred_ms = (time() - start_t) * 1000

        if output == 1:
            reporter.report(
                severity="medium",
                tier="xgboost_old",
                attack_type="DDoS",
                confidence=1.0,
                details={"window": window_num, "mavlink_counts": data_point},
            )
            print(f"  [#{window_num}] {data_point} → "
                  f"\033[91mATTACK\033[0m  ({pred_ms:.1f}ms)")
        else:
            reporter.report(
                severity="none",
                tier="xgboost_old",
                attack_type="BenignTraffic",
                confidence=1.0,
                details={"window": window_num, "mavlink_counts": data_point},
            )
            print(f"  [#{window_num}] {data_point} → "
                  f"\033[92mNORMAL\033[0m  ({pred_ms:.1f}ms)")


# ======================================================================
# Main — Launch 3 threads (seniors' pattern)
# ======================================================================
def main():
    parser = argparse.ArgumentParser(
        description="Old-style XGBoost DDoS detector (3-thread, busy-wait)")
    parser.add_argument("--iface", default=DEFAULT_IFACE,
                        help="Network interface (default: wlan0)")
    parser.add_argument("--window", type=int, default=100,
                        help="Compatibility flag; xgb_old uses 0.60s windows")
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Compatibility flag; xgb_old is binary")
    args = parser.parse_args()

    if not os.path.exists(MODEL_FILE):
        print(f"Error: model not found: {MODEL_FILE}")
        sys.exit(1)

    print(f"[XGB-OLD] Starting 3-thread pipeline (seniors' architecture)")
    print(f"[XGB-OLD] Model: {MODEL_FILE}")
    print(f"[XGB-OLD] Window: {WINDOW_SIZE}s  Lookback: {LOOKBACK}")
    print(f"[XGB-OLD] Interface: {args.iface}\n")

    # Inter-thread queues (same as ddos_pipeline.py)
    capture_q = Queue()
    detection_q = Queue()

    # Launch threads
    t_capture = Thread(target=capture_thread,
                       args=(capture_q, args.iface), daemon=True)
    t_preprocess = Thread(target=preprocess_thread,
                          args=(capture_q, detection_q), daemon=True)
    t_detect = Thread(target=detection_thread,
                      args=(detection_q,), daemon=True)

    t_capture.start()
    t_preprocess.start()
    t_detect.start()

    print("[XGB-OLD] All 3 threads running.\n")

    try:
        while True:
            sleep(1)
    except KeyboardInterrupt:
        print("\n[XGB-OLD] Stopped.")


if __name__ == "__main__":
    main()
