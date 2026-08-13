#!/usr/bin/env python3
"""
GCS Benchmark Server - sscheduler/sgcs_bench.py
"Operation Chronos v2": Comprehensive E2E MAVProxy Benchmark

This script runs on the GCS (Windows) machine and:
1. Listens for commands from drone on TCP 48080
2. Starts/stops crypto proxies per suite
3. Generates traffic through the tunnel
4. Collects GCS-side metrics (CPU, memory, MAVLink)
5. Returns metrics to drone for consolidation

Usage:
    python -m sscheduler.sgcs_bench [--port 48080]

Network:
    - LAN: 192.168.0.101 (GCS) <-> 192.168.0.105 (Drone)
    - Control: TCP 48080 (listens)
    - Plaintext: UDP 47001/47002
    - MAVLink: UDP 14550/14552
"""

import os
import sys
import time
import json
import uuid
import socket
import signal
import argparse
import threading
import subprocess
import statistics
import logging
import platform
import shutil
import atexit
import re
from pathlib import Path
from datetime import datetime, timezone
from dataclasses import asdict
from typing import Dict, List, Any, Optional, Tuple

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG
from core.suites import get_suite, list_suites
from core.process import ManagedProcess
from core.clock_sync import ClockSync
from core.mavlink_collector import MavLinkMetricsCollector, HAS_PYMAVLINK
# GCS system metrics collection (runtime)
from core.metrics_collectors import SystemCollector
# Comprehensive metrics aggregator (GCS side)
from core.metrics_aggregator import MetricsAggregator
from sscheduler.common import resolve_benchmark_mode
from sscheduler.control_security import get_control_auth_key, verify_request_mac
# NOTE: GCS system resource metrics removed per POLICY REALIGNMENT
# GCS is non-constrained observer; only validation metrics retained

# Import RobustLogger for aggressive append-mode logging
try:
    from core.robust_logger import RobustLogger, SyncTracker
    HAS_ROBUST_LOGGER = True
except ImportError:
    HAS_ROBUST_LOGGER = False
    RobustLogger = None
    SyncTracker = None

# =============================================================================
# Configuration
# =============================================================================

DRONE_HOST = str(CONFIG.get("DRONE_HOST", "192.168.0.102"))
GCS_HOST = str(CONFIG.get("GCS_HOST", "192.168.0.101"))
GCS_CONTROL_HOST = str(CONFIG.get("GCS_CONTROL_HOST", "0.0.0.0"))
GCS_CONTROL_PORT = int(CONFIG.get("GCS_CONTROL_PORT", 48080))

GCS_PLAIN_TX_PORT = int(CONFIG.get("GCS_PLAINTEXT_TX", 47001))
GCS_PLAIN_RX_PORT = int(CONFIG.get("GCS_PLAINTEXT_RX", 47002))
DRONE_PLAIN_RX_PORT = int(CONFIG.get("DRONE_PLAINTEXT_RX", 47004))

MAVLINK_SNIFF_PORT = int(CONFIG.get("MAVLINK_SNIFF_GCS", 14552))
MAVLINK_INPUT_PORT = GCS_PLAIN_RX_PORT  # MAVProxy input from proxy (47002)
QGC_PORT = 14550            # Output for QGC/Local tools

SECRETS_DIR = Path(__file__).parent.parent / "secrets" / "matrix"
ROOT = Path(__file__).parent.parent
# Note: LOGS_DIR is now set dynamically when drone sends run_id
# to ensure consistent log directory between GCS and drone
_LOGS_DIR_BASE = ROOT / "logs" / "benchmarks"
LOGS_DIR: Path = None  # Set dynamically in GcsBenchmarkServer

PAYLOAD_SIZE = 1200
DEFAULT_RATE_MBPS = 110.0

# MAVProxy configuration
MAVPROXY_ENABLE_GUI = True  # Enable --map and --console

# =============================================================================
# Logging Setup
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] [sgcs-bench] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%dT%H:%M:%SZ'
)
logger = logging.getLogger("sgcs_bench")

def log(msg: str, level: str = "INFO"):
    getattr(logger, level.lower(), logger.info)(msg)

# =============================================================================
# Environment Info
# =============================================================================

def get_kernel_version() -> str:
    """Get kernel/OS version."""
    try:
        return platform.platform()
    except Exception:
        return "unknown"

def get_python_env() -> str:
    """Get Python environment info."""
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

# =============================================================================
# MAVProxy Manager (GCS side with GUI)
# =============================================================================

class GcsMavProxyManager:
    """
    Manages MAVProxy subprocess on GCS side with optional GUI (--map --console).
    
    MAVProxy receives telemetry from the crypto proxy on UDP 14550
    and outputs to UDP 14552 for sniffing/validation.
    """
    
    def __init__(self, logs_dir: Path, enable_gui: bool = MAVPROXY_ENABLE_GUI):
        self.logs_dir = logs_dir
        self.enable_gui = enable_gui
        self.process: Optional[ManagedProcess] = None
        self._log_handle = None
    
    def start(self) -> bool:
        """Start MAVProxy with map and console if enabled."""
        if self.process and self.process.is_running():  # BUG-08 fix: was poll()
            log("[MAVPROXY] Already running")
            return True
        
        # Build command. Prefer module invocation when mavproxy.py script is
        # not present (common on Linux venv installs).
        if platform.system() == "Windows":
            cmd = [
                sys.executable, "-m", "MAVProxy.mavproxy",
                f"--master=udpin:127.0.0.1:{MAVLINK_INPUT_PORT}",
                "--dialect=ardupilotmega",
                "--nowait",
                f"--out=udp:127.0.0.1:{QGC_PORT}",
            ]
        else:
            mavproxy_bin = shutil.which("mavproxy.py")
            if mavproxy_bin:
                cmd = [
                    mavproxy_bin,
                    f"--master=udpin:127.0.0.1:{MAVLINK_INPUT_PORT}",
                    "--dialect=ardupilotmega",
                    "--nowait",
                    f"--out=udp:127.0.0.1:{QGC_PORT}",
                ]
            else:
                cmd = [
                    sys.executable, "-m", "MAVProxy.mavproxy",
                    f"--master=udpin:127.0.0.1:{MAVLINK_INPUT_PORT}",
                    "--dialect=ardupilotmega",
                    "--nowait",
                    f"--out=udp:127.0.0.1:{QGC_PORT}",
                ]
        
        if self.enable_gui:
            cmd.extend(["--map", "--console"])
            log("[MAVPROXY] Starting with GUI (map + console)")
        else:
            cmd.append("--daemon")
            log("[MAVPROXY] Starting headless (--daemon)")
        
        try:
            # Log file for MAVProxy output (only used in headless mode)
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            log_path = self.logs_dir / f"mavproxy_gcs_{timestamp}.log"
            
            # BUG-09 fix: actually open the log file for headless mode
            if not self.enable_gui:
                try:
                    self._log_handle = open(log_path, "w", encoding="utf-8")
                except Exception:
                    self._log_handle = subprocess.DEVNULL
            
            # Start MAVProxy - always use new_console on Windows
            # because prompt_toolkit requires a Windows console buffer.
            # CRITICAL: stdout/stderr MUST be None when new_console=True,
            # otherwise the file handles override the console screen buffer
            # and prompt_toolkit still fails with NoConsoleScreenBufferError.
            # The --daemon flag suppresses interactive prompts in headless mode.
            self.process = ManagedProcess(
                cmd=cmd,
                name="mavproxy-gcs",
                stdin=None if sys.platform == "win32" else subprocess.DEVNULL,
                stdout=None,
                stderr=None,
                new_console=True  # Always needed on Windows for prompt_toolkit
            )
            
            if self.process.start():
                log(f"[MAVPROXY] Started (PID: {self.process.process.pid})")
                return True
            else:
                log("[MAVPROXY] Failed to start ManagedProcess")
                return False
            
        except FileNotFoundError:
            log("[MAVPROXY] mavproxy.py not found in PATH")
            return False
        except Exception as e:
            log(f"[MAVPROXY] Failed to start: {e}")
            return False
    
    def stop(self):
        """Stop MAVProxy."""
        if self.process:
            self.process.stop()
            self.process = None
            log("[MAVPROXY] Stopped")
        
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None
    
    def is_running(self) -> bool:
        return self.process is not None and self.process.is_running()


# =============================================================================
# GCS System Metrics - REMOVED PER POLICY REALIGNMENT
# =============================================================================
# Justification: GCS is non-constrained. CPU/memory/thread metrics do NOT
# influence policy decisions, suite ranking, or scheduler choices.
# Collecting them adds overhead without policy value.
# =============================================================================

class GcsSystemMetricsCollector:
    """Collects GCS system metrics during a suite run."""

    def __init__(self, sample_interval_s: float = 0.5):
        self._collector = SystemCollector()
        self._interval = sample_interval_s
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._samples: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._samples = []

        def loop():
            while self._running:
                sample = self._collector.collect()
                with self._lock:
                    self._samples.append(sample)
                time.sleep(self._interval)

        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self) -> Dict[str, Any]:
        if not self._running:
            return {}
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)

        with self._lock:
            samples = list(self._samples)

        if not samples:
            return {}

        def _numeric(values: List[Any]) -> List[float]:
            return [v for v in values if isinstance(v, (int, float))]

        cpu_vals = _numeric([s.get("cpu_percent") for s in samples])
        last = samples[-1]

        return {
            "cpu_usage_avg_percent": sum(cpu_vals) / len(cpu_vals) if cpu_vals else None,
            "cpu_usage_peak_percent": max(cpu_vals) if cpu_vals else None,
            "cpu_freq_mhz": last.get("cpu_freq_mhz"),
            "memory_rss_mb": last.get("memory_rss_mb"),
            "memory_vms_mb": last.get("memory_vms_mb"),
            "thread_count": last.get("thread_count"),
            "temperature_c": last.get("temperature_c"),
            "uptime_s": last.get("uptime_s"),
            "load_avg_1m": last.get("load_avg_1m"),
            "load_avg_5m": last.get("load_avg_5m"),
            "load_avg_15m": last.get("load_avg_15m"),
        }
# REMOVED METRICS:
#   - cpu_avg_percent
#   - cpu_peak_percent  
#   - memory_rss_mb
#   - thread_count
# =============================================================================

# =============================================================================
# MAVLink Metrics Collector (GCS side)
# =============================================================================

class GcsMavLinkCollector:
    """
    Collects MAVLink validation metrics on GCS side via pymavlink.
    
    POLICY REALIGNMENT: Only validation-critical metrics retained:
      - total_msgs_received: Cross-side correlation
      - seq_gap_count: MAVLink integrity validation
    
    REMOVED (non-essential):
      - msg_type_counts histogram
      - heartbeat_interval_ms statistics
    """
    
    def __init__(self, listen_port: int = MAVLINK_SNIFF_PORT):
        self.listen_port = listen_port
        self._conn = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # VALIDATION-ONLY counters
        self._total_rx = 0
        self._seq_gaps = 0
        self._last_seq: Dict[int, int] = {}
        
        self._mavutil = None
        try:
            from pymavlink import mavutil
            self._mavutil = mavutil
        except ImportError:
            log("[MAVLINK] pymavlink not available")
    
    def start(self):
        """Start listening for MAVLink messages."""
        if not self._mavutil:
            return False
        
        try:
            self._conn = self._mavutil.mavlink_connection(
                f"udpin:0.0.0.0:{self.listen_port}",
                source_system=255
            )
            self._running = True
            self._thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._thread.start()
            log(f"[MAVLINK] Listening on UDP {self.listen_port}")
            return True
        except Exception as e:
            log(f"[MAVLINK] Failed to start: {e}")
            return False
    
    def _listen_loop(self):
        while self._running:
            try:
                msg = self._conn.recv_match(blocking=True, timeout=1.0)
                if msg:
                    self._process_message(msg)
            except Exception:
                if self._running:
                    pass
    
    def _process_message(self, msg):
        """Process MAVLink message - validation metrics only."""
        with self._lock:
            self._total_rx += 1
            
            # Sequence gap detection for integrity validation
            if hasattr(msg, '_header'):
                sysid = msg._header.srcSystem
                seq = msg._header.seq
                if sysid in self._last_seq:
                    expected = (self._last_seq[sysid] + 1) % 256
                    if seq != expected:
                        self._seq_gaps += 1
                self._last_seq[sysid] = seq
    
    def stop(self) -> Dict[str, Any]:
        """Stop and return validation metrics only."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        
        with self._lock:
            # VALIDATION-ONLY output
            return {
                "total_msgs_received": self._total_rx,
                "seq_gap_count": self._seq_gaps,
            }
    
    def reset(self):
        """Reset counters for new suite."""
        with self._lock:
            self._total_rx = 0
            self._seq_gaps = 0
            self._last_seq = {}

# =============================================================================
# GCS Proxy Manager
# =============================================================================


def _resolve_matrix_key_path(suite_name: str, filename: str) -> Optional[Path]:
    """Resolve canonical suite keys against canonical or legacy matrix dirs."""
    suite = get_suite(suite_name) or {}
    kem_token = str(suite.get("kem_token", "") or "")
    sig_token = str(suite.get("sig_token", "") or "")
    candidates = [SECRETS_DIR / suite_name / filename]
    if kem_token and sig_token:
        for entry in sorted(SECRETS_DIR.glob(f"cs-{kem_token}-*-{sig_token}")):
            candidates.append(entry / filename)
    seen = set()
    for candidate in candidates:
        candidate_str = str(candidate)
        if candidate_str in seen:
            continue
        seen.add(candidate_str)
        if candidate.exists():
            return candidate
    return None

class GcsProxyManager:
    """Manages GCS proxy subprocess."""
    
    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        self.managed_proc: Optional[ManagedProcess] = None
        self.current_suite: Optional[str] = None
        self._log_handle = None
        self._rekey_mode: bool = False
    
    def start(self, suite_name: str, rekey_mode: bool = False) -> bool:
        """Start proxy with given suite."""
        # In rekey mode, keep existing proxy alive for in-band rekey.
        if rekey_mode and self.managed_proc and self.managed_proc.is_running():
            self.current_suite = suite_name
            self._rekey_mode = True
            return True
        if self.managed_proc and self.managed_proc.is_running():
            self.stop()
        
        suite = get_suite(suite_name)
        if not suite:
            log(f"Unknown suite: {suite_name}")
            return False
        
        gcs_key = _resolve_matrix_key_path(suite_name, "gcs_signing.key")
        
        if not gcs_key:
            log(f"Missing key for suite: {suite_name} (gcs_signing.key)")
            return False
        
        cmd = [
            sys.executable, "-m", "core.run_proxy", "gcs",
            "--suite", suite_name,
            "--gcs-secret-file", str(gcs_key),
            "--quiet",
            "--status-file", str(self.logs_dir / "gcs_status.json")
        ]
        # In-band rekey mode: tell the GCS proxy that the drone is the
        # coordinator so it responds to prepare_rekey control messages.
        if rekey_mode:
            cmd.insert(cmd.index("--quiet"), "--enable-tcp-control")
            cmd.extend(["--coordinator-role", "drone"])
            self._rekey_mode = True
        
        def _make_log_handle(suffix: str = "") -> Tuple[Path, Any]:
            timestamp = time.strftime("%Y%m%d-%H%M%S")
            safe_suffix = f"_{suffix}" if suffix else ""
            path = self.logs_dir / f"gcs_proxy_{suite_name}_{timestamp}{safe_suffix}.log"
            return path, open(path, "w", encoding="utf-8")

        def _should_retry_ephemeral(path: Path) -> bool:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                return False
            tail = text[-8192:]
            return (
                "Loaded GCS signing identity does not match the configured public key" in tail
                or "oqs build may not support reloading persistent secret keys safely" in tail
            )

        def _with_ephemeral(cmd_in: List[str]) -> List[str]:
            if "--ephemeral" in cmd_in:
                return list(cmd_in)
            try:
                idx = cmd_in.index("--quiet")
            except ValueError:
                return [*cmd_in, "--ephemeral"]
            return [*cmd_in[:idx], "--ephemeral", *cmd_in[idx:]]

        log_path, self._log_handle = _make_log_handle()
        
        # Ensure subprocess can find 'core' package
        env = os.environ.copy()
        project_root = str(Path(__file__).parent.parent.absolute())
        existing_pp = env.get("PYTHONPATH", "")
        if project_root not in existing_pp:
            sep = ";" if sys.platform.startswith("win") else ":"
            env["PYTHONPATH"] = f"{project_root}{sep}{existing_pp}" if existing_pp else project_root

        self.managed_proc = ManagedProcess(
            cmd=cmd,
            name=f"gcs-proxy-{suite_name}",
            cwd=project_root,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            env=env
        )
        
        if self.managed_proc.start():
            self.current_suite = suite_name
            time.sleep(2.0)
            if not self.managed_proc.is_running():
                # Some OQS builds can fail to reload persistent secret keys safely.
                # core.run_proxy suggests --ephemeral for that exact scenario.
                try:
                    if self._log_handle and not self._log_handle.closed:
                        self._log_handle.flush()
                        self._log_handle.close()
                except Exception:
                    pass
                self._log_handle = None

                if "--ephemeral" not in cmd and _should_retry_ephemeral(log_path):
                    log(f"Proxy exited early for {suite_name}; retrying with --ephemeral")
                    cmd2 = _with_ephemeral(cmd)
                    _log_path2, self._log_handle = _make_log_handle("ephemeral")
                    self.managed_proc = ManagedProcess(
                        cmd=cmd2,
                        name=f"gcs-proxy-{suite_name}",
                        cwd=project_root,
                        stdout=self._log_handle,
                        stderr=subprocess.STDOUT,
                        env=env,
                    )
                    if self.managed_proc.start():
                        self.current_suite = suite_name
                        time.sleep(2.0)
                        if self.managed_proc.is_running():
                            log(f"GCS proxy started for {suite_name} (ephemeral)")
                            return True

                log(f"Proxy exited early for {suite_name}")
                return False
            log(f"GCS proxy started for {suite_name}")
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
# Control Server
# =============================================================================

class GcsBenchmarkServer:
    """
    GCS benchmark server - listens for drone commands.
    
    Commands:
        ping: Check if server is ready
        get_info: Return GCS environment info
        prepare_rekey: Stop current proxy
        start_proxy: Start proxy for suite
        start_traffic: Start traffic generation
        stop_suite: Stop suite and return metrics
        shutdown: Graceful shutdown
    """
    
    def __init__(self, logs_dir: Path, run_id: str, enable_gui: bool = True, mode: str = "MAVPROXY"):
        global LOGS_DIR
        
        self.run_id = run_id
        self.mode = mode
        self._active_run_id = run_id  # Track the active run_id from drone
        
        # BUG-16 fix: honor the run-specific logs_dir passed from main().
        # Keep LOGS_DIR pointed at the active run folder so other code sees the same path.
        LOGS_DIR = logs_dir
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.logs_dir = LOGS_DIR
        self._logs_base_dir = self.logs_dir.parent
        
        # Components
        self.proxy = GcsProxyManager(self.logs_dir)
        self.mavproxy = GcsMavProxyManager(self.logs_dir, enable_gui=enable_gui)
        # mavlink_monitor is set per-suite in start_proxy handler,
        # sharing the aggregator's mavlink_collector to avoid duplicate port binding.
        self.mavlink_monitor = None
        self.mavlink_available = HAS_PYMAVLINK
        self._chronos_offset = None  # stored for re-application after suite reset
        self.clock_sync = ClockSync(
            smoothing=bool(CONFIG.get("CLOCK_SYNC_SMOOTHING", False)),
            window=int(CONFIG.get("CLOCK_SYNC_WINDOW", 3)),
        )
        self.system_metrics = GcsSystemMetricsCollector()
        self.metrics_aggregator = MetricsAggregator(
            role="gcs",
            output_dir=str(self.logs_dir / "comprehensive")
        )
        self.metrics_aggregator.set_run_id(run_id)
        
        # Initialize sync tracker and robust logger (aggressive append-mode)
        self.sync_tracker = None
        self.robust_logger = None
        if HAS_ROBUST_LOGGER:
            try:
                self.sync_tracker = SyncTracker()
                self.robust_logger = RobustLogger(
                    run_id=run_id,
                    role="gcs",
                    base_dir=self._logs_base_dir,
                    sync_tracker=self.sync_tracker,
                )
                log("RobustLogger initialized for aggressive append-mode logging")
            except Exception as e:
                log(f"RobustLogger init failed: {e}", "WARN")
        
        # Server state
        self.server_sock: Optional[socket.socket] = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        
        # Current suite state
        self.current_suite: Optional[str] = None
        self.handshake_start_time = 0.0
        self.suite_log = self.logs_dir / "gcs_suite_metrics.jsonl"
        self._suite_activation_error: str = ""
        self._suite_handshake_ok: bool = False

        self._handshake_timeout_s = 45.0
        self._shutdown_reason: Optional[str] = None
        self._shutdown_error: bool = False
        self._cleanup_done: bool = False

        raw_allowed = CONFIG.get("MAV_ALLOWED_SENDERS", [])
        allowed_senders: List[str] = []
        if isinstance(raw_allowed, str):
            allowed_senders = [p.strip() for p in raw_allowed.split(",") if p.strip()]
        elif isinstance(raw_allowed, (list, tuple, set)):
            allowed_senders = [str(p).strip() for p in raw_allowed if str(p).strip()]

        # Default to DRONE_HOST-only allowlist unless explicitly widened.
        if DRONE_HOST and DRONE_HOST not in allowed_senders:
            allowed_senders.append(DRONE_HOST)

        self.allowed_senders = allowed_senders
        self._auth_key = get_control_auth_key()
        self.require_auth = True
        self.allow_unauth_ping = True
        self.max_request_bytes = 64 * 1024
        self.nonce_ttl_s = 120.0
        self._nonce_lock = threading.Lock()
        self._seen_nonces_expiry: Dict[str, float] = {}

    def _mavlink_live_log_path(self, suite: str) -> Path:
        safe_suite = re.sub(r"[^A-Za-z0-9_.-]+", "_", suite or "unknown")
        return self.logs_dir / f"mavlink_sniff_live_{safe_suite}.jsonl"

    def _start_mavlink_live_export(self, suite: str) -> None:
        if not self.mavlink_monitor:
            return
        try:
            self.mavlink_monitor.start_live_export(
                str(self._mavlink_live_log_path(suite)),
                interval_s=1.0,
                recent_messages=20,
                context={
                    "role": "gcs",
                    "run_id": self._active_run_id or self.run_id,
                    "suite": suite,
                    "mode": self.mode,
                },
            )
        except Exception as exc:
            log(f"Failed to start MAVLink live export for {suite}: {exc}", "WARN")

    def _reset_suite_runtime_state(self, suite: Optional[str] = None) -> None:
        self.current_suite = suite
        self.handshake_start_time = 0.0
        self._suite_activation_error = ""
        self._suite_handshake_ok = False

    def _abort_suite_activation(self, suite: str, reason: str) -> dict:
        log(f"Suite activation failed on GCS for {suite}: {reason}", "WARN")
        self._suite_activation_error = reason
        self._suite_handshake_ok = False
        try:
            if self.mavlink_monitor:
                try:
                    self.mavlink_monitor.stop_rtt_probe()
                except Exception:
                    pass
                self.mavlink_monitor.stop()
        except Exception:
            pass
        try:
            self.system_metrics.stop()
        except Exception:
            pass
        try:
            self.proxy.stop()
        except Exception:
            pass
        if self.metrics_aggregator:
            try:
                self.metrics_aggregator.record_handshake_end(success=False, failure_reason=reason)
            except Exception:
                pass
            try:
                self.metrics_aggregator.finalize_suite()
            except Exception:
                pass
        if self.robust_logger:
            try:
                self.robust_logger.end_suite(success=False, error=reason)
            except Exception:
                pass
        self._reset_suite_runtime_state(None)
        return {"status": "error", "message": reason, "suite": suite}

    def _current_suite_status_payload(self) -> dict:
        proxy_status = self._read_proxy_status()
        mavlink_validation = {"total_msgs_received": 0, "seq_gap_count": 0}
        link_status = {
            "state": "idle",
            "stream_active": False,
            "heartbeat_present": False,
        }
        if self.mavlink_monitor:
            try:
                mav = self.mavlink_monitor.get_metrics()
                mavlink_validation = {
                    "total_msgs_received": mav.get("total_msgs_received", 0),
                    "seq_gap_count": mav.get("seq_gap_count", 0),
                }
                link_status = mav.get("link_status") or link_status
            except Exception:
                pass
        return {
            "status": "ok",
            "suite": self.current_suite,
            "handshake_ok": self._suite_handshake_ok,
            "activation_error": self._suite_activation_error,
            "proxy_status": proxy_status,
            "mavlink_validation": mavlink_validation,
            "link_status": link_status,
        }
    
    def _update_run_id(self, new_run_id: str):
        """Update log directory when drone sends its run_id."""
        global LOGS_DIR
        
        if new_run_id == self._active_run_id:
            return  # No change needed
        
        log(f"Updating run_id from {self._active_run_id} to {new_run_id}")
        self._active_run_id = new_run_id
        
        # Update LOGS_DIR
        LOGS_DIR = self._logs_base_dir / str(new_run_id)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        self.logs_dir = LOGS_DIR
        
        # Reinitialize components with new directory
        # BUG-03 fix: stop old proxy before creating a new one
        if self.proxy:
            try:
                self.proxy.stop()
            except Exception:
                pass
        self.proxy = GcsProxyManager(self.logs_dir)
        self.suite_log = self.logs_dir / "gcs_suite_metrics.jsonl"
        
        # Reinitialize metrics aggregator
        self.metrics_aggregator = MetricsAggregator(
            role="gcs",
            output_dir=str(self.logs_dir / "comprehensive")
        )
        self.metrics_aggregator.set_run_id(new_run_id)
        
        # Reinitialize robust logger
        if HAS_ROBUST_LOGGER:
            try:
                if self.robust_logger:
                    self.robust_logger.stop()
                self.robust_logger = RobustLogger(
                    run_id=new_run_id,
                    role="gcs",
                    base_dir=self._logs_base_dir,
                    sync_tracker=self.sync_tracker,
                )
            except Exception as e:
                log(f"RobustLogger reinit failed: {e}", "WARN")
    
    def start(self):
        """Start the benchmark server."""
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((GCS_CONTROL_HOST, GCS_CONTROL_PORT))
        self.server_sock.listen(5)
        self.server_sock.settimeout(1.0)
        
        self.running = True
        self.thread = threading.Thread(target=self._server_loop, daemon=True)
        self.thread.start()
        
        # Start MAVProxy in either GUI or headless mode. Headless runs are still
        # valid MAV-to-MAV benchmarks and should not skip the GCS MAVProxy path.
        if not self.mavproxy.start():
            log("[WARNING] MAVProxy failed to start - continuing without it")
        if self.mode == "MAVPROXY" and not self.mavproxy.is_running():
            self._shutdown_reason = "error: mavproxy_not_running"
            self._shutdown_error = True
            log("MAVProxy mode requires MAVProxy to be running; aborting", "ERROR")
            self.shutdown(self._shutdown_reason, error=True)
            return
        
        log(f"GCS Benchmark Server listening on {GCS_CONTROL_HOST}:{GCS_CONTROL_PORT}")
        log(f"Run ID: {self.run_id}")
    
    def _server_loop(self):
        while self.running:
            try:
                client, addr = self.server_sock.accept()
                log(f"Connection from {addr}")
                t = threading.Thread(target=self._handle_client, args=(client, addr), daemon=True)
                t.start()
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    log(f"Server error: {e}")
    
    def _handle_client(self, client: socket.socket, addr: Tuple[str, int]):
        """Handle one or more commands on a persistent TCP connection."""
        try:
            client.settimeout(120.0)
            peer_ip = None
            try:
                peer_ip = str(addr[0])
            except Exception:
                peer_ip = None
            if self.allowed_senders and peer_ip not in self.allowed_senders:
                log(f"Rejected sender {peer_ip} (not in allowlist)", "WARN")
                return
            buf = b""
            while self.running:
                try:
                    chunk = client.recv(4096)
                    if not chunk:
                        break  # client disconnected
                    buf += chunk

                    if len(buf) > self.max_request_bytes:

                        client.sendall(json.dumps({"status": "error", "message": "request_too_large"}).encode() + b"\n")

                        return
                    # Process all complete newline-delimited messages in buffer
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        if not line.strip():
                            continue
                        try:
                            request = json.loads(line.decode().strip())
                            cmd = request.get("cmd", "")
                            if not (cmd == "ping" and self.allow_unauth_ping):
                                if self.require_auth:
                                    if not self._auth_key:
                                        client.sendall(json.dumps({"status": "error", "message": "auth_not_configured"}).encode() + b"\n")
                                        continue
                                    nonce = request.get("nonce")
                                    mac = request.get("mac")
                                    if not nonce or not mac:
                                        client.sendall(json.dumps({"status": "error", "message": "auth_required"}).encode() + b"\n")
                                        continue
                                    params = {k: v for k, v in request.items() if k not in ("cmd", "nonce", "mac")}
                                    if not verify_request_mac(cmd=cmd, params=params, nonce_hex=str(nonce), mac_hex=str(mac), key=self._auth_key):
                                        client.sendall(json.dumps({"status": "error", "message": "auth_failed"}).encode() + b"\n")
                                        continue
                                    now = time.monotonic()
                                    nonce_hex = str(nonce)
                                    with self._nonce_lock:
                                        expired = [n for n, exp in self._seen_nonces_expiry.items() if exp <= now]
                                        for n in expired:
                                            del self._seen_nonces_expiry[n]
                                        if nonce_hex in self._seen_nonces_expiry:
                                            client.sendall(json.dumps({"status": "error", "message": "replay"}).encode() + b"\n")
                                            continue
                                        self._seen_nonces_expiry[nonce_hex] = now + self.nonce_ttl_s
                            response = self._handle_command(request)
                            client.sendall(json.dumps(response).encode() + b"\n")
                        except json.JSONDecodeError:
                            client.sendall(json.dumps({"status": "error", "message": "invalid json"}).encode() + b"\n")
                except socket.timeout:
                    continue  # keep connection alive, wait for more commands
                except (ConnectionResetError, BrokenPipeError, OSError):
                    break
        except Exception as e:
            log(f"Client error: {e}")
        finally:
            try:
                client.close()
            except Exception:
                pass
    
    def _handle_command(self, request: dict) -> dict:
        cmd = request.get("cmd", "")
        
        if cmd == "ping":
            return {
                "status": "ok",
                "message": "pong",
                "role": "gcs_benchmark",
                "run_id": self.run_id,
            }
        
        elif cmd == "get_info":
            return {
                "status": "ok",
                "hostname": socket.gethostname(),
                "ip": GCS_HOST,
                "kernel_version": get_kernel_version(),
                "python_env": get_python_env(),
            }

        elif cmd == "get_suite_status":
            requested_suite = request.get("suite")
            if requested_suite and self.current_suite and requested_suite != self.current_suite:
                return {
                    "status": "error",
                    "message": "suite_mismatch",
                    "requested_suite": requested_suite,
                    "current_suite": self.current_suite,
                }
            if requested_suite and not self.current_suite:
                return {
                    "status": "error",
                    "message": "no_active_suite",
                    "requested_suite": requested_suite,
                }
            return self._current_suite_status_payload()
        
        elif cmd == "prepare_rekey":
            log("CMD: prepare_rekey")
            # Stop proxy
            self.proxy.stop()
            self._reset_suite_runtime_state(None)
            
            return {"status": "ok"}
        
        elif cmd == "start_proxy":
            suite = request.get("suite")
            if not suite:
                return {"status": "error", "message": "missing suite parameter"}
            
            # Check if drone sent a run_id - use it to sync log directories
            drone_run_id = request.get("run_id")
            if drone_run_id and drone_run_id != self._active_run_id:
                self._update_run_id(drone_run_id)
            
            log(f"CMD: start_proxy({suite})")
            self._reset_suite_runtime_state(suite)
            
            # Start robust logging for this suite
            if self.robust_logger:
                suite_config = get_suite(suite)
                self.robust_logger.start_suite(suite, suite_config)
                self.robust_logger.log_event("suite_started_from_drone", {
                    "suite": suite,
                    "drone_run_id": drone_run_id,
                })
            
            # Reset MAVLink validation counters per suite by restarting collector
            # NOTE: We no longer create a separate mavlink_monitor here.
            # The aggregator's start_suite() will handle sniffing via its own
            # mavlink_collector.  Creating a second listener on the same port
            # causes one to silently fail (only one UDP socket can bind a port).
            if self.mavlink_monitor:
                try:
                    self.mavlink_monitor.stop()
                except Exception:
                    pass
            self.mavlink_monitor = None  # will be set after start_suite

            # Start GCS system sampling
            self.system_metrics.start()
            
            # Record suite start + handshake start (monotonic)
            suite_config = get_suite(suite)
            self.metrics_aggregator.start_suite(suite, suite_config)
            self.metrics_aggregator.record_handshake_start()
            self.metrics_aggregator.record_control_plane_metrics(
                scheduler_action_type=cmd,
                scheduler_action_reason="command",
                policy_name="GcsBenchmarkServer",
                policy_state="ACTIVE",
            )

            # Share the aggregator's mavlink_collector as our monitor so
            # stop_suite reads from the same instance that is actively sniffing.
            self.mavlink_monitor = self.metrics_aggregator.mavlink_collector

            # Propagate Chronos clock offset to the (reset) collector so
            # OWL can be computed even without GPS-derived SYSTEM_TIME.
            if self._chronos_offset is not None and self.mavlink_monitor is not None:
                self.mavlink_monitor.set_clock_offset(self._chronos_offset)
            self._start_mavlink_live_export(suite)
            self.handshake_start_time = time.time()
            
            # Ensure MAVProxy is running in both GUI and headless MAVProxy mode.
            if not self.mavproxy.is_running():
                log("[MAVPROXY] Restarting crashed/stopped MAVProxy instance...")
                self.mavproxy.start()
                if self.mode == "MAVPROXY" and not self.mavproxy.is_running():
                    return self._abort_suite_activation(suite, "mavproxy_not_running")
            
            # Start proxy
            rekey_mode = bool(request.get("rekey_mode", False))
            if not self.proxy.start(suite, rekey_mode=rekey_mode):
                return self._abort_suite_activation(suite, "proxy_start_failed")

            # FIX-S1: Wait for proxy to bind TCP port before telling drone "ok".
            # Without this, the drone may attempt TCP connect before GCS proxy
            # is listening, wasting 45s on handshake timeout.
            if not self._wait_for_proxy_listening(timeout_s=10.0):
                log("Proxy failed to reach listening state within 10s", "ERROR")
                self.proxy.stop()
                return self._abort_suite_activation(suite, "proxy_listen_timeout")

            # Record handshake end asynchronously to avoid blocking start_proxy.
            # C4 fix: Capture the current aggregator reference at launch time so
            # that _update_run_id replacing self.metrics_aggregator won't cause
            # the thread to write to a stale or wrong-suite aggregator.
            _launch_aggregator = self.metrics_aggregator
            _launch_suite = suite

            def _await_handshake(agg=_launch_aggregator, s=_launch_suite) -> None:
                if self.current_suite != s:
                    return  # Suite changed; this thread is stale
                if self._wait_for_handshake_ok(timeout_s=self._handshake_timeout_s):
                    if self.current_suite == s:  # Double-check after wait
                        self._suite_handshake_ok = True
                        agg.record_handshake_end(success=True)
                        # WINDOW-ALIGN: reset collector counters so the
                        # counting window starts with the proxy forwarding
                        # loop, not with the pre-handshake start_suite().
                        agg.reset_mavlink_count_window()
                else:
                    if self.current_suite == s:
                        self._suite_activation_error = "handshake_timeout"
                        agg.record_handshake_end(
                            success=False,
                            failure_reason="handshake_timeout"
                        )

            threading.Thread(target=_await_handshake, daemon=True).start()
            
            return {
                "status": "ok",
                "message": "suite_started",
                "suite": suite,
                "handshake_start_time": self.handshake_start_time,
            }
        
        elif cmd == "start_traffic":
            log("CMD: start_traffic")
            return {"status": "error", "message": "traffic_generation_removed"}

        elif cmd == "stop_traffic":
            log("CMD: stop_traffic")
            return {"status": "error", "message": "traffic_generation_removed"}
        
        elif cmd == "collect_metrics":
            # Collect GCS-side metrics for the current suite WITHOUT
            # stopping the proxy.  Used in in_band_rekey mode where the
            # proxy must remain alive for the next rekey negotiation.
            log("CMD: collect_metrics")
            requested_suite = request.get("suite")
            if requested_suite and requested_suite != self.current_suite:
                return {
                    "status": "error",
                    "message": "suite_mismatch",
                    "requested_suite": requested_suite,
                    "current_suite": self.current_suite,
                }
            if not self.current_suite:
                return {"status": "error", "message": "no_active_suite"}

            mavlink_metrics = None
            if self.mavlink_monitor:
                try:
                    self.mavlink_monitor.stop_rtt_probe()
                except Exception:
                    pass
                mavlink_metrics = self.mavlink_monitor.stop()

            system_gcs = self.system_metrics.stop()

            # NOTE: proxy is NOT stopped

            mavlink_validation, latency_metrics, mavlink_observability = self._extract_mavlink_reports(mavlink_metrics)

            gcs_export = self.metrics_aggregator.get_exportable_data()
            payload = {
                "status": "ok",
                "suite": self.current_suite,
                "run_id": self._active_run_id or "",
                "mavlink_validation": mavlink_validation,
                "latency_jitter": latency_metrics,
                "mavlink_observability": mavlink_observability,
                "system_gcs": system_gcs,
                "metrics_export": gcs_export,
            }

            self.metrics_aggregator.record_control_plane_metrics(
                scheduler_action_type=cmd,
                scheduler_action_reason="collect_live",
                policy_name="GcsBenchmarkServer",
                policy_state="ACTIVE",
            )
            self.metrics_aggregator.finalize_suite()

            # R1-FIX: If the drone specifies next_suite, restart GCS-side
            # metrics collection for the upcoming suite immediately.  This
            # ensures GCS metrics (system, MAVLink, latency) are properly
            # segmented per suite without stopping/restarting the proxy.
            next_suite = request.get("next_suite")
            if next_suite:
                log(f"  Restarting GCS metrics for next suite: {next_suite}")
                suite_config = get_suite(next_suite) or {}
                self.metrics_aggregator.start_suite(next_suite, suite_config)
                self.mavlink_monitor = self.metrics_aggregator.mavlink_collector
                if self._chronos_offset is not None and self.mavlink_monitor is not None:
                    self.mavlink_monitor.set_clock_offset(self._chronos_offset)
                self._start_mavlink_live_export(next_suite)
                self.system_metrics.start()
                self._reset_suite_runtime_state(next_suite)

            return payload

        elif cmd == "stop_suite":
            log("CMD: stop_suite")
            requested_suite = request.get("suite")
            if requested_suite and requested_suite != self.current_suite:
                return {
                    "status": "error",
                    "message": "suite_mismatch",
                    "requested_suite": requested_suite,
                    "current_suite": self.current_suite,
                }
            if not self.current_suite:
                return {"status": "error", "message": "no_active_suite"}
            # Collect validation-only MAVLink metrics
            mavlink_metrics = None
            if self.mavlink_monitor:
                try:
                    self.mavlink_monitor.stop_rtt_probe()
                except Exception:
                    pass
                mavlink_metrics = self.mavlink_monitor.stop()

            # Collect GCS system metrics
            system_gcs = self.system_metrics.stop()

            # FIX-M4: Read proxy status BEFORE stopping to capture final counters.
            # The proxy status writer thread flushes every ~100ms. If we stop
            # first, the last 100ms of data-plane counters is lost.
            proxy_status = self._read_proxy_status()

            # Stop proxy AFTER reading its last status
            self.proxy.stop()
            
            mavlink_validation, latency_metrics, mavlink_observability = self._extract_mavlink_reports(mavlink_metrics)

            gcs_export = self.metrics_aggregator.get_exportable_data()
            payload = {
                "status": "ok",
                "suite": self.current_suite,
                "run_id": self._active_run_id or "",
                "mavlink_validation": mavlink_validation,
                "latency_jitter": latency_metrics,
                "mavlink_observability": mavlink_observability,
                "system_gcs": system_gcs,
                "metrics_export": gcs_export,
                "proxy_status": proxy_status,
            }
            
            # Log metrics incrementally using robust logger (AGGRESSIVE LOGGING)
            suite_success = bool(self._suite_handshake_ok or (proxy_status or {}).get("status") in {"handshake_ok", "running"})
            suite_error = self._suite_activation_error
            if self.robust_logger:
                if mavlink_validation:
                    self.robust_logger.log_metrics_incremental("mavlink", mavlink_validation)
                if latency_metrics:
                    self.robust_logger.log_metrics_incremental("latency", latency_metrics)
                if mavlink_observability:
                    self.robust_logger.log_metrics_incremental("mavlink_observability", mavlink_observability)
                if system_gcs:
                    self.robust_logger.log_metrics_incremental("system", system_gcs)
                # End suite in robust logger
                self.robust_logger.end_suite(success=suite_success, error=suite_error)

            self.metrics_aggregator.record_control_plane_metrics(
                scheduler_action_type=cmd,
                scheduler_action_reason="command",
                policy_name="GcsBenchmarkServer",
                policy_state="ADVANCE",
            )
            self.metrics_aggregator.finalize_suite()

            # Write to JSONL with retry (AGGRESSIVE LOGGING)
            for attempt in range(3):
                try:
                    with open(self.suite_log, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(payload) + "\n")
                        fh.flush()
                        os.fsync(fh.fileno())  # BUG-23 fix: use module-level os
                    break
                except Exception as e:
                    if attempt < 2:
                        time.sleep(0.5)
                    else:
                        log(f"Failed to write suite log after 3 attempts: {e}", "WARN")

            self._reset_suite_runtime_state(None)

            return payload
        
        elif cmd == "chronos_sync":
            try:
                resp = self.clock_sync.server_handle_sync(request)
                # Record sync in robust logger
                if self.sync_tracker and self.robust_logger:
                    # Extract offset from response
                    t1 = request.get("t1", 0)
                    t2 = resp.get("t2", 0)
                    t3 = resp.get("t3", 0)
                    if t1 and t2 and t3:
                        # GCS is the server, so we record from its perspective
                        self.robust_logger.log_event("clock_sync_served", {
                            "t1": t1, "t2": t2, "t3": t3,
                        })
                return resp
            except Exception as e:
                return {"status": "error", "message": str(e)}
        
        elif cmd == "set_clock_offset":
            # Drone sends computed Chronos offset so GCS-side
            # MavLinkMetricsCollector can compute OWL without GPS.
            try:
                offset = float(request.get("offset", 0.0))
                self._chronos_offset = offset
                if self.mavlink_monitor is not None:
                    self.mavlink_monitor.set_clock_offset(offset)
                if self.metrics_aggregator is not None:
                    self.metrics_aggregator.set_clock_offset(offset, method="chronos")
                offset_ms = offset * 1000.0
                if self.robust_logger:
                    self.robust_logger.record_sync(offset_ms, method="chronos")
                elif self.sync_tracker:
                    self.sync_tracker.record_sync(offset_ms, method="chronos")
                log(f"Clock offset set from drone: {offset:.6f}s")
                return {"status": "ok", "offset_applied": offset}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        
        elif cmd == "shutdown":
            # Shutdown is executed asynchronously so the client receives
            # a response before sockets/processes are torn down.
            reason = str(request.get("reason", "remote: shutdown") or "remote: shutdown")
            error = bool(request.get("error", False))

            threading.Thread(
                target=self.shutdown,
                args=(reason,),
                kwargs={"error": error},
                daemon=True,
            ).start()

            return {
                "status": "ok",
                "message": "shutting_down",
                "reason": reason,
                "error": error,
            }

        return {"status": "error", "message": f"unknown_cmd: {cmd}"}
    
    def stop(self):
        """Stop the server."""
        if self._cleanup_done:
            return
        # Mark cleanup started immediately to prevent re-entrancy
        self._cleanup_done = True

        log("Shutting down...")
        self.running = False
        
        self.proxy.stop()
        self.mavproxy.stop()
        
        # Stop robust logger (flushes all buffered data)
        if self.robust_logger:
            self.robust_logger.log_event("server_shutdown", {"reason": self._shutdown_reason})
            self.robust_logger.stop()
        
        if self.server_sock:
            self.server_sock.close()
        
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=2.0)
        self._cleanup_done = True

    def shutdown(self, reason: str, *, error: bool) -> None:
        if self._cleanup_done:
            return
        level = "ERROR" if error else "INFO"
        log(f"Shutdown reason: {reason}", level)
        self.stop()

    def _read_proxy_status(self) -> Dict[str, Any]:
        status_path = self.logs_dir / "gcs_status.json"
        if not status_path.exists():
            return {}
        try:
            with open(status_path, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    @staticmethod
    def _extract_mavlink_reports(mavlink_metrics: dict):
        """Extract validation, latency, and observability dicts from collector output.

        FIX-M5: Deduplicated from collect_metrics and stop_suite handlers
        to ensure both paths produce identical metric dictionaries.
        """
        if not mavlink_metrics:
            return None, None, None
        validation = {
            "total_msgs_received": mavlink_metrics.get("total_msgs_received"),
            "seq_gap_count": mavlink_metrics.get("seq_gap_count"),
        }
        latency = {
            "one_way_latency_avg_ms": mavlink_metrics.get("one_way_latency_avg_ms"),
            "one_way_latency_p95_ms": mavlink_metrics.get("one_way_latency_p95_ms"),
            "one_way_latency_valid": mavlink_metrics.get("one_way_latency_valid"),
            "jitter_avg_ms": mavlink_metrics.get("jitter_avg_ms"),
            "jitter_p95_ms": mavlink_metrics.get("jitter_p95_ms"),
            "latency_sample_count": mavlink_metrics.get("latency_sample_count"),
            "latency_invalid_reason": mavlink_metrics.get("latency_invalid_reason"),
            "rtt_avg_ms": mavlink_metrics.get("rtt_avg_ms"),
            "rtt_p95_ms": mavlink_metrics.get("rtt_p95_ms"),
            "rtt_sample_count": mavlink_metrics.get("rtt_sample_count"),
            "rtt_invalid_reason": mavlink_metrics.get("rtt_invalid_reason"),
            "rtt_valid": mavlink_metrics.get("rtt_valid"),
        }
        observability = {
            "link_status": mavlink_metrics.get("link_status"),
            "flight_controller": mavlink_metrics.get("flight_controller"),
            "top_message_types": mavlink_metrics.get("top_message_types"),
            "recent_statustext": mavlink_metrics.get("recent_statustext"),
            "recent_messages": mavlink_metrics.get("recent_messages"),
        }
        return validation, latency, observability


    def _wait_for_proxy_listening(self, timeout_s: float = 10.0) -> bool:
        """Wait for proxy status to show it's listening for TCP handshake.

        FIX-S1: The drone proxy attempts TCP connect immediately after receiving
        'ok' from start_proxy. Without this check, GCS may not have bound
        port 46000 yet, causing a 45s handshake timeout.
        """
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            status = self._read_proxy_status()
            state = status.get("status") if isinstance(status, dict) else None
            if state in {"listening", "handshake_ok", "running"}:
                return True
            time.sleep(0.2)
        return False

    def _wait_for_handshake_ok(self, timeout_s: float = 45.0) -> bool:
        """Wait for proxy status to show handshake completion."""
        deadline = time.monotonic() + float(timeout_s)
        while time.monotonic() < deadline:
            status = self._read_proxy_status()
            state = status.get("status") if isinstance(status, dict) else None
            if state in {"handshake_ok", "running"}:
                return True
            time.sleep(0.2)
        return False

# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    global LOGS_DIR
    parser = argparse.ArgumentParser(description="GCS Benchmark Server - Operation Chronos v2")
    parser.add_argument("--port", type=int, default=GCS_CONTROL_PORT,
                        help=f"Control server port (default: {GCS_CONTROL_PORT})")
    parser.add_argument("--run-id", type=str, default=None,
                        help="Run ID (default: auto-generated)")
    parser.add_argument("--no-gui", action="store_true",
                        help="Disable MAVProxy GUI (map + console)")
    parser.add_argument("--log-dir", type=str,
                        help="Override base log directory for this run")
    parser.add_argument("--mode", type=str,
                        help="Benchmark mode: MAVPROXY")
    args = parser.parse_args()

    # Apply --port override (server.start() binds using module-level GCS_CONTROL_PORT).
    globals()["GCS_CONTROL_PORT"] = int(args.port)


    args.mode_resolved = resolve_benchmark_mode(args.mode, default_mode="MAVPROXY")
    log(f"BENCHMARK_MODE resolved to {args.mode_resolved}")

    if args.log_dir:
        LOGS_DIR = Path(args.log_dir).expanduser().resolve()
    else:
        # Default: use the base logs directory with a timestamped run folder
        LOGS_DIR = _LOGS_DIR_BASE / f"live_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # NOTE: GUI is always enabled for benchmark runs (map + console)
    
    # Generate run ID
    run_id = args.run_id or f"gcs_bench_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    # Create logs directory
    run_logs_dir = LOGS_DIR / run_id
    run_logs_dir.mkdir(parents=True, exist_ok=True)
    
    # Start server
    server = GcsBenchmarkServer(
        logs_dir=run_logs_dir,
        run_id=run_id,
        enable_gui=not args.no_gui,
        mode=args.mode_resolved,
    )

    def _atexit_cleanup():
        try:
            server.shutdown("normal: atexit", error=False)
        except Exception:
            pass

    atexit.register(_atexit_cleanup)
    
    # Handle signals
    def signal_handler(sig, frame):
        log("Interrupt received, stopping...")
        server.shutdown("normal: interrupted", error=False)
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    log("=" * 60)
    log("OPERATION CHRONOS v2: GCS Benchmark Server")
    log("=" * 60)
    log(f"Listening for drone commands...")
    log(f"Press Ctrl+C to stop")
    
    server.start()
    
    # Keep main thread alive
    try:
        while server.running:
            time.sleep(1.0)
    except KeyboardInterrupt:
        log("Stopping...")
        server.shutdown("normal: interrupted", error=False)

if __name__ == "__main__":
    main()











