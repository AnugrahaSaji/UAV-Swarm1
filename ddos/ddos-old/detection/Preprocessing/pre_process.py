import os
import pandas as pd

# Import universal path helper for cross-platform compatibility
try:
    # Navigate to project root (4 levels up from Preprocessing)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    import sys
    sys.path.insert(0, project_root)
    from universal_paths import setup_paths
    setup_paths()
    PATHS_AVAILABLE = True
except ImportError:
    PATHS_AVAILABLE = False


def process_file(file_name, simple_name, lim_dict, window=0.25):
    try:
        if "normal" in file_name:
            status = 0
        else:
            status = 1
        df = pd.read_csv(file_name)
        df_filtered = df[["Time", "Protocol", "Length"]]
        t_min = df_filtered["Time"].min()
        # min(df_filtered["Time"].max(), lim_dict[simple_name])
        t_max = df_filtered["Time"].max()
        mavlink_packets = []
        total_length = []
        curr_time = t_min
        while curr_time < t_max:

            filtered_df = df_filtered[(df_filtered["Time"] >= curr_time) & (
                df_filtered["Time"] < curr_time + window)]

            # Total Length
            t_length = int((filtered_df[["Length"]].sum()).iloc[0])
            total_length.append(t_length)

            # Packet_count
            p_count = int(
                ((filtered_df[["Protocol"]] == "MAVLink 2.0").sum()).iloc[0])
            mavlink_packets.append(p_count)

            # Update Time
            curr_time += window

        df_processed = pd.DataFrame(
            {"Total_length": total_length, "Mavlink_Count": mavlink_packets})
        df_processed["Status"] = status
        return df_processed
    except Exception as E:
        print("Error: ", E)
        return pd.DataFrame()


def gen_data(file_paths, attack, mode, window_size):
    # Initialize an empty list to store aggregated DataFrames
    aggregated_dfs = []
    lim_dict = {}
    print("Generating ", attack, " ", mode, " data")

    attack_files = [
        "attack_" + str(i*2) + ".csv" for i in range(1, len(file_paths)//2 + 1)]
    normal_files = ["normal_" +
                    str(1 + i*2) + ".csv" for i in range(len(file_paths)//2)]

    # Iterate over each file path
    for file_path in file_paths:
        count = len(file_paths)//2
        for elem in range(count):
            attack_file_tem = os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "Data", attack, mode, attack_files[elem])
            normal_file_tem = os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "Data", attack, mode, normal_files[elem])

            temp_max_elems = min((pd.read_csv(attack_file_tem))["Time"].max(), (
                pd.read_csv(normal_file_tem))["Time"].max())
            lim_dict[attack_files[elem]] = temp_max_elems
            lim_dict[normal_files[elem]] = temp_max_elems

    for file_name in file_paths:
        print("processing: ", file_name)
        # Process the file and get the aggregated DataFrame
        if PATHS_AVAILABLE:
            # Use universal paths for cross-platform compatibility
            base_dir = os.path.dirname(os.path.abspath(__file__))
            file_path = os.path.join(base_dir, "Data", attack, mode, file_name)
        else:
            # Fallback to original method
            file_path = os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "Data", attack, mode, file_name)
        
        aggregated_df = process_file(
            file_path, file_name, lim_dict, window_size)
        if aggregated_df is not None:
            # Add the aggregated DataFrame to the list
            aggregated_dfs.append(aggregated_df)

    # Concatenate all aggregated DataFrames into a single DataFrame
    final_df = pd.concat(aggregated_dfs)
    
    # Use cross-platform path for output
    if PATHS_AVAILABLE:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_path = os.path.join(base_dir, "Data", attack, "processed", 
                                  f"{attack}_{mode}_ddos_data_{window_size}.csv")
    else:
        output_path = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), "Data", attack, "processed", 
            attack + "_" + mode + '_ddos_data_' + str(window_size) + '.csv')
    
    final_df.to_csv(output_path)


def gen_data_combined(file_paths, mode, window_size):
    # Initialize an empty list to store aggregated DataFrames
    aggregated_dfs = []
    lim_dict = {}
    print("Generating ", mode, " data")

    attack_files = [
        "attack_" + str(i*2) + ".csv" for i in range(1, len(file_paths)//2 + 1)]
    normal_files = ["normal_" +
                    str(1 + i*2) + ".csv" for i in range(len(file_paths)//2)]

    # Iterate over each file path
    for file_path in file_paths:
        count = len(file_paths)//2
        for elem in range(count):
            attack_file_tem = os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "Data", "combined", mode, attack_files[elem])
            normal_file_tem = os.path.join(os.path.dirname(
                os.path.abspath(__file__)), "Data", "combined", mode, normal_files[elem])

            temp_max_elems = min((pd.read_csv(attack_file_tem))["Time"].max(), (
                pd.read_csv(normal_file_tem))["Time"].max())
            lim_dict[attack_files[elem]] = temp_max_elems
            lim_dict[normal_files[elem]] = temp_max_elems

    for file_name in file_paths:
        print("processing: ", file_name)
        # Process the file and get the aggregated DataFrame
        file_path = os.path.join(os.path.dirname(
            os.path.abspath(__file__)), "Data", "combined", mode, file_name)
        aggregated_df = process_file(
            file_path, file_name, lim_dict, window_size)
        if aggregated_df is not None:
            # Add the aggregated DataFrame to the list
            aggregated_dfs.append(aggregated_df)

    # Concatenate all aggregated DataFrames into a single DataFrame
    final_df = pd.concat(aggregated_dfs)
    final_df.to_csv(os.path.join(os.path.dirname(
        os.path.abspath(__file__)), "Data", "combined", "processed", mode + '_ddos_data_' + str(window_size) + '.csv'))


def run():
    window_size = 0.1  # Window size in seconds

    train_file_paths = ['normal_1.csv', 'attack_2.csv', 'normal_3.csv', 'attack_4.csv',
                        ]  # 'normal_7.csv', 'attack_8.csv' 'normal_1.csv', 'attack_2.csv', 'normal_5.csv', 'attack_6.csv',

    test_file_paths = ['normal_1.csv', 'attack_2.csv']

    attacks = ["icmp"]  # ["tcp", "icmp"]

    # gen_data_combined(train_file_paths, "train", window_size)
    # gen_data_combined(test_file_paths, "test", window_size)

    for attack in attacks:
        # gen_data(train_file_paths, attack, "train", window_size)
        gen_data(test_file_paths, attack, "test", window_size)
        pass


run()
