#!/usr/bin/env python3
"""
Simplified GCS Scheduler (FOLLOWER) - sscheduler/sgcs.py

REVERSED CONTROL: GCS follows drone commands.
- GCS has control server, waits for drone commands
- GCS starts its proxy when drone says "start"
- GCS runs traffic generator when commanded
- Drone controls suite order, timing, rekey

Usage:
    python -m sscheduler.sgcs [options]

Environment:
    DRONE_HOST          Drone IP (default: from config)
    GCS_HOST            GCS IP (default: from config)
    GCS_CONTROL_HOST    GCS control server bind IP (default: GCS_HOST)
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
import atexit
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG
from core.suites import get_suite, list_suites
from core.process import ManagedProcess
from sscheduler.mavproxy_manager import MavProxyManager
from sscheduler.gcs_metrics import GcsMetricsCollector
from core.clock_sync import ClockSync

# Consolidated scheduler utilities
from sscheduler.common import resolve_benchmark_mode, log, read_handshake_status
from sscheduler.gcs_client import send_gcs_command, wait_for_gcs
from sscheduler.proxy_managers import GcsProxyManager
from sscheduler.traffic import UdpEchoServer
from sscheduler.control_server_base import ControlServerBase


# Extract config values (single source of truth)
DRONE_HOST = str(CONFIG.get("DRONE_HOST"))
GCS_HOST = str(CONFIG.get("GCS_HOST"))

GCS_PLAIN_TX_PORT = int(CONFIG.get("GCS_PLAINTEXT_TX", 47001))
GCS_PLAIN_RX_PORT = int(CONFIG.get("GCS_PLAINTEXT_RX", 47002))
DRONE_PLAIN_RX_PORT = int(CONFIG.get("DRONE_PLAINTEXT_RX", 47004))

GCS_TELEMETRY_PORT = int(CONFIG.get("GCS_TELEMETRY_PORT", 52080))
GCS_TELEMETRY_SNIFF_PORT = 14552
TCP_CTRL_PORT = int(CONFIG.get("TCP_HANDSHAKE_PORT", 46000))
QGC_PORT = int(CONFIG.get("QGC_PORT", 14550))
# Bind control server to 0.0.0.0 so Drone can connect in diverse networks
GCS_CONTROL_HOST = str(CONFIG.get("GCS_CONTROL_HOST", "0.0.0.0"))
# Use configured GCS control port (default 48080)
GCS_CONTROL_PORT = int(CONFIG.get("GCS_CONTROL_PORT", 48080))

# Derived internal proxy control port to avoid collision when ports change
PROXY_INTERNAL_CONTROL_PORT = GCS_CONTROL_PORT + 100

SECRETS_DIR = Path(__file__).parent.parent / "secrets" / "matrix"

# Default traffic settings (can be overridden by drone)
DEFAULT_RATE_MBPS = 110.0
DEFAULT_DURATION = 10.0
PAYLOAD_SIZE = 1200

# --------------------
# Local editable configuration (edit here, no CLI args needed)
# --------------------
LOCAL_RATE_MBPS = None  # e.g. 110.0
LOCAL_DURATION = None  # e.g. 10.0
LOCAL_MAX_SUITES = None
LOCAL_SUITES = None

# Get all suites (list_suites returns dict, convert to list of dicts)
_suites_dict = list_suites()
SUITES = [{"name": k, **v} for k, v in _suites_dict.items()]

# ============================================================
# Mode Resolution (identical logic across schedulers)
# ============================================================

def wait_for_tcp_port(port: int, timeout: float = 5.0) -> bool:
    """Wait for a local TCP port to be listening."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (ConnectionRefusedError, OSError, socket.timeout):
            time.sleep(0.2)
    return False

# ============================================================
# Telemetry Sender
# ============================================================

class TelemetrySender:
    """Sends telemetry updates to all configured Drones via UDP (Fire-and-Forget)"""
    def __init__(self, target_host: str, target_port: int, target_hosts: Optional[List[str]] = None):
        self.target_host = target_host
        self.port = target_port
        drone_hosts_dict = CONFIG.get("DRONE_HOSTS", {})
        hosts_list = target_hosts or (list(drone_hosts_dict.values()) if isinstance(drone_hosts_dict, dict) else [target_host])
        self.target_addrs = list({(h, target_port) for h in hosts_list if h})
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.seq = 0
        self.lock = threading.Lock()

    def send(self, packet: dict):
        """Send a telemetry packet (Schema v1) to all target drones"""
        with self.lock:
            self.seq += 1
            packet["seq"] = self.seq
        
        try:
            payload = json.dumps(packet).encode('utf-8')
            for addr in self.target_addrs:
                self.sock.sendto(payload, addr)
        except Exception:
            # Fire and forget
            pass

    def close(self):
        self.sock.close()

# ============================================================
# Control Server (GCS listens for drone commands)
# ============================================================

class ControlServer(ControlServerBase):
    """TCP control server - GCS listens for commands from drone"""
    
    def __init__(self, proxy: GcsProxyManager, mode: str):
        raw_allowed = CONFIG.get("MAV_ALLOWED_SENDERS", [])
        allowed_senders: List[str] = []
        if isinstance(raw_allowed, str):
            allowed_senders = [p.strip() for p in raw_allowed.split(",") if p.strip()]
        elif isinstance(raw_allowed, (list, tuple, set)):
            allowed_senders = [str(p).strip() for p in raw_allowed if str(p).strip()]

        # Populate allowlist with all configured drone IPs (DRONE_HOSTS & DRONE_HOST_ALLOWLIST)
        drone_hosts_dict = CONFIG.get("DRONE_HOSTS", {})
        if isinstance(drone_hosts_dict, dict):
            for ip in drone_hosts_dict.values():
                if ip and ip not in allowed_senders:
                    allowed_senders.append(str(ip))

        allowlist = CONFIG.get("DRONE_HOST_ALLOWLIST", [])
        if isinstance(allowlist, (list, tuple, set)):
            for ip in allowlist:
                if ip and ip not in allowed_senders:
                    allowed_senders.append(str(ip))

        if DRONE_HOST and DRONE_HOST not in allowed_senders:
            allowed_senders.append(DRONE_HOST)
        super().__init__(
            proxy,
            GCS_CONTROL_HOST,
            GCS_CONTROL_PORT,
            SUITES,
            allowed_senders=allowed_senders,
            require_auth=True,
            default_rate_mbps=DEFAULT_RATE_MBPS,
            default_duration_s=DEFAULT_DURATION,
        )
        self.mode = mode
        self.mavproxy = MavProxyManager("gcs")
        # Persistent mavproxy subprocess handle (if started here)
        self.mavproxy_proc = None
        self.clock_sync = ClockSync(
            smoothing=bool(CONFIG.get("CLOCK_SYNC_SMOOTHING", False)),
            window=int(CONFIG.get("CLOCK_SYNC_WINDOW", 3)),
        )
        
        # Telemetry
        self.telemetry = TelemetrySender(DRONE_HOST, GCS_TELEMETRY_PORT)
        self.telemetry_thread = None
        
        # Metrics Collector
        self.metrics_collector = GcsMetricsCollector(
            mavlink_host="127.0.0.1",
            mavlink_port=GCS_TELEMETRY_SNIFF_PORT,
            proxy_manager=self.proxy,
            log_dir=Path(__file__).parent.parent / "logs" / "gcs_telemetry"
        )

    def start_persistent_mavproxy(self):
        """Start a persistent mavproxy subprocess for the lifetime of the scheduler.

        Uses `sys.executable -m MAVProxy.mavproxy` where possible so Windows/sudo
        environments resolve correctly.
        """
        try:
            bind_host = str(CONFIG.get("GCS_PLAINTEXT_BIND", "0.0.0.0"))
            listen_port = int(CONFIG.get("GCS_PLAINTEXT_RX", GCS_PLAIN_RX_PORT))
            tunnel_out_port = int(CONFIG.get("GCS_PLAINTEXT_TX", GCS_PLAIN_TX_PORT))
            QGC_PORT = int(CONFIG.get("QGC_PORT", 14550))

            master_str = f"udpin:{bind_host}:{listen_port}"
            # out_arg = f"udp:127.0.0.1:{tunnel_out_port}"

            # Prefer module invocation to avoid PATH issues on Windows
            python_exe = sys.executable
            
            # Interactive mode requested: Remove --daemon and use CREATE_NEW_CONSOLE on Windows
            # Removed --out to proxy to prevent loops; rely on reply-to-sender from proxy
            # [FIX] Removed --daemon, added --map --console for interactive GUI
            # Added telemetry sniff port output
            cmd = [
                python_exe, "-m", "MAVProxy.mavproxy", 
                f"--master={master_str}", 
                "--dialect=ardupilotmega", 
                "--nowait", 
                "--map", 
                "--console", 
                f"--out=udp:127.0.0.1:{QGC_PORT}",
                f"--out=udp:127.0.0.1:{GCS_TELEMETRY_SNIFF_PORT}"
            ]

            log(f"Starting persistent mavproxy: {' '.join(cmd)}")

            log_dir = Path(__file__).resolve().parents[1] / "logs" / "sscheduler" / "gcs"
            log_dir.mkdir(parents=True, exist_ok=True)
            ts_now = time.strftime("%Y%m%d-%H%M%S")
            log_path = log_dir / f"mavproxy_gcs_{ts_now}.log"
            try:
                fh = open(log_path, "w", encoding="utf-8")
            except Exception:
                fh = subprocess.DEVNULL

            stdout_arg = fh
            stderr_arg = subprocess.STDOUT
            
            if sys.platform == "win32":
                # On Windows, redirecting stdout breaks prompt_toolkit even with new_console=True
                stdout_arg = None
                stderr_arg = None
            
            # Add TERM=dumb to environment to avoid prompt_toolkit crash on Windows
            env = os.environ.copy()
            env["TERM"] = "dumb"

            stdin_arg = subprocess.DEVNULL
            if sys.platform == "win32":
                stdin_arg = None # Allow inheritance/detachment for interactive console

            self.mavproxy_proc = ManagedProcess(
                cmd=cmd,
                name="mavproxy-gcs",
                stdout=stdout_arg,
                stderr=stderr_arg,
                stdin=stdin_arg,
                new_console=True, # Windows requires a console for prompt_toolkit
                env=env
            )
            
            if self.mavproxy_proc.start():
                # Update metrics collector with process handle
                self.metrics_collector.mavproxy_proc = self.mavproxy_proc
                
                if wait_for_tcp_port(TCP_CTRL_PORT, timeout=5.0):
                    log("Persistent mavproxy started (port open)")
                    return True
                elif self.mavproxy_proc.is_running():
                    log("Persistent mavproxy started (process running, but port not yet ready)")
                    return True
                else:
                    log("Persistent mavproxy failed to start")
                    return False
            return False
        except Exception as e:
            log(f"start_persistent_mavproxy exception: {e}")
            return False

    def on_start(self):
        # Start metrics collector
        self.metrics_collector.start()
        
        # Start telemetry loop
        self.telemetry_thread = threading.Thread(target=self._telemetry_loop, daemon=True)
        self.telemetry_thread.start()

    def _telemetry_loop(self):
        """Periodically send status to drone"""
        while self.running:
            try:
                # Get latest metrics snapshot
                snapshot = self.metrics_collector.get_snapshot()
                self.telemetry.send(snapshot)
            except Exception:
                pass
            
            time.sleep(0.2)

    def _status_payload(self) -> dict:
        return {
            "mavproxy_running": bool(self.mavproxy_proc and self.mavproxy_proc.is_running()),
        }

    def after_proxy_started(self, request: dict) -> Optional[str]:
        if self.mode == "MAVPROXY" and not (self.mavproxy_proc and self.mavproxy_proc.is_running()):
            return "mavproxy_not_running"
        log("Proxy started; persistent MAVProxy assumed running")
        return None

    def on_prepare_rekey(self, request: dict):
        log("Prepare rekey: stopping proxy...")

    def on_stop_command(self, request: dict):
        log("Stop command received")
        if self.mavproxy_proc:
            try:
                self.mavproxy_proc.stop()
            except Exception:
                pass
            self.mavproxy_proc = None

    def on_stop(self):
        if self.telemetry_thread:
            self.telemetry_thread.join(timeout=2.0)
        if self.metrics_collector:
            self.metrics_collector.stop()
        if self.telemetry:
            self.telemetry.close()
        if self.mavproxy_proc:
            try:
                self.mavproxy_proc.stop()
            except Exception:
                pass
            self.mavproxy_proc = None

    def handle_custom_command(self, request: dict) -> Optional[dict]:
        cmd = request.get("cmd", "")

        if cmd == "start":
            suite = request.get("suite")
            if not suite:
                return {"status": "error", "message": "missing suite"}

            log(f"Start requested for suite: {suite}")
            if not self.proxy.start(suite):
                return {"status": "error", "message": "proxy_start_failed"}

            time.sleep(1.0)
            log("Traffic start requested (MAVProxy is already running)")
            if not (self.mavproxy_proc and self.mavproxy_proc.is_running()):
                return {"status": "error", "message": "mavproxy_not_running"}
            return {"status": "ok", "message": "started"}

        if cmd == "start_traffic":
            return {"status": "error", "message": "traffic_generation_disabled"}

        if cmd == "chronos_sync":
            try:
                return self.clock_sync.server_handle_sync(request)
            except Exception as exc:
                return {"status": "error", "message": str(exc)}

        return None

# ============================================================
# Main
# ============================================================

def cleanup_environment(mode: Optional[str] = None):
    """Force kill any stale instances of our components."""
    mode = mode or resolve_benchmark_mode(None, default_mode="MAVPROXY")
    if mode == "MAVPROXY":
        return
    log("Cleaning up stale processes...")
    
    # Current PID to avoid suicide (though unlikely to match targets)
    my_pid = os.getpid()
    
    targets = ["mavproxy", "core.run_proxy"]
    
    if sys.platform.startswith("win"):
        # Windows: Use taskkill for known PIDs if we tracked them, but here we are cleaning up *stale* ones.
        # WMIC is slow but effective for pattern matching.
        for t in targets:
            # Clause: name='python.exe' AND commandline like '%target%' AND ProcessId != my_pid
            query = f"name='python.exe' and commandline like '%{t}%' and ProcessId!={my_pid}"
            cmd = f'wmic process where "{query}" call terminate'
            try:
                subprocess.run(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
    else:
        # Linux/Posix
        for t in targets:
             subprocess.run(["pkill", "-f", t], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
             
    time.sleep(1.0)

def main():
    parser = argparse.ArgumentParser(description="GCS Scheduler (Follower)")
    parser.add_argument("--mode", type=str, help="Benchmark mode: MAVPROXY")
    args = parser.parse_args()

    args.mode_resolved = resolve_benchmark_mode(args.mode, default_mode="MAVPROXY")
    log(f"BENCHMARK_MODE resolved to {args.mode_resolved}")
    
    print("=" * 60)
    print("Simplified GCS Scheduler (FOLLOWER) - sscheduler")
    print("=" * 60)
    # Configuration dump for debugging
    cfg = {
        "DRONE_HOST": DRONE_HOST,
        "GCS_HOST": GCS_HOST,
        "GCS_CONTROL_BIND": f"{GCS_CONTROL_HOST}:{GCS_CONTROL_PORT}",
        "PROXY_INTERNAL_CONTROL_PORT": PROXY_INTERNAL_CONTROL_PORT,
        "GCS_PLAINTEXT_RX": GCS_PLAIN_RX_PORT,
        "GCS_PLAINTEXT_TX": GCS_PLAIN_TX_PORT,
        "DRONE_PLAINTEXT_RX": DRONE_PLAIN_RX_PORT,
    }
    log("Configuration Dump:")
    for k, v in cfg.items():
        log(f"  {k}: {v}")
    log("GCS scheduler running. Waiting for commands from drone...")
    log("(Drone will send 'start', 'rekey', 'stop' commands)")

    # Register cleanup on exit
    atexit.register(cleanup_environment, args.mode_resolved)
    
    # Cleanup environment before starting
    cleanup_environment(args.mode_resolved)

    # Initialize components
    proxy = GcsProxyManager()
    control = ControlServer(proxy, args.mode_resolved)
    control.start()

    # Start persistent MAVProxy for the scheduler lifetime
    try:
        ok = control.start_persistent_mavproxy()
        if ok:
            log("persistent mavproxy started at scheduler startup")
        else:
            if args.mode_resolved == "MAVPROXY":
                log("Shutdown reason: error: mavproxy_not_running")
                control.stop()
                proxy.stop()
                return 2
            log("persistent mavproxy failed to start at scheduler startup")
    except Exception as _e:
        log(f"persistent mavproxy startup exception: {_e}")

    # Apply local in-file overrides for rate/duration if set
    if LOCAL_RATE_MBPS is not None:
        control.rate_mbps = float(LOCAL_RATE_MBPS)
    if LOCAL_DURATION is not None:
        control.duration = float(LOCAL_DURATION)
    
    # Wait for shutdown
    shutdown = threading.Event()
    
    def signal_handler(sig, frame):
        log("Shutdown reason: normal: interrupted")
        shutdown.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        while not shutdown.is_set():
            shutdown.wait(timeout=1.0)
    finally:
        if not shutdown.is_set():
            log("Shutdown reason: normal: completed")
        log("Shutting down...")
        control.stop()
        proxy.stop()
    
    log("GCS scheduler stopped")
    return 0

if __name__ == "__main__":
    sys.exit(main())



