import time
import os
import sys
from threading import Thread, Lock
from collections import deque

import numpy as np
import pandas as pd
import torch
import xgboost as xgb
from sklearn.preprocessing import StandardScaler

from tstplus import TSTPlus, _TSTBackbone, _TSTEncoder, _TSTEncoderLayer

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
WINDOW_SIZE = 0.60
TST_SEQ_LENGTH = 400
XGB_SEQ_LENGTH = 5
BUFFER_SIZE = 900

# --- Shared State ---
# This dictionary holds the configuration that can be changed at runtime.
DETECTOR_CONFIG = {'current_model': 'XGBOOST'} # Start with XGBoost by default
CONFIG_LOCK = Lock()

# --- Thread 1: Data Collector ---
def collector_thread(buffer, buffer_lock):
    """Sniffs packets and continuously updates a shared buffer of packet counts."""
    print("[Collector] Started. Sniffing packets...")
    
    # This queue is internal to the collector for thread-safe sniffing
    packet_timestamps = deque()

    def packet_callback(packet):
        if scapy.IP in packet and scapy.UDP in packet and scapy.Raw in packet:
            if packet[scapy.Raw].load.startswith(b'\xfd'):
                packet_timestamps.append(time.time())

    sniffer = Thread(target=scapy.sniff, kwargs={'prn': packet_callback, 'store': 0, 'iface': 'wlan0'}, daemon=True)
    sniffer.start()
    print("[Collector] Sniffer is running.")

    while True:
        time.sleep(WINDOW_SIZE) 
        
        # Count packets that arrived in the last window
        count = len(packet_timestamps)
        packet_timestamps.clear()

        with buffer_lock:
            buffer.append(count)

# --- Thread 2: User Input Controller ---
def input_controller_thread(config, lock):
    """Waits for user input to change the active model."""
    while True:
        print("\n--- waiting for input ---")
        choice = input("Enter '1' for XGBoost, '2' for TST: ")
        with lock:
            if choice == '1':
                if config['current_model'] != 'XGBOOST':
                    print("\n>>> Switching to XGBoost model...")
                    config['current_model'] = 'XGBOOST'
            elif choice == '2':
                if config['current_model'] != 'TST':
                    print("\n>>> Switching to TST model...")
                    config['current_model'] = 'TST'

# --- Thread 3: The Detector ---
def detector_thread(config, config_lock, buffer, buffer_lock):
    """The main detection loop. Checks the config and runs the appropriate model."""
    print("[Detector] Started. Loading all models...")

    # Load XGBoost
    xgb_model = xgb.XGBClassifier()
    xgb_model.load_model(XGB_MODEL_FILE)

    # Load TST and Scaler
    train_data = pd.read_csv(TRAIN_DATA_FILE)
    scaler = StandardScaler().fit(train_data[['Mavlink_Count', 'Total_length']])
    tst_model = torch.load(TST_MODEL_FILE, map_location=torch.device('cpu'))
    tst_model.eval()
    
    print("[Detector] All models loaded.")

    while True:
        time.sleep(WINDOW_SIZE * 1.1) # Run slightly slower than the collector
        
        active_model = ""
        with config_lock:
            active_model = config['current_model']

        # --- XGBOOST LOGIC ---
        if active_model == 'XGBOOST':
            with buffer_lock:
                if len(buffer) < XGB_SEQ_LENGTH:
                    print("[XGBoost] Collecting initial data...")
                    continue
                data_point = list(buffer)[-XGB_SEQ_LENGTH:]
            
            data_point_np = np.array(data_point).reshape(1, -1)
            prediction = xgb_model.predict(data_point_np)[0]
            status = "ATTACK" if prediction == 1 else "NORMAL"
            print(f"[XGBoost ACTIVE] -> Prediction: {status}")

        # --- TST LOGIC ---
        elif active_model == 'TST':
            with buffer_lock:
                if len(buffer) < TST_SEQ_LENGTH:
                    print(f"[TST ACTIVE] -> Collecting data... ({len(buffer)}/{TST_SEQ_LENGTH})")
                    continue
                sequence_to_predict = list(buffer)[-TST_SEQ_LENGTH:]

            # Prepare data
            sequence_reshaped = np.array(sequence_to_predict).reshape(-1, 1)
            dummy_column = np.zeros_like(sequence_reshaped)
            sequence_scaled = scaler.transform(np.hstack([sequence_reshaped, dummy_column]))[:, 0]
            x_tensor = torch.tensor(sequence_scaled, dtype=torch.float32).unsqueeze(0).unsqueeze(0)

            # Predict
            with torch.no_grad():
                logit = tst_model(x_tensor).item()
                # c_out=1 → single logit, use sigmoid (NOT softmax/argmax)
                prob_attack = 1.0 / (1.0 + np.exp(-logit))
                pred_class = 1 if prob_attack > 0.5 else 0
            
            status = "ATTACK" if pred_class == 1 else "NORMAL"
            print(f"[TST ACTIVE] -> Prediction: {status}  (P(attack)={prob_attack:.4f})")

# --- Main Execution ---
if __name__ == "__main__":
    print("--- Manual Control DDoS Detection System ---")
    print("NOTE: This script requires root/administrator privileges.")

    # Shared data structures
    shared_buffer = deque(maxlen=BUFFER_SIZE)
    buffer_lock = Lock()

    # Create and start threads
    collector = Thread(target=collector_thread, args=(shared_buffer, buffer_lock), daemon=True)
    detector = Thread(target=detector_thread, args=(DETECTOR_CONFIG, CONFIG_LOCK, shared_buffer, buffer_lock), daemon=True)
    input_controller = Thread(target=input_controller_thread, args=(DETECTOR_CONFIG, CONFIG_LOCK), daemon=True)

    collector.start()
    detector.start()
    input_controller.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n--- System shutting down ---")
