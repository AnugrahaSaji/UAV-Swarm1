#!/usr/bin/env python3
"""
Simplified Drone Scheduler (CONTROLLER) - sscheduler/sdrone.py

REVERSED CONTROL: Drone is the controller, GCS follows.
- Drone decides suite order, timing, rekey
- Drone sends commands to GCS
- Drone runs echo server (receives traffic from GCS)
- Drone starts its proxy first, then tells GCS to start

Usage:
    python -m sscheduler.sdrone [options]

Environment:
    DRONE_HOST          Drone IP (default: from config)
    GCS_HOST            GCS IP (default: from config)
    GCS_CONTROL_HOST    GCS control server IP (default: GCS_HOST)
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
import logging
import atexit
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG
from core.suites import list_suites
from core.process import ManagedProcess
from core.clock_sync import ClockSync
from sscheduler.mavproxy_manager import MavProxyManager
from sscheduler.policy import LinearLoopPolicy, RandomPolicy, ManualOverridePolicy
from sscheduler.common import resolve_benchmark_mode
from sscheduler.gcs_client import send_gcs_command as _send_gcs_command, wait_for_gcs as _wait_for_gcs, resolve_control_host
from sscheduler.proxy_managers import DroneProxyManager

# Extract config values (use CONFIG as single source of truth)
DRONE_HOST = str(CONFIG.get("DRONE_HOST"))
GCS_HOST = str(CONFIG.get("GCS_HOST"))
DRONE_PLAIN_RX_PORT = int(CONFIG.get("DRONE_PLAINTEXT_RX", 47004))
DRONE_PLAIN_TX_PORT = int(CONFIG.get("DRONE_PLAINTEXT_TX", 47003))
GCS_TELEMETRY_PORT = int(CONFIG.get("GCS_TELEMETRY_PORT", 52080))

# Control endpoint for GCS: use configured GCS_CONTROL_HOST or GCS_HOST and GCS_CONTROL_PORT
GCS_CONTROL_HOST = resolve_control_host(CONFIG.get("GCS_CONTROL_HOST", CONFIG.get("GCS_HOST")))
GCS_CONTROL_PORT = int(CONFIG.get("GCS_CONTROL_PORT", 48080))

# Derived internal proxy control port to avoid collisions
PROXY_INTERNAL_CONTROL_PORT = GCS_CONTROL_PORT + 100

DEFAULT_SUITE = "cs-mlkem768-mldsa65"
SECRETS_DIR = Path(__file__).parent.parent / "secrets" / "matrix"

# Traffic settings (for telling GCS how long to run)
DEFAULT_DURATION = 10.0  # seconds per suite
DEFAULT_RATE_MBPS = 110.0
PAYLOAD_SIZE = 1200

# --------------------
# Local editable configuration (edit here, no CLI args needed)
# --------------------
LOCAL_DURATION = 30.0  # override DEFAULT_DURATION if set, e.g. 10.0
LOCAL_RATE_MBPS = None  # override DEFAULT_RATE_MBPS if set, e.g. 110.0
LOCAL_MAX_SUITES = 3  # limit suites run, e.g. 2
# Use fast ML-KEM suites instead of slow Classic McEliece
LOCAL_SUITES = [
    "cs-mlkem768-mldsa65",
    "cs-mlkem512-mldsa44",
    "cs-mlkem1024-mldsa87",
]

# Get all suites (list_suites returns dict, convert to list of dicts)
_suites_dict = list_suites()
SUITES = [{"name": k, **v} for k, v in _suites_dict.items()]

ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs" / "sscheduler" / "drone"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# Logging
# ============================================================

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [sdrone-ctrl] {msg}", flush=True)

# ============================================================
# Telemetry Listener & Decision Context
# ============================================================

class TelemetryListener:
    """Receives telemetry updates from GCS via UDP"""
    def __init__(self, port: int):
        self.port = port
        self.sock = None
        self.running = False
        self.thread = None
        self.latest_data = {}
        self.last_update = 0
        self.lock = threading.Lock()

    def start(self):
        if self.running:
            return
            
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", self.port))
        self.sock.settimeout(1.0)
        
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        log(f"Telemetry listener started on port {self.port}")

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(65535)
                try:
                    packet = json.loads(data.decode('utf-8'))
                    with self.lock:
                        # Support v1 schema (flat) or legacy (nested data)
                        if "schema" in packet:
                            self.latest_data = packet
                        else:
                            self.latest_data = packet.get("data", {})
                        self.last_update = time.time()
                except json.JSONDecodeError:
                    pass
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    log(f"Telemetry error: {e}")

    def get_latest(self):
        with self.lock:
            return self.latest_data, self.last_update

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.sock:
            self.sock.close()

class DecisionContext:
    """Aggregates system state for policy decisions"""
    def __init__(self, telemetry: TelemetryListener):
        self.telemetry = telemetry

    def get_gcs_status(self):
        data, ts = self.telemetry.get_latest()
        age = time.time() - ts
        return data, age

# MavProxyManager imported from tools.mavproxy_manager

# ============================================================
# GCS Control Client (drone sends commands to GCS)
# ============================================================

def send_gcs_command(cmd: str, **params) -> dict:
    """Send command to GCS control server"""
    return _send_gcs_command(cmd, host=GCS_CONTROL_HOST, port=GCS_CONTROL_PORT, **params)

def wait_for_gcs(timeout: float = 30.0) -> bool:
    """Wait for GCS control server to be ready"""
    return _wait_for_gcs(timeout=timeout, host=GCS_CONTROL_HOST, port=GCS_CONTROL_PORT)

# ============================================================
# Suite Runner
# ============================================================

def run_suite(proxy: DroneProxyManager, mavproxy, 
              suite_name: str, duration: float, is_first: bool = False) -> dict:
    """Run a single suite test - drone controls the flow.
    
    NOTE: Even though drone is the controller, GCS proxy must start first
    because the TCP handshake requires GCS to listen and drone to connect.
    Drone controls WHEN to start, but GCS proxy goes up first.
    """
    
    result = {
        "suite": suite_name,
        "status": "unknown",
        "echo_rx": 0,
        "echo_tx": 0,
    }
    
    # Ensure mavproxy (application-layer relay) is available
    mav_running = False
    try:
        # Support either the manager object with is_running(), or a subprocess.Popen
        if hasattr(mavproxy, "is_running"):
            mav_running = bool(mavproxy.is_running())
        else:
            # treat mavproxy as subprocess-like
            mav_running = mavproxy is not None and getattr(mavproxy, "poll", lambda: None)() is None
    except Exception:
        mav_running = False
    
    if not is_first:
        # Rekey: tell GCS to prepare (stop its proxy)
        log("Preparing GCS for rekey...")
        resp = send_gcs_command("prepare_rekey")
        if resp.get("status") != "ok":
            log(f"GCS prepare_rekey failed: {resp}")
            result["status"] = "gcs_prepare_failed"
            return result
        
        # Stop our proxy too
        proxy.stop()
        time.sleep(0.5)
    
    # Tell GCS to start its proxy first (GCS listens, drone connects)
    log(f"Telling GCS to start proxy for {suite_name}...")
    resp = send_gcs_command("start_proxy", suite=suite_name)
    log(f"GCS start_proxy response: {resp}")
    if resp.get("status") != "ok":
        log(f"GCS start_proxy failed: {resp}")
        result["status"] = "gcs_start_failed"
        return result

    # Wait for GCS proxy to be ready by polling status
    log("Waiting for GCS proxy to report ready...")
    start_wait = time.time()
    ready = False
    while time.time() - start_wait < 20.0:
        time.sleep(0.5)
        try:
            st = send_gcs_command("status")
            if st.get("proxy_running"):
                ready = True
                break
        except Exception:
            pass

    if not ready:
        log("GCS proxy did not become ready in time")
        result["status"] = "gcs_not_ready"
        return result
    
    # Now start drone proxy (it will connect to GCS)
    log(f"Starting drone proxy for {suite_name}...")
    if not proxy.start(suite_name):
        result["status"] = "proxy_start_failed"
        # include last log path if available
        try:
            tail = getattr(proxy, "_last_log", None)
            if tail:
                result["log"] = str(tail)
        except Exception:
            pass
        return result
    
    # Wait for handshake
    time.sleep(1.0)
    
    log("MAVProxy tunnel active; holding for suite duration...")
    start_time = time.time()
    while time.time() - start_time < duration:
        time.sleep(2.0)
        try:
            log(f"mavproxy running: {mavproxy.is_running()}")
        except Exception:
            pass
        if not proxy.is_running():
            log("Proxy exited unexpectedly")
            result["status"] = "proxy_exited"
            return result
    
    # Indicate mavproxy and proxy status in result
    try:
        if hasattr(mavproxy, "is_running"):
            result["mavproxy_running"] = bool(mavproxy.is_running())
        else:
            result["mavproxy_running"] = mavproxy is not None and getattr(mavproxy, "poll", lambda: 1)() is None
    except Exception:
        result["mavproxy_running"] = False
    result["proxy_running"] = bool(proxy.is_running())
    result["status"] = "pass"
    
    return result


# ============================================================
# Scheduler Class
# ============================================================


class DroneScheduler:
    """Manages persistent MAVProxy and per-suite crypto tunnels."""

    def __init__(self, args, suites):
        self.args = args
        self.mode = getattr(args, "mode_resolved", None) or resolve_benchmark_mode(
            getattr(args, "mode", None),
            default_mode="MAVPROXY",
        )
        self.suites = suites
        self.policy = LinearLoopPolicy(self.suites, duration_s=float(self.args.duration))
        self.proxy = DroneProxyManager()
        self.mavproxy_proc = None
        self.current_proxy_proc = None
        self.clock_sync = ClockSync(
            smoothing=bool(CONFIG.get("CLOCK_SYNC_SMOOTHING", False)),
            window=int(CONFIG.get("CLOCK_SYNC_WINDOW", 3)),
        )
        
        # Telemetry & Decision Context
        self.telemetry = TelemetryListener(GCS_TELEMETRY_PORT)
        self.context = DecisionContext(self.telemetry)
        
        # Simple GCS client wrapper exposing send_command
        class _GcsClient:
            def send_command(self, cmd, params=None):
                params = params or {}
                try:
                    return send_gcs_command(cmd, **params)
                except Exception as e:
                    return {"status": "error", "message": str(e)}

        self.gcs_client = _GcsClient()

    def wait_for_handshake_completion(self, timeout: float = 10.0) -> bool:
        """Poll for the handshake completion status file."""
        status_file = Path(__file__).resolve().parents[1] / "logs" / "sscheduler" / "drone" / "drone_status.json"
        start_time = time.time()
        while time.time() - start_time < timeout:
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

    def start_persistent_mavproxy(self) -> bool:
        """Start MAVProxy once for the scheduler and keep handle."""
        try:
            python_exe = sys.executable
            master = self.args.mav_master

            # OS auto-fallback: if master is a Linux device path (/dev/...) on Windows, fallback to SITL UDP
            if sys.platform == "win32" and str(master).startswith("/dev/"):
                fallback_master = "udp:127.0.0.1:14550"
                log(f"Warning: Linux device path '{master}' is invalid on Windows. Auto-falling back to '{fallback_master}'.")
                master = fallback_master

            out_arg = f"udp:127.0.0.1:{DRONE_PLAIN_TX_PORT}"

            # Interactive GUI mode (map and console) enabled by default (disable with --no-map)
            cmd = [
                python_exe,
                "-m",
                "MAVProxy.mavproxy",
                f"--master={master}",
                f"--out={out_arg}",
                "--dialect=ardupilotmega",
                "--nowait",
            ]
            if getattr(self.args, "map", True):
                cmd.extend(["--map", "--console"])
            else:
                cmd.append("--daemon")

            ts = time.strftime("%Y%m%d-%H%M%S")
            log_dir = LOGS_DIR
            log_dir.mkdir(parents=True, exist_ok=True)
            log_path = log_dir / f"mavproxy_drone_{ts}.log"
            try:
                fh = open(log_path, "w", encoding="utf-8")
            except Exception:
                fh = subprocess.DEVNULL

            stdout_arg = fh
            stderr_arg = subprocess.STDOUT
            stdin_arg = subprocess.DEVNULL
            new_console = False

            if sys.platform == "win32":
                # On Windows, redirecting stdout/stderr breaks prompt_toolkit even with --daemon unless stdout=None
                stdout_arg = None
                stderr_arg = None
                stdin_arg = None
                new_console = True

            env = os.environ.copy()
            env["TERM"] = "dumb"

            log(f"Starting persistent mavproxy (drone): {' '.join(cmd)} (log: {log_path})")

            self.mavproxy_proc = ManagedProcess(
                cmd=cmd,
                name="mavproxy-drone",
                stdin=stdin_arg,
                stdout=stdout_arg,
                stderr=stderr_arg,
                new_console=new_console,
                env=env,
            )

            if self.mavproxy_proc.start():
                time.sleep(1.5)
                if not self.mavproxy_proc.is_running():
                    log(f"MAVProxy exited immediately after start. See log: {log_path}")
                    return False
                return True
            return False
        except Exception as e:
            log(f"start_persistent_mavproxy exception: {e}")
            return False

    def start_tunnel_for_suite(self, suite_name: str) -> bool:
        return self.proxy.start(suite_name)

    def stop_current_tunnel(self):
        try:
            # stop crypto proxy
            if self.proxy and self.proxy.is_running():
                logging.info("Stopping crypto proxy")
                self.proxy.stop()
        except Exception:
            pass

    def cleanup(self):
        logging.info("--- DroneScheduler CLEANUP START ---")
        try:
            if self.telemetry:
                self.telemetry.stop()
        except Exception:
            pass

        try:
            self.stop_current_tunnel()
        except Exception:
            pass

        try:
            if self.mavproxy_proc:
                logging.info(f"Terminating MAVProxy")
                self.mavproxy_proc.stop()
        except Exception:
            pass

        logging.info("--- DroneScheduler CLEANUP COMPLETE ---")

    def _shutdown(self, reason: str, *, error: bool) -> None:
        level = "ERROR" if error else "INFO"
        log(f"Shutdown reason: {reason} ({level})")
        self.cleanup()

    def run_scheduler(self):
        def _sigint(sig, frame):
            self._shutdown("normal: interrupted", error=False)
            sys.exit(0)

        signal.signal(signal.SIGINT, _sigint)

        # Start Telemetry Listener
        self.telemetry.start()

        # Clock sync with GCS control server
        try:
            t1 = time.time()
            resp = send_gcs_command("chronos_sync", t1=t1)
            t4 = time.time()
            if resp.get("status") == "ok":
                offset = self.clock_sync.update_from_rpc(t1, t4, resp)
                log(f"Clock sync offset (gcs-drone): {offset:.6f}s")
            else:
                log(f"Clock sync failed: {resp}")
        except Exception as e:
            log(f"Clock sync error: {e}")

        # Start MAVProxy once
        ok = self.start_persistent_mavproxy()
        if not ok:
            if self.mode == "MAVPROXY":
                self._shutdown("error: mavproxy_not_running", error=True)
                return
            log("Warning: persistent MAVProxy failed to start; continuing")

        count = 0
        shutdown_reason = None
        shutdown_error = False
        try:
            while True:
                if self.mode == "MAVPROXY" and not (self.mavproxy_proc and self.mavproxy_proc.is_running()):
                    shutdown_reason = "error: mavproxy_died"
                    shutdown_error = True
                    log("ERROR: MAVProxy died during MAVProxy-only run; aborting")
                    break
                suite_name = self.policy.next_suite()
                duration = self.policy.get_duration()
                log(f"=== Activating Suite: {suite_name} (duration={duration}) ===")

                # Coordinate with GCS: request GCS to start its proxy BEFORE starting local proxy
                try:
                    log(f"Telling GCS to start proxy for {suite_name}...")
                    resp = self.gcs_client.send_command("start_proxy", {"suite": suite_name})
                    if resp.get("status") != "ok":
                        logging.error(f"GCS rejected start_proxy: {resp}")
                        # skip this suite and continue
                        time.sleep(1.0)
                        continue
                    else:
                        log(f"GCS acknowledged start_proxy for {suite_name}")
                except Exception as e:
                    logging.error(f"Failed to command GCS: {e}")
                    time.sleep(1.0)
                    continue

                # Now start local crypto tunnel (drone proxy)
                self.start_tunnel_for_suite(suite_name)
                
                # Wait for handshake to complete before counting duration
                if self.wait_for_handshake_completion(timeout=10.0):
                    log(f"Handshake complete for {suite_name}")
                else:
                    log(f"Warning: Handshake timed out for {suite_name}")

                time.sleep(duration)
                self.stop_current_tunnel()

                count += 1
                if self.args.max_suites and count >= int(self.args.max_suites):
                    shutdown_reason = "normal: max_suites_reached"
                    shutdown_error = False
                    break

                time.sleep(2.0)
        except Exception as e:
            logging.error(f"Scheduler crash: {e}")
        finally:
            if shutdown_reason is None:
                shutdown_reason = "normal: completed"
                shutdown_error = False
            self._shutdown(shutdown_reason, error=shutdown_error)


# ============================================================
# Main
# ============================================================

def cleanup_environment(mode: Optional[str] = None):
    """Force kill any stale instances of our components (Linux/Posix)."""
    mode = mode or resolve_benchmark_mode(None, default_mode="MAVPROXY")
    if mode == "MAVPROXY":
        return
    log("Cleaning up stale processes...")
    patterns = ["mavproxy.py", "core.run_proxy"]
    for p in patterns:
        try:
            # -f matches full command line, ignore exit code (1 if not found)
            subprocess.run(["pkill", "-f", p], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception as e:
            log(f"Cleanup warning: {e}")
    # Give OS time to reclaim resources
    time.sleep(1.0)

def main():
    default_master = str(CONFIG.get("MAV_FC_DEVICE", "/dev/ttyACM0"))
    if sys.platform == "win32" and default_master.startswith("/dev/"):
        default_master = "udp:127.0.0.1:14550"

    parser = argparse.ArgumentParser(description="Drone Scheduler (Controller)")
    parser.add_argument("--mav-master", default=default_master, help="Primary MAVLink master (e.g. COM3, udp:127.0.0.1:14550, or /dev/ttyACM0)")
    parser.add_argument("--suite", default=None, help="Single suite to run")
    parser.add_argument("--nist-level", choices=["L1", "L3", "L5"], help="Run suites for NIST level")
    parser.add_argument("--all", action="store_true", help="Run all suites")
    parser.add_argument("--duration", type=float, default=DEFAULT_DURATION, help="Seconds per suite")
    parser.add_argument("--rate", type=float, default=DEFAULT_RATE_MBPS, help="Traffic rate Mbps")
    parser.add_argument("--max-suites", type=int, default=None, help="Max suites to run")
    parser.add_argument("--map", action="store_true", default=True, help="Launch interactive MAVProxy Map and Console GUI windows (default: True)")
    parser.add_argument("--no-map", dest="map", action="store_false", help="Disable interactive MAVProxy Map and Console GUI windows")
    parser.add_argument("--mode", type=str, help="Benchmark mode: MAVPROXY")
    args = parser.parse_args()

    args.mode_resolved = resolve_benchmark_mode(args.mode, default_mode="MAVPROXY")
    log(f"BENCHMARK_MODE resolved to {args.mode_resolved}")
    
    print("=" * 60)
    print("Simplified Drone Scheduler (CONTROLLER) - sscheduler")
    print("=" * 60)
    # Configuration dump for debugging
    cfg = {
        "DRONE_HOST": DRONE_HOST,
        "GCS_HOST": GCS_HOST,
        "GCS_CONTROL": f"{GCS_CONTROL_HOST}:{GCS_CONTROL_PORT}",
        "PROXY_INTERNAL_CONTROL_PORT": PROXY_INTERNAL_CONTROL_PORT,
        "DRONE_PLAINTEXT_RX": DRONE_PLAIN_RX_PORT,
        "DRONE_PLAINTEXT_TX": DRONE_PLAIN_TX_PORT,
    }
    log("Configuration Dump:")
    for k, v in cfg.items():
        log(f"  {k}: {v}")
    log(f"Duration: {args.duration}s per suite, Rate: {args.rate} Mbps")
    
    # Determine suites to run
    if args.suite:
        suites_to_run = [args.suite]
    elif args.nist_level:
        suites_to_run = [s["name"] for s in SUITES if s.get("nist_level") == args.nist_level]
    elif args.all:
        suites_to_run = [s["name"] for s in SUITES]
    else:
        # Default: run all available suites
        suites_to_run = [s["name"] for s in SUITES]

    if args.max_suites:
        suites_to_run = suites_to_run[:args.max_suites]

    # Register cleanup on exit
    atexit.register(cleanup_environment, args.mode_resolved)

    # Apply local in-file overrides
    if LOCAL_RATE_MBPS is not None:
        args.rate = float(LOCAL_RATE_MBPS)
    if LOCAL_DURATION is not None:
        args.duration = float(LOCAL_DURATION)
    if LOCAL_SUITES:
        suites_to_run = [s for s in LOCAL_SUITES if s in [x["name"] for x in SUITES]]
    if LOCAL_MAX_SUITES:
        suites_to_run = suites_to_run[: int(LOCAL_MAX_SUITES)]

    log(f"Suites to run: {len(suites_to_run)}")

    # Cleanup environment before starting
    cleanup_environment(args.mode_resolved)

    # Initialize components
    scheduler = DroneScheduler(args, suites_to_run)
    # configure logging
    logging.basicConfig(level=logging.INFO)
    scheduler.run_scheduler()

    return 0

if __name__ == "__main__":
    sys.exit(main())
