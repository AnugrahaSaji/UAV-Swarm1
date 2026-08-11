import sys
from dataclasses import fields
from pathlib import Path

sys.path.insert(0, "C:/Users/burak/ptojects/secure-tunnel")
from core import metrics_schema as ms

category_meta = {
    "run_context": "Intended: capture run/session context. Implemented: MetricsAggregator.start_suite populates via EnvironmentCollector. Conditions: ENV collector available; git/oqs may be unavailable -> empty strings. Failure: fields None if env lookup fails. Validity: CONDITIONAL.",
    "crypto_identity": "Intended: suite identity. Implemented: MetricsAggregator.start_suite sets from suite config. Conditions: suite_id resolves in core.suites. Failure: unknown suite -> None. Validity: CONDITIONAL.",
    "lifecycle": "Intended: suite timing. Implemented: MetricsAggregator.start_suite and finalize_suite timestamps. Conditions: MetricsAggregator used. Failure: None if not started. Validity: CONDITIONAL.",
    "handshake": "Intended: handshake timing/success. Implemented: record_handshake_start/end calls from schedulers. Conditions: scheduler must call; otherwise None. Failure: handshake_status_missing. Validity: CONDITIONAL.",
    "crypto_primitives": "Intended: primitive timings/artifact sizes. Implemented: MetricsAggregator.record_crypto_primitives merges handshake metrics. Conditions: handshake metrics populated. Failure: handshake_primitives_missing. Validity: CONDITIONAL.",
    "rekey": "Intended: rekey counters/blackout. Implemented: record_data_plane_metrics uses proxy counters. Conditions: proxy counters captured. Failure: proxy_rekey_counters_missing. Validity: CONDITIONAL.",
    "data_plane": "Intended: proxy throughput/counters. Implemented: record_data_plane_metrics + finalize_suite. Conditions: proxy counters captured. Failure: proxy_counters_missing. Validity: CONDITIONAL.",
    "latency_jitter": "Intended: MAVLink latency/jitter. Implemented: MavLinkMetricsCollector. Conditions: MAVLink collector available and timestamped messages. Failure: latency_invalid_reason. Validity: CONDITIONAL.",
    "mavproxy_drone": "Intended: drone MAVProxy stats. Implemented: MavLinkMetricsCollector.populate_schema_metrics. Conditions: MAVLink collector available. Failure: mavlink_collector_unavailable. Validity: CONDITIONAL.",
    "mavproxy_gcs": "Intended: GCS validation metrics only. Implemented: peer merge via MetricsAggregator._merge_peer_data. Conditions: GCS sends mavlink_validation. Failure: gcs_mavlink_validation_missing. Validity: CONDITIONAL.",
    "mavlink_integrity": "Intended: MAVLink integrity. Implemented: MavLinkMetricsCollector.populate_mavlink_integrity. Conditions: MAVLink collector. Failure: mavlink_collector_unavailable. Validity: CONDITIONAL.",
    "fc_telemetry": "Intended: FC telemetry. Implemented: MavLink collector get_flight_controller_metrics. Conditions: drone role + MAVLink collector. Failure: mavlink_collector_unavailable. Validity: CONDITIONAL.",
    "control_plane": "Intended: scheduler actions. Implemented: MetricsAggregator.record_control_plane_metrics. Conditions: scheduler calls. Failure: not recorded. Validity: CONDITIONAL.",
    "system_drone": "Intended: drone resource stats. Implemented: SystemCollector samples. Conditions: background collection on. Failure: no_system_samples. Validity: CONDITIONAL.",
    "system_gcs": "Intended: GCS resources. Implemented: deprecated; null unless peer merges. Conditions: GCS metrics provided. Failure: gcs_system_metrics_missing. Validity: CONDITIONAL/PRUNED.",
    "power_energy": "Intended: power/energy. Implemented: PowerCollector sampling. Conditions: power backend available + samples. Failure: no_power_samples. Validity: CONDITIONAL.",
    "observability": "Intended: sampling stats. Implemented: based on system samples. Conditions: system samples present. Failure: no_system_samples. Validity: CONDITIONAL.",
    "validation": "Intended: integrity/pass-fail. Implemented: based on observability + handshake. Conditions: handshake status + samples. Failure: handshake_status_missing. Validity: CONDITIONAL.",
}


def emit_fields(prefix, cls):
    return [f"{prefix}.{f.name}" for f in fields(cls)]


metric_paths = []
metric_paths += emit_fields("run_context", ms.RunContextMetrics)
metric_paths += emit_fields("crypto_identity", ms.SuiteCryptoIdentity)
metric_paths += emit_fields("lifecycle", ms.SuiteLifecycleTimeline)
metric_paths += emit_fields("handshake", ms.HandshakeMetrics)
metric_paths += emit_fields("crypto_primitives", ms.CryptoPrimitiveBreakdown)
metric_paths += emit_fields("rekey", ms.RekeyMetrics)
metric_paths += emit_fields("data_plane", ms.DataPlaneMetrics)
metric_paths += emit_fields("latency_jitter", ms.LatencyJitterMetrics)
metric_paths += emit_fields("mavproxy_drone", ms.MavProxyDroneMetrics)
metric_paths += emit_fields("mavproxy_gcs", ms.MavProxyGcsMetrics)
metric_paths += emit_fields("mavlink_integrity", ms.MavLinkIntegrityMetrics)
metric_paths += emit_fields("fc_telemetry", ms.FlightControllerTelemetry)
metric_paths += emit_fields("control_plane", ms.ControlPlaneMetrics)
metric_paths += emit_fields("system_drone", ms.SystemResourcesDrone)
metric_paths += emit_fields("system_gcs", ms.SystemResourcesGcs)
metric_paths += emit_fields("power_energy", ms.PowerEnergyMetrics)
metric_paths += emit_fields("observability", ms.ObservabilityMetrics)
metric_paths += emit_fields("validation", ms.ValidationMetrics)

lines = []
lines.append("Metric | Intended | Implemented | File | Field | Conditions | Failure Mode | Scientific Validity")
lines.append("---|---|---|---|---|---|---|---")
for path in metric_paths:
    group = path.split(".")[0]
    meta = category_meta.get(group, "CONDITIONAL")
    intended = meta.split("Implemented:")[0].replace("Intended:", "").strip()
    implemented = "CONDITIONAL" if "Implemented" in meta else "NOT IMPLEMENTED"
    lines.append(
        f"{path} | {intended} | {implemented} | core/metrics_schema.py; core/metrics_aggregator.py | {path} | {meta} | See metric_status in metrics_aggregator | CONDITIONAL"
    )

out = Path("C:/Users/burak/ptojects/secure-tunnel/text-files/metric_truth_table.md")
out.write_text("\n".join(lines), encoding="utf-8")
print(f"rows {len(metric_paths)} out {out}")
