import os
import sys
import time
import torch
import numpy as np
import pandas as pd
from statistics import mode
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset
from tstplus import _TSTEncoderLayer, _TSTEncoder, _TSTBackbone, TSTPlus


ddos_dir = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(__file__))))
data_dir = os.path.join(ddos_dir, "Preprocessing", "Finaldata")
models_dir = os.path.join(ddos_dir, "evaluation", "tst", "models")
output_dir = os.path.join(ddos_dir, "evaluation", "tst", "results", "seq_len")


def create_sequences(data, seq_length):
    xs = []
    ys = []

    for i in range(len(data) - seq_length):
        x = data['Mavlink_Count'].iloc[i:(i + seq_length)].values
        # y = data['Status'].iloc[i + seq_length]
        y = mode(data['Status'].iloc[i: i + seq_length + 1].values)
        xs.append(x)
        ys.append(y)

    return np.array(xs), np.array(ys)


def get_prediction_time(model, dataloader):
    model.eval()  # Set the model to evaluation mode
    total_time = 0
    total_records = 0

    with torch.no_grad():
        for inputs, _ in dataloader:
            start_time = time.time()
            outputs = model(inputs)
            end_time = time.time()

            batch_time = end_time - start_time
            total_time += batch_time
            total_records += len(inputs)

    average_time = total_time / total_records
    return average_time


def dry_run(seq_len, file_name):
    bs = 4
    scaler = StandardScaler()
    # '/content/test_ddos_data_0.1.csv' #os.path.join(path, 'test_ddos_data_' + str(window) + '.csv')  # Replace with your test file path
    # 'tcp_test_ddos_data_0.1.csv'
    test_file_path = os.path.join(data_dir, file_name)
    test_data = pd.read_csv(test_file_path)
    test_data[['Mavlink_Count', 'Total_length']] = scaler.fit_transform(
        test_data[['Mavlink_Count', 'Total_length']])
    X_test, y_test = create_sequences(test_data, seq_len)
    X_test_tensor = torch.tensor(X_test).float().unsqueeze(1)
    y_test_tensor = torch.tensor(y_test).float()
    test_dataset = TensorDataset(X_test_tensor, y_test_tensor)
    test_udp_dataloader = DataLoader(
        test_dataset, batch_size=bs, shuffle=True, drop_last=True)

    model_name = os.path.join(models_dir, str(
        seq_len) + "_64_32_64_2_0.1_0.1_" + "entire_model.pth")
    model = torch.load(model_name, map_location=torch.device('cpu'))

    # Assuming test_udp_dataloader is defined
    prediction_time = get_prediction_time(model, test_udp_dataloader)
    print("Average Prediction Time per Record for seq_len : ",
          seq_len, " is ", prediction_time, " seconds")
    return prediction_time


# List of test files
test_files = [
#    'tcp_test_ddos_data_0.1.csv',
    'icmp_test_ddos_data_0.1.csv',
#    'tcp_test_fast_ddos_data_0.1.csv',
#    'icmp_test_fast_ddos_data_0.1.csv',
#    'tcp_test_faster_ddos_data_0.1.csv',
#    'icmp_test_faster_ddos_data_0.1.csv',
#    'tcp_icmp_test_ddos_data_0.1.csv'
]


def run():
    seq_len = [100, 200, 300, 400, 500]
    for file_name in test_files:
        print(f"Testing {file_name}...")
        results = {}
        for s_l in seq_len:
            results[s_l] = dry_run(s_l, file_name)
        with open(os.path.join(output_dir, file_name + "_seq_len_results.txt"), 'w') as f:
            for key, value in results.items():
                f.write('%s:%s\n' % (key, value))
        print(results)
        print("\n")  # Print newline for readability between tests


run()
