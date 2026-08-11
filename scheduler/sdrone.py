#!/usr/bin/env python3
from __future__ import annotations
"""Simplified Drone Scheduler - Runs drone proxy with UDP echo for all suites.

This scheduler:
1. Starts the drone proxy for each suite
2. Runs a UDP echo server to reflect traffic back to GCS
3. Accepts rekey commands from GCS scheduler via TCP control
4. Iterates through all available suites on command

No benchmarking, no power monitoring - just robust PQC tunnel operation.
"""

# --------------------
# Local editable configuration (edit here, no CLI args needed)
# Keep this block near the top for quick edits.
# --------------------
LOCAL_CONTROL_HOST = None  # e.g. "127.0.0.1" or None to use config/env
LOCAL_CONTROL_PORT = None  # e.g. 48080 or None to use config

import sys
from pathlib import Path


def _ensure_core_importable() -> Path:
    """Guarantee the repository root is on sys.path before importing core."""
    root = Path(__file__).resolve().parents[1]
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    try:
        __import__("core")
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            f"Unable to import 'core'; repo root {root} missing from sys.path."
        ) from exc
    return root


ROOT = _ensure_core_importable()

import argparse
import json
import os
import signal
import socket
import struct
import subprocess
import threading
import time
from typing import Dict, IO, List, Optional, Tuple

from core.config import CONFIG
from core import suites as suites_mod
from core.suites import DEFAULT_SUITE_ID, get_suite, list_runtime_suites, list_suites

# ---------------------------------------------------------------------------
# Configuration from core.config (same as drone_follower.py)
# ---------------------------------------------------------------------------

_CONTROL_HOST_FALLBACK = CONFIG.get("DRONE_HOST", "127.0.0.1")
CONTROL_HOST = str(
    CONFIG.get("DRONE_CONTROL_HOST")
    or os.getenv("DRONE_CONTROL_HOST")
    or _CONTROL_HOST_FALLBACK
).strip() or str(_CONTROL_HOST_FALLBACK)
CONTROL_PORT = int(CONFIG.get("DRONE_CONTROL_PORT", 48080))

APP_BIND_HOST = CONFIG.get("DRONE_PLAINTEXT_HOST", "127.0.0.1")
APP_RECV_PORT = int(CONFIG.get("DRONE_PLAINTEXT_RX", 47004))
APP_SEND_HOST = CONFIG.get("DRONE_PLAINTEXT_HOST", "127.0.0.1")
APP_SEND_PORT = int(CONFIG.get("DRONE_PLAINTEXT_TX", 47003))

DRONE_HOST = CONFIG["DRONE_HOST"]
GCS_HOST = CONFIG["GCS_HOST"]

SECRETS_DIR = ROOT / "secrets/matrix"
LOGS_DIR = ROOT / "logs/scheduler/drone"

# ---------------------------------------------------------------------------
# Utility Functions
# ---------------------------------------------------------------------------

def ts() -> str:
    """Return ISO timestamp."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def log(msg: str) -> None:
    """Print timestamped log message."""
    print(f"[{ts()}] [sdrone] {msg}", flush=True)


def get_available_suites() -> List[str]:
    """Return list of suite IDs that have keys in secrets/matrix/."""
    available = []
    all_suites = list_runtime_suites()
    
    for suite_id in sorted(all_suites.keys()):
        suite_dir = SECRETS_DIR / suite_id
        pub_file = suite_dir / "gcs_signing.pub"
        if pub_file.exists():
            available.append(suite_id)
    
    return available


def popen(cmd: List[str], **kwargs) -> subprocess.Popen:
    """Launch subprocess with proper flags."""
    if sys.platform == "win32":
        kwargs.setdefault("creationflags", subprocess.CREATE_NEW_PROCESS_GROUP)
    return subprocess.Popen(cmd, **kwargs)


def killtree(proc: subprocess.Popen) -> None:
    """Terminate process tree."""
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                timeout=5,
            )
        else:
            import os as _os
            _os.killpg(_os.getpgid(proc.pid), signal.SIGKILL)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# UDP Echo Server
# ---------------------------------------------------------------------------

class UdpEchoServer(threading.Thread):
    """Simple UDP echo server - reflects all received packets back."""
    
    def __init__(
        self,
        bind_host: str,
        recv_port: int,
        send_host: str,
        send_port: int,
        stop_event: threading.Event,
    ):
        super().__init__(daemon=True)
        self.bind_host = bind_host
        self.recv_port = recv_port
        self.send_host = send_host
        self.send_port = send_port
        self.stop_event = stop_event
        self.rx_count = 0
        self.tx_count = 0
        self.rx_bytes = 0
        self.tx_bytes = 0
        self._lock = threading.Lock()
    
    def run(self) -> None:
        rx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            rx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        except Exception:
            pass
        rx_sock.bind((self.bind_host, self.recv_port))
        rx_sock.settimeout(0.5)
        
        tx_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            tx_sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        except Exception:
            pass
        
        log(f"Echo server listening on {self.bind_host}:{self.recv_port}")
        
        while not self.stop_event.is_set():
            try:
                data, addr = rx_sock.recvfrom(65535)
                with self._lock:
                    self.rx_count += 1
                    self.rx_bytes += len(data)
                
                tx_sock.sendto(data, (self.send_host, self.send_port))
                with self._lock:
                    self.tx_count += 1
                    self.tx_bytes += len(data)
                    
            except socket.timeout:
                continue
            except Exception as e:
                if not self.stop_event.is_set():
                    log(f"Echo error: {e}")
        
        rx_sock.close()
        tx_sock.close()
        log("Echo server stopped")
    
    def get_stats(self) -> Dict[str, int]:
        with self._lock:
            return {
                "rx_count": self.rx_count,
                "tx_count": self.tx_count,
                "rx_bytes": self.rx_bytes,
                "tx_bytes": self.tx_bytes,
            }
    
    def reset_stats(self) -> None:
        with self._lock:
            self.rx_count = 0
            self.tx_count = 0
            self.rx_bytes = 0
            self.tx_bytes = 0


# ---------------------------------------------------------------------------
# TCP Control Server (accepts commands from GCS scheduler)
# ---------------------------------------------------------------------------

class ControlServer(threading.Thread):
    """TCP control server - accepts rekey commands from GCS scheduler."""
    
    def __init__(
        self,
        host: str,
        port: int,
        state: Dict,
        stop_event: threading.Event,
    ):
        super().__init__(daemon=True)
        self.host = host
        self.port = port
        self.state = state
        self.stop_event = stop_event
    
    def run(self) -> None:
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.settimeout(1.0)
        server.bind((self.host, self.port))
        server.listen(5)
        
        log(f"Control server listening on {self.host}:{self.port}")
        
        while not self.stop_event.is_set():
            try:
                conn, addr = server.accept()
                conn.settimeout(10.0)
                threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if not self.stop_event.is_set():
                    log(f"Control server error: {e}")
        
        server.close()
        log("Control server stopped")
    
    def _handle_client(self, conn: socket.socket, addr: Tuple) -> None:
        try:
            data = conn.recv(8192)
            if not data:
                return
            
            try:
                request = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                conn.sendall(json.dumps({"error": "invalid_json"}).encode())
                return
            
            cmd = request.get("cmd", "")
            response = self._handle_command(cmd, request)
            conn.sendall(json.dumps(response).encode())
            
        except Exception as e:
            log(f"Client handler error: {e}")
        finally:
            conn.close()
    
    def _handle_command(self, cmd: str, request: Dict) -> Dict:
        if cmd == "ping":
            return {"status": "ok", "ts": ts()}
        
        elif cmd == "status":
            return {
                "status": "ok",
                "suite": self.state.get("suite"),
                "proxy_running": self.state.get("proxy") is not None and self.state["proxy"].poll() is None,
                "echo_stats": self.state.get("echo").get_stats() if self.state.get("echo") else {},
            }
        
        elif cmd == "start":
            # Start proxy for the first time (GCS already listening)
            suite = request.get("suite") or self.state.get("pending_suite")
            if not suite:
                return {"status": "error", "error": "missing_suite"}
            
            # If proxy already running, stop it first
            old_proxy = self.state.get("proxy")
            if old_proxy and old_proxy.poll() is None:
                log("Stopping current proxy for new start...")
                try:
                    old_proxy.terminate()
                    old_proxy.wait(timeout=5)
                except Exception:
                    killtree(old_proxy)
                
                old_log = self.state.get("log_handle")
                if old_log:
                    try:
                        old_log.close()
                    except Exception:
                        pass
                
                self.state["proxy"] = None
                self.state["log_handle"] = None
                self.state["suite"] = None
                time.sleep(1)
            
            try:
                result = self._do_start(suite)
                return result
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        elif cmd == "prepare_rekey":
            # Stop current proxy in preparation for rekey (GCS will start first)
            log("Prepare rekey: stopping proxy...")
            old_proxy = self.state.get("proxy")
            if old_proxy and old_proxy.poll() is None:
                try:
                    old_proxy.terminate()
                    old_proxy.wait(timeout=5)
                except Exception:
                    killtree(old_proxy)
            
            old_log = self.state.get("log_handle")
            if old_log:
                try:
                    old_log.close()
                except Exception:
                    pass
            
            self.state["proxy"] = None
            self.state["log_handle"] = None
            self.state["suite"] = None
            
            # Reset echo stats
            echo = self.state.get("echo")
            if echo:
                echo.reset_stats()
            
            return {"status": "ok", "message": "ready_for_rekey"}
        
        elif cmd == "rekey":
            new_suite = request.get("suite")
            if not new_suite:
                return {"status": "error", "error": "missing_suite"}
            
            try:
                result = self._do_rekey(new_suite)
                return result
            except Exception as e:
                return {"status": "error", "error": str(e)}
        
        elif cmd == "stop":
            self.stop_event.set()
            return {"status": "ok", "message": "stopping"}
        
        elif cmd == "get_suites":
            return {"status": "ok", "suites": get_available_suites()}
        
        else:
            return {"status": "error", "error": f"unknown_cmd: {cmd}"}
    
    def _do_start(self, suite: str) -> Dict:
        """Start proxy for the first time (GCS must already be listening)."""
        log(f"Start requested for suite: {suite}")
        
        # Validate suite exists
        suite_dir = SECRETS_DIR / suite
        pub_file = suite_dir / "gcs_signing.pub"
        if not pub_file.exists():
            return {"status": "error", "error": f"no_keys_for_suite: {suite}"}
        
        # Check if already running
        old_proxy = self.state.get("proxy")
        if old_proxy and old_proxy.poll() is None:
            return {"status": "error", "error": "proxy_already_running"}
        
        # Reset echo stats
        echo = self.state.get("echo")
        if echo:
            echo.reset_stats()
        
        # Start new proxy
        log(f"Starting proxy with suite {suite}")
        try:
            proc, log_handle = start_drone_proxy(suite)
            self.state["proxy"] = proc
            self.state["log_handle"] = log_handle
            self.state["suite"] = suite
            
            # Wait for handshake
            time.sleep(3)
            
            if proc.poll() is not None:
                return {"status": "error", "error": "proxy_exited_early"}
            
            return {"status": "ok", "suite": suite}
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def _do_rekey(self, new_suite: str) -> Dict:
        """Stop current proxy, start new one with different suite."""
        log(f"Rekey requested: {self.state.get('suite')} -> {new_suite}")
        
        # Validate suite exists
        suite_dir = SECRETS_DIR / new_suite
        pub_file = suite_dir / "gcs_signing.pub"
        if not pub_file.exists():
            return {"status": "error", "error": f"no_keys_for_suite: {new_suite}"}
        
        # Stop current proxy
        old_proxy = self.state.get("proxy")
        if old_proxy and old_proxy.poll() is None:
            log("Stopping current proxy...")
            try:
                old_proxy.terminate()
                old_proxy.wait(timeout=5)
            except Exception:
                killtree(old_proxy)
        
        # Close old log handle
        old_log = self.state.get("log_handle")
        if old_log:
            try:
                old_log.close()
            except Exception:
                pass
        
        # Wait for ports to clear
        time.sleep(1)
        
        # Reset echo stats
        echo = self.state.get("echo")
        if echo:
            echo.reset_stats()
        
        # Start new proxy
        log(f"Starting proxy with suite {new_suite}")
        try:
            proc, log_handle = start_drone_proxy(new_suite)
            self.state["proxy"] = proc
            self.state["log_handle"] = log_handle
            self.state["suite"] = new_suite
            
            # Wait for handshake
            time.sleep(3)
            
            if proc.poll() is not None:
                return {"status": "error", "error": "proxy_exited_early"}
            
            return {"status": "ok", "suite": new_suite}
            
        except Exception as e:
            return {"status": "error", "error": str(e)}


# ---------------------------------------------------------------------------
# Proxy Management
# ---------------------------------------------------------------------------

def start_drone_proxy(suite: str) -> Tuple[subprocess.Popen, IO[str]]:
    """Start drone proxy for the given suite."""
    suite_dir = SECRETS_DIR / suite
    pub_file = suite_dir / "gcs_signing.pub"
    
    if not pub_file.exists():
        raise FileNotFoundError(f"Public key not found: {pub_file}")
    
    # Set environment
    env = os.environ.copy()
    env["DRONE_HOST"] = DRONE_HOST
    env["GCS_HOST"] = GCS_HOST
    env["ENABLE_PACKET_TYPE"] = "1" if CONFIG.get("ENABLE_PACKET_TYPE", True) else "0"
    env["STRICT_UDP_PEER_MATCH"] = "1" if CONFIG.get("STRICT_UDP_PEER_MATCH", True) else "0"
    
    root_str = str(ROOT)
    existing_py_path = env.get("PYTHONPATH")
    if existing_py_path:
        if root_str not in existing_py_path.split(os.pathsep):
            env["PYTHONPATH"] = root_str + os.pathsep + existing_py_path
    else:
        env["PYTHONPATH"] = root_str
    
    # Create log directory
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"drone_{suite}_{time.strftime('%Y%m%d-%H%M%S')}.log"
    log_handle = open(log_path, "w", encoding="utf-8")
    
    cmd = [
        sys.executable,
        "-m", "core.run_proxy",
        "drone",
        "--suite", suite,
        "--peer-pubkey-file", str(pub_file),
        "--quiet",
    ]
    
    log(f"Launching: {' '.join(cmd)}")
    
    proc = popen(
        cmd,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
        cwd=str(ROOT),
    )
    
    return proc, log_handle


# ---------------------------------------------------------------------------
# Main Entry Point
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simplified Drone Scheduler - Run PQC tunnel with all suites"
    )
    parser.add_argument(
        "--suite",
        default=None,
        help="Initial suite (default: first available)",
    )
    parser.add_argument(
        "--control-host",
        default=CONTROL_HOST,
        help=f"Control server bind host (default: {CONTROL_HOST})",
    )
    parser.add_argument(
        "--control-port",
        type=int,
        default=CONTROL_PORT,
        help=f"Control server port (default: {CONTROL_PORT})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    
    print("=" * 60)
    print("Simplified Drone Scheduler (sdrone)")
    print("=" * 60)
    log(f"DRONE_HOST={DRONE_HOST}, GCS_HOST={GCS_HOST}")
    log(f"Control: {args.control_host}:{args.control_port}")
    
    # Get available suites
    available_suites = get_available_suites()
    if not available_suites:
        log("ERROR: No suites with keys found in secrets/matrix/")
        return 1
    
    log(f"Available suites: {len(available_suites)}")
    
    # Determine initial suite
    initial_suite = args.suite
    if initial_suite and initial_suite not in available_suites:
        log(f"WARNING: Suite {initial_suite} not available, using first available")
        initial_suite = None
    if not initial_suite:
        initial_suite = available_suites[0]
    
    log(f"Initial suite: {initial_suite}")
    
    # Setup
    stop_event = threading.Event()
    
    def signal_handler(signum, frame):
        log("Received shutdown signal")
        stop_event.set()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Start echo server
    echo = UdpEchoServer(
        APP_BIND_HOST, APP_RECV_PORT,
        APP_SEND_HOST, APP_SEND_PORT,
        stop_event
    )
    echo.start()
    
    # State dict shared with control server
    # NOTE: Proxy is started on first rekey command from GCS (GCS must start first)
    state = {
        "proxy": None,
        "log_handle": None,
        "suite": None,
        "pending_suite": initial_suite,  # Will start this on first 'start' or 'rekey' command
        "echo": echo,
        "stop_event": stop_event,
    }

    # If LOCAL control overrides are set, update the control server bind values
    if LOCAL_CONTROL_HOST:
        args.control_host = LOCAL_CONTROL_HOST
    if LOCAL_CONTROL_PORT:
        args.control_port = int(LOCAL_CONTROL_PORT)
    
    # Start control server
    control = ControlServer(
        args.control_host,
        args.control_port,
        state,
        stop_event
    )
    control.start()
    
    # Main loop
    log("Drone scheduler running. Waiting for 'start' command from GCS...")
    log("(GCS must start first, then send 'start' or 'rekey' command)")
    
    proxy = None
    try:
        while not stop_event.is_set():
            # Check if proxy is running
            proxy = state.get("proxy")
            if proxy and proxy.poll() is not None:
                log(f"Proxy exited with code {proxy.returncode}")
                state["proxy"] = None
                state["suite"] = None
            
            # Print periodic status
            stats = echo.get_stats()
            if stats["rx_count"] > 0:
                log(f"Echo stats: RX={stats['rx_count']}, TX={stats['tx_count']}, "
                    f"RX_bytes={stats['rx_bytes']:,}, TX_bytes={stats['tx_bytes']:,}")
            
            time.sleep(5)
            
    except KeyboardInterrupt:
        log("Interrupted")
        stop_event.set()
    
    # Cleanup
    log("Shutting down...")
    
    proxy = state.get("proxy")
    if proxy and proxy.poll() is None:
        try:
            proxy.terminate()
            proxy.wait(timeout=5)
        except Exception:
            killtree(proxy)
    
    log_handle = state.get("log_handle")
    if log_handle:
        try:
            log_handle.close()
        except Exception:
            pass
    
    log("Drone scheduler stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
