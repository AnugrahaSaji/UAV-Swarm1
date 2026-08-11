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
from Crypto.Util.Padding import pad, unpad
from src.crypto.utils.crypto_dep.Speck.speck import Python_SPECK
import socket

# Updated paths for current Raspberry Pi environment
def time_series_transformer():
    # Updated paths for dev@uavpi environment
    ddos_dir = os.path.normpath("/home/dev/crypto")
    data_dir = os.path.join(ddos_dir, "data")  # Adjusted for your setup
    models_dir = os.path.join(ddos_dir, "models")
    output_dir = os.path.join(ddos_dir, "results")
    
    # Create directories if they don't exist
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(models_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    def load_model(model_name):
        model_path = os.path.join(models_dir, model_name)
        if os.path.exists(model_path):
            model = torch.load(model_path, map_location=torch.device('cpu'))
            return model
        else:
            print(f"Model {model_path} not found. Creating dummy model for testing.")
            # Create a simple dummy model for testing
            model = TSTPlus(c_in=1, c_out=2, seq_len=400, d_model=64, n_heads=32, d_ff=64, n_layers=1, dropout=0.1)
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
        test_duration = 30  # Run for 30 seconds instead of infinite loop
        start_test = time.time()
        
        print("Starting DDOS detection model testing...")
        with torch.no_grad():
            while time.time() - start_test < test_duration:
                for inputs, _ in dataloader:
                    start_time = time.time()
                    outputs = model(inputs)
                    end_time = time.time()
                    
                    total_time += (end_time - start_time)
                    total_records += inputs.size(0)
                    
                    if time.time() - start_test >= test_duration:
                        break
                        
        if total_records > 0:
            average_time = total_time / total_records
            print(f"Total time: {total_time:.4f}s")
            print(f"Total records: {total_records}")
            print(f"Average prediction time: {average_time:.6f}s per record")
            return average_time
        else:
            print("No records processed")
            return 0

    def create_dummy_data(file_path):
        """Create dummy test data if real data doesn't exist"""
        print(f"Creating dummy data at {file_path}")
        # Generate synthetic MAVLink-like data
        np.random.seed(42)
        data = {
            'Mavlink_Count': np.random.randint(1, 100, 1000),
            'Total_length': np.random.randint(10, 1500, 1000),
            'Status': np.random.choice([0, 1], 1000, p=[0.8, 0.2])  # 80% normal, 20% attack
        }
        df = pd.DataFrame(data)
        df.to_csv(file_path, index=False)
        return df

    def dry_run(model, file_name, scaler):
        test_file_path = os.path.join(data_dir, file_name)
        
        # Check if test file exists, create dummy data if not
        if not os.path.exists(test_file_path):
            print(f"Test file {test_file_path} not found. Creating dummy data...")
            test_data = create_dummy_data(test_file_path)
        else:
            test_data = pd.read_csv(test_file_path)
            
        # Ensure required columns exist
        if 'Mavlink_Count' not in test_data.columns or 'Total_length' not in test_data.columns:
            print("Required columns not found. Creating dummy data...")
            test_data = create_dummy_data(test_file_path)
            
        test_data[['Mavlink_Count', 'Total_length']] = scaler.transform(test_data[['Mavlink_Count', 'Total_length']])
        X_test, y_test = create_sequences(test_data, 400)
        
        if len(X_test) == 0:
            print("Not enough data for sequence creation. Using smaller sequence length...")
            X_test, y_test = create_sequences(test_data, min(50, len(test_data)//2))
            
        if len(X_test) == 0:
            print("Still not enough data. Skipping this test.")
            return
            
        X_test_tensor = torch.tensor(X_test).float().unsqueeze(1)
        y_test_tensor = torch.tensor(y_test).float()
        test_dataset = TensorDataset(X_test_tensor, y_test_tensor)
        test_udp_dataloader = DataLoader(test_dataset, batch_size=4, shuffle=True, drop_last=True)
        
        prediction_time = get_prediction_time(model, test_udp_dataloader)
        print(f"Average Prediction Time per Record for {file_name}: {prediction_time:.6f} seconds")

    # Test files (will create dummy data if not exists)
    test_files = ['tcp_test_ddos_data_0.1.csv', 'udp_test_ddos_data_0.1.csv']
    
    # Load or create model
    model = load_model("400_64_32_64_1_0.1_0.1_entire_model.pth")
    
    for file_path in test_files:
        print(f"\nTesting {file_path}...")
        scaler = StandardScaler()
        
        # Create or load training data for scaler fitting
        train_file_path = os.path.join(data_dir, 'train_ddos_data_0.1.csv')
        if not os.path.exists(train_file_path):
            print("Creating training data for scaler...")
            train_data = create_dummy_data(train_file_path)
        else:
            train_data = pd.read_csv(train_file_path)
            
        if 'Mavlink_Count' not in train_data.columns or 'Total_length' not in train_data.columns:
            train_data = create_dummy_data(train_file_path)
            
        train_data[['Mavlink_Count', 'Total_length']] = scaler.fit_transform(train_data[['Mavlink_Count', 'Total_length']])
        
        dry_run(model, file_path, scaler)
        print()

if __name__ == '__main__':
    p1 = multiprocessing.Process(target=time_series_transformer)
    
    p1.start()
    p1.join()
    
    print("DDOS detection test completed!")


#test ddos detectetion done 

