#!/usr/bin/env python3
"""
Drone-side LAN Benchmark Controller

This script runs on the RPi Drone and:
1. Controls the benchmark - iterates through all cipher suites
2. Connects to GCS on LAN IP (192.168.0.101)
3. Collects FULL metrics (CPU, memory, temperature, power, load)
4. Consolidates metrics from both sides

Usage (on drone via SSH through Tailscale):
    cd ~/pqc-uav-research
    source cenv/bin/activate
    python -m bench.lan_benchmark_drone --max-suites 2  # Test first
    python -m bench.lan_benchmark_drone                 # All suites

Network Configuration:
    - GCS LAN IP: 192.168.0.101 (benchmark traffic)
    - Drone LAN IP: 192.168.0.105 (benchmark traffic)
    - Tailscale 100.101.93.23: SSH management ONLY

Metrics Collected (Drone side - FULL):
    - CPU usage (average, peak)
    - Memory RSS
    - Temperature (RPi thermal zones)
    - Load average (1m, 5m, 15m)
    - Power (INA219 if available)
      - Voltage, Current, Power
      - Energy per handshake
      - Total energy consumed
    - Packet counts & bytes
    - Latency measurements
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
import statistics
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG
from core.power_monitor import PowerMonitorUnavailable, create_power_monitor
from core.suites import (
    aead_profiles_by_nist_level,
    get_suite,
    list_suites,
    normalize_aead_token,
    normalize_aead_token_for_level,
)
from core.process import ManagedProcess

# =============================================================================
# Network Configuration - LAN IPs for Benchmark
# =============================================================================

# LAN addresses - USED FOR ALL BENCHMARK TRAFFIC
GCS_LAN_IP = CONFIG.get("GCS_HOST_LAN", "192.168.0.101")
DRONE_LAN_IP = CONFIG.get("DRONE_HOST_LAN", "192.168.0.105")
DEFAULT_BENCHMARK_PSK_HEX = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"

# Control port for GCS benchmark server
GCS_CONTROL_PORT = int(CONFIG.get("GCS_CONTROL_PORT", 48080))

# Plaintext ports
DRONE_PLAIN_RX = int(CONFIG.get("DRONE_PLAINTEXT_RX", 47004))
DRONE_PLAIN_TX = int(CONFIG.get("DRONE_PLAINTEXT_TX", 47003))

ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs" / "lan_benchmark"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# =============================================================================
# Benchmark Parameters
# =============================================================================

TRAFFIC_DURATION = 10.0      # seconds of traffic per suite
HANDSHAKE_TIMEOUT = 45.0     # seconds to wait for handshake
INTER_SUITE_DELAY = 3.0      # seconds between suites
MAX_RETRIES = 2              # retries per suite on failure

# =============================================================================
# Logging
# =============================================================================

def log(msg: str, level: str = "INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    print(f"[{ts}] [{level}] {msg}", flush=True)

def log_err(msg: str):
    log(msg, "ERROR")


def _benchmark_proxy_env(*, gcs_host: Optional[str] = None, drone_host: Optional[str] = None) -> Dict[str, str]:
    env = os.environ.copy()
    env["DRONE_PSK"] = env.get("DRONE_PSK") or DEFAULT_BENCHMARK_PSK_HEX
    if gcs_host:
        env["GCS_HOST"] = gcs_host
        env["GCS_HOST_LAN"] = gcs_host
    if drone_host:
        env["DRONE_HOST"] = drone_host
        env["DRONE_HOST_LAN"] = drone_host
    return env

# =============================================================================
# Suite Discovery
# =============================================================================

def get_available_suites(key_root: Path, include: List[str], exclude: List[str]) -> List[Dict[str, Any]]:
    """Build the level-aware suite x AEAD benchmark matrix with available peer keys."""
    all_suites = list_suites()
    available = []
    
    for name, config in all_suites.items():
        suite_dir = key_root / name
        gcs_pub = suite_dir / "gcs_signing.pub"
        
        if gcs_pub.exists():
            level = str(config.get("nist_level", "")).upper()
            if include:
                tokens: List[str] = []
                for token in include:
                    try:
                        tokens.append(normalize_aead_token_for_level(token, level))
                    except ValueError:
                        continue
            else:
                tokens = list(aead_profiles_by_nist_level(runtime_only=True).get(level, ()))

            if exclude:
                blocked = set()
                for token in exclude:
                    try:
                        blocked.add(normalize_aead_token_for_level(token, level))
                    except ValueError:
                        continue
                tokens = [token for token in tokens if token not in blocked]

            for aead_token in dict.fromkeys(tokens):
                available.append({"name": name, **config, "aead_token": aead_token})
    
    return available

# =============================================================================
# Drone Metrics Collector (Full - including power)
# =============================================================================

@dataclass
class DronePowerSample:
    """Single power sample from INA219."""
    timestamp_ns: int
    voltage_v: float
    current_a: float
    power_w: float

@dataclass
class DroneMetrics:
    """Full drone metrics - INCLUDING power."""
    suite_id: str = ""
    
    # Timing
    handshake_start_ns: int = 0
    handshake_end_ns: int = 0
    handshake_duration_ms: float = 0.0
    traffic_start_ns: int = 0
    traffic_end_ns: int = 0
    traffic_duration_s: float = 0.0
    
    # System
    cpu_samples: List[float] = field(default_factory=list)
    cpu_avg_percent: float = 0.0
    cpu_peak_percent: float = 0.0
    memory_rss_mb: float = 0.0
    temperature_c: float = 0.0
    load_avg_1m: float = 0.0
    load_avg_5m: float = 0.0
    load_avg_15m: float = 0.0
    
    # Power (drone-only)
    power_samples: List[DronePowerSample] = field(default_factory=list)
    power_avg_w: float = 0.0
    power_peak_w: float = 0.0
    power_min_w: float = 0.0
    voltage_avg_v: float = 0.0
    current_avg_a: float = 0.0
    energy_total_j: float = 0.0
    energy_per_handshake_j: float = 0.0
    
    # Network
    packets_sent: int = 0
    packets_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "handshake_duration_ms": self.handshake_duration_ms,
            "traffic_duration_s": self.traffic_duration_s,
            "cpu_avg_percent": self.cpu_avg_percent,
            "cpu_peak_percent": self.cpu_peak_percent,
            "memory_rss_mb": self.memory_rss_mb,
            "temperature_c": self.temperature_c,
            "load_avg_1m": self.load_avg_1m,
            "load_avg_5m": self.load_avg_5m,
            "load_avg_15m": self.load_avg_15m,
            "power_avg_w": self.power_avg_w,
            "power_peak_w": self.power_peak_w,
            "power_min_w": self.power_min_w,
            "voltage_avg_v": self.voltage_avg_v,
            "current_avg_a": self.current_avg_a,
            "energy_total_j": self.energy_total_j,
            "energy_per_handshake_j": self.energy_per_handshake_j,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
        }


class DroneMetricsCollector:
    """Collects full metrics on drone side - INCLUDING POWER."""
    
    def __init__(self):
        self._current: Optional[DroneMetrics] = None
        self._sampling = False
        self._sample_thread: Optional[threading.Thread] = None
        self._power_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Try to import psutil
        try:
            import psutil
            self._psutil = psutil
        except ImportError:
            self._psutil = None
            log("[WARN] psutil not available - CPU/memory metrics disabled")
        
        # Try to initialize the validated power-monitor backend.
        self._power_monitor = None
        self._power_available = False
        try:
            self._power_monitor = create_power_monitor(
                LOGS_DIR / "power_samples",
                sample_hz=1000,
            )
            self._power_available = True
            log(
                f"[POWER] Power monitor initialized at "
                f"{getattr(self._power_monitor, 'sample_hz', 0)} Hz"
            )
        except PowerMonitorUnavailable as e:
            log(f"[WARN] Power monitor not available: {e}")
        except Exception as e:
            log(f"[WARN] Power monitor init failed: {e}")
    
    def start_suite(self, suite_id: str):
        """Start collecting metrics for a suite."""
        self._current = DroneMetrics(suite_id=suite_id)
        self._stop_event.clear()
        self._sampling = True
        
        # Start CPU sampling thread
        if self._psutil:
            self._sample_thread = threading.Thread(target=self._sample_cpu_loop, daemon=True)
            self._sample_thread.start()
        
        # Start power sampling thread
        if self._power_available:
            self._power_thread = threading.Thread(target=self._sample_power_loop, daemon=True)
            self._power_thread.start()
    
    def _sample_cpu_loop(self):
        """Background CPU sampling."""
        while self._sampling and not self._stop_event.is_set():
            if self._current and self._psutil:
                cpu = self._psutil.cpu_percent(interval=0.5)
                self._current.cpu_samples.append(cpu)
    
    def _sample_power_loop(self):
        """Background power sampling via the validated core power monitor."""
        monitor = self._power_monitor
        if monitor is None:
            return
        try:
            for sample in monitor.iter_samples():
                if not self._sampling or self._stop_event.is_set():
                    break
                if self._current is None:
                    continue
                self._current.power_samples.append(
                    DronePowerSample(
                        timestamp_ns=sample.timestamp_ns,
                        voltage_v=sample.voltage_v,
                        current_a=sample.current_a,
                        power_w=sample.power_w,
                    )
                )
        except Exception as exc:
            log(f"[WARN] Power sampling stopped: {exc}")
    
    def record_handshake_start(self):
        if self._current:
            self._current.handshake_start_ns = time.time_ns()
    
    def record_handshake_end(self, success: bool):
        if self._current:
            self._current.handshake_end_ns = time.time_ns()
            self._current.handshake_duration_ms = (
                self._current.handshake_end_ns - self._current.handshake_start_ns
            ) / 1_000_000
    
    def record_traffic_start(self):
        if self._current:
            self._current.traffic_start_ns = time.time_ns()
    
    def record_traffic_end(self):
        if self._current:
            self._current.traffic_end_ns = time.time_ns()
            self._current.traffic_duration_s = (
                self._current.traffic_end_ns - self._current.traffic_start_ns
            ) / 1e9
    
    def update_network_stats(self, packets_sent: int, packets_received: int,
                             bytes_sent: int, bytes_received: int):
        if self._current:
            self._current.packets_sent = packets_sent
            self._current.packets_received = packets_received
            self._current.bytes_sent = bytes_sent
            self._current.bytes_received = bytes_received
    
    def finalize(self) -> Optional[Dict[str, Any]]:
        """Stop sampling and compute final metrics."""
        self._sampling = False
        self._stop_event.set()
        
        if self._sample_thread:
            self._sample_thread.join(timeout=2.0)
            self._sample_thread = None
        
        if self._power_thread:
            self._power_thread.join(timeout=2.0)
            self._power_thread = None
        
        if not self._current:
            return None
        
        # Compute CPU stats
        if self._current.cpu_samples:
            self._current.cpu_avg_percent = statistics.mean(self._current.cpu_samples)
            self._current.cpu_peak_percent = max(self._current.cpu_samples)
        
        # Get memory
        if self._psutil:
            proc = self._psutil.Process()
            mem = proc.memory_info()
            self._current.memory_rss_mb = mem.rss / (1024 * 1024)
        
        # Get temperature (RPi specific)
        try:
            thermal_path = "/sys/class/thermal/thermal_zone0/temp"
            if os.path.exists(thermal_path):
                with open(thermal_path) as f:
                    self._current.temperature_c = int(f.read().strip()) / 1000.0
        except Exception:
            pass
        
        # Get load average (Linux specific)
        try:
            load = os.getloadavg()
            self._current.load_avg_1m = load[0]
            self._current.load_avg_5m = load[1]
            self._current.load_avg_15m = load[2]
        except (OSError, AttributeError):
            pass
        
        # Compute power stats
        if self._current.power_samples:
            powers = [s.power_w for s in self._current.power_samples]
            voltages = [s.voltage_v for s in self._current.power_samples]
            currents = [s.current_a for s in self._current.power_samples]
            
            self._current.power_avg_w = statistics.mean(powers)
            self._current.power_peak_w = max(powers)
            self._current.power_min_w = min(powers)
            self._current.voltage_avg_v = statistics.mean(voltages)
            self._current.current_avg_a = statistics.mean(currents)
            
            # Total energy = average power × duration
            if self._current.traffic_duration_s > 0:
                self._current.energy_total_j = (
                    self._current.power_avg_w * self._current.traffic_duration_s
                )
            
            # Energy per handshake
            if self._current.handshake_duration_ms > 0:
                handshake_s = self._current.handshake_duration_ms / 1000.0
                self._current.energy_per_handshake_j = (
                    self._current.power_avg_w * handshake_s
                )
        
        return self._current.to_dict()

# =============================================================================
# UDP Echo Server (for traffic measurement)
# =============================================================================

class UdpEchoServer:
    """Echoes UDP packets back through the tunnel."""
    
    def __init__(self, bind_host: str, rx_port: int, tx_port: int):
        self.bind_host = bind_host
        self.rx_port = rx_port
        self.tx_port = tx_port
        self.rx_sock: Optional[socket.socket] = None
        self.tx_sock: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.stats = {"rx_count": 0, "tx_count": 0, "rx_bytes": 0, "tx_bytes": 0}
        self.lock = threading.Lock()
    
    def start(self):
        if self.running:
            return
        
        self.rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        self.rx_sock.bind((self.bind_host, self.rx_port))
        self.rx_sock.settimeout(1.0)
        
        self.tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.tx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        log(f"Echo server listening on {self.bind_host}:{self.rx_port}")
    
    def _loop(self):
        while self.running:
            try:
                data, addr = self.rx_sock.recvfrom(65535)
                with self.lock:
                    self.stats["rx_count"] += 1
                    self.stats["rx_bytes"] += len(data)
                
                # Echo back
                self.tx_sock.sendto(data, (self.bind_host, self.tx_port))
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
        log("Echo server stopped")

# =============================================================================
# GCS Control Client
# =============================================================================

def send_gcs_command(cmd: str, gcs_host: Optional[str] = None, **params) -> dict:
    """Send command to GCS benchmark server over LAN."""
    try:
        target_host = gcs_host or GCS_LAN_IP
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
# Drone Proxy Manager
# =============================================================================

class DroneProxyManager:
    """Manages drone crypto proxy subprocess."""
    
    def __init__(self, logs_dir: Path, key_root: Path, *, gcs_host: str, drone_host: str):
        self.logs_dir = logs_dir
        self.key_root = key_root
        self.gcs_host = gcs_host
        self.drone_host = drone_host
        self.managed_proc: Optional[ManagedProcess] = None
        self.current_suite: Optional[str] = None
        self.current_aead: Optional[str] = None
        self._log_handle = None
    
    def start(self, suite_name: str, *, aead_token: Optional[str] = None) -> bool:
        """Start proxy with given suite."""
        if self.managed_proc and self.managed_proc.is_running():
            self.stop()
        
        suite = get_suite(suite_name)
        if not suite:
            log_err(f"Unknown suite: {suite_name}")
            return False
        
        resolved_aead = normalize_aead_token(aead_token) if aead_token else str(suite.get("aead_token", "aesgcm"))
        secret_dir = self.key_root / suite_name
        peer_pubkey = secret_dir / "gcs_signing.pub"
        
        if not peer_pubkey.exists():
            log_err(f"Missing key: {peer_pubkey}")
            return False
        
        cmd = [
            sys.executable, "-m", "core.run_proxy", "drone",
            "--suite", suite_name,
            "--peer-pubkey-file", str(peer_pubkey),
            "--aead", resolved_aead,
            "--quiet",
            "--status-file", str(self.logs_dir / "drone_status.json")
        ]
        
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        log_path = self.logs_dir / f"drone_proxy_{suite_name}_{resolved_aead}_{timestamp}.log"
        self._log_handle = open(log_path, "w", encoding="utf-8")
        
        self.managed_proc = ManagedProcess(
            cmd=cmd,
            name=f"drone-proxy-{suite_name}",
            env=_benchmark_proxy_env(gcs_host=self.gcs_host, drone_host=self.drone_host),
            stdout=self._log_handle,
            stderr=subprocess.STDOUT
        )
        
        if self.managed_proc.start():
            self.current_suite = suite_name
            self.current_aead = resolved_aead
            time.sleep(2.0)
            if not self.managed_proc.is_running():
                log_err(f"Proxy exited early for {suite_name}")
                return False
            log(f"Drone proxy started for {suite_name} (aead={resolved_aead})")
            return True
        return False
    
    def stop(self):
        """Stop proxy."""
        if self.managed_proc:
            self.managed_proc.stop()
            self.managed_proc = None
            self.current_suite = None
            self.current_aead = None
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None
    
    def is_running(self) -> bool:
        return self.managed_proc is not None and self.managed_proc.is_running()

# =============================================================================
# Consolidated Benchmark Result
# =============================================================================

@dataclass
class ConsolidatedResult:
    """Combined metrics from GCS and Drone."""
    suite_id: str
    success: bool
    error_message: str = ""
    retry_count: int = 0
    
    # Suite info
    kem_algorithm: str = ""
    sig_algorithm: str = ""
    aead_algorithm: str = ""
    nist_level: str = ""
    
    # Timing
    handshake_duration_ms: float = 0.0
    traffic_duration_s: float = 0.0
    
    # GCS metrics (minimal)
    gcs_cpu_avg_percent: float = 0.0
    gcs_cpu_peak_percent: float = 0.0
    gcs_memory_rss_mb: float = 0.0
    gcs_rtt_mean_ms: float = 0.0
    gcs_rtt_p95_ms: float = 0.0
    gcs_rtt_max_ms: float = 0.0
    
    # Drone metrics (full)
    drone_cpu_avg_percent: float = 0.0
    drone_cpu_peak_percent: float = 0.0
    drone_memory_rss_mb: float = 0.0
    drone_temperature_c: float = 0.0
    drone_load_avg_1m: float = 0.0
    
    # Drone power (exclusive)
    drone_power_avg_w: float = 0.0
    drone_power_peak_w: float = 0.0
    drone_energy_total_j: float = 0.0
    drone_energy_per_handshake_j: float = 0.0
    
    # Network
    packets_sent: int = 0
    packets_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

# =============================================================================
# Drone Benchmark Controller
# =============================================================================

class DroneBenchmarkController:
    """Controls the benchmark - iterates through all suites."""
    
    def __init__(self, logs_dir: Path, run_id: str, suites: List[Dict[str, Any]], key_root: Path):
        self.logs_dir = logs_dir
        self.run_id = run_id
        self.suites = suites
        
        self.proxy = DroneProxyManager(logs_dir, key_root, gcs_host=GCS_LAN_IP, drone_host=DRONE_LAN_IP)
        self.metrics = DroneMetricsCollector()
        self.echo_server = UdpEchoServer("127.0.0.1", DRONE_PLAIN_RX, DRONE_PLAIN_TX)
        
        self.results: List[ConsolidatedResult] = []
    
    def wait_for_gcs(self, timeout: float = 60.0) -> bool:
        """Wait for GCS benchmark server to be ready."""
        log(f"Connecting to GCS at {GCS_LAN_IP}:{GCS_CONTROL_PORT}...")
        start = time.time()
        while time.time() - start < timeout:
            result = send_gcs_command("ping")
            if result.get("status") == "ok":
                log(f"GCS ready: {result.get('lan_ip')}")
                return True
            time.sleep(1.0)
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
                        if data.get("status") in {"handshake_ok", "running"}:
                            return True
                except Exception:
                    pass
            time.sleep(0.1)
        return False
    
    def benchmark_suite(self, suite: Dict[str, Any]) -> ConsolidatedResult:
        """Benchmark a single suite."""
        suite_name = suite["name"]
        result = ConsolidatedResult(suite_id=suite_name, success=False)
        
        # Fill crypto identity
        result.kem_algorithm = suite.get("kem_name", "")
        result.sig_algorithm = suite.get("sig_name", "")
        result.aead_algorithm = suite.get("aead_token", "")
        result.nist_level = suite.get("nist_level", "")
        
        try:
            log(f"[{suite_name}] Starting benchmark...")
            
            # Reset echo server stats
            self.echo_server.reset_stats()
            
            # Remove old status file
            status_file = self.logs_dir / "drone_status.json"
            if status_file.exists():
                status_file.unlink()
            
            # Start metrics collection
            self.metrics.start_suite(suite_name)
            self.metrics.record_handshake_start()
            
            # Tell GCS to start proxy (over LAN!)
            log(f"[{suite_name}] Telling GCS to start proxy...")
            gcs_resp = send_gcs_command("start_suite", suite=suite_name, aead=result.aead_algorithm)
            if gcs_resp.get("status") != "ok":
                result.error_message = f"GCS start failed: {gcs_resp.get('message')}"
                log_err(f"[{suite_name}] {result.error_message}")
                self.metrics.record_handshake_end(success=False)
                self.metrics.finalize()
                return result
            
            # Start drone proxy
            log(f"[{suite_name}] Starting drone proxy...")
            if not self.proxy.start(suite_name, aead_token=result.aead_algorithm):
                result.error_message = "Drone proxy start failed"
                log_err(f"[{suite_name}] {result.error_message}")
                self.metrics.record_handshake_end(success=False)
                self.metrics.finalize()
                send_gcs_command("stop_suite")
                return result
            
            # Wait for handshake
            log(f"[{suite_name}] Waiting for handshake...")
            if not self.wait_for_handshake():
                result.error_message = "Handshake timeout"
                log_err(f"[{suite_name}] {result.error_message}")
                self.metrics.record_handshake_end(success=False)
                self.metrics.finalize()
                self.proxy.stop()
                send_gcs_command("stop_suite")
                return result
            
            self.metrics.record_handshake_end(success=True)
            handshake_ms = self.metrics._current.handshake_duration_ms if self.metrics._current else 0
            log(f"[{suite_name}] Handshake complete in {handshake_ms:.1f}ms")
            
            # Run traffic
            log(f"[{suite_name}] Running traffic for {TRAFFIC_DURATION}s...")
            self.metrics.record_traffic_start()
            traffic_resp = send_gcs_command("run_traffic", duration_s=TRAFFIC_DURATION)
            self.metrics.record_traffic_end()
            if traffic_resp.get("status") != "ok":
                result.error_message = f"Traffic run failed: {traffic_resp.get('message')}"
                log_err(f"[{suite_name}] {result.error_message}")
                self.metrics.finalize()
                self.proxy.stop()
                send_gcs_command("stop_suite")
                return result
            
            # Get echo stats
            echo_stats = self.echo_server.get_stats()
            self.metrics.update_network_stats(
                packets_sent=echo_stats["tx_count"],
                packets_received=echo_stats["rx_count"],
                bytes_sent=echo_stats["tx_bytes"],
                bytes_received=echo_stats["rx_bytes"],
            )
            
            log(f"[{suite_name}] Traffic complete. RX: {echo_stats['rx_count']} pkts")
            
            # Stop GCS and get metrics
            log(f"[{suite_name}] Stopping suite...")
            gcs_resp = send_gcs_command("stop_suite")
            gcs_metrics = gcs_resp.get("gcs_metrics", {})
            
            # Finalize drone metrics
            drone_metrics = self.metrics.finalize()
            
            # Stop drone proxy
            self.proxy.stop()
            
            # Consolidate results
            result.success = True
            result.handshake_duration_ms = drone_metrics.get("handshake_duration_ms", 0)
            result.traffic_duration_s = drone_metrics.get("traffic_duration_s", 0)
            
            # GCS metrics (minimal)
            result.gcs_cpu_avg_percent = gcs_metrics.get("cpu_avg_percent", 0)
            result.gcs_cpu_peak_percent = gcs_metrics.get("cpu_peak_percent", 0)
            result.gcs_memory_rss_mb = gcs_metrics.get("memory_rss_mb", 0)
            result.gcs_rtt_mean_ms = gcs_metrics.get("rtt_mean_ms", 0)
            result.gcs_rtt_p95_ms = gcs_metrics.get("rtt_p95_ms", 0)
            result.gcs_rtt_max_ms = gcs_metrics.get("rtt_max_ms", 0)
            
            # Drone metrics (full)
            result.drone_cpu_avg_percent = drone_metrics.get("cpu_avg_percent", 0)
            result.drone_cpu_peak_percent = drone_metrics.get("cpu_peak_percent", 0)
            result.drone_memory_rss_mb = drone_metrics.get("memory_rss_mb", 0)
            result.drone_temperature_c = drone_metrics.get("temperature_c", 0)
            result.drone_load_avg_1m = drone_metrics.get("load_avg_1m", 0)
            
            # Drone power
            result.drone_power_avg_w = drone_metrics.get("power_avg_w", 0)
            result.drone_power_peak_w = drone_metrics.get("power_peak_w", 0)
            result.drone_energy_total_j = drone_metrics.get("energy_total_j", 0)
            result.drone_energy_per_handshake_j = drone_metrics.get("energy_per_handshake_j", 0)
            
            # Network
            result.packets_sent = drone_metrics.get("packets_sent", 0)
            result.packets_received = drone_metrics.get("packets_received", 0)
            result.bytes_sent = drone_metrics.get("bytes_sent", 0)
            result.bytes_received = drone_metrics.get("bytes_received", 0)
            
            log(f"[{suite_name}] Benchmark complete!")
            
        except Exception as e:
            result.error_message = str(e)
            log_err(f"[{suite_name}] Exception: {e}")
            try:
                self.proxy.stop()
                send_gcs_command("stop_suite")
            except Exception:
                pass
        
        return result
    
    def run_all_benchmarks(self) -> List[ConsolidatedResult]:
        """Run benchmarks for all suites."""
        log(f"Starting benchmark run: {len(self.suites)} suites")
        log(f"Run ID: {self.run_id}")
        log(f"Traffic duration: {TRAFFIC_DURATION}s per suite")
        log(f"GCS: {GCS_LAN_IP}:{GCS_CONTROL_PORT}")
        log(f"Drone: {DRONE_LAN_IP}")
        
        # Start echo server
        self.echo_server.start()
        
        # Wait for GCS
        if not self.wait_for_gcs():
            log_err("GCS benchmark server not responding!")
            log_err(f"Make sure it's running: python -m bench.lan_benchmark_gcs")
            return []
        
        total = len(self.suites)
        
        for idx, suite in enumerate(self.suites, 1):
            suite_name = suite["name"]
            aead_token = suite.get("aead_token", "")
            log(f"\n{'='*60}")
            log(f"Suite {idx}/{total}: {suite_name} [{aead_token}]")
            log(f"{'='*60}")
            
            # Try with retries
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
            if idx < total:
                time.sleep(INTER_SUITE_DELAY)
        
        # Cleanup
        self.echo_server.stop()
        
        # Tell GCS to shutdown
        send_gcs_command("shutdown")
        
        return self.results
    
    def save_results(self) -> Path:
        """Save benchmark results to JSON."""
        summary = {
            "run_id": self.run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "gcs_lan_ip": GCS_LAN_IP,
            "drone_lan_ip": DRONE_LAN_IP,
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
    global GCS_LAN_IP
    
    parser = argparse.ArgumentParser(description="Drone LAN Benchmark Controller")
    parser.add_argument("--run-id", default=None, help="Run ID (default: timestamp)")
    parser.add_argument("--max-suites", type=int, default=None,
                        help="Maximum suites to benchmark (for testing)")
    parser.add_argument("--suite", default=None, help="Single suite to benchmark")
    parser.add_argument("--gcs-host", default=GCS_LAN_IP,
                        help=f"GCS LAN IP (default: {GCS_LAN_IP})")
    parser.add_argument("--key-root", default=str(ROOT / "tmp_bench_keys"),
                        help="Key root containing benchmark public keys (default: tmp_bench_keys)")
    parser.add_argument("--aead", action="append", default=[],
                        help="AEAD token to include (repeatable)")
    parser.add_argument("--exclude-aead", action="append", default=[],
                        help="AEAD token to exclude (repeatable)")
    args = parser.parse_args()
    
    # Override GCS host if specified
    if args.gcs_host:
        GCS_LAN_IP = args.gcs_host
    
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    # Create logs directory
    logs_dir = LOGS_DIR / run_id
    logs_dir.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("DRONE LAN BENCHMARK CONTROLLER")
    print("=" * 70)
    print(f"Run ID: {run_id}")
    print(f"Logs: {logs_dir}")
    print(f"GCS LAN IP: {GCS_LAN_IP}")
    print(f"Drone LAN IP: {DRONE_LAN_IP}")
    print()
    print("NETWORK CONFIGURATION:")
    print("  - All benchmark traffic uses LAN IPs")
    print("  - Tailscale (100.x.x.x) is for SSH ONLY")
    print()
    print("METRICS COLLECTED:")
    print("  GCS (minimal):  CPU, Memory")
    print("  Drone (full):   CPU, Memory, Temperature, Load, POWER")
    print()
    
    key_root = Path(args.key_root).expanduser().resolve()
    # Get available suites
    suites = get_available_suites(key_root, args.aead, args.exclude_aead)
    log(f"Found {len(suites)} suites with keys")
    
    # Filter if requested
    if args.suite:
        suites = [s for s in suites if s["name"] == args.suite]
        if not suites:
            log_err(f"Suite not found: {args.suite}")
            return 1
    
    # Limit if requested
    if args.max_suites:
        suites = suites[:args.max_suites]
        log(f"Limited to first {args.max_suites} suites for testing")
    
    controller = DroneBenchmarkController(logs_dir, run_id, suites, key_root)
    
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
    print("\n" + "=" * 70)
    print("BENCHMARK SUMMARY")
    print("=" * 70)
    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    print(f"Total suites: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    
    if successful > 0:
        avg_handshake = statistics.mean([r.handshake_duration_ms for r in results if r.success])
        print(f"\nAverage handshake: {avg_handshake:.1f}ms")
        power_values = [r.drone_power_avg_w for r in results if r.success and r.drone_power_avg_w > 0]
        if power_values:
            avg_power = statistics.mean(power_values)
            print(f"Average power: {avg_power:.2f}W")
    
    print(f"\nResults: {output_file}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
