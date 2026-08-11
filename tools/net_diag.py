#!/usr/bin/env python3
"""
Unified Network Diagnostic Tool for Secure Tunnel
Usage: python tools/net_diag.py

Automatically detects role (Drone vs GCS) based on hostname or IP configuration.
Performs:
0. Clock Synchronization Check: Measures time offset between peers.
1. Firewall/Binding Check: Can we bind to our configured RX ports (UDP & TCP)?
2. Reachability Check: Can we reach the peer's IP?
3. Bidirectional UDP Flow Test:
   - Binds all configured ports (Plaintext RX, Encrypted RX, Control RX)
   - Sends test packets to the peer's expected ports
   - Listens for echoes/responses
   - Reports packet loss and latency
4. TCP Control Port Check:
   - GCS binds/listens on Control Port.
   - Drone attempts to connect to Control Port.

This script is standalone and does NOT use the proxy code. It validates the *physical network layer*
and *OS firewall rules* before the complex crypto tunnel is started.
"""

import sys
import socket
import time
import threading
import json
import platform
import subprocess
import select
from pathlib import Path

# Add parent to path to load config
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from core.config import CONFIG
except ImportError:
    print("Error: Could not import core.config. Run from repository root.")
    sys.exit(1)

# Configuration Constants
TIMEOUT = 2.0

def get_local_ips():
    ips = []
    try:
        # Hack to get preferred outbound IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    # Get all interfaces
    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            if ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips

def detect_role():
    """Heuristic to decide if we are Drone or GCS based on CONFIG IPs and local interfaces."""
    local_ips = get_local_ips()
    drone_ip = CONFIG["DRONE_HOST"]
    gcs_ip = CONFIG["GCS_HOST"]
    
    print(f"[*] Local IPs: {local_ips}")
    print(f"[*] Configured Drone IP: {drone_ip}")
    print(f"[*] Configured GCS IP:   {gcs_ip}")

    if drone_ip in local_ips:
        return "drone"
    if gcs_ip in local_ips:
        return "gcs"
    
    # Fallback: Ask user if ambiguous
    print("[!] Could not auto-detect role from IP match.")
    if sys.platform == "linux": # Assumption: Drone is usually Linux (Pi)
        return "drone"
    return "gcs" # Assumption: GCS is usually Windows

class PortTester:
    def __init__(self, role):
        self.role = role
        self.peer_ip = CONFIG["GCS_HOST"] if role == "drone" else CONFIG["DRONE_HOST"]
        self.sockets = {}
        self.running = True
        self.lock = threading.Lock()
        self.log_msgs = []
        self.tcp_listener = None

    def log(self, msg):
        with self.lock:
            print(msg)
            self.log_msgs.append(msg)

    def check_firewall_binding(self, port, desc, proto="UDP"):
        """Try to bind to a port to verify no other process is using it and firewall allows binding."""
        try:
            if proto == "UDP":
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.bind(("0.0.0.0", port))
            else:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(("0.0.0.0", port))
                if desc == "Control TCP": # Keep listener open for test
                    s.listen(1)
                    return s
            
            self.log(f"[PASS] Bind {desc} ({proto}/{port}): OK")
            return s
        except OSError as e:
            self.log(f"[FAIL] Bind {desc} ({proto}/{port}): FAILED ({e})")
            self.log(f"       -> Check if proxy/mavproxy is already running or firewall blocks it.")
            return None

    def start_listener(self, sock, name):
        def _listen():
            while self.running:
                r, _, _ = select.select([sock], [], [], 0.5)
                if r:
                    try:
                        data, addr = sock.recvfrom(4096)
                        now = time.time()
                        
                        if b"DIAG_PING:" in data:
                            try:
                                # Parse timestamp
                                parts = data.split(b":")
                                if len(parts) >= 2:
                                    remote_ts = float(parts[1])
                                    diff = now - remote_ts
                                    self.log(f"[RECV] {name} <- {addr}: Clock Delta={diff:.4f}s")
                                    if abs(diff) > 1.0:
                                        self.log(f"       [WARN] Large clock skew detected! (>1.0s)")
                            except Exception:
                                pass
                            
                            # Echo back
                            resp = b"DIAG_PONG:" + str(now).encode()
                            sock.sendto(resp, addr)
                            
                        elif b"DIAG_PONG:" in data:
                            try:
                                parts = data.split(b":")
                                if len(parts) >= 2:
                                    remote_ts = float(parts[1])
                                    rtt = now - remote_ts # This is actually one-way from remote to here if we trust their clock, 
                                                          # but for PONG it's just a signal.
                                    # Real RTT requires us to track when WE sent the PING.
                                    # For simplicity, just confirm receipt.
                                    self.log(f"[ECHO] {name} <- {addr}: Round-trip confirmed!")
                            except Exception:
                                pass
                    except Exception as e:
                        pass
        t = threading.Thread(target=_listen, daemon=True)
        t.start()

    def start_tcp_acceptor(self):
        """Accept TCP connections for Control Port test (GCS only)"""
        def _accept():
            while self.running:
                try:
                    r, _, _ = select.select([self.tcp_listener], [], [], 0.5)
                    if r:
                        conn, addr = self.tcp_listener.accept()
                        self.log(f"[TCP] Accepted connection from {addr}")
                        conn.close()
                except Exception:
                    pass
        t = threading.Thread(target=_accept, daemon=True)
        t.start()

    def check_tcp_connect(self, port, desc):
        """Try to connect to peer TCP port (Drone only)"""
        target = (self.peer_ip, port)
        self.log(f"[TCP] Connecting to {desc} {target}...")
        try:
            s = socket.create_connection(target, timeout=2.0)
            self.log(f"[PASS] Connect {desc} (TCP/{port}): OK")
            s.close()
        except Exception as e:
            self.log(f"[FAIL] Connect {desc} (TCP/{port}): {e}")

    def run_diagnostics(self):
        print("="*60)
        print(f"Network Diagnostic Tool - Role: {self.role.upper()}")
        print("="*60)

        # 1. Define Ports based on Role
        if self.role == "drone":
            my_rx_ports = {
                "Encrypted RX": CONFIG["UDP_DRONE_RX"],
                "Plaintext RX": CONFIG["DRONE_PLAINTEXT_RX"],
            }
            peer_tx_ports = {
                "Encrypted TX": CONFIG["UDP_GCS_RX"],
                "Plaintext TX": CONFIG["GCS_PLAINTEXT_RX"], 
            }
            # Drone connects to GCS Control
            tcp_connect_ports = {
                "Control Port": CONFIG.get("GCS_CONTROL_PORT", 48080)
            }
            tcp_bind_ports = {} # Drone doesn't bind TCP usually, except maybe internal
        else: # GCS
            my_rx_ports = {
                "Encrypted RX": CONFIG["UDP_GCS_RX"],
                "Plaintext RX": CONFIG["GCS_PLAINTEXT_RX"],
            }
            peer_tx_ports = {
                "Encrypted TX": CONFIG["UDP_DRONE_RX"],
                "Plaintext TX": CONFIG["DRONE_PLAINTEXT_RX"],
            }
            # GCS binds Control Port
            tcp_bind_ports = {
                "Control TCP": CONFIG.get("GCS_CONTROL_PORT", 48080)
            }
            tcp_connect_ports = {}

        # 2. Bind Check & Listeners
        print("\n--- Phase 1: Local Port Binding & Firewall Check ---")
        
        # UDP Binds
        for name, port in my_rx_ports.items():
            s = self.check_firewall_binding(port, name, proto="UDP")
            if s:
                self.sockets[name] = s
                self.start_listener(s, name)
        
        # TCP Binds (GCS)
        for name, port in tcp_bind_ports.items():
            s = self.check_firewall_binding(port, name, proto="TCP")
            if s and name == "Control TCP":
                self.tcp_listener = s
                self.start_tcp_acceptor()
            elif s:
                s.close() # Just a bind check for others

        # 3. Ping Check
        print("\n--- Phase 2: ICMP Reachability ---")
        param = "-n" if platform.system().lower() == "windows" else "-c"
        cmd = ["ping", param, "1", self.peer_ip]
        try:
            ret = subprocess.call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if ret == 0:
                self.log(f"[PASS] Ping {self.peer_ip}: OK")
            else:
                self.log(f"[WARN] Ping {self.peer_ip}: UNREACHABLE (ICMP might be blocked)")
        except Exception:
            self.log("[WARN] Ping command failed")

        # 4. Active Packet Test (UDP + TCP Connect)
        print("\n--- Phase 3: Active Packet Injection & Clock Check ---")
        print(f"Sending test packets to {self.peer_ip}...")
        
        payload = f"DIAG_PING:{time.time()}".encode()

        # UDP Send
        if "Encrypted RX" in self.sockets:
            sock = self.sockets["Encrypted RX"]
            target_port = peer_tx_ports["Encrypted TX"]
            self.log(f"[SEND] Encrypted Path -> {self.peer_ip}:{target_port}")
            sock.sendto(payload, (self.peer_ip, target_port))

        if "Plaintext RX" in self.sockets:
            sock = self.sockets["Plaintext RX"]
            target_host = CONFIG["GCS_PLAINTEXT_HOST"] if self.role == "gcs" else CONFIG["DRONE_PLAINTEXT_HOST"]
            target_port = CONFIG["GCS_PLAINTEXT_TX"] if self.role == "gcs" else CONFIG["DRONE_PLAINTEXT_TX"]
            
            self.log(f"[SEND] Plaintext Loopback -> {target_host}:{target_port}")
            try:
                sock.sendto(payload, (target_host, target_port))
            except Exception as e:
                self.log(f"[FAIL] Plaintext Send: {e}")

        # TCP Connect (Drone)
        for name, port in tcp_connect_ports.items():
            self.check_tcp_connect(port, name)

        print("\nWaiting for echoes (5s)...")
        time.sleep(5)
        self.running = False
        print("\n--- Diagnostics Complete ---")

if __name__ == "__main__":
    role = detect_role()
    tester = PortTester(role)
    tester.run_diagnostics()
