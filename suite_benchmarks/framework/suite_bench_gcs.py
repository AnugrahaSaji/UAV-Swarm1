#!/usr/bin/env python3
"""
Suite Benchmark - GCS Side (Scheduler)
======================================

End-to-end application benchmark coordinator for PQC secure tunnel.
Controls drone via TCP, runs GCS proxy, and collects metrics.

Metrics Collected per Suite:
- Handshake timing (full end-to-end)
- Rekey timing, blackout duration
- Round-trip latency through tunnel
- Throughput (packets/sec, bytes/sec)
- Power consumption (from drone side)
- System metrics (both sides)

Usage:
    On GCS (Windows):
    conda activate oqs-dev
    python suite_benchmarks/framework/suite_bench_gcs.py

Configuration:
    Edit LOCAL_* variables below or use CLI arguments.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is importable
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# =============================================================================
# Local Configuration (Edit Here)
# =============================================================================

# Suites to test (None = all available with keys)
LOCAL_SUITES = [
    "cs-mlkem768-aesgcm-mldsa65",      # L3 baseline
    "cs-mlkem512-aesgcm-mldsa44",      # L1 fast
    "cs-mlkem1024-aesgcm-mldsa87",     # L5 secure
    "cs-mlkem768-chacha20poly1305-mldsa65",  # ChaCha variant
    "cs-mlkem768-ascon128-mldsa65",    # Ascon variant (lightweight)
]

# Iterations per suite
LOCAL_ITERATIONS = 10

# Traffic duration per suite (seconds)
LOCAL_DURATION_S = 30.0

# Include rekey test in each suite run
LOCAL_TEST_REKEY = True


import argparse
import json
import os
import signal
import socket
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

# Optional psutil
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


# =============================================================================
# Configuration
# =============================================================================

DRONE_HOST = CONFIG.get("DRONE_HOST_TAILSCALE", "100.101.93.23")  # SSH/control via Tailscale
DRONE_LAN = CONFIG.get("DRONE_HOST_LAN", "192.168.0.101")  # Data plane via LAN
CONTROL_PORT = 48082  # Suite benchmark control port
GCS_HOST = CONFIG["GCS_HOST"]
SECRETS_DIR = ROOT / "secrets/matrix"
OUTPUT_DIR = ROOT / "suite_benchmarks/raw_data/gcs"
LOGS_DIR = ROOT / "suite_benchmarks/logs"


# =============================================================================
# Data Structures
# =============================================================================

@dataclass
class SuiteBenchResult:
    """Complete benchmark result for one suite iteration."""
    suite_id: str
    iteration: int
    timestamp_iso: str
    
    # Handshake
    handshake_total_ms: float = 0.0
    handshake_gcs_ms: float = 0.0
    handshake_drone_ms: float = 0.0
    
    # Rekey (optional)
    rekey_ms: float = 0.0
    rekey_blackout_ms: float = 0.0
    
    # Traffic
    duration_s: float = 0.0
    packets_sent: int = 0
    packets_received: int = 0
    packet_loss_percent: float = 0.0
    throughput_pps: float = 0.0
    throughput_mbps: float = 0.0
    
    # Latency (from drone)
    latency_mean_us: float = 0.0
    latency_p50_us: float = 0.0
    latency_p95_us: float = 0.0
    latency_p99_us: float = 0.0
    
    # Power (from drone)
    power_mean_w: float = 0.0
    power_peak_w: float = 0.0
    energy_total_j: float = 0.0
    
    # System (GCS side)
    gcs_cpu_percent: float = 0.0
    gcs_memory_mb: float = 0.0
    
    # System (Drone side)
    drone_cpu_percent: float = 0.0
    drone_memory_mb: float = 0.0
    drone_temp_c: float = 0.0
    
    # Status
    success: bool = False
    error: str = ""


# =============================================================================
# Drone Control Client
# =============================================================================

class DroneController:
    """Control drone benchmark server."""
    
    def __init__(self, host: str, port: int, timeout: float = 60.0):
        self.host = host
        self.port = port
        self.timeout = timeout
    
    def _send_command(self, cmd: Dict) -> Dict:
        """Send command and get response."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect((self.host, self.port))
            sock.sendall(json.dumps(cmd).encode("utf-8"))
            response = sock.recv(1024 * 1024)  # 1MB max
            return json.loads(response.decode("utf-8"))
        finally:
            sock.close()
    
    def ping(self) -> bool:
        """Check if drone is responding."""
        try:
            resp = self._send_command({"cmd": "ping"})
            return resp.get("status") == "ok"
        except Exception:
            return False
    
    def status(self) -> Dict:
        """Get drone status."""
        return self._send_command({"cmd": "status"})
    
    def start_suite(self, suite_id: str, iteration: int) -> Dict:
        """Start suite on drone."""
        return self._send_command({
            "cmd": "start_suite",
            "suite": suite_id,
            "iteration": iteration,
        })
    
    def stop_suite(self) -> Dict:
        """Stop current suite and get metrics."""
        return self._send_command({"cmd": "stop_suite"})
    
    def get_metrics(self) -> Dict:
        """Get current live metrics."""
        return self._send_command({"cmd": "get_metrics"})
    
    def get_results(self) -> Dict:
        """Get all collected results."""
        return self._send_command({"cmd": "get_results"})
    
    def rekey(self, new_suite: Optional[str] = None) -> Dict:
        """Trigger rekey."""
        return self._send_command({"cmd": "rekey", "suite": new_suite})
    
    def shutdown(self) -> Dict:
        """Shutdown drone benchmark server."""
        return self._send_command({"cmd": "shutdown"})


# =============================================================================
# GCS Proxy Manager
# =============================================================================

class GCSProxyManager:
    """Manage GCS proxy subprocess."""
    
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.log_file = None
        self.current_suite: Optional[str] = None
    
    def start(self, suite_id: str) -> Tuple[bool, float]:
        """Start proxy for given suite. Returns (success, handshake_ms)."""
        self.stop()
        
        suite_dir = SECRETS_DIR / suite_id
        key_file = suite_dir / "gcs_signing.key"
        
        if not key_file.exists():
            print(f"[ERROR] Secret key not found: {key_file}")
            return False, 0.0
        
        # Environment
        env = os.environ.copy()
        env["DRONE_HOST"] = DRONE_LAN
        env["GCS_HOST"] = GCS_HOST
        env["PYTHONPATH"] = str(ROOT)
        
        # Log file
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = LOGS_DIR / f"gcs_proxy_{suite_id}_{ts}.log"
        self.log_file = open(log_path, "w")
        
        cmd = [
            sys.executable,
            "-m", "core.run_proxy",
            "gcs",
            "--suite", suite_id,
            "--gcs-secret-file", str(key_file),
        ]
        
        print(f"[INFO] Starting GCS proxy: {' '.join(cmd)}")
        
        start_time = time.perf_counter_ns()
        
        try:
            if sys.platform == "win32":
                self.process = subprocess.Popen(
                    cmd,
                    stdout=self.log_file,
                    stderr=subprocess.STDOUT,
                    env=env,
                    cwd=str(ROOT),
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
            else:
                self.process = subprocess.Popen(
                    cmd,
                    stdout=self.log_file,
                    stderr=subprocess.STDOUT,
                    env=env,
                    cwd=str(ROOT),
                )
            
            self.current_suite = suite_id
            time.sleep(3)  # Wait for proxy init and handshake
            
            handshake_ms = (time.perf_counter_ns() - start_time) / 1e6
            
            if self.process.poll() is not None:
                print("[ERROR] GCS proxy exited immediately")
                return False, handshake_ms
            
            return True, handshake_ms
            
        except Exception as e:
            print(f"[ERROR] Failed to start GCS proxy: {e}")
            return False, 0.0
    
    def stop(self):
        """Stop current proxy."""
        if self.process:
            try:
                if sys.platform == "win32":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(self.process.pid)],
                        capture_output=True,
                        timeout=5,
                    )
                else:
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
# Traffic Generator
# =============================================================================

class TrafficGenerator(threading.Thread):
    """Generate UDP traffic through the tunnel."""
    
    def __init__(
        self,
        target_host: str,
        target_port: int,
        duration_s: float,
        payload_bytes: int = 1200,
        rate_pps: int = 1000,
    ):
        super().__init__(daemon=True)
        self.target_host = target_host
        self.target_port = target_port
        self.duration_s = duration_s
        self.payload_bytes = payload_bytes
        self.rate_pps = rate_pps
        
        self.packets_sent = 0
        self.bytes_sent = 0
        self.running = False
        self.done = threading.Event()
    
    def run(self):
        """Generate traffic."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
        try:
            interval = 1.0 / self.rate_pps if self.rate_pps > 0 else 0
            start_time = time.time()
            seq = 0
            
            self.running = True
            
            while self.running and (time.time() - start_time) < self.duration_s:
                # Create packet with sequence number and timestamp
                ts_bytes = time.perf_counter_ns().to_bytes(8, 'big')
                seq_bytes = seq.to_bytes(4, 'big')
                padding = b'\x00' * (self.payload_bytes - 12)
                packet = seq_bytes + ts_bytes + padding
                
                try:
                    sock.sendto(packet, (self.target_host, self.target_port))
                    self.packets_sent += 1
                    self.bytes_sent += len(packet)
                    seq += 1
                except Exception:
                    pass
                
                if interval > 0:
                    time.sleep(interval)
            
        finally:
            sock.close()
            self.running = False
            self.done.set()
    
    def stop(self):
        """Stop traffic generation."""
        self.running = False
        self.done.wait(timeout=2)


# =============================================================================
# Suite Benchmark Runner
# =============================================================================

class SuiteBenchmarkRunner:
    """Main benchmark runner."""
    
    def __init__(
        self,
        suites: List[str],
        iterations: int = 10,
        duration_s: float = 30.0,
        test_rekey: bool = True,
    ):
        self.suites = suites
        self.iterations = iterations
        self.duration_s = duration_s
        self.test_rekey = test_rekey
        
        self.drone = DroneController(DRONE_HOST, CONTROL_PORT)
        self.gcs_proxy = GCSProxyManager()
        self.results: List[SuiteBenchResult] = []
        
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    def verify_environment(self) -> bool:
        """Verify both systems are ready."""
        print("\n" + "=" * 60)
        print("PHASE 2: ENVIRONMENT VERIFICATION")
        print("=" * 60)
        
        # Check drone
        print(f"\n[CHECK] Drone control at {DRONE_HOST}:{CONTROL_PORT}...")
        if not self.drone.ping():
            print("[FAIL] Drone not responding!")
            print("       Please start suite_bench_drone.py on the Pi first.")
            return False
        
        status = self.drone.status()
        print(f"[OK] Drone responding: {status}")
        
        # Check secrets
        print(f"\n[CHECK] Suite keys in {SECRETS_DIR}...")
        missing = []
        for suite_id in self.suites:
            key_file = SECRETS_DIR / suite_id / "gcs_signing.key"
            if not key_file.exists():
                missing.append(suite_id)
        
        if missing:
            print(f"[FAIL] Missing keys for: {missing}")
            return False
        
        print(f"[OK] All {len(self.suites)} suite keys present")
        
        return True
    
    def run_suite_iteration(self, suite_id: str, iteration: int) -> SuiteBenchResult:
        """Run single suite iteration."""
        result = SuiteBenchResult(
            suite_id=suite_id,
            iteration=iteration,
            timestamp_iso=datetime.utcnow().isoformat() + "Z",
            duration_s=self.duration_s,
        )
        
        print(f"\n--- {suite_id} (iteration {iteration + 1}/{self.iterations}) ---")
        
        try:
            # 1. Start drone proxy
            print("  [1/5] Starting drone proxy...")
            drone_resp = self.drone.start_suite(suite_id, iteration)
            if drone_resp.get("status") != "ok":
                result.error = f"Drone start failed: {drone_resp.get('error')}"
                return result
            result.handshake_drone_ms = drone_resp.get("handshake_ms", 0)
            
            # 2. Start GCS proxy
            print("  [2/5] Starting GCS proxy...")
            gcs_start = time.perf_counter_ns()
            success, gcs_hs_ms = self.gcs_proxy.start(suite_id)
            if not success:
                result.error = "GCS proxy start failed"
                self.drone.stop_suite()
                return result
            result.handshake_gcs_ms = gcs_hs_ms
            result.handshake_total_ms = (time.perf_counter_ns() - gcs_start) / 1e6
            
            # 3. Wait for connection establishment
            print("  [3/5] Waiting for tunnel establishment...")
            time.sleep(2)
            
            # 4. Run traffic
            print(f"  [4/5] Running traffic for {self.duration_s}s...")
            # Traffic goes to GCS plaintext port, through tunnel
            traffic = TrafficGenerator(
                target_host=CONFIG.get("GCS_PLAINTEXT_HOST", "127.0.0.1"),
                target_port=int(CONFIG.get("GCS_PLAINTEXT_TX", 47001)),
                duration_s=self.duration_s,
                rate_pps=1000,
            )
            traffic.start()
            
            # Wait for traffic to complete
            traffic.done.wait(timeout=self.duration_s + 5)
            
            result.packets_sent = traffic.packets_sent
            result.throughput_pps = traffic.packets_sent / self.duration_s
            result.throughput_mbps = (traffic.bytes_sent * 8) / (self.duration_s * 1e6)
            
            # 5. Test rekey if enabled
            if self.test_rekey:
                print("  [5/5] Testing rekey...")
                rekey_start = time.perf_counter_ns()
                rekey_resp = self.drone.rekey()
                rekey_end = time.perf_counter_ns()
                
                if rekey_resp.get("status") == "ok":
                    result.rekey_ms = rekey_resp.get("rekey_ms", (rekey_end - rekey_start) / 1e6)
                    result.rekey_blackout_ms = rekey_resp.get("blackout_ms", result.rekey_ms)
            else:
                print("  [5/5] Rekey test skipped")
            
            # 6. Get metrics from drone
            print("  [*] Collecting metrics...")
            drone_metrics = self.drone.stop_suite()
            
            if drone_metrics.get("status") == "ok":
                metrics = drone_metrics.get("metrics", {})
                
                # Latency
                result.latency_mean_us = metrics.get("latency_mean_us", 0)
                result.latency_p50_us = metrics.get("latency_p50_us", 0)
                result.latency_p95_us = metrics.get("latency_p95_us", 0)
                result.latency_p99_us = metrics.get("latency_p99_us", 0)
                
                # Power
                result.power_mean_w = metrics.get("power_mean_w", 0)
                result.power_peak_w = metrics.get("power_peak_w", 0)
                result.energy_total_j = metrics.get("energy_total_j", 0)
                
                # Drone system
                result.drone_cpu_percent = metrics.get("cpu_percent", 0)
                result.drone_memory_mb = metrics.get("memory_mb", 0)
                result.drone_temp_c = metrics.get("temp_c", 0)
                
                # Packet stats
                result.packets_received = metrics.get("packets_received", 0)
                if result.packets_sent > 0:
                    result.packet_loss_percent = (
                        (result.packets_sent - result.packets_received) / result.packets_sent * 100
                    )
            
            # GCS system metrics
            if PSUTIL_AVAILABLE:
                result.gcs_cpu_percent = psutil.cpu_percent()
                result.gcs_memory_mb = psutil.Process().memory_info().rss / (1024 * 1024)
            
            result.success = True
            
        except Exception as e:
            result.error = str(e)
            traceback.print_exc()
        
        finally:
            # Cleanup
            self.gcs_proxy.stop()
        
        return result
    
    def run(self):
        """Run full benchmark suite."""
        print("\n" + "=" * 60)
        print("PQC SUITE BENCHMARK - GCS SCHEDULER")
        print("=" * 60)
        print(f"Session ID: {self.session_id}")
        print(f"Suites: {len(self.suites)}")
        print(f"Iterations: {self.iterations}")
        print(f"Duration per suite: {self.duration_s}s")
        print(f"Test rekey: {self.test_rekey}")
        print("=" * 60)
        
        # Verify environment
        if not self.verify_environment():
            print("\n[ABORT] Environment verification failed!")
            return
        
        print("\n" + "=" * 60)
        print("PHASE 3: RUNNING BENCHMARKS")
        print("=" * 60)
        
        total = len(self.suites) * self.iterations
        completed = 0
        
        for suite_id in self.suites:
            print(f"\n{'=' * 40}")
            print(f"SUITE: {suite_id}")
            print(f"{'=' * 40}")
            
            for i in range(self.iterations):
                result = self.run_suite_iteration(suite_id, i)
                self.results.append(result)
                completed += 1
                
                status = "✓" if result.success else "✗"
                print(f"  [{status}] Iteration {i + 1}: "
                      f"handshake={result.handshake_total_ms:.1f}ms, "
                      f"throughput={result.throughput_mbps:.2f}Mbps, "
                      f"latency_p50={result.latency_p50_us:.0f}µs")
                
                if not result.success:
                    print(f"      Error: {result.error}")
                
                # Save intermediate results
                self._save_results()
                
                # Brief pause between iterations
                time.sleep(1)
        
        # Final report
        self._generate_report()
    
    def _save_results(self):
        """Save results to JSON."""
        output_file = OUTPUT_DIR / f"suite_bench_{self.session_id}.json"
        
        data = {
            "session_id": self.session_id,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "config": {
                "suites": self.suites,
                "iterations": self.iterations,
                "duration_s": self.duration_s,
                "test_rekey": self.test_rekey,
            },
            "results": [asdict(r) for r in self.results],
        }
        
        with open(output_file, "w") as f:
            json.dump(data, f, indent=2, default=str)
    
    def _generate_report(self):
        """Generate summary report."""
        print("\n" + "=" * 60)
        print("BENCHMARK SUMMARY")
        print("=" * 60)
        
        # Group by suite
        by_suite: Dict[str, List[SuiteBenchResult]] = {}
        for r in self.results:
            if r.suite_id not in by_suite:
                by_suite[r.suite_id] = []
            by_suite[r.suite_id].append(r)
        
        print(f"\n{'Suite':<45} {'Handshake':<12} {'Throughput':<12} {'Latency P50':<12} {'Power':<10}")
        print("-" * 91)
        
        for suite_id, results in by_suite.items():
            successful = [r for r in results if r.success]
            if not successful:
                print(f"{suite_id:<45} FAILED")
                continue
            
            avg_hs = sum(r.handshake_total_ms for r in successful) / len(successful)
            avg_tp = sum(r.throughput_mbps for r in successful) / len(successful)
            avg_lat = sum(r.latency_p50_us for r in successful) / len(successful)
            avg_pwr = sum(r.power_mean_w for r in successful) / len(successful)
            
            print(f"{suite_id:<45} {avg_hs:>8.1f}ms {avg_tp:>9.2f}Mbps {avg_lat:>8.0f}µs {avg_pwr:>7.2f}W")
        
        # Save final results
        self._save_results()
        
        print(f"\nResults saved to: {OUTPUT_DIR / f'suite_bench_{self.session_id}.json'}")


# =============================================================================
# Main
# =============================================================================

def get_available_suites() -> List[str]:
    """Get suites that have keys generated."""
    available = []
    all_suites = list_suites()
    
    for suite_id in sorted(all_suites.keys()):
        key_file = SECRETS_DIR / suite_id / "gcs_signing.key"
        if key_file.exists():
            available.append(suite_id)
    
    return available


def main():
    parser = argparse.ArgumentParser(description="Suite Benchmark - GCS Scheduler")
    parser.add_argument("-s", "--suites", nargs="*", help="Specific suites to test")
    parser.add_argument("-n", "--iterations", type=int, default=LOCAL_ITERATIONS,
                        help="Iterations per suite")
    parser.add_argument("-d", "--duration", type=float, default=LOCAL_DURATION_S,
                        help="Traffic duration per suite (seconds)")
    parser.add_argument("--no-rekey", action="store_true", help="Skip rekey tests")
    parser.add_argument("--list", action="store_true", help="List available suites and exit")
    args = parser.parse_args()
    
    if args.list:
        suites = get_available_suites()
        print(f"Available suites ({len(suites)}):")
        for s in suites:
            print(f"  {s}")
        return
    
    # Determine suites to test
    if args.suites:
        suites = args.suites
    elif LOCAL_SUITES:
        suites = LOCAL_SUITES
    else:
        suites = get_available_suites()[:10]  # Limit to 10 for quick runs
    
    runner = SuiteBenchmarkRunner(
        suites=suites,
        iterations=args.iterations,
        duration_s=args.duration,
        test_rekey=not args.no_rekey,
    )
    
    def signal_handler(sig, frame):
        print("\n[INFO] Interrupted, saving results...")
        runner._save_results()
        runner.gcs_proxy.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        runner.run()
    except KeyboardInterrupt:
        pass
    finally:
        runner.gcs_proxy.stop()


if __name__ == "__main__":
    main()
