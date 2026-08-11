#!/usr/bin/env python3
"""
Drone Scheduler – MAV-to-MAV PQC Tunnel Controller
sscheduler/sdrone.py

REVERSED CONTROL: Drone is the controller, GCS follows.

Data flow (bidirectional MAVLink):
  FC (serial) → MAVProxy → plaintext UDP → PQC Proxy → encrypted UDP → GCS
  FC (serial) ← MAVProxy ← plaintext UDP ← PQC Proxy ← encrypted UDP ← GCS

Two scheduling policies:
  deterministic  – Fixed-interval cycling through filtered suites (benchmark)
  intelligent    – Adaptive selection driven by battery, thermal, link quality,
                   mission criticality, and AEAD / NIST-level constraints (flight)

The drone never generates software test traffic.  All data flowing through
the tunnel is real MAVLink produced by MAVProxy ↔ flight-controller.

Usage:
  python -m sscheduler.sdrone --policy intelligent
  python -m sscheduler.sdrone --policy deterministic --duration 10
"""

import os
import sys
import time
import json
import socket
import signal
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
from core.suites import get_suite, list_benchmark_suites, list_runtime_suites, list_suites, normalize_aead_token
from core.process import ManagedProcess
from sscheduler.policy import (
    TelemetryAwarePolicyV2,
    EnergyAwarePolicy,
    PolicyAction,
    PolicyOutput,
    DecisionInput,
    DetectorLevel,
)
from sscheduler.detector_manager import DetectorManager
from sscheduler.benchmark_policy import BenchmarkPolicy, BenchmarkAction
from sscheduler.telemetry_window import TelemetryWindow
from sscheduler.local_mon import LocalMonitor
from sscheduler.gcs_client import (
    resolve_control_host,
    send_gcs_command as _send_gcs_command,
    wait_for_gcs as _wait_for_gcs,
)
from sscheduler.control_security import get_control_auth_key, verify_telemetry_mac

try:
    from core.clock_sync import ClockSync
except ImportError:
    ClockSync = None  # type: ignore

# ---------------------------------------------------------------------------
# Configuration – single source of truth from core.config
# ---------------------------------------------------------------------------

DRONE_HOST = str(CONFIG["DRONE_HOST"])
GCS_HOST = str(CONFIG["GCS_HOST"])
DRONE_PLAIN_RX = int(CONFIG["DRONE_PLAINTEXT_RX"])
DRONE_PLAIN_TX = int(CONFIG["DRONE_PLAINTEXT_TX"])
GCS_CONTROL_HOST = resolve_control_host(CONFIG.get("GCS_CONTROL_HOST", CONFIG.get("GCS_HOST")))
GCS_CONTROL_PORT = int(CONFIG.get("GCS_CONTROL_PORT", 48080))
GCS_TELEMETRY_PORT = int(CONFIG.get("GCS_TELEMETRY_PORT", 52080))

SECRETS_DIR = Path(__file__).parent.parent / "secrets" / "matrix"
ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs" / "sscheduler" / "drone"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# Scheduler tick interval (seconds)
EVAL_INTERVAL_S = 1.0
# Cooldown after a suite switch to prevent rapid thrashing
SWITCH_COOLDOWN_S = 5.0

_suites_dict = list_suites()
ALL_SUITES = [{"name": k, **v} for k, v in _suites_dict.items()]


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def log(msg: str):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"[{ts}] [sdrone] {msg}", flush=True)


# ---------------------------------------------------------------------------
# GCS Control Client (TCP JSON-RPC)
# ---------------------------------------------------------------------------

def send_gcs_command(cmd: str, **params) -> dict:
    """Send a JSON command to the GCS control server over TCP."""
    return _send_gcs_command(cmd, host=GCS_CONTROL_HOST, port=GCS_CONTROL_PORT, **params)


def wait_for_gcs(timeout: float = 120.0) -> bool:
    """Block until GCS control server responds to ping."""
    return _wait_for_gcs(timeout=timeout, host=GCS_CONTROL_HOST, port=GCS_CONTROL_PORT)


# ---------------------------------------------------------------------------
# Drone Proxy Manager
# ---------------------------------------------------------------------------

class DroneProxyManager:
    """Manages the drone-side PQC proxy subprocess (core.run_proxy drone)."""

    def __init__(self):
        self.proc: Optional[ManagedProcess] = None
        self.current_suite: Optional[str] = None
        self.current_aead: Optional[str] = None
        self._last_log: Optional[Path] = None
        self._log_handle = None

    def start(self, suite_name: str, *, aead_token: Optional[str] = None) -> bool:
        if self.proc and self.proc.is_running():
            self.stop()

        suite = get_suite(suite_name)
        if not suite:
            log(f"Unknown suite: {suite_name}")
            return False
        resolved_aead = normalize_aead_token(aead_token) if aead_token else str(suite.get("aead_token", "aesgcm"))

        peer_pubkey = SECRETS_DIR / suite_name / "gcs_signing.pub"
        if not peer_pubkey.exists():
            log(f"Missing public key: {peer_pubkey}")
            return False

        cmd = [
            sys.executable, "-m", "core.run_proxy", "drone",
            "--suite", suite_name,
            "--aead", resolved_aead,
            "--peer-pubkey-file", str(peer_pubkey),
            "--quiet",
            "--status-file", str(LOGS_DIR / "drone_status.json"),
        ]

        ts = time.strftime("%Y%m%d-%H%M%S")
        log_path = LOGS_DIR / f"proxy_{suite_name}_{resolved_aead}_{ts}.log"
        log(f"Starting proxy: {suite_name} (aead={resolved_aead})")

        try:
            self._log_handle = open(log_path, "w", encoding="utf-8")
        except Exception:
            self._log_handle = subprocess.DEVNULL

        self.proc = ManagedProcess(
            cmd=cmd,
            name=f"proxy-{suite_name}",
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
        )
        if not self.proc.start():
            return False

        self._last_log = log_path
        self.current_suite = suite_name
        self.current_aead = resolved_aead

        # Wait for proxy startup + handshake
        time.sleep(3.0)
        if not self.proc.is_running():
            log(f"Proxy exited early for {suite_name}")
            self._dump_log_tail()
            return False
        return True

    def stop(self):
        if self.proc:
            self.proc.stop()
            self.proc = None
            self.current_suite = None
            self.current_aead = None
        if self._log_handle not in (None, subprocess.DEVNULL):
            try:
                self._log_handle.close()
            except Exception:
                pass
        self._log_handle = None

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.is_running()

    def _dump_log_tail(self, n: int = 20):
        if not self._last_log or not self._last_log.exists():
            return
        try:
            lines = self._last_log.read_text(encoding="utf-8").splitlines()[-n:]
            for ln in lines:
                log(f"  | {ln}")
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Telemetry Receiver  (GCS → Drone, UDP)
# ---------------------------------------------------------------------------

class TelemetryReceiver:
    """Listens for GCS telemetry packets and feeds them into TelemetryWindow.

    Accepts both individual packets and batched envelopes
    (schema ``uav.pqc.telemetry.batch.v1``).
    """

    def __init__(self, port: int, window: TelemetryWindow):
        self.port = port
        self.window = window
        self._sock: Optional[socket.socket] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._auth_key = get_control_auth_key()
        allow_unsigned = os.getenv("ALLOW_UNSIGNED_SCHEDULER_TELEMETRY", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        self._require_auth = True if not allow_unsigned else bool(self._auth_key)
        if self._require_auth and not self._auth_key:
            raise RuntimeError(
                "Scheduler telemetry auth key missing. Set MAV_AUTH_KEY or DRONE_PSK, "
                "or explicitly opt out with ALLOW_UNSIGNED_SCHEDULER_TELEMETRY=1."
            )
        self._nonce_ttl_s = 120.0
        self._nonce_lock = threading.Lock()
        self._seen_nonces_expiry: Dict[str, float] = {}

        raw_allowed = CONFIG.get("MAV_ALLOWED_SENDERS", [])
        allowed_senders: List[str] = []
        if isinstance(raw_allowed, str):
            allowed_senders = [p.strip() for p in raw_allowed.split(",") if p.strip()]
        elif isinstance(raw_allowed, (list, tuple, set)):
            allowed_senders = [str(p).strip() for p in raw_allowed if str(p).strip()]
        if GCS_HOST and GCS_HOST not in allowed_senders:
            allowed_senders.append(GCS_HOST)
        self._allowed_senders = set(allowed_senders)

    def start(self):
        if self._running:
            return
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("0.0.0.0", self.port))
        self._sock.settimeout(1.0)
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log(f"Telemetry receiver listening on :{self.port}")

    def _loop(self):
        while self._running:
            try:
                data, addr = self._sock.recvfrom(65535)
                peer_ip = str(addr[0]) if isinstance(addr, tuple) and addr else ""
                if self._allowed_senders and peer_ip not in self._allowed_senders:
                    continue

                packet = json.loads(data.decode("utf-8"))
                if not isinstance(packet, dict):
                    continue

                if self._require_auth:
                    nonce_hex = str(packet.get("nonce", "") or "").strip()
                    mac_hex = str(packet.get("mac", "") or "").strip()
                    if not nonce_hex or not mac_hex or not self._auth_key:
                        continue
                    envelope = {k: v for k, v in packet.items() if k not in {"nonce", "mac"}}
                    if not verify_telemetry_mac(
                        envelope=envelope,
                        nonce_hex=nonce_hex,
                        mac_hex=mac_hex,
                        key=self._auth_key,
                    ):
                        continue
                    if not self._nonce_check_and_store(nonce_hex):
                        continue

                now = time.monotonic()

                # Handle batched envelope
                schema = packet.get("schema", "")
                if schema.startswith("uav.pqc.telemetry.batch"):
                    for sample in packet.get("samples", []):
                        self.window.add(now, sample)
                else:
                    # Single-sample packet (legacy / fallback)
                    self.window.add(now, packet)
            except socket.timeout:
                continue
            except Exception:
                pass

    def _nonce_check_and_store(self, nonce_hex: str) -> bool:
        now = time.monotonic()
        expiry = now + self._nonce_ttl_s
        with self._nonce_lock:
            if self._seen_nonces_expiry:
                stale = [n for n, exp in self._seen_nonces_expiry.items() if exp <= now]
                for n in stale:
                    self._seen_nonces_expiry.pop(n, None)

            if nonce_hex in self._seen_nonces_expiry:
                return False

            self._seen_nonces_expiry[nonce_hex] = expiry
            return True

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._sock:
            self._sock.close()


# ---------------------------------------------------------------------------
# Telemetry Reporter  (Drone → logfile, periodic status dump)
# ---------------------------------------------------------------------------

class TelemetryReporter:
    """Periodically logs a combined snapshot of local + GCS telemetry
    to a JSONL file for post-flight analysis."""

    def __init__(
        self,
        local_mon: LocalMonitor,
        telem_window: TelemetryWindow,
        log_dir: Path,
    ):
        self._local = local_mon
        self._window = telem_window
        self._log_path = log_dir / "drone_telemetry.jsonl"
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            try:
                lm = self._local.get_metrics()
                gs = self._window.summarize(time.monotonic())
                record = {
                    "ts_ns": time.time_ns(),
                    "local": {
                        "battery_mv": lm.battery_mv,
                        "battery_roc": round(lm.battery_roc, 2),
                        "temp_c": round(lm.temp_c, 1),
                        "temp_roc": round(lm.temp_roc, 2),
                        "armed": lm.armed,
                        "cpu_pct": round(lm.cpu_pct, 1),
                    },
                    "gcs": {
                        "sample_count": gs["sample_count"],
                        "rx_pps_median": gs["rx_pps_median"],
                        "gap_p95_ms": gs["gap_p95_ms"],
                        "silence_max_ms": gs["silence_max_ms"],
                        "jitter_ms": gs["jitter_ms"],
                        "confidence": gs["confidence"],
                    },
                }
                with open(self._log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record) + "\n")
            except Exception:
                pass
            time.sleep(2.0)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)


# ===========================================================================
# MAV Tunnel Scheduler
# ===========================================================================

class MavTunnelScheduler:
    """Orchestrates a MAV-to-MAV PQC tunnel with policy-driven suite selection.

    Architecture
    ~~~~~~~~~~~~
    * **MAVProxy** (persistent): bridges FC serial ↔ plaintext UDP ports.
    * **PQC Proxy** (per-suite): encrypts plaintext UDP ↔ encrypted UDP.
    * **LocalMonitor**: battery, thermal, armed state from Pixhawk.
    * **TelemetryReceiver**: GCS link-quality metrics via UDP.
    * **Policy Engine**: deterministic (benchmark) *or* intelligent (flight).

    Intelligent Policy Inputs (from settings.json)
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    * mission_criticality  – low / medium / high
    * max_nist_level       – L1 / L3 / L5 ceiling
    * allowed_aead         – aesgcm / chacha20poly1305 / ascon128
    * battery thresholds   – critical_mv, low_mv, warn_mv, rate_warn_mv_per_min
    * thermal thresholds   – critical_c, warn_c, rate_warn_c_per_min
    * link thresholds      – min_pps, max_gap_ms, max_blackout_count
    * rekey limits         – min_stable_s, max_per_window, window_s, blacklist_ttl_s
    * hysteresis timers    – downgrade_s (fast), upgrade_s (slow)

    Decision Flow
    ~~~~~~~~~~~~~
    1. Collect local metrics  (battery_mv, temp_c, armed, rates-of-change)
    2. Collect GCS telemetry  (rx_pps, gap_p95, silence, jitter, blackouts)
    3. Build immutable DecisionInput snapshot
    4. policy.evaluate(inp) → PolicyOutput  (HOLD / UPGRADE / DOWNGRADE /
       REKEY / ROLLBACK)
    5. Execute: coordinate GCS prepare_rekey → stop proxy → start new suite
    """

    def __init__(self, args):
        self.args = args
        self.running = True

        # --- sub-components ---
        self.proxy = DroneProxyManager()
        self.local_mon = LocalMonitor(
            mav_port=int(CONFIG.get("MAV_LOCAL_OUT_PORT_2", 14551)),
        )
        self.telem_window = TelemetryWindow(window_s=5.0)
        self.telem_rx = TelemetryReceiver(GCS_TELEMETRY_PORT, self.telem_window)
        self.reporter = TelemetryReporter(self.local_mon, self.telem_window, LOGS_DIR)
        self.mavproxy_proc: Optional[ManagedProcess] = None
        self.clock_sync = ClockSync(
            smoothing=bool(CONFIG.get("CLOCK_SYNC_SMOOTHING", False)),
            window=int(CONFIG.get("CLOCK_SYNC_WINDOW", 3)),
        ) if ClockSync else None

        # --- state ---
        self.current_suite: Optional[str] = None
        self.last_switch_mono: float = 0.0
        self.cooldown_until_mono: float = 0.0
        self.local_epoch: int = 0

        # --- resolve suites ---
        self.suites_to_run = self._resolve_suites()
        if not self.suites_to_run:
            raise RuntimeError("No suites available to run")

        # --- policy ---
        forced_detector = str(getattr(args, "detector_level", "NONE") or "NONE").upper()
        if args.policy == "deterministic":
            self.policy_mode = "deterministic"
            self.bench_policy = BenchmarkPolicy(
                cycle_interval_s=float(args.duration),
                suite_list=self.suites_to_run,
            )
            self.intel_policy = None
            self.energy_policy = None
            self.detector_mgr = DetectorManager() if forced_detector != DetectorLevel.NONE.value else None
        elif args.policy == "energy_aware":
            self.policy_mode = "energy_aware"
            self.bench_policy = None
            self.intel_policy = None
            self.energy_policy = EnergyAwarePolicy()
            self.detector_mgr = DetectorManager()
        else:
            self.policy_mode = "intelligent"
            self.bench_policy = None
            self.intel_policy = TelemetryAwarePolicyV2()
            self.energy_policy = None
            self.detector_mgr = None
            # Ensure at least one suite survives the filter
            if not self.intel_policy.filtered_suites:
                raise RuntimeError(
                    "Intelligent policy filtered all suites – check "
                    "settings.json (allowed_aead, max_nist_level)"
                )

        log(f"Policy: {self.policy_mode}  |  suites: {len(self.suites_to_run)}")

    # ------------------------------------------------------------------ #
    # Suite resolution
    # ------------------------------------------------------------------ #

    def _resolve_suites(self) -> List[str]:
        if self.args.suite:
            return [self.args.suite]
        suite_map = list_benchmark_suites() if self.args.policy == "deterministic" else list_runtime_suites()
        names = list(suite_map.keys())
        if self.args.nist_level:
            names = [sid for sid, cfg in suite_map.items() if cfg.get("nist_level") == self.args.nist_level]
        if self.args.max_suites:
            names = names[: self.args.max_suites]
        return names

    # ------------------------------------------------------------------ #
    # MAVProxy (persistent)
    # ------------------------------------------------------------------ #

    def _start_mavproxy(self) -> bool:
        """Start persistent MAVProxy bridging FC serial ↔ plaintext UDP."""
        master = self.args.mav_master
        out_port = DRONE_PLAIN_TX

        cmd = [
            sys.executable, "-m", "MAVProxy.mavproxy",
            f"--master={master}",
            f"--out=udp:127.0.0.1:{out_port}",
            "--dialect=ardupilotmega",
            "--nowait",
            "--daemon",
        ]
        if os.getenv("DRONE_MAVPROXY_BIDIR_IN", "").strip().lower() in {"1", "true", "yes", "on"}:
            cmd.insert(4, f"--master=udpin:127.0.0.1:{DRONE_PLAIN_RX}")

        ts_str = time.strftime("%Y%m%d-%H%M%S")
        log_path = LOGS_DIR / f"mavproxy_{ts_str}.log"
        try:
            fh = open(log_path, "w", encoding="utf-8")
        except Exception:
            fh = subprocess.DEVNULL

        log(f"Starting MAVProxy: master={master}  out=127.0.0.1:{out_port}")
        self.mavproxy_proc = ManagedProcess(
            cmd=cmd,
            name="mavproxy-drone",
            stdout=fh,
            stderr=subprocess.STDOUT,
            new_console=False,
        )
        if not self.mavproxy_proc.start():
            return False
        time.sleep(1.0)
        return self.mavproxy_proc.is_running()

    # ------------------------------------------------------------------ #
    # Clock synchronisation (Chronos)
    # ------------------------------------------------------------------ #

    def _sync_clock(self):
        if not self.clock_sync:
            return
        try:
            t1 = time.time()
            resp = send_gcs_command("chronos_sync", t1=t1)
            t4 = time.time()
            if resp.get("status") == "ok":
                offset = self.clock_sync.update_from_rpc(t1, t4, resp)
                log(f"Clock-sync offset (GCS − Drone): {offset:.6f} s")
        except Exception as e:
            log(f"Clock-sync error: {e}")

    # ------------------------------------------------------------------ #
    # Suite life-cycle helpers
    # ------------------------------------------------------------------ #

    def _coordinate_suite_start(self, suite_name: str, *, aead_token: Optional[str] = None) -> bool:
        """Tell GCS to start its proxy, then start local proxy.

        GCS proxy must start first because the TCP handshake requires
        GCS to listen and drone to connect.
        """
        if aead_token:
            log(f"Requesting GCS proxy for {suite_name} (aead={aead_token}) …")
        else:
            log(f"Requesting GCS proxy for {suite_name} …")
        resp = send_gcs_command("start_proxy", suite=suite_name, aead=aead_token)
        if resp.get("status") != "ok":
            log(f"GCS start_proxy failed: {resp}")
            return False

        # Poll until GCS proxy is ready
        deadline = time.time() + 20.0
        while time.time() < deadline:
            time.sleep(0.5)
            st = send_gcs_command("status")
            if st.get("proxy_running"):
                break
        else:
            log("GCS proxy did not become ready in time")
            return False

        # Start local proxy (connects to GCS)
        if not self.proxy.start(suite_name, aead_token=aead_token):
            log(f"Local proxy start failed for {suite_name}")
            return False

        # Handshake settling
        time.sleep(1.0)

        self.current_suite = suite_name
        self.last_switch_mono = time.monotonic()
        self.cooldown_until_mono = self.last_switch_mono + SWITCH_COOLDOWN_S
        self.local_epoch += 1
        active_aead = aead_token or self.proxy.current_aead or str(get_suite(suite_name).get("aead_token", "aesgcm"))
        log(f"Suite ACTIVE: {suite_name} / {active_aead}  (epoch {self.local_epoch})")
        return True

    def _switch_suite(self, target_suite: str, *, target_aead: Optional[str] = None) -> bool:
        """Full suite switch: stop current → coordinate new."""
        current_aead = self.proxy.current_aead or ""
        if target_aead:
            log(f"Suite switch: {self.current_suite}/{current_aead} → {target_suite}/{target_aead}")
        else:
            log(f"Suite switch: {self.current_suite}/{current_aead} → {target_suite}")

        # 1. Tell GCS to tear down its side
        resp = send_gcs_command("prepare_rekey")
        if resp.get("status") != "ok":
            log(f"GCS prepare_rekey failed: {resp}")
            return False

        # 2. Stop local proxy
        self.proxy.stop()
        time.sleep(0.5)

        # 3. Stand up the new suite
        return self._coordinate_suite_start(target_suite, aead_token=target_aead)

    # ------------------------------------------------------------------ #
    # Decision-input builder
    # ------------------------------------------------------------------ #

    def _read_proxy_counters(self) -> dict:
        """Read the proxy's drone_status.json for AEAD timing data."""
        status_file = LOGS_DIR / "drone_status.json"
        try:
            data = json.loads(status_file.read_text(encoding="utf-8"))
            return data.get("counters", {})
        except Exception:
            return {}

    def _build_decision_input(self) -> DecisionInput:
        """Assemble a DecisionInput from LocalMonitor + TelemetryWindow + proxy counters."""
        now_s = time.monotonic()
        now_ms = now_s * 1000.0

        lm = self.local_mon.get_metrics()
        gs = self.telem_window.summarize(now_s)
        flight = self.telem_window.get_flight_state()

        telemetry_valid = gs["sample_count"] > 0
        telemetry_age_ms = gs.get("telemetry_age_ms", -1.0)
        if telemetry_age_ms < 0:
            telemetry_valid = False

        synced = 0.0
        if self.clock_sync:
            try:
                synced = self.clock_sync.now()
            except Exception:
                synced = time.time()

        # Derive blackout count from silence duration
        silence_ms = max(gs.get("silence_max_ms", 0.0), 0.0)
        blackout_count = 0
        if silence_ms > 1000.0:
            blackout_count = int(silence_ms / 1000.0)

        # Read proxy status/counters (AEAD timing for energy-aware policy)
        status_file = LOGS_DIR / "drone_status.json"
        try:
            status_payload = json.loads(status_file.read_text(encoding="utf-8"))
        except Exception:
            status_payload = {}
        pc = status_payload.get("counters", {})
        part_b = pc.get("part_b_metrics", {})
        if not isinstance(part_b, dict):
            part_b = {}
        current_aead = str(status_payload.get("aead_token", "") or "").strip().lower()
        if not current_aead:
            data_aead_id = str(status_payload.get("data_aead_id", "") or "")
            if data_aead_id.startswith("dap-"):
                current_aead = data_aead_id[4:].strip().lower()
        if not current_aead:
            current_aead = str(self.proxy.current_aead or "").strip().lower()
        if not current_aead:
            fallback_suite = self.current_suite or (self.suites_to_run[0] if self.suites_to_run else "")
            if fallback_suite:
                current_aead = str(get_suite(fallback_suite).get("aead_token", "aesgcm")).lower()
            else:
                current_aead = "aesgcm"

        # Convert ms → ns for the policy's ns-based fields
        def _ms_to_ns(v: object) -> float:
            try:
                return float(v) * 1_000_000.0
            except (TypeError, ValueError):
                return 0.0

        return DecisionInput(
            mono_ms=now_ms,
            telemetry_valid=telemetry_valid,
            telemetry_age_ms=max(telemetry_age_ms, 0.0),
            sample_count=gs["sample_count"],
            rx_pps_median=gs["rx_pps_median"],
            gap_p95_ms=gs["gap_p95_ms"],
            silence_max_ms=silence_ms,
            jitter_ms=gs["jitter_ms"],
            blackout_count=blackout_count,
            battery_mv=lm.battery_mv,
            battery_roc=lm.battery_roc,
            temp_c=lm.temp_c,
            temp_roc=lm.temp_roc,
            armed=lm.armed or flight.get("armed", False),
            current_suite=self.current_suite or "",
            local_epoch=self.local_epoch,
            last_switch_mono_ms=self.last_switch_mono * 1000.0,
            cooldown_until_mono_ms=self.cooldown_until_mono * 1000.0,
            current_aead=current_aead,
            # Proxy performance
            aead_encrypt_avg_ns=_ms_to_ns(part_b.get("aead_encrypt_avg_ms")),
            aead_decrypt_avg_ns=_ms_to_ns(part_b.get("aead_decrypt_avg_ms")),
            proxy_enc_in=int(pc.get("enc_in", 0) or 0),
            proxy_enc_out=int(pc.get("enc_out", 0) or 0),
            proxy_drop_total=int(pc.get("drops", 0) or 0),
            proxy_uptime_s=max(1.0, now_s - self.last_switch_mono),
            cpu_pct=lm.cpu_pct,
            synced_time=synced,
            # Axis 3: DDoS detector state
            detector_level=(
                self.detector_mgr.current_level
                if self.detector_mgr else DetectorLevel.NONE.value
            ),
            detector_active=(
                self.detector_mgr.is_running
                if self.detector_mgr else False
            ),
            detector_warmup=(
                self.detector_mgr.is_warming_up
                if self.detector_mgr else False
            ),
        )

    # ------------------------------------------------------------------ #
    # Scheduler loops
    # ------------------------------------------------------------------ #

    def _run_deterministic(self):
        """Fixed-interval cycling through all suites (benchmark mode).

        Uses BenchmarkPolicy which evaluates elapsed time per suite and
        proposes NEXT_SUITE / COMPLETE actions.
        """
        policy = self.bench_policy
        first_suite = policy.start_benchmark(time.monotonic())
        forced_aead = getattr(self.args, "aead", None)

        if not self._coordinate_suite_start(first_suite, aead_token=forced_aead):
            log("Failed to start first suite – aborting deterministic run")
            return

        forced_detector = str(getattr(self.args, "detector_level", "NONE") or "NONE").upper()
        measurement_phase_path = None
        measurement_started_wall_ns = None
        if self.detector_mgr and forced_detector != DetectorLevel.NONE.value:
            if self.detector_mgr.set_level(forced_detector):
                log(f"Detector ACTIVE: {forced_detector}  {self.detector_mgr.get_status()}")
                if forced_detector == DetectorLevel.TST.value:
                    ready_path = Path(
                        os.environ.get(
                            "DETECTOR_TST_METRICS_PATH",
                            "/tmp/tst_metrics.json",
                        )
                    )
                    ready_timeout_s = float(
                        os.environ.get("DETECTOR_READY_TIMEOUT_S", "120")
                    )
                    deadline = time.monotonic() + ready_timeout_s
                    ready_payload = None
                    while self.running and time.monotonic() < deadline:
                        try:
                            ready_payload = json.loads(
                                ready_path.read_text(encoding="utf-8")
                            )
                        except (OSError, ValueError):
                            ready_payload = None
                        if (
                            isinstance(ready_payload, dict)
                            and ready_payload.get("status") in {"ready", "running"}
                        ):
                            break
                        if not self.detector_mgr.is_running:
                            break
                        time.sleep(0.1)
                    if not ready_payload or ready_payload.get("status") not in {
                        "ready",
                        "running",
                    }:
                        log(
                            f"Detector readiness failed: {forced_detector} "
                            f"after {ready_timeout_s:.1f}s"
                        )
                        return
                    log(
                        f"Detector READY: {forced_detector} "
                        f"startup_to_ready_ms="
                        f"{ready_payload.get('startup_to_ready_ms')}"
                    )
                    gate_value = os.environ.get(
                        "DETECTOR_MEASUREMENT_GATE", ""
                    ).strip()
                    if gate_value:
                        gate_path = Path(gate_value)
                        gate_deadline = time.monotonic() + ready_timeout_s
                        log(f"Waiting for measurement gate: {gate_path}")
                        while (
                            self.running
                            and time.monotonic() < gate_deadline
                            and not gate_path.exists()
                        ):
                            if not self.detector_mgr.is_running:
                                break
                            time.sleep(0.05)
                        if not gate_path.exists():
                            log(
                                f"Measurement gate timeout after "
                                f"{ready_timeout_s:.1f}s"
                            )
                            return
                        log("Measurement gate OPEN")
                    phase_value = os.environ.get(
                        "DETECTOR_MEASUREMENT_PHASE_PATH", ""
                    ).strip()
                    if phase_value:
                        measurement_phase_path = Path(phase_value)
                        measurement_started_wall_ns = time.time_ns()
                        measurement_phase_path.write_text(
                            json.dumps(
                                {
                                    "schema": "detector_measurement_phase.v1",
                                    "status": "running",
                                    "start_wall_ns": measurement_started_wall_ns,
                                    "start_mono_ns": time.monotonic_ns(),
                                },
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                policy.last_switch_mono = time.monotonic()
                log("Benchmark MEASUREMENT READY")
            else:
                log(f"Detector start failed: {forced_detector}")

        while self.running:
            now = time.monotonic()
            out = policy.evaluate(now)

            if out.action == BenchmarkAction.NEXT_SUITE:
                target = out.target_suite
                pct = out.progress_pct
                log(
                    f"[deterministic] → {target}  "
                    f"({out.current_index}/{out.total_suites}  {pct:.0f}%)"
                )
                if self._switch_suite(target, target_aead=forced_aead):
                    policy.confirm_advance(time.monotonic())
                else:
                    log(f"Suite switch to {target} FAILED – skipping")
                    policy.confirm_advance(time.monotonic())

            elif out.action == BenchmarkAction.COMPLETE:
                log("Deterministic benchmark run COMPLETE")
                break

            # Health check
            if self.current_suite and not self.proxy.is_running():
                log("Proxy died – attempting restart on current suite")
                self._coordinate_suite_start(self.current_suite, aead_token=self.proxy.current_aead)

            time.sleep(EVAL_INTERVAL_S)

        if measurement_phase_path and measurement_started_wall_ns:
            try:
                phase_payload = json.loads(
                    measurement_phase_path.read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                phase_payload = {
                    "schema": "detector_measurement_phase.v1",
                    "start_wall_ns": measurement_started_wall_ns,
                }
            phase_payload.update(
                {
                    "status": "complete",
                    "end_wall_ns": time.time_ns(),
                    "end_mono_ns": time.monotonic_ns(),
                }
            )
            measurement_phase_path.write_text(
                json.dumps(phase_payload, indent=2),
                encoding="utf-8",
            )

    def _run_intelligent(self):
        """Adaptive suite selection driven by telemetry (flight mode).

        Uses TelemetryAwarePolicyV2 which considers battery, thermal,
        link quality, mission criticality, and hysteresis timers.

        Decision priority (highest → lowest):
          1. Safety gate        – stale telemetry → HOLD
          2. Emergency safety   – battery critical / temp critical → DOWNGRADE
                                  to lightest suite immediately
          3. Link failure       – blackouts after recent switch → ROLLBACK +
                                  blacklist the failing suite
          4. Cooldown gate      – just switched → HOLD
          5. Link degradation   – persistent high gap / low pps → DOWNGRADE
                                  (with hysteresis timer)
          6. Thermal / battery  – rising temp or falling voltage → DOWNGRADE
                                  (with hysteresis timer)
          7. Proactive rekey    – stable for min_stable_s → REKEY same suite
                                  (bounded by max_per_window)
          8. Upgrade            – disarmed, stable, no stress → UPGRADE to
                                  next heavier suite (very conservative)
        """
        policy = self.intel_policy

        # Start with the lightest-tier suite from the filtered pool
        initial = policy.filtered_suites[0]
        initial_aead = str(get_suite(initial).get("aead_token", "aesgcm")).lower()
        if not self._coordinate_suite_start(initial, aead_token=initial_aead):
            log("Failed to start initial suite – aborting intelligent run")
            return

        while self.running:
            inp = self._build_decision_input()
            out = policy.evaluate(inp)

            if out.action == PolicyAction.HOLD:
                pass  # Nominal – stay on current suite

            elif out.action in (
                PolicyAction.UPGRADE,
                PolicyAction.DOWNGRADE,
                PolicyAction.ROLLBACK,
            ):
                target = out.target_suite
                target_aead = out.target_aead or inp.current_aead
                if target and (target != self.current_suite or target_aead != inp.current_aead):
                    log(
                        f"[intelligent] {out.action.value} → {target}/{target_aead}  "
                        f"(reasons: {', '.join(out.reasons)})"
                    )
                    if self._switch_suite(target, target_aead=target_aead):
                        policy.record_rekey(time.monotonic())
                    else:
                        log(f"Suite switch to {target}/{target_aead} FAILED")

            elif out.action == PolicyAction.REKEY:
                target = out.target_suite or self.current_suite
                target_aead = out.target_aead or inp.current_aead
                log(
                    f"[intelligent] REKEY → {target}/{target_aead}  "
                    f"(reasons: {', '.join(out.reasons)})"
                )
                if self._switch_suite(target, target_aead=target_aead):
                    policy.record_rekey(time.monotonic())

            # Health check
            if self.current_suite and not self.proxy.is_running():
                log("Proxy died – restarting current suite")
                self._coordinate_suite_start(self.current_suite, aead_token=self.proxy.current_aead)

            time.sleep(EVAL_INTERVAL_S)

    def _run_energy_aware(self):
        """Three-axis AEAD-aware adaptive suite selection (deployment mode).

        Uses EnergyAwarePolicy which independently selects:
          - Axis 1: AEAD token (runtime power/thermal axis)
          - Axis 2: Security level (handshake/mission axis)
          - Axis 3: DDoS detector level (detection overhead axis)

        Actions handled: HOLD, SWITCH_AEAD, UPGRADE_LEVEL,
                         DOWNGRADE_LEVEL, EMERGENCY, REKEY,
                         DOWNGRADE_DETECTOR, UPGRADE_DETECTOR
        """
        policy = self.energy_policy

        # Start at mission-default level with preferred AEAD
        # (gives room to degrade under stress)
        from sscheduler.policy import _compose_suite, load_settings
        ea_settings = load_settings()
        initial_level = ea_settings.get("initial_level", "L3")
        initial_aead = ea_settings.get("preferred_aead", "chacha20poly1305")
        if initial_aead not in policy._available.get(initial_level, set()):
            initial_aead = policy._best_aead_for_level(initial_level)
        initial = _compose_suite(initial_aead, initial_level)
        if initial not in {s["name"] for s in ALL_SUITES}:
            # Fallback: try aesgcm at the same level
            initial = _compose_suite("aesgcm", initial_level)
        if initial not in {s["name"] for s in ALL_SUITES}:
            # Last resort: first available suite
            initial = self.suites_to_run[0]

        log(f"[energy_aware] Starting at {initial} (level={initial_level}, aead={initial_aead})")

        if not self._coordinate_suite_start(initial, aead_token=initial_aead):
            log("Failed to start initial suite – aborting energy_aware run")
            return

        while self.running:
            inp = self._build_decision_input()
            out = policy.evaluate(inp)

            if out.action == PolicyAction.HOLD:
                pass  # Nominal – stay on current suite

            elif out.action in (
                PolicyAction.SWITCH_AEAD,
                PolicyAction.UPGRADE_LEVEL,
                PolicyAction.DOWNGRADE_LEVEL,
                PolicyAction.EMERGENCY,
            ):
                target = out.target_suite
                target_aead = out.target_aead or inp.current_aead
                if target and (target != self.current_suite or target_aead != inp.current_aead):
                    prev_suite = self.current_suite
                    now_mono = time.monotonic()
                    if hasattr(policy, "allow_rekey_transition"):
                        ok, reason = policy.allow_rekey_transition(
                            out.action,
                            prev_suite or "",
                            target,
                            now_mono,
                        )
                        if not ok:
                            log(
                                f"[energy_aware] BLOCK {out.action.value} → {target} "
                                f"(budget: {reason})"
                            )
                            time.sleep(EVAL_INTERVAL_S)
                            continue
                    log(
                        f"[energy_aware] {out.action.value} → {target}/{target_aead}  "
                        f"(reasons: {', '.join(out.reasons)})"
                    )
                    switch_start = time.monotonic()
                    if self._switch_suite(target, target_aead=target_aead):
                        switch_ms = (time.monotonic() - switch_start) * 1000.0
                        policy.record_rekey(
                            time.monotonic(),
                            previous_suite=prev_suite,
                            target_suite=target,
                            action=out.action,
                        )
                        # Feed rekey cost back for break-even calibration
                        if hasattr(policy, "record_rekey_cost"):
                            policy.record_rekey_cost(switch_ms)
                    else:
                        log(f"Suite switch to {target}/{target_aead} FAILED")

            elif out.action == PolicyAction.REKEY:
                target = out.target_suite or self.current_suite
                target_aead = out.target_aead or inp.current_aead
                prev_suite = self.current_suite
                now_mono = time.monotonic()
                if hasattr(policy, "allow_rekey_transition"):
                    ok, reason = policy.allow_rekey_transition(
                        out.action,
                        prev_suite or "",
                        target or "",
                        now_mono,
                    )
                    if not ok:
                        log(
                            f"[energy_aware] BLOCK REKEY → {target} "
                            f"(budget: {reason})"
                        )
                        time.sleep(EVAL_INTERVAL_S)
                        continue
                log(
                    f"[energy_aware] REKEY → {target}/{target_aead}  "
                    f"(reasons: {', '.join(out.reasons)})"
                )
                switch_start = time.monotonic()
                if self._switch_suite(target, target_aead=target_aead):
                    switch_ms = (time.monotonic() - switch_start) * 1000.0
                    policy.record_rekey(
                        time.monotonic(),
                        previous_suite=prev_suite,
                        target_suite=target,
                        action=out.action,
                    )
                    if hasattr(policy, "record_rekey_cost"):
                        policy.record_rekey_cost(switch_ms)

            elif out.action in (
                PolicyAction.DOWNGRADE_DETECTOR,
                PolicyAction.UPGRADE_DETECTOR,
            ):
                # Axis 3: adjust DDoS detector level
                # Extract target level from reasons (format: "→ XGBOOST" / "→ NONE")
                target_level = DetectorLevel.NONE.value
                for r in out.reasons:
                    for lvl in (DetectorLevel.TST.value,
                                DetectorLevel.XGBOOST.value,
                                DetectorLevel.NONE.value):
                        if lvl in r.upper():
                            target_level = lvl
                            break
                if self.detector_mgr:
                    log(
                        f"[energy_aware] {out.action.value} → {target_level}  "
                        f"(reasons: {', '.join(out.reasons)})"
                    )
                    self.detector_mgr.set_level(target_level)

            # Health check
            if self.current_suite and not self.proxy.is_running():
                log("Proxy died – restarting current suite")
                self._coordinate_suite_start(self.current_suite, aead_token=self.proxy.current_aead)

            time.sleep(EVAL_INTERVAL_S)

        # Dump transition log on shutdown for publication analysis
        tlog = policy.get_transition_log()
        if tlog:
            log_path = LOGS_DIR / "policy_transitions.json"
            try:
                log_path.write_text(json.dumps(tlog, indent=2), encoding="utf-8")
                log(f"Policy transition log: {log_path} ({len(tlog)} transitions)")
            except Exception as e:
                log(f"Failed to write transition log: {e}")

    # ------------------------------------------------------------------ #
    # Entrypoint
    # ------------------------------------------------------------------ #

    def start(self) -> int:
        """Initialise all components and run the selected scheduler loop."""

        def _sighandler(sig, frame):
            log("Interrupted – shutting down")
            self.running = False

        signal.signal(signal.SIGINT, _sighandler)
        signal.signal(signal.SIGTERM, _sighandler)

        # 1. Local monitor (battery / thermal / armed)
        self.local_mon.start()
        log("Local monitor started")

        # 2. GCS telemetry receiver
        self.telem_rx.start()

        # 3. Telemetry reporter (JSONL log)
        self.reporter.start()

        # 4. Wait for GCS scheduler
        log("Waiting for GCS scheduler …")
        if not wait_for_gcs(timeout=120.0):
            log("ERROR: GCS scheduler not responding")
            self.cleanup()
            return 1

        # 5. Clock synchronisation
        self._sync_clock()

        # 6. Inform GCS of parameters
        send_gcs_command("configure", duration=self.args.duration)

        # 7. Start persistent MAVProxy (FC serial ↔ plaintext UDP)
        if not self._start_mavproxy():
            log("WARNING: MAVProxy failed to start – tunnel still works "
                "for testing but no MAVLink will flow")

        # Initialize Swarm Context for Drone
        from hierarchical_swarm.context import SwarmContext
        drone_id = str(CONFIG.get("DRONE_ID", "follower-A1"))
        self.swarm_ctx = SwarmContext(
            drone_id=drone_id,
            role="CANDIDATE",
        )
        self.swarm_ctx.initialize()

        # 8. Run the chosen policy loop
        try:
            if self.policy_mode == "deterministic":
                self._run_deterministic()
            elif self.policy_mode == "energy_aware":
                self._run_energy_aware()
            else:
                self._run_intelligent()
        except Exception as e:
            log(f"Scheduler error: {e}")
        finally:
            self.cleanup()

        return 0

    def cleanup(self):
        log("Cleaning up …")
        self.running = False
        if hasattr(self, "swarm_ctx") and self.swarm_ctx:
            try:
                self.swarm_ctx.shutdown()
            except Exception:
                pass
        # Stop DDoS detector subprocess first (Axis 3)
        if self.detector_mgr:
            try:
                self.detector_mgr.cleanup()
            except Exception:
                pass
        for component in [
            self.proxy,
            self.telem_rx,
            self.reporter,
            self.local_mon,
        ]:
            try:
                component.stop()
            except Exception:
                pass
        try:
            if self.mavproxy_proc:
                self.mavproxy_proc.stop()
        except Exception:
            pass
        try:
            send_gcs_command("stop")
        except Exception:
            pass
        log("Cleanup complete")


# ===========================================================================
# CLI
# ===========================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Drone MAV-to-MAV PQC Tunnel Scheduler",
    )
    parser.add_argument(
        "--policy",
        choices=["deterministic", "intelligent", "energy_aware"],
        default="intelligent",
        help="Scheduling policy (default: intelligent, energy_aware for deployment)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Seconds per suite (deterministic mode)",
    )
    parser.add_argument(
        "--mav-master",
        default=str(CONFIG.get("MAV_FC_DEVICE", "/dev/ttyACM0")),
        help="MAVLink master (serial device or tcp:host:port)",
    )
    parser.add_argument("--suite", help="Run a single suite only")
    parser.add_argument("--aead", help="Runtime AEAD override for deterministic runs")
    parser.add_argument(
        "--detector-level",
        choices=["NONE", "LGBM", "RF", "XGBOOST", "TST"],
        default="NONE",
        help="Force a DDoS detector during deterministic benchmark runs",
    )
    parser.add_argument(
        "--nist-level",
        choices=["L1", "L3", "L5"],
        help="Filter suites by NIST level",
    )
    parser.add_argument("--max-suites", type=int, help="Limit number of suites")

    args = parser.parse_args()

    print("=" * 60)
    print("  Drone MAV-to-MAV PQC Tunnel Scheduler")
    print(f"  Policy: {args.policy}  |  Duration: {args.duration}s")
    print("=" * 60)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(name)-12s  %(levelname)-7s  %(message)s",
    )

    try:
        scheduler = MavTunnelScheduler(args)
        return scheduler.start()
    except Exception as e:
        log(f"Fatal: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
