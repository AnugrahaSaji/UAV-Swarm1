#!/usr/bin/env python3
"""
MAVLink Metrics Collector
core/mavlink_collector.py

Collects bidirectional MAVLink communication metrics for both GCS and Drone sides.
Provides message-level tracking, heartbeat monitoring, sequence gap detection,
and command latency measurement.

Usage:
    from core.mavlink_collector import MavLinkMetricsCollector
    
    collector = MavLinkMetricsCollector(role="gcs")
    collector.start_sniffing(port=14552)
    # ... run benchmark ...
    metrics = collector.get_metrics()
"""

import os
import sys
import time
import json
import socket
import struct
import threading
from pathlib import Path
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timezone

try:
    from pymavlink import mavutil
    HAS_PYMAVLINK = True
except ImportError:
    HAS_PYMAVLINK = False


MESSAGE_FIELD_PRIORITY = {
    "HEARTBEAT": ("type", "autopilot", "base_mode", "custom_mode", "system_status"),
    "STATUSTEXT": ("severity", "text"),
    "GLOBAL_POSITION_INT": ("lat", "lon", "alt", "relative_alt", "vx", "vy", "vz", "hdg"),
    "ATTITUDE": ("roll", "pitch", "yaw", "rollspeed", "pitchspeed", "yawspeed"),
    "SYS_STATUS": (
        "battery_remaining",
        "voltage_battery",
        "current_battery",
        "drop_rate_comm",
        "load",
        "errors_count1",
        "errors_count2",
    ),
    "BATTERY_STATUS": ("battery_remaining", "current_battery", "voltages"),
    "GPS_RAW_INT": ("fix_type", "satellites_visible", "lat", "lon", "alt"),
    "PING": ("time_usec", "seq", "target_system", "target_component"),
    "COMMAND_LONG": ("command", "target_system", "target_component", "param1", "param2"),
    "COMMAND_ACK": ("command", "result", "progress"),
    "VFR_HUD": ("airspeed", "groundspeed", "heading", "throttle", "alt", "climb"),
    "LOCAL_POSITION_NED": ("x", "y", "z", "vx", "vy", "vz"),
    "HIGH_LATENCY2": ("target_distance", "heading", "battery", "temperature_air"),
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class MavLinkMessageStats:
    """Statistics for a single MAVLink message type."""
    msg_id: int = 0
    msg_name: str = ""
    count_tx: int = 0
    count_rx: int = 0
    first_seen_mono: float = 0.0
    last_seen_mono: float = 0.0
    avg_interval_ms: float = 0.0
    size_bytes: int = 0


@dataclass
class HeartbeatStats:
    """Heartbeat-specific tracking."""
    count: int = 0
    expected_count: int = 0
    loss_count: int = 0
    last_time_mono: float = 0.0
    avg_interval_ms: float = 0.0
    interval_samples: List[float] = field(default_factory=list)
    sysid: int = 0
    compid: int = 0
    mode: int = 0
    armed: bool = False


@dataclass
class CommandStats:
    """Command/ACK tracking."""
    cmd_sent: int = 0
    cmd_ack_received: int = 0
    ack_pending: Dict[int, float] = field(default_factory=dict)  # cmd_id -> send_time
    latency_samples: List[float] = field(default_factory=list)


@dataclass
class SequenceStats:
    """MAVLink sequence number tracking."""
    last_seq: Dict[int, int] = field(default_factory=dict)  # sysid -> last_seq
    gaps: int = 0
    duplicates: int = 0
    out_of_order: int = 0


# =============================================================================
# MAVLINK METRICS COLLECTOR
# =============================================================================

class MavLinkMetricsCollector:
    """
    Collects comprehensive MAVLink metrics for benchmark analysis.
    
    Tracks:
    - Message rates (tx/rx per second)
    - Message type counts
    - Heartbeat intervals and losses
    - Sequence gaps/duplicates
    - Command acknowledgement latency
    - CRC errors and decode failures
    """
    
    def __init__(self, role: str = "auto"):
        """
        Initialize collector.
        
        Args:
            role: "gcs" or "drone" - determines which metrics to collect
        """
        self.role = role if role != "auto" else self._detect_role()
        
        # Connection
        self._mav_conn = None
        self._sock = None
        self._sniff_port = 0
        
        # Thread control
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        
        # Timing
        self._start_time_mono = 0.0
        self._end_time_mono = 0.0
        
        # Message tracking
        self._msg_stats: Dict[int, MavLinkMessageStats] = {}
        self._total_rx = 0
        self._total_tx = 0
        self._total_bytes_rx = 0
        self._total_bytes_tx = 0
        
        # Heartbeat tracking
        self._heartbeat = HeartbeatStats()
        self._last_heartbeat_mono = 0.0
        self._heartbeat_intervals: List[float] = []
        
        # Command tracking
        self._commands = CommandStats()
        
        # Sequence tracking
        self._sequences = SequenceStats()
        
        # Error tracking
        self._crc_errors = 0
        self._decode_errors = 0
        self._msg_drops = 0
        
        # Latency tracking (for timestamped messages)
        self._latency_samples: List[float] = []
        self._latency_jitter_samples: List[float] = []
        self._last_latency_ms: Optional[float] = None
        self._boot_to_unix_offset_s: Optional[float] = None
        self._boot_to_unix_last_mono: float = 0.0

        # RTT tracking (COMMAND_LONG -> COMMAND_ACK)
        self._rtt_samples_ms: List[float] = []
        
        # Raw message log (bounded)
        self._msg_log: deque = deque(maxlen=10000)
        self._status_text_log: deque = deque(maxlen=128)

        # Protocol info
        self._protocol_version: Optional[str] = None
        
        # Chronos Telemetry Store
        self._last_telemetry = {
            "alt_rel_m": 0.0,
            "hdg_deg": 0.0,
            "batt_rem_pct": 0,
            "last_update": 0.0
        }

        # Flight controller telemetry fields
        self._fc_mode: str = ""
        self._fc_armed: bool = False
        self._fc_heartbeat_last_mono: float = 0.0
        self._fc_attitude_first_mono: float = 0.0
        self._fc_attitude_last_mono: float = 0.0
        self._fc_attitude_count: int = 0
        self._fc_position_first_mono: float = 0.0
        self._fc_position_last_mono: float = 0.0
        self._fc_position_count: int = 0
        self._fc_batt_voltage_v: float = 0.0
        self._fc_batt_current_a: float = 0.0
        self._fc_batt_remaining_pct: float = 0.0
        self._fc_cpu_load_pct: float = 0.0
        self._fc_sensor_health_flags: int = 0
        self._min_latency_samples = 5
        self._min_rtt_samples = 5

        # External clock offset (from Chronos clock-sync) as fallback for OWL
        # When SYSTEM_TIME is unavailable (no GPS), the chronos offset lets us
        # convert boot_ms timestamps to wall-clock for one-way latency.
        self._external_clock_offset_s: Optional[float] = None

        # Optional active RTT probe (PING)
        self._probe_running = False
        self._probe_thread: Optional[threading.Thread] = None
        self._probe_recv_thread: Optional[threading.Thread] = None
        self._probe_send_conn = None
        self._probe_target_host: str = "127.0.0.1"
        self._probe_target_port: int = 0
        self._probe_interval_s: float = 1.0
        self._probe_seq: int = 1
        self._probe_pending: Dict[int, float] = {}

        # Optional live JSONL export for sniff-port observability.
        self._live_export_path: Optional[Path] = None
        self._live_export_interval_s: float = 1.0
        self._live_export_recent_messages: int = 20
        self._live_export_context: Dict[str, Any] = {}
        self._live_export_running = False
        self._live_export_thread: Optional[threading.Thread] = None
        
    def _detect_role(self) -> str:
        """Detect role from platform."""
        import platform
        machine = platform.machine().lower()
        if "arm" in machine or "aarch" in machine:
            return "drone"
        return "gcs"

    def set_clock_offset(self, offset_seconds: float) -> None:
        """
        Inject an external clock offset (GCS_wall - Drone_wall) as fallback
        for OWL computation when SYSTEM_TIME is unavailable (no GPS).

        With this offset, _track_message_latency can convert boot_ms timestamps:
          sent_wall = boot_ms/1000 + _boot_to_unix_offset_s
        where _boot_to_unix_offset_s is synthesised from:
          drone_wall_now + offset = gcs_wall_now  (offset is gcs-drone)
          boot_to_unix = drone_wall_now - boot_s  (from first HEARTBEAT/attitude)
        So we store the offset and reconstruct _boot_to_unix_offset_s when we get
        a message with time_boot_ms.
        """
        try:
            self._external_clock_offset_s = float(offset_seconds)
        except (TypeError, ValueError):
            pass
    
    def start_sniffing(self, port: int = 14552, host: str = "127.0.0.1"):
        """
        Start sniffing MAVLink traffic on a UDP port.
        
        For GCS: sniff MAVProxy's duplicate output port (e.g., 14552)
        For Drone: sniff the proxy's plaintext output
        """
        if self._running:
            return

        # Reset counters for a new suite to avoid cumulative leakage
        self.reset()
        
        self._sniff_port = port
        self._start_time_mono = time.monotonic()
        self._running = True
        
        self._thread = threading.Thread(
            target=self._sniff_loop,
            args=(host, port),
            daemon=True
        )
        self._thread.start()

    def reset(self) -> None:
        """Reset all counters and state for a new suite."""
        with self._lock:
            # Connection timing
            self._start_time_mono = 0.0
            self._end_time_mono = 0.0

            # Message tracking
            self._msg_stats = {}
            self._total_rx = 0
            self._total_tx = 0
            self._total_bytes_rx = 0
            self._total_bytes_tx = 0

            # Heartbeat tracking
            self._heartbeat = HeartbeatStats()
            self._last_heartbeat_mono = 0.0
            self._heartbeat_intervals = []

            # Command tracking
            self._commands = CommandStats()

            # Sequence tracking
            self._sequences = SequenceStats()

            # Error tracking
            self._crc_errors = 0
            self._decode_errors = 0
            self._msg_drops = 0

            # Latency tracking
            self._latency_samples = []
            self._latency_jitter_samples = []
            self._last_latency_ms = None
            self._boot_to_unix_offset_s = None
            self._boot_to_unix_last_mono = 0.0
            # NOTE: _external_clock_offset_s is NOT reset here — it persists
            # across suites since clock sync is done less frequently.

            # RTT samples
            self._rtt_samples_ms = []

            # Raw message log
            self._msg_log = deque(maxlen=10000)
            self._status_text_log = deque(maxlen=128)

            # Protocol info
            self._protocol_version = None

            # Flight controller telemetry fields
            self._fc_mode = ""
            self._fc_armed = False
            self._fc_heartbeat_last_mono = 0.0
            self._fc_attitude_first_mono = 0.0
            self._fc_attitude_last_mono = 0.0
            self._fc_attitude_count = 0
            self._fc_position_first_mono = 0.0
            self._fc_position_last_mono = 0.0
            self._fc_position_count = 0
            self._fc_batt_voltage_v = 0.0
            self._fc_batt_current_a = 0.0
            self._fc_batt_remaining_pct = 0.0
            self._fc_cpu_load_pct = 0.0
            self._fc_sensor_health_flags = 0

            # Active probe state
            self._probe_pending = {}
            self._probe_seq = 1

    def reset_count_window(self) -> None:
        """Reset message counters and timing to align the counting window
        with the proxy forwarding start.

        The sniff thread keeps running (no socket teardown) but all
        accumulated counts are zeroed so that only messages received
        from this point onward contribute to the suite metrics.
        """
        with self._lock:
            self._start_time_mono = time.monotonic()
            self._total_rx = 0
            self._total_tx = 0
            self._total_bytes_rx = 0
            self._total_bytes_tx = 0
            self._msg_stats = {}
            self._sequences = SequenceStats()
            self._heartbeat = HeartbeatStats()
            self._last_heartbeat_mono = 0.0
            self._heartbeat_intervals = []
            self._crc_errors = 0
            self._decode_errors = 0
            self._msg_drops = 0
            self._latency_samples = []
            self._latency_jitter_samples = []
            self._last_latency_ms = None
            self._rtt_samples_ms = []
            self._msg_log = deque(maxlen=10000)
            self._status_text_log = deque(maxlen=128)

    def stop(self) -> Dict[str, Any]:
        """Stop sniffing and return collected metrics."""
        if not self._running:
            return self.get_metrics()

        self.stop_live_export()
        self.stop_rtt_probe()
        
        self._running = False
        self._end_time_mono = time.monotonic()
        
        if self._thread:
            self._thread.join(timeout=2.0)
        
        if self._sock:
            try:
                self._sock.close()
            except:
                pass
        
        if self._mav_conn:
            try:
                self._mav_conn.close()
            except:
                pass
        
        return self.get_metrics()

    def start_rtt_probe(self, host: str = "127.0.0.1", port: int = 47001, rate_hz: float = 1.0) -> None:
        """
        Start active RTT probing by sending MAVLink PING messages.

        This is used in MAVPROXY benchmark mode where no COMMAND_LONG traffic may
        be generated, causing COMMAND_ACK-based RTT to remain unavailable.
        """
        if not HAS_PYMAVLINK:
            return
        if self._probe_running:
            return
        try:
            self._probe_target_host = host
            self._probe_target_port = int(port)
            hz = float(rate_hz)
            if hz <= 0:
                hz = 1.0
            self._probe_interval_s = 1.0 / hz
            self._probe_send_conn = mavutil.mavlink_connection(
                f"udpout:{self._probe_target_host}:{self._probe_target_port}",
                source_system=255,
                source_component=190,
            )
        except Exception:
            self._probe_send_conn = None
            return

        self._probe_running = True

        def _probe_loop() -> None:
            while self._probe_running:
                try:
                    now_mono = time.monotonic()
                    now_us = int(time.time() * 1_000_000)
                    seq = self._probe_seq
                    self._probe_seq = (self._probe_seq + 1) % 2_147_483_647
                    if self._probe_send_conn:
                        self._probe_send_conn.mav.ping_send(
                            now_us,
                            seq,
                            0,   # broadcast target; autopilot may answer
                            0,
                        )
                        with self._lock:
                            self._probe_pending[seq] = now_mono
                            # prevent unbounded growth if replies are missing
                            if len(self._probe_pending) > 1024:
                                cutoff = now_mono - 30.0
                                stale = [k for k, v in self._probe_pending.items() if v < cutoff]
                                for k in stale:
                                    self._probe_pending.pop(k, None)
                except Exception:
                    pass
                time.sleep(self._probe_interval_s)

        def _probe_recv_loop() -> None:
            """Receive PING responses on the probe connection itself.

            MAVProxy relays PING messages to all --out endpoints, but the
            original probe connection (udpout) may also receive responses
            directly when the autopilot replies on the same UDP channel.
            This thread ensures we capture those replies for RTT computation.
            """
            while self._probe_running:
                try:
                    if self._probe_send_conn is None:
                        break
                    reply = self._probe_send_conn.recv_match(
                        type="PING", blocking=True, timeout=0.25,
                    )
                    if reply is not None:
                        self._handle_ping(reply, time.monotonic())
                except Exception:
                    time.sleep(0.05)

        self._probe_thread = threading.Thread(target=_probe_loop, daemon=True)
        self._probe_thread.start()
        self._probe_recv_thread = threading.Thread(target=_probe_recv_loop, daemon=True)
        self._probe_recv_thread.start()

    def stop_rtt_probe(self) -> None:
        """Stop active RTT probe thread and close sender connection."""
        if not self._probe_running:
            return
        self._probe_running = False
        if self._probe_thread:
            self._probe_thread.join(timeout=1.0)
        self._probe_thread = None
        if self._probe_recv_thread:
            self._probe_recv_thread.join(timeout=1.0)
        self._probe_recv_thread = None
        if self._probe_send_conn is not None:
            try:
                self._probe_send_conn.close()
            except Exception:
                pass
        self._probe_send_conn = None

    def start_live_export(
        self,
        output_path: str,
        interval_s: float = 1.0,
        recent_messages: int = 20,
        context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Start periodic JSONL export of link status and recent sniffed messages."""
        if not output_path:
            return

        self.stop_live_export()

        try:
            self._live_export_path = Path(output_path)
            self._live_export_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            self._live_export_path = None
            return

        try:
            self._live_export_interval_s = max(0.1, float(interval_s))
        except (TypeError, ValueError):
            self._live_export_interval_s = 1.0
        try:
            self._live_export_recent_messages = max(1, min(int(recent_messages), 64))
        except (TypeError, ValueError):
            self._live_export_recent_messages = 20
        self._live_export_context = dict(context or {})
        self._live_export_running = True
        self._live_export_thread = threading.Thread(
            target=self._live_export_loop,
            name=f"mavlink-live-export-{self.role}",
            daemon=True,
        )
        self._live_export_thread.start()

    def stop_live_export(self) -> None:
        """Stop periodic JSONL export and append one final snapshot."""
        if not self._live_export_running:
            return

        self._live_export_running = False
        if self._live_export_thread:
            self._live_export_thread.join(timeout=1.5)
        self._live_export_thread = None
        self._write_live_snapshot(phase="final")

    def _live_export_loop(self) -> None:
        while self._live_export_running:
            self._write_live_snapshot()
            time.sleep(self._live_export_interval_s)

    def _write_live_snapshot(self, phase: str = "live") -> None:
        if not self._live_export_path:
            return
        try:
            snapshot = self.get_live_snapshot(recent_messages=self._live_export_recent_messages)
            snapshot["phase"] = phase
            with self._live_export_path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(snapshot, default=str) + "\n")
        except Exception:
            pass
    
    def _sniff_loop(self, host: str, port: int):
        """Main sniffing loop."""
        # Require pymavlink; no raw socket fallback
        if not HAS_PYMAVLINK:
            return
        try:
            conn_str = f"udpin:{host}:{port}"
            self._mav_conn = mavutil.mavlink_connection(
                conn_str,
                source_system=255,
                source_component=0
            )
            # Enlarge the kernel UDP receive buffer to prevent drops at high msg
            # rates.  pymavlink's udpin connections expose the raw socket on
            # .port; the default Windows buffer (8 KB) overflows at ≥200 msg/s.
            _sock = getattr(self._mav_conn, 'port', None)
            if _sock and hasattr(_sock, 'setsockopt'):
                try:
                    _sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2 * 1024 * 1024)
                except OSError:
                    pass
            self._protocol_version = "MAVLink 2.0"
            import logging
            logging.getLogger(__name__).warning(
                f"[MavLinkCollector:{self.role}] sniff_loop STARTED on {conn_str}"
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).error(
                f"[MavLinkCollector:{self.role}] sniff_loop FAILED to bind {host}:{port}: {exc}"
            )
            self._mav_conn = None
            return
        
        msg_count = 0
        while self._running:
            try:
                self._process_one()
                new_count = self._total_rx
                if new_count > msg_count and new_count <= 5:
                    import logging
                    logging.getLogger(__name__).warning(
                        f"[MavLinkCollector:{self.role}] rx #{new_count} on port {port}"
                    )
                msg_count = new_count
            except Exception as e:
                import logging
                logging.getLogger(__name__).debug(
                    "sniff_loop error: %s", e, exc_info=True
                )
                time.sleep(0.01)
    
    def _process_one(self):
        """Process one MAVLink message."""
        if self._mav_conn:
            msg = self._mav_conn.recv_match(blocking=True, timeout=0.1)
            if msg:
                now = time.monotonic()
                now_wall = time.time()
                self._handle_message(msg, now, now_wall)
        
    
    def _handle_message(self, msg, now: float, now_wall: float):
        """Handle a parsed MAVLink message."""
        with self._lock:
            msg_type = msg.get_type()
            msg_id = msg.get_msgId()
            sysid = msg.get_srcSystem()
            compid = msg.get_srcComponent()
            
            # Skip BAD_DATA
            if msg_type == "BAD_DATA":
                self._decode_errors += 1
                return
            
            # Update total counts
            self._total_rx += 1
            
            # Estimate size
            size = 12  # MAVLink 2.0 header
            try:
                payload = msg.get_payload()
                if payload and isinstance(payload, (bytes, bytearray)):
                    size += len(payload)
            except:
                pass
            self._total_bytes_rx += size
            
            # Track message type
            if msg_id not in self._msg_stats:
                self._msg_stats[msg_id] = MavLinkMessageStats(
                    msg_id=msg_id,
                    msg_name=msg_type,
                    first_seen_mono=now
                )
            
            stats = self._msg_stats[msg_id]
            stats.count_rx += 1
            stats.last_seen_mono = now
            stats.size_bytes = size
            
            # Sequence tracking
            try:
                seq = msg.get_seq()
                self._track_sequence(sysid, seq)
            except:
                pass
            
            # Heartbeat tracking
            if msg_type == "HEARTBEAT":
                self._handle_heartbeat(msg, now)

            # Track MAVLink one-way latency (timestamped messages)
            self._track_message_latency(msg, now_wall)
            
            # Command tracking / RTT
            if msg_type in {"COMMAND_LONG", "COMMAND_INT"}:
                try:
                    cmd_id = int(getattr(msg, "command", 0) or 0)
                except Exception:
                    cmd_id = 0
                if cmd_id > 0:
                    self._commands.cmd_sent += 1
                    self._commands.ack_pending[cmd_id] = now
            elif msg_type == "COMMAND_ACK":
                self._handle_command_ack(msg, now)

            elif msg_type == "PING":
                self._handle_ping(msg, now)
            
            # Chronos Telemetry Parsing
            elif msg_type == "GLOBAL_POSITION_INT":
                try:
                    self._last_telemetry["alt_rel_m"] = msg.relative_alt / 1000.0
                    self._last_telemetry["hdg_deg"] = msg.hdg / 100.0
                    self._last_telemetry["last_update"] = now
                except: pass
                # Position update rate tracking
                if self._fc_position_count == 0:
                    self._fc_position_first_mono = now
                self._fc_position_last_mono = now
                self._fc_position_count += 1
            elif msg_type == "SYS_STATUS":
                try:
                    self._last_telemetry["batt_rem_pct"] = msg.battery_remaining
                    self._last_telemetry["last_update"] = now
                except: pass
                try:
                    # SYS_STATUS battery fields are in mV and 10mA units
                    if getattr(msg, "voltage_battery", None) is not None:
                        self._fc_batt_voltage_v = msg.voltage_battery / 1000.0
                    if getattr(msg, "current_battery", None) is not None:
                        self._fc_batt_current_a = msg.current_battery / 100.0
                    if getattr(msg, "battery_remaining", None) is not None:
                        self._fc_batt_remaining_pct = float(msg.battery_remaining)
                    if getattr(msg, "load", None) is not None:
                        self._fc_cpu_load_pct = float(msg.load) / 10.0
                    if getattr(msg, "onboard_control_sensors_health", None) is not None:
                        self._fc_sensor_health_flags = int(msg.onboard_control_sensors_health)
                except Exception:
                    pass
            elif msg_type == "BATTERY_STATUS":
                try:
                    # Use first non-zero cell voltage (mV)
                    voltages = getattr(msg, "voltages", []) or []
                    for mv in voltages:
                        if mv and mv > 0:
                            self._fc_batt_voltage_v = mv / 1000.0
                            break
                    if getattr(msg, "current_battery", None) is not None:
                        self._fc_batt_current_a = msg.current_battery / 100.0
                    if getattr(msg, "battery_remaining", None) is not None:
                        self._fc_batt_remaining_pct = float(msg.battery_remaining)
                except Exception:
                    pass
            elif msg_type == "ATTITUDE":
                if self._fc_attitude_count == 0:
                    self._fc_attitude_first_mono = now
                self._fc_attitude_last_mono = now
                self._fc_attitude_count += 1

            elif msg_type == "STATUSTEXT":
                try:
                    text = getattr(msg, "text", "")
                    if isinstance(text, bytes):
                        text = text.decode("utf-8", errors="ignore")
                    severity = getattr(msg, "severity", None)
                    self._status_text_log.append({
                        "t": now,
                        "severity": severity,
                        "text": str(text)[:160],
                    })
                except Exception:
                    pass
            
            # Log message
            self._msg_log.append({
                "t": now,
                "wall_time_utc": datetime.fromtimestamp(now_wall, tz=timezone.utc).isoformat(),
                "id": msg_id,
                "type": msg_type,
                "sysid": sysid,
                "compid": compid,
                "seq": self._safe_message_seq(msg),
                "size_bytes": size,
                "fields": self._extract_message_fields(msg, msg_type),
            })

    def _safe_message_seq(self, msg) -> Optional[int]:
        try:
            return int(msg.get_seq())
        except Exception:
            header = getattr(msg, "_header", None)
            if header is None:
                return None
            try:
                return int(getattr(header, "seq"))
            except Exception:
                return None

    def _sanitize_field_value(self, value: Any) -> Any:
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return round(value, 6)
        if isinstance(value, str):
            return value[:160]
        if isinstance(value, bytes):
            return value[:24].hex()
        if isinstance(value, (list, tuple)):
            cleaned = []
            for item in value[:8]:
                if isinstance(item, (bool, int, float, str)):
                    cleaned.append(self._sanitize_field_value(item))
            return cleaned
        return None

    def _extract_message_fields(self, msg, msg_type: str) -> Dict[str, Any]:
        fields: Dict[str, Any] = {}
        preferred = MESSAGE_FIELD_PRIORITY.get(msg_type, ())
        raw: Dict[str, Any] = {}
        try:
            to_dict = getattr(msg, "to_dict", None)
            if callable(to_dict):
                maybe = to_dict()
                if isinstance(maybe, dict):
                    raw = maybe
        except Exception:
            raw = {}

        for key in preferred:
            if key in raw:
                value = self._sanitize_field_value(raw.get(key))
                if value is not None:
                    fields[key] = value

        if not fields and raw:
            for key, value in raw.items():
                if key.startswith("_") or key == "mavpackettype":
                    continue
                clean = self._sanitize_field_value(value)
                if clean is None:
                    continue
                fields[key] = clean
                if len(fields) >= 8:
                    break

        return fields

    def _recent_messages_locked(self, limit: int = 20) -> List[Dict[str, Any]]:
        count = max(0, min(int(limit), len(self._msg_log)))
        if count <= 0:
            return []
        recent = list(self._msg_log)[-count:]
        return [dict(entry) for entry in recent]

    def _recent_status_text_locked(self, limit: int = 5) -> List[Dict[str, Any]]:
        count = max(0, min(int(limit), len(self._status_text_log)))
        if count <= 0:
            return []
        return [dict(entry) for entry in list(self._status_text_log)[-count:]]

    def _top_message_types_locked(self, limit: int = 8) -> List[Dict[str, Any]]:
        items = sorted(
            self._msg_stats.values(),
            key=lambda stats: (stats.count_rx, stats.last_seen_mono),
            reverse=True,
        )
        top: List[Dict[str, Any]] = []
        for stats in items[:max(1, int(limit))]:
            top.append({
                "type": stats.msg_name,
                "msg_id": stats.msg_id,
                "count_rx": stats.count_rx,
                "size_bytes": stats.size_bytes,
            })
        return top

    def _link_status_locked(self, duration_s: float, rx_pps: Optional[float]) -> Dict[str, Any]:
        now = time.monotonic()
        last_message_age_ms = None
        if self._msg_log:
            last_message_age_ms = max(0.0, (now - self._msg_log[-1]["t"]) * 1000.0)
        heartbeat_age_ms = None
        if self._fc_heartbeat_last_mono > 0:
            heartbeat_age_ms = max(0.0, (now - self._fc_heartbeat_last_mono) * 1000.0)

        degraded_reasons: List[str] = []
        if self._sequences.gaps > 0:
            degraded_reasons.append("sequence_gaps")
        if self._sequences.duplicates > 0:
            degraded_reasons.append("duplicates")
        if self._sequences.out_of_order > 0:
            degraded_reasons.append("out_of_order")
        if self._decode_errors > 0:
            degraded_reasons.append("decode_errors")
        if self._heartbeat.loss_count > 0:
            degraded_reasons.append("heartbeat_loss")

        state = "initializing"
        if self._total_rx <= 0:
            state = "idle" if duration_s >= 1.0 else "initializing"
        else:
            if (last_message_age_ms is not None and last_message_age_ms > 3000.0) or (
                heartbeat_age_ms is not None and heartbeat_age_ms > 3000.0
            ):
                state = "down"
            elif (
                degraded_reasons
                or (last_message_age_ms is not None and last_message_age_ms > 1500.0)
                or (heartbeat_age_ms is not None and heartbeat_age_ms > 1500.0)
            ):
                state = "degraded"
            else:
                state = "healthy"

        last_status = None
        if self._status_text_log:
            last_status = dict(self._status_text_log[-1])

        return {
            "state": state,
            "stream_active": bool(last_message_age_ms is not None and last_message_age_ms <= 2000.0),
            "heartbeat_present": self._heartbeat.count > 0,
            "heartbeat_age_ms": None if heartbeat_age_ms is None else round(heartbeat_age_ms, 1),
            "last_message_age_ms": None if last_message_age_ms is None else round(last_message_age_ms, 1),
            "rx_pps": None if rx_pps is None else round(rx_pps, 2),
            "duration_s": round(duration_s, 3),
            "total_msgs_received": self._total_rx,
            "total_bytes_received": self._total_bytes_rx,
            "seq_gap_count": self._sequences.gaps,
            "seq_duplicate_count": self._sequences.duplicates,
            "seq_out_of_order_count": self._sequences.out_of_order,
            "decode_error_count": self._decode_errors,
            "heartbeat_loss_count": self._heartbeat.loss_count,
            "degraded_reasons": degraded_reasons,
            "last_statustext": last_status,
        }

    def get_live_snapshot(self, recent_messages: int = 20) -> Dict[str, Any]:
        """Return a compact real-time snapshot for GCS sniff-port monitoring."""
        metrics = self.get_metrics()
        snapshot = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "role": self.role,
            "sniff_port": self._sniff_port,
            "context": dict(self._live_export_context),
            "link_status": metrics.get("link_status"),
            "flight_controller": metrics.get("flight_controller"),
            "top_message_types": metrics.get("top_message_types"),
            "recent_messages": metrics.get("recent_messages", [])[:max(1, int(recent_messages))],
            "recent_statustext": metrics.get("recent_statustext"),
        }
        return snapshot
    
    def _track_sequence(self, sysid: int, seq: int):
        """Track sequence numbers for gap detection."""
        if sysid in self._sequences.last_seq:
            expected = (self._sequences.last_seq[sysid] + 1) % 256
            if seq != expected:
                if seq == self._sequences.last_seq[sysid]:
                    self._sequences.duplicates += 1
                else:
                    # Use circular distance (mod 256) to classify
                    forward_dist = (seq - expected) % 256
                    if forward_dist <= 128:
                        # Forward jump — count as gaps
                        self._sequences.gaps += forward_dist
                    else:
                        # Backward — out-of-order / late arrival
                        self._sequences.out_of_order += 1
        
        self._sequences.last_seq[sysid] = seq
    
    def _handle_heartbeat(self, msg, now: float):
        """Handle heartbeat message."""
        self._heartbeat.count += 1
        self._heartbeat.sysid = msg.get_srcSystem()
        self._heartbeat.compid = msg.get_srcComponent()
        self._fc_heartbeat_last_mono = now
        
        try:
            self._heartbeat.mode = msg.custom_mode
            if HAS_PYMAVLINK:
                self._heartbeat.armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        except:
            pass

        # Flight controller mode/armed state
        try:
            if HAS_PYMAVLINK:
                self._fc_mode = mavutil.mode_string_v10(msg)
                self._fc_armed = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            else:
                self._fc_mode = str(getattr(msg, "custom_mode", ""))
        except Exception:
            pass
        
        # Calculate interval
        if self._last_heartbeat_mono > 0:
            interval_ms = (now - self._last_heartbeat_mono) * 1000.0
            self._heartbeat_intervals.append(interval_ms)
            
            # Detect lost heartbeats (expected ~1Hz)
            if interval_ms > 1500:  # > 1.5s gap
                expected_beats = int(interval_ms / 1000.0)
                self._heartbeat.loss_count += max(0, expected_beats - 1)
        
        self._last_heartbeat_mono = now
    
    def _handle_command_ack(self, msg, now: float):
        """Handle command acknowledgement."""
        self._commands.cmd_ack_received += 1
        
        # Try to match with pending command
        try:
            cmd_id = msg.command
            if cmd_id in self._commands.ack_pending:
                send_time = self._commands.ack_pending.pop(cmd_id)
                latency_ms = (now - send_time) * 1000.0
                self._commands.latency_samples.append(latency_ms)
                self._rtt_samples_ms.append(latency_ms)
        except:
            pass

    def _handle_ping(self, msg, now: float):
        """Handle MAVLink PING response and derive RTT sample."""
        try:
            seq = int(getattr(msg, "seq", -1) or -1)
        except Exception:
            seq = -1
        if seq < 0:
            return

        send_time = self._probe_pending.pop(seq, None)
        if send_time is None:
            return
        rtt_ms = (now - send_time) * 1000.0
        if rtt_ms < 0 or rtt_ms > 60_000:
            return
        self._rtt_samples_ms.append(rtt_ms)
    
    def record_command_sent(self, cmd_id: int):
        """Record that a command was sent (for latency tracking)."""
        with self._lock:
            self._commands.cmd_sent += 1
            self._commands.ack_pending[cmd_id] = time.monotonic()
    
    def record_tx_message(self, msg_id: int = 0, size: int = 0):
        """Record a transmitted message."""
        with self._lock:
            self._total_tx += 1
            self._total_bytes_tx += size
            
            if msg_id > 0:
                if msg_id not in self._msg_stats:
                    self._msg_stats[msg_id] = MavLinkMessageStats(
                        msg_id=msg_id,
                        first_seen_mono=time.monotonic()
                    )
                self._msg_stats[msg_id].count_tx += 1

    def inject_rtt_sample(self, rtt_ms: float) -> None:
        """Inject an externally-measured RTT sample (e.g. from RPC echo).

        This enables application-level RTT measurement when MAVLink PING
        is not routable through the proxy architecture.
        """
        if rtt_ms < 0 or rtt_ms > 60_000:
            return
        with self._lock:
            self._rtt_samples_ms.append(rtt_ms)

    def _track_message_latency(self, msg, now_wall: float) -> None:
        """Track one-way latency for MAVLink messages when timestamp is available."""
        # Update boot->unix mapping from SYSTEM_TIME
        try:
            if msg.get_type() == "SYSTEM_TIME":
                time_unix_usec = getattr(msg, "time_unix_usec", 0) or 0
                time_boot_ms = getattr(msg, "time_boot_ms", 0) or 0
                if time_unix_usec and time_boot_ms:
                    self._boot_to_unix_offset_s = (time_unix_usec / 1_000_000.0) - (time_boot_ms / 1000.0)
                    self._boot_to_unix_last_mono = time.monotonic()
        except Exception:
            pass

        # Fallback: if SYSTEM_TIME never provided a valid unix timestamp but we
        # have a Chronos clock-sync offset AND time_boot_ms, we can synthesise
        # the boot-to-unix mapping.  The Chronos offset is (gcs_wall - drone_wall).
        # For the GCS receiver:
        #   sent_wall_gcs = drone_wall + offset = (boot_time + boot_epoch_drone) + offset
        # We need boot_epoch_drone which is (drone_wall_now - boot_s_now).
        # Since we receive on the GCS side, now_wall IS gcs_wall:
        #   drone_wall_now ≈ now_wall - offset
        #   boot_epoch_drone = drone_wall_now - boot_s_now
        # We capture this once from the first message with time_boot_ms.
        if self._boot_to_unix_offset_s is None and self._external_clock_offset_s is not None:
            time_boot_ms_init = getattr(msg, "time_boot_ms", None)
            if time_boot_ms_init is not None and time_boot_ms_init > 0:
                boot_s = float(time_boot_ms_init) / 1000.0
                # drone wall time approximation
                drone_wall_now = now_wall - self._external_clock_offset_s
                self._boot_to_unix_offset_s = drone_wall_now - boot_s
                self._boot_to_unix_last_mono = time.monotonic()

        # Prefer unix microsecond timestamps if present and plausible
        timestamp_us = getattr(msg, "time_usec", None)
        if isinstance(timestamp_us, (int, float)) and timestamp_us > 1_000_000_000_000:
            sent_time = float(timestamp_us) / 1_000_000.0
            latency_ms = (now_wall - sent_time) * 1000.0
        else:
            # Use boot time + SYSTEM_TIME offset when available
            time_boot_ms = getattr(msg, "time_boot_ms", None)
            if time_boot_ms is None or self._boot_to_unix_offset_s is None:
                return
            sent_time = self._boot_to_unix_offset_s + (float(time_boot_ms) / 1000.0)
            latency_ms = (now_wall - sent_time) * 1000.0

        # Filter out implausible samples (negative or extreme)
        if latency_ms < 0 or latency_ms > 60_000:
            return

        self._latency_samples.append(latency_ms)
        if self._last_latency_ms is not None:
            self._latency_jitter_samples.append(abs(latency_ms - self._last_latency_ms))
        self._last_latency_ms = latency_ms
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get comprehensive MAVLink metrics."""
        with self._lock:
            end_time = self._end_time_mono if self._end_time_mono > 0 else time.monotonic()
            duration_s = end_time - self._start_time_mono if self._start_time_mono > 0 else 0.0
            
            # Calculate rates
            rx_pps = self._total_rx / duration_s if duration_s > 0 else None
            tx_pps = self._total_tx / duration_s if duration_s > 0 else None
            
            # Heartbeat stats
            hb_interval_avg = 0.0
            if self._heartbeat_intervals:
                hb_interval_avg = sum(self._heartbeat_intervals) / len(self._heartbeat_intervals)
            
            # Expected heartbeats (1 Hz)
            expected_hb = int(duration_s)
            self._heartbeat.expected_count = expected_hb
            
            # Command latency stats
            cmd_latency_avg = 0.0
            cmd_latency_p95 = 0.0
            if self._commands.latency_samples:
                samples = sorted(self._commands.latency_samples)
                cmd_latency_avg = sum(samples) / len(samples)
                p95_idx = int(len(samples) * 0.95)
                cmd_latency_p95 = samples[min(p95_idx, len(samples) - 1)]
            
            # Message latency stats (timestamped messages)
            msg_latency_avg = None
            msg_latency_p95 = None
            if self._latency_samples:
                samples = sorted(self._latency_samples)
                msg_latency_avg = sum(samples) / len(samples)
                p95_idx = int(len(samples) * 0.95)
                msg_latency_p95 = samples[min(p95_idx, len(samples) - 1)]

            # Jitter stats
            jitter_avg = None
            jitter_p95 = None
            if self._latency_jitter_samples:
                jitter_samples = sorted(self._latency_jitter_samples)
                jitter_avg = sum(jitter_samples) / len(jitter_samples)
                j95_idx = int(len(jitter_samples) * 0.95)
                jitter_p95 = jitter_samples[min(j95_idx, len(jitter_samples) - 1)]

            latency_invalid_reason = None
            if not self._latency_samples:
                if self._boot_to_unix_offset_s is None:
                    latency_invalid_reason = "missing_system_time_reference"
                else:
                    latency_invalid_reason = "no_timestamped_messages"
            elif len(self._latency_samples) < self._min_latency_samples:
                latency_invalid_reason = "insufficient_samples"

            # RTT stats (command -> ack)
            rtt_avg = None
            rtt_p95 = None
            if self._rtt_samples_ms:
                rtt_samples = sorted(self._rtt_samples_ms)
                rtt_avg = sum(rtt_samples) / len(rtt_samples)
                r95_idx = int(len(rtt_samples) * 0.95)
                rtt_p95 = rtt_samples[min(r95_idx, len(rtt_samples) - 1)]

            rtt_invalid_reason = None
            if self._rtt_samples_ms:
                if len(self._rtt_samples_ms) < self._min_rtt_samples:
                    rtt_invalid_reason = "insufficient_samples"
            elif self._commands.cmd_sent > 0:
                rtt_invalid_reason = "no_command_ack"
            else:
                rtt_invalid_reason = "no_rtt_samples"

            one_way_latency_valid = latency_invalid_reason is None
            rtt_valid = rtt_invalid_reason is None
            
            # Message type counts
            msg_type_counts = {
                stats.msg_name: stats.count_rx
                for stats in self._msg_stats.values()
            }
            
            # Stream rate (messages per second, excluding heartbeat)
            non_hb_msgs = sum(
                stats.count_rx for stats in self._msg_stats.values()
                if stats.msg_name != "HEARTBEAT"
            )
            stream_rate = non_hb_msgs / duration_s if duration_s > 0 else None
            recent_messages = self._recent_messages_locked(limit=20)
            recent_statustext = self._recent_status_text_locked(limit=5)
            top_message_types = self._top_message_types_locked(limit=8)
            link_status = self._link_status_locked(duration_s=duration_s, rx_pps=rx_pps)
            flight_controller = {
                "fc_mode": self._fc_mode,
                "fc_armed_state": self._fc_armed,
                "fc_heartbeat_age_ms": link_status.get("heartbeat_age_ms"),
                "fc_attitude_update_rate_hz": None,
                "fc_position_update_rate_hz": None,
                "fc_battery_voltage_v": self._fc_batt_voltage_v,
                "fc_battery_current_a": self._fc_batt_current_a,
                "fc_battery_remaining_percent": self._fc_batt_remaining_pct,
                "fc_cpu_load_percent": self._fc_cpu_load_pct,
                "fc_sensor_health_flags": self._fc_sensor_health_flags,
            }

            if self._fc_attitude_count > 1 and self._fc_attitude_last_mono > self._fc_attitude_first_mono:
                duration = self._fc_attitude_last_mono - self._fc_attitude_first_mono
                if duration > 0:
                    flight_controller["fc_attitude_update_rate_hz"] = round(self._fc_attitude_count / duration, 3)

            if self._fc_position_count > 1 and self._fc_position_last_mono > self._fc_position_first_mono:
                duration = self._fc_position_last_mono - self._fc_position_first_mono
                if duration > 0:
                    flight_controller["fc_position_update_rate_hz"] = round(self._fc_position_count / duration, 3)
            
            return {
                # Basic counts
                "total_msgs_sent": self._total_tx,
                "total_msgs_received": self._total_rx,
                "total_bytes_sent": self._total_bytes_tx,
                "total_bytes_received": self._total_bytes_rx,
                
                # Rates
                "tx_pps": None if tx_pps is None else round(tx_pps, 2),
                "rx_pps": None if rx_pps is None else round(rx_pps, 2),
                "stream_rate_hz": None if stream_rate is None else round(stream_rate, 2),
                
                # Duration
                "start_time": self._start_time_mono,
                "end_time": end_time,
                "duration_s": round(duration_s, 3),
                
                # Message type breakdown
                "msg_type_counts": msg_type_counts,
                
                # Heartbeat
                "heartbeat_count": self._heartbeat.count,
                "heartbeat_expected": expected_hb,
                "heartbeat_loss_count": self._heartbeat.loss_count,
                "heartbeat_interval_ms": round(hb_interval_avg, 2),
                "heartbeat_sysid": self._heartbeat.sysid,
                "heartbeat_compid": self._heartbeat.compid,
                "heartbeat_armed": self._heartbeat.armed,
                "heartbeat_mode": self._heartbeat.mode,
                
                # Sequence tracking
                "seq_gap_count": self._sequences.gaps,
                "seq_duplicate_count": self._sequences.duplicates,
                "seq_out_of_order_count": self._sequences.out_of_order,
                
                # Command tracking
                "cmd_sent_count": self._commands.cmd_sent,
                "cmd_ack_received_count": self._commands.cmd_ack_received,
                "cmd_ack_latency_avg_ms": None if self._commands.cmd_sent <= 0 else round(cmd_latency_avg, 2),
                "cmd_ack_latency_p95_ms": None if self._commands.cmd_sent <= 0 else round(cmd_latency_p95, 2),
                
                # Errors
                "crc_error_count": self._crc_errors,
                "decode_error_count": self._decode_errors,
                "msg_drop_count": self._msg_drops,
                
                # Message latency (if available)
                "message_latency_avg_ms": None if msg_latency_avg is None else round(msg_latency_avg, 2),
                "message_latency_p95_ms": None if msg_latency_p95 is None else round(msg_latency_p95, 2),

                # Latency / jitter summary
                "one_way_latency_avg_ms": None if msg_latency_avg is None else round(msg_latency_avg, 2),
                "one_way_latency_p95_ms": None if msg_latency_p95 is None else round(msg_latency_p95, 2),
                "jitter_avg_ms": None if jitter_avg is None else round(jitter_avg, 2),
                "jitter_p95_ms": None if jitter_p95 is None else round(jitter_p95, 2),
                "latency_sample_count": None if not self._latency_samples else len(self._latency_samples),
                "latency_invalid_reason": latency_invalid_reason,
                "one_way_latency_valid": one_way_latency_valid,

                "rtt_avg_ms": None if rtt_avg is None else round(rtt_avg, 2),
                "rtt_p95_ms": None if rtt_p95 is None else round(rtt_p95, 2),
                "rtt_sample_count": None if not self._rtt_samples_ms else len(self._rtt_samples_ms),
                "rtt_invalid_reason": rtt_invalid_reason,
                "rtt_valid": rtt_valid,
                
                # Protocol
                "protocol_version": self._protocol_version or None,
                "sniff_port": self._sniff_port,

                # Real-time observability
                "link_status": link_status,
                "flight_controller": flight_controller,
                "top_message_types": top_message_types,
                "recent_statustext": recent_statustext,
                "recent_messages": recent_messages,
            }
    
    def populate_schema_metrics(self, mavproxy_metrics, role: str = "gcs"):
        """
        Populate the schema dataclass from collected metrics.
        
        Args:
            mavproxy_metrics: MavProxyDroneMetrics or MavProxyGcsMetrics instance
            role: "gcs" or "drone"
        """
        m = self.get_metrics()
        
        if role == "gcs":
            mavproxy_metrics.mavproxy_gcs_total_msgs_received = m["total_msgs_received"]
            mavproxy_metrics.mavproxy_gcs_seq_gap_count = m["seq_gap_count"]
        else:
            mavproxy_metrics.mavproxy_drone_start_time = m["start_time"]
            mavproxy_metrics.mavproxy_drone_end_time = m["end_time"]
            mavproxy_metrics.mavproxy_drone_tx_pps = m["tx_pps"]
            mavproxy_metrics.mavproxy_drone_rx_pps = m["rx_pps"]
            mavproxy_metrics.mavproxy_drone_total_msgs_sent = m["total_msgs_sent"]
            mavproxy_metrics.mavproxy_drone_total_msgs_received = m["total_msgs_received"]
            mavproxy_metrics.mavproxy_drone_msg_type_counts = m["msg_type_counts"]
            mavproxy_metrics.mavproxy_drone_heartbeat_interval_ms = m["heartbeat_interval_ms"]
            mavproxy_metrics.mavproxy_drone_heartbeat_loss_count = m["heartbeat_loss_count"]
            mavproxy_metrics.mavproxy_drone_seq_gap_count = m["seq_gap_count"]
            mavproxy_metrics.mavproxy_drone_cmd_sent_count = m["cmd_sent_count"]
            mavproxy_metrics.mavproxy_drone_cmd_ack_received_count = m["cmd_ack_received_count"]
            mavproxy_metrics.mavproxy_drone_cmd_ack_latency_avg_ms = m["cmd_ack_latency_avg_ms"]
            mavproxy_metrics.mavproxy_drone_cmd_ack_latency_p95_ms = m["cmd_ack_latency_p95_ms"]
            mavproxy_metrics.mavproxy_drone_stream_rate_hz = m["stream_rate_hz"]
    
    def populate_mavlink_integrity(self, integrity_metrics):
        """
        Populate MAVLink integrity metrics.
        
        Args:
            integrity_metrics: MavLinkIntegrityMetrics instance
        """
        m = self.get_metrics()
        
        integrity_metrics.mavlink_sysid = m["heartbeat_sysid"]
        integrity_metrics.mavlink_compid = m["heartbeat_compid"]
        integrity_metrics.mavlink_protocol_version = m["protocol_version"] or None
        integrity_metrics.mavlink_packet_crc_error_count = m["crc_error_count"]
        integrity_metrics.mavlink_decode_error_count = m["decode_error_count"]
        integrity_metrics.mavlink_msg_drop_count = m["msg_drop_count"]
        integrity_metrics.mavlink_out_of_order_count = m["seq_out_of_order_count"]
        integrity_metrics.mavlink_duplicate_count = m["seq_duplicate_count"]
        integrity_metrics.mavlink_message_latency_avg_ms = m["message_latency_avg_ms"]

    def get_flight_controller_metrics(self) -> Dict[str, Any]:
        """Return derived flight controller telemetry metrics."""
        with self._lock:
            now = time.monotonic()

            hb_age_ms = 0.0
            if self._fc_heartbeat_last_mono > 0:
                hb_age_ms = max(0.0, (now - self._fc_heartbeat_last_mono) * 1000.0)

            attitude_rate_hz = 0.0
            if self._fc_attitude_count > 1 and self._fc_attitude_last_mono > self._fc_attitude_first_mono:
                duration = self._fc_attitude_last_mono - self._fc_attitude_first_mono
                if duration > 0:
                    attitude_rate_hz = self._fc_attitude_count / duration

            position_rate_hz = 0.0
            if self._fc_position_count > 1 and self._fc_position_last_mono > self._fc_position_first_mono:
                duration = self._fc_position_last_mono - self._fc_position_first_mono
                if duration > 0:
                    position_rate_hz = self._fc_position_count / duration

            return {
                "fc_mode": self._fc_mode,
                "fc_armed_state": self._fc_armed,
                "fc_heartbeat_age_ms": hb_age_ms,
                "fc_attitude_update_rate_hz": attitude_rate_hz,
                "fc_position_update_rate_hz": position_rate_hz,
                "fc_battery_voltage_v": self._fc_batt_voltage_v,
                "fc_battery_current_a": self._fc_batt_current_a,
                "fc_battery_remaining_percent": self._fc_batt_remaining_pct,
                "fc_cpu_load_percent": self._fc_cpu_load_pct,
                "fc_sensor_health_flags": self._fc_sensor_health_flags,
            }
    def get_chronos_data(self) -> Dict[str, Any]:
        """
        Get latest telemetry for Chronos Sensor Fusion.
        Returns dict with "alt", "hdg", "batt".
        """
        with self._lock:
            return {
                "alt": self._last_telemetry["alt_rel_m"],
                "hdg": self._last_telemetry["hdg_deg"],
                "batt": self._last_telemetry["batt_rem_pct"]
            }

# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("MAVLINK METRICS COLLECTOR TEST")
    print("=" * 60)
    
    collector = MavLinkMetricsCollector(role="gcs")
    print(f"Role: {collector.role}")
    print(f"pymavlink available: {HAS_PYMAVLINK}")
    
    # Start sniffing (this will bind to a port)
    print("\nStarting collector on port 14599 (test port)...")
    collector.start_sniffing(port=14599)
    
    # Wait a bit
    time.sleep(2.0)
    
    # Stop and get metrics
    metrics = collector.stop()
    
    print("\n--- COLLECTED METRICS ---")
    for k, v in metrics.items():
        if isinstance(v, dict) and len(v) > 5:
            print(f"  {k}: <{len(v)} items>")
        else:
            print(f"  {k}: {v}")
    
    print("\nTest completed!")
