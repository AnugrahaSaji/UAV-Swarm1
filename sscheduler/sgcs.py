#!/usr/bin/env python3
"""
GCS Scheduler – MAV-to-MAV PQC Tunnel Follower
sscheduler/sgcs.py

REVERSED CONTROL: GCS is the follower; drone is the controller.

Data flow (bidirectional MAVLink):
  FC (serial) → MAVProxy(D) → PQC Proxy(D) ──encrypted──▸ PQC Proxy(G) → MAVProxy(G) → QGC
  FC (serial) ← MAVProxy(D) ← PQC Proxy(D) ◂──encrypted── PQC Proxy(G) ← MAVProxy(G) ← QGC

GCS responsibilities:
  1. Listen for TCP control commands from the drone scheduler.
  2. Start / stop PQC proxy for each suite on command.
  3. Run a persistent MAVProxy (--map --console) for QGC.
  4. Collect receiver-side MAVLink metrics via GcsMetricsCollector.
  5. Batch and forward telemetry snapshots to the drone over UDP.
  6. Serve Chronos clock-sync requests so the drone can align timestamps.

The GCS never initiates suite changes.  All scheduling decisions are made
by the drone's policy engine (deterministic or intelligent).

Usage:
  python -m sscheduler.sgcs
"""

import os
import sys
import time
import json
import socket
import signal
import atexit
import argparse
import logging
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

# Ensure parent on sys.path for core imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG
from core.suites import list_suites
from core.process import ManagedProcess
from core.clock_sync import ClockSync
from sscheduler.gcs_metrics import GcsMetricsCollector
from sscheduler.proxy_managers import GcsProxyManager
from sscheduler.control_server_base import ControlServerBase
from sscheduler.control_security import create_nonce_hex, compute_telemetry_mac, get_control_auth_key

# ---------------------------------------------------------------------------
# Configuration – single source of truth from core.config
# ---------------------------------------------------------------------------

DRONE_HOST = str(CONFIG.get("DRONE_HOST"))
GCS_HOST = str(CONFIG.get("GCS_HOST"))

GCS_PLAIN_TX_PORT = int(CONFIG.get("GCS_PLAINTEXT_TX", 47001))
GCS_PLAIN_RX_PORT = int(CONFIG.get("GCS_PLAINTEXT_RX", 47002))
TCP_CTRL_PORT = int(CONFIG.get("TCP_HANDSHAKE_PORT", 46000))
QGC_PORT = int(CONFIG.get("QGC_PORT", 14550))

# Telemetry sniff port: MAVProxy sends a copy of all MAVLink to this
# local UDP port so GcsMetricsCollector can parse it without interfering.
GCS_TELEMETRY_SNIFF_PORT = 14552

# Control plane
GCS_CONTROL_HOST = str(CONFIG.get("GCS_CONTROL_HOST", "0.0.0.0"))
GCS_CONTROL_PORT = int(CONFIG.get("GCS_CONTROL_PORT", 48080))

# Telemetry plane  (GCS → Drone, UDP)
GCS_TELEMETRY_PORT = int(CONFIG.get("GCS_TELEMETRY_PORT", 52080))

SECRETS_DIR = Path(__file__).parent.parent / "secrets" / "matrix"
ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs" / "sscheduler" / "gcs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Telemetry batching
TELEMETRY_HZ = 5.0           # Snapshot frequency
TELEMETRY_BATCH_SIZE = 5     # Samples per batch envelope
TELEMETRY_BATCH_INTERVAL_S = 1.0  # Max wait before flushing partial batch

_suites_dict = list_suites()
ALL_SUITES = [{"name": k, **v} for k, v in _suites_dict.items()]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [sgcs] {msg}", flush=True)


def wait_for_tcp_port(port: int, timeout: float = 5.0) -> bool:
    """Wait until a local TCP port accepts connections."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (ConnectionRefusedError, OSError, socket.timeout):
            time.sleep(0.2)
    return False


# ---------------------------------------------------------------------------
# Batched Telemetry Sender  (GCS → Drone, UDP)
# ---------------------------------------------------------------------------

class TelemetrySender:
    """Sends receiver-side telemetry snapshots to the Drone over UDP.

    Individual `GcsMetricsCollector.get_snapshot()` samples are buffered and
    sent as *batch envelopes* (``uav.pqc.telemetry.batch.v1``).  The
    batching strategy reduces per-packet overhead and lets the drone's
    `TelemetryReceiver` ingest multiple timestamped samples at once.

    Batching rules
    ~~~~~~~~~~~~~~
    * A batch is flushed when *TELEMETRY_BATCH_SIZE* samples have
      accumulated **or** when *TELEMETRY_BATCH_INTERVAL_S* elapses since
      the first sample in the current batch – whichever comes first.
    """

    BATCH_SCHEMA = "uav.pqc.telemetry.batch.v1"

    def __init__(self, target_host: str, target_port: int, target_hosts: Optional[List[str]] = None):
        self.target_host = target_host
        self.port = target_port
        self.target_addr = (target_host, target_port)
        
        # Support multi-drone telemetry dispatch
        drone_hosts_dict = CONFIG.get("DRONE_HOSTS", {})
        hosts_list = target_hosts or (list(drone_hosts_dict.values()) if isinstance(drone_hosts_dict, dict) else [target_host])
        self.target_addrs = list({(h, target_port) for h in hosts_list if h})

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.seq = 0
        self._lock = threading.Lock()
        self._auth_key = get_control_auth_key()
        self._warned_no_auth = False

        allow_unsigned_env = os.getenv("ALLOW_UNSIGNED_SCHEDULER_TELEMETRY", "").strip().lower()
        if allow_unsigned_env:
            allow_unsigned = allow_unsigned_env in {"1", "true", "yes", "on"}
        else:
            allow_unsigned = bool(CONFIG.get("ALLOW_UNSIGNED_SCHEDULER_TELEMETRY", True))

        if not self._auth_key and not allow_unsigned:
            raise RuntimeError(
                "Scheduler telemetry auth key missing. Set MAV_AUTH_KEY or DRONE_PSK, "
                "or explicitly opt out with ALLOW_UNSIGNED_SCHEDULER_TELEMETRY=1."
            )

        # Batch buffer
        self._batch: List[Dict[str, Any]] = []
        self._batch_start: float = 0.0

    # ---- low-level send ------------------------------------------------- #

    def _send_raw(self, payload: dict):
        """Fire-and-forget UDP send to all target drones."""
        try:
            data = json.dumps(payload).encode("utf-8")
            for addr in self.target_addrs:
                self.sock.sendto(data, addr)
        except Exception:
            pass  # Best-effort

    # ---- public API ----------------------------------------------------- #

    def add_sample(self, snapshot: dict):
        """Add a single telemetry snapshot to the batch buffer.

        Automatically flushes when the batch is full or the interval
        expires.
        """
        with self._lock:
            now = time.monotonic()
            if not self._batch:
                self._batch_start = now

            self.seq += 1
            sample = dict(snapshot)
            sample["batch_seq"] = self.seq
            self._batch.append(sample)

            # Flush conditions
            if (len(self._batch) >= TELEMETRY_BATCH_SIZE or
                    now - self._batch_start >= TELEMETRY_BATCH_INTERVAL_S):
                self._flush_locked()

    def flush(self):
        """Force-send whatever is currently buffered."""
        with self._lock:
            self._flush_locked()

    def _flush_locked(self):
        """Internal flush (caller holds self._lock)."""
        if not self._batch:
            return
        envelope = {
            "schema": self.BATCH_SCHEMA,
            "batch_wall_ns": time.time_ns(),
            "count": len(self._batch),
            "samples": self._batch,
        }

        if self._auth_key:
            nonce_hex = create_nonce_hex()
            mac_hex = compute_telemetry_mac(envelope=envelope, nonce_hex=nonce_hex, key=self._auth_key)
            envelope = {**envelope, "nonce": nonce_hex, "mac": mac_hex}
        elif not self._warned_no_auth:
            log("WARNING: telemetry auth key missing; sending unsigned telemetry")
            self._warned_no_auth = True

        self._send_raw(envelope)
        self._batch = []
        self._batch_start = 0.0

    def close(self):
        self.flush()
        try:
            self.sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Control Server  (TCP – GCS listens, Drone sends commands)
# ---------------------------------------------------------------------------

class ControlServer(ControlServerBase):
    """TCP JSON-RPC server that accepts commands from the drone scheduler.

    Supported commands
    ~~~~~~~~~~~~~~~~~~
    ping           – liveness check
    status         – proxy and MAVProxy health
    configure      – accept scheduling parameters from drone
    start_proxy    – start GCS PQC proxy for a given suite
    prepare_rekey  – tear down current proxy (drone about to switch suite)
    stop           – full shutdown
    get_suites     – return available suite names
    chronos_sync   – serve an NTP-lite clock synchronisation round
    """

    def __init__(self, proxy: GcsProxyManager):
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

        auth_key = get_control_auth_key()
        allow_unsigned = os.getenv("ALLOW_UNSIGNED_SCHEDULER_CONTROL", "1").strip().lower() in {"1", "true", "yes", "on"}
        require_auth = False if allow_unsigned else bool(auth_key)

        super().__init__(
            proxy,
            GCS_CONTROL_HOST,
            GCS_CONTROL_PORT,
            ALL_SUITES,
            allowed_senders=allowed_senders,
            auth_key=auth_key,
            require_auth=require_auth,
            default_duration_s=10.0,
        )

        self.clock_sync = ClockSync(
            smoothing=bool(CONFIG.get("CLOCK_SYNC_SMOOTHING", False)),
            window=int(CONFIG.get("CLOCK_SYNC_WINDOW", 3)),
        )

        # Persistent MAVProxy subprocess handle
        self.mavproxy_proc: Optional[ManagedProcess] = None

        # Telemetry subsystem
        self.telemetry = TelemetrySender(DRONE_HOST, GCS_TELEMETRY_PORT)
        self.metrics_collector = GcsMetricsCollector(
            mavlink_host="127.0.0.1",
            mavlink_port=GCS_TELEMETRY_SNIFF_PORT,
            proxy_manager=self.proxy,
            log_dir=LOGS_DIR / "telemetry",
        )

        self._telemetry_thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------ #
    # Persistent MAVProxy  (GCS side)
    # ------------------------------------------------------------------ #

    def start_persistent_mavproxy(self) -> bool:
        """Start a long-lived MAVProxy for QGC and telemetry sniffing.

        Data path
        ~~~~~~~~~
        PQC Proxy → (GCS_PLAIN_RX_PORT) → MAVProxy →
            ├── udp:127.0.0.1:QGC_PORT        (QGroundControl)
            └── udp:127.0.0.1:SNIFF_PORT      (GcsMetricsCollector)
        """
        bind_host = str(CONFIG.get("GCS_PLAINTEXT_BIND", "0.0.0.0"))
        master_str = f"udpin:{bind_host}:{GCS_PLAIN_RX_PORT}"

        cmd = [
            sys.executable, "-m", "MAVProxy.mavproxy",
            f"--master={master_str}",
            "--dialect=ardupilotmega",
            "--nowait",
            "--map",
            "--console",
            f"--out=udp:127.0.0.1:{QGC_PORT}",
            f"--out=udp:127.0.0.1:{GCS_TELEMETRY_SNIFF_PORT}",
        ]
        extra_sniff_port = os.getenv("GCS_EXTRA_SNIFF_PORT", "").strip()
        if extra_sniff_port:
            try:
                port = int(extra_sniff_port)
                if port > 0 and port != GCS_TELEMETRY_SNIFF_PORT and port != QGC_PORT:
                    cmd.append(f"--out=udp:127.0.0.1:{port}")
                    log(f"Extra MAVLink sniff output enabled on 127.0.0.1:{port}")
            except ValueError:
                log(f"Ignoring invalid GCS_EXTRA_SNIFF_PORT={extra_sniff_port!r}")

        log(f"Starting persistent MAVProxy: {' '.join(cmd)}")

        ts_str = time.strftime("%Y%m%d-%H%M%S")
        log_path = LOGS_DIR / f"mavproxy_gcs_{ts_str}.log"

        try:
            fh = open(log_path, "w", encoding="utf-8")
        except Exception:
            fh = subprocess.DEVNULL

        # Platform-specific I/O handles
        stdout_arg = fh
        stderr_arg = subprocess.STDOUT
        stdin_arg = subprocess.DEVNULL
        if sys.platform == "win32":
            # On Windows prompt_toolkit needs a real console; suppress
            # stdout/stderr to avoid crash while still capturing to log.
            stdout_arg = None
            stderr_arg = None
            stdin_arg = None

        env = os.environ.copy()
        env["TERM"] = "dumb"  # Prevent prompt_toolkit escape issues

        self.mavproxy_proc = ManagedProcess(
            cmd=cmd,
            name="mavproxy-gcs",
            stdout=stdout_arg,
            stderr=stderr_arg,
            stdin=stdin_arg,
            new_console=True,
            env=env,
        )

        if not self.mavproxy_proc.start():
            log("MAVProxy failed to start")
            return False

        # Update metrics collector with the process handle
        self.metrics_collector.mavproxy_proc = self.mavproxy_proc

        # Wait for TCP handshake port or process to settle
        if wait_for_tcp_port(TCP_CTRL_PORT, timeout=5.0):
            log("Persistent MAVProxy started (TCP port open)")
            return True
        if self.mavproxy_proc.is_running():
            log("Persistent MAVProxy started (process alive, port not yet ready)")
            return True

        log("Persistent MAVProxy failed to start")
        return False

    # ------------------------------------------------------------------ #
    # TCP control server lifecycle
    # ------------------------------------------------------------------ #

    def on_start(self):
        # Start GCS metrics collector
        self.metrics_collector.start()

        # Start telemetry loop (sends batched snapshots to drone)
        self._telemetry_thread = threading.Thread(
            target=self._telemetry_loop, daemon=True, name="telem-sender"
        )
        self._telemetry_thread.start()

    def on_stop(self):
        if self._telemetry_thread:
            self._telemetry_thread.join(timeout=2.0)
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

    # ------------------------------------------------------------------ #
    # Telemetry loop  (5 Hz → batched at ~1 Hz to drone)
    # ------------------------------------------------------------------ #

    def _telemetry_loop(self):
        """Collect GcsMetricsCollector snapshots and feed into batcher."""
        interval_s = 1.0 / TELEMETRY_HZ
        while self.running:
            try:
                snapshot = self.metrics_collector.get_snapshot()
                self.telemetry.add_sample(snapshot)
            except Exception:
                pass
            time.sleep(interval_s)

        # Final flush on shutdown
        try:
            self.telemetry.flush()
        except Exception:
            pass

    def _status_payload(self) -> dict:
        return {
            "mavproxy_running": bool(self.mavproxy_proc and self.mavproxy_proc.is_running()),
        }

    def on_configure(self, request: dict):
        self.duration = float(request.get("duration", self.duration))
        log(f"Configured: duration={self.duration}s")

    def after_proxy_started(self, request: dict) -> Optional[str]:
        allow_no_mavproxy = os.getenv("ALLOW_MAVPROXY_FAIL", "1").strip().lower() in {"1", "true", "yes", "on"}
        if not allow_no_mavproxy and not (self.mavproxy_proc and self.mavproxy_proc.is_running()):
            log("WARNING: persistent MAVProxy is not running")
            return "mavproxy_not_running"
        return None

    def on_prepare_rekey(self, request: dict):
        log("prepare_rekey: stopping GCS proxy …")

    def on_stop_command(self, request: dict):
        log("stop command received – tearing down")
        if self.mavproxy_proc:
            try:
                self.mavproxy_proc.stop()
            except Exception:
                pass
            self.mavproxy_proc = None

    def handle_custom_command(self, request: dict) -> Optional[dict]:
        if request.get("cmd") == "chronos_sync":
            try:
                return self.clock_sync.server_handle_sync(request)
            except Exception as exc:
                return {"status": "error", "message": str(exc)}
        return None


# ---------------------------------------------------------------------------
# Process cleanup
# ---------------------------------------------------------------------------

def cleanup_stale_processes():
    """Best-effort cleanup of orphaned mavproxy / proxy processes."""
    my_pid = os.getpid()
    targets = ["mavproxy", "core.run_proxy"]

    if sys.platform.startswith("win"):
        for t in targets:
            query = (
                f"name='python.exe' and commandline like '%{t}%' "
                f"and ProcessId!={my_pid}"
            )
            cmd = f'wmic process where "{query}" call terminate'
            try:
                subprocess.run(
                    cmd, shell=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass
    else:
        for t in targets:
            subprocess.run(
                ["pkill", "-f", t],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    time.sleep(1.0)


# ===========================================================================
# Main
# ===========================================================================

def main() -> int:
    parser = argparse.ArgumentParser(
        description="GCS MAV-to-MAV PQC Tunnel Follower",
    )
    parser.add_argument(
        "--no-mavproxy",
        action="store_true",
        help="Skip starting persistent MAVProxy (for testing without FC)",
    )
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Skip stale-process cleanup on startup",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-12s  %(levelname)-7s  %(message)s",
    )

    print("=" * 60)
    print("  GCS MAV-to-MAV PQC Tunnel Follower")
    print("=" * 60)

    # Dump configuration for debugging
    cfg_dump = {
        "DRONE_HOST": DRONE_HOST,
        "GCS_HOST": GCS_HOST,
        "GCS_CONTROL_BIND": f"{GCS_CONTROL_HOST}:{GCS_CONTROL_PORT}",
        "GCS_PLAINTEXT_RX": GCS_PLAIN_RX_PORT,
        "GCS_PLAINTEXT_TX": GCS_PLAIN_TX_PORT,
        "QGC_PORT": QGC_PORT,
        "SNIFF_PORT": GCS_TELEMETRY_SNIFF_PORT,
        "TELEMETRY_TARGET": f"{DRONE_HOST}:{GCS_TELEMETRY_PORT}",
    }
    log("Configuration:")
    for k, v in cfg_dump.items():
        log(f"  {k}: {v}")

    # Cleanup stale processes
    if not args.no_cleanup:
        cleanup_stale_processes()

    atexit.register(cleanup_stale_processes)

    # Initialise components
    proxy = GcsProxyManager()
    control = ControlServer(proxy)

    # Initialize Swarm Context for GCS (Root Leader)
    from hierarchical_swarm.context import SwarmContext
    swarm = SwarmContext(
        drone_id="root-00",
        role="ROOT_LEADER",
    )
    swarm.initialize()

    # Start persistent MAVProxy
    if not args.no_mavproxy:
        ok = control.start_persistent_mavproxy()
        if ok:
            log("Persistent MAVProxy started")
        else:
            log("ERROR: persistent MAVProxy failed – aborting")
            swarm.shutdown()
            return 2
    else:
        log("Persistent MAVProxy skipped (--no-mavproxy)")

    # Start control server + telemetry loop
    control.start()

    log("GCS follower running.  Waiting for commands from drone …")

    # Block until interrupted
    shutdown = threading.Event()

    def _sighandler(sig, frame):
        log("Interrupted – shutting down")
        shutdown.set()

    signal.signal(signal.SIGINT, _sighandler)
    signal.signal(signal.SIGTERM, _sighandler)

    try:
        while not shutdown.is_set():
            shutdown.wait(timeout=1.0)
    finally:
        log("Shutting down …")
        swarm.shutdown()
        control.stop()
        proxy.stop()

    log("GCS follower stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())


