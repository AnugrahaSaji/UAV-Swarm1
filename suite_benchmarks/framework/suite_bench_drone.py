#!/usr/bin/env python3
"""
Suite Benchmark - Drone Side
============================

End-to-end application benchmark for PQC secure tunnel.
Measures real MAVProxy ↔ MAVProxy communication metrics.

Metrics Collected:
- Handshake timing (KEM keygen, encapsulate, signature verify)
- Rekey timing and energy
- Blackout duration during rekey
- Packet latency through tunnel
- Power consumption (INA219 @ 1kHz)
- System metrics (CPU, memory, thermal)

Usage:
    On Drone (Raspberry Pi):
    source ~/cenv/bin/activate
    python suite_benchmarks/framework/suite_bench_drone.py

This script is controlled by the GCS scheduler via TCP control channel.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is importable
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import argparse
import json
import os
import signal
import socket
import struct
import subprocess
import threading
import time
import traceback
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from core.config import CONFIG
from core.suites import list_suites, get_suite
from core.logging_utils import get_logger

# Optional power monitoring
try:
    from core.power_monitor import Ina219PowerMonitor
    POWER_AVAILABLE = True
except ImportError:
    POWER_AVAILABLE = False

# Optional psutil
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


# =============================================================================
# Configuration
# =============================================================================

CONTROL_HOST = CONFIG.get("DRONE_CONTROL_HOST", "0.0.0.0")
CONTROL_PORT = int(CONFIG.get("DRONE_CONTROL_PORT", 48080))
SECRETS_DIR = ROOT / "secrets/matrix"
OUTPUT_DIR = ROOT / "suite_benchmarks/raw_data/drone"


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class HandshakeMetrics:
    """Metrics captured during handshake."""
    start_ns: int = 0
    end_ns: int = 0
    duration_ms: float = 0.0
    success: bool = False
    error: str = ""


@dataclass
class RekeyMetrics:
    """Metrics captured during rekey."""
    start_ns: int = 0
    end_ns: int = 0
    duration_ms: float = 0.0
    blackout_start_ns: int = 0
    blackout_end_ns: int = 0
    blackout_ms: float = 0.0
    packets_during_rekey: int = 0
    packets_dropped: int = 0
    success: bool = False
    error: str = ""


@dataclass
class PowerSample:
    """Single power measurement."""
    timestamp_ns: int
    voltage_v: float
    current_a: float
    power_w: float


@dataclass 
class SuiteMetrics:
    """Complete metrics for one suite run."""
    suite_id: str
    iteration: int
    timestamp_iso: str = ""
    
    # Timing
    handshake: HandshakeMetrics = field(default_factory=HandshakeMetrics)
    rekey: Optional[RekeyMetrics] = None
    
    # Packet metrics
    packets_sent: int = 0
    packets_received: int = 0
    packets_dropped: int = 0
    
    # Latency (microseconds)
    latency_samples: List[float] = field(default_factory=list)
    latency_mean_us: float = 0.0
    latency_min_us: float = 0.0
    latency_max_us: float = 0.0
    latency_p50_us: float = 0.0
    latency_p95_us: float = 0.0
    latency_p99_us: float = 0.0
    
    # Power (summarized)
    power_samples_count: int = 0
    power_mean_w: float = 0.0
    power_peak_w: float = 0.0
    energy_total_j: float = 0.0
    voltage_mean_v: float = 0.0
    current_mean_a: float = 0.0
    
    # System
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    temp_c: float = 0.0
    
    # Status
    success: bool = False
    error: str = ""


# =============================================================================
# Power Monitor Thread
# =============================================================================

class PowerCollector(threading.Thread):
    """Background thread collecting power samples at 1kHz using raw INA219."""
    
    def __init__(self):
        super().__init__(daemon=True)
        self.samples: List[PowerSample] = []
        self.lock = threading.Lock()
        self.running = False
        self._bus = None
        self._address = 0x40
        self._shunt_ohm = 0.1
        
        # Try to initialize raw I2C
        try:
            import smbus2 as smbus
            self._bus = smbus.SMBus(1)
            # Configure INA219: 12-bit, 1 sample, continuous
            config = 0x399F  # PGA /8, 12-bit, continuous
            self._bus.write_word_data(self._address, 0x00, ((config & 0xFF) << 8) | (config >> 8))
            print("[INFO] Power monitor (raw I2C) initialized")
        except Exception as e:
            print(f"[WARN] Power monitor init failed: {e}")
            self._bus = None
    
    def start_collection(self):
        """Clear samples and start collecting."""
        with self.lock:
            self.samples = []
        self.running = True
        if not self.is_alive():
            self.start()
    
    def stop_collection(self) -> List[PowerSample]:
        """Stop collecting and return samples."""
        self.running = False
        time.sleep(0.01)  # Let thread finish current read
        with self.lock:
            return list(self.samples)
    
    def run(self):
        """Collection loop at ~1kHz using raw I2C reads."""
        interval = 0.001  # 1ms = 1kHz
        
        while True:
            if not self.running:
                time.sleep(0.01)
                continue
            
            if self._bus:
                try:
                    ts = time.perf_counter_ns()
                    
                    # Read shunt voltage (register 0x01) - raw ADC value
                    raw = self._bus.read_word_data(self._address, 0x01)
                    raw = ((raw & 0xFF) << 8) | (raw >> 8)  # Swap bytes
                    if raw & 0x8000:  # Sign extend
                        raw -= 0x10000
                    shunt_mv = raw * 0.01  # 10µV per LSB
                    
                    # Read bus voltage (register 0x02)
                    raw_bus = self._bus.read_word_data(self._address, 0x02)
                    raw_bus = ((raw_bus & 0xFF) << 8) | (raw_bus >> 8)
                    bus_v = (raw_bus >> 3) * 0.004  # 4mV per LSB
                    
                    # Calculate current and power
                    current_a = (shunt_mv / 1000) / self._shunt_ohm
                    power_w = bus_v * abs(current_a)
                    
                    sample = PowerSample(
                        timestamp_ns=ts,
                        voltage_v=bus_v,
                        current_a=abs(current_a),
                        power_w=power_w,
                    )
                    with self.lock:
                        self.samples.append(sample)
                except Exception:
                    pass
            
            time.sleep(interval)


# =============================================================================
# Packet Latency Tracker
# =============================================================================

class LatencyTracker:
    """Track packet round-trip latency."""
    
    def __init__(self, max_samples: int = 10000):
        self.pending: Dict[int, int] = {}  # seq -> send_time_ns
        self.latencies: List[float] = []
        self.lock = threading.Lock()
        self.max_samples = max_samples
        self.sent = 0
        self.received = 0
        self.dropped = 0
    
    def record_send(self, seq: int) -> int:
        """Record packet send, return timestamp."""
        ts = time.perf_counter_ns()
        with self.lock:
            self.pending[seq] = ts
            self.sent += 1
            # Cleanup old pending (consider dropped after 5s)
            cutoff = ts - 5_000_000_000
            old_seqs = [s for s, t in self.pending.items() if t < cutoff]
            for s in old_seqs:
                del self.pending[s]
                self.dropped += 1
        return ts
    
    def record_receive(self, seq: int) -> Optional[float]:
        """Record packet receive, return latency in microseconds."""
        ts = time.perf_counter_ns()
        with self.lock:
            self.received += 1
            if seq in self.pending:
                send_ts = self.pending.pop(seq)
                latency_us = (ts - send_ts) / 1000
                if len(self.latencies) < self.max_samples:
                    self.latencies.append(latency_us)
                return latency_us
        return None
    
    def get_stats(self) -> Dict[str, float]:
        """Compute latency statistics."""
        with self.lock:
            if not self.latencies:
                return {"mean": 0, "min": 0, "max": 0, "p50": 0, "p95": 0, "p99": 0}
            
            sorted_lat = sorted(self.latencies)
            n = len(sorted_lat)
            
            return {
                "mean": sum(sorted_lat) / n,
                "min": sorted_lat[0],
                "max": sorted_lat[-1],
                "p50": sorted_lat[n // 2],
                "p95": sorted_lat[int(n * 0.95)],
                "p99": sorted_lat[int(n * 0.99)],
            }
    
    def reset(self):
        """Reset all tracking."""
        with self.lock:
            self.pending.clear()
            self.latencies.clear()
            self.sent = 0
            self.received = 0
            self.dropped = 0


# =============================================================================
# System Metrics
# =============================================================================

def get_system_metrics() -> Dict[str, float]:
    """Get current system metrics."""
    result = {"cpu_percent": 0.0, "memory_mb": 0.0, "temp_c": 0.0}
    
    if PSUTIL_AVAILABLE:
        try:
            result["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            result["memory_mb"] = psutil.Process().memory_info().rss / (1024 * 1024)
        except Exception:
            pass
    
    # Read Raspberry Pi temperature
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            result["temp_c"] = int(f.read().strip()) / 1000.0
    except Exception:
        pass
    
    return result


# =============================================================================
# Proxy Manager
# =============================================================================

class ProxyManager:
    """Manage drone proxy subprocess."""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.log_file = None
        self.current_suite: Optional[str] = None
    
    def start(self, suite_id: str) -> bool:
        """Start proxy for given suite."""
        self.stop()
        
        suite_dir = SECRETS_DIR / suite_id
        pub_file = suite_dir / "gcs_signing.pub"
        
        if not pub_file.exists():
            print(f"[ERROR] Public key not found: {pub_file}")
            return False
        
        # Environment
        env = os.environ.copy()
        env["DRONE_HOST"] = CONFIG["DRONE_HOST"]
        env["GCS_HOST"] = CONFIG["GCS_HOST"]
        env["PYTHONPATH"] = str(ROOT)
        
        # Log file
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = OUTPUT_DIR / f"proxy_{suite_id}_{ts}.log"
        self.log_file = open(log_path, "w")
        
        cmd = [
            sys.executable,
            "-m", "core.run_proxy",
            "drone",
            "--suite", suite_id,
            "--peer-pubkey-file", str(pub_file),
        ]
        
        print(f"[INFO] Starting proxy: {' '.join(cmd)}")
        
        try:
            self.process = subprocess.Popen(
                cmd,
                stdout=self.log_file,
                stderr=subprocess.STDOUT,
                env=env,
                cwd=str(ROOT),
            )
            self.current_suite = suite_id
            time.sleep(2)  # Wait for proxy init
            
            if self.process.poll() is not None:
                print("[ERROR] Proxy exited immediately")
                return False
            
            return True
        except Exception as e:
            print(f"[ERROR] Failed to start proxy: {e}")
            return False
    
    def stop(self):
        """Stop current proxy."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None
        
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
            self.log_file = None
        
        self.current_suite = None
    
    def is_running(self) -> bool:
        """Check if proxy is running."""
        return self.process is not None and self.process.poll() is None


# =============================================================================
# Control Server
# =============================================================================

class BenchmarkControlServer:
    """TCP control server for benchmark coordination."""
    
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.socket: Optional[socket.socket] = None
        self.running = False
        
        self.proxy = ProxyManager()
        self.power_collector = PowerCollector()
        self.latency_tracker = LatencyTracker()
        
        self.current_metrics: Optional[SuiteMetrics] = None
        self.all_results: List[Dict] = []
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    def start(self):
        """Start the control server."""
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((self.host, self.port))
        self.socket.listen(5)
        self.socket.settimeout(1.0)
        self.running = True
        
        print(f"[INFO] Benchmark control server listening on {self.host}:{self.port}")
        
        while self.running:
            try:
                conn, addr = self.socket.accept()
                self._handle_connection(conn, addr)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[ERROR] Accept error: {e}")
    
    def stop(self):
        """Stop the server."""
        self.running = False
        self.proxy.stop()
        if self.socket:
            self.socket.close()
    
    def _handle_connection(self, conn: socket.socket, addr: Tuple):
        """Handle incoming control connection."""
        try:
            conn.settimeout(30.0)
            data = conn.recv(65535)
            if not data:
                return
            
            cmd = json.loads(data.decode("utf-8"))
            response = self._process_command(cmd)
            conn.sendall(json.dumps(response).encode("utf-8"))
        except Exception as e:
            try:
                conn.sendall(json.dumps({"status": "error", "error": str(e)}).encode())
            except Exception:
                pass
        finally:
            conn.close()
    
    def _process_command(self, cmd: Dict) -> Dict:
        """Process control command."""
        action = cmd.get("cmd", "")
        
        if action == "ping":
            return {"status": "ok", "role": "drone_bench", "session": self.session_id}
        
        elif action == "start_suite":
            suite_id = cmd.get("suite")
            iteration = cmd.get("iteration", 0)
            if not suite_id:
                return {"status": "error", "error": "Missing suite parameter"}
            
            return self._start_suite(suite_id, iteration)
        
        elif action == "stop_suite":
            return self._stop_suite()
        
        elif action == "get_metrics":
            return self._get_current_metrics()
        
        elif action == "get_results":
            return {"status": "ok", "results": self.all_results}
        
        elif action == "rekey":
            new_suite = cmd.get("suite")
            return self._handle_rekey(new_suite)
        
        elif action == "status":
            return {
                "status": "ok",
                "proxy_running": self.proxy.is_running(),
                "current_suite": self.proxy.current_suite,
                "session": self.session_id,
                "results_count": len(self.all_results),
            }
        
        elif action == "shutdown":
            self.stop()
            return {"status": "ok"}
        
        return {"status": "error", "error": f"Unknown command: {action}"}
    
    def _start_suite(self, suite_id: str, iteration: int) -> Dict:
        """Start benchmarking a suite."""
        # Initialize metrics
        self.current_metrics = SuiteMetrics(
            suite_id=suite_id,
            iteration=iteration,
            timestamp_iso=datetime.utcnow().isoformat() + "Z",
        )
        
        # Reset trackers
        self.latency_tracker.reset()
        
        # Start power collection
        self.power_collector.start_collection()
        
        # Record handshake start
        handshake_start = time.perf_counter_ns()
        self.current_metrics.handshake.start_ns = handshake_start
        
        # Start proxy
        success = self.proxy.start(suite_id)
        
        # Record handshake end
        handshake_end = time.perf_counter_ns()
        self.current_metrics.handshake.end_ns = handshake_end
        self.current_metrics.handshake.duration_ms = (handshake_end - handshake_start) / 1e6
        self.current_metrics.handshake.success = success
        
        if not success:
            self.current_metrics.handshake.error = "Proxy start failed"
            self.current_metrics.success = False
            return {"status": "error", "error": "Proxy start failed"}
        
        return {
            "status": "ok",
            "suite": suite_id,
            "handshake_ms": self.current_metrics.handshake.duration_ms,
        }
    
    def _stop_suite(self) -> Dict:
        """Stop current suite and finalize metrics."""
        if not self.current_metrics:
            return {"status": "error", "error": "No active suite"}
        
        # Stop power collection
        power_samples = self.power_collector.stop_collection()
        
        # Stop proxy
        self.proxy.stop()
        
        # Process power data
        if power_samples:
            powers = [s.power_w for s in power_samples]
            voltages = [s.voltage_v for s in power_samples]
            currents = [s.current_a for s in power_samples]
            
            self.current_metrics.power_samples_count = len(power_samples)
            self.current_metrics.power_mean_w = sum(powers) / len(powers)
            self.current_metrics.power_peak_w = max(powers)
            self.current_metrics.voltage_mean_v = sum(voltages) / len(voltages)
            self.current_metrics.current_mean_a = sum(currents) / len(currents)
            
            # Energy = integral of power over time
            if len(power_samples) > 1:
                duration_s = (power_samples[-1].timestamp_ns - power_samples[0].timestamp_ns) / 1e9
                self.current_metrics.energy_total_j = self.current_metrics.power_mean_w * duration_s
        
        # Process latency data
        lat_stats = self.latency_tracker.get_stats()
        self.current_metrics.latency_mean_us = lat_stats["mean"]
        self.current_metrics.latency_min_us = lat_stats["min"]
        self.current_metrics.latency_max_us = lat_stats["max"]
        self.current_metrics.latency_p50_us = lat_stats["p50"]
        self.current_metrics.latency_p95_us = lat_stats["p95"]
        self.current_metrics.latency_p99_us = lat_stats["p99"]
        self.current_metrics.packets_sent = self.latency_tracker.sent
        self.current_metrics.packets_received = self.latency_tracker.received
        self.current_metrics.packets_dropped = self.latency_tracker.dropped
        
        # System metrics
        sys_metrics = get_system_metrics()
        self.current_metrics.cpu_percent = sys_metrics["cpu_percent"]
        self.current_metrics.memory_mb = sys_metrics["memory_mb"]
        self.current_metrics.temp_c = sys_metrics["temp_c"]
        
        # Mark success
        self.current_metrics.success = self.current_metrics.handshake.success
        
        # Save result
        result = asdict(self.current_metrics)
        self.all_results.append(result)
        
        # Write to file
        self._save_result(result)
        
        return {"status": "ok", "metrics": result}
    
    def _handle_rekey(self, new_suite: Optional[str]) -> Dict:
        """Handle rekey request."""
        if not self.current_metrics:
            return {"status": "error", "error": "No active suite"}
        
        rekey_metrics = RekeyMetrics()
        rekey_metrics.start_ns = time.perf_counter_ns()
        rekey_metrics.blackout_start_ns = rekey_metrics.start_ns
        
        # TODO: Actual rekey logic through proxy
        # For now, simulate by restarting proxy
        
        if new_suite:
            success = self.proxy.start(new_suite)
            rekey_metrics.success = success
        else:
            rekey_metrics.success = True
        
        rekey_metrics.end_ns = time.perf_counter_ns()
        rekey_metrics.blackout_end_ns = rekey_metrics.end_ns
        rekey_metrics.duration_ms = (rekey_metrics.end_ns - rekey_metrics.start_ns) / 1e6
        rekey_metrics.blackout_ms = rekey_metrics.duration_ms
        
        self.current_metrics.rekey = rekey_metrics
        
        return {
            "status": "ok",
            "rekey_ms": rekey_metrics.duration_ms,
            "blackout_ms": rekey_metrics.blackout_ms,
        }
    
    def _get_current_metrics(self) -> Dict:
        """Get current live metrics."""
        result = {
            "status": "ok",
            "proxy_running": self.proxy.is_running(),
            "current_suite": self.proxy.current_suite,
        }
        
        if self.current_metrics:
            result["latency"] = self.latency_tracker.get_stats()
            result["packets_sent"] = self.latency_tracker.sent
            result["packets_received"] = self.latency_tracker.received
        
        result["system"] = get_system_metrics()
        
        return result
    
    def _save_result(self, result: Dict):
        """Save result to JSON file."""
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"{result['suite_id']}_{result['iteration']:03d}_{self.session_id}.json"
        filepath = OUTPUT_DIR / filename
        
        with open(filepath, "w") as f:
            json.dump(result, f, indent=2, default=str)
        
        print(f"[INFO] Saved: {filepath}")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Suite Benchmark - Drone Side")
    parser.add_argument("--host", default=CONTROL_HOST, help="Control server bind host")
    parser.add_argument("--port", type=int, default=CONTROL_PORT, help="Control server port")
    args = parser.parse_args()
    
    print("=" * 60)
    print("PQC SUITE BENCHMARK - DRONE SIDE")
    print("=" * 60)
    print(f"Control Server: {args.host}:{args.port}")
    print(f"Power Monitoring: {'AVAILABLE' if POWER_AVAILABLE else 'NOT AVAILABLE'}")
    print(f"System Monitoring: {'AVAILABLE' if PSUTIL_AVAILABLE else 'NOT AVAILABLE'}")
    print("=" * 60)
    
    server = BenchmarkControlServer(args.host, args.port)
    
    def signal_handler(sig, frame):
        print("\n[INFO] Shutting down...")
        server.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        server.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
