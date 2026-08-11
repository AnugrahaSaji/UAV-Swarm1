import multiprocessing
import os
import time
import torch
import pandas as pd
import numpy as np
from statistics import mode
from memory_profiler import profile
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
from torch.utils.data import DataLoader, TensorDataset
import sys

# Add paths to important modules - Updated with correct paths
# Path to tstplus.py
# Parent directory for speck.py
# Fixed: crypto_dep now in proper package structure  # Alternative path for speck.py

try:
    from tstplus import _TSTEncoderLayer, _TSTEncoder, _TSTBackbone, TSTPlus
except ImportError:
    print("Error importing tstplus module. Check that the path is correct.")
    sys.exit(1)

try:
    from Crypto.Util.Padding import pad, unpad
except ImportError:
    print("Error importing Crypto.Util.Padding. Make sure pycryptodome is installed.")

try:
    from speck import Python_SPECK
except ImportError:
    print("Error importing speck module. Check that the path is correct.")

import socket

# Time Series Transformer Code 1
def time_series_transformer():
    ddos_dir = os.path.normpath("/home/dev/src/ddos")
    data_dir = os.path.join(ddos_dir, "detection", "Preprocessing", "Finaldata")
    models_dir = os.path.join(ddos_dir, "detection", "evaluation", "tst", "models")
    output_dir = os.path.join(ddos_dir, "detection", "evaluation", "tst", "results", "performance")
    
    # Check if directories exist
    print(f"Checking if data_dir exists: {os.path.exists(data_dir)}")
    print(f"Checking if models_dir exists: {os.path.exists(models_dir)}")
    print(f"Checking if output_dir exists: {os.path.exists(output_dir)}")

    def load_model(model_name):
        if not os.path.exists(model_name):
            print(f"ERROR: Model file not found: {model_name}")
            return None
        model = torch.load(model_name, map_location=torch.device('cpu'))
        return model

    def create_sequences(data, seq_length):
        xs = []
        ys = []
        for i in range(len(data) - seq_length):
            x = data['Mavlink_Count'].iloc[i:(i + seq_length)].values
            y = mode(data['Status'].iloc[i: i + seq_length + 1].values)
            xs.append(x)
            ys.append(y)
        return np.array(xs), np.array(ys)

    def get_prediction_time(model, dataloader):
        model.eval()
        total_time = 0
        total_records = 0
        
        print("Running prediction at time = ", time.time())
        with torch.no_grad():
            for inputs, _ in dataloader:
                start_time = time.time()
                outputs = model(inputs)
                end_time = time.time()
                total_time += (end_time - start_time)
                total_records += 1
                if total_records >= 10:  # Limit to 10 samples for testing
                    break
        
        if total_records > 0:
            average_time = total_time / total_records
        else:
            average_time = 0
            
        print("Total time is : ", total_time)
        print("Total records are : ", total_records)
        return average_time

    def dry_run(model, file_name, scaler):
        test_file_path = os.path.join(data_dir, file_name)
        if not os.path.exists(test_file_path):
            print(f"ERROR: Test file not found: {test_file_path}")
            return
        
        try:
            test_data = pd.read_csv(test_file_path)
            test_data[['Mavlink_Count', 'Total_length']] = scaler.transform(test_data[['Mavlink_Count', 'Total_length']])
            X_test, y_test = create_sequences(test_data, 400)
            X_test_tensor = torch.tensor(X_test).float().unsqueeze(1)
            y_test_tensor = torch.tensor(y_test).float()
            test_dataset = TensorDataset(X_test_tensor, y_test_tensor)
            test_udp_dataloader = DataLoader(test_dataset, batch_size=4, shuffle=True, drop_last=True)
            prediction_time = get_prediction_time(model, test_udp_dataloader)
            print(f"Average Prediction Time per Record for {file_name}: {prediction_time} seconds")
        except Exception as e:
            print(f"Error during dry run: {str(e)}")

    test_files = ['tcp_test_ddos_data_0.1.csv']
    model_path = os.path.join(models_dir, "400_64_32_64_1_0.1_0.1_entire_model.pth")
    print(f"Loading model from: {model_path}")
    
    model = load_model(model_path)
    if model is None:
        print("Failed to load model")
        return
    
    for file_path in test_files:
        print(f"Testing {file_path}...")
        scaler = StandardScaler()
        train_file_path = os.path.join(data_dir, 'train_ddos_data_0.1.csv')
        if not os.path.exists(train_file_path):
            print(f"ERROR: Train file not found: {train_file_path}")
            continue
            
        train_data = pd.read_csv(train_file_path)
        train_data[['Mavlink_Count', 'Total_length']] = scaler.fit_transform(train_data[['Mavlink_Count', 'Total_length']])
        dry_run(model, file_path, scaler)
        print("\n")

if __name__ == '__main__':
    print("Starting TST testing script...")
    p1 = multiprocessing.Process(target=time_series_transformer)
    p1.start()
    p1.join()
    print("TST testing completed!")
