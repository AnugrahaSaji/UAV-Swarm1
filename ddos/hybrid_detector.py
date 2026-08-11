import time
import os
import sys
from queue import Queue
from threading import Thread, Lock
from collections import deque

import numpy as np
import pandas as pd
import torch
import xgboost as xgb
from sklearn.preprocessing import StandardScaler

from tstplus import TSTPlus, _TSTBackbone, _TSTEncoder, _TSTEncoderLayer
from mitigation import DDoSMitigator

# --- Scapy for Packet Sniffing ---
try:
    import scapy.all as scapy
except ImportError:
    print("Error: Scapy is not installed. Please run: pip install scapy")
    sys.exit(1)

# --- Configuration ---
# Models
XGB_MODEL_FILE = "xgboost_model.bin"
TST_MODEL_FILE = "tst_model.pth"
TRAIN_DATA_FILE = "train_ddos_data_0.1.csv"

# Pipeline
WINDOW_SIZE = 0.60  # Time window in seconds to count packets
TST_SEQ_LENGTH = 400
XGB_SEQ_LENGTH = 5
BUFFER_SIZE = 900   # Store ~9 minutes of data (900 * 0.6s)

# --- Shared IP Tracking for Mitigation ---
recent_ip_counts = {}
ip_lock = Lock()

# --- Thread 1: Data Collector & Buffer ---
def collector_thread(buffer, buffer_lock, xgboost_queue):
    """Sniffs packets, counts them, and maintains a shared buffer of recent counts."""
    print("[Collector] Started. Sniffing packets...")
    
    packet_timestamps = Queue()

    def packet_callback(packet):
        if scapy.IP in packet and scapy.UDP in packet and scapy.Raw in packet:
            if packet[scapy.Raw].load.startswith(b'\xfd'):
                src_ip = packet[scapy.IP].src
                packet_timestamps.put(time.time())
                with ip_lock:
                    recent_ip_counts[src_ip] = recent_ip_counts.get(src_ip, 0) + 1

    # Start sniffing in a background thread
    sniffer = Thread(target=scapy.sniff, kwargs={'prn': packet_callback, 'store': 0, 'iface': 'wlan0'}, daemon=True)
    sniffer.start()
    print("[Collector] Sniffer is running.")

    last_time = time.time()
    while True:
        # Count packets within the time window
        count = 0
        while (time.time() - last_time) < WINDOW_SIZE:
            if not packet_timestamps.empty():
                packet_timestamps.get()
                count += 1
            time.sleep(0.01)
        last_time = time.time()

        # Safely add the new count to the shared buffer
        with buffer_lock:
            buffer.append(count)
        
        # Send the latest 5 counts to the XGBoost screener
        if len(buffer) >= XGB_SEQ_LENGTH:
            with buffer_lock:
                # Create a list from the right-end of the deque
                xgboost_input = list(buffer)[-XGB_SEQ_LENGTH:]
            xgboost_queue.put(xgboost_input)

# --- Thread 2: XGBoost "Screener" ---
def xgboost_screener_thread(buffer, buffer_lock, xgboost_queue, tst_queue):
    """Runs fast predictions on recent data and triggers TST if an attack is suspected."""
    print("[XGBoost] Started. Loading model...")
    model = xgb.XGBClassifier()
    model.load_model(XGB_MODEL_FILE)
    print("[XGBoost] Model loaded. Screening traffic...")

    while True:
        # Get the latest 5 data points from the collector
        data_point = xgboost_queue.get()
        
        # Reshape for prediction
        data_point_np = np.array(data_point).reshape(1, -1)
        
        prediction = model.predict(data_point_np)[0]

        # If XGBoost flags an attack, trigger the TST confirmation
        if prediction == 1:
            print("\n[XGBoost] 🚨 Potential Attack Detected! Triggering TST for confirmation...")
            with buffer_lock:
                # Check if buffer has enough data for TST
                if len(buffer) >= TST_SEQ_LENGTH:
                    # Get the last 400 data points for deep analysis
                    tst_sequence = list(buffer)[-TST_SEQ_LENGTH:]
                    tst_queue.put(tst_sequence)
                else:
                    print("[XGBoost] Warning: Not enough data in buffer for TST confirmation yet.")
        else:
            # Print a dot for normal traffic to show it's working
            print(".", end="", flush=True)

# --- Thread 3: TST "Confirmer" ---
def tst_confirmer_thread(tst_queue, mitigator):
    """Waits for a trigger and runs a deep analysis on the provided data sequence."""
    print("[TST] Started. Loading model and scaler...")

    # Load Scaler and TST Model
    train_data = pd.read_csv(TRAIN_DATA_FILE)
    scaler = StandardScaler().fit(train_data[['Mavlink_Count', 'Total_length']])
    model = torch.load(TST_MODEL_FILE, map_location=torch.device('cpu'))
    model.eval()
    print("[TST] Model and scaler loaded. Waiting for confirmation tasks...")

    while True:
        # Wait for a sequence to analyze
        sequence_to_predict = tst_queue.get()
        print("[TST] Received sequence. Running deep analysis...")

        # Prepare data for TST model
        sequence_reshaped = np.array(sequence_to_predict).reshape(-1, 1)
        dummy_column = np.zeros_like(sequence_reshaped)
        sequence_scaled = scaler.transform(np.hstack([sequence_reshaped, dummy_column]))[:, 0]
        x_tensor = torch.tensor(sequence_scaled, dtype=torch.float32).unsqueeze(0).unsqueeze(0)

        # Make Prediction
        with torch.no_grad():
            output_logits = model(x_tensor)
            # c_out=1 → single logit, use sigmoid (NOT softmax)
            logit = output_logits.item()
            prob_attack = 1.0 / (1.0 + np.exp(-logit))
            predicted_class = 1 if prob_attack > 0.5 else 0

        # Display Final Result
        prediction_status = "CONFIRMED ATTACK" if predicted_class == 1 else "FALSE ALARM"
        confidence = (prob_attack if predicted_class == 1 else 1.0 - prob_attack) * 100

        print("--- TST CONFIRMATION ---")
        if prediction_status == "CONFIRMED ATTACK":
            print(f"   🔥🔥🔥 Result: {prediction_status} (Confidence: {confidence:.2f}%) 🔥🔥🔥")
            # Identify the source IP with the highest traffic volume
            with ip_lock:
                if recent_ip_counts:
                    attacker_ip = max(recent_ip_counts, key=recent_ip_counts.get)
                    print(f"   [Mitigation Trigger] High-rate IP identified: {attacker_ip} "
                          f"({recent_ip_counts[attacker_ip]} packets in window)")
                    # Inject drop rule at the kernel level
                    mitigator.block_ip(attacker_ip, reason=f"DDoS confirmed by TST (Confidence: {confidence:.1f}%)")
                    # Clear counts
                    recent_ip_counts.clear()
                else:
                    print("   [Mitigation Trigger] Warning: Attacker IP could not be resolved from counts.")
        else:
            print(f"   ✅ Result: {prediction_status} (Confidence: {confidence:.2f}%)")
            # Clear counts for benign traffic
            with ip_lock:
                recent_ip_counts.clear()
        print("------------------------")

# --- Main Execution ---
if __name__ == "__main__":
    print("--- Hybrid DDoS Detection System ---")
    print("NOTE: This script requires root/administrator privileges.")

    # Initialize DDoS Mitigator
    mitigator = DDoSMitigator()

    # Shared data structures
    shared_buffer = deque(maxlen=BUFFER_SIZE)
    buffer_lock = Lock()
    
    # Queues for inter-thread communication
    xgboost_q = Queue()
    tst_q = Queue()

    # Create and start threads
    collector = Thread(target=collector_thread, args=(shared_buffer, buffer_lock, xgboost_q), daemon=True)
    xgboost_screener = Thread(target=xgboost_screener_thread, args=(shared_buffer, buffer_lock, xgboost_q, tst_q), daemon=True)
    tst_confirmer = Thread(target=tst_confirmer_thread, args=(tst_q, mitigator), daemon=True)

    collector.start()
    xgboost_screener.start()
    tst_confirmer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n--- System shutting down ---")
        mitigator.clear_all_blocks()
