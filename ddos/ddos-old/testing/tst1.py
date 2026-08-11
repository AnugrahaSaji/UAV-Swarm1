import multiprocessing
import os
import time
import torch
import pandas as pd
import numpy as np
import sys
from statistics import mode
from memory_profiler import profile
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
from torch.utils.data import DataLoader, TensorDataset

# Add paths to important modules
from tstplus import _TSTEncoderLayer, _TSTEncoder, _TSTBackbone, TSTPlus
from Crypto.Util.Padding import pad, unpad
from speck import Python_SPECK
import socket

# Time Series Transformer Code 1
def time_series_transformer():
    ddos_dir = os.path.normpath("/home/dev/src/ddos")
    data_dir = os.path.join(ddos_dir, "detection", "Preprocessing", "Finaldata")
    models_dir = os.path.join(ddos_dir, "detection", "evaluation", "tst", "models")
    output_dir = os.path.join(ddos_dir, "detection", "evaluation", "tst", "results", "performance")

    def load_model(model_name):
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
        print("running at time = ", time.time())
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
        print("Total Records are : ", total_records)
        return average_time

    def dry_run(model, file_name, scaler):
        test_file_path = os.path.join(data_dir, file_name)
        test_data = pd.read_csv(test_file_path)
        test_data[['Mavlink_Count', 'Total_length']] = scaler.transform(test_data[['Mavlink_Count', 'Total_length']])
        X_test, y_test = create_sequences(test_data, 400)
        X_test_tensor = torch.tensor(X_test).float().unsqueeze(1)
        y_test_tensor = torch.tensor(y_test).float()
        test_dataset = TensorDataset(X_test_tensor, y_test_tensor)
        test_udp_dataloader = DataLoader(test_dataset, batch_size=4, shuffle=True, drop_last=True)
        prediction_time = get_prediction_time(model, test_udp_dataloader)
        print("Average Prediction Time per Record for  : ", file_name, " is ", prediction_time, " seconds")

    test_files = ['tcp_test_ddos_data_0.1.csv']
    model = load_model(os.path.join(models_dir, "400_64_32_64_1_0.1_0.1_entire_model.pth"))
    for file_path in test_files:
        print(f"Testing {file_path}...")
        scaler = StandardScaler()
        train_file_path = os.path.join(data_dir, 'train_ddos_data_0.1.csv')
        train_data = pd.read_csv(train_file_path)
        train_data[['Mavlink_Count', 'Total_length']] = scaler.fit_transform(train_data[['Mavlink_Count', 'Total_length']])
        dry_run(model, file_path, scaler)
        print("\n")
        
if __name__ == '__main__':
    p1 = multiprocessing.Process(target=time_series_transformer)
    # p2 = multiprocessing.Process(target=time_series_transformer_2)
    # p3 = multiprocessing.Process(target=speck_cryptography_proxy_algorithm)

    p1.start()
    # p2.start()
    # p3.start()

    p1.join()
    # p2.join()
    # p3.join()
