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


ddos_dir = os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(__file__))))
data_dir = os.path.join(ddos_dir, "Preprocessing", "Finaldata")
models_dir = os.path.join(ddos_dir, "evaluation", "tst", "models")
output_dir = os.path.join(ddos_dir, "evaluation",
                          "tst", "results", "performance")


@profile(precision=8)
def load_model(model_name):
    model = torch.load(model_name, map_location=torch.device('cpu'))
    return model


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


# @profile(precision=8)
def get_prediction_time(model, dataloader):
    model.eval()  # Set the model to evaluation mode
    total_time = 0
    total_records = 0
    while True:
        print("running at time = ", time.time())
        with torch.no_grad():
            for inputs, _ in dataloader:
                start_time = time.time()
                outputs = model(inputs)
                end_time = time.time()

                #batch_time = end_time - start_time
                #total_time += batch_time
                #total_records += len(inputs)

    average_time = total_time / total_records
    print("Total time is : ", total_time)
    print("Total Records are : ", total_records)
    return average_time


def evaluate_model(model, dataloader, thres=0.8):
    model.eval()
    true_labels = []
    predictions = []
    
    with torch.no_grad():
        for xb, yb in dataloader:
            outputs = model(xb)
            outputs = outputs.squeeze()
            probabilities = torch.sigmoid(outputs)
            predicted_labels = (probabilities >= thres).long()

            true_labels.extend(yb.tolist())
            predictions.extend(predicted_labels.tolist())

    report = classification_report(true_labels, predictions, output_dict=True)
    return report


def dry_run(model, file_name, scaler):

    # '/content/test_ddos_data_0.1.csv' #os.path.join(path, 'test_ddos_data_' + str(window) + '.csv')  # Replace with your test file path
    test_file_path = os.path.join(data_dir, file_name)
    test_data = pd.read_csv(test_file_path)

    # Normalizing the 'c4' column in test data (using the same scaler as the training set)
    test_data[['Mavlink_Count', 'Total_length']] = scaler.transform(
        test_data[['Mavlink_Count', 'Total_length']])

    X_test, y_test = create_sequences(test_data, 400)
    X_test_tensor = torch.tensor(X_test).float().unsqueeze(1)
    y_test_tensor = torch.tensor(y_test).float()
    test_dataset = TensorDataset(X_test_tensor, y_test_tensor)
    test_udp_dataloader = DataLoader(
        test_dataset, batch_size=4, shuffle=True, drop_last=True)

    prediction_time = get_prediction_time(model, test_udp_dataloader)
    print("Average Prediction Time per Record for  : ",
          file_name, " is ", prediction_time, " seconds")
    report = {}
    #for t_p in [0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9]:
    #    report[t_p] = evaluate_model(model, test_udp_dataloader, thres=t_p)

    #o_p_filename = os.path.join(output_dir, file_name + "_results.txt")
    #with open(o_p_filename, 'w') as f:
    #    for key, value in report.items():
    #        f.write('%s:%s\n' % (key, value))


# List of test files
test_files = [
    'tcp_test_ddos_data_0.1.csv',
#    'icmp_test_ddos_data_0.1.csv',
#    'tcp_test_fast_ddos_data_0.1.csv',
#    'icmp_test_fast_ddos_data_0.1.csv',
#    'tcp_test_faster_ddos_data_0.1.csv',
#    'icmp_test_faster_ddos_data_0.1.csv',
#    'tcp_icmp_test_ddos_data_0.1.csv'
]

model = load_model(os.path.join(models_dir, "400_64_32_64_1_0.1_0.1_entire_model.pth"))

for file_path in test_files:
    print(f"Testing {file_path}...")
    bs = 4
    scaler = StandardScaler()
    # Load the training CSV file
    # os.path.join(path, 'train_ddos_data_'+ str(window) + '.csv')   # Replace with your file path
    train_file_path = os.path.join(data_dir, 'train_ddos_data_0.1.csv')
    train_data = pd.read_csv(train_file_path)

    # Normalizing the 'c4' column in training data
    scaler = StandardScaler()
    train_data[['Mavlink_Count', 'Total_length']] = scaler.fit_transform(
        train_data[['Mavlink_Count', 'Total_length']])

    dry_run(model, file_path, scaler)
    print("\n")  # Print newline for readability between tests
