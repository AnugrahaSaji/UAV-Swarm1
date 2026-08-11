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
from tstplus import _TSTEncoderLayer, _TSTEncoder, _TSTBackbone, TSTPlus
import sys
from Crypto.Util.Padding import pad, unpad

# Add path for crypto dependency
sys.path.append(os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../../../")))
try:
    from src.crypto.pre_quantum.speck.speck import Python_SPECK
except ImportError:
    # Fallback to the old location
    try:
        from src.crypto.utils.crypto_dep.Speck.speck import Python_SPECK
    except ImportError:
        print("WARNING: Could not import Python_SPECK, crypto functions may not work")
import socket

# Time Series Transformer Code 1
def time_series_transformer():
    # Get the project root directory and construct paths relative to it
    current_dir = os.path.dirname(os.path.abspath(__file__))
    ddos_dir = os.path.normpath(os.path.join(current_dir, "..", "..", ".."))
    data_dir = os.path.join(ddos_dir, "Preprocessing", "Finaldata")
    models_dir = os.path.join(ddos_dir, "evaluation", "tst", "models")
    output_dir = os.path.join(ddos_dir, "evaluation", "tst", "results", "performance")
    
    print(f"Data directory: {data_dir}")
    print(f"Models directory: {models_dir}")
    print(f"Output directory: {output_dir}")

    def load_model(model_name):
        print(f"Loading model from: {model_name}")
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
                # Limit the number of iterations for testing
                if total_records >= 10:
                    break
        
        if total_records == 0:
            print("No records processed!")
            return 0
            
        average_time = total_time / total_records
        print("Total time is : ", total_time)
        print("Total Records are : ", total_records)
        return average_time

    def dry_run(model, file_name, scaler):
        test_file_path = os.path.join(data_dir, file_name)
        print(f"Reading test data from: {test_file_path}")
        test_data = pd.read_csv(test_file_path)
        print(f"Test data shape: {test_data.shape}")
        
        # Check if required columns exist
        if 'Mavlink_Count' not in test_data.columns or 'Total_length' not in test_data.columns:
            print(f"Required columns missing. Available columns: {test_data.columns}")
            return
            
        test_data[['Mavlink_Count', 'Total_length']] = scaler.transform(test_data[['Mavlink_Count', 'Total_length']])
        X_test, y_test = create_sequences(test_data, 400)
        print(f"Created sequences with shape: {X_test.shape}")
        
        X_test_tensor = torch.tensor(X_test).float().unsqueeze(1)
        y_test_tensor = torch.tensor(y_test).float()
        test_dataset = TensorDataset(X_test_tensor, y_test_tensor)
        test_udp_dataloader = DataLoader(test_dataset, batch_size=4, shuffle=True, drop_last=True)
        
        prediction_time = get_prediction_time(model, test_udp_dataloader)
        print("Average Prediction Time per Record for  : ", file_name, " is ", prediction_time, " seconds")

    test_files = ['tcp_test_ddos_data_0.1.csv']
    try:
        model = load_model(os.path.join(models_dir, "400_64_32_64_1_0.1_0.1_entire_model.pth"))
        for file_path in test_files:
            print(f"Testing {file_path}...")
            scaler = StandardScaler()
            train_file_path = os.path.join(data_dir, 'train_ddos_data_0.1.csv')
            print(f"Reading training data from: {train_file_path}")
            train_data = pd.read_csv(train_file_path)
            print(f"Train data shape: {train_data.shape}")
            
            # Check if required columns exist
            if 'Mavlink_Count' not in train_data.columns or 'Total_length' not in train_data.columns:
                print(f"Required columns missing in training data. Available columns: {train_data.columns}")
                continue
                
            train_data[['Mavlink_Count', 'Total_length']] = scaler.fit_transform(train_data[['Mavlink_Count', 'Total_length']])
            dry_run(model, file_path, scaler)
            print("\n")
    except Exception as e:
        print(f"Error in time_series_transformer: {e}")
        import traceback
        traceback.print_exc()
        
if __name__ == '__main__':
    print("Starting TST (Time Series Transformer) process...")
    try:
        p1 = multiprocessing.Process(target=time_series_transformer)
        p1.start()
        p1.join()
        print("TST process completed.")
    except Exception as e:
        print(f"Error running TST process: {e}")
        import traceback
        traceback.print_exc()
