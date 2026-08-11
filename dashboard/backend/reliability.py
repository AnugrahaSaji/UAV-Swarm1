"""
Metric Reliability Classifications
Based on Forensic Audit 2026-01-24

This module defines the ground-truth reliability status for all metrics
in the Secure-Tunnel benchmark system. Classifications are based on
actual code analysis, not schema intentions.

Usage:
    from reliability import get_reliability, ReliabilityClass, NOT_COLLECTED_FIELDS
    
    reliability = get_reliability("handshake_total_duration_ms")  # -> REAL
    reliability = get_reliability("handshake_total_duration_ms")  # -> REAL
"""

from enum import Enum
from typing import Set


class ReliabilityClass(str, Enum):
    """Metric reliability classification based on forensic audit."""
    REAL = "REAL"                   # Collected from runtime events
    DERIVED = "DERIVED"             # Computed post-hoc from real data
    CONDITIONAL = "CONDITIONAL"     # Depends on caller injection
    NOT_COLLECTED = "NOT_COLLECTED" # Schema only - never populated


# =============================================================================
# NOT_COLLECTED FIELDS
# These fields exist in schema but are NEVER populated with real data.
# Dashboard MUST hide these or show "N/A".
# =============================================================================

NOT_COLLECTED_FIELDS: Set[str] = {
    # Empty: all non-collected fields removed from schema
}


# =============================================================================
# DERIVED FIELDS
# These fields are computed post-hoc from real data.
# Dashboard SHOULD label these as "DERIVED" for transparency.
# =============================================================================

DERIVED_FIELDS: Set[str] = {
    # Category B
    "kem_family",
    "sig_family",
    
    # Category C
    "suite_total_duration_ms",
    "suite_active_duration_ms",
    
    # Category E
    "total_crypto_time_ms",
    
    # Category G
    "achieved_throughput_mbps",
    "goodput_mbps",
    "wire_rate_mbps",
    "packets_dropped",
    "packet_loss_ratio",
    "packet_delivery_ratio",
    "decode_failure_count",
    
    # Category I
    "mavproxy_drone_tx_pps",
    "mavproxy_drone_rx_pps",
    "mavproxy_drone_heartbeat_interval_ms",
    "mavproxy_drone_cmd_ack_latency_avg_ms",
    "mavproxy_drone_cmd_ack_latency_p95_ms",
    "mavproxy_drone_stream_rate_hz",
    
    # Category L
    "fc_heartbeat_age_ms",
    "fc_attitude_update_rate_hz",
    "fc_position_update_rate_hz",
    
    # Category N
    "cpu_usage_avg_percent",
    "cpu_usage_peak_percent",
    
    # Category P
    "power_avg_w",
    "power_peak_w",
    "energy_total_j",
    "energy_per_handshake_j",
    "voltage_avg_v",
    "current_avg_a",
    
    # Category Q
    "collection_duration_ms",
    
    # Category R
    "expected_samples",
    "lost_samples",
    "success_rate_percent",
    "benchmark_pass_fail",
}


# =============================================================================
# CONDITIONAL FIELDS
# These require explicit caller injection to be populated.
# May legitimately be 0/empty if benchmark doesn't use them.
# =============================================================================

CONDITIONAL_FIELDS: Set[str] = {
    "mavlink_message_latency_avg_ms",
    "clock_offset_ms",
}


def get_reliability(field_name: str) -> ReliabilityClass:
    """
    Get reliability classification for a metric field.
    
    Args:
        field_name: The metric field name to classify
        
    Returns:
        ReliabilityClass enum value
    """
    if field_name in NOT_COLLECTED_FIELDS:
        return ReliabilityClass.NOT_COLLECTED
    if field_name in DERIVED_FIELDS:
        return ReliabilityClass.DERIVED
    if field_name in CONDITIONAL_FIELDS:
        return ReliabilityClass.CONDITIONAL
    return ReliabilityClass.REAL


def should_display(field_name: str) -> bool:
    """
    Determine if a field should be displayed on the dashboard.
    
    NOT_COLLECTED fields should be hidden.
    
    Args:
        field_name: The metric field name
        
    Returns:
        True if field should be displayed, False otherwise
    """
    return field_name not in NOT_COLLECTED_FIELDS


def get_badge_class(field_name: str) -> str:
    """
    Get CSS badge class for dashboard display.
    
    Args:
        field_name: The metric field name
        
    Returns:
        CSS class name for badge styling
    """
    reliability = get_reliability(field_name)
    return {
        ReliabilityClass.REAL: "badge-success",
        ReliabilityClass.DERIVED: "badge-info",
        ReliabilityClass.CONDITIONAL: "badge-warning",
        ReliabilityClass.NOT_COLLECTED: "badge-danger",
    }.get(reliability, "badge-secondary")


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "ReliabilityClass",
    "NOT_COLLECTED_FIELDS",
    "DERIVED_FIELDS",
    "CONDITIONAL_FIELDS",
    "get_reliability",
    "should_display",
    "get_badge_class",
]
