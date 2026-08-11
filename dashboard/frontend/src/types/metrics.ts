/**
 * TypeScript types matching backend Pydantic models.
 * 
 * Mirrors the canonical schema from core/metrics_schema.py
 */

// =============================================================================
// ENUMS
// =============================================================================

export type ReliabilityClass = 'VERIFIED' | 'CONDITIONAL' | 'DEPRECATED' | 'MISSING';
export type MetricStatus = { status: 'not_collected' | 'invalid' | 'not_implemented'; reason?: string };

// =============================================================================
// A. RUN & CONTEXT METRICS
// =============================================================================

export interface RunContextMetrics {
    run_id: string;
    suite_id: string;
    suite_index: number;
    git_commit_hash: string | null;
    git_dirty_flag: boolean | null;
    gcs_hostname: string | null;
    drone_hostname: string | null;
    gcs_ip: string | null;
    drone_ip: string | null;
    python_env_gcs: string | null;
    python_env_drone: string | null;
    liboqs_version: string | null;
    kernel_version_gcs: string | null;
    kernel_version_drone: string | null;
    clock_offset_ms: number | null;
    clock_offset_method: string | null;
    run_start_time_wall: string;
    run_end_time_wall: string;
    run_start_time_mono: number;
    run_end_time_mono: number;
}

// =============================================================================
// B. SUITE CRYPTO IDENTITY
// =============================================================================

export interface SuiteCryptoIdentity {
    kem_algorithm: string | null;
    kem_family: string | null;
    kem_nist_level: string | null;
    sig_algorithm: string | null;
    sig_family: string | null;
    sig_nist_level: string | null;
    aead_algorithm: string | null;
    suite_security_level: string | null;
}

// =============================================================================
// C. SUITE LIFECYCLE TIMELINE
// =============================================================================

export interface SuiteLifecycleTimeline {
    suite_selected_time: number;
    suite_activated_time: number;
    suite_deactivated_time: number;
    suite_total_duration_ms: number;
    suite_active_duration_ms: number;
}

// =============================================================================
// D. HANDSHAKE METRICS
// =============================================================================

export interface HandshakeMetrics {
    handshake_start_time_drone: number | null;
    handshake_end_time_drone: number | null;
    handshake_total_duration_ms: number | null;
    protocol_handshake_duration_ms: number | null;
    end_to_end_handshake_duration_ms: number | null;
    handshake_success: boolean | null;
    handshake_failure_reason: string | null;
}

// =============================================================================
// E. CRYPTO PRIMITIVE BREAKDOWN
// =============================================================================

export interface CryptoPrimitiveBreakdown {
    kem_keygen_time_ms: number | null;
    kem_encapsulation_time_ms: number | null;
    kem_decapsulation_time_ms: number | null;
    signature_sign_time_ms: number | null;
    signature_verify_time_ms: number | null;
    total_crypto_time_ms: number | null;
    kem_keygen_ns: number | null;
    kem_encaps_ns: number | null;
    kem_decaps_ns: number | null;
    sig_sign_ns: number | null;
    sig_verify_ns: number | null;
    pub_key_size_bytes: number | null;
    ciphertext_size_bytes: number | null;
    sig_size_bytes: number | null;
    shared_secret_size_bytes: number | null;
}

// =============================================================================
// F. REKEY METRICS
// =============================================================================

export interface RekeyMetrics {
    rekey_attempts: number | null;
    rekey_success: number | null;
    rekey_failure: number | null;
    rekey_interval_ms: number | null;
    rekey_duration_ms: number | null;
    rekey_blackout_duration_ms: number | null;
    rekey_trigger_reason: string | null;
}

// =============================================================================
// G. DATA PLANE
// =============================================================================

export interface DataPlaneMetrics {
    achieved_throughput_mbps: number | null;
    goodput_mbps: number | null;
    wire_rate_mbps: number | null;
    packets_sent: number | null;
    packets_received: number | null;
    packets_dropped: number | null;
    packet_loss_ratio: number | null;
    packet_delivery_ratio: number | null;
    replay_drop_count: number | null;
    decode_failure_count: number | null;
    ptx_in: number | null;
    ptx_out: number | null;
    enc_in: number | null;
    enc_out: number | null;
    drop_replay: number | null;
    drop_auth: number | null;
    drop_header: number | null;
    bytes_sent: number | null;
    bytes_received: number | null;
    aead_encrypt_avg_ns: number | null;
    aead_decrypt_avg_ns: number | null;
    aead_encrypt_count: number | null;
    aead_decrypt_count: number | null;
}

// =============================================================================
// H. LATENCY & JITTER
// =============================================================================

export interface LatencyJitterMetrics {
    one_way_latency_avg_ms: number | null;
    one_way_latency_p95_ms: number | null;
    jitter_avg_ms: number | null;
    jitter_p95_ms: number | null;
    latency_sample_count: number | null;
    latency_invalid_reason: string | null;
    one_way_latency_valid: boolean | null;
    rtt_avg_ms: number | null;
    rtt_p95_ms: number | null;
    rtt_sample_count: number | null;
    rtt_invalid_reason: string | null;
    rtt_valid: boolean | null;
}

// =============================================================================
// I. MAVPROXY DRONE
// =============================================================================

export interface MavProxyDroneMetrics {
    mavproxy_drone_start_time: number | null;
    mavproxy_drone_end_time: number | null;
    mavproxy_drone_tx_pps: number | null;
    mavproxy_drone_rx_pps: number | null;
    mavproxy_drone_total_msgs_sent: number | null;
    mavproxy_drone_total_msgs_received: number | null;
    mavproxy_drone_msg_type_counts: Record<string, number> | null;
    mavproxy_drone_heartbeat_interval_ms: number | null;
    mavproxy_drone_heartbeat_loss_count: number | null;
    mavproxy_drone_seq_gap_count: number | null;
    mavproxy_drone_cmd_sent_count: number | null;
    mavproxy_drone_cmd_ack_received_count: number | null;
    mavproxy_drone_cmd_ack_latency_avg_ms: number | null;
    mavproxy_drone_cmd_ack_latency_p95_ms: number | null;
    mavproxy_drone_stream_rate_hz: number | null;
}

// =============================================================================
// J. MAVPROXY GCS (PRUNED)
// =============================================================================

export interface MavProxyGcsMetrics {
    mavproxy_gcs_total_msgs_received: number | null;
    mavproxy_gcs_seq_gap_count: number | null;
}

// =============================================================================
// K. MAVLINK INTEGRITY
// =============================================================================

export interface MavLinkIntegrityMetrics {
    mavlink_sysid: number | null;
    mavlink_compid: number | null;
    mavlink_protocol_version: string | null;
    mavlink_packet_crc_error_count: number | null;
    mavlink_decode_error_count: number | null;
    mavlink_msg_drop_count: number | null;
    mavlink_out_of_order_count: number | null;
    mavlink_duplicate_count: number | null;
    mavlink_message_latency_avg_ms: number | null;
}

// =============================================================================
// L. FLIGHT CONTROLLER TELEMETRY
// =============================================================================

export interface FlightControllerTelemetry {
    fc_mode: string | null;
    fc_armed_state: boolean | null;
    fc_heartbeat_age_ms: number | null;
    fc_attitude_update_rate_hz: number | null;
    fc_position_update_rate_hz: number | null;
    fc_battery_voltage_v: number | null;
    fc_battery_current_a: number | null;
    fc_battery_remaining_percent: number | null;
    fc_cpu_load_percent: number | null;
    fc_sensor_health_flags: number | null;
}

// =============================================================================
// M. CONTROL PLANE
// =============================================================================

export interface ControlPlaneMetrics {
    scheduler_tick_interval_ms: number | null;
    scheduler_action_type: string | null;
    scheduler_action_reason: string | null;
    policy_name: string | null;
    policy_state: string | null;
    policy_suite_index: number | null;
    policy_total_suites: number | null;
}

// =============================================================================
// N. SYSTEM RESOURCES DRONE
// =============================================================================

export interface SystemResourcesDrone {
    cpu_usage_avg_percent: number | null;
    cpu_usage_peak_percent: number | null;
    cpu_freq_mhz: number | null;
    memory_rss_mb: number | null;
    memory_vms_mb: number | null;
    thread_count: number | null;
    temperature_c: number | null;
    uptime_s: number | null;
    load_avg_1m: number | null;
    load_avg_5m: number | null;
    load_avg_15m: number | null;
}

// =============================================================================
// O. SYSTEM RESOURCES GCS (DEPRECATED)
// =============================================================================

export interface SystemResourcesGcs {
    cpu_usage_avg_percent: number | null;
    cpu_usage_peak_percent: number | null;
    cpu_freq_mhz: number | null;
    memory_rss_mb: number | null;
    memory_vms_mb: number | null;
    thread_count: number | null;
    temperature_c: number | null;
    uptime_s: number | null;
    load_avg_1m: number | null;
    load_avg_5m: number | null;
    load_avg_15m: number | null;
}

// =============================================================================
// P. POWER & ENERGY
// =============================================================================

export interface PowerEnergyMetrics {
    power_sensor_type: string | null;
    power_sampling_rate_hz: number | null;
    voltage_avg_v: number | null;
    current_avg_a: number | null;
    power_avg_w: number | null;
    power_peak_w: number | null;
    energy_total_j: number | null;
    energy_per_handshake_j: number | null;
}

// =============================================================================
// Q. OBSERVABILITY
// =============================================================================

export interface ObservabilityMetrics {
    log_sample_count: number | null;
    metrics_sampling_rate_hz: number | null;
    collection_start_time: number | null;
    collection_end_time: number | null;
    collection_duration_ms: number | null;
}

// =============================================================================
// R. VALIDATION
// =============================================================================

export interface ValidationMetrics {
    expected_samples: number | null;
    collected_samples: number | null;
    lost_samples: number | null;
    success_rate_percent: number | null;
    benchmark_pass_fail: string | null;
    metric_status?: Record<string, MetricStatus>;
}

// =============================================================================
// COMPREHENSIVE SUITE METRICS
// =============================================================================

export interface ComprehensiveSuiteMetrics {
    run_context: RunContextMetrics;
    crypto_identity: SuiteCryptoIdentity;
    lifecycle: SuiteLifecycleTimeline;
    handshake: HandshakeMetrics;
    crypto_primitives: CryptoPrimitiveBreakdown;
    rekey: RekeyMetrics;
    data_plane: DataPlaneMetrics;
    latency_jitter: LatencyJitterMetrics;
    mavproxy_drone: MavProxyDroneMetrics;
    mavproxy_gcs: MavProxyGcsMetrics;
    mavlink_integrity: MavLinkIntegrityMetrics;
    fc_telemetry: FlightControllerTelemetry;
    control_plane: ControlPlaneMetrics;
    system_drone: SystemResourcesDrone;
    system_gcs: SystemResourcesGcs;
    power_energy: PowerEnergyMetrics;
    observability: ObservabilityMetrics;
    validation: ValidationMetrics;
    ingest_status?: string | null;
    latency_source?: string | null;
    integrity_source?: string | null;
    packet_counters_source?: string | null;
    raw_drone?: Record<string, unknown> | null;
    raw_gcs?: Record<string, unknown> | null;
    gcs_validation?: Record<string, unknown> | null;
}

// =============================================================================
// API RESPONSE TYPES
// =============================================================================

export interface SuiteSummary {
    suite_id: string;
    run_id: string;
    suite_index: number;
    kem_algorithm: string | null;
    sig_algorithm: string | null;
    aead_algorithm: string | null;
    suite_security_level: string | null;
    handshake_success: boolean | null;
    handshake_total_duration_ms: number | null;
    power_sensor_type?: string | null;
    power_avg_w: number | null;
    energy_total_j: number | null;
    benchmark_pass_fail: string | null;
    ingest_status?: string | null;
}

export interface RunSummary {
    run_id: string;
    run_start_time_wall: string | null;
    gcs_hostname: string | null;
    drone_hostname: string | null;
    suite_count: number | null;
    git_commit_hash: string | null;
    run_type?: string | null;
    scenario_folder?: string | null;
}

export interface SchemaField {
    name: string;
    category: string;
    type: string;
    unit: string;
    reliability: ReliabilityClass;
    description: string;
}

export interface HealthResponse {
    status: string;
    suites_loaded: number;
    runs_loaded: number;
}

export interface FiltersResponse {
    kem_families: string[];
    sig_families: string[];
    aead_algorithms: string[];
    nist_levels: string[];
}

export interface MetricInventoryItem {
    key: string;
    value: unknown;
    source: string;
    status: string;
    reason?: string | null;
    nullable_expected?: boolean | null;
    zero_valid?: string | null;
    origin_function?: string | null;
    trigger?: string | null;
    side?: string | null;
    lifecycle_phase?: string | null;
    is_legacy?: boolean;
    value_type?: string | null;
    classification?: string | null;
}

export interface SuiteInventoryResponse {
    suite_key: string;
    metrics: MetricInventoryItem[];
    raw: {
        drone: Record<string, unknown>;
        gcs: Record<string, unknown>;
        gcs_validation?: Record<string, unknown>;
    };
}

// =============================================================================
// SETTINGS & MULTI-RUN TYPES
// =============================================================================

export type RunType = 'no_ddos' | 'ddos_xgboost' | 'ddos_txt';

export interface RunTypeInfo {
    label: string;
    color: string;
    order: number;
}

export interface RunLabel {
    label: string;
    type: RunType;
}

export interface AnomalyThresholds {
    handshake_ms_high: number;
    handshake_ms_critical: number;
    packet_loss_warning: number;
    packet_loss_critical: number;
    power_deviation_pct: number;
    energy_deviation_pct: number;
    [key: string]: number;
}

export interface ScenarioStatus {
    run_type: string;
    folder_exists: boolean;
    file_count: number;
    run_count: number;
    suite_count: number;
    run_ids: string[];
}

export interface DashboardSettings {
    run_labels: Record<string, RunLabel>;
    active_runs: string[];
    anomaly_thresholds: AnomalyThresholds;
    run_types: Record<RunType, RunTypeInfo>;
    available_runs: RunSummary[];
    scenario_status?: Record<string, ScenarioStatus>;
}

export interface MultiRunOverviewItem {
    run_id: string;
    label: string;
    run_type: RunType;
    total_suites: number;
    passed: number;
    failed: number;
    pass_rate: number;
    avg_handshake_ms: number | null;
    max_handshake_ms: number | null;
    avg_power_w: number | null;
    avg_energy_j: number | null;
    total_energy_j: number | null;
    avg_packet_loss: number | null;
    anomaly_count: number;
}

export interface MultiRunCompareResult {
    suite_id: string;
    runs: Array<{
        run_id: string;
        label: string;
        run_type: RunType;
        suite: ComprehensiveSuiteMetrics;
    }>;
}

export interface AnomalyFlag {
    metric: string;
    value: number | string;
    severity: 'warning' | 'critical';
    threshold: number | null;
}

export interface AnomalyItem {
    suite_id: string;
    run_id: string;
    key: string;
    kem: string | null;
    sig: string | null;
    flags: AnomalyFlag[];
    severity: 'warning' | 'critical';
}

export interface AnomalyResponse {
    anomalies: AnomalyItem[];
    total: number;
    thresholds: AnomalyThresholds;
}

// Run type colors for consistent UI theming
export const RUN_TYPE_COLORS: Record<RunType, string> = {
    no_ddos: '#3b82f6',
    ddos_xgboost: '#f59e0b',
    ddos_txt: '#ef4444',
};

export const RUN_TYPE_LABELS: Record<RunType, string> = {
    no_ddos: 'No DDoS (Baseline)',
    ddos_xgboost: 'DDoS – XGBoost',
    ddos_txt: 'DDoS – TXT',
};

// =============================================================================
// CROSS-RUN ANALYSIS TYPES
// =============================================================================

export interface CrossRunSuiteMetrics {
    handshake_ms: number | null;
    protocol_hs_ms: number | null;
    e2e_hs_ms: number | null;
    handshake_success: boolean | null;
    kem_keygen_ms: number | null;
    kem_encaps_ms: number | null;
    kem_decaps_ms: number | null;
    sig_sign_ms: number | null;
    sig_verify_ms: number | null;
    total_crypto_ms: number | null;
    cpu_avg_pct: number | null;
    cpu_peak_pct: number | null;
    memory_mb: number | null;
    temperature_c: number | null;
    load_avg_1m: number | null;
    power_avg_w: number | null;
    power_peak_w: number | null;
    energy_j: number | null;
    energy_per_hs_j: number | null;
    voltage_v: number | null;
    current_a: number | null;
    goodput_mbps: number | null;
    packet_loss: number | null;
    packets_sent: number | null;
    packets_dropped: number | null;
    drop_replay: number | null;
    drop_auth: number | null;
    rtt_avg_ms: number | null;
    rtt_p95_ms: number | null;
    jitter_avg_ms: number | null;
    owl_avg_ms: number | null;
    mavlink_crc_errors: number | null;
    mavlink_decode_errors: number | null;
    mavlink_ooo: number | null;
    mavlink_duplicates: number | null;
    benchmark_pass: string | null;
    fc_battery_v: number | null;
    fc_battery_pct: number | null;
}

export interface CrossRunSuiteEntry {
    suite_id: string;
    kem: string | null;
    sig: string | null;
    aead: string | null;
    nist: string | null;
    kem_family: string | null;
    sig_family: string | null;
    runs: Partial<Record<RunType, CrossRunSuiteMetrics>>;
}

export interface OverheadMetricDetail {
    baseline_avg: number | null;
    target_avg: number | null;
    delta_pct: number | null;
    delta_abs: number | null;
}

export interface CrossRunAnalysisResponse {
    suites: CrossRunSuiteEntry[];
    runs: Array<{ run_id: string; label: string; run_type: RunType }>;
    overhead: Partial<Record<RunType, Record<string, OverheadMetricDetail>>>;
}
