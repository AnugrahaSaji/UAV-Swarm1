"""
Local System Monitor (Drone Side)
sscheduler/local_mon.py

Collects local safety metrics:
- Pixhawk Battery (via local MAVLink sniff)
- Armed State (via local MAVLink sniff)
- Pi Temperature (thermal_zone0)
- Pi CPU Usage (psutil)
- Process Health

Designed to be fail-safe: if metrics fail, report safe defaults or error flags.
"""

import os
import time
import threading
import logging
import socket
from pathlib import Path
from collections import deque
from dataclasses import dataclass

try:
    import psutil
except ImportError:
    psutil = None

try:
    from pymavlink import mavutil
except ImportError:
    mavutil = None

# Default thermal zone for Raspberry Pi
THERMAL_ZONE_PATH = "/sys/class/thermal/thermal_zone0/temp"

@dataclass(frozen=True)
class LocalMetrics:
    temp_c: float
    temp_roc: float
    cpu_pct: float
    battery_mv: int
    battery_pct: int
    battery_roc: float
    armed: bool
    mav_age_s: float

class LocalMonitor:
    def __init__(self, mav_port=14555):
        self.mav_port = mav_port
        self.running = False
        self.thread = None
        self.lock = threading.Lock()
        
        # Metrics State
        self.battery_mv = 0
        self.battery_pct = 0
        self.armed = False
        self.cpu_freq = 0.0
        self.cpu_pct = 0.0
        self.temp_c = 0.0
        
        # Rate of change tracking
        self.temp_history = deque(maxlen=60) # 1 minute at 1Hz
        self.batt_history = deque(maxlen=60)
        
        self.temp_roc = 0.0 # deg C per minute
        self.batt_roc = 0.0 # mV per minute
        
        self.mav_conn = None
        self.last_mav_msg = 0.0

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.thread.start()
        logging.info(f"LocalMonitor started (MAVLink port {self.mav_port})")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2.0)
        if self.mav_conn:
            self.mav_conn.close()

    def _connect_mav(self):
        if not mavutil:
            return
        try:
            # Listen on UDP port for MAVLink broadcast from local MAVProxy
            self.mav_conn = mavutil.mavlink_connection(f"udpin:127.0.0.1:{self.mav_port}")
        except Exception as e:
            logging.error(f"Local MAVLink bind failed: {e}")

    def _read_thermal(self):
        try:
            if os.path.exists(THERMAL_ZONE_PATH):
                with open(THERMAL_ZONE_PATH, "r") as f:
                    # Value is in millidegrees C
                    return int(f.read().strip()) / 1000.0
        except Exception:
            pass
        return 0.0

    def _read_cpu(self):
        if not psutil:
            return 0.0, 0.0
        try:
            freq = psutil.cpu_freq()
            current_freq = freq.current if freq else 0.0
            pct = psutil.cpu_percent(interval=None)
            return current_freq, pct
        except Exception:
            return 0.0, 0.0

    def _update_rates(self, now):
        # Temperature ROC
        self.temp_history.append((now, self.temp_c))
        if len(self.temp_history) > 10:
            t0, v0 = self.temp_history[0]
            t1, v1 = self.temp_history[-1]
            dt_min = (t1 - t0) / 60.0
            if dt_min > 0:
                self.temp_roc = (v1 - v0) / dt_min

        # Battery ROC
        if self.battery_mv > 0:
            self.batt_history.append((now, self.battery_mv))
            if len(self.batt_history) > 10:
                t0, v0 = self.batt_history[0]
                t1, v1 = self.batt_history[-1]
                dt_min = (t1 - t0) / 60.0
                if dt_min > 0:
                    self.batt_roc = (v1 - v0) / dt_min

    def _monitor_loop(self):
        self._connect_mav()
        
        while self.running:
            now = time.time()
            
            # 1. Read System Metrics
            self.temp_c = self._read_thermal()
            self.cpu_freq, self.cpu_pct = self._read_cpu()
            
            # 2. Read MAVLink (drain queue)
            if self.mav_conn:
                while True:
                    msg = self.mav_conn.recv_match(blocking=False)
                    if not msg:
                        break
                    
                    self.last_mav_msg = now
                    msg_type = msg.get_type()
                    
                    if msg_type == 'SYS_STATUS':
                        self.battery_mv = msg.voltage_battery
                        self.battery_pct = msg.battery_remaining
                    elif msg_type == 'HEARTBEAT':
                        if msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
                            self.armed = True
                        else:
                            self.armed = False

            # 3. Update Rates
            self._update_rates(now)
            
            time.sleep(1.0)

    def get_metrics(self) -> LocalMetrics:
        """Return immutable snapshot of local metrics."""
        return LocalMetrics(
            temp_c=self.temp_c,
            temp_roc=self.temp_roc,
            cpu_pct=self.cpu_pct,
            battery_mv=self.battery_mv,
            battery_pct=self.battery_pct,
            battery_roc=self.batt_roc,
            armed=self.armed,
            mav_age_s=time.time() - self.last_mav_msg if self.last_mav_msg > 0 else 999.0
        )
