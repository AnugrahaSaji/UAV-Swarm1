
import time
import os
import sys
from queue import Queue
from threading import Thread
from statistics import mode

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler

# --- Add tstplus module to path ---
# This allows us to import the model architecture
from tstplus import TSTPlus, _TSTBackbone, _TSTEncoder, _TSTEncoderLayer

# --- Scapy for Packet Sniffing ---
# Scapy is a powerful packet manipulation tool.
# Note: Scapy requires administrator/root privileges to run.
try:
    import scapy.all as scapy
except ImportError:
    print("Error: Scapy is not installed. Please run: pip install scapy")
    sys.exit(1)
except PermissionError:
    print("Error: Scapy requires root/administrator privileges.")
    print("Please run this script with sudo (Linux/macOS) or as Administrator (Windows).")
    sys.exit(1)

# --- Configuration ---
# TST Model Config
MODEL_FILE = "tst_model.pth"
TRAIN_DATA_FILE = "train_ddos_data_0.1.csv" # Used to fit the scaler
SEQ_LENGTH = 400 # This MUST match the model's training sequence length

# Real-time Pipeline Config
WINDOW_SIZE = 0.60 # Time window in seconds to count packets

# --- Component 1: Packet Capture Thread ---
def capture_packets(capture_queue):
    """Sniffs network traffic and puts packet timestamps onto a queue."""
    print("-> [Capture Thread] Started. Sniffing packets on 'wlan0'...")
    
    def packet_callback(packet):
        # This callback is triggered for each packet sniffed.
        # We are interested in a specific type of UDP packet as in the original script.
        if scapy.IP in packet and scapy.UDP in packet and scapy.Raw in packet:
            if packet[scapy.Raw].load.startswith(b'\xfd'):
                capture_queue.put(time.time())

    try:
        scapy.sniff(prn=packet_callback, store=0, iface="wlan0")
    except Exception as e:
        print(f"-> [Capture Thread] Error: Could not start sniffing. Ensure 'wlan0' is a valid interface.")
        print(f"   {e}")
        os._exit(1) # Exit all threads if sniffing fails

# --- Component 2: Preprocessing Thread ---
def preprocess_for_tst(capture_queue, detection_queue):
    """Collects packet counts and creates sequences of length 400 for the TST model."""
    print(f"-> [Preprocess Thread] Started. Waiting for {SEQ_LENGTH} data points...")
    
    packet_counts = []
    last_time = time.time()

    while True:
        # Count packets within the time window
        count = 0
        while (time.time() - last_time) < WINDOW_SIZE:
            if not capture_queue.empty():
                capture_queue.get() # We just need the count, not the timestamp itself
                count += 1
            time.sleep(0.01) # Small sleep to prevent busy-waiting
        last_time = time.time()
        
        # Add the new packet count to our list
        packet_counts.append(count)
        
        # If we have enough data to form a full sequence
        if len(packet_counts) == SEQ_LENGTH:
            print(f"\n-> [Preprocess Thread] Sequence of {SEQ_LENGTH} created. Sending to detector.")
            # Send a copy of the sequence to the detection thread
            detection_queue.put(list(packet_counts))
            
            # Slide the window: remove the oldest data point to make room for the next one
            packet_counts.pop(0)
        else:
            # Print progress until the first sequence is ready
            print(f"-> [Preprocess Thread] Collected {len(packet_counts)}/{SEQ_LENGTH} data points...", end='\r')

# --- Component 3: Detection Thread ---
def detect_ddos_with_tst(detection_queue):
    """Loads the TST model and performs prediction on incoming sequences."""
    print("-> [Detection Thread] Started. Loading model and scaler...")

    # 1. Load the Scaler
    try:
        train_data = pd.read_csv(TRAIN_DATA_FILE)
        scaler = StandardScaler()
        # Fit the scaler on the same data used during training
        scaler.fit(train_data[['Mavlink_Count', 'Total_length']])
    except FileNotFoundError:
        print(f"-> [Detection Thread] Error: Training data file '{TRAIN_DATA_FILE}' not found.")
        os._exit(1)

    # 2. Load the TST Model
    try:
        model = torch.load(MODEL_FILE, map_location=torch.device('cpu'))
        model.eval() # Set model to evaluation mode
    except FileNotFoundError:
        print(f"-> [Detection Thread] Error: Model file '{MODEL_FILE}' not found.")
        os._exit(1)

    print("-> [Detection Thread] Model and scaler loaded successfully. Waiting for data...")

    while True:
        # Wait for a full sequence from the preprocessing thread
        sequence_to_predict = detection_queue.get()
        
        start_time = time.time()

        # Prepare the sequence for the model
        # a. Scale the data (must be in the same format as the training scaler)
        sequence_reshaped = np.array(sequence_to_predict).reshape(-1, 1)
        dummy_column = np.zeros_like(sequence_reshaped)
        sequence_scaled = scaler.transform(np.hstack([sequence_reshaped, dummy_column]))[:, 0]

        # b. Convert to a PyTorch tensor with the correct shape: [batch_size, num_vars, seq_len]
        x_tensor = torch.tensor(sequence_scaled, dtype=torch.float32).unsqueeze(0).unsqueeze(0)

        # 3. Make Prediction
        with torch.no_grad():
            output_logits = model(x_tensor)
            # c_out=1 → single logit, use sigmoid (NOT softmax)
            logit = output_logits.item()
            prob_attack = 1.0 / (1.0 + np.exp(-logit))
            predicted_class = 1 if prob_attack > 0.5 else 0

        end_time = time.time()
        prediction_time_ms = (end_time - start_time) * 1000

        # 4. Display Result
        prediction_status = "ATTACK" if predicted_class == 1 else "NORMAL"
        confidence = (prob_attack if predicted_class == 1 else 1.0 - prob_attack) * 100

        print(f"--- PREDICTION RESULT ---")
        if prediction_status == "ATTACK":
            print(f"   🚨 Result: {prediction_status} DETECTED (Confidence: {confidence:.2f}%)")
        else:
            print(f"   ✅ Result: {prediction_status} Traffic (Confidence: {confidence:.2f}%)")
        print(f"   (Prediction took {prediction_time_ms:.2f} ms)")
        print(f"-------------------------")

# --- Main Execution ---
if __name__ == "__main__":
    print("--- Real-Time TST DDoS Detection System ---")
    print("NOTE: This script requires root/administrator privileges for packet sniffing.")

    # Create queues to pass data between threads
    capture_q = Queue()
    detection_q = Queue()

    # Create the threads
    capture_thread = Thread(target=capture_packets, args=(capture_q,), daemon=True)
    preprocess_thread = Thread(target=preprocess_for_tst, args=(capture_q, detection_q), daemon=True)
    detection_thread = Thread(target=detect_ddos_with_tst, args=(detection_q,), daemon=True)

    # Start the threads
    capture_thread.start()
    preprocess_thread.start()
    detection_thread.start()

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n--- System shutting down ---")
