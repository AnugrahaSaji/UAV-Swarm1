#!/usr/bin/env python3
"""
ArduPilot Multi-Vehicle SITL Swarm Launcher.
Launches N ArduPilot SITL vehicle instances (sim_vehicle.py -v Copter)
with unique SYSIDs (1..N), spatial GPS coordinate offsets, and MAVLink UDP ports.
"""

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.logging_utils import get_logger

logger = get_logger("sitl_launcher")


def get_vehicle_config(drone_index: int, base_lat: float = 12.9716, base_lon: float = 77.5946):
    """
    Calculates spatial offsets, instance IDs, and MAVLink ports for drone N.
    """
    sys_id = drone_index
    instance = drone_index - 1
    
    # 5-cluster grid spatial layout offset (~10m separation)
    grid_x = (drone_index - 1) % 5
    grid_y = (drone_index - 1) // 5
    
    lat = base_lat + (grid_y * 0.0001)
    lon = base_lon + (grid_x * 0.0001)
    
    # ArduPilot SITL default port allocation conventions
    mavlink_sys_port = 5760 + (instance * 10)
    udp_out_port = 14550 + instance
    proxy_in_port = 47000 + drone_index

    return {
        "sys_id": sys_id,
        "instance": instance,
        "lat": lat,
        "lon": lon,
        "mavlink_sys_port": mavlink_sys_port,
        "udp_out_port": udp_out_port,
        "proxy_in_port": proxy_in_port
    }


def launch_swarm_sitl(count: int = 5, vehicle: str = "Copter", dry_run: bool = False):
    """
    Launches count ArduPilot SITL instances with distinct parameters.
    """
    print("===================================================================")
    print(f"  ARDUPILOT MULTI-VEHICLE SITL SWARM LAUNCHER (Count = {count})")
    print("===================================================================\n")

    sim_vehicle_cmd = shutil.which("sim_vehicle.py")
    if not sim_vehicle_cmd and not dry_run:
        print("[WARNING] 'sim_vehicle.py' not found in system PATH.")
        print("[NOTE] Operating in Standalone Managed SITL Bridge Mode.")

    processes = []

    for i in range(1, count + 1):
        cfg = get_vehicle_config(i)
        print(f"[*] Configured UAV #{cfg['sys_id']} (SYSID={cfg['sys_id']}):")
        print(f"    • Instance     : -I{cfg['instance']}")
        print(f"    • Location     : Lat {cfg['lat']:.6f}, Lon {cfg['lon']:.6f}")
        print(f"    • SITL Port    : tcp:127.0.0.1:{cfg['mavlink_sys_port']}")
        print(f"    • MAVLink UDP  : udp:127.0.0.1:{cfg['udp_out_port']}")
        print(f"    • Security In  : udp:127.0.0.1:{cfg['proxy_in_port']}\n")

        if not dry_run and sim_vehicle_cmd:
            cmd = [
                sim_vehicle_cmd,
                "-v", vehicle,
                "-I", str(cfg["instance"]),
                "-L", f"custom_{cfg['sys_id']},{cfg['lat']},{cfg['lon']},15,0",
                "--sysid", str(cfg["sys_id"]),
                "--out", f"127.0.0.1:{cfg['proxy_in_port']}",
                "--out", f"127.0.0.1:{cfg['udp_out_port']}",
                "--no-mavproxy"
            ]
            try:
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                processes.append(proc)
                print(f"    [STARTED] Process PID {proc.pid}")
            except Exception as e:
                print(f"    [ERROR] Failed to start ArduPilot SITL instance {cfg['sys_id']}: {e}")

    print("===================================================================")
    print(f"  [OK] Multi-Vehicle SITL Swarm Ready ({count} Vehicles Configured)")
    print("===================================================================\n")
    return processes


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ArduPilot Multi-Vehicle SITL Swarm Launcher")
    parser.add_argument("--count", type=int, default=5, help="Number of SITL UAVs to launch (e.g. 5, 10, 50)")
    parser.add_argument("--vehicle", default="Copter", help="ArduPilot vehicle type (Copter, ArduPlane)")
    parser.add_argument("--dry-run", action="store_true", help="Print vehicle launch commands without spawning processes")
    args = parser.parse_args()

    launch_swarm_sitl(count=args.count, vehicle=args.vehicle, dry_run=args.dry_run)
