#!/usr/bin/env python3
"""
Comprehensive Metrics Schema for PQC Benchmark
core/metrics_schema.py

Defines all 18 metric categories (A-R) as structured dataclasses.
This schema ensures consistent, typed metrics collection across GCS and Drone.

Categories:
    A. Run & Context Metrics
    B. Suite Crypto Identity
    C. Suite Lifecycle Timeline
    D. Handshake Metrics
    E. Crypto Primitive Breakdown
    F. Rekey Metrics
    G. Data Plane (Proxy Level)
    H. Latency & Jitter (Transport)
    I. MAVProxy Application Layer — Drone Side
    J. MAVProxy Application Layer — GCS Side
    K. MAVLink Semantic Integrity
    L. Flight Controller Telemetry (Drone)
    M. Control Plane (Scheduler)
    N. System Resources — Drone
    O. System Resources — GCS
    P. Power & Energy (Drone)
    Q. Observability & Logging
    R. Validation & Integrity
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any
from datetime import datetime
import json
import time
import platform
import os
import subprocess


# =============================================================================
# A. RUN & CONTEXT METRICS
# =============================================================================

@dataclass
class RunContextMetrics:
    """Run-level context and environment information."""
    run_id: str = ""
    suite_id: str = ""
    suite_index: int = 0
    git_commit_hash: Optional[str] = None
    git_dirty_flag: Optional[bool] = None
    gcs_hostname: Optional[str] = None
    drone_hostname: Optional[str] = None
    gcs_ip: Optional[str] = None
    drone_ip: Optional[str] = None
    python_env_gcs: Optional[str] = None
    python_env_drone: Optional[str] = None
    liboqs_version: Optional[str] = None
    kernel_version_gcs: Optional[str] = None
    kernel_version_drone: Optional[str] = None
    clock_offset_ms: Optional[float] = None
    clock_offset_method: Optional[str] = None
    run_start_time_wall: str = ""
    run_end_time_wall: str = ""
    run_start_time_mono: float = 0.0
    run_end_time_mono: float = 0.0


# =============================================================================
# B. SUITE CRYPTO IDENTITY
# =============================================================================

@dataclass
class SuiteCryptoIdentity:
    """Cryptographic identity and parameters for the suite."""
    kem_algorithm: Optional[str] = None
    kem_family: Optional[str] = None
    kem_nist_level: Optional[str] = None
    sig_algorithm: Optional[str] = None
    sig_family: Optional[str] = None
    sig_nist_level: Optional[str] = None
    aead_algorithm: Optional[str] = None
    suite_security_level: Optional[str] = None


# =============================================================================
# C. SUITE LIFECYCLE TIMELINE
# =============================================================================

@dataclass
class SuiteLifecycleTimeline:
    """Timeline of suite activation and operation."""
    suite_selected_time: float = 0.0
    suite_activated_time: float = 0.0
    suite_deactivated_time: float = 0.0
    suite_total_duration_ms: float = 0.0
    suite_active_duration_ms: float = 0.0


# =============================================================================
# D. HANDSHAKE METRICS
# =============================================================================

@dataclass
class HandshakeMetrics:
    """Handshake timing and status."""
    handshake_start_time_drone: Optional[float] = None
    handshake_end_time_drone: Optional[float] = None
    handshake_total_duration_ms: Optional[float] = None
    protocol_handshake_duration_ms: Optional[float] = None
    end_to_end_handshake_duration_ms: Optional[float] = None
    handshake_success: Optional[bool] = None
    handshake_failure_reason: Optional[str] = None


# =============================================================================
# E. CRYPTO PRIMITIVE BREAKDOWN
# =============================================================================

@dataclass
class CryptoPrimitiveBreakdown:
    """Detailed timing for each cryptographic primitive."""
    kem_keygen_time_ms: Optional[float] = None
    kem_encapsulation_time_ms: Optional[float] = None
    kem_decapsulation_time_ms: Optional[float] = None
    signature_sign_time_ms: Optional[float] = None
    signature_verify_time_ms: Optional[float] = None
    total_crypto_time_ms: Optional[float] = None
    
    # Extended primitive timing (nanoseconds for precision)
    kem_keygen_ns: Optional[int] = None
    kem_encaps_ns: Optional[int] = None
    kem_decaps_ns: Optional[int] = None
    sig_sign_ns: Optional[int] = None
    sig_verify_ns: Optional[int] = None
    
    # Artifact sizes
    pub_key_size_bytes: Optional[int] = None
    ciphertext_size_bytes: Optional[int] = None
    sig_size_bytes: Optional[int] = None
    shared_secret_size_bytes: Optional[int] = None


# =============================================================================
# F. REKEY METRICS
# =============================================================================

@dataclass
class RekeyMetrics:
    """Rekey operation metrics."""
    rekey_attempts: Optional[int] = None
    rekey_success: Optional[int] = None
    rekey_failure: Optional[int] = None
    rekey_interval_ms: Optional[float] = None
    rekey_duration_ms: Optional[float] = None
    rekey_blackout_duration_ms: Optional[float] = None
    rekey_trigger_reason: Optional[str] = None


# =============================================================================
# G. DATA PLANE (PROXY LEVEL)
# =============================================================================

@dataclass
class DataPlaneMetrics:
    """Proxy-level data plane metrics."""
    achieved_throughput_mbps: Optional[float] = None
    goodput_mbps: Optional[float] = None
    wire_rate_mbps: Optional[float] = None
    packets_sent: Optional[int] = None
    packets_received: Optional[int] = None
    packets_dropped: Optional[int] = None
    packet_loss_ratio: Optional[float] = None
    packet_delivery_ratio: Optional[float] = None
    replay_drop_count: Optional[int] = None
    decode_failure_count: Optional[int] = None
    
    # Detailed packet counters
    ptx_in: Optional[int] = None  # Plaintext in
    ptx_out: Optional[int] = None  # Plaintext out
    enc_in: Optional[int] = None  # Encrypted in
    enc_out: Optional[int] = None  # Encrypted out
    drop_replay: Optional[int] = None
    drop_auth: Optional[int] = None
    drop_header: Optional[int] = None
    # FIX-AGG: Previously only the 3 crypto-layer drop counters were surfaced.
    # These 4 additional counters make ALL proxy-side drops visible in the
    # dashboard without changing the existing packet_loss_ratio formula.
    drop_session_epoch: Optional[int] = None
    drop_other: Optional[int] = None
    drop_src_addr: Optional[int] = None
    sniff_drop: Optional[int] = None
    
    # Byte counters
    bytes_sent: Optional[int] = None
    bytes_received: Optional[int] = None
    
    # AEAD timing
    aead_encrypt_avg_ns: Optional[float] = None
    aead_decrypt_avg_ns: Optional[float] = None
    aead_encrypt_count: Optional[int] = None
    aead_decrypt_count: Optional[int] = None


# =============================================================================
# H. LATENCY & JITTER (TRANSPORT)
# =============================================================================

@dataclass
class LatencyJitterMetrics:
    """Latency and jitter derived from MAVLink traffic."""
    one_way_latency_avg_ms: Optional[float] = None
    one_way_latency_p95_ms: Optional[float] = None
    jitter_avg_ms: Optional[float] = None
    jitter_p95_ms: Optional[float] = None
    latency_sample_count: Optional[int] = None
    latency_invalid_reason: Optional[str] = None
    one_way_latency_valid: Optional[bool] = None

    rtt_avg_ms: Optional[float] = None
    rtt_p95_ms: Optional[float] = None
    rtt_sample_count: Optional[int] = None
    rtt_invalid_reason: Optional[str] = None
    rtt_valid: Optional[bool] = None
    # FIX-S4b: Distinguish control-plane vs data-plane RTT for downstream
    # consumers (dashboard, reports). Default "control_tcp" since the current
    # RTT probe goes through TCP port 48080, not the encrypted UDP tunnel.
    rtt_source: Optional[str] = None


# =============================================================================
# I. MAVPROXY APPLICATION LAYER — DRONE SIDE
# =============================================================================

@dataclass
class MavProxyDroneMetrics:
    """MAVProxy metrics from the drone side."""
    mavproxy_drone_start_time: Optional[float] = None
    mavproxy_drone_end_time: Optional[float] = None
    mavproxy_drone_tx_pps: Optional[float] = None
    mavproxy_drone_rx_pps: Optional[float] = None
    mavproxy_drone_total_msgs_sent: Optional[int] = None
    mavproxy_drone_total_msgs_received: Optional[int] = None
    mavproxy_drone_msg_type_counts: Optional[Dict[str, int]] = None
    mavproxy_drone_heartbeat_interval_ms: Optional[float] = None
    mavproxy_drone_heartbeat_loss_count: Optional[int] = None
    mavproxy_drone_seq_gap_count: Optional[int] = None
    mavproxy_drone_cmd_sent_count: Optional[int] = None
    mavproxy_drone_cmd_ack_received_count: Optional[int] = None
    mavproxy_drone_cmd_ack_latency_avg_ms: Optional[float] = None
    mavproxy_drone_cmd_ack_latency_p95_ms: Optional[float] = None
    mavproxy_drone_stream_rate_hz: Optional[float] = None


# =============================================================================
# J. MAVPROXY APPLICATION LAYER — GCS SIDE (PRUNED)
# =============================================================================
# POLICY REALIGNMENT (2026-01-18):
# GCS MAVProxy metrics pruned to VALIDATION-ONLY subset.
#
# RETAINED (validation/integrity):
#   - mavproxy_gcs_total_msgs_received: Cross-side correlation
#   - mavproxy_gcs_seq_gap_count: MAVLink integrity
#
# REMOVED (non-essential):
#   - msg_type_counts histogram
#   - heartbeat_interval_ms statistics
#   - heartbeat_loss_count
#   - stream_rate_hz
#   - cmd_ack_* latency tracking
# =============================================================================

@dataclass
class MavProxyGcsMetrics:
    """
    MAVProxy metrics from the GCS side.
    
    POLICY REALIGNMENT: Pruned to validation-only metrics.
    GCS deep introspection removed as non-policy-relevant.
    """
    # VALIDATION metrics (retained)
    mavproxy_gcs_total_msgs_received: Optional[int] = None
    mavproxy_gcs_seq_gap_count: Optional[int] = None


# =============================================================================
# K. MAVLINK SEMANTIC INTEGRITY
# =============================================================================

@dataclass
class MavLinkIntegrityMetrics:
    """MAVLink protocol integrity metrics."""
    mavlink_sysid: Optional[int] = None
    mavlink_compid: Optional[int] = None
    mavlink_protocol_version: Optional[str] = None
    mavlink_packet_crc_error_count: Optional[int] = None
    mavlink_decode_error_count: Optional[int] = None
    mavlink_msg_drop_count: Optional[int] = None
    mavlink_out_of_order_count: Optional[int] = None
    mavlink_duplicate_count: Optional[int] = None
    mavlink_message_latency_avg_ms: Optional[float] = None


# =============================================================================
# L. FLIGHT CONTROLLER TELEMETRY (DRONE)
# =============================================================================

@dataclass
class FlightControllerTelemetry:
    """Flight controller telemetry from the drone."""
    fc_mode: Optional[str] = None
    fc_armed_state: Optional[bool] = None
    fc_heartbeat_age_ms: Optional[float] = None
    fc_attitude_update_rate_hz: Optional[float] = None
    fc_position_update_rate_hz: Optional[float] = None
    fc_battery_voltage_v: Optional[float] = None
    fc_battery_current_a: Optional[float] = None
    fc_battery_remaining_percent: Optional[float] = None
    fc_cpu_load_percent: Optional[float] = None
    fc_sensor_health_flags: Optional[int] = None


# =============================================================================
# M. CONTROL PLANE (SCHEDULER)
# =============================================================================

@dataclass
class ControlPlaneMetrics:
    """Scheduler and control plane metrics."""
    scheduler_tick_interval_ms: Optional[float] = None
    scheduler_action_type: Optional[str] = None
    scheduler_action_reason: Optional[str] = None
    policy_name: Optional[str] = None
    policy_state: Optional[str] = None
    policy_suite_index: Optional[int] = None
    policy_total_suites: Optional[int] = None


# =============================================================================
# N. SYSTEM RESOURCES — DRONE
# =============================================================================

@dataclass
class SystemResourcesDrone:
    """System resource metrics from the drone."""
    cpu_usage_avg_percent: Optional[float] = None
    cpu_usage_peak_percent: Optional[float] = None
    cpu_freq_mhz: Optional[float] = None
    memory_rss_mb: Optional[float] = None
    memory_vms_mb: Optional[float] = None
    thread_count: Optional[int] = None
    temperature_c: Optional[float] = None
    
    # Extended system info
    uptime_s: Optional[float] = None
    load_avg_1m: Optional[float] = None
    load_avg_5m: Optional[float] = None
    load_avg_15m: Optional[float] = None


# =============================================================================
# O. SYSTEM RESOURCES — GCS (DEPRECATED)
# =============================================================================
# POLICY REALIGNMENT (2026-01-18):
# GCS system resource metrics are NO LONGER COLLECTED.
# 
# Justification:
#   - GCS is a non-constrained observer system
#   - GCS CPU/memory does NOT influence policy decisions
#   - GCS resources do NOT affect suite ranking or crypto selection
#   - Collecting these adds overhead without policy value
#
# This dataclass is RETAINED for schema compatibility but fields
# will remain at default values. Do NOT reintroduce collection
# without explicit policy justification.
# =============================================================================


@dataclass
class SystemResourcesGcs:
    """System resource metrics from the GCS."""
    cpu_usage_avg_percent: Optional[float] = None
    cpu_usage_peak_percent: Optional[float] = None
    cpu_freq_mhz: Optional[float] = None
    memory_rss_mb: Optional[float] = None
    memory_vms_mb: Optional[float] = None
    thread_count: Optional[int] = None
    temperature_c: Optional[float] = None
    uptime_s: Optional[float] = None
    load_avg_1m: Optional[float] = None
    load_avg_5m: Optional[float] = None
    load_avg_15m: Optional[float] = None

# =============================================================================
# P. POWER & ENERGY (DRONE)
# =============================================================================

@dataclass
class PowerEnergyMetrics:
    """Power and energy measurements from the drone."""
    power_sensor_type: Optional[str] = None  # "ina219", "rpi5_pmic", "rpi5_hwmon", "none"
    power_sampling_rate_hz: Optional[float] = None
    voltage_avg_v: Optional[float] = None
    current_avg_a: Optional[float] = None
    power_avg_w: Optional[float] = None
    power_peak_w: Optional[float] = None
    energy_total_j: Optional[float] = None
    energy_per_handshake_j: Optional[float] = None
    # Power segmentation (PART 2): handshake vs steady-state isolation
    handshake_energy_mj: Optional[float] = None
    handshake_peak_power_mw: Optional[float] = None
    steady_energy_mj: Optional[float] = None
    steady_avg_power_mw: Optional[float] = None


# =============================================================================
# Q. OBSERVABILITY & LOGGING
# =============================================================================

@dataclass
class ObservabilityMetrics:
    """Logging and observability metrics."""
    log_sample_count: Optional[int] = None
    metrics_sampling_rate_hz: Optional[float] = None
    
    # Collection timestamps
    collection_start_time: Optional[float] = None
    collection_end_time: Optional[float] = None
    collection_duration_ms: Optional[float] = None


# =============================================================================
# R. VALIDATION & INTEGRITY
# =============================================================================

@dataclass
class ValidationMetrics:
    """Validation and integrity check results."""
    expected_samples: Optional[int] = None
    collected_samples: Optional[int] = None
    lost_samples: Optional[int] = None
    success_rate_percent: Optional[float] = None
    benchmark_pass_fail: Optional[str] = None
    metric_status: Dict[str, Dict[str, str]] = field(default_factory=dict)


# =============================================================================
# COMPREHENSIVE SUITE METRICS (ALL CATEGORIES)
# =============================================================================

@dataclass
class ComprehensiveSuiteMetrics:
    """
    Complete metrics for a single suite benchmark iteration.
    Combines all 18 categories (A-R) into one unified structure.
    """
    # A. Run & Context
    run_context: RunContextMetrics = field(default_factory=RunContextMetrics)
    
    # B. Suite Crypto Identity
    crypto_identity: SuiteCryptoIdentity = field(default_factory=SuiteCryptoIdentity)
    
    # C. Suite Lifecycle Timeline
    lifecycle: SuiteLifecycleTimeline = field(default_factory=SuiteLifecycleTimeline)
    
    # D. Handshake Metrics
    handshake: HandshakeMetrics = field(default_factory=HandshakeMetrics)
    
    # E. Crypto Primitive Breakdown
    crypto_primitives: CryptoPrimitiveBreakdown = field(default_factory=CryptoPrimitiveBreakdown)
    
    # F. Rekey Metrics
    rekey: RekeyMetrics = field(default_factory=RekeyMetrics)
    
    # G. Data Plane (Proxy Level)
    data_plane: DataPlaneMetrics = field(default_factory=DataPlaneMetrics)

    # H. Latency & Jitter
    latency_jitter: LatencyJitterMetrics = field(default_factory=LatencyJitterMetrics)
    
    # I. MAVProxy Drone
    mavproxy_drone: MavProxyDroneMetrics = field(default_factory=MavProxyDroneMetrics)
    
    # J. MAVProxy GCS
    mavproxy_gcs: MavProxyGcsMetrics = field(default_factory=MavProxyGcsMetrics)
    
    # K. MAVLink Integrity
    mavlink_integrity: MavLinkIntegrityMetrics = field(default_factory=MavLinkIntegrityMetrics)
    
    # L. Flight Controller Telemetry
    fc_telemetry: FlightControllerTelemetry = field(default_factory=FlightControllerTelemetry)
    
    # M. Control Plane
    control_plane: ControlPlaneMetrics = field(default_factory=ControlPlaneMetrics)
    
    # N. System Resources Drone
    system_drone: SystemResourcesDrone = field(default_factory=SystemResourcesDrone)

    # O. System Resources GCS
    system_gcs: SystemResourcesGcs = field(default_factory=SystemResourcesGcs)
    
    # P. Power & Energy
    power_energy: PowerEnergyMetrics = field(default_factory=PowerEnergyMetrics)
    
    # Q. Observability
    observability: ObservabilityMetrics = field(default_factory=ObservabilityMetrics)
    
    # R. Validation
    validation: ValidationMetrics = field(default_factory=ValidationMetrics)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)
    
    def save_json(self, filepath: str):
        """Save metrics to JSON file."""
        with open(filepath, 'w') as f:
            f.write(self.to_json())
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ComprehensiveSuiteMetrics':
        """Create from dictionary."""
        metrics = cls()
        
        if 'run_context' in data:
            metrics.run_context = RunContextMetrics(**data['run_context'])
        if 'crypto_identity' in data:
            metrics.crypto_identity = SuiteCryptoIdentity(**data['crypto_identity'])
        if 'lifecycle' in data:
            metrics.lifecycle = SuiteLifecycleTimeline(**data['lifecycle'])
        if 'handshake' in data:
            metrics.handshake = HandshakeMetrics(**data['handshake'])
        if 'crypto_primitives' in data:
            metrics.crypto_primitives = CryptoPrimitiveBreakdown(**data['crypto_primitives'])
        if 'rekey' in data:
            metrics.rekey = RekeyMetrics(**data['rekey'])
        if 'data_plane' in data:
            metrics.data_plane = DataPlaneMetrics(**data['data_plane'])
        if 'latency_jitter' in data:
            metrics.latency_jitter = LatencyJitterMetrics(**data['latency_jitter'])
        if 'mavproxy_drone' in data:
            metrics.mavproxy_drone = MavProxyDroneMetrics(**data['mavproxy_drone'])
        if 'mavproxy_gcs' in data:
            metrics.mavproxy_gcs = MavProxyGcsMetrics(**data['mavproxy_gcs'])
        if 'mavlink_integrity' in data:
            metrics.mavlink_integrity = MavLinkIntegrityMetrics(**data['mavlink_integrity'])
        if 'fc_telemetry' in data:
            metrics.fc_telemetry = FlightControllerTelemetry(**data['fc_telemetry'])
        if 'control_plane' in data:
            metrics.control_plane = ControlPlaneMetrics(**data['control_plane'])
        if 'system_drone' in data:
            metrics.system_drone = SystemResourcesDrone(**data['system_drone'])
        if 'system_gcs' in data:
            metrics.system_gcs = SystemResourcesGcs(**data['system_gcs'])
        if 'power_energy' in data:
            metrics.power_energy = PowerEnergyMetrics(**data['power_energy'])
        if 'observability' in data:
            metrics.observability = ObservabilityMetrics(**data['observability'])
        if 'validation' in data:
            metrics.validation = ValidationMetrics(**data['validation'])
        
        return metrics
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ComprehensiveSuiteMetrics':
        """Create from JSON string."""
        return cls.from_dict(json.loads(json_str))
    
    @classmethod
    def load_json(cls, filepath: str) -> 'ComprehensiveSuiteMetrics':
        """Load from JSON file."""
        with open(filepath, 'r') as f:
            return cls.from_json(f.read())


# =============================================================================
# HELPER: Get metric field count
# =============================================================================

def count_metrics() -> Dict[str, int]:
    """Count metrics in each category."""
    from dataclasses import fields
    
    categories = {
        'A. Run & Context': RunContextMetrics,
        'B. Suite Crypto Identity': SuiteCryptoIdentity,
        'C. Suite Lifecycle Timeline': SuiteLifecycleTimeline,
        'D. Handshake Metrics': HandshakeMetrics,
        'E. Crypto Primitive Breakdown': CryptoPrimitiveBreakdown,
        'F. Rekey Metrics': RekeyMetrics,
        'G. Data Plane': DataPlaneMetrics,
        'I. MAVProxy Drone': MavProxyDroneMetrics,
        'J. MAVProxy GCS': MavProxyGcsMetrics,
        'K. MAVLink Integrity': MavLinkIntegrityMetrics,
        'L. Flight Controller': FlightControllerTelemetry,
        'M. Control Plane': ControlPlaneMetrics,
        'N. System Drone': SystemResourcesDrone,
        'P. Power & Energy': PowerEnergyMetrics,
        'Q. Observability': ObservabilityMetrics,
        'R. Validation': ValidationMetrics,
    }
    
    counts = {}
    total = 0
    for name, cls in categories.items():
        count = len(fields(cls))
        counts[name] = count
        total += count
    
    counts['TOTAL'] = total
    return counts


if __name__ == "__main__":
    # Print metric counts
    print("=" * 60)
    print("COMPREHENSIVE METRICS SCHEMA")
    print("=" * 60)
    
    counts = count_metrics()
    for category, count in counts.items():
        print(f"  {category}: {count} fields")
    
    print()
    print("Creating sample metrics object...")
    
    # Create a sample metrics object
    metrics = ComprehensiveSuiteMetrics()
    metrics.run_context.run_id = "test_run_001"
    metrics.run_context.suite_id = "cs-mlkem512-falcon512"
    metrics.crypto_identity.kem_algorithm = "ML-KEM-512"
    metrics.handshake.handshake_total_duration_ms = 15.5
    
    # Print sample JSON
    print("\nSample JSON (truncated):")
    print(metrics.to_json()[:500] + "...")
