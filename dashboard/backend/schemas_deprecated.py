from typing import List, Dict, Optional
from pydantic import BaseModel, Field

# =============================================================================
# FORENSIC DASHBOARD SCHEMA
# Mirrors metrics_schema.py (Canonical) with strict enforcement
# =============================================================================

class CanonicalMetrics(BaseModel):
    """
    The definitive 163-field schema for Secure-Tunnel Benchmarks.
    Source Authority: dashboard_architecture.md v2.0
    """

    # --- A. RUN & CONTEXT (20) ---
    run_id: str = Field(..., description="UUID of the run")
    suite_id: str = Field(..., description="Canonical suite ID string")
    suite_index: int = Field(..., description="0-based index of suite in run")
    git_commit_hash: str
    git_dirty_flag: bool
    gcs_hostname: str
    drone_hostname: str
    gcs_ip: str
    drone_ip: str
    python_env_gcs: str
    python_env_drone: str
    liboqs_version: str
    kernel_version_gcs: str
    kernel_version_drone: str
    clock_offset_ms: Optional[float] = 0.0  # PRUNED
    clock_offset_method: Optional[str] = None # PRUNED
    run_start_time_wall: str
    run_end_time_wall: str
    run_start_time_mono: float
    run_end_time_mono: float

    # --- B. CRYPTO IDENTITY (13) ---
    kem_algorithm: str
    kem_family: str
    kem_nist_level: str # L1-5
    sig_algorithm: str
    sig_family: str
    sig_nist_level: str # L1-5
    aead_algorithm: str
    suite_security_level: str # L1-5

    # --- C. LIFECYCLE (11) ---
    suite_selected_time: float
    suite_activated_time: float
    suite_deactivated_time: float
    suite_total_duration_ms: float
    suite_active_duration_ms: float

    # --- D. HANDSHAKE (8) ---
    handshake_start_time_drone: Optional[float] = None
    handshake_end_time_drone: Optional[float] = None
    handshake_total_duration_ms: Optional[float] = None
    handshake_success: Optional[bool] = None
    handshake_failure_reason: Optional[str] = None

    # --- E. CRYPTO PRIMITIVES (8) ---
    # Marked CONDITIONAL in Arch - Use Optional
    kem_keygen_time_ms: Optional[float] = 0.0
    kem_encapsulation_time_ms: Optional[float] = 0.0
    kem_decapsulation_time_ms: Optional[float] = 0.0
    signature_sign_time_ms: Optional[float] = 0.0
    signature_verify_time_ms: Optional[float] = 0.0
    total_crypto_time_ms: Optional[float] = None

    # --- F. REKEY METRICS (7) ---
    # All PRUNED/FORBIDDEN - Optional/0
    rekey_attempts: Optional[int] = 0
    rekey_success: Optional[bool] = False
    rekey_failure: Optional[bool] = False
    rekey_interval_ms: Optional[float] = 0.0
    rekey_duration_ms: Optional[float] = 0.0
    rekey_blackout_duration_ms: Optional[float] = 0.0
    rekey_trigger_reason: Optional[str] = ""

    # --- G. DATA PLANE (11) ---
    achieved_throughput_mbps: Optional[float] = 0.0 # PRUNED
    goodput_mbps: Optional[float] = 0.0 # PRUNED
    wire_rate_mbps: Optional[float] = 0.0 # PRUNED
    packets_sent: Optional[int] = None
    packets_received: Optional[int] = None
    packets_dropped: Optional[int] = None
    packet_loss_ratio: Optional[float] = None
    packet_delivery_ratio: Optional[float] = None
    replay_drop_count: Optional[int] = 0 # CONDITIONAL
    decode_failure_count: Optional[int] = 0 # PRUNED

    # --- H. LATENCY & JITTER (10) ---
    # --- H. LATENCY & JITTER (REAL, MAVLink-derived) ---
    one_way_latency_avg_ms: Optional[float] = None
    one_way_latency_p95_ms: Optional[float] = None
    jitter_avg_ms: Optional[float] = None
    jitter_p95_ms: Optional[float] = None
    latency_sample_count: Optional[int] = None
    latency_invalid_reason: Optional[str] = None

    rtt_avg_ms: Optional[float] = None
    rtt_p95_ms: Optional[float] = None
    rtt_sample_count: Optional[int] = None
    rtt_invalid_reason: Optional[str] = None

    # --- I. MAVPROXY DRONE (17) ---
    mavproxy_drone_start_time: float
    mavproxy_drone_end_time: float
    mavproxy_drone_tx_pps: float
    mavproxy_drone_rx_pps: float
    mavproxy_drone_total_msgs_sent: int
    mavproxy_drone_total_msgs_received: int
    mavproxy_drone_msg_type_counts: Dict[str, int]
    mavproxy_drone_heartbeat_interval_ms: float
    mavproxy_drone_heartbeat_loss_count: int
    mavproxy_drone_seq_gap_count: int
    mavproxy_drone_cmd_sent_count: int
    mavproxy_drone_cmd_ack_received_count: int
    mavproxy_drone_cmd_ack_latency_avg_ms: Optional[float] = None
    mavproxy_drone_cmd_ack_latency_p95_ms: Optional[float] = None
    mavproxy_drone_stream_rate_hz: Optional[float] = None

    # --- J. MAVPROXY GCS (13) ---
    # Mirrored structure
    mavproxy_gcs_total_msgs_received: Optional[int] = None
    mavproxy_gcs_seq_gap_count: Optional[int] = None

    # --- K. MAVLINK INTEGRITY (10) ---
    mavlink_sysid: Optional[int] = None
    mavlink_compid: Optional[int] = None
    mavlink_protocol_version: Optional[str] = None
    mavlink_packet_crc_error_count: Optional[int] = None
    mavlink_decode_error_count: Optional[int] = None
    mavlink_msg_drop_count: Optional[int] = None
    mavlink_out_of_order_count: Optional[int] = None
    mavlink_duplicate_count: Optional[int] = None
    mavlink_message_latency_avg_ms: Optional[float] = None

    # --- L. FC TELEMETRY (10) ---
    # ALL PRUNED
    fc_mode: Optional[str] = ""
    fc_armed_state: Optional[bool] = False
    fc_heartbeat_age_ms: Optional[float] = 0.0
    fc_attitude_update_rate_hz: Optional[float] = 0.0
    fc_position_update_rate_hz: Optional[float] = 0.0
    fc_battery_voltage_v: Optional[float] = 0.0
    fc_battery_current_a: Optional[float] = 0.0
    fc_battery_remaining_percent: Optional[float] = 0.0
    fc_cpu_load_percent: Optional[float] = 0.0
    fc_sensor_health_flags: Optional[int] = 0

    # --- M. CONTROL PLANE (7) ---
    scheduler_tick_interval_ms: Optional[float] = None
    scheduler_action_type: Optional[str] = None
    scheduler_action_reason: Optional[str] = None
    policy_name: Optional[str] = None
    policy_state: Optional[str] = None
    policy_suite_index: Optional[int] = None
    policy_total_suites: Optional[int] = None

    # --- N. SYSTEM RESOURCES (8) ---
    cpu_usage_avg_percent: Optional[float] = None
    cpu_usage_peak_percent: Optional[float] = None
    cpu_freq_mhz: Optional[float] = None
    memory_rss_mb: Optional[float] = None
    memory_vms_mb: Optional[float] = None
    thread_count: Optional[int] = None
    temperature_c: Optional[float] = None
    uptime_s: Optional[float] = None

    # --- O. SYSTEM RESOURCES GCS (NEW) ---
    gcs_cpu_usage_avg_percent: Optional[float] = None
    gcs_cpu_usage_peak_percent: Optional[float] = None
    gcs_cpu_freq_mhz: Optional[float] = None
    gcs_memory_rss_mb: Optional[float] = None
    gcs_memory_vms_mb: Optional[float] = None
    gcs_thread_count: Optional[int] = None
    gcs_temperature_c: Optional[float] = None
    gcs_uptime_s: Optional[float] = None
    gcs_load_avg_1m: Optional[float] = None
    gcs_load_avg_5m: Optional[float] = None
    gcs_load_avg_15m: Optional[float] = None

    # --- P. POWER & ENERGY (10) ---
    power_sensor_type: Optional[str] = None
    power_sampling_rate_hz: Optional[float] = None
    voltage_avg_v: Optional[float] = None
    current_avg_a: Optional[float] = None
    power_avg_w: Optional[float] = None
    power_peak_w: Optional[float] = None
    energy_total_j: Optional[float] = None
    energy_per_handshake_j: Optional[float] = None

    # --- Q-R. OBSERVABILITY & VALIDATION (10) ---
    log_sample_count: Optional[int] = None
    metrics_sampling_rate_hz: Optional[float] = None
    expected_samples: Optional[int] = None
    collected_samples: Optional[int] = None
    lost_samples: Optional[int] = None
    success_rate_percent: Optional[float] = None
    benchmark_pass_fail: Optional[str] = None

    metric_status: Optional[Dict[str, Dict[str, str]]] = None

    # --- Derived / Augmented Fields (Not in Schema but needed for Dashboard) ---
    # These will be computed during ingestion
    suite_relative_start_s: Optional[float] = 0.0
    
class RunSummary(BaseModel):
    run_id: str
    timestamp: str
    suites_total: int
    suites_completed: int
    success_rate: float
    duration_s: float

class SuiteDetail(CanonicalMetrics):
    pass
