#!/usr/bin/env python3
"""
Verify dashboard truthfulness against comprehensive suite metrics.

Fails if:
- A displayed metric is missing (null) without metric_status reason
- A displayed metric is present while marked invalid/not_collected
- Latency exists without samples
- RTT exists without command send count
- Defaults mask missing data
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
COMPREHENSIVE_DIR = ROOT / "logs" / "benchmarks" / "comprehensive"


DISPLAYED_FIELDS = [
    "run_context.run_id",
    "run_context.suite_id",
    "run_context.suite_index",
    "run_context.git_commit_hash",
    "run_context.gcs_hostname",
    "run_context.drone_hostname",
    "run_context.run_start_time_wall",
    "crypto_identity.kem_algorithm",
    "crypto_identity.sig_algorithm",
    "crypto_identity.aead_algorithm",
    "crypto_identity.suite_security_level",
    "handshake.handshake_total_duration_ms",
    "handshake.handshake_success",
    "handshake.handshake_failure_reason",
    "data_plane.packets_sent",
    "data_plane.packets_received",
    "data_plane.packets_dropped",
    "data_plane.packet_delivery_ratio",
    "latency_jitter.one_way_latency_avg_ms",
    "latency_jitter.one_way_latency_p95_ms",
    "latency_jitter.jitter_avg_ms",
    "latency_jitter.jitter_p95_ms",
    "latency_jitter.rtt_avg_ms",
    "latency_jitter.rtt_p95_ms",
    "mavlink_integrity.mavlink_out_of_order_count",
    "mavlink_integrity.mavlink_packet_crc_error_count",
    "mavlink_integrity.mavlink_decode_error_count",
    "mavlink_integrity.mavlink_duplicate_count",
    "system_drone.cpu_usage_avg_percent",
    "system_drone.cpu_usage_peak_percent",
    "system_drone.memory_rss_mb",
    "system_drone.temperature_c",
    "system_gcs.cpu_usage_avg_percent",
    "system_gcs.cpu_usage_peak_percent",
    "system_gcs.memory_rss_mb",
    "system_gcs.temperature_c",
    "power_energy.power_sensor_type",
    "power_energy.power_avg_w",
    "power_energy.power_peak_w",
    "power_energy.energy_total_j",
    "power_energy.voltage_avg_v",
    "power_energy.current_avg_a",
    "power_energy.energy_per_handshake_j",
    "power_energy.power_sampling_rate_hz",
    "validation.collected_samples",
    "validation.lost_samples",
    "validation.success_rate_percent",
    "validation.benchmark_pass_fail",
]


def _get_path(data: Dict[str, Any], path: str) -> Any:
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def verify_suite(payload: Dict[str, Any], filepath: Path) -> List[str]:
    errors: List[str] = []
    metric_status = _get_path(payload, "validation.metric_status") or {}

    for field in DISPLAYED_FIELDS:
        value = _get_path(payload, field)
        status_entry = metric_status.get(field) or metric_status.get(field.split(".")[0])

        if value is None:
            if not status_entry:
                errors.append(f"{filepath}: missing value for {field} without metric_status")
        else:
            if status_entry and status_entry.get("status") in {"not_collected", "invalid", "not_implemented"}:
                errors.append(f"{filepath}: {field} has value but is marked {status_entry.get('status')}")

    # Latency sample checks
    latency_avg = _get_path(payload, "latency_jitter.one_way_latency_avg_ms")
    latency_count = _get_path(payload, "latency_jitter.latency_sample_count") or 0
    if latency_avg is not None and latency_count <= 0:
        errors.append(f"{filepath}: latency avg present without samples")
    if latency_count > 0 and latency_avg is None:
        errors.append(f"{filepath}: latency samples exist without avg")

    # RTT checks
    rtt_avg = _get_path(payload, "latency_jitter.rtt_avg_ms")
    rtt_count = _get_path(payload, "latency_jitter.rtt_sample_count") or 0
    cmd_sent = _get_path(payload, "mavproxy_drone.mavproxy_drone_cmd_sent_count") or 0
    if rtt_avg is not None and (rtt_count <= 0 or cmd_sent <= 0):
        errors.append(f"{filepath}: RTT avg present without samples or command sends")
    if rtt_count > 0 and rtt_avg is None:
        errors.append(f"{filepath}: RTT samples exist without avg")
    cmd_ack_avg = _get_path(payload, "mavproxy_drone.mavproxy_drone_cmd_ack_latency_avg_ms")
    if cmd_sent <= 0 and cmd_ack_avg is not None:
        errors.append(f"{filepath}: CMD ACK latency present without command sends")

    # MAVLink message latency consistency
    msg_latency = _get_path(payload, "mavlink_integrity.mavlink_message_latency_avg_ms")
    if msg_latency is not None and latency_count <= 0:
        errors.append(f"{filepath}: MAVLink message latency present without latency samples")

    return errors


def main() -> int:
    if not COMPREHENSIVE_DIR.exists():
        print("No comprehensive metrics directory found.")
        return 2

    files = list(COMPREHENSIVE_DIR.glob("*.json"))
    if not files:
        print("No comprehensive metrics files found.")
        return 2

    all_errors: List[str] = []
    for path in files:
        payload = _load_json(path)
        if not payload:
            all_errors.append(f"{path}: failed to parse JSON")
            continue
        all_errors.extend(verify_suite(payload, path))

    if all_errors:
        print("Truth verification FAILED:")
        for err in all_errors:
            print(f"- {err}")
        return 1

    print("Truth verification PASSED: all displayed metrics are traceable.")
    return 0


if __name__ == "__main__":
    sys.exit(main())