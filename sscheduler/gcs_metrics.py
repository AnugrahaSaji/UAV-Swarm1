"""
GCS Telemetry Metrics Collector (Schema v1)
sscheduler/gcs_metrics.py

Collects real-time receiver-side metrics for the GCS, matching schema uav.pqc.telemetry.v1.
Non-blocking, bounded memory, best-effort.
"""

import os
import time
import json
import threading
import socket
import logging
import math
from pathlib import Path
from collections import deque, defaultdict
from datetime import datetime, timezone
from core.config import CONFIG

try:
    import psutil
except ImportError:
    psutil = None

try:
    from pymavlink import mavutil
except ImportError:
    mavutil = None

# Constants
SCHEMA_NAME = "uav.pqc.telemetry.v1"
SCHEMA_VER = 1
WINDOW_S = 5.0
BURST_GAP_THRESHOLD_MS = 200.0
MAX_PACKETS_PER_LOOP = int(CONFIG.get("GCS_METRICS_PACKETS_PER_LOOP", 100))

class GcsMetricsCollector:
    def __init__(self, mavlink_host, mavlink_port, proxy_manager=None, mavproxy_proc=None, log_dir=None):
        self.mavlink_host = mavlink_host
        self.mavlink_port = mavlink_port
        self.proxy_manager = proxy_manager
        self.mavproxy_proc = mavproxy_proc
        
        if log_dir:
            self.log_dir = Path(log_dir)
        else:
            self.log_dir = Path(__file__).parent.parent / "logs"
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # Telemetry always writes to the production file. Simulation support removed.
        self.log_file = self.log_dir / "gcs_telemetry_v1.jsonl"
        
        self.running = False
        self.thread = None
        self.mav_conn = None
        self.sock = None
        self.lock = threading.Lock()
        
        # Identity
        self.pid = os.getpid()
        self.boot_id = int(time.time())
        
        # Metrics State (Sliding Window)
        self.arrival_times = deque() # (mono_s, size_bytes)
        self.gaps = deque()          # (mono_s, gap_ms)
        self.burst_gaps = 0          # Count of gaps > threshold in window
        
        # MAVLink State
        self.mav_state = {
            "heartbeat": None,
            "sys_status": None,
            "radio_status": None,
            "failsafe": {"flags": 0, "last_statustext": None},
            "decode_stats": {"ok": 0, "parse_errors": 0, "reason": None}
        }
        self.msg_rates = defaultdict(int) # msg_id -> count in window
        self.msg_timestamps = deque()     # (mono_s, msg_id)
        
        # Tunnel/Events
        self.events = [] # List of event dicts
        
        # Loop health
        self.last_tick_mono = 0.0
        self.loop_lag_ms = 0.0

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logging.info(f"GCS Metrics Collector v1 started on {self.mavlink_host}:{self.mavlink_port}")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.mav_conn:
            self.mav_conn.close()

    def _connect(self):
        # Use udpin to bind and listen for packets from MAVProxy
        conn_str = f"udpin:{self.mavlink_host}:{self.mavlink_port}"
        if not mavutil:
            logging.error("pymavlink is required for MAVLink telemetry collection")
            return False
        try:
            self.mav_conn = mavutil.mavlink_connection(conn_str, source_system=255)
            return True
        except Exception as e:
            logging.error(f"MAVLink connect failed: {e}")
            return False

    def _prune_windows(self, now_mono):
        cutoff = now_mono - WINDOW_S
        
        while self.arrival_times and self.arrival_times[0][0] < cutoff:
            self.arrival_times.popleft()
            
        while self.gaps and self.gaps[0][0] < cutoff:
            self.gaps.popleft()
            
        while self.msg_timestamps and self.msg_timestamps[0][0] < cutoff:
            _, msg_id = self.msg_timestamps.popleft()
            self.msg_rates[msg_id] = max(0, self.msg_rates[msg_id] - 1)

    def _process_mavlink(self, msg, now_mono):
        msg_type = msg.get_type()
        msg_id = msg.get_msgId()
        
        # Rate tracking
        self.msg_rates[msg_id] += 1
        self.msg_timestamps.append((now_mono, msg_id))
        
        if msg_type == 'HEARTBEAT':
            self.mav_state['heartbeat'] = {
                "age_ms": 0, # Updated at snapshot time
                "last_mono": now_mono,
                "armed": bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) if mavutil else False,
                "mode": msg.custom_mode,
                "sysid": msg.get_srcSystem(),
                "compid": msg.get_srcComponent()
            }
        elif msg_type == 'SYS_STATUS':
            self.mav_state['sys_status'] = {
                "battery_remaining_pct": msg.battery_remaining,
                "voltage_battery_mv": msg.voltage_battery,
                "drop_rate_comm": msg.drop_rate_comm,
                "errors_count": [msg.errors_count1, msg.errors_count2, msg.errors_count3, msg.errors_count4],
                "load_pct": msg.load / 10.0 # usually 1000 = 100%
            }
        elif msg_type == 'RADIO_STATUS':
            self.mav_state['radio_status'] = {
                "rssi": msg.rssi,
                "remrssi": msg.remrssi,
                "noise": msg.noise,
                "remnoise": msg.remnoise,
                "rxerrors": msg.rxerrors,
                "fixed": msg.fixed
            }
        elif msg_type == 'STATUSTEXT':
            txt = msg.text
            if isinstance(txt, bytes):
                txt = txt.decode('utf-8', errors='ignore')
            self.mav_state['failsafe']['last_statustext'] = txt

    def _read_packets(self):
        count = 0
        now_mono = time.monotonic()
        
        while count < MAX_PACKETS_PER_LOOP:
            ts_mono = None
            size = 0
            msg = None
            
            if self.mav_conn:
                try:
                    msg = self.mav_conn.recv_match(blocking=False)
                    if msg:
                        # Robust guard: Check for BAD_DATA explicitly
                        if msg.get_type() == 'BAD_DATA':
                            self.mav_state['decode_stats']['parse_errors'] += 1
                            # Bound reason string
                            reason = "MAVLink_bad_data"
                            if hasattr(msg, 'reason'):
                                reason = str(msg.reason)[:50]
                            self.mav_state['decode_stats']['reason'] = reason
                            continue

                        ts_mono = time.monotonic()
                        # Estimate size
                        size = 20 # Header
                        if hasattr(msg, 'get_payload'):
                             payload = msg.get_payload()
                             # Robust guard: Never call len(payload) unless payload is bytes-like
                             if payload is not None and isinstance(payload, (bytes, bytearray)):
                                 size += len(payload)
                             elif payload is None:
                                 # Payload is None, safe to ignore or handle
                                 pass
                        
                        self.mav_state['decode_stats']['ok'] += 1
                        self._process_mavlink(msg, ts_mono)
                except Exception as e:
                    self.mav_state['decode_stats']['parse_errors'] += 1
                    self.mav_state['decode_stats']['reason'] = str(e)[:50] # Bounded reason string
            if ts_mono:
                with self.lock:
                    # Gap detection
                    if self.arrival_times:
                        last_mono = self.arrival_times[-1][0]
                        gap_ms = (ts_mono - last_mono) * 1000.0
                        self.gaps.append((ts_mono, gap_ms))
                        if gap_ms > BURST_GAP_THRESHOLD_MS:
                            self.burst_gaps += 1
                    
                    self.arrival_times.append((ts_mono, size))
                count += 1
            else:
                break
        
        with self.lock:
            self._prune_windows(now_mono)
            # Prune burst gaps count (recalculate from window)
            self.burst_gaps = sum(1 for _, g in self.gaps if g > BURST_GAP_THRESHOLD_MS)

    def get_snapshot(self):
        now_mono_ns = time.monotonic_ns()
        now_wall_ns = time.time_ns()

        with self.lock:
            # Basic link metrics
            count = len(self.arrival_times)
            total_bytes = sum(s for _, s in self.arrival_times)

            rx_pps = (count / WINDOW_S) if WINDOW_S > 0 else 0.0
            rx_bps = (total_bytes / WINDOW_S) if WINDOW_S > 0 else 0.0

            silence_ms = 0.0
            if self.arrival_times:
                silence_ms = (time.monotonic() - self.arrival_times[-1][0]) * 1000.0

            gap_max_ms = 0.0
            gap_values = [g for _, g in self.gaps] if self.gaps else []
            if gap_values:
                gap_values_sorted = sorted(gap_values)
                gap_max_ms = gap_values_sorted[-1]
            else:
                gap_values_sorted = []

            def pct(vals, p):
                if not vals:
                    return 0.0
                k = max(0, min(len(vals) - 1, int(math.ceil((p / 100.0) * len(vals)) - 1)))
                return float(vals[k])

            gap_p90_ms = round(pct(gap_values_sorted, 90), 1)
            gap_p60_ms = round(pct(gap_values_sorted, 60), 1)

            # Jitter as mean absolute deviation of gaps (if available)
            jitter_ms = 0.0
            if len(gap_values_sorted) > 1:
                mean_gap = sum(gap_values_sorted) / len(gap_values_sorted)
                jitter_ms = sum(abs(g - mean_gap) for g in gap_values_sorted) / len(gap_values_sorted)

            # Blackout calculation: gaps larger than BLACKOUT_THRESHOLD_MS
            BLACKOUT_THRESHOLD_MS = 1000.0
            blackout_gaps = [g for g in gap_values_sorted if g >= BLACKOUT_THRESHOLD_MS]
            blackout_count = len(blackout_gaps)
            blackout_total_ms = round(sum(blackout_gaps), 1)

            # Minimal MAV health
            hb = self.mav_state.get('heartbeat')
            hb_age_ms = None
            if hb and 'last_mono' in hb:
                hb_age_ms = (time.monotonic() - hb['last_mono']) * 1000.0

            sys_status = self.mav_state.get('sys_status') or {}
            voltage_mv = sys_status.get('voltage_battery_mv') if isinstance(sys_status, dict) else None

            # Proxy status
            proxy_alive = False
            proxy_pid = 0
            if self.proxy_manager:
                try:
                    proxy_alive = self.proxy_manager.is_running()
                    if self.proxy_manager.managed_proc and getattr(self.proxy_manager.managed_proc, 'process', None):
                        proxy_pid = getattr(self.proxy_manager.managed_proc.process, 'pid', 0)
                except Exception:
                    proxy_alive = False

            reduced = {
                "schema": SCHEMA_NAME,
                "schema_ver": SCHEMA_VER,
                "sender": {
                    "role": "gcs",
                    "node_id": socket.gethostname(),
                    "pid": self.pid
                },
                "t": {
                    "wall_ns": now_wall_ns,
                    "mono_ns": now_mono_ns,
                    "boot_id": self.boot_id
                },
                "metrics": {
                    "link": {
                        "window_s": WINDOW_S,
                        "sample_count": count,
                        "rx_pps": round(rx_pps, 1),
                        "rx_bps": round(rx_bps, 1),
                        "silence_ms": round(silence_ms, 1),
                        "gap_max_ms": round(gap_max_ms, 1),
                        "gap_p90_ms": gap_p90_ms,
                        "gap_p60_ms": gap_p60_ms,
                        "jitter_ms": round(jitter_ms, 1),
                        "blackout_count": blackout_count,
                        "blackout_total_ms": blackout_total_ms
                    }
                },
                "mav": {
                    "heartbeat_age_ms": round(hb_age_ms, 1) if hb_age_ms is not None else None,
                    "voltage_battery_mv": voltage_mv
                },
                "proxy": {
                    "proxy_alive": proxy_alive,
                    "proxy_pid": proxy_pid
                }
            }

            # Clear one-shot events (we no longer export them by default)
            self.events.clear()

            return reduced

    def _run_loop(self):
        self._connect()
        last_log_time = time.monotonic()
        
        while self.running:
            loop_start = time.monotonic()
            
            # Reconnect
            if not self.mav_conn:
                if not self._connect():
                    time.sleep(1.0)
                    continue

            self._read_packets()
            
            # Logging (1Hz)
            if loop_start - last_log_time >= 1.0:
                self._write_log()
                last_log_time = loop_start
            
            # Loop health
            self.last_tick_mono = loop_start
            elapsed = time.monotonic() - loop_start
            self.loop_lag_ms = elapsed * 1000.0
            
            sleep_time = max(0.01, 0.1 - elapsed) # Aim for 10Hz loop
            time.sleep(sleep_time)

    def _write_log(self):
        try:
            snapshot = self.get_snapshot()
            # JSON serialization helper for non-serializable types
            def default(o):
                if isinstance(o, (datetime,)):
                    return o.isoformat()
                return str(o)
                
            with open(self.log_file, "a") as f:
                f.write(json.dumps(snapshot, default=default) + "\n")
        except Exception:
            pass

    def add_event(self, event_type, **kwargs):
        with self.lock:
            evt = {
                "type": event_type,
                "t_mono_ms": time.monotonic() * 1000.0,
                **kwargs
            }
            self.events.append(evt)
