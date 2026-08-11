#!/usr/bin/env python3
"""
Full Benchmark Runner - bench/run_full_benchmark.py

Executes comprehensive PQC benchmarks across ALL cipher suites.
- NO policy-driven decisions - just iterate through all suites
- 10 seconds of MAVProxy traffic per suite
- Collects metrics from both GCS and Drone
- Consolidates data for IEEE documentation

Usage (GCS side):
    python -m bench.run_full_benchmark --role gcs

Usage (Drone side):
    python -m bench.run_full_benchmark --role drone

The benchmark process:
1. GCS starts in server mode, waiting for drone commands
2. Drone iterates through ALL suites with keys
3. For each suite:
   a. Start crypto proxies on both sides
   b. Wait for handshake completion
   c. Run MAVProxy traffic for TRAFFIC_DURATION seconds
   d. Collect and save metrics
   e. Stop proxies
4. After all suites, consolidate metrics files
"""

import os
import sys
import time
import json
import socket
import signal
import argparse
import threading
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict
import statistics

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG
from core.suites import get_suite, list_suites
from core.process import ManagedProcess
from core.metrics_aggregator import MetricsAggregator

# =============================================================================
# Configuration
# =============================================================================

DRONE_HOST = str(CONFIG.get("DRONE_HOST"))
GCS_HOST = str(CONFIG.get("GCS_HOST"))
GCS_CONTROL_PORT = int(CONFIG.get("GCS_CONTROL_PORT", 48080))

DRONE_PLAIN_RX_PORT = int(CONFIG.get("DRONE_PLAINTEXT_RX", 47004))
DRONE_PLAIN_TX_PORT = int(CONFIG.get("DRONE_PLAINTEXT_TX", 47003))
GCS_PLAIN_TX_PORT = int(CONFIG.get("GCS_PLAINTEXT_TX", 47001))
GCS_PLAIN_RX_PORT = int(CONFIG.get("GCS_PLAINTEXT_RX", 47002))

SECRETS_DIR = Path(__file__).parent.parent / "secrets" / "matrix"
ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs" / "full_benchmark"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ========================================
# BENCHMARK PARAMETERS - EDIT HERE
# ========================================
TRAFFIC_DURATION = 10.0  # seconds of MAVProxy traffic per suite
HANDSHAKE_TIMEOUT = 30.0  # seconds to wait for handshake
INTER_SUITE_DELAY = 2.0   # seconds between suites
MAX_RETRIES = 2           # retries per suite on failure

# =============================================================================
# Logging
# =============================================================================

def log(msg: str, level: str = "INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    print(f"[{ts}] [{level}] {msg}", flush=True)

def log_err(msg: str):
    log(msg, "ERROR")

# =============================================================================
# Suite Discovery
# =============================================================================

def get_available_suites() -> List[Dict[str, Any]]:
    """Get all suites that have keys available."""
    all_suites = list_suites()
    available = []
    
    for name, config in all_suites.items():
        suite_dir = SECRETS_DIR / name
        # Check for required key files
        gcs_key = suite_dir / "gcs_signing.key"
        drone_pub = suite_dir / "gcs_signing.pub"
        
        if gcs_key.exists() and drone_pub.exists():
            available.append({"name": name, **config})
    
    return available

# =============================================================================
# Suite Benchmark Result
# =============================================================================

@dataclass
class SuiteBenchmarkResult:
    """Result of benchmarking a single suite."""
    suite_id: str
    success: bool
    
    # Timing
    handshake_duration_ms: float = 0.0
    traffic_duration_s: float = 0.0
    total_duration_s: float = 0.0
    
    # Handshake
    handshake_success: bool = False
    handshake_failure_reason: str = ""
    
    # Crypto Identity
    kem_algorithm: str = ""
    sig_algorithm: str = ""
    aead_algorithm: str = ""
    nist_level: str = ""
    
    # Data Plane (packets)
    packets_sent: int = 0
    packets_received: int = 0
    packets_dropped: int = 0
    packet_loss_ratio: float = 0.0
    
    # Bytes
    bytes_sent: int = 0
    bytes_received: int = 0
    
    # Latency (ms)
    latency_avg_ms: float = 0.0
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0
    latency_max_ms: float = 0.0
    
    # System (GCS) - NO POWER for GCS
    gcs_cpu_avg_percent: float = 0.0
    gcs_cpu_peak_percent: float = 0.0
    gcs_memory_rss_mb: float = 0.0
    
    # System (Drone) - FULL METRICS including power
    drone_cpu_avg_percent: float = 0.0
    drone_cpu_peak_percent: float = 0.0
    drone_memory_rss_mb: float = 0.0
    drone_temperature_c: float = 0.0
    drone_load_avg_1m: float = 0.0
    
    # Power (Drone only)
    drone_power_avg_w: float = 0.0
    drone_power_peak_w: float = 0.0
    drone_energy_total_j: float = 0.0
    drone_energy_per_handshake_j: float = 0.0
    
    # Errors
    error_message: str = ""
    retry_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

# =============================================================================
# Echo Server (Drone)
# =============================================================================

class UdpEchoServer:
    """Echoes UDP packets back through the tunnel."""
    
    def __init__(self, rx_host: str, rx_port: int, tx_port: int):
        self.rx_host = rx_host
        self.rx_port = rx_port
        self.tx_port = tx_port
        self.rx_sock = None
        self.tx_sock = None
        self.running = False
        self.thread = None
        self.stats = {"rx_count": 0, "tx_count": 0, "rx_bytes": 0, "tx_bytes": 0}
        self.lock = threading.Lock()
    
    def start(self):
        if self.running:
            return
        
        self.rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        self.rx_sock.bind((self.rx_host, self.rx_port))
        self.rx_sock.settimeout(1.0)
        
        self.tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.tx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        log(f"Echo server listening on {self.rx_host}:{self.rx_port}")
    
    def _loop(self):
        while self.running:
            try:
                data, addr = self.rx_sock.recvfrom(65535)
                with self.lock:
                    self.stats["rx_count"] += 1
                    self.stats["rx_bytes"] += len(data)
                
                # Echo back
                self.tx_sock.sendto(data, (self.rx_host, self.tx_port))
                with self.lock:
                    self.stats["tx_count"] += 1
                    self.stats["tx_bytes"] += len(data)
            except socket.timeout:
                continue
            except Exception:
                if self.running:
                    pass
    
    def get_stats(self) -> Dict[str, int]:
        with self.lock:
            return self.stats.copy()
    
    def reset_stats(self):
        with self.lock:
            self.stats = {"rx_count": 0, "tx_count": 0, "rx_bytes": 0, "tx_bytes": 0}
    
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.rx_sock:
            self.rx_sock.close()
        if self.tx_sock:
            self.tx_sock.close()

# =============================================================================
# GCS Control Client (Drone -> GCS commands)
# =============================================================================

# Global override for GCS host (set via command line)
_GCS_HOST_OVERRIDE = None

def send_gcs_command(cmd: str, **params) -> dict:
    """Send command to GCS benchmark server."""
    target_host = _GCS_HOST_OVERRIDE or GCS_HOST
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(30.0)
        sock.connect((target_host, GCS_CONTROL_PORT))
        
        request = {"cmd": cmd, **params}
        sock.sendall(json.dumps(request).encode() + b"\n")
        
        response = b""
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if b"\n" in response:
                break
        
        sock.close()
        return json.loads(response.decode().strip())
    except Exception as e:
        return {"status": "error", "message": str(e)}

# =============================================================================
# Proxy Managers
# =============================================================================

class ProxyManager:
    """Manages crypto proxy subprocess."""
    
    def __init__(self, role: str, logs_dir: Path):
        self.role = role
        self.logs_dir = logs_dir
        self.managed_proc = None
        self.current_suite = None
        self._log_handle = None
    
    def start(self, suite_name: str) -> bool:
        """Start proxy with given suite."""
        if self.managed_proc and self.managed_proc.is_running():
            self.stop()
        
        suite = get_suite(suite_name)
        if not suite:
            log_err(f"Unknown suite: {suite_name}")
            return False
        
        secret_dir = SECRETS_DIR / suite_name
        
        if self.role == "drone":
            peer_pubkey = secret_dir / "gcs_signing.pub"
            if not peer_pubkey.exists():
                log_err(f"Missing key: {peer_pubkey}")
                return False
            
            cmd = [
                sys.executable, "-m", "core.run_proxy", "drone",
                "--suite", suite_name,
                "--peer-pubkey-file", str(peer_pubkey),
                "--quiet",
                "--status-file", str(self.logs_dir / "drone_status.json")
            ]
        else:  # gcs
            gcs_key = secret_dir / "gcs_signing.key"
            if not gcs_key.exists():
                log_err(f"Missing key: {gcs_key}")
                return False
            
            cmd = [
                sys.executable, "-m", "core.run_proxy", "gcs",
                "--suite", suite_name,
                "--gcs-secret-file", str(gcs_key),
                "--quiet",
                "--status-file", str(self.logs_dir / "gcs_status.json")
            ]
        
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        log_path = self.logs_dir / f"{self.role}_{suite_name}_{timestamp}.log"
        self._log_handle = open(log_path, "w", encoding="utf-8")
        
        self.managed_proc = ManagedProcess(
            cmd=cmd,
            name=f"proxy-{suite_name}",
            stdout=self._log_handle,
            stderr=subprocess.STDOUT
        )
        
        if self.managed_proc.start():
            self.current_suite = suite_name
            time.sleep(2.0)
            if not self.managed_proc.is_running():
                log_err(f"Proxy exited early for {suite_name}")
                return False
            return True
        return False
    
    def stop(self):
        """Stop proxy."""
        if self.managed_proc:
            self.managed_proc.stop()
            self.managed_proc = None
            self.current_suite = None
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None
    
    def is_running(self) -> bool:
        return self.managed_proc is not None and self.managed_proc.is_running()

# =============================================================================
# GCS Benchmark Server
# =============================================================================

class GcsBenchmarkServer:
    """GCS runs as server, responding to drone benchmark commands."""
    
    def __init__(self, logs_dir: Path, run_id: str):
        self.logs_dir = logs_dir
        self.run_id = run_id
        self.proxy = ProxyManager("gcs", logs_dir)
        self.metrics = MetricsAggregator(role="gcs", output_dir=str(logs_dir / "metrics"))
        self.metrics.set_run_id(run_id)
        
        self.server_sock = None
        self.running = False
        self.thread = None
        
        # MAVProxy subprocess
        self.mavproxy_proc = None
    
    def start_mavproxy(self) -> bool:
        """Start persistent MAVProxy for GCS."""
        bind_host = str(CONFIG.get("GCS_PLAINTEXT_BIND", "0.0.0.0"))
        listen_port = GCS_PLAIN_RX_PORT
        
        master_str = f"udpin:{bind_host}:{listen_port}"
        
        cmd = [
            sys.executable, "-m", "MAVProxy.mavproxy",
            f"--master={master_str}",
            "--dialect=ardupilotmega",
            "--nowait",
            "--daemon",
        ]
        
        log_path = self.logs_dir / f"mavproxy_gcs_{time.strftime('%Y%m%d-%H%M%S')}.log"
        fh = open(log_path, "w", encoding="utf-8")
        
        self.mavproxy_proc = ManagedProcess(
            cmd=cmd,
            name="mavproxy-gcs",
            stdout=fh,
            stderr=subprocess.STDOUT,
            new_console=False
        )
        
        if self.mavproxy_proc.start():
            time.sleep(2.0)
            if self.mavproxy_proc.is_running():
                log("GCS MAVProxy started")
                return True
        return False
    
    def start(self):
        """Start the benchmark server."""
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind(("0.0.0.0", GCS_CONTROL_PORT))
        self.server_sock.listen(5)
        self.server_sock.settimeout(1.0)
        
        self.running = True
        self.thread = threading.Thread(target=self._server_loop, daemon=True)
        self.thread.start()
        
        log(f"GCS Benchmark Server listening on port {GCS_CONTROL_PORT}")
    
    def _server_loop(self):
        while self.running:
            try:
                client, addr = self.server_sock.accept()
                self._handle_client(client)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    log_err(f"Server error: {e}")
    
    def _handle_client(self, client):
        try:
            data = b""
            client.settimeout(10.0)
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break
            
            if data:
                request = json.loads(data.decode().strip())
                response = self._handle_command(request)
                client.sendall(json.dumps(response).encode() + b"\n")
        except Exception as e:
            log_err(f"Client error: {e}")
        finally:
            client.close()
    
    def _handle_command(self, request: dict) -> dict:
        cmd = request.get("cmd", "")
        
        if cmd == "ping":
            return {"status": "ok", "message": "pong", "role": "gcs_benchmark"}
        
        elif cmd == "start_suite":
            suite = request.get("suite")
            suite_config = request.get("suite_config", {})
            
            log(f"Starting suite: {suite}")
            
            # Start metrics collection
            self.metrics.start_suite(suite, suite_config)
            self.metrics.record_handshake_start()
            
            # Start proxy
            if not self.proxy.start(suite):
                self.metrics.record_handshake_end(success=False, failure_reason="proxy_start_failed")
                return {"status": "error", "message": "proxy_start_failed"}
            
            self.metrics.record_handshake_end(success=True)
            self.metrics.record_traffic_start()
            
            return {"status": "ok", "message": "suite_started"}
        
        elif cmd == "stop_suite":
            log("Stopping suite")
            
            self.metrics.record_traffic_end()
            
            # Finalize metrics
            final_metrics = self.metrics.finalize_suite()
            
            # Stop proxy
            self.proxy.stop()
            
            # Return GCS metrics for consolidation
            return {
                "status": "ok",
                "message": "suite_stopped",
                "gcs_metrics": self.metrics.get_exportable_data() if self.metrics._current_metrics else {}
            }
        
        elif cmd == "get_metrics":
            # Return current metrics snapshot
            return {
                "status": "ok",
                "metrics": self.metrics.get_exportable_data() if self.metrics._current_metrics else {}
            }
        
        elif cmd == "shutdown":
            log("Shutdown command received")
            self.running = False
            return {"status": "ok", "message": "shutting_down"}
        
        return {"status": "error", "message": f"unknown command: {cmd}"}
    
    def stop(self):
        """Stop the benchmark server."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.server_sock:
            self.server_sock.close()
        if self.proxy:
            self.proxy.stop()
        if self.mavproxy_proc:
            self.mavproxy_proc.stop()

# =============================================================================
# Drone Benchmark Controller
# =============================================================================

class DroneBenchmarkController:
    """Drone controls the benchmark, iterating through all suites."""
    
    def __init__(self, logs_dir: Path, run_id: str, suites: List[Dict[str, Any]]):
        self.logs_dir = logs_dir
        self.run_id = run_id
        self.suites = suites
        
        self.proxy = ProxyManager("drone", logs_dir)
        self.metrics = MetricsAggregator(role="drone", output_dir=str(logs_dir / "metrics"))
        self.metrics.set_run_id(run_id)
        
        self.echo_server = UdpEchoServer(DRONE_HOST, DRONE_PLAIN_RX_PORT, DRONE_PLAIN_TX_PORT)
        self.mavproxy_proc = None
        
        self.results: List[SuiteBenchmarkResult] = []
    
    def start_mavproxy(self) -> bool:
        """Start persistent MAVProxy for drone."""
        master = str(CONFIG.get("MAV_MASTER", "/dev/ttyACM0"))
        out_arg = f"udp:127.0.0.1:{DRONE_PLAIN_TX_PORT}"
        
        cmd = [
            sys.executable, "-m", "MAVProxy.mavproxy",
            f"--master={master}",
            f"--out={out_arg}",
            "--nowait",
            "--daemon",
        ]
        
        log_path = self.logs_dir / f"mavproxy_drone_{time.strftime('%Y%m%d-%H%M%S')}.log"
        fh = open(log_path, "w", encoding="utf-8")
        
        self.mavproxy_proc = ManagedProcess(
            cmd=cmd,
            name="mavproxy-drone",
            stdout=fh,
            stderr=subprocess.STDOUT,
            new_console=False
        )
        
        if self.mavproxy_proc.start():
            time.sleep(2.0)
            if self.mavproxy_proc.is_running():
                log("Drone MAVProxy started")
                return True
        return False
    
    def wait_for_gcs(self, timeout: float = 30.0) -> bool:
        """Wait for GCS benchmark server to be ready."""
        start = time.time()
        while time.time() - start < timeout:
            result = send_gcs_command("ping")
            if result.get("status") == "ok":
                return True
            time.sleep(0.5)
        return False
    
    def wait_for_handshake(self, timeout: float = HANDSHAKE_TIMEOUT) -> bool:
        """Wait for handshake completion by checking status file."""
        status_file = self.logs_dir / "drone_status.json"
        start = time.time()
        while time.time() - start < timeout:
            if status_file.exists():
                try:
                    with open(status_file, "r") as f:
                        data = json.load(f)
                        if data.get("status") == "handshake_ok":
                            return True
                except Exception:
                    pass
            time.sleep(0.1)
        return False
    
    def benchmark_suite(self, suite: Dict[str, Any]) -> SuiteBenchmarkResult:
        """Benchmark a single suite."""
        suite_name = suite["name"]
        result = SuiteBenchmarkResult(suite_id=suite_name, success=False)
        
        # Fill crypto identity
        result.kem_algorithm = suite.get("kem_name", "")
        result.sig_algorithm = suite.get("sig_name", "")
        result.aead_algorithm = suite.get("aead", "")
        result.nist_level = suite.get("nist_level", "")
        
        start_time = time.time()
        
        try:
            log(f"[{suite_name}] Starting benchmark...")
            
            # Reset echo server stats
            self.echo_server.reset_stats()
            
            # Start metrics collection
            self.metrics.start_suite(suite_name, suite)
            self.metrics.record_handshake_start()
            
            # Tell GCS to start proxy
            log(f"[{suite_name}] Telling GCS to start proxy...")
            gcs_resp = send_gcs_command("start_suite", suite=suite_name, suite_config=suite)
            if gcs_resp.get("status") != "ok":
                result.error_message = f"GCS start failed: {gcs_resp.get('message', 'unknown')}"
                result.handshake_failure_reason = result.error_message
                log_err(f"[{suite_name}] {result.error_message}")
                self.metrics.record_handshake_end(success=False, failure_reason=result.error_message)
                self.metrics.finalize_suite()
                return result
            
            # Start drone proxy
            log(f"[{suite_name}] Starting drone proxy...")
            if not self.proxy.start(suite_name):
                result.error_message = "Drone proxy start failed"
                result.handshake_failure_reason = result.error_message
                log_err(f"[{suite_name}] {result.error_message}")
                self.metrics.record_handshake_end(success=False, failure_reason=result.error_message)
                self.metrics.finalize_suite()
                send_gcs_command("stop_suite")
                return result
            
            # Wait for handshake
            log(f"[{suite_name}] Waiting for handshake...")
            handshake_start = time.time()
            if not self.wait_for_handshake():
                result.error_message = "Handshake timeout"
                result.handshake_failure_reason = result.error_message
                log_err(f"[{suite_name}] {result.error_message}")
                self.metrics.record_handshake_end(success=False, failure_reason=result.error_message)
                self.metrics.finalize_suite()
                self.proxy.stop()
                send_gcs_command("stop_suite")
                return result
            
            handshake_duration = (time.time() - handshake_start) * 1000
            result.handshake_duration_ms = handshake_duration
            result.handshake_success = True
            
            self.metrics.record_handshake_end(success=True)
            log(f"[{suite_name}] Handshake complete in {handshake_duration:.1f}ms")
            
            # Run traffic for TRAFFIC_DURATION seconds
            log(f"[{suite_name}] Running traffic for {TRAFFIC_DURATION}s...")
            self.metrics.record_traffic_start()
            traffic_start = time.time()
            
            # Just wait - MAVProxy is already forwarding traffic
            time.sleep(TRAFFIC_DURATION)
            
            self.metrics.record_traffic_end()
            result.traffic_duration_s = time.time() - traffic_start
            
            # Get echo server stats
            echo_stats = self.echo_server.get_stats()
            result.packets_received = echo_stats["rx_count"]
            result.packets_sent = echo_stats["tx_count"]
            result.bytes_received = echo_stats["rx_bytes"]
            result.bytes_sent = echo_stats["tx_bytes"]
            
            log(f"[{suite_name}] Traffic complete. RX: {result.packets_received} pkts, TX: {result.packets_sent} pkts")
            
            # Stop suite on GCS and get metrics
            log(f"[{suite_name}] Stopping suite...")
            gcs_resp = send_gcs_command("stop_suite")
            
            # Finalize drone metrics
            final_metrics = self.metrics.finalize_suite()
            
            # Stop drone proxy
            self.proxy.stop()
            
            # Extract metrics from final_metrics
            if final_metrics:
                # Drone system
                result.drone_cpu_avg_percent = final_metrics.system_drone.cpu_usage_avg_percent
                result.drone_cpu_peak_percent = final_metrics.system_drone.cpu_usage_peak_percent
                result.drone_memory_rss_mb = final_metrics.system_drone.memory_rss_mb
                result.drone_temperature_c = final_metrics.system_drone.temperature_c
                result.drone_load_avg_1m = final_metrics.system_drone.load_avg_1m
                
                # Drone power
                result.drone_power_avg_w = final_metrics.power_energy.power_avg_w
                result.drone_power_peak_w = final_metrics.power_energy.power_peak_w
                result.drone_energy_total_j = final_metrics.power_energy.energy_total_j
                result.drone_energy_per_handshake_j = final_metrics.power_energy.energy_per_handshake_j
            
            result.total_duration_s = time.time() - start_time
            result.success = True
            
            log(f"[{suite_name}] Benchmark complete. Duration: {result.total_duration_s:.1f}s")
            
        except Exception as e:
            result.error_message = str(e)
            log_err(f"[{suite_name}] Exception: {e}")
            try:
                self.proxy.stop()
                send_gcs_command("stop_suite")
            except Exception:
                pass
        
        return result
    
    def run_all_benchmarks(self) -> List[SuiteBenchmarkResult]:
        """Run benchmarks for all suites."""
        log(f"Starting full benchmark run: {len(self.suites)} suites")
        log(f"Run ID: {self.run_id}")
        log(f"Traffic duration: {TRAFFIC_DURATION}s per suite")
        
        # Start echo server
        self.echo_server.start()
        
        # Start MAVProxy
        if not self.start_mavproxy():
            log_err("Failed to start MAVProxy")
        
        # Wait for GCS
        log("Waiting for GCS benchmark server...")
        if not self.wait_for_gcs():
            log_err("GCS benchmark server not responding")
            return []
        log("GCS benchmark server ready")
        
        total_suites = len(self.suites)
        
        for idx, suite in enumerate(self.suites, 1):
            suite_name = suite["name"]
            log(f"\n{'='*60}")
            log(f"Suite {idx}/{total_suites}: {suite_name}")
            log(f"{'='*60}")
            
            # Try benchmark with retries
            result = None
            for attempt in range(MAX_RETRIES + 1):
                if attempt > 0:
                    log(f"[{suite_name}] Retry {attempt}/{MAX_RETRIES}")
                    time.sleep(INTER_SUITE_DELAY)
                
                result = self.benchmark_suite(suite)
                result.retry_count = attempt
                
                if result.success:
                    break
            
            self.results.append(result)
            
            # Inter-suite delay
            if idx < total_suites:
                time.sleep(INTER_SUITE_DELAY)
        
        # Cleanup
        self.echo_server.stop()
        if self.mavproxy_proc:
            self.mavproxy_proc.stop()
        
        # Tell GCS to shutdown
        send_gcs_command("shutdown")
        
        return self.results
    
    def save_results(self):
        """Save benchmark results to JSON."""
        summary = {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "traffic_duration_s": TRAFFIC_DURATION,
            "total_suites": len(self.suites),
            "successful_suites": sum(1 for r in self.results if r.success),
            "failed_suites": sum(1 for r in self.results if not r.success),
            "results": [r.to_dict() for r in self.results]
        }
        
        output_file = self.logs_dir / f"benchmark_results_{self.run_id}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
        
        log(f"Results saved to: {output_file}")
        return output_file

# =============================================================================
# Main
# =============================================================================

def main():
    global _GCS_HOST_OVERRIDE
    
    parser = argparse.ArgumentParser(description="Full PQC Benchmark Runner")
    parser.add_argument("--role", choices=["gcs", "drone"], required=True,
                        help="Role: gcs (server) or drone (controller)")
    parser.add_argument("--run-id", default=None,
                        help="Run ID (default: timestamp)")
    parser.add_argument("--max-suites", type=int, default=None,
                        help="Maximum number of suites to benchmark")
    parser.add_argument("--suite", default=None,
                        help="Single suite to benchmark (for testing)")
    parser.add_argument("--gcs-host", default=None,
                        help="Override GCS host IP (e.g., for Tailscale)")
    args = parser.parse_args()
    
    # Set GCS host override
    if args.gcs_host:
        _GCS_HOST_OVERRIDE = args.gcs_host
    
    # Generate run ID
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    # Create logs directory for this run
    logs_dir = LOGS_DIR / run_id
    logs_dir.mkdir(parents=True, exist_ok=True)
    (logs_dir / "metrics").mkdir(exist_ok=True)
    
    print("=" * 60)
    print(f"Full PQC Benchmark - {args.role.upper()}")
    print("=" * 60)
    print(f"Run ID: {run_id}")
    print(f"Logs: {logs_dir}")
    print(f"Traffic Duration: {TRAFFIC_DURATION}s per suite")
    print()
    
    if args.role == "gcs":
        # GCS runs as server
        server = GcsBenchmarkServer(logs_dir, run_id)
        server.start()
        
        # Start MAVProxy
        if not server.start_mavproxy():
            log_err("Failed to start MAVProxy")
        
        log("GCS benchmark server running. Waiting for drone commands...")
        log("Press Ctrl+C to stop")
        
        shutdown = threading.Event()
        
        def signal_handler(sig, frame):
            log("Shutdown signal received")
            shutdown.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        
        try:
            while server.running and not shutdown.is_set():
                shutdown.wait(timeout=1.0)
        finally:
            server.stop()
        
        log("GCS benchmark server stopped")
        
    else:
        # Drone runs as controller
        # Get available suites
        suites = get_available_suites()
        log(f"Found {len(suites)} suites with keys")
        
        # Filter if specific suite requested
        if args.suite:
            suites = [s for s in suites if s["name"] == args.suite]
            if not suites:
                log_err(f"Suite not found: {args.suite}")
                return 1
        
        # Limit if requested
        if args.max_suites:
            suites = suites[:args.max_suites]
        
        controller = DroneBenchmarkController(logs_dir, run_id, suites)
        
        def signal_handler(sig, frame):
            log("Interrupted - saving partial results")
            controller.save_results()
            sys.exit(1)
        
        signal.signal(signal.SIGINT, signal_handler)
        
        # Run benchmarks
        results = controller.run_all_benchmarks()
        
        # Save results
        output_file = controller.save_results()
        
        # Print summary
        print("\n" + "=" * 60)
        print("BENCHMARK SUMMARY")
        print("=" * 60)
        successful = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        print(f"Total suites: {len(results)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        
        if successful > 0:
            avg_handshake = statistics.mean([r.handshake_duration_ms for r in results if r.success])
            print(f"Average handshake: {avg_handshake:.1f}ms")
        
        print(f"\nResults saved to: {output_file}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
