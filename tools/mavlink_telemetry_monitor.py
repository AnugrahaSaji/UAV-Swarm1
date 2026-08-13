#!/usr/bin/env python3
"""Multi-Message Real Pixhawk MAVLink Telemetry Monitor & Performance Analyzer."""

import argparse
import json
import socket
import sys
import time
from collections import Counter, defaultdict

try:
    from pymavlink import mavutil
    HAS_PYMAVLINK = True
except ImportError:
    HAS_PYMAVLINK = False


def main():
    parser = argparse.ArgumentParser(description="Multi-Message Pixhawk Telemetry Monitor over PQC Tunnel")
    parser.add_argument("--host", default="127.0.0.1", help="GCS decrypted plaintext host")
    parser.add_argument("--port", type=int, default=47002, help="GCS decrypted plaintext port (default 47002)")
    parser.add_argument("--duration", type=float, default=30.0, help="Monitoring duration in seconds")
    parser.add_argument("--json-export", type=str, default=None, help="Path to export JSON benchmark summary")
    args = parser.parse_args()

    print(f"===========================================================")
    print(f" PQC Secure Tunnel: Live Pixhawk Telemetry Monitor")
    print(f" Listening on decrypted GCS port: udp:{args.host}:{args.port}")
    print(f" Duration: {args.duration:.1f} seconds")
    print(f"===========================================================\n")

    if not HAS_PYMAVLINK:
        print("Error: pymavlink is required. Run 'pip install pymavlink'")
        sys.exit(1)

    mav_conn = mavutil.mavlink_connection(f"udpin:{args.host}:{args.port}")
    
    msg_counts = Counter()
    msg_samples = {}
    total_bytes = 0
    total_packets = 0
    start_time = time.monotonic()
    last_print = time.monotonic()

    try:
        while True:
            now = time.monotonic()
            elapsed = now - start_time
            if args.duration > 0 and elapsed >= args.duration:
                break

            msg = mav_conn.recv_match(blocking=True, timeout=1.0)
            if msg is None:
                continue

            msg_type = msg.get_type()
            msg_counts[msg_type] += 1
            total_packets += 1
            
            # Record sample data for key telemetry types
            if msg_type == "ATTITUDE":
                msg_samples["ATTITUDE"] = f"Roll: {msg.roll:.3f} rad, Pitch: {msg.pitch:.3f} rad, Yaw: {msg.yaw:.3f} rad"
            elif msg_type == "GLOBAL_POSITION_INT":
                msg_samples["GLOBAL_POSITION_INT"] = f"Lat: {msg.lat/1e7:.5f}°, Lon: {msg.lon/1e7:.5f}°, Alt: {msg.alt/1000.0:.1f}m"
            elif msg_type == "GPS_RAW_INT":
                msg_samples["GPS_RAW_INT"] = f"Fix: {msg.fix_type}, Sats: {msg.satellites_visible}, Lat: {msg.lat/1e7:.5f}°"
            elif msg_type == "SYS_STATUS":
                msg_samples["SYS_STATUS"] = f"Load: {msg.load/10.0:.1f}%, BatVolt: {msg.voltage_battery/1000.0:.2f}V, BatCurr: {msg.current_battery/100.0:.2f}A"
            elif msg_type == "BATTERY_STATUS":
                msg_samples["BATTERY_STATUS"] = f"Volt: {msg.voltages[0]/1000.0:.2f}V, Remainder: {msg.battery_remaining}%"
            elif msg_type == "VFR_HUD":
                msg_samples["VFR_HUD"] = f"Airspeed: {msg.airspeed:.1f} m/s, GroundSpeed: {msg.groundspeed:.1f} m/s, Heading: {msg.heading}°"
            elif msg_type == "HEARTBEAT":
                msg_samples["HEARTBEAT"] = f"SysID: {msg.get_srcSystem()}, CompID: {msg.get_srcComponent()}, Type: {msg.type}, Autopilot: {msg.autopilot}"

            # Periodic status print every 3 seconds
            if now - last_print >= 3.0:
                last_print = now
                throughput_kbs = (total_packets * 150) / (elapsed * 1024.0)  # estimated throughput
                print(f"[{elapsed:.1f}s] Packets Decrypted: {total_packets} | Unique Msg Types: {len(msg_counts)} | Est. Speed: {throughput_kbs:.2f} KB/s")
                for mtype, sample in msg_samples.items():
                    print(f"   ├─ {mtype:20s} ({msg_counts[mtype]} msgs) -> {sample}")
                print()

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user.")

    total_time = time.monotonic() - start_time
    throughput = total_packets / max(0.1, total_time)

    print("\n===========================================================")
    print("      LIVE PIXHAWK TELEMETRY SUMMARY REPORT")
    print("===========================================================")
    print(f"Total Monitoring Time    : {total_time:.2f} seconds")
    print(f"Total Decrypted Packets  : {total_packets}")
    print(f"Telemetry Arrival Rate   : {throughput:.2f} packets/sec")
    print(f"Unique MAVLink Messages  : {len(msg_counts)}")
    print("-----------------------------------------------------------")
    print("MESSAGE TYPE BREAKDOWN:")
    for mtype, count in msg_counts.most_common():
        pct = (count / max(1, total_packets)) * 100.0
        print(f"  • {mtype:24s} : {count:5d} msgs ({pct:5.1f}%)")
    print("-----------------------------------------------------------")

    if args.json_export:
        report = {
            "duration_s": total_time,
            "total_packets": total_packets,
            "packets_per_sec": throughput,
            "unique_msg_types": len(msg_counts),
            "msg_breakdown": dict(msg_counts),
            "sample_telemetry": msg_samples,
        }
        with open(args.json_export, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        print(f"Report exported to: {args.json_export}")

    return 0


if __name__ == "__main__":
    main()
