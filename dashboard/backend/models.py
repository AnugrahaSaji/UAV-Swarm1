"""
Pydantic models for PQC Benchmark Dashboard.
Mirrors the canonical schema from core/metrics_schema.py.

Each model corresponds to one of the 18 metric categories (A-R).
"""

from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class ReliabilityClass(str, Enum):
    """Metric reliability classification."""
    VERIFIED = "VERIFIED"
    CONDITIONAL = "CONDITIONAL"
    DEPRECATED = "DEPRECATED"
    MISSING = "MISSING"


# =============================================================================
# A. RUN & CONTEXT METRICS
# =============================================================================

class RunContextMetrics(BaseModel):
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

    class Config:
        extra = "allow"


# =============================================================================
# B. SUITE CRYPTO IDENTITY
# =============================================================================

class SuiteCryptoIdentity(BaseModel):
    """Cryptographic identity and parameters for the suite."""
    kem_algorithm: Optional[str] = None
    kem_family: Optional[str] = None
    kem_nist_level: Optional[str] = None
    sig_algorithm: Optional[str] = None
    sig_family: Optional[str] = None
    sig_nist_level: Optional[str] = None
    aead_algorithm: Optional[str] = None
    suite_security_level: Optional[str] = None

    class Config:
        extra = "allow"


# =============================================================================
# C. SUITE LIFECYCLE TIMELINE
# =============================================================================

class SuiteLifecycleTimeline(BaseModel):
    """Timeline of suite activation and operation."""
    suite_selected_time: float = 0.0
    suite_activated_time: float = 0.0
    suite_deactivated_time: float = 0.0
    suite_total_duration_ms: float = 0.0
    suite_active_duration_ms: float = 0.0

    class Config:
        extra = "allow"


# =============================================================================
# D. HANDSHAKE METRICS
# =============================================================================

class HandshakeMetrics(BaseModel):
    """Handshake timing and status."""
    handshake_start_time_drone: Optional[float] = None
    handshake_end_time_drone: Optional[float] = None
    handshake_total_duration_ms: Optional[float] = None
    protocol_handshake_duration_ms: Optional[float] = None
    end_to_end_handshake_duration_ms: Optional[float] = None
    handshake_success: Optional[bool] = None
    handshake_failure_reason: Optional[str] = None

    class Config:
        extra = "allow"


# =============================================================================
# E. CRYPTO PRIMITIVE BREAKDOWN
# =============================================================================

class CryptoPrimitiveBreakdown(BaseModel):
    """Detailed timing for each cryptographic primitive."""
    kem_keygen_time_ms: Optional[float] = None
    kem_encapsulation_time_ms: Optional[float] = None
    kem_decapsulation_time_ms: Optional[float] = None
    signature_sign_time_ms: Optional[float] = None
    signature_verify_time_ms: Optional[float] = None
    total_crypto_time_ms: Optional[float] = None
    kem_keygen_ns: Optional[int] = None
    kem_encaps_ns: Optional[int] = None
    kem_decaps_ns: Optional[int] = None
    sig_sign_ns: Optional[int] = None
    sig_verify_ns: Optional[int] = None
    pub_key_size_bytes: Optional[int] = None
    ciphertext_size_bytes: Optional[int] = None
    sig_size_bytes: Optional[int] = None
    shared_secret_size_bytes: Optional[int] = None

    class Config:
        extra = "allow"


# =============================================================================
# F. REKEY METRICS
# =============================================================================

class RekeyMetrics(BaseModel):
    """Rekey operation metrics."""
    rekey_attempts: Optional[int] = None
    rekey_success: Optional[int] = None
    rekey_failure: Optional[int] = None
    rekey_interval_ms: Optional[float] = None
    rekey_duration_ms: Optional[float] = None
    rekey_blackout_duration_ms: Optional[float] = None
    rekey_trigger_reason: Optional[str] = None

    class Config:
        extra = "allow"


# =============================================================================
# G. DATA PLANE (PROXY LEVEL)
# =============================================================================

class DataPlaneMetrics(BaseModel):
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
    ptx_in: Optional[int] = None
    ptx_out: Optional[int] = None
    enc_in: Optional[int] = None
    enc_out: Optional[int] = None
    drop_replay: Optional[int] = None
    drop_auth: Optional[int] = None
    drop_header: Optional[int] = None
    bytes_sent: Optional[int] = None
    bytes_received: Optional[int] = None
    aead_encrypt_avg_ns: Optional[float] = None
    aead_decrypt_avg_ns: Optional[float] = None
    aead_encrypt_count: Optional[int] = None
    aead_decrypt_count: Optional[int] = None

    class Config:
        extra = "allow"


# =============================================================================
# H. LATENCY & JITTER (TRANSPORT)
# =============================================================================

class LatencyJitterMetrics(BaseModel):
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

    class Config:
        extra = "allow"

# =============================================================================
# I. MAVPROXY APPLICATION LAYER — DRONE SIDE
# =============================================================================

class MavProxyDroneMetrics(BaseModel):
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

    class Config:
        extra = "allow"


# =============================================================================
# J. MAVPROXY APPLICATION LAYER — GCS SIDE (PRUNED)
# =============================================================================

class MavProxyGcsMetrics(BaseModel):
    """MAVProxy metrics from the GCS side (validation-only)."""
    mavproxy_gcs_total_msgs_received: Optional[int] = None
    mavproxy_gcs_seq_gap_count: Optional[int] = None

    class Config:
        extra = "allow"


# =============================================================================
# K. MAVLINK SEMANTIC INTEGRITY

class MavLinkIntegrityMetrics(BaseModel):
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

    class Config:
        extra = "allow"


# =============================================================================
# L. FLIGHT CONTROLLER TELEMETRY (DRONE)
# =============================================================================

class FlightControllerTelemetry(BaseModel):
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

    class Config:
        extra = "allow"


# =============================================================================
# M. CONTROL PLANE (SCHEDULER)
# =============================================================================

class ControlPlaneMetrics(BaseModel):
    """Scheduler and control plane metrics."""
    scheduler_tick_interval_ms: Optional[float] = None
    scheduler_action_type: Optional[str] = None
    scheduler_action_reason: Optional[str] = None
    policy_name: Optional[str] = None
    policy_state: Optional[str] = None
    policy_suite_index: Optional[int] = None
    policy_total_suites: Optional[int] = None

    class Config:
        extra = "allow"


# =============================================================================
# N. SYSTEM RESOURCES — DRONE
# =============================================================================

class SystemResourcesDrone(BaseModel):
    """System resource metrics from the drone."""
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

    class Config:
        extra = "allow"


# =============================================================================
# O. SYSTEM RESOURCES — GCS (DEPRECATED)
# =============================================================================

class SystemResourcesGcs(BaseModel):
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

    class Config:
        extra = "allow"

# =============================================================================
# P. POWER & ENERGY (DRONE)
# =============================================================================

class PowerEnergyMetrics(BaseModel):
    """Power and energy measurements from the drone."""
    power_sensor_type: Optional[str] = None
    power_sampling_rate_hz: Optional[float] = None
    voltage_avg_v: Optional[float] = None
    current_avg_a: Optional[float] = None
    power_avg_w: Optional[float] = None
    power_peak_w: Optional[float] = None
    energy_total_j: Optional[float] = None
    energy_per_handshake_j: Optional[float] = None

    class Config:
        extra = "allow"


# =============================================================================
# Q. OBSERVABILITY & LOGGING
# =============================================================================

class ObservabilityMetrics(BaseModel):
    """Logging and observability metrics."""
    log_sample_count: Optional[int] = None
    metrics_sampling_rate_hz: Optional[float] = None
    collection_start_time: Optional[float] = None
    collection_end_time: Optional[float] = None
    collection_duration_ms: Optional[float] = None

    class Config:
        extra = "allow"


# =============================================================================
# R. VALIDATION & INTEGRITY
# =============================================================================

class ValidationMetrics(BaseModel):
    """Validation and integrity check results."""
    expected_samples: Optional[int] = None
    collected_samples: Optional[int] = None
    lost_samples: Optional[int] = None
    success_rate_percent: Optional[float] = None
    benchmark_pass_fail: Optional[str] = None
    metric_status: Dict[str, Dict[str, str]] = Field(default_factory=dict)

    class Config:
        extra = "allow"


# =============================================================================
# COMPREHENSIVE SUITE METRICS (ALL CATEGORIES)
# =============================================================================

class ComprehensiveSuiteMetrics(BaseModel):
    """
    Complete metrics for a single suite benchmark iteration.
    Combines all 18 categories (A-R) into one unified structure.
    """
    model_config = {"extra": "allow"}
    run_context: RunContextMetrics = Field(default_factory=RunContextMetrics)
    crypto_identity: SuiteCryptoIdentity = Field(default_factory=SuiteCryptoIdentity)
    lifecycle: SuiteLifecycleTimeline = Field(default_factory=SuiteLifecycleTimeline)
    handshake: HandshakeMetrics = Field(default_factory=HandshakeMetrics)
    crypto_primitives: CryptoPrimitiveBreakdown = Field(default_factory=CryptoPrimitiveBreakdown)
    rekey: RekeyMetrics = Field(default_factory=RekeyMetrics)
    data_plane: DataPlaneMetrics = Field(default_factory=DataPlaneMetrics)
    latency_jitter: LatencyJitterMetrics = Field(default_factory=LatencyJitterMetrics)
    mavproxy_drone: MavProxyDroneMetrics = Field(default_factory=MavProxyDroneMetrics)
    mavproxy_gcs: MavProxyGcsMetrics = Field(default_factory=MavProxyGcsMetrics)
    mavlink_integrity: MavLinkIntegrityMetrics = Field(default_factory=MavLinkIntegrityMetrics)
    fc_telemetry: FlightControllerTelemetry = Field(default_factory=FlightControllerTelemetry)
    control_plane: ControlPlaneMetrics = Field(default_factory=ControlPlaneMetrics)
    system_drone: SystemResourcesDrone = Field(default_factory=SystemResourcesDrone)
    system_gcs: SystemResourcesGcs = Field(default_factory=SystemResourcesGcs)
    power_energy: PowerEnergyMetrics = Field(default_factory=PowerEnergyMetrics)
    observability: ObservabilityMetrics = Field(default_factory=ObservabilityMetrics)
    validation: ValidationMetrics = Field(default_factory=ValidationMetrics)
    ingest_status: Optional[str] = None
    latency_source: Optional[str] = None
    integrity_source: Optional[str] = None
    packet_counters_source: Optional[str] = None
    raw_drone: Optional[Dict[str, Any]] = None
    raw_gcs: Optional[Dict[str, Any]] = None
    gcs_validation: Dict[str, Any] = Field(default_factory=dict)


# =============================================================================
# API RESPONSE MODELS
# =============================================================================

class SuiteSummary(BaseModel):
    """Summary of a suite for listing."""
    suite_id: str
    run_id: str
    suite_index: int
    kem_algorithm: Optional[str] = None
    sig_algorithm: Optional[str] = None
    aead_algorithm: Optional[str] = None
    suite_security_level: Optional[str] = None
    handshake_success: Optional[bool] = None
    handshake_total_duration_ms: Optional[float] = None
    power_sensor_type: Optional[str] = None
    power_avg_w: Optional[float] = None
    energy_total_j: Optional[float] = None
    benchmark_pass_fail: Optional[str] = None
    ingest_status: Optional[str] = None


class RunSummary(BaseModel):
    """Summary of a benchmark run."""
    run_id: str
    run_start_time_wall: Optional[str] = None
    gcs_hostname: Optional[str] = None
    drone_hostname: Optional[str] = None
    suite_count: Optional[int] = None
    git_commit_hash: Optional[str] = None
    run_type: Optional[str] = None        # no_ddos | ddos_xgboost | ddos_txt
    scenario_folder: Optional[str] = None  # original folder name (no-ddos, ddos-xgboost, ddos-txt)


class ComparisonResult(BaseModel):
    """Result of comparing two suites."""
    suite_a: ComprehensiveSuiteMetrics
    suite_b: ComprehensiveSuiteMetrics
    diff_handshake_ms: Optional[float] = None
    diff_power_w: Optional[float] = None
    diff_energy_j: Optional[float] = None


class SchemaField(BaseModel):
    """Schema field definition."""
    name: str
    category: str
    type: str
    unit: str
    reliability: ReliabilityClass
    description: str


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    suites_loaded: int
    runs_loaded: int


class MetricInventoryItem(BaseModel):
    """Single metric inventory entry with provenance and validity metadata."""
    key: str
    value: Any
    source: str
    status: str
    reason: Optional[str] = None
    nullable_expected: Optional[bool] = None
    zero_valid: Optional[str] = None
    origin_function: Optional[str] = None
    trigger: Optional[str] = None
    side: Optional[str] = None
    lifecycle_phase: Optional[str] = None
    is_legacy: bool = False
    value_type: Optional[str] = None
    classification: Optional[str] = None


class SuiteInventoryResponse(BaseModel):
    """Full metric inventory for a suite, including raw payloads."""
    suite_key: str
    metrics: List[MetricInventoryItem]
    raw: Dict[str, Any]
