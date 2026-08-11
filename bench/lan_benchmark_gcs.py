#!/usr/bin/env python3
"""
GCS-side LAN Benchmark Server

This script runs on the GCS (Windows) machine and:
1. Listens for commands from drone on LAN IP (192.168.0.101)
2. Starts/stops crypto proxies per suite
3. Collects MINIMAL metrics (CPU, memory, network - NO power/temp)
4. Reports metrics back to drone for consolidation

Usage:
    python -m bench.lan_benchmark_gcs [--port 48080]

Network Configuration:
    - GCS LAN IP: 192.168.0.101 (benchmark traffic)
    - Drone LAN IP: 192.168.0.105 (benchmark traffic)
    - Tailscale: SSH/Git only - NOT used for benchmark

Metrics Collected (GCS side - minimal):
    - CPU usage (average, peak)
    - Memory RSS
    - Network bytes sent/received
    - Handshake timing
    - Packet counts

NOT collected on GCS:
    - Power (INA219 is drone-only)
    - Temperature (RPi-specific)
    - Load average (Linux-specific)
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
from core.suites import get_suite, normalize_aead_token
from core.process import ManagedProcess

# =============================================================================
# Network Configuration - LAN IPs for Benchmark
# =============================================================================

# LAN addresses - USED FOR ALL BENCHMARK TRAFFIC
GCS_LAN_IP = CONFIG.get("GCS_HOST_LAN", "192.168.0.101")
DRONE_LAN_IP = CONFIG.get("DRONE_HOST_LAN", "192.168.0.105")
DEFAULT_BENCHMARK_PSK_HEX = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff"

# Control port for GCS benchmark server
CONTROL_PORT = int(CONFIG.get("GCS_CONTROL_PORT", 48080))
GCS_PLAIN_TX = int(CONFIG.get("GCS_PLAINTEXT_TX", 47001))
GCS_PLAIN_RX = int(CONFIG.get("GCS_PLAINTEXT_RX", 47002))
GCS_PLAIN_HOST = str(CONFIG.get("GCS_PLAINTEXT_HOST", "127.0.0.1"))

ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs" / "lan_benchmark"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

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


def ensure_identity(suite_name: str, key_root: Path) -> Path:
    """Ensure a benchmark identity exists for the requested suite."""
    suite_dir = key_root / suite_name
    key_file = suite_dir / "gcs_signing.key"
    pub_file = suite_dir / "gcs_signing.pub"
    if key_file.exists() and pub_file.exists():
        return suite_dir

    suite_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-m",
        "core.run_proxy",
        "init-identity",
        "--suite",
        suite_name,
        "--output-dir",
        str(suite_dir),
    ]
    subprocess.run(
        cmd,
        cwd=ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return suite_dir


def run_udp_loopback(duration_s: float, *, interval_s: float = 0.05, timeout_s: float = 0.5) -> Dict[str, Any]:
    """Inject UDP traffic through the GCS plaintext port and measure echoed RTT."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((GCS_PLAIN_HOST, GCS_PLAIN_RX))
    sock.settimeout(0.2)

    drain_until = time.time() + 0.5
    while time.time() < drain_until:
        try:
            sock.recvfrom(65535)
        except socket.timeout:
            break
        except ConnectionResetError:
            continue

    sent = 0
    received = 0
    bytes_sent = 0
    bytes_received = 0
    timeouts = 0
    resets = 0
    rtts_ms: List[float] = []
    started = time.time()
    next_send = started
    sequence = 0

    while time.time() - started < duration_s:
        now = time.time()
        if now < next_send:
            time.sleep(min(0.01, next_send - now))
            continue

        payload = f"bench-{sequence:06d}".encode("ascii")
        sent += 1
        bytes_sent += len(payload)
        start_ns = time.perf_counter_ns()
        sock.sendto(payload, (GCS_PLAIN_HOST, GCS_PLAIN_TX))

        matched = False
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                data, _addr = sock.recvfrom(65535)
            except socket.timeout:
                continue
            except ConnectionResetError:
                resets += 1
                continue
            if data == payload:
                received += 1
                bytes_received += len(data)
                rtts_ms.append((time.perf_counter_ns() - start_ns) / 1_000_000.0)
                matched = True
                break

        if not matched:
            timeouts += 1

        sequence += 1
        next_send += interval_s

    sock.close()

    result: Dict[str, Any] = {
        "packets_sent": sent,
        "packets_received": received,
        "bytes_sent": bytes_sent,
        "bytes_received": bytes_received,
        "timeouts": timeouts,
        "resets": resets,
        "rtt_mean_ms": 0.0,
        "rtt_p95_ms": 0.0,
        "rtt_max_ms": 0.0,
    }
    if rtts_ms:
        ordered = sorted(rtts_ms)
        p95_index = min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))
        result["rtt_mean_ms"] = round(statistics.mean(rtts_ms), 4)
        result["rtt_p95_ms"] = round(ordered[p95_index], 4)
        result["rtt_max_ms"] = round(max(rtts_ms), 4)
    return result

# =============================================================================
# GCS Metrics Collector (Minimal - no power)
# =============================================================================

@dataclass
class GcsMetrics:
    """Minimal GCS metrics - NO power metrics."""
    suite_id: str = ""
    
    # Timing
    handshake_start_ns: int = 0
    handshake_end_ns: int = 0
    handshake_duration_ms: float = 0.0
    traffic_start_ns: int = 0
    traffic_end_ns: int = 0
    traffic_duration_s: float = 0.0
    
    # System (minimal)
    cpu_samples: List[float] = field(default_factory=list)
    cpu_avg_percent: float = 0.0
    cpu_peak_percent: float = 0.0
    memory_rss_mb: float = 0.0
    
    # Network
    packets_sent: int = 0
    packets_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    rtt_mean_ms: float = 0.0
    rtt_p95_ms: float = 0.0
    rtt_max_ms: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "suite_id": self.suite_id,
            "handshake_duration_ms": self.handshake_duration_ms,
            "traffic_duration_s": self.traffic_duration_s,
            "cpu_avg_percent": self.cpu_avg_percent,
            "cpu_peak_percent": self.cpu_peak_percent,
            "memory_rss_mb": self.memory_rss_mb,
            "packets_sent": self.packets_sent,
            "packets_received": self.packets_received,
            "bytes_sent": self.bytes_sent,
            "bytes_received": self.bytes_received,
            "rtt_mean_ms": self.rtt_mean_ms,
            "rtt_p95_ms": self.rtt_p95_ms,
            "rtt_max_ms": self.rtt_max_ms,
        }


class GcsMetricsCollector:
    """Collects minimal metrics on GCS side."""
    
    def __init__(self):
        self._current: Optional[GcsMetrics] = None
        self._sampling = False
        self._sample_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Try to import psutil
        try:
            import psutil
            self._psutil = psutil
        except ImportError:
            self._psutil = None
            log("[WARN] psutil not available - CPU/memory metrics disabled")
    
    def start_suite(self, suite_id: str):
        """Start collecting metrics for a suite."""
        self._current = GcsMetrics(suite_id=suite_id)
        self._stop_event.clear()
        self._sampling = True
        
        if self._psutil:
            self._sample_thread = threading.Thread(target=self._sample_loop, daemon=True)
            self._sample_thread.start()
    
    def _sample_loop(self):
        """Background CPU sampling."""
        while self._sampling and not self._stop_event.is_set():
            if self._current and self._psutil:
                cpu = self._psutil.cpu_percent(interval=0.5)
                self._current.cpu_samples.append(cpu)
    
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

    def update_network_stats(self, packets_sent: int, packets_received: int, bytes_sent: int, bytes_received: int):
        if self._current:
            self._current.packets_sent = packets_sent
            self._current.packets_received = packets_received
            self._current.bytes_sent = bytes_sent
            self._current.bytes_received = bytes_received

    def update_latency_stats(self, *, rtt_mean_ms: float, rtt_p95_ms: float, rtt_max_ms: float):
        if self._current:
            self._current.rtt_mean_ms = rtt_mean_ms
            self._current.rtt_p95_ms = rtt_p95_ms
            self._current.rtt_max_ms = rtt_max_ms
    
    def finalize(self) -> Optional[Dict[str, Any]]:
        """Stop sampling and compute final metrics."""
        self._sampling = False
        self._stop_event.set()
        
        if self._sample_thread:
            self._sample_thread.join(timeout=2.0)
            self._sample_thread = None
        
        if not self._current:
            return None
        
        # Compute CPU stats
        if self._current.cpu_samples:
            self._current.cpu_avg_percent = statistics.mean(self._current.cpu_samples)
            self._current.cpu_peak_percent = max(self._current.cpu_samples)
        
        # Get memory (current snapshot)
        if self._psutil:
            proc = self._psutil.Process()
            mem = proc.memory_info()
            self._current.memory_rss_mb = mem.rss / (1024 * 1024)
        
        return self._current.to_dict()

# =============================================================================
# Proxy Manager
# =============================================================================

class GcsProxyManager:
    """Manages GCS crypto proxy subprocess."""
    
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
        secret_dir = ensure_identity(suite_name, self.key_root)
        gcs_key = secret_dir / "gcs_signing.key"
        
        cmd = [
            sys.executable, "-m", "core.run_proxy", "gcs",
            "--suite", suite_name,
            "--gcs-secret-file", str(gcs_key),
            "--aead", resolved_aead,
            "--quiet",
            "--status-file", str(self.logs_dir / "gcs_status.json")
        ]
        
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        log_path = self.logs_dir / f"gcs_proxy_{suite_name}_{resolved_aead}_{timestamp}.log"
        self._log_handle = open(log_path, "w", encoding="utf-8")
        
        self.managed_proc = ManagedProcess(
            cmd=cmd,
            name=f"gcs-proxy-{suite_name}",
            env=_benchmark_proxy_env(gcs_host=self.gcs_host, drone_host=self.drone_host),
            stdout=self._log_handle,
            stderr=subprocess.STDOUT
        )
        
        if self.managed_proc.start():
            self.current_suite = suite_name
            self.current_aead = resolved_aead
            time.sleep(2.0)  # Allow proxy to initialize
            if not self.managed_proc.is_running():
                log_err(f"Proxy exited early for {suite_name}")
                return False
            log(f"GCS proxy started for {suite_name} (aead={resolved_aead})")
            return True
        return False
    
    def stop(self):
        """Stop proxy."""
        if self.managed_proc:
            self.managed_proc.stop()
            self.managed_proc = None
            self.current_suite = None
            self.current_aead = None
            log("GCS proxy stopped")
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None
    
    def is_running(self) -> bool:
        return self.managed_proc is not None and self.managed_proc.is_running()

# =============================================================================
# GCS Benchmark Server
# =============================================================================

class GcsBenchmarkServer:
    """
    GCS benchmark server - listens on LAN IP for drone commands.
    
    Commands:
        ping: Check if server is ready
        start_suite: Start proxy + metrics for a suite
        stop_suite: Stop proxy + return metrics
        shutdown: Graceful shutdown
    """
    
    def __init__(
        self,
        logs_dir: Path,
        run_id: str,
        key_root: Path,
        bind_host: str = "0.0.0.0",
        port: int = CONTROL_PORT,
        advertise_host: str = GCS_LAN_IP,
        drone_host: str = DRONE_LAN_IP,
    ):
        self.logs_dir = logs_dir
        self.run_id = run_id
        self.key_root = key_root
        self.bind_host = bind_host
        self.port = port
        self.advertise_host = advertise_host
        self.drone_host = drone_host
        
        self.proxy = GcsProxyManager(logs_dir, key_root, gcs_host=advertise_host, drone_host=drone_host)
        self.metrics = GcsMetricsCollector()
        
        self.server_sock: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
    
    def start(self):
        """Start the benchmark server."""
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.bind_host, self.port))
        self.server_sock.listen(5)
        self.server_sock.settimeout(1.0)
        
        self.running = True
        self.thread = threading.Thread(target=self._server_loop, daemon=True)
        self.thread.start()
        
        log(f"GCS Benchmark Server listening on {self.bind_host}:{self.port}")
        log(f"LAN IP: {self.advertise_host}")
    
    def _server_loop(self):
        while self.running:
            try:
                client, addr = self.server_sock.accept()
                log(f"Connection from {addr}")
                self._handle_client(client)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    log_err(f"Server error: {e}")
    
    def _handle_client(self, client: socket.socket):
        try:
            data = b""
            client.settimeout(30.0)
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
            return {
                "status": "ok",
                "message": "pong",
                "role": "gcs_benchmark",
                "run_id": self.run_id,
                "lan_ip": self.advertise_host,
            }
        
        elif cmd == "start_suite":
            suite = request.get("suite")
            aead_token = request.get("aead")
            if not suite:
                return {"status": "error", "message": "missing suite parameter"}
            
            log(f"Starting suite: {suite} (aead={aead_token or 'default'})")
            
            # Start metrics collection
            self.metrics.start_suite(suite)
            self.metrics.record_handshake_start()
            
            # Start proxy
            if not self.proxy.start(suite, aead_token=aead_token):
                self.metrics.record_handshake_end(success=False)
                return {"status": "error", "message": "proxy_start_failed"}
            
            self.metrics.record_handshake_end(success=True)
            
            return {"status": "ok", "message": "suite_started", "suite": suite}
        
        elif cmd == "run_traffic":
            duration_s = float(request.get("duration_s", 10.0) or 10.0)
            interval_s = float(request.get("interval_s", 0.05) or 0.05)
            self.metrics.record_traffic_start()
            traffic_metrics = run_udp_loopback(duration_s, interval_s=interval_s)
            self.metrics.record_traffic_end()
            self.metrics.update_network_stats(
                packets_sent=int(traffic_metrics.get("packets_sent", 0)),
                packets_received=int(traffic_metrics.get("packets_received", 0)),
                bytes_sent=int(traffic_metrics.get("bytes_sent", 0)),
                bytes_received=int(traffic_metrics.get("bytes_received", 0)),
            )
            self.metrics.update_latency_stats(
                rtt_mean_ms=float(traffic_metrics.get("rtt_mean_ms", 0.0)),
                rtt_p95_ms=float(traffic_metrics.get("rtt_p95_ms", 0.0)),
                rtt_max_ms=float(traffic_metrics.get("rtt_max_ms", 0.0)),
            )
            return {"status": "ok", "message": "traffic_complete", "traffic_metrics": traffic_metrics}
        
        elif cmd == "stop_suite":
            log("Stopping suite")
            # Finalize metrics
            gcs_metrics = self.metrics.finalize()
            
            # Stop proxy
            self.proxy.stop()
            
            return {
                "status": "ok",
                "message": "suite_stopped",
                "gcs_metrics": gcs_metrics or {}
            }
        
        elif cmd == "get_status":
            return {
                "status": "ok",
                "proxy_running": self.proxy.is_running(),
                "current_suite": self.proxy.current_suite,
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
        log("GCS benchmark server stopped")

# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="GCS LAN Benchmark Server")
    parser.add_argument("--port", type=int, default=CONTROL_PORT,
                        help=f"Control port (default: {CONTROL_PORT})")
    parser.add_argument("--run-id", default=None,
                        help="Run ID (default: timestamp)")
    parser.add_argument("--bind", default="0.0.0.0",
                        help="Bind address (default: 0.0.0.0)")
    parser.add_argument("--advertise-host", default=GCS_LAN_IP,
                        help=f"Reachable GCS LAN IP to advertise to drone/proxies (default: {GCS_LAN_IP})")
    parser.add_argument("--drone-host", default=DRONE_LAN_IP,
                        help=f"Drone LAN IP for proxy environment overrides (default: {DRONE_LAN_IP})")
    parser.add_argument("--key-root", default=str(ROOT / "tmp_bench_keys"),
                        help="Key root for benchmark identities (default: tmp_bench_keys)")
    args = parser.parse_args()
    
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    
    # Create logs directory
    logs_dir = LOGS_DIR / run_id
    logs_dir.mkdir(parents=True, exist_ok=True)
    key_root = Path(args.key_root).expanduser().resolve()
    key_root.mkdir(parents=True, exist_ok=True)
    
    print("=" * 70)
    print("GCS LAN BENCHMARK SERVER")
    print("=" * 70)
    print(f"Run ID: {run_id}")
    print(f"Logs: {logs_dir}")
    print(f"LAN IP: {args.advertise_host}")
    print(f"Drone LAN IP: {args.drone_host}")
    print(f"Control Port: {args.port}")
    print()
    print("NETWORK CONFIGURATION:")
    print("  - All benchmark traffic uses LAN IPs")
    print("  - Tailscale (100.x.x.x) is for SSH/Git ONLY")
    print()
    print("METRICS COLLECTED (GCS - minimal):")
    print("  - CPU usage (avg, peak)")
    print("  - Memory RSS")
    print("  - Network bytes")
    print("  - NO power metrics (drone-only)")
    print()
    
    server = GcsBenchmarkServer(
        logs_dir,
        run_id,
        key_root,
        args.bind,
        args.port,
        advertise_host=args.advertise_host,
        drone_host=args.drone_host,
    )
    server.start()
    
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
    return 0

if __name__ == "__main__":
    sys.exit(main())
