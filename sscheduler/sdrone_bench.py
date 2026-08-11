#!/usr/bin/env python3
"""
Benchmark Drone Scheduler - sscheduler/sdrone_bench.py

A specialized drone scheduler for comprehensive suite benchmarking.
Cycles through the canonical benchmark matrix on a nominal 10-second dwell,
with readiness gates allowed to extend a suite slightly when metrics are not yet safe to finalize.

Usage:
    python -m sscheduler.sdrone_bench [options]

Options:
    --interval SECS     Suite cycle interval (default: 10)
    --filter-aead AEAD  Only benchmark suites with this AEAD (aesgcm|chacha|ascon)
    --max-suites N      Maximum suites to benchmark
    --dry-run           Print plan without executing
"""

import os
import sys
import time
import json
import socket
import glob
import signal
import argparse
import threading
import subprocess
import logging
import atexit
import statistics
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

_SCHEDULER = None

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG

from core.suites import get_suite, list_suites
from core.process import ManagedProcess
from core.clock_sync import ClockSync
from sscheduler.benchmark_policy import BenchmarkPolicy, BenchmarkAction, get_suite_count
from sscheduler.common import resolve_benchmark_mode, read_handshake_status as _read_handshake_status
from sscheduler.gcs_client import resolve_control_host
from sscheduler.control_security import create_nonce_hex, compute_request_mac, get_control_auth_key

_CONTROL_AUTH_KEY = get_control_auth_key()

# Import MetricsAggregator for comprehensive metrics collection
try:
    from core.metrics_aggregator import MetricsAggregator
    HAS_METRICS_AGGREGATOR = True
except ImportError:
    HAS_METRICS_AGGREGATOR = False
    MetricsAggregator = None

# Import RobustLogger for aggressive append-mode logging
try:
    from core.robust_logger import RobustLogger, SyncTracker
    HAS_ROBUST_LOGGER = True
except ImportError:
    HAS_ROBUST_LOGGER = False
    RobustLogger = None
    SyncTracker = None

# Extract config values
DRONE_HOST = str(CONFIG.get("DRONE_HOST"))
GCS_HOST = str(CONFIG.get("GCS_HOST"))
# For GCS control, resolve the advertised/bind host into a reachable client target.
# Can override with GCS_CONTROL_HOST env var or --gcs-host CLI arg.
GCS_CONTROL_HOST = resolve_control_host(
    os.environ.get("GCS_CONTROL_HOST") or str(CONFIG.get("GCS_CONTROL_HOST", CONFIG.get("GCS_HOST")))
)
GCS_CONTROL_PORT = int(CONFIG.get("GCS_CONTROL_PORT", 48080))
GCS_TELEMETRY_PORT = int(CONFIG.get("GCS_TELEMETRY_PORT", 52080))
DRONE_PLAIN_RX_PORT = int(CONFIG.get("DRONE_PLAINTEXT_RX", 47004))
DRONE_PLAIN_TX_PORT = int(CONFIG.get("DRONE_PLAINTEXT_TX", 47003))

SECRETS_DIR = Path(__file__).parent.parent / "secrets" / "matrix"
ROOT = Path(__file__).resolve().parents[1]
# Note: LOGS_DIR is now set dynamically in BenchmarkScheduler.__init__
# to ensure consistent run_id between drone and GCS
_LOGS_DIR_BASE = ROOT / "logs" / "benchmarks"
LOGS_DIR: Path = None  # Set in BenchmarkScheduler.__init__

# Re-sync clock every N suites or N seconds
CLOCK_SYNC_INTERVAL_SUITES = 10
CLOCK_SYNC_INTERVAL_SECONDS = 1200  # 20 minutes
DEFAULT_REKEY_TIMEOUT_S = float(CONFIG.get("REKEY_HANDSHAKE_TIMEOUT", 45.0))
CLOCK_SYNC_SAMPLE_COUNT = 3
FLOW_READY_TIMEOUT_S = 4.0
FLOW_READY_POLL_S = 0.2
FLOW_READY_CONSECUTIVE_POLLS = 3
FLOW_READY_LOCAL_MIN_PACKETS = 32
FLOW_READY_GCS_MIN_MSGS = 32

# =============================================================================
# Logging
# =============================================================================

def log(msg: str, level: str = "INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prefix = f"[{ts}] [sdrone-bench]"
    if level == "ERROR":
        print(f"{prefix} ERROR: {msg}", flush=True)
    elif level == "WARN":
        print(f"{prefix} WARN: {msg}", flush=True)
    else:
        print(f"{prefix} {msg}", flush=True)

# =============================================================================
# GCS Control Client
# =============================================================================

# Persistent TCP connection pool for GCS control commands.
# Avoids opening a new TCP connection for every ping/command (was ~1/s).
_gcs_persistent_sock: Optional[socket.socket] = None
_gcs_persistent_buf: bytes = b""
_gcs_sock_lock = threading.Lock()

def _get_gcs_sock() -> socket.socket:
    """Return a persistent TCP socket to GCS control server, reconnecting if needed."""
    global _gcs_persistent_sock, _gcs_persistent_buf
    if _gcs_persistent_sock is not None:
        return _gcs_persistent_sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    handshake_timeout = float(CONFIG.get("REKEY_HANDSHAKE_TIMEOUT", 45.0))
    sock.settimeout(max(90.0, handshake_timeout + 15.0))
    sock.connect((resolve_control_host(GCS_CONTROL_HOST), GCS_CONTROL_PORT))
    _gcs_persistent_sock = sock
    _gcs_persistent_buf = b""
    return sock

def _close_gcs_sock():
    """Close the persistent GCS control socket."""
    global _gcs_persistent_sock, _gcs_persistent_buf
    with _gcs_sock_lock:
        if _gcs_persistent_sock is not None:
            try:
                _gcs_persistent_sock.close()
            except Exception:
                pass
            _gcs_persistent_sock = None
            _gcs_persistent_buf = b""

def send_gcs_command(cmd: str, **params) -> dict:
    """Send command to GCS control server using persistent TCP connection."""
    global _gcs_persistent_sock, _gcs_persistent_buf
    with _gcs_sock_lock:
        for attempt in range(2):
            try:
                sock = _get_gcs_sock()

                if cmd == "ping":
                    request = {"cmd": cmd, **params}
                else:
                    if _CONTROL_AUTH_KEY is None:
                        return {"status": "error", "message": "control_auth_key_missing"}
                    nonce = create_nonce_hex()
                    mac = compute_request_mac(cmd=cmd, params=params, nonce_hex=nonce, key=_CONTROL_AUTH_KEY)
                    request = {"cmd": cmd, **params, "nonce": nonce, "mac": mac}

                sock.sendall(json.dumps(request).encode() + b"\n")
                buf = _gcs_persistent_buf
                while b"\n" not in buf:
                    chunk = sock.recv(4096)
                    if not chunk:
                        raise ConnectionError("GCS closed connection")
                    buf = buf + chunk
                line, _sep, rest = buf.partition(b"\n")
                _gcs_persistent_buf = rest
                return json.loads(line.decode().strip() or "{}")
            except Exception as e:
                # Connection broken — close and retry once
                try:
                    if _gcs_persistent_sock is not None:
                        _gcs_persistent_sock.close()
                except Exception:
                    pass
                _gcs_persistent_sock = None
                _gcs_persistent_buf = b""
                if attempt == 0:
                    continue
                return {"status": "error", "message": str(e)}

def wait_for_gcs(timeout: float = 30.0) -> bool:
    """Wait for GCS control server to be ready."""
    start = time.time()
    while time.time() - start < timeout:
        result = send_gcs_command("ping")
        if result.get("status") == "ok":
            return True
        time.sleep(0.5)
    return False


def _select_clock_sync_sample(samples: List[Dict[str, float]]) -> Optional[Dict[str, float]]:
    """Select a representative sample from a short Chronos burst."""
    if not samples:
        return None
    offsets = [float(sample["offset"]) for sample in samples]
    return {
        "offset": statistics.median(offsets),
        "offset_ms": statistics.median(offsets) * 1000.0,
        "rtt_ms_best": min(float(sample["rtt_ms"]) for sample in samples),
        "samples": len(samples),
    }


def _is_live_data_flow_ready(
    local_counters: Dict[str, Any],
    gcs_status: Dict[str, Any],
    *,
    local_min_packets: int = FLOW_READY_LOCAL_MIN_PACKETS,
    gcs_min_msgs: int = FLOW_READY_GCS_MIN_MSGS,
) -> bool:
    """Return True once both local and GCS sides show real packet flow."""
    local_packets = 0
    for key in ("ptx_in", "enc_out", "enc_in", "ptx_out"):
        try:
            local_packets = max(local_packets, int(local_counters.get(key, 0) or 0))
        except Exception:
            continue

    link_status = {}
    mavlink_validation = {}
    if isinstance(gcs_status, dict):
        link_status = gcs_status.get("link_status") or {}
        mavlink_validation = gcs_status.get("mavlink_validation") or {}

    try:
        gcs_msgs = int(mavlink_validation.get("total_msgs_received", 0) or 0)
    except Exception:
        gcs_msgs = 0

    local_ready = local_packets >= int(local_min_packets)
    gcs_ready = bool(link_status.get("stream_active")) or bool(link_status.get("heartbeat_present")) or gcs_msgs >= int(gcs_min_msgs)
    return local_ready and gcs_ready


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

# =============================================================================
# Drone Proxy Manager
# =============================================================================

class DroneProxyManager:
    """Manages drone proxy subprocess."""
    
    def __init__(self, switch_mode: str = "cold_restart"):
        self.managed_proc = None
        self.current_suite = None
        self.last_log_path = None
        self._log_handle = None  # BUG-06 fix: track log file handle
        self._switch_mode = switch_mode
    
    def start(self, suite_name: str) -> bool:
        """Start drone proxy with given suite."""
        # In in_band_rekey mode, the proxy stays alive across suites.
        # Don't kill it if it's already running for an earlier suite.
        if self.managed_proc and self.managed_proc.is_running():
            if self._switch_mode == "in_band_rekey":
                self.current_suite = suite_name
                return True
            self.stop()
        
        suite = get_suite(suite_name)
        if not suite:
            log(f"Unknown suite: {suite_name}", "ERROR")
            return False
        
        peer_pubkey = _resolve_matrix_key_path(suite_name, "gcs_signing.pub")
        
        if not peer_pubkey:
            log(f"Missing key for suite: {suite_name} (gcs_signing.pub)", "ERROR")
            return False
        
        cmd = [
            sys.executable, "-m", "core.run_proxy", "drone",
            "--suite", suite_name,
            "--peer-pubkey-file", str(peer_pubkey),
            "--quiet",
            "--status-file", str(LOGS_DIR / "drone_status.json")
        ]
        # In-band rekey mode: enable TCP control server on the proxy so
        # the scheduler can send {"cmd":"rekey","suite":"..."} without
        # stopping and restarting the subprocess.
        if self._switch_mode == "in_band_rekey":
            cmd.extend(["--enable-tcp-control", "--coordinator-role", "drone"])

        timestamp = time.strftime("%Y%m%d-%H%M%S")
        log_path = LOGS_DIR / f"drone_{suite_name}_{timestamp}.log"
        self._log_handle = open(log_path, "w", encoding="utf-8")  # BUG-06 fix: store handle
        
        # Ensure subprocess can find 'core' package AND oqs-python
        env = os.environ.copy()
        project_root = str(Path(__file__).parent.parent.absolute())
        sep = ";" if sys.platform.startswith("win") else ":"
        paths_to_add = [project_root]
        # Include LIBOQS_PYTHON_DIR so the proxy subprocess can import oqs
        liboqs_dir = env.get("LIBOQS_PYTHON_DIR", "")
        if liboqs_dir and os.path.isdir(liboqs_dir):
            paths_to_add.append(liboqs_dir)
        existing_pp = env.get("PYTHONPATH", "")
        for p in paths_to_add:
            if p not in existing_pp:
                existing_pp = f"{p}{sep}{existing_pp}" if existing_pp else p
        env["PYTHONPATH"] = existing_pp

        self.managed_proc = ManagedProcess(
            cmd=cmd,
            name=f"proxy-{suite_name}",
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            env=env
        )
        
        if self.managed_proc.start():
            self.last_log_path = log_path
            self.current_suite = suite_name
            time.sleep(1.0)  # Short wait for process to start
            if not self.managed_proc.is_running():
                log(f"Proxy exited early", "ERROR")
                return False
            return True
        return False
    
    def request_rekey(self, suite_name: str) -> dict:
        """Send in-band rekey command to the running proxy via TCP control port.

        Returns the JSON response from the proxy's control server.  The caller
        should then poll the status file for ``rekey_ok``.
        """
        drone_control_host = str(CONFIG.get("DRONE_CONTROL_HOST", "127.0.0.1"))
        drone_control_port = int(CONFIG.get("DRONE_CONTROL_PORT", 48080))
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10.0)
            sock.connect((drone_control_host, drone_control_port))
            payload = json.dumps({"cmd": "rekey", "suite": suite_name}) + "\n"
            sock.sendall(payload.encode("utf-8"))
            response = b""
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                response += chunk
                if b"\n" in response:
                    break
            return json.loads(response.decode("utf-8").strip())
        except Exception as e:
            return {
                "ok": False,
                "error": str(e),
                "control_host": drone_control_host,
                "control_port": drone_control_port,
            }
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

    def stop(self):
        """Stop drone proxy."""
        if self.managed_proc:
            self.managed_proc.stop()
            self.managed_proc = None
            self.current_suite = None
        # BUG-06 fix: close log file handle to prevent FD leak
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except Exception:
                pass
            self._log_handle = None
    
    def is_running(self) -> bool:
        return self.managed_proc is not None and self.managed_proc.is_running()

# =============================================================================
# Handshake Status Reader
# =============================================================================

def read_handshake_status(timeout: float = DEFAULT_REKEY_TIMEOUT_S) -> Dict[str, Any]:
    """Read handshake status and metrics from status file."""
    return _read_handshake_status(timeout=timeout, status_file=LOGS_DIR / "drone_status.json")

# =============================================================================
# MAVProxy Manager
# =============================================================================

# Sniff port for MAVLink metrics collector (different from proxy port to avoid conflict)
MAVLINK_SNIFF_PORT = int(CONFIG.get("MAVLINK_SNIFF_DRONE", 47005))


def _discover_serial_masters() -> List[str]:
    """Return candidate FC serial masters in priority order."""
    candidates: List[str] = []

    by_id_paths = sorted(glob.glob("/dev/serial/by-id/*"))
    for path in by_id_paths:
        if os.path.exists(path):
            candidates.append(path)

    tty_globs = ["/dev/ttyACM*", "/dev/ttyUSB*", "/dev/ttyAMA*"]
    for pattern in tty_globs:
        for path in sorted(glob.glob(pattern)):
            if os.path.exists(path):
                candidates.append(path)

    seen = set()
    ordered: List[str] = []
    for item in candidates:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _resolve_mav_master(requested_master: str) -> str:
    """Resolve MAVProxy master with serial auto-detect and UDP fallback."""
    requested = str(requested_master or "").strip()
    if not requested:
        requested = "auto"

    network_prefixes = ("udp:", "udpin:", "udpout:", "tcp:", "tcpin:", "tcpout:")
    if requested.startswith(network_prefixes):
        return requested

    if requested != "auto" and requested.startswith("/dev/") and os.path.exists(requested):
        return requested

    detected = _discover_serial_masters()
    if detected:
        chosen = detected[0]
        if requested not in {"auto", chosen}:
            log(
                f"Requested MAV master {requested} not found, using detected device {chosen}",
                "WARN",
            )
        else:
            log(f"Using detected MAV serial device: {chosen}")
        return chosen

    # No serial FC device visible: keep benchmark alive by listening for UDP MAVLink.
    fallback = f"udpin:0.0.0.0:{int(CONFIG.get('MAV_GCS_IN_PORT_1', 14550))}"
    log(
        "No serial FC device detected (/dev/serial/by-id,/dev/ttyACM*,/dev/ttyUSB*); "
        f"falling back to {fallback}",
        "WARN",
    )
    return fallback

def start_mavproxy(mav_master: str) -> Optional[ManagedProcess]:
    """Start persistent MAVProxy for drone."""
    python_exe = sys.executable
    # Primary output to proxy for encryption/forwarding
    out_proxy = f"udp:127.0.0.1:{DRONE_PLAIN_TX_PORT}"
    # Secondary output for MAVLink metrics sniffing
    out_sniff = f"udp:127.0.0.1:{MAVLINK_SNIFF_PORT}"
    
    cmd = [
        python_exe, "-m", "MAVProxy.mavproxy",
        f"--master={mav_master}",
        f"--out={out_proxy}",
        f"--out={out_sniff}",
        "--nowait",
        "--daemon",
    ]
    
    ts = time.strftime("%Y%m%d-%H%M%S")
    log_path = LOGS_DIR / f"mavproxy_bench_{ts}.log"
    
    try:
        fh = open(log_path, "w", encoding="utf-8")
    except Exception:
        fh = subprocess.DEVNULL
    
    log(f"Starting MAVProxy: {' '.join(cmd)}")
    
    proc = ManagedProcess(
        cmd=cmd,
        name="mavproxy-bench",
        stdout=fh,
        stderr=subprocess.STDOUT,
        new_console=False
    )
    # BUG-07 fix: attach log handle to proc so _cleanup can close it
    proc._mavproxy_log_handle = fh
    
    if proc.start():
        time.sleep(1.0)
        return proc if proc.is_running() else None
    return None

# =============================================================================
# Benchmark Scheduler
# =============================================================================

class BenchmarkScheduler:
    """Main benchmark scheduler orchestrating suite cycling."""
    
    def __init__(self, args):
        global LOGS_DIR
        
        self.args = args
        self.mode = getattr(args, "mode_resolved", None) or resolve_benchmark_mode(
            getattr(args, "mode", None),
            default_mode="MAVPROXY",
        )
        
        # Suite-switch mode: "cold_restart" (legacy) or "in_band_rekey"
        # Resolved early so DroneProxyManager can use it at construction time.
        cli_bm = getattr(args, "benchmark_mode", None)
        self.switch_mode = cli_bm or str(CONFIG.get("BENCHMARK_MODE", "cold_restart"))
        if self.switch_mode not in ("cold_restart", "in_band_rekey"):
            self.switch_mode = "cold_restart"
        
        self.proxy = DroneProxyManager(switch_mode=self.switch_mode)
        self.mavproxy_proc = None
        self._mavproxy_restart_attempts = 0
        self.clock_sync = ClockSync(
            smoothing=bool(CONFIG.get("CLOCK_SYNC_SMOOTHING", False)),
            window=int(CONFIG.get("CLOCK_SYNC_WINDOW", 3)),
        )
        self._suite_start_mono = None
        self._suite_activation_mono = None
        self._advance_grace_s = 10.0
        self._shutdown_reason: Optional[str] = None
        self._shutdown_error: bool = False
        self._cleanup_done: bool = False
        
        # Track clock sync timing
        self._last_sync_suite_idx = 0
        self._last_sync_mono = time.monotonic()
        
        # Initialize benchmark policy
        explicit_suite_sequence = getattr(args, "suite_sequence", None)
        self.policy = BenchmarkPolicy(
            cycle_interval_s=args.interval,
            filter_aead=args.filter_aead,
            filter_kem=getattr(args, 'filter_kem', None),
            suite_list=explicit_suite_sequence,
        )
        
        # Set up LOGS_DIR with consistent run_id (drone is the master)
        # Respect --log-dir override if it was set before scheduler init
        if LOGS_DIR is None:
            LOGS_DIR = _LOGS_DIR_BASE / f"live_run_{self.policy.run_id}"
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        
        # Limit suites if requested
        if args.max_suites and args.max_suites < len(self.policy.suite_list):
            self.policy.suite_list = self.policy.suite_list[:args.max_suites]
            log(f"Limited to {args.max_suites} suites")
        
        # Results tracking
        self.results_file = LOGS_DIR / f"benchmark_{self.policy.run_id}.jsonl"
        self.summary_file = LOGS_DIR / f"benchmark_summary_{self.policy.run_id}.json"
        self.gcs_results_file = LOGS_DIR / f"benchmark_gcs_{self.policy.run_id}.jsonl"
        
        # Initialize sync tracker and robust logger (aggressive append-mode)
        self.sync_tracker = None
        self.robust_logger = None
        if HAS_ROBUST_LOGGER:
            try:
                self.sync_tracker = SyncTracker()
                self.robust_logger = RobustLogger(
                    run_id=self.policy.run_id,
                    role="drone",
                    base_dir=_LOGS_DIR_BASE,
                    sync_tracker=self.sync_tracker,
                )
                log("RobustLogger initialized for aggressive append-mode logging")
            except Exception as e:
                log(f"RobustLogger init failed: {e}", "WARN")
        
        # Initialize comprehensive metrics aggregator (drone side)
        self.metrics_aggregator = None
        if HAS_METRICS_AGGREGATOR:
            try:
                self.metrics_aggregator = MetricsAggregator(
                    role="drone",
                    output_dir=str(LOGS_DIR / "comprehensive")
                )
                self.metrics_aggregator.set_run_id(self.policy.run_id)
                log("MetricsAggregator initialized for comprehensive metrics")
            except Exception as e:
                log(f"MetricsAggregator init failed: {e}", "WARN")
    
    def run(self):
        """Run the benchmark."""
        total_suites = len(self.policy.suite_list)
        estimated_time = total_suites * self.args.interval
        
        log("=" * 70)
        log("BENCHMARK MODE - Comprehensive Suite Testing")
        log("=" * 70)
        log(f"Total suites to test: {total_suites}")
        log(f"Interval per suite: {self.args.interval}s")
        log(f"Estimated total time: {estimated_time/60:.1f} minutes")
        log(f"Output directory: {LOGS_DIR}")
        log(f"Filter AEAD: {self.args.filter_aead or 'all'}")
        log(f"BENCHMARK_MODE: {self.mode}")
        log(f"SWITCH_MODE: {self.switch_mode}")
        log("=" * 70)
        
        if self.args.dry_run:
            log("DRY RUN - Printing plan only:")
            for i, suite in enumerate(self.policy.suite_list):
                cfg = self.policy.all_suites.get(suite, {})
                log(f"  {i+1:3d}. {suite} ({cfg.get('nist_level', '?')})")
            return
        
        # Wait for GCS
        log("Waiting for GCS control server...")
        if not wait_for_gcs(timeout=60.0):
            log("GCS not available, aborting", "ERROR")
            if self.robust_logger:
                self.robust_logger.log_event("gcs_unavailable", {"timeout": 60.0})
            return
        log("GCS connected")

        # Initial clock sync with GCS
        self._perform_clock_sync()
        
        # Start MAVProxy
        log("Starting MAVProxy...")
        self.mavproxy_proc = None
        self.args.mav_master = _resolve_mav_master(self.args.mav_master)
        log(f"Resolved MAVProxy master: {self.args.mav_master}")
        for attempt in range(1, 4):
            self.mavproxy_proc = start_mavproxy(self.args.mav_master)
            if self.mavproxy_proc and self.mavproxy_proc.is_running():
                if attempt > 1:
                    log(f"MAVProxy started on retry {attempt}/3", "WARN")
                break
            log(f"MAVProxy start attempt {attempt}/3 failed", "WARN")
            time.sleep(2.0)
        if not self.mavproxy_proc:
            log("MAVProxy failed to start after retries", "WARN")
        if self.mode == "MAVPROXY" and not (self.mavproxy_proc and self.mavproxy_proc.is_running()):
            self._shutdown_reason = "error: mavproxy_not_running"
            self._shutdown_error = True
            log("MAVProxy-only mode requires MAVProxy to be running; aborting", "ERROR")
            self._shutdown(self._shutdown_reason, error=True)
            return
        
        # Start benchmark
        try:
            # Always use monotonic clock for policy timing to avoid
            # time-domain mixing (synced_time returns wall-clock ~1.7e9
            # which would make elapsed_on_suite permanently negative).
            start_time = time.monotonic()
            first_suite = self.policy.start_benchmark(start_time_mono=start_time)
            log(f"Starting benchmark with {first_suite}")
            
            self._run_loop()
            
        except KeyboardInterrupt:
            self._shutdown_reason = "normal: interrupted"
            self._shutdown_error = False
            log("Benchmark interrupted by user")
        finally:
            if self._shutdown_reason is None:
                self._shutdown_reason = "normal: completed"
                self._shutdown_error = False
            self._shutdown(self._shutdown_reason, error=self._shutdown_error)
            self._save_final_summary()
    
    def _run_loop(self):
        """Main benchmark loop."""
        current_suite = self.policy.get_current_suite()
        
        while not self.policy.benchmark_complete:
            if self.mode == "MAVPROXY" and not (self.mavproxy_proc and self.mavproxy_proc.is_running()):
                if self._mavproxy_restart_attempts >= 1:
                    self._shutdown_reason = "error: mavproxy_died"
                    self._shutdown_error = True
                    log("MAVProxy died during MAVProxy-only run; aborting", "ERROR")
                    return
                self._mavproxy_restart_attempts += 1
                log("MAVProxy died; attempting one restart", "WARN")
                self.mavproxy_proc = start_mavproxy(self.args.mav_master)
                if not (self.mavproxy_proc and self.mavproxy_proc.is_running()):
                    self._shutdown_reason = "error: mavproxy_restart_failed"
                    self._shutdown_error = True
                    log("MAVProxy restart failed during MAVProxy-only run", "ERROR")
                    return
                log("MAVProxy restart succeeded; continuing benchmark", "INFO")
                time.sleep(1.0)
            # Activate current suite
            if not self._activate_suite(current_suite):
                log(f"Failed to activate {current_suite}, marking as failed", "WARN")
                # Note: finalize_suite_metrics is called inside _finalize_metrics
            
            # Wait for policy to switch
            while True:
                # C3 fix: Always use monotonic for policy timing to avoid
                # time-domain mixing if clock sync state changes mid-run.
                now = time.monotonic()
                output = self.policy.evaluate(now)
                
                if output.action == BenchmarkAction.COMPLETE:
                    if not self._ready_to_advance() and not self._grace_elapsed():
                        log("Metrics not ready; extending suite before completion")
                        time.sleep(1.0)
                        continue
                    log("Benchmark complete!")
                    if self.metrics_aggregator:
                        self.metrics_aggregator.record_control_plane_metrics(
                            scheduler_action_type=str(output.action),
                            scheduler_action_reason=output.reasons[0] if output.reasons else "",
                            policy_name="BenchmarkPolicy",
                            policy_state="COMPLETE",
                            policy_suite_index=output.current_index,
                            policy_total_suites=output.total_suites,
                            scheduler_tick_interval_ms=self.args.interval * 1000.0,
                        )
                    
                    # 1. Collect GCS metrics FIRST (so we can include them in final report)
                    gcs_metrics = self._collect_gcs_metrics(current_suite)

                    # 2. Finalize current suite metrics BEFORE advancing
                    #    (appends last suite to collected_metrics before _save_results)
                    self._finalize_metrics(success=True, gcs_metrics=gcs_metrics)

                    # 3. Commit state change — triggers _save_results() with complete data
                    self.policy.confirm_advance(now)
                    self._shutdown_reason = "normal: benchmark_complete"
                    self._shutdown_error = False
                    return
                
                if output.action == BenchmarkAction.NEXT_SUITE:
                    if not self._ready_to_advance() and not self._grace_elapsed():
                        log("Metrics not ready; extending suite before advancing")
                        time.sleep(1.0)
                        continue
                    progress = output.progress_pct
                    log(f"[{progress:.1f}%] Switching to {output.target_suite}")

                    if self.metrics_aggregator:
                        self.metrics_aggregator.record_control_plane_metrics(
                            scheduler_action_type=str(output.action),
                            scheduler_action_reason=output.reasons[0] if output.reasons else "",
                            policy_name="BenchmarkPolicy",
                            policy_state="ADVANCE",
                            policy_suite_index=output.current_index,
                            policy_total_suites=output.total_suites,
                            scheduler_tick_interval_ms=self.args.interval * 1000.0,
                        )
                    
                    # 1. Collect GCS metrics FIRST
                    if self.switch_mode == "in_band_rekey":
                        # R1-FIX: Pass next_suite so GCS restarts metrics
                        # collection for the upcoming suite after finalizing
                        # the current one.
                        gcs_metrics = self._collect_gcs_metrics_live(
                            current_suite, next_suite=output.target_suite)
                    else:
                        gcs_metrics = self._collect_gcs_metrics(current_suite)
                    gcs_ok = bool(gcs_metrics)
                    
                    # 2. Finalize current suite metrics BEFORE advancing
                    #    (appends current suite to collected_metrics before new suite starts)
                    self._finalize_metrics(success=True, gcs_metrics=gcs_metrics)

                    if self.switch_mode == "in_band_rekey":
                        # ── In-band rekey path ──────────────────────────────
                        # Proxy stays alive; send TCP rekey to the drone proxy's
                        # control port.  The proxy coordinator (drone) triggers
                        # the two-phase commit over the encrypted in-band
                        # control plane ↔ GCS proxy.
                        #
                        # R3-FIX: confirm_advance() is deferred until rekey
                        # success is confirmed.  On failure the suite index
                        # stays on the current suite so the policy timer
                        # re-fires and the old cipher remains active.
                        self._stop_traffic()
                        target_suite = output.target_suite

                        # Start metrics for the new suite so handshake timing
                        # is captured.
                        if self.metrics_aggregator:
                            suite_config = self.policy.all_suites.get(target_suite, {})
                            self.metrics_aggregator.start_suite(target_suite, suite_config)
                            self.metrics_aggregator.record_handshake_start()

                        # Clear stale status file before rekey
                        status_file = LOGS_DIR / "drone_status.json"
                        try:
                            if status_file.exists():
                                status_file.unlink()
                        except Exception:
                            pass

                        resp = self.proxy.request_rekey(target_suite)
                        if not resp.get("ok"):
                            log(f"Rekey request rejected: {resp}", "ERROR")
                            # R3-FIX: Do NOT advance — old cipher still active.
                            # Finalize the short-lived target metrics as failed,
                            # then restart metrics on the old (still-active) suite.
                            if self.metrics_aggregator:
                                self.metrics_aggregator.record_handshake_end(
                                    success=False,
                                    failure_reason=f"rekey_rejected:{resp.get('error')}"
                                )
                                self.metrics_aggregator.finalize_suite()
                                suite_config = self.policy.all_suites.get(current_suite, {})
                                self.metrics_aggregator.start_suite(current_suite, suite_config)
                            # R1/R3: Realign GCS metrics back to old suite.
                            try:
                                send_gcs_command("collect_metrics", next_suite=current_suite)
                            except Exception:
                                pass
                            self._log_result(target_suite, {}, success=False, error=f"rekey_rejected:{resp.get('error')}")
                            # Reset policy timer so it dwells a full interval before
                            # re-proposing NEXT_SUITE (prevents tight retry loop).
                            self.policy.last_switch_mono = time.monotonic()
                            if self.mode != "MAVPROXY":
                                self._start_traffic()
                            continue

                        log(f"  Rekey initiated (rid={resp.get('rid')}), waiting for completion...")

                        # Poll status file for rekey_ok (reuses handshake timeout)
                        rekey_status = self._read_rekey_status(timeout=DEFAULT_REKEY_TIMEOUT_S)
                        if rekey_status.get("status") == "rekey_ok":
                            metrics = rekey_status.get("handshake_metrics", {})
                            self.policy.record_handshake_metrics(metrics)
                            rekey_ms = metrics.get("rekey_ms", 0)
                            log(f"  Rekey OK: {rekey_ms:.1f}ms (suite={target_suite})")
                            if self.metrics_aggregator:
                                self.metrics_aggregator.record_handshake_end(success=True)
                                self.metrics_aggregator.record_crypto_primitives(metrics)
                            # R3-FIX: Advance suite index ONLY after confirmed rekey.
                            self.policy.confirm_advance(now)
                            self._suite_start_mono = time.monotonic()
                            # WINDOW-ALIGN: same reset as cold_restart path
                            if self.metrics_aggregator:
                                self.metrics_aggregator.reset_mavlink_count_window()
                            self._log_result(target_suite, metrics, success=True)
                            self.proxy.current_suite = target_suite
                            current_suite = target_suite
                            if self.mode != "MAVPROXY":
                                self._start_traffic()
                        else:
                            log(f"  Rekey timeout/failed for {target_suite}", "WARN")
                            if self.metrics_aggregator:
                                self.metrics_aggregator.record_handshake_end(
                                    success=False,
                                    failure_reason="rekey_timeout"
                                )
                            self._log_result(target_suite, {}, success=False, error="rekey_timeout")
                            # R3-FIX: Do NOT advance — old cipher still active.
                            # Finalize failed target metrics and restart on old suite.
                            if self.metrics_aggregator:
                                self.metrics_aggregator.finalize_suite()
                                suite_config = self.policy.all_suites.get(current_suite, {})
                                self.metrics_aggregator.start_suite(current_suite, suite_config)
                            # R1/R3: Realign GCS metrics back to old suite.
                            try:
                                send_gcs_command("collect_metrics", next_suite=current_suite)
                            except Exception:
                                pass
                            # Reset policy timer so it dwells a full interval before
                            # re-proposing NEXT_SUITE (prevents tight retry loop).
                            self.policy.last_switch_mono = time.monotonic()
                            if self.mode != "MAVPROXY":
                                self._start_traffic()

                        # Continue inner while loop (success: new suite; failure: old suite retries)
                        continue
                    else:
                        # 3. Commit state change — starts metrics for next suite
                        #    (cold_restart advances here; in_band_rekey advances
                        #     inside the rekey-success branch above)
                        self.policy.confirm_advance(now)

                        # ── Cold restart path (legacy) ──────────────────────
                        # Stop current proxy
                        self.proxy.stop()
                        # F7: Always ensure GCS proxy is stopped before starting the next suite.
                        # _collect_gcs_metrics calls stop_suite which stops the GCS proxy,
                        # but if that call failed (gcs_ok=False), explicitly send prepare_rekey.
                        # This prevents orphaned GCS proxy processes.
                        if not gcs_ok:
                            resp = send_gcs_command("prepare_rekey")
                            if resp.get("status") != "ok":
                                log(f"GCS prepare_rekey failed: {resp}", "WARN")
                        time.sleep(0.5)
                        
                        # F8: Verify drone proxy is actually dead before proceeding.
                        # On Pi under load, SIGTERM may take time.  Stale proxy holding
                        # the UDP port would cause the next proxy bind() to fail.
                        if self.proxy.is_running():
                            log("Proxy still running after stop(); force-killing", "WARN")
                            self.proxy.stop()  # Second attempt triggers SIGKILL path
                            time.sleep(0.2)
                        
                        current_suite = output.target_suite
                        break
                
                # R2-FIX: Lightweight proxy liveness check in in_band_rekey
                # mode.  In cold_restart, liveness is checked at activation;
                # in in_band_rekey the proxy must stay alive across suites.
                if self.switch_mode == "in_band_rekey" and not self.proxy.is_running():
                    log("Proxy process died during in-band dwell; aborting benchmark", "ERROR")
                    self._finalize_metrics(success=False, error="proxy_died")
                    self._log_result(current_suite, {}, success=False, error="proxy_died")
                    self._shutdown_reason = "error: proxy_died_in_band"
                    self._shutdown_error = True
                    return

                # HOLD — BUG-26 fix: sleep only the remaining interval fraction
                # instead of a fixed 1s to avoid overshooting the suite interval.
                remaining = self.args.interval - (time.monotonic() - self.policy.last_switch_mono)
                sleep_s = max(0.1, min(remaining, 1.0))

                # Application-level RTT probe: measure round-trip through the
                # encrypted tunnel using a lightweight RPC ping.  This is used
                # instead of MAVLink PING because the proxy architecture is
                # unidirectional and doesn't route PINGs back.
                try:
                    t_rtt_1 = time.monotonic()
                    rtt_resp = send_gcs_command("ping")
                    t_rtt_4 = time.monotonic()
                    if rtt_resp.get("status") == "ok" and self.metrics_aggregator:
                        # FIX-S4: This is CONTROL-PLANE RTT (TCP port 48080), not
                        # data-plane UDP tunnel latency. Used as a proxy since MAVLink
                        # PINGs don't route back through the unidirectional tunnel.
                        rtt_ms = (t_rtt_4 - t_rtt_1) * 1000.0
                        self.metrics_aggregator.inject_rtt_sample(rtt_ms)
                except Exception:
                    pass

                time.sleep(sleep_s)
    
    def _activate_suite(self, suite_name: str) -> bool:
        """Activate a suite on both drone and GCS."""
        log(f"Activating suite: {suite_name}")
        self._suite_activation_mono = time.monotonic()
        
        # Check if we should re-sync clocks
        if self._should_resync():
            log("Performing periodic clock re-sync...")
            self._perform_clock_sync()
        
        # Get suite config for metrics
        suite_config = self.policy.all_suites.get(suite_name, {})
        
        # Start robust logging for this suite (aggressive append-mode)
        if self.robust_logger:
            self.robust_logger.start_suite(suite_name, suite_config)
            self.robust_logger.log_event("suite_activation_started", {
                "suite_index": self.policy.current_index,
                "total_suites": len(self.policy.suite_list),
            })
        
        # Start comprehensive metrics collection
        if self.metrics_aggregator:
            try:
                self.metrics_aggregator.start_suite(suite_name, suite_config)
                self.metrics_aggregator.record_handshake_start()
                self.metrics_aggregator.record_control_plane_metrics(
                    scheduler_tick_interval_ms=self.args.interval * 1000.0,
                    policy_name="BenchmarkPolicy",
                    policy_state="ACTIVE",
                    policy_suite_index=self.policy.current_index,
                    policy_total_suites=len(self.policy.suite_list),
                )
            except Exception as e:
                log(f"Metrics start failed: {e}", "WARN")
        
        # Clear old status file to avoid reading stale data
        status_file = LOGS_DIR / "drone_status.json"
        try:
            if status_file.exists():
                status_file.unlink()
        except Exception:
            pass
        
        # Tell GCS to start proxy
        start_kw: Dict[str, Any] = {"suite": suite_name, "run_id": self.policy.run_id}
        if self.switch_mode == "in_band_rekey":
            start_kw["rekey_mode"] = True
        resp = send_gcs_command("start_proxy", **start_kw)
        if resp.get("status") != "ok":
            log(f"GCS rejected: {resp}", "ERROR")
            if self.robust_logger:
                self.robust_logger.log_event("gcs_rejected", {"response": resp})
                self.robust_logger.end_suite(success=False, error="gcs_rejected")
            self._finalize_metrics(success=False, error="gcs_rejected")
            return False
        
        log(f"  GCS proxy started, starting drone proxy...")
        
        # Start drone proxy
        if not self.proxy.start(suite_name):
            log("Drone proxy failed to start", "ERROR")
            if self.robust_logger:
                self.robust_logger.log_event("proxy_start_failed", {})
                self.robust_logger.end_suite(success=False, error="proxy_start_failed")
            self._finalize_metrics(success=False, error="proxy_start_failed")
            return False
        
        log(f"  Drone proxy started, waiting for handshake...")
        
        # Read handshake metrics (allow 45s for Classic McEliece)
        status = read_handshake_status(timeout=DEFAULT_REKEY_TIMEOUT_S)
        if status.get("status") == "handshake_ok":
            metrics = status.get("handshake_metrics", {})
            self.policy.record_handshake_metrics(metrics)
            
            handshake_ms = metrics.get("rekey_ms", 0)
            log(f"  Handshake OK: {handshake_ms:.1f}ms")
            
            # Log handshake metrics incrementally (AGGRESSIVE LOGGING)
            if self.robust_logger:
                self.robust_logger.log_metrics_incremental("handshake", {
                    "handshake_ms": handshake_ms,
                    "rekey_ms": metrics.get("rekey_ms", 0),
                    "kem_keygen_ms": metrics.get("kem_keygen_max_ms", 0),
                    "kem_encaps_ms": metrics.get("kem_encaps_max_ms", 0),
                    "kem_decaps_ms": metrics.get("kem_decaps_max_ms", 0),
                    "sig_sign_ms": metrics.get("sig_sign_max_ms", 0),
                    "sig_verify_ms": metrics.get("sig_verify_max_ms", 0),
                    "pub_key_size_bytes": metrics.get("pub_key_size_bytes", 0),
                    "ciphertext_size_bytes": metrics.get("ciphertext_size_bytes", 0),
                    "sig_size_bytes": metrics.get("sig_size_bytes", 0),
                })
            
            # Record crypto primitives in aggregator
            if self.metrics_aggregator:
                try:
                    self.metrics_aggregator.record_handshake_end(success=True)
                    self.metrics_aggregator.record_crypto_primitives(metrics)
                except Exception as e:
                    log(f"Metrics record failed: {e}", "WARN")

            # WINDOW-ALIGN: Reset the MAVLink sniff collector's counters so
            # that the counting window starts NOW — at the moment the proxy
            # forwarding loop is actually live.  Before this point the
            # collector was counting messages during GCS-command round-trip,
            # subprocess startup and PQC handshake — none of which the proxy
            # could receive (port 47003 was not bound yet).
            if self.metrics_aggregator:
                self.metrics_aggregator.reset_mavlink_count_window()

            if self.mode == "MAVPROXY":
                # MAVProxy-only invariant: no software traffic generation.
                log("MAVProxy-only mode: traffic generation disabled")
            else:
                self._start_traffic()

            if self._wait_for_live_data_flow(suite_name):
                self._suite_start_mono = time.monotonic()
                warmup_ms = 0.0
                if self._suite_activation_mono is not None:
                    warmup_ms = (self._suite_start_mono - self._suite_activation_mono) * 1000.0
                log(f"  Data flow ready; dwell starts after {warmup_ms:.1f}ms activation warmup")
                if self.robust_logger:
                    self.robust_logger.log_event("data_flow_ready", {
                        "suite": suite_name,
                        "activation_warmup_ms": round(warmup_ms, 3),
                    })
            else:
                self._suite_start_mono = time.monotonic()
                log("  Data flow readiness not confirmed before dwell start", "WARN")
                if self.robust_logger:
                    self.robust_logger.log_event("data_flow_ready_timeout", {
                        "suite": suite_name,
                        "timeout_s": FLOW_READY_TIMEOUT_S,
                    })
            
            # Log to results file
            self._log_result(suite_name, metrics, success=True)
            
            # NOTE: _finalize_metrics() is called AFTER the interval wait, in _run_loop
            # when NEXT_SUITE is triggered, so data plane metrics can accumulate
            return True
        else:
            log(f"  Handshake timeout/failed", "WARN")
            if self.robust_logger:
                self.robust_logger.log_event("handshake_failed", {"status": status})
                self.robust_logger.end_suite(success=False, error="handshake_timeout")
            if self.metrics_aggregator:
                try:
                    self.metrics_aggregator.record_handshake_end(success=False, failure_reason="handshake_timeout")
                except Exception:
                    pass
            self._suite_start_mono = None
            self._log_result(suite_name, {}, success=False, error="handshake_timeout")
            self._finalize_metrics(success=False, error="handshake_timeout")
            return False

    def _perform_clock_sync(self) -> bool:
        """Perform clock synchronization with GCS."""
        try:
            samples: List[Dict[str, float]] = []
            failures: List[Dict[str, Any]] = []
            for idx in range(CLOCK_SYNC_SAMPLE_COUNT):
                t1 = time.time()
                resp = send_gcs_command("chronos_sync", t1=t1)
                t4 = time.time()
                if resp.get("status") != "ok":
                    failures.append({"sample": idx + 1, "response": resp})
                    continue
                t2 = float(resp.get("t2", 0.0) or 0.0)
                t3 = float(resp.get("t3", 0.0) or 0.0)
                if t2 == 0.0 or t3 == 0.0:
                    failures.append({"sample": idx + 1, "response": resp, "error": "invalid_timestamps"})
                    continue
                offset = ((t2 - t1) + (t3 - t4)) / 2.0
                rtt_ms = max(0.0, ((t4 - t1) - (t3 - t2)) * 1000.0)
                samples.append({"offset": offset, "rtt_ms": rtt_ms})
                time.sleep(0.05)

            selected = _select_clock_sync_sample(samples)
            if not selected:
                log(f"Clock sync failed: {failures or 'no valid samples'}", "WARN")
                if self.robust_logger:
                    self.robust_logger.log_event("clock_sync_failed", {
                        "failures": failures,
                        "samples_attempted": CLOCK_SYNC_SAMPLE_COUNT,
                    })
                return False

            offset = float(selected["offset"])
            offset_ms = float(selected["offset_ms"])
            self.clock_sync.set_offset(offset)
            log(
                "Clock sync offset (gcs-drone): "
                f"{offset:.6f}s ({offset_ms:.2f}ms), "
                f"samples={int(selected['samples'])}, best_rtt_ms={selected['rtt_ms_best']:.2f}"
            )

            if self.metrics_aggregator:
                self.metrics_aggregator.set_clock_offset(offset, method="chronos")

            try:
                send_gcs_command("set_clock_offset", offset=offset)
            except Exception:
                pass

            if self.robust_logger:
                self.robust_logger.record_sync(offset_ms, method="chronos")
            elif self.sync_tracker:
                self.sync_tracker.record_sync(offset_ms, method="chronos")

            self._last_sync_suite_idx = self.policy.current_index
            self._last_sync_mono = time.monotonic()
            return True
        except Exception as e:
            log(f"Clock sync error: {e}", "WARN")
            if self.robust_logger:
                self.robust_logger.log_event("clock_sync_error", {"error": str(e)})
            return False

    def _read_local_proxy_counters(self) -> Dict[str, Any]:
        status_file = LOGS_DIR / "drone_status.json"
        if not status_file.exists():
            return {}
        try:
            with open(status_file, "r", encoding="utf-8") as fh:
                status_data = json.load(fh)
            counters = status_data.get("counters", {})
            return counters if isinstance(counters, dict) else {}
        except Exception:
            return {}

    def _get_gcs_suite_status(self, suite_name: str) -> Dict[str, Any]:
        try:
            return send_gcs_command("get_suite_status", suite=suite_name)
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def _wait_for_live_data_flow(self, suite_name: str) -> bool:
        consecutive_ready = 0
        deadline = time.monotonic() + FLOW_READY_TIMEOUT_S
        last_local_counters: Dict[str, Any] = {}
        last_gcs_status: Dict[str, Any] = {}

        while time.monotonic() < deadline:
            last_local_counters = self._read_local_proxy_counters()
            last_gcs_status = self._get_gcs_suite_status(suite_name)
            if last_gcs_status.get("status") == "ok" and _is_live_data_flow_ready(
                last_local_counters,
                last_gcs_status,
            ):
                consecutive_ready += 1
                if consecutive_ready >= FLOW_READY_CONSECUTIVE_POLLS:
                    return True
            else:
                consecutive_ready = 0
            time.sleep(FLOW_READY_POLL_S)

        log(
            "  Live data flow not confirmed "
            f"(local={last_local_counters}, gcs_status={last_gcs_status})",
            "WARN",
        )
        return False

    def _should_resync(self) -> bool:
        """Check if we should re-sync clocks."""
        suites_since = self.policy.current_index - self._last_sync_suite_idx
        time_since = time.monotonic() - self._last_sync_mono
        return (suites_since >= CLOCK_SYNC_INTERVAL_SUITES or 
                time_since >= CLOCK_SYNC_INTERVAL_SECONDS)

    def _ready_to_advance(self) -> bool:
        """Return True when suite can advance without truncating benchmark evidence."""
        if self.mode == "MAVPROXY":
            # MAVProxy-only invariant: only require MAVProxy alive and control plane alive.
            if not (self.mavproxy_proc and self.mavproxy_proc.is_running()):
                return False
            try:
                resp = send_gcs_command("ping")
                return resp.get("status") == "ok"
            except Exception:
                return False

        if not self.metrics_aggregator or not self.metrics_aggregator.mavlink_collector:
            return False
        try:
            mav_metrics = self.metrics_aggregator.mavlink_collector.get_metrics()
            total_msgs = mav_metrics.get("total_msgs_received")
            if total_msgs is None or int(total_msgs) <= 0:
                return False
        except Exception:
            return False

        status_file = LOGS_DIR / "drone_status.json"
        if status_file.exists():
            try:
                with open(status_file, "r") as f:
                    status_data = json.load(f)
                counters = status_data.get("counters", {})
                ptx_in = counters.get("ptx_in", 0) or 0
                enc_out = counters.get("enc_out", 0) or 0
                if int(ptx_in) <= 0 and int(enc_out) <= 0:
                    return False
            except Exception:
                return False
        else:
            return False
        return True

    def _grace_elapsed(self) -> bool:
        if self._suite_start_mono is None:
            return True
        return (time.monotonic() - self._suite_start_mono) >= (self.args.interval + self._advance_grace_s)
    
    def _finalize_metrics(self, success: bool, error: str = "", gcs_metrics: Dict = None):
        """Finalize and save comprehensive metrics for current suite."""
        # Record result in the policy's collected_metrics list
        self.policy.finalize_suite_metrics(success=success, error_message=error)
        
        # Read data plane metrics from proxy status file (allow a brief window for the status writer to run)
        status_file = LOGS_DIR / "drone_status.json"
        counters: Dict[str, Any] = {}
        if status_file.exists():
            for _ in range(3):  # up to ~0.45s total (status writer flushes every 0.1s)
                try:
                    with open(status_file, "r") as f:
                        status_data = json.load(f)
                    candidate = status_data.get("counters", {})
                    counters = candidate or counters
                    # Break early if counters are present and non-empty
                    if candidate:
                        break
                except Exception:
                    pass
                time.sleep(0.15)
        
        # MEASUREMENT-SYNC: Stop MAVLink collector immediately after reading
        # ptx_in from the status file so mav_d is snapshotted at the same
        # instant.  This eliminates the 1-2 s processing delay that previously
        # inflated mav_d by 250-520 messages relative to ptx_in.
        if self.metrics_aggregator:
            self.metrics_aggregator.stop_mavlink_collector_early()
        
        # Log data plane metrics incrementally (AGGRESSIVE LOGGING)
        if counters and self.robust_logger:
            self.robust_logger.log_metrics_incremental("data_plane", {
                "ptx_in": counters.get("ptx_in", 0),
                "ptx_out": counters.get("ptx_out", 0),
                "enc_in": counters.get("enc_in", 0),
                "enc_out": counters.get("enc_out", 0),
            })
            log(
                "  Data plane: ptx_in=%s, enc_out=%s" %
                (counters.get("ptx_in", 0), counters.get("enc_out", 0))
            )
        
        # Log GCS metrics incrementally
        if gcs_metrics and self.robust_logger:
            self.robust_logger.log_metrics_incremental("gcs", gcs_metrics)
        
        # End suite in robust logger
        if self.robust_logger:
            self.robust_logger.end_suite(success=success, error=error)
        
        if not self.metrics_aggregator:
            return
        try:
            if counters:
                self.metrics_aggregator.record_data_plane_metrics(counters)
            
            # NOTE: record_handshake_end() is NOT called here.
            # It was already called in _activate_suite() immediately after handshake completion.
            # Calling it here would overwrite the correct handshake duration with the suite duration.
            
            # MERGE GCS METRICS HERE
            comprehensive = self.metrics_aggregator.finalize_suite(merge_from=gcs_metrics)
            if comprehensive:
                invalid_reasons = []
                mav_msgs = comprehensive.mavproxy_drone.mavproxy_drone_total_msgs_received
                latency_valid = comprehensive.latency_jitter.one_way_latency_valid
                rtt_valid = comprehensive.latency_jitter.rtt_valid
                if mav_msgs is None or int(mav_msgs) <= 0:
                    invalid_reasons.append("mavlink_no_messages")
                # Only flag latency as invalid if it's a real failure, not structural
                # unavailability (e.g., no GPS time → missing_system_time_reference)
                _structural_latency_reasons = {
                    "missing_system_time_reference",
                    "no_command_sent",
                    "no_timestamped_messages",
                }
                latency_reason = comprehensive.latency_jitter.latency_invalid_reason or ""
                rtt_reason = comprehensive.latency_jitter.rtt_invalid_reason or ""
                latency_structural = latency_reason in _structural_latency_reasons
                rtt_structural = rtt_reason in _structural_latency_reasons
                if (
                    latency_valid is not True
                    and rtt_valid is not True
                    and not latency_structural
                    and not rtt_structural
                ):
                    invalid_reasons.append("mavlink_latency_invalid")
                packets_sent = comprehensive.data_plane.packets_sent
                packets_received = comprehensive.data_plane.packets_received
                if (
                    packets_sent is None
                    or packets_received is None
                    or (int(packets_sent) <= 0 and int(packets_received) <= 0)
                ):
                    invalid_reasons.append("data_plane_no_traffic")

                if invalid_reasons:
                    comprehensive.validation.benchmark_pass_fail = "FAIL"
                    comprehensive.validation.success_rate_percent = 0.0
                    for reason in invalid_reasons:
                        comprehensive.validation.metric_status[f"suite_validity.{reason}"] = {
                            "status": "invalid",
                            "reason": reason,
                        }
                    if self.policy.collected_metrics:
                        self.policy.collected_metrics[-1].success = False
                        self.policy.collected_metrics[-1].error_message = ",".join(invalid_reasons)

                # Export to JSON
                output_path = self.metrics_aggregator.save_suite_metrics(comprehensive)
                if output_path:
                    log(f"  Comprehensive metrics saved: {output_path}")
        except Exception as e:
            log(f"Metrics finalize failed: {e}", "WARN")

    def _start_traffic(self) -> None:
        if self.mode == "MAVPROXY":
            raise RuntimeError("MAVProxy-only mode forbids software traffic generation")
        # TRAFFIC GENERATION DISABLED FOR LIVE MAVLINK
        log("Traffic generation disabled (Live MAVLink mode)")

    def _stop_traffic(self) -> None:
        if self.mode == "MAVPROXY":
            return

    def _collect_gcs_metrics(self, suite_name: str) -> Optional[Dict[str, Any]]:
        """Fetch GCS-side metrics for the suite and return them (also log to JSONL)."""
        self._stop_traffic()
        gcs_info: Dict[str, Any] = {}
        try:
            info_resp = send_gcs_command("get_info")
            if info_resp.get("status") == "ok":
                gcs_info = info_resp
        except Exception:
            gcs_info = {}
        try:
            resp = send_gcs_command("stop_suite", suite=suite_name)
        except Exception as e:
            log(f"GCS stop_suite error: {e}", "WARN")
            return None

        if resp.get("status") != "ok":
            log(f"GCS stop_suite failed: {resp}", "WARN")
            return None

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "suite_id": suite_name,
            "gcs_metrics": resp,
            "gcs_info": gcs_info,
        }
        try:
            with open(self.gcs_results_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log(f"Failed to log GCS metrics: {e}", "WARN")
            # Don't return None here, we still have the metrics to pass to aggregator
        
        if gcs_info:
            resp = dict(resp)
            resp["gcs_info"] = gcs_info
        return resp
    
    def _collect_gcs_metrics_live(self, suite_name: str, next_suite: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Collect GCS-side metrics WITHOUT stopping the GCS proxy.

        Used in ``in_band_rekey`` mode where the GCS proxy must stay alive
        for the in-band control plane to negotiate the next handshake.
        Sends ``collect_metrics`` instead of ``stop_suite``.

        R1-FIX: When *next_suite* is provided, the GCS will call
        ``start_suite(next_suite)`` after finalizing the current suite
        so that GCS-side metrics are properly segmented per suite.
        """
        self._stop_traffic()
        gcs_info: Dict[str, Any] = {}
        try:
            info_resp = send_gcs_command("get_info")
            if info_resp.get("status") == "ok":
                gcs_info = info_resp
        except Exception:
            gcs_info = {}
        cmd_kwargs: Dict[str, Any] = {}
        if next_suite:
            cmd_kwargs["next_suite"] = next_suite
        cmd_kwargs["suite"] = suite_name
        try:
            resp = send_gcs_command("collect_metrics", **cmd_kwargs)
        except Exception as e:
            log(f"GCS collect_metrics error: {e}", "WARN")
            return None

        if resp.get("status") != "ok":
            log(f"GCS collect_metrics failed: {resp}", "WARN")
            return None

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "suite_id": suite_name,
            "gcs_metrics": resp,
            "gcs_info": gcs_info,
        }
        try:
            with open(self.gcs_results_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log(f"Failed to log GCS metrics: {e}", "WARN")

        if gcs_info:
            resp = dict(resp)
            resp["gcs_info"] = gcs_info
        return resp

    def _read_rekey_status(self, timeout: float = 45.0) -> Dict[str, Any]:
        """Poll drone status file for ``rekey_ok`` after an in-band rekey request.

        Returns the status dict with ``handshake_metrics`` if rekey succeeded,
        or ``{"status": "timeout"}`` if the deadline expires.
        """
        status_file = LOGS_DIR / "drone_status.json"
        start_time = time.time()

        while time.time() - start_time < timeout:
            if status_file.exists():
                try:
                    with open(status_file, "r") as f:
                        data = json.load(f)
                    status = data.get("status")
                    if status == "rekey_ok":
                        metrics = data.get("handshake_metrics", {})
                        data["handshake_metrics"] = metrics
                        return data
                except Exception:
                    pass
            time.sleep(0.2)

        return {"status": "timeout", "handshake_metrics": {}}
    
    def _log_result(self, suite_name: str, metrics: Dict, success: bool, error: str = ""):
        """Log result to JSONL file."""
        cfg = self.policy.all_suites.get(suite_name, {})
        
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "suite_id": suite_name,
            "nist_level": cfg.get("nist_level", ""),
            "kem_name": cfg.get("kem_name", ""),
            "sig_name": cfg.get("sig_name", ""),
            "aead": cfg.get("aead_token", cfg.get("aead", "")),
            "success": success,
            "error": error,
            "handshake_ms": metrics.get("rekey_ms", 0),
            "kem_keygen_ms": metrics.get("kem_keygen_max_ms", 0),
            "kem_encaps_ms": metrics.get("kem_encaps_max_ms", 0),
            "kem_decaps_ms": metrics.get("kem_decaps_max_ms", 0),
            "sig_sign_ms": metrics.get("sig_sign_max_ms", 0),
            "sig_verify_ms": metrics.get("sig_verify_max_ms", 0),
            "pub_key_size_bytes": metrics.get("pub_key_size_bytes", 0),
            "ciphertext_size_bytes": metrics.get("ciphertext_size_bytes", 0),
            "sig_size_bytes": metrics.get("sig_size_bytes", 0)
        }
        
        try:
            with open(self.results_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            log(f"Failed to log result: {e}", "WARN")
    
    def _cleanup(self):
        """Cleanup resources."""
        # BUG-02 fix: re-entrancy guard inside _cleanup itself
        if self._cleanup_done:
            return
        self._cleanup_done = True
        log("Cleaning up...")
        self._stop_traffic()
        _close_gcs_sock()  # Close persistent TCP control connection
        if self.proxy:
            self.proxy.stop()
        if self.mavproxy_proc:
            # BUG-07 fix: close mavproxy log handle
            fh = getattr(self.mavproxy_proc, '_mavproxy_log_handle', None)
            self.mavproxy_proc.stop()
            if fh is not None and fh is not subprocess.DEVNULL:
                try:
                    fh.close()
                except Exception:
                    pass
        # Stop robust logger (flushes all buffered data)
        if self.robust_logger:
            self.robust_logger.log_event("benchmark_cleanup", {"reason": self._shutdown_reason})
            self.robust_logger.stop()

    def _shutdown(self, reason: str, *, error: bool) -> None:
        if self._cleanup_done:
            return
        level = "ERROR" if error else "INFO"
        log(f"Shutdown reason: {reason}", level)
        self._cleanup()
    
    def _save_final_summary(self):
        """Save final benchmark summary."""
        summary = self.policy.get_progress_summary()
        summary["collected_metrics"] = len(self.policy.collected_metrics)
        summary["results_file"] = str(self.results_file)
        
        # Calculate statistics
        successful = [m for m in self.policy.collected_metrics if m.success]
        if successful:
            handshake_times = [m.handshake_ms for m in successful]
            summary["stats"] = {
                "successful_count": len(successful),
                "failed_count": len(self.policy.collected_metrics) - len(successful),
                "handshake_min_ms": min(handshake_times),
                "handshake_max_ms": max(handshake_times),
                "handshake_avg_ms": sum(handshake_times) / len(handshake_times)
            }
        
        try:
            with open(self.summary_file, "w") as f:
                json.dump(summary, f, indent=2)
            log(f"Summary saved to {self.summary_file}")
        except Exception as e:
            log(f"Failed to save summary: {e}", "WARN")

# =============================================================================
# Cleanup
# =============================================================================

def cleanup_environment(aggressive: bool = False, mode: Optional[str] = None):
    """Kill stale processes.
    
    BUG-01 fix: In MAVPROXY mode, still kill managed processes via the
    global _SCHEDULER reference.  Pattern-based pkill is only used in
    non-MAVPROXY mode where MAVProxy is launched by the scheduler itself.
    """
    mode = mode or resolve_benchmark_mode(None, default_mode="MAVPROXY")

    # Always try to clean up via the scheduler object (safe in all modes)
    global _SCHEDULER
    if _SCHEDULER is not None:
        try:
            _SCHEDULER._cleanup()
        except Exception:
            pass

    if mode == "MAVPROXY":
        # In MAVPROXY mode, only kill managed processes (done above).
        # Do NOT pkill by name — real MAVProxy might be user-owned.
        return

    # Non-MAVPROXY mode: safe to pkill by pattern
    patterns = ["mavproxy.py"]
    if aggressive:
        patterns.append("core.run_proxy")
    for p in patterns:
        try:
            subprocess.run(["pkill", "-f", p], 
                          stdout=subprocess.DEVNULL, 
                          stderr=subprocess.DEVNULL)
        except Exception:
            pass
    time.sleep(0.5)


def _atexit_cleanup():
    global _SCHEDULER
    try:
        if _SCHEDULER is not None:
            _SCHEDULER._cleanup()
    except Exception:
        pass
    try:
        cleanup_environment(aggressive=True)
    except Exception:
        pass

# =============================================================================
# Main
# =============================================================================

def main():
    global GCS_CONTROL_HOST
    global GCS_CONTROL_PORT
    global LOGS_DIR
    parser = argparse.ArgumentParser(description="Benchmark Drone Scheduler")
    parser.add_argument("--mav-master", 
                       default=str(CONFIG.get("MAV_FC_DEVICE", "/dev/ttyACM0")),
                       help="MAVLink master (e.g., /dev/ttyACM0)")
    parser.add_argument("--interval", type=float, default=10.0,
                       help="Seconds per suite (default: 10)")
    parser.add_argument("--filter-aead", choices=["aesgcm", "chacha", "ascon"],
                       help="Only benchmark suites with this AEAD")
    parser.add_argument("--filter-kem", type=str,
                       help="Only benchmark suites whose KEM token contains this substring (e.g. mlkem, classicmceliece)")
    parser.add_argument("--max-suites", type=int,
                       help="Maximum number of suites to benchmark")
    parser.add_argument("--dry-run", action="store_true",
                       help="Print plan without executing")
    parser.add_argument("--gcs-host", type=str,
                       help="GCS control server host (override for Tailscale)")
    parser.add_argument("--gcs-port", type=int,
                       default=int(CONFIG.get("GCS_CONTROL_PORT", 48080)),
                       help="GCS control server port (default: CONFIG[GCS_CONTROL_PORT])")
    parser.add_argument("--mode", type=str,
                       help="Benchmark mode: MAVPROXY")
    parser.add_argument("--log-dir", type=str,
                       help="Override base log directory for this run")
    parser.add_argument("--benchmark-mode", type=str,
                       choices=["cold_restart", "in_band_rekey"],
                       default=None,
                       help="Suite-switch mode: cold_restart (default) or in_band_rekey")
    parser.add_argument("--suite-sequence-file", type=str,
                       help="Path to JSON file containing ordered suite IDs (duplicates allowed)")
    parser.add_argument("--suite-sequence", type=str,
                       help="Comma-separated ordered suite IDs (duplicates allowed)")
    args = parser.parse_args()

    if args.suite_sequence_file and args.suite_sequence:
        parser.error("Use either --suite-sequence-file or --suite-sequence, not both")

    if args.suite_sequence_file:
        seq_path = Path(args.suite_sequence_file).expanduser().resolve()
        try:
            loaded = json.loads(seq_path.read_text(encoding="utf-8"))
        except Exception as e:
            parser.error(f"Failed to read suite sequence file {seq_path}: {e}")
        if not isinstance(loaded, list) or not loaded or any(not isinstance(x, str) for x in loaded):
            parser.error("Suite sequence file must be a non-empty JSON array of suite ID strings")
        args.suite_sequence = [x.strip() for x in loaded if isinstance(x, str) and x.strip()]

    elif args.suite_sequence:
        parsed = [s.strip() for s in args.suite_sequence.split(",") if s.strip()]
        if not parsed:
            parser.error("--suite-sequence must contain at least one suite ID")
        args.suite_sequence = parsed

    if args.suite_sequence:
        known = list_suites()
        unknown = [sid for sid in args.suite_sequence if sid not in known]
        if unknown:
            parser.error(f"Unknown suite IDs in sequence: {', '.join(unknown[:8])}")
        log(f"Using explicit suite sequence with {len(args.suite_sequence)} entries")

    args.mode_resolved = resolve_benchmark_mode(args.mode, default_mode="MAVPROXY")
    log(f"BENCHMARK_MODE resolved to {args.mode_resolved}")

    if args.log_dir:
        LOGS_DIR = Path(args.log_dir).expanduser().resolve()
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    # Override GCS host if provided
    if args.gcs_host:
        GCS_CONTROL_HOST = resolve_control_host(args.gcs_host)
        log(f"Using GCS host override: {GCS_CONTROL_HOST}")

    # Override GCS port if provided
    if args.gcs_port:
        try:
            port_val = int(args.gcs_port)
        except (TypeError, ValueError):
            port_val = None
        if not port_val or port_val <= 0 or port_val > 65535:
            parser.error("--gcs-port must be an integer in 1..65535")
        if port_val != GCS_CONTROL_PORT:
            _close_gcs_sock()
        GCS_CONTROL_PORT = port_val
        log(f"Using GCS port override: {GCS_CONTROL_PORT}")
    
    # Setup signal handler
    def sigint_handler(sig, frame):
        log("Interrupted")
        cleanup_environment(aggressive=True, mode=args.mode_resolved)  # BUG-01 fix: pass mode
        sys.exit(0)
    
    signal.signal(signal.SIGINT, sigint_handler)
    # Don't register atexit - it kills proxies during normal benchmark flow
    
    # Light cleanup before starting (just MAVProxy, not proxies)
    # Aggressive cleanup before starting to ensure clean slate (per Operational Plan)
    cleanup_environment(aggressive=True, mode=args.mode_resolved)
    
    # Run benchmark
    scheduler = BenchmarkScheduler(args)
    global _SCHEDULER
    _SCHEDULER = scheduler
    atexit.register(_atexit_cleanup)
    scheduler.run()
    
    return 0

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())

