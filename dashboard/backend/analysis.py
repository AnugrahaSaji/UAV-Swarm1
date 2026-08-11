"""
Analysis Module for PQC Benchmark Dashboard.

Provides Pandas-based analysis functions for:
- Per-suite metric extraction
- Cross-suite comparison
- Regime filtering
- Drone vs GCS metric split
"""

import csv
import json
from pathlib import Path
import pandas as pd
from typing import Dict, List, Optional, Any, Tuple, Iterable

try:
    from .models import (
        ComprehensiveSuiteMetrics,
        ComparisonResult,
        ReliabilityClass,
        SchemaField,
    )
except ImportError:
    from models import (
        ComprehensiveSuiteMetrics,
        ComparisonResult,
        ReliabilityClass,
        SchemaField,
    )


# =============================================================================
# SCHEMA METADATA
# =============================================================================

# Fields that are DEPRECATED/CONDITIONAL (from policy realignment)
DEPRECATED_FIELDS = {
    # No deprecated fields in current canonical schema
}

# Fields that are validation-only from GCS
CONDITIONAL_FIELDS = {
    "mavproxy_gcs.mavproxy_gcs_total_msgs_received",
    "mavproxy_gcs.mavproxy_gcs_seq_gap_count",
}

# Metric units
METRIC_UNITS = {
    "handshake_total_duration_ms": "ms",
    "protocol_handshake_duration_ms": "ms",
    "end_to_end_handshake_duration_ms": "ms",
    "kem_keygen_time_ms": "ms",
    "kem_encapsulation_time_ms": "ms",
    "kem_decapsulation_time_ms": "ms",
    "signature_sign_time_ms": "ms",
    "signature_verify_time_ms": "ms",
    "goodput_mbps": "Mbps",
    "achieved_throughput_mbps": "Mbps",
    "wire_rate_mbps": "Mbps",
    "packet_loss_ratio": "ratio",
    "packet_delivery_ratio": "ratio",
    "packet_delivery_ratio": "ratio",
    "packets_sent": "count",
    "packets_received": "count",
    "packets_dropped": "count",
    "rekey_duration_ms": "ms",
    "rekey_blackout_duration_ms": "ms",
    "power_avg_w": "W",
    "power_peak_w": "W",
    "energy_total_j": "J",
    "energy_per_handshake_j": "J",
    "voltage_avg_v": "V",
    "current_avg_a": "A",
    "cpu_usage_avg_percent": "%",
    "cpu_usage_peak_percent": "%",
    "memory_rss_mb": "MB",
    "temperature_c": "°C",
    "packets_sent": "count",
    "packets_received": "count",
    "packets_dropped": "count",
    "suite_total_duration_ms": "ms",
    "suite_active_duration_ms": "ms",
    "one_way_latency_avg_ms": "ms",
    "one_way_latency_p95_ms": "ms",
    "jitter_avg_ms": "ms",
    "jitter_p95_ms": "ms",
    "rtt_avg_ms": "ms",
    "rtt_p95_ms": "ms",
}


def is_suite_invalid(suite: ComprehensiveSuiteMetrics) -> bool:
    if getattr(suite, "ingest_status", None) in {"invalid_run", "comprehensive_failed"}:
        return True
    status = getattr(suite.validation, "metric_status", {}) or {}
    suite_validity = status.get("suite_validity")
    if isinstance(suite_validity, dict) and suite_validity.get("status") == "invalid":
        return True
    return False


def filter_valid_suites(suites: List[ComprehensiveSuiteMetrics]) -> List[ComprehensiveSuiteMetrics]:
    return [s for s in suites if not is_suite_invalid(s)]


def get_field_reliability(field_path: str) -> ReliabilityClass:
    """Get the reliability class for a field."""
    if field_path in DEPRECATED_FIELDS:
        return ReliabilityClass.DEPRECATED
    if field_path in CONDITIONAL_FIELDS:
        return ReliabilityClass.CONDITIONAL
    return ReliabilityClass.VERIFIED


def get_field_unit(field_name: str) -> str:
    """Get the unit for a field."""
    return METRIC_UNITS.get(field_name, "")


# =============================================================================
# SUITE DATA EXTRACTION
# =============================================================================

def suite_to_flat_dict(suite: ComprehensiveSuiteMetrics) -> Dict[str, Any]:
    """Flatten a suite's metrics into a single-level dictionary."""
    flat = {}
    data = suite.model_dump(exclude={"raw_drone", "raw_gcs", "gcs_validation"})
    
    for category, fields in data.items():
        if isinstance(fields, dict):
            for field, value in fields.items():
                # Skip complex nested structures for flat representation
                if isinstance(value, (list, dict)) and value:
                    continue
                flat[f"{category}.{field}"] = value
        else:
            flat[category] = fields
    
    return flat


TRUTH_TABLE_PATH = Path("logs/benchmarks/analysis_metrics/metrics_truth_table.csv")
SCHEMA_VS_OBSERVED_PATH = Path("logs/benchmarks/analysis_metrics/schema_vs_observed.json")
OBSERVED_SUMMARY_PATH = Path("logs/benchmarks/analysis_metrics/observed_summary.json")
CONSISTENCY_MATRIX_PATH = Path("logs/benchmarks/analysis_metrics/consistency_matrix.csv")
_TRUTH_TABLE_CACHE: Optional[Dict[str, Dict[str, Any]]] = None
_SCHEMA_VS_OBSERVED_CACHE: Optional[Dict[str, Any]] = None
_OBSERVED_SUMMARY_CACHE: Optional[Dict[str, Any]] = None
_CONSISTENCY_MATRIX_CACHE: Optional[Dict[str, str]] = None


def _load_truth_table() -> Dict[str, Dict[str, Any]]:
    global _TRUTH_TABLE_CACHE
    if _TRUTH_TABLE_CACHE is not None:
        return _TRUTH_TABLE_CACHE
    if not TRUTH_TABLE_PATH.exists():
        _TRUTH_TABLE_CACHE = {}
        return _TRUTH_TABLE_CACHE
    table: Dict[str, Dict[str, Any]] = {}
    with TRUTH_TABLE_PATH.open("r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            key = row.get("metric_key")
            if not key:
                continue
            nullable_raw = row.get("nullable_expected")
            nullable = None
            if isinstance(nullable_raw, str):
                if nullable_raw.lower() == "true":
                    nullable = True
                elif nullable_raw.lower() == "false":
                    nullable = False
            table[key] = {
                "nullable_expected": nullable,
                "zero_valid": row.get("zero_valid"),
                "origin_function": row.get("origin_function"),
                "trigger": row.get("trigger"),
                "side": row.get("side"),
                "lifecycle_phase": row.get("lifecycle_phase"),
                "type_hint": row.get("type_hint"),
                "category": row.get("category"),
            }
    _TRUTH_TABLE_CACHE = table
    return table


def _flatten_payload(data: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(data, dict):
        for key, value in data.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                yield from _flatten_payload(value, next_prefix)
            else:
                yield next_prefix, value
    else:
        if prefix:
            yield prefix, data


def build_metric_inventory(suite: ComprehensiveSuiteMetrics) -> List[Dict[str, Any]]:
    truth_table = _load_truth_table()
    metric_status = getattr(suite.validation, "metric_status", {}) or {}
    consistency_map = _load_consistency_matrix()
    canonical_keys = _get_canonical_keys()

    inventory: List[Dict[str, Any]] = []

    def _make_item(key: str, value: Any, *, source: str, is_legacy: bool = False) -> None:
        meta = truth_table.get(key, {})
        status_entry = metric_status.get(key)
        status = None
        reason = None

        if isinstance(status_entry, dict):
            status = status_entry.get("status")
            reason = status_entry.get("reason")

        nullable_expected = meta.get("nullable_expected")
        zero_valid = meta.get("zero_valid")

        if status is None:
            if is_legacy:
                status = "legacy"
                reason = "not_in_schema"
            else:
                if value is None:
                    if nullable_expected is True:
                        status = "not_collected"
                    elif nullable_expected is False:
                        status = "invalid"
                        reason = "null_when_non_nullable"
                    else:
                        status = "unknown"
                else:
                    if isinstance(value, str) and value.strip() == "" and nullable_expected is True:
                        status = "not_collected"
                        reason = "empty_string_when_nullable"
                    elif zero_valid == "no (null when missing)" and isinstance(value, (int, float)) and value == 0:
                        status = "invalid"
                        reason = "zero_when_null_expected"
                    else:
                        status = "collected"

        inventory.append({
            "key": key,
            "value": value,
            "source": source,
            "status": status,
            "reason": reason,
            "nullable_expected": nullable_expected,
            "zero_valid": zero_valid,
            "origin_function": meta.get("origin_function"),
            "trigger": meta.get("trigger"),
            "side": meta.get("side"),
            "lifecycle_phase": meta.get("lifecycle_phase"),
            "is_legacy": is_legacy,
            "value_type": type(value).__name__ if value is not None else "null",
            "classification": consistency_map.get(key),
        })

    raw_drone = suite.raw_drone or {}
    raw_gcs = suite.raw_gcs or {}

    drone_keys: set[str] = set()
    for key, value in _flatten_payload(raw_drone):
        drone_keys.add(key)
        _make_item(key, value, source="DRONE", is_legacy=key not in truth_table)

    for key, value in _flatten_payload(raw_gcs):
        _make_item(key, value, source="GCS_VALIDATION", is_legacy=key not in truth_table)

    gcs_validation = suite.gcs_validation or {}
    jsonl_payload = gcs_validation.get("jsonl") if isinstance(gcs_validation, dict) else None
    if isinstance(jsonl_payload, dict):
        for section_key, section_value in jsonl_payload.items():
            if not isinstance(section_value, dict):
                continue
            for key, value in _flatten_payload(section_value, prefix=section_key):
                if key not in canonical_keys:
                    continue
                _make_item(key, value, source="GCS_VALIDATION", is_legacy=key not in truth_table)

    for key in truth_table.keys():
        if key not in drone_keys:
            source = _infer_source_from_meta(truth_table.get(key, {}))
            _make_item(key, None, source=source, is_legacy=False)

    inventory.sort(key=lambda item: (item.get("source", ""), item.get("key", "")))
    return inventory


def _infer_source_from_meta(meta: Dict[str, Any]) -> str:
    side = (meta.get("side") or "").upper()
    if "GCS" in side and "DRONE" not in side:
        return "GCS_VALIDATION"
    if "DRONE" in side:
        return "DRONE"
    return "UNKNOWN"


def suites_to_dataframe(suites: List[ComprehensiveSuiteMetrics]) -> pd.DataFrame:
    """Convert a list of suites to a Pandas DataFrame."""
    rows = [suite_to_flat_dict(s) for s in suites]
    return pd.DataFrame(rows)


# =============================================================================
# COMPARISON
# =============================================================================

def compare_suites(
    suite_a: ComprehensiveSuiteMetrics,
    suite_b: ComprehensiveSuiteMetrics
) -> ComparisonResult:
    """
    Compare two suites side-by-side.
    
    Returns a ComparisonResult with both suites and computed differences.
    """
    val_a_handshake = get_metric_value_for_summary(suite_a, "handshake.handshake_total_duration_ms")
    val_b_handshake = get_metric_value_for_summary(suite_b, "handshake.handshake_total_duration_ms")
    diff_handshake = val_b_handshake - val_a_handshake if isinstance(val_a_handshake, (int, float)) and isinstance(val_b_handshake, (int, float)) else None

    val_a_power = get_metric_value_for_summary(suite_a, "power_energy.power_avg_w")
    val_b_power = get_metric_value_for_summary(suite_b, "power_energy.power_avg_w")
    diff_power = val_b_power - val_a_power if isinstance(val_a_power, (int, float)) and isinstance(val_b_power, (int, float)) else None

    val_a_energy = get_metric_value_for_summary(suite_a, "power_energy.energy_total_j")
    val_b_energy = get_metric_value_for_summary(suite_b, "power_energy.energy_total_j")
    diff_energy = val_b_energy - val_a_energy if isinstance(val_a_energy, (int, float)) and isinstance(val_b_energy, (int, float)) else None
    
    return ComparisonResult(
        suite_a=suite_a,
        suite_b=suite_b,
        diff_handshake_ms=diff_handshake,
        diff_power_w=diff_power,
        diff_energy_j=diff_energy
    )


def compute_comparison_table(
    suite_a: ComprehensiveSuiteMetrics,
    suite_b: ComprehensiveSuiteMetrics
) -> List[Dict[str, Any]]:
    """
    Create a detailed comparison table of all metrics.
    
    Returns a list of rows with metric, value_a, value_b, diff, unit, reliability.
    """
    inventory_a = get_inventory_status_map(suite_a)
    inventory_b = get_inventory_status_map(suite_b)

    all_keys = set(inventory_a.keys()) | set(inventory_b.keys())

    rows = []
    for key in sorted(all_keys):
        item_a = inventory_a.get(key)
        item_b = inventory_b.get(key)
        val_a = item_a.get("value") if item_a and item_a.get("status") == "collected" else None
        val_b = item_b.get("value") if item_b and item_b.get("status") == "collected" else None

        diff = None
        if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
            diff = val_b - val_a

        field_name = key.split(".")[-1] if "." in key else key
        rows.append({
            "metric": key,
            "value_a": val_a,
            "value_b": val_b,
            "diff": diff,
            "unit": get_field_unit(field_name),
            "reliability": get_field_reliability(key).value,
            "status_a": item_a.get("status") if item_a else "unknown",
            "status_b": item_b.get("status") if item_b else "unknown",
            "reason_a": item_a.get("reason") if item_a else None,
            "reason_b": item_b.get("reason") if item_b else None,
        })

    return rows
        # TRUTH TABLE
        # =============================================================================



# =============================================================================
# DRONE VS GCS SPLIT
# =============================================================================

def extract_drone_metrics(suite: ComprehensiveSuiteMetrics) -> Dict[str, Any]:
    """Extract drone-side metrics from a suite."""
    return {
        "mavproxy": suite.mavproxy_drone.model_dump(),
        "system": suite.system_drone.model_dump(),
        "power_energy": suite.power_energy.model_dump(),
        "fc_telemetry": suite.fc_telemetry.model_dump(),
    }


def extract_gcs_metrics(suite: ComprehensiveSuiteMetrics) -> Dict[str, Any]:
    """
    Extract GCS-side metrics from a suite.
    
    Note: Only validation-only MAVProxy metrics are available.
    """
    return {
        "mavproxy": suite.mavproxy_gcs.model_dump(),
        "system": suite.system_gcs.model_dump(),
    }


def get_drone_vs_gcs_summary(suite: ComprehensiveSuiteMetrics) -> Dict[str, Any]:
    """Get comparative summary of drone vs GCS for a suite."""
    drone_msgs = suite.mavproxy_drone.mavproxy_drone_total_msgs_received
    gcs_validation = suite.gcs_validation.get("jsonl", {}) if isinstance(suite.gcs_validation, dict) else {}
    mavlink_validation = gcs_validation.get("mavlink_validation") if isinstance(gcs_validation, dict) else None
    if isinstance(mavlink_validation, dict):
        gcs_msgs = mavlink_validation.get("total_msgs_received")
        gcs_seq_gaps = mavlink_validation.get("seq_gap_count")
    else:
        gcs_msgs = suite.mavproxy_gcs.mavproxy_gcs_total_msgs_received
        gcs_seq_gaps = suite.mavproxy_gcs.mavproxy_gcs_seq_gap_count
    
    return {
        "drone": {
            "msgs_received": drone_msgs,
            "seq_gaps": suite.mavproxy_drone.mavproxy_drone_seq_gap_count,
            "heartbeat_loss": suite.mavproxy_drone.mavproxy_drone_heartbeat_loss_count,
            "cpu_avg": suite.system_drone.cpu_usage_avg_percent,
            "memory_mb": suite.system_drone.memory_rss_mb,
            "power_w": suite.power_energy.power_avg_w,
        },
        "gcs": {
            "msgs_received": gcs_msgs,
        # SCHEMA DEFINITION
        # =============================================================================

            "msgs_received_reliability": ReliabilityClass.CONDITIONAL.value,
            "seq_gaps": gcs_seq_gaps,
            "seq_gaps_reliability": ReliabilityClass.CONDITIONAL.value,
        },
        "cross_side": {
            "msg_delivery_ratio": gcs_msgs / drone_msgs if isinstance(drone_msgs, (int, float)) and drone_msgs > 0 and isinstance(gcs_msgs, (int, float)) else None,
        # METRIC INVENTORY
        # =============================================================================

        }
    }


# =============================================================================
# AGGREGATION (EXPLICIT ONLY)
# =============================================================================

def aggregate_by_kem_family(
    suites: List[ComprehensiveSuiteMetrics]
) -> pd.DataFrame:
    """
    Aggregate metrics by KEM family.
    
    This is an EXPLICIT aggregation - only called when user requests it.
    """
    suites = filter_valid_suites(suites)
    df = suites_to_dataframe(suites)
    df = apply_truth_table_nulls(df)
    
    if df.empty:
        return pd.DataFrame()
    
    if "latency_jitter.one_way_latency_valid" in df.columns:
        df.loc[df["latency_jitter.one_way_latency_valid"] != True, "latency_jitter.one_way_latency_avg_ms"] = None
        df.loc[df["latency_jitter.one_way_latency_valid"] != True, "latency_jitter.one_way_latency_p95_ms"] = None
    if "latency_jitter.rtt_valid" in df.columns:
        df.loc[df["latency_jitter.rtt_valid"] != True, "latency_jitter.rtt_avg_ms"] = None
        df.loc[df["latency_jitter.rtt_valid"] != True, "latency_jitter.rtt_p95_ms"] = None

    # Group by KEM family
    agg_cols = {
        "handshake.handshake_total_duration_ms": ["mean", "std", "min", "max"],
        "data_plane.goodput_mbps": ["mean", "min", "max"],
        "data_plane.packet_loss_ratio": ["mean", "min", "max"],
        "latency_jitter.one_way_latency_avg_ms": ["mean", "min", "max"],
        "latency_jitter.one_way_latency_p95_ms": ["mean", "min", "max"],
        "latency_jitter.rtt_avg_ms": ["mean", "min", "max"],
        "latency_jitter.rtt_p95_ms": ["mean", "min", "max"],
        "power_energy.power_avg_w": ["mean", "std"],
        "power_energy.energy_total_j": ["mean", "sum"],
    }
    
    available_cols = {c: agg for c, agg in agg_cols.items() if c in df.columns}
    
    if not available_cols:
        return pd.DataFrame()
    
    grouped = df.groupby("crypto_identity.kem_family").agg(available_cols)
    return grouped.where(pd.notnull(grouped), None)


def aggregate_by_nist_level(
    suites: List[ComprehensiveSuiteMetrics]
) -> pd.DataFrame:
    """
    Aggregate metrics by NIST security level.
    
    This is an EXPLICIT aggregation - only called when user requests it.
    """
    suites = filter_valid_suites(suites)
    df = suites_to_dataframe(suites)
    df = apply_truth_table_nulls(df)
    
    if df.empty:
        return pd.DataFrame()
    
    if "latency_jitter.one_way_latency_valid" in df.columns:
        df.loc[df["latency_jitter.one_way_latency_valid"] != True, "latency_jitter.one_way_latency_avg_ms"] = None
        df.loc[df["latency_jitter.one_way_latency_valid"] != True, "latency_jitter.one_way_latency_p95_ms"] = None
    if "latency_jitter.rtt_valid" in df.columns:
        df.loc[df["latency_jitter.rtt_valid"] != True, "latency_jitter.rtt_avg_ms"] = None
        df.loc[df["latency_jitter.rtt_valid"] != True, "latency_jitter.rtt_p95_ms"] = None

    agg_cols = {
        "handshake.handshake_total_duration_ms": ["mean", "std", "count"],
        "data_plane.goodput_mbps": ["mean", "min", "max"],
        "data_plane.packet_loss_ratio": ["mean", "min", "max"],
        "latency_jitter.one_way_latency_avg_ms": ["mean", "min", "max"],
        "latency_jitter.one_way_latency_p95_ms": ["mean", "min", "max"],
        "latency_jitter.rtt_avg_ms": ["mean", "min", "max"],
        "latency_jitter.rtt_p95_ms": ["mean", "min", "max"],
        "power_energy.power_avg_w": ["mean", "std"],
        "power_energy.energy_total_j": ["mean"],
    }
    
    available_cols = {c: agg for c, agg in agg_cols.items() if c in df.columns}
    
    if not available_cols:
        return pd.DataFrame()
    
    grouped = df.groupby("crypto_identity.suite_security_level").agg(available_cols)
    return grouped.where(pd.notnull(grouped), None)


# =============================================================================
# SCHEMA DEFINITION
# =============================================================================

def generate_schema_definition() -> List[SchemaField]:
    """Generate schema field definitions from the truth table."""
    truth_table = _load_truth_table()
    schema: List[SchemaField] = []

    for key in sorted(truth_table.keys()):
        category = truth_table.get(key, {}).get("category") or (key.split(".", 1)[0] if "." in key else "root")
        field_name = key.split(".")[-1] if "." in key else key
        schema.append(
            SchemaField(
                name=key,
                category=category,
                type=str(truth_table.get(key, {}).get("type_hint", "unknown")),
                unit=get_field_unit(field_name),
                reliability=get_field_reliability(key),
                description="",
            )
        )

    return schema


def _load_schema_vs_observed() -> Dict[str, Any]:
    global _SCHEMA_VS_OBSERVED_CACHE
    if _SCHEMA_VS_OBSERVED_CACHE is not None:
        return _SCHEMA_VS_OBSERVED_CACHE
    if not SCHEMA_VS_OBSERVED_PATH.exists():
        _SCHEMA_VS_OBSERVED_CACHE = {}
        return _SCHEMA_VS_OBSERVED_CACHE
    try:
        _SCHEMA_VS_OBSERVED_CACHE = json.loads(SCHEMA_VS_OBSERVED_PATH.read_text(encoding="utf-8"))
    except Exception:
        _SCHEMA_VS_OBSERVED_CACHE = {}
    return _SCHEMA_VS_OBSERVED_CACHE


def _get_canonical_keys() -> set[str]:
    truth_table = _load_truth_table()
    observed = _load_schema_vs_observed()
    extra_keys = set(observed.get("extra_keys", []) or []) if isinstance(observed, dict) else set()
    return set(truth_table.keys()) | extra_keys


def _load_observed_summary() -> Dict[str, Any]:
    global _OBSERVED_SUMMARY_CACHE
    if _OBSERVED_SUMMARY_CACHE is not None:
        return _OBSERVED_SUMMARY_CACHE
    if not OBSERVED_SUMMARY_PATH.exists():
        _OBSERVED_SUMMARY_CACHE = {}
        return _OBSERVED_SUMMARY_CACHE
    try:
        _OBSERVED_SUMMARY_CACHE = json.loads(OBSERVED_SUMMARY_PATH.read_text(encoding="utf-8"))
    except Exception:
        _OBSERVED_SUMMARY_CACHE = {}
    return _OBSERVED_SUMMARY_CACHE


def _load_consistency_matrix() -> Dict[str, str]:
    global _CONSISTENCY_MATRIX_CACHE
    if _CONSISTENCY_MATRIX_CACHE is not None:
        return _CONSISTENCY_MATRIX_CACHE
    if not CONSISTENCY_MATRIX_PATH.exists():
        _CONSISTENCY_MATRIX_CACHE = {}
        return _CONSISTENCY_MATRIX_CACHE
    try:
        matrix: Dict[str, str] = {}
        with CONSISTENCY_MATRIX_PATH.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                key = row.get("metric_key")
                classification = row.get("classification")
                if key and classification:
                    matrix[key] = classification
        _CONSISTENCY_MATRIX_CACHE = matrix
    except Exception:
        _CONSISTENCY_MATRIX_CACHE = {}
    return _CONSISTENCY_MATRIX_CACHE


def generate_metric_semantics() -> List[Dict[str, Any]]:
    """
    Generate metric semantics from the Pydantic model schema + truth table
    (if available) + observed data from loaded suites.

    This works even when the static analysis CSV/JSON artefacts don't exist
    by introspecting ComprehensiveSuiteMetrics model fields.
    """
    truth_table = _load_truth_table()
    observed = _load_schema_vs_observed()
    observed_summary = (
        _load_observed_summary().get("summary", {})
        if isinstance(_load_observed_summary(), dict)
        else {}
    )

    # ── Derive keys from the Pydantic model schema ──────────────────────
    _CATEGORY_TO_SIDE = {
        "run_context":       "BOTH",
        "crypto_identity":   "DRONE",
        "lifecycle":         "DRONE",
        "handshake":         "DRONE",
        "crypto_primitives": "DRONE",
        "rekey":             "DRONE",
        "data_plane":        "DRONE",
        "latency_jitter":    "DRONE",
        "mavproxy_drone":    "DRONE",
        "mavproxy_gcs":      "GCS",
        "mavlink_integrity":  "DRONE",
        "fc_telemetry":      "DRONE",
        "control_plane":     "DRONE",
        "system_drone":      "DRONE",
        "system_gcs":        "GCS",
        "power_energy":      "DRONE",
        "observability":     "DRONE",
        "validation":        "DRONE",
    }

    _CATEGORY_TO_PHASE = {
        "run_context":       "setup",
        "crypto_identity":   "setup",
        "lifecycle":         "lifecycle",
        "handshake":         "handshake",
        "crypto_primitives": "handshake",
        "rekey":             "rekey",
        "data_plane":        "data_plane",
        "latency_jitter":    "data_plane",
        "mavproxy_drone":    "data_plane",
        "mavproxy_gcs":      "data_plane",
        "mavlink_integrity":  "data_plane",
        "fc_telemetry":      "data_plane",
        "control_plane":     "control",
        "system_drone":      "data_plane",
        "system_gcs":        "data_plane",
        "power_energy":      "data_plane",
        "observability":     "data_plane",
        "validation":        "validation",
    }

    NULLABLE_FIELDS: set[str] = {
        "one_way_latency_avg_ms", "one_way_latency_p95_ms",
        "jitter_avg_ms", "jitter_p95_ms", "rtt_avg_ms", "rtt_p95_ms",
        "handshake_failure_reason", "latency_invalid_reason", "rtt_invalid_reason",
        "rekey_trigger_reason",
    }
    ZERO_VALID_NO: set[str] = set()   # nothing currently flagged

    # Build model-derived keys (category.field)
    model_keys: Dict[str, Dict[str, Any]] = {}
    for category, field_info in ComprehensiveSuiteMetrics.model_fields.items():
        ann = field_info.annotation
        # Only introspect sub-model categories
        if ann is None or not hasattr(ann, "model_fields"):
            # unwrap Optional[SubModel] if needed
            origin = getattr(ann, "__origin__", None)
            args = getattr(ann, "__args__", ())
            if origin is not None and args:
                inner = [a for a in args if a is not type(None)]
                ann = inner[0] if inner and hasattr(inner[0], "model_fields") else None
            else:
                ann = None
        if ann is None or not hasattr(ann, "model_fields"):
            continue
        for field_name, fld in ann.model_fields.items():
            key = f"{category}.{field_name}"
            ftype = fld.annotation
            type_hint = getattr(ftype, "__name__", str(ftype) if ftype else "unknown")
            # strip Optional wrapper
            ftype_origin = getattr(ftype, "__origin__", None)
            ftype_args = getattr(ftype, "__args__", ())
            if ftype_origin is not None and ftype_args:
                inner = [a for a in ftype_args if a is not type(None)]
                if inner:
                    type_hint = getattr(inner[0], "__name__", str(inner[0]))
            nullable = field_name in NULLABLE_FIELDS or fld.default is None
            model_keys[key] = {
                "category": category,
                "type_hint": type_hint,
                "nullable": nullable,
            }

    # Merge truth-table keys, model keys, and observed keys
    schema_keys = set(observed.get("schema_keys", []) or [])
    extra_keys = set(observed.get("extra_keys", []) or [])
    all_keys = schema_keys | extra_keys | set(truth_table.keys()) | set(model_keys.keys())

    semantics: List[Dict[str, Any]] = []
    for key in sorted(all_keys):
        meta = truth_table.get(key, {})
        model_meta = model_keys.get(key, {})

        category = (
            meta.get("category")
            or model_meta.get("category")
            or (key.split(".", 1)[0] if "." in key else "root")
        )
        nullable_expected = meta.get("nullable_expected")
        if nullable_expected is None and model_meta:
            nullable_expected = model_meta.get("nullable")
        zero_valid = meta.get("zero_valid")

        origin_side = meta.get("side") or _CATEGORY_TO_SIDE.get(category, "UNKNOWN")
        lifecycle_phase = meta.get("lifecycle_phase") or _CATEGORY_TO_PHASE.get(category)
        is_legacy = key in extra_keys and key not in model_keys

        authoritative_side = "DRONE"
        if "gcs" in category.lower():
            authoritative_side = "GCS_VALIDATION"

        observed_types = None
        if isinstance(observed_summary, dict):
            summary_entry = observed_summary.get(key)
            if isinstance(summary_entry, dict):
                observed_types = summary_entry.get("types")
        # Fallback: use type_hint from model introspection
        if observed_types is None and model_meta.get("type_hint"):
            observed_types = model_meta["type_hint"]

        semantics.append({
            "key": key,
            "category": category,
            "origin_side": origin_side,
            "authoritative_side": authoritative_side,
            "lifecycle_phase": lifecycle_phase,
            "nullable_expected": nullable_expected,
            "zero_valid": zero_valid,
            "invalid_reasons": [],
            "legacy": is_legacy,
            "origin_function": meta.get("origin_function"),
            "trigger": meta.get("trigger"),
            "side": meta.get("side"),
            "type_hint": meta.get("type_hint") or model_meta.get("type_hint"),
            "observed_types": observed_types,
        })

    return semantics


def get_inventory_status_map(suite: ComprehensiveSuiteMetrics) -> Dict[str, Dict[str, Any]]:
    inventory = build_metric_inventory(suite)
    return {
        item["key"]: item
        for item in inventory
        if item.get("source") == "DRONE"
    }


def get_metric_value_for_summary(suite: ComprehensiveSuiteMetrics, key: str) -> Any:
    status_map = get_inventory_status_map(suite)
    item = status_map.get(key)
    if not item:
        return None
    status = item.get("status")
    if status != "collected":
        return None
    return item.get("value")


def apply_truth_table_nulls(df: pd.DataFrame) -> pd.DataFrame:
    truth_table = _load_truth_table()
    for key, meta in truth_table.items():
        if key not in df.columns:
            continue
        if meta.get("zero_valid") == "no (null when missing)":
            df.loc[df[key] == 0, key] = None
    return df
