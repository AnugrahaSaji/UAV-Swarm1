import random
import socket
import struct
import sqlite3
from time import time, sleep
from queue import Queue
import scapy.all as scapy
from threading import Thread
import xgboost as xgb

from http.server import SimpleHTTPRequestHandler
from socketserver import TCPServer
from urllib.parse import parse_qs, urlparse
import sys
import json


import os
# Get the directory of the current script
script_directory = os.path.dirname(os.path.realpath(__file__))
# Set the current working directory to the script directory
os.chdir(script_directory)

lookback = 5
window_size = 0.60
insert_query = ""
flag = 0

packet_rate = []
status = []

port_address = 8000

network_attack = False
detection_halt = time()
detection_halt_window = 30

##################################################################################################################

# Capture Component


def capture(capture_queue_in):
    def packet_callback(packet):
        if scapy.IP in packet and scapy.UDP in packet:
            udp_payload = packet[scapy.UDP].payload
            if scapy.Raw in packet:
                raw_payload = packet[scapy.Raw].load
                raw_data = str(raw_payload[:1])
                pre1 = raw_data.replace("b", "")
                pre2 = pre1.replace("'", "")
                pre3 = pre2.replace(" ", "")
                if pre3 == "\\xfd":
                    capture_queue_in.put(float(time()))
                    return
        return
    scapy.sniff(prn=packet_callback, store=0, iface="wlan0")


##########################################################################################
# DDOS Module


# Pre-Process Component
def ddos_preprocess(capture_queue_out, detection_queue_in, input_storage_queue_in):
    previous_processed_time = time()
    initial_run = True
    global packet_rate
    while True:
        if initial_run:
            data = [0 for i in range(lookback)]  # list of data points
            for datapoint in range(lookback):
                while (time() - previous_processed_time) < window_size:
                    if not capture_queue_out.empty():
                        capture_queue_out.get()
                        data[datapoint] = data[datapoint] + 1
                previous_processed_time = time()
            initial_run = False
            packet_rate = data
        else:
            data = data[1:]
            count = 0
            while (time() - previous_processed_time) < window_size:
                if not capture_queue_out.empty():
                    capture_queue_out.get()
                    count += 1
            data.append(count)
        #    packet_rate.append(count)
       # print("data point is ", data)
        detection_queue_in.put(data)
        input_storage_queue_in.put(data)
       # if len(packet_rate) > 1000:
       #     packet_rate = packet_rate[-1000:]
        previous_processed_time = time()


# Detection Component


def ddos_detection(detection_queue_out, mitigation_queue_in, output_storage_queue_in):
    # Load Model
    model = xgb.XGBClassifier()
    model.load_model('xgboost_model.bin')
   # global status
    prev_time = time()
    global detection_halt
    global detection_halt_window
    global network_attack
    while True:
        data_point = [detection_queue_out.get()]
        if time()-prev_time > 0:
            if network_attack:
                if time() - detection_halt > detection_halt_window:
                    network_attack = False
            else:
                start_predict = time()
                output = model.predict(data_point)[0]
                end_predict = time()
                print("Pridiction Time is ", (end_predict-start_predict)
                      * 10**3, "ms", ' output ', output)
                mitigation_queue_in.put(output)
                output_storage_queue_in.put(output)
                prev_time = time()

# Mitigation Component


def ddos_mitigation(mitigation_queue_out):
    prev_time = time()
    status_list = []
    context_length = 40
    global network_attack
    global detection_halt
    global detection_halt_window
    while True:
        status = mitigation_queue_out.get()
        status_list.append(status)
        if len(status_list) > context_length:
            status_list = status_list[-1*context_length:]

        if status:
            if ((time()-prev_time > 40) and (sum(status_list) > 30)):
                # Clear Network Stats
                os.system('conntrack -F')
                os.system('ip neigh flush all')
                sleep(2)
                # Release the IP
                os.system("dhclient -r wlan0")
                sleep(1)
                # Change the MAC
                os.system("macchanger -r wlan0")
                sleep(5)
                # Renew IP
                os.system("dhclient wlan0")
                network_attack = True
                # ip_command = "ifconfig wlan0 " + str(socket.inet_ntoa(struct.pack('>I',random.randint(1, 0xffffffff))))
                # os.system(ip_command)
                # os.system('dhclient wlan0')
                detection_halt = time()
                print("Detection Halted for ",
                      detection_halt_window, " seconds")
                prev_time = time()
            else:
                pass
        else:
            pass

###################################################################################################################################
# Storage Componenet


def gen_table_name(decode=False, table_name="", raw=False):
    global lookback
    global window_size

    if raw:
        return "L" + str(lookback) + "WS" + str(window_size)

    digit_mapping = {
        '0': 'Z',
        '1': 'O',
        '2': 'T',
        '3': 'T',
        '4': 'f',
        '5': 'F',
        '6': 's',
        '7': 'S',
        '8': 'E',
        '9': 'N',
        '.': 'P'
    }
    reversed_mapping = {value: key for key, value in digit_mapping.items()}

    if not decode:
        encoded_lookback = ''.join([digit_mapping[digit]
                                    for digit in str(lookback)])
        encoded_window_size = ''.join(
            [digit_mapping[digit] for digit in str(window_size)])
        return encoded_lookback + "D" + encoded_window_size
    else:
        decoded_lookback = table_name.split("D")[0]
        decoded_window_size = table_name.split("D")[1]
        decoded_lookback = int(
            ''.join([reversed_mapping[elem] for elem in decoded_lookback]))
        decoded_window_size = float(
            ''.join([reversed_mapping[elem] for elem in decoded_window_size]))
        return decoded_lookback, decoded_window_size


def create_input_table():
    conn = sqlite3.connect('input.db')
    cursor = conn.cursor()
    global lookback
    global window_size

    table_name = gen_table_name()

    print("Curent Table name is: ", table_name)

    query = 'CREATE TABLE IF NOT EXISTS ' + table_name + \
        " ( id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL,"

    insert_query = 'INSERT INTO ' + table_name + " ( timestamp, "

    insert_query_end = "( ?, "
    if lookback > 1:
        for column in range(lookback-1):
            query += ' c' + str(column) + ' REAL, '
            insert_query += 'c' + str(column) + ', '
            insert_query_end += "?, "

    query += ' c' + str(lookback-1) + ' REAL, label REAL )'
    insert_query += 'c' + str(lookback-1) + \
        ', label) VALUES ' + insert_query_end + '?, ?)'

    # print(query)
    # print(insert_query)

    cursor.execute(query)
    conn.commit()
    return insert_query


def create_output_table():
    conn = sqlite3.connect('output.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS unprocessed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL, status REAL
        )
    ''')
    cursor.execute(
        'CREATE INDEX IF NOT EXISTS value_index ON unprocessed (timestamp)')
    conn.commit()

    return


'INSERT INTO unprocessed (timestamp, status) VALUES (?, ?)'


def store_input(insert_query, input_storage_queue_out):
    process_conn = sqlite3.connect('input.db')
    global flag
    while True:
        data = [time()]
        data = data + input_storage_queue_out.get() + [flag]
        # print("data point is ", data)
        process_conn.execute(insert_query, tuple(data))
        process_conn.commit()


def store_output(output_storage_queue_out):
    process_conn = sqlite3.connect('output.db')
    insert_query = 'INSERT INTO unprocessed (timestamp, status) VALUES (?, ?)'
    while True:
        data = output_storage_queue_out.get()
        process_conn.execute(insert_query, (time(), data))
        process_conn.commit()

##########################################################################################
# Check if the system configuration is modified


def update_config():
    class MyHandler(SimpleHTTPRequestHandler):
        def do_GET(self):
            global flag, lookback, window_size, packet_rate, status

            if self.path.startswith('/update-parameters'):
                parsed_url = urlparse(self.path)
                params = parse_qs(parsed_url.query)
                data_flag = params.get("flag")
                if data_flag is None:
                    pass
                else:
                    flag = int(data_flag[0])
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                response_data = {'status': 'success', 'timestamp': time()}
                self.wfile.write(bytes(json.dumps(response_data), 'utf-8'))

            else:
                super().do_GET()

    Handler = MyHandler
    global port_address
    with TCPServer(("", port_address), Handler) as httpd:
        httpd.serve_forever()

#################################################################################################
# RUN


def run(port):
    global port_address
    port_address = port
    capture_queue = Queue()
    detection_queue = Queue()
    mitigation_queue = Queue()
    input_storage_queue = Queue()
    output_storage_queue = Queue()

    # Capture Component
    capture_thread = Thread(target=capture, args=(capture_queue, ))

    # DDOS
    # Pre Process Module
    ddos_preprocess_thread = Thread(target=ddos_preprocess, args=(
        capture_queue, detection_queue, input_storage_queue))

    # Detection Module
    ddos_detection_thread = Thread(target=ddos_detection, args=(
        detection_queue, mitigation_queue, output_storage_queue))

    # Mitigation Module
    ddos_mitigation_thread = Thread(
        target=ddos_mitigation, args=(mitigation_queue, ))

    # Storage Component
    global insert_query
    insert_query = create_input_table()
    create_output_table()
    input_storage_thread = Thread(
        target=store_input, args=(insert_query, input_storage_queue,))
    output_storage_thread = Thread(
        target=store_output, args=(output_storage_queue,))

    # Config Update
    update_config_thread = Thread(target=update_config)

    capture_thread.start()

    ddos_preprocess_thread.start()
    #ddos_detection_thread.start()
    #ddos_mitigation_thread.start()

    input_storage_thread.start()
    # output_storage_thread.start()

    update_config_thread.start()

#######################################################################################################################


if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1:
        port = int(sys.argv[1])
    run(port)
