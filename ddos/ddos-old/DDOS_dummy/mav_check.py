from scapy.all import *
from time import time

def packet_callback(packet):
    if IP in packet and UDP in packet:
        udp_payload = packet[UDP].payload
        if Raw in packet:
            raw_payload = packet[Raw].load
            raw_data = str(raw_payload[:1])
            pre1 = raw_data.replace("b", "")
            pre2 = pre1.replace("'", "")
            pre3 = pre2.replace(" ", "")
            if pre3 == "\\xfd":
                print(time(), "A")
                return 
    return 

# Sniff the network for Mavlink packets
mavlink_packets = sniff(prn=packet_callback, store=0, iface="wlan0")

# Process the captured Mavlink packets
for packet in mavlink_packets:
    print(packet.summary())
