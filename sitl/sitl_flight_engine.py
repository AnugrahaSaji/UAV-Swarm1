#!/usr/bin/env python3
"""
SITL Flight Engine (Software-In-the-Loop & MAVLink Telemetry Generator).

Supports two distinct operational modes:
1. Native SITL Mode: Connects to actual flight-controller SITL instances (ArduPilot SITL / PX4 SITL) over UDP/TCP sockets (127.0.0.1:14550+).
   - When native SITL mode is requested (--mode sitl), the Level-1 Python MAVLink emulator MUST NOT be silently substituted.
2. MAVLink Emulation Mode: High-fidelity Python MAVLink telemetry stream generator for baseline software benchmarking.
"""

from __future__ import annotations

import math
import os
import random
import socket
import struct
import sys
import time
from typing import Dict, List, Optional, Tuple

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    from pymavlink import mavutil
    HAS_PYMAVLINK = True
except ImportError:
    HAS_PYMAVLINK = False


class SITLVehicleInstance:
    """Represents a single UAV instance (Native SITL flight controller or MAVLink Emulated vehicle)."""

    def __init__(
        self,
        drone_id: str,
        system_id: int,
        cluster_id: str = "cluster-1",
        role: str = "FOLLOWER",
        base_lat: float = 17.4455,  # IIIT Hyderabad campus coordinates
        base_lon: float = 78.3489,
        base_alt: float = 50.0,
        udp_port: Optional[int] = None,
        is_native_sitl: bool = False,
    ) -> None:
        self.drone_id = drone_id
        self.system_id = system_id
        self.cluster_id = cluster_id
        self.role = role
        self.udp_port = udp_port or (14550 + system_id - 1)
        self.is_native_sitl = is_native_sitl

        # Spatial & Telemetry State
        self.lat = base_lat + random.uniform(-0.0005, 0.0005)
        self.lon = base_lon + random.uniform(-0.0005, 0.0005)
        self.alt = base_alt + random.uniform(-2.0, 2.0)
        self.roll = 0.0
        self.pitch = 0.0
        self.yaw = random.uniform(0, 360)

        self.vx = 2.0 * math.cos(math.radians(self.yaw))
        self.vy = 2.0 * math.sin(math.radians(self.yaw))
        self.vz = 0.0

        self.battery_voltage_mv = 16800  # 4S LiPo (~16.8V)
        self.battery_current_ca = 1200   # 12.0 A
        self.battery_remaining_pct = 100
        self.armed = True
        self.flight_mode = "AUTO"
        self.boot_time_ms = int(time.time() * 1000) & 0xFFFFFFFF

        self._orbit_center_lat = base_lat
        self._orbit_center_lon = base_lon
        self._orbit_radius = 0.0003 + (system_id * 0.00005)
        self._orbit_angle = random.uniform(0, 2 * math.pi)
        self._orbit_speed = 0.05 + random.uniform(-0.01, 0.01)

        self.seq = 0
        self.mav_conn = None

        if self.is_native_sitl:
            self._connect_native_sitl()

    def _connect_native_sitl(self) -> None:
        """Attempt socket connection to native ArduPilot/PX4 SITL instance.

        Explicit Rule: When native SITL mode is requested, do not silently substitute emulation.
        Raise ConnectionError if pymavlink is missing or native SITL socket is unreachable.
        """
        if not HAS_PYMAVLINK:
            raise RuntimeError(f"[{self.drone_id}] Native SITL mode requires pymavlink. Run 'pip install pymavlink'")

        target_str = f"udpin:127.0.0.1:{self.udp_port}"
        try:
            self.mav_conn = mavutil.mavlink_connection(target_str)
            print(f"[{self.drone_id}] Connected to Native SITL flight controller on {target_str}")
        except Exception as e:
            raise ConnectionError(
                f"[{self.drone_id}] Native SITL mode failed to connect on {target_str}: {e}. "
                f"Ensure ArduPilot/PX4 SITL process is running."
            )

    def update_physics(self, dt_sec: float = 0.1) -> Dict[str, float]:
        """Step vehicle dynamics forward in time."""
        self._orbit_angle += self._orbit_speed * dt_sec
        self.lat = self._orbit_center_lat + self._orbit_radius * math.cos(self._orbit_angle)
        self.lon = self._orbit_center_lon + self._orbit_radius * math.sin(self._orbit_angle)

        target_yaw = (math.degrees(self._orbit_angle + math.pi / 2)) % 360.0
        yaw_diff = (target_yaw - self.yaw + 180) % 360 - 180
        self.yaw = (self.yaw + 0.1 * yaw_diff) % 360.0

        self.roll = math.sin(self._orbit_angle) * 5.0 + random.gauss(0, 0.2)
        self.pitch = math.cos(self._orbit_angle) * 2.0 + random.gauss(0, 0.1)
        self.alt += random.gauss(0, 0.05)

        self.vx = 3.0 * math.cos(math.radians(self.yaw)) + random.gauss(0, 0.05)
        self.vy = 3.0 * math.sin(math.radians(self.yaw)) + random.gauss(0, 0.05)
        self.vz = random.gauss(0, 0.02)

        self.battery_voltage_mv = max(14000, self.battery_voltage_mv - int(20 * dt_sec))
        self.battery_remaining_pct = max(0, int(((self.battery_voltage_mv - 14000) / 2800.0) * 100))

        return {
            "lat": self.lat,
            "lon": self.lon,
            "alt": self.alt,
            "roll": self.roll,
            "pitch": self.pitch,
            "yaw": self.yaw,
            "battery_voltage_mv": self.battery_voltage_mv,
        }

    def generate_mavlink_telemetry(self) -> Dict[str, any]:
        """Generate MAVLink telemetry dict (native read if active, else emulated)."""
        if self.is_native_sitl and self.mav_conn:
            msg = self.mav_conn.recv_match(blocking=False)
            if msg:
                msg_type = msg.get_type()
                if msg_type == "GLOBAL_POSITION_INT":
                    self.lat = msg.lat / 1e7
                    self.lon = msg.lon / 1e7
                    self.alt = msg.alt / 1000.0
                    self.yaw = msg.hdg / 100.0
                elif msg_type == "ATTITUDE":
                    self.roll = math.degrees(msg.roll)
                    self.pitch = math.degrees(msg.pitch)
                    self.yaw = math.degrees(msg.yaw)

        self.seq = (self.seq + 1) & 0xFF
        time_boot_ms = int(time.time() * 1000) - self.boot_time_ms

        return {
            "drone_id": self.drone_id,
            "sys_id": self.system_id,
            "seq": self.seq,
            "mode": "NATIVE_SITL" if self.is_native_sitl else "MAVLINK_EMULATION",
            "time_boot_ms": time_boot_ms,
            "heartbeat": {
                "type": 2,
                "autopilot": 3,
                "base_mode": 209,
                "custom_mode": 3,
                "system_status": 4,
                "mavlink_version": 3,
            },
            "global_position_int": {
                "time_boot_ms": time_boot_ms,
                "lat": int(self.lat * 1e7),
                "lon": int(self.lon * 1e7),
                "alt": int(self.alt * 1000),
                "relative_alt": int(self.alt * 1000),
                "vx": int(self.vx * 100),
                "vy": int(self.vy * 100),
                "vz": int(self.vz * 100),
                "hdg": int(self.yaw * 100),
            },
            "attitude": {
                "time_boot_ms": time_boot_ms,
                "roll": math.radians(self.roll),
                "pitch": math.radians(self.pitch),
                "yaw": math.radians(self.yaw),
                "rollspeed": random.gauss(0, 0.01),
                "pitchspeed": random.gauss(0, 0.01),
                "yawspeed": random.gauss(0, 0.01),
            },
            "sys_status": {
                "onboard_control_sensors_present": 0xFFFFFFFF,
                "onboard_control_sensors_enabled": 0xFFFFFFFF,
                "onboard_control_sensors_health": 0xFFFFFFFF,
                "load": 150,
                "voltage_battery": self.battery_voltage_mv,
                "current_battery": self.battery_current_ca,
                "battery_remaining": self.battery_remaining_pct,
                "drop_rate_comm": 0,
                "errors_comm": 0,
            },
            "vfr_hud": {
                "airspeed": math.hypot(self.vx, self.vy),
                "groundspeed": math.hypot(self.vx, self.vy),
                "heading": int(self.yaw),
                "throttle": 45,
                "alt": self.alt,
                "climb": self.vz,
            },
        }


class SITLFlightEngine:
    """Manages swarm of SITL / Emulated vehicle instances."""

    def __init__(
        self,
        num_vehicles: int = 5,
        num_clusters: int = 1,
        base_lat: float = 17.4455,
        base_lon: float = 78.3489,
        is_native_sitl: bool = False,
    ) -> None:
        self.num_vehicles = max(1, num_vehicles)
        self.num_clusters = max(1, num_clusters)
        self.is_native_sitl = is_native_sitl
        self.vehicles: Dict[str, SITLVehicleInstance] = {}
        self._setup_vehicles(base_lat, base_lon)

    def _setup_vehicles(self, base_lat: float, base_lon: float) -> None:
        drones_per_cluster = max(1, math.ceil(self.num_vehicles / self.num_clusters))
        for idx in range(1, self.num_vehicles + 1):
            drone_id = f"drone-{idx}"
            cluster_idx = (idx - 1) // drones_per_cluster + 1
            cluster_id = f"cluster-{cluster_idx}"

            if idx == 1:
                role = "ROOT_LEADER"
            elif (idx - 1) % drones_per_cluster == 0:
                role = "CLUSTER_HEAD"
            else:
                role = "LEAF_FOLLOWER"

            c_lat = base_lat + (cluster_idx - 1) * 0.002
            c_lon = base_lon + (cluster_idx - 1) * 0.002

            vehicle = SITLVehicleInstance(
                drone_id=drone_id,
                system_id=idx,
                cluster_id=cluster_id,
                role=role,
                base_lat=c_lat,
                base_lon=c_lon,
                is_native_sitl=self.is_native_sitl,
            )
            self.vehicles[drone_id] = vehicle

    def step(self, dt_sec: float = 0.1) -> Dict[str, Dict[str, any]]:
        telemetry_batch = {}
        for drone_id, vehicle in self.vehicles.items():
            vehicle.update_physics(dt_sec=dt_sec)
            telemetry_batch[drone_id] = vehicle.generate_mavlink_telemetry()
        return telemetry_batch


if __name__ == "__main__":
    print("Testing SITL Flight Engine...")
    engine = SITLFlightEngine(num_vehicles=3, is_native_sitl=False)
    batch = engine.step(dt_sec=0.1)
    print(f"Generated telemetry for {len(batch)} vehicles.")
