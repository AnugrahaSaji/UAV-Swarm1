# Frontend ↔ Backend Suite Field Audit (No Assumptions)
Date: 2026-02-06

Scope:
- UI fields rendered per suite (Suite Explorer + Suite Detail + Overview aggregates).
- Backend model paths and concrete collection points.
- Any wiring gaps that prevent visibility in the UI.

References:
- Suite Explorer summary: [dashboard/frontend/src/pages/SuiteExplorer.tsx](dashboard/frontend/src/pages/SuiteExplorer.tsx#L1-L190)
- Suite Detail cards: [dashboard/frontend/src/pages/SuiteDetail.tsx](dashboard/frontend/src/pages/SuiteDetail.tsx#L170-L610)
- Overview aggregates: [dashboard/frontend/src/pages/Overview.tsx](dashboard/frontend/src/pages/Overview.tsx#L1-L200)
- Backend models: [dashboard/backend/models.py](dashboard/backend/models.py#L380-L452)
- Metrics aggregation: [core/metrics_aggregator.py](core/metrics_aggregator.py#L170-L1060)
- GCS JSONL merge: [dashboard/backend/ingest.py](dashboard/backend/ingest.py#L396-L438)
- Inventory generation: [dashboard/backend/analysis.py](dashboard/backend/analysis.py#L200-L290)

---

## 1) Suite Explorer (Summary Table)
Rendered in: [dashboard/frontend/src/pages/SuiteExplorer.tsx](dashboard/frontend/src/pages/SuiteExplorer.tsx#L100-L190)
Backend type: `SuiteSummary` [dashboard/backend/models.py](dashboard/backend/models.py#L402-L452)
Population: [dashboard/backend/ingest.py](dashboard/backend/ingest.py#L60-L120)

| UI Column | Backend Field Path | Collection Source (Code) | Notes |
|---|---|---|---|
| Suite ID | `suite_id` | `MetricsAggregator.start_suite()` sets `run_context.suite_id` then ingested into summary | [core/metrics_aggregator.py](core/metrics_aggregator.py#L173-L252)
| Suite Index | `suite_index` | `MetricsAggregator.start_suite()` sets `run_context.suite_index` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L173-L252)
| KEM | `kem_algorithm` | `MetricsAggregator.start_suite()` (suite_config) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L225-L280)
| Signature | `sig_algorithm` | `MetricsAggregator.start_suite()` (suite_config) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L225-L280)
| AEAD | `aead_algorithm` | `MetricsAggregator.start_suite()` (suite_config) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L225-L280)
| Level | `suite_security_level` | `MetricsAggregator.start_suite()` (suite_config) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L225-L280)
| Handshake (ms) | `handshake_total_duration_ms` | `MetricsAggregator.record_handshake_end()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L314-L352)
| Power (W) | `power_avg_w` | `MetricsAggregator.finalize_suite()` (power collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L700-L740)
| Energy (J) | `energy_total_j` | `MetricsAggregator.finalize_suite()` (power collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L700-L740)
| Status | `benchmark_pass_fail` | `MetricsAggregator.finalize_suite()` (handshake status) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L986-L1010)

---

## 2) Suite Detail Cards (Per Suite)
Rendered in: [dashboard/frontend/src/pages/SuiteDetail.tsx](dashboard/frontend/src/pages/SuiteDetail.tsx#L170-L610)
Backend type: `ComprehensiveSuiteMetrics` [dashboard/backend/models.py](dashboard/backend/models.py#L380-L430)

### A. Run Context
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| Run ID | `run_context.run_id` | `MetricsAggregator.set_run_id()` then `start_suite()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L155-L210)
| Suite Index | `run_context.suite_index` | `MetricsAggregator.start_suite()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L173-L252)
| Git Commit | `run_context.git_commit_hash` | `EnvironmentCollector` (start_suite) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L173-L252)
| GCS Host | `run_context.gcs_hostname` | `EnvironmentCollector` (role=gcs) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L198-L214)
| Drone Host | `run_context.drone_hostname` | `EnvironmentCollector` (role=drone) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L206-L214)
| Start Time | `run_context.run_start_time_wall` | `start_suite()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L214-L240)

### B. Crypto Identity
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| KEM | `crypto_identity.kem_algorithm` | `start_suite()` (suite_config) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L225-L280)
| KEM Family | `crypto_identity.kem_family` | Derived in `start_suite()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L245-L280)
| Signature | `crypto_identity.sig_algorithm` | `start_suite()` (suite_config) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L225-L280)
| Sig Family | `crypto_identity.sig_family` | Derived in `start_suite()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L260-L290)
| AEAD | `crypto_identity.aead_algorithm` | `start_suite()` (suite_config) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L225-L280)
| Security Level | `crypto_identity.suite_security_level` | `start_suite()` (suite_config) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L225-L280)

### D. Handshake Metrics
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| Total Duration | `handshake.handshake_total_duration_ms` | `record_handshake_end()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L323-L352)
| Protocol Duration | `handshake.protocol_handshake_duration_ms` | `record_crypto_primitives()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L387-L423)
| End-to-end Duration | `handshake.end_to_end_handshake_duration_ms` | `record_handshake_end()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L336-L352)
| Success | `handshake.handshake_success` | `record_handshake_end()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L345-L352)
| Failure Reason | `handshake.handshake_failure_reason` | `record_handshake_end()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L345-L352)

### M. Control Plane
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| Scheduler Tick | `control_plane.scheduler_tick_interval_ms` | `record_control_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L519-L547)
| Policy Name | `control_plane.policy_name` | `record_control_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L519-L547)
| Policy State | `control_plane.policy_state` | `record_control_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L519-L547)
| Action Type | `control_plane.scheduler_action_type` | `record_control_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L519-L547)
| Action Reason | `control_plane.scheduler_action_reason` | `record_control_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L519-L547)

### G. Data Plane
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| Packets Sent | `data_plane.packets_sent` | `record_data_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L437-L500)
| Packets Received | `data_plane.packets_received` | `record_data_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L437-L500)
| Packets Dropped | `data_plane.packets_dropped` | `record_data_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L437-L500)
| Delivery Ratio | `data_plane.packet_delivery_ratio` | `record_data_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L470-L500)

### Link Quality
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| Goodput | `data_plane.goodput_mbps` | `finalize_suite()` throughput calc | [core/metrics_aggregator.py](core/metrics_aggregator.py#L620-L700)
| Achieved Throughput | `data_plane.achieved_throughput_mbps` | `finalize_suite()` throughput calc | [core/metrics_aggregator.py](core/metrics_aggregator.py#L620-L700)
| Packet Loss | `data_plane.packet_loss_ratio` | `record_data_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L470-L500)
| Delivery Ratio | `data_plane.packet_delivery_ratio` | `record_data_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L470-L500)

### H. Latency & Jitter
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| One-way Avg | `latency_jitter.one_way_latency_avg_ms` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L800-L850)
| One-way P95 | `latency_jitter.one_way_latency_p95_ms` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L800-L850)
| Jitter Avg | `latency_jitter.jitter_avg_ms` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L800-L850)
| Jitter P95 | `latency_jitter.jitter_p95_ms` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L800-L850)
| One-way Valid | `latency_jitter.one_way_latency_valid` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L820-L850)
| RTT Avg | `latency_jitter.rtt_avg_ms` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L820-L850)
| RTT P95 | `latency_jitter.rtt_p95_ms` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L820-L850)
| RTT Valid | `latency_jitter.rtt_valid` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L820-L850)
| Latency Invalid Reason | `latency_jitter.latency_invalid_reason` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L820-L850)
| RTT Invalid Reason | `latency_jitter.rtt_invalid_reason` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L820-L850)

### K. MAVLink Integrity
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| Out of Order | `mavlink_integrity.mavlink_out_of_order_count` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L790-L830)
| CRC Errors | `mavlink_integrity.mavlink_packet_crc_error_count` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L790-L830)
| Decode Errors | `mavlink_integrity.mavlink_decode_error_count` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L790-L830)
| Duplicates | `mavlink_integrity.mavlink_duplicate_count` | `finalize_suite()` (MAVLink collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L790-L830)

### N. System Resources (Drone)
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| CPU Avg | `system_drone.cpu_usage_avg_percent` | `finalize_suite()` (system samples) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L680-L720)
| CPU Peak | `system_drone.cpu_usage_peak_percent` | `finalize_suite()` (system samples) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L680-L720)
| Memory RSS | `system_drone.memory_rss_mb` | `finalize_suite()` (system samples) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L700-L720)
| Temperature | `system_drone.temperature_c` | `finalize_suite()` (system samples) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L700-L720)

### O. System Resources (GCS)
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| CPU Avg | `system_gcs.cpu_usage_avg_percent` | **Not mapped from JSONL** | GCS JSONL captured in `gcs_validation.jsonl.system_gcs` only.
| CPU Peak | `system_gcs.cpu_usage_peak_percent` | **Not mapped from JSONL** | [dashboard/backend/ingest.py](dashboard/backend/ingest.py#L396-L438)
| Memory RSS | `system_gcs.memory_rss_mb` | **Not mapped from JSONL** | [dashboard/backend/ingest.py](dashboard/backend/ingest.py#L396-L438)
| Temperature | `system_gcs.temperature_c` | **Not mapped from JSONL** | [dashboard/backend/ingest.py](dashboard/backend/ingest.py#L396-L438)

### P. Power & Energy
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| Sensor Type | `power_energy.power_sensor_type` | `finalize_suite()` (power collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L700-L740)
| Power Avg | `power_energy.power_avg_w` | `finalize_suite()` (power collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L700-L740)
| Power Peak | `power_energy.power_peak_w` | `finalize_suite()` (power collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L700-L740)
| Energy Total | `power_energy.energy_total_j` | `finalize_suite()` (power collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L700-L740)
| Voltage Avg | `power_energy.voltage_avg_v` | `finalize_suite()` (power collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L700-L740)
| Current Avg | `power_energy.current_avg_a` | `finalize_suite()` (power collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L700-L740)
| Energy/Handshake | `power_energy.energy_per_handshake_j` | `finalize_suite()` (power collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L715-L740)
| Sampling Rate | `power_energy.power_sampling_rate_hz` | `finalize_suite()` (power collector) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L700-L740)

### F. Rekey Metrics
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| Rekey Attempts | `rekey.rekey_attempts` | `record_data_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L470-L520)
| Rekey Duration | `rekey.rekey_duration_ms` | `record_data_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L470-L520)
| Rekey Blackout | `rekey.rekey_blackout_duration_ms` | `record_data_plane_metrics()` | [core/metrics_aggregator.py](core/metrics_aggregator.py#L470-L520)

### R. Validation
| UI Field | Backend Field Path | Collection Source (Code) |
|---|---|---|
| Collected Samples | `validation.collected_samples` | `finalize_suite()` (system samples) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L960-L1010)
| Lost Samples | `validation.lost_samples` | `finalize_suite()` (system samples) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L960-L1010)
| Success Rate | `validation.success_rate_percent` | `finalize_suite()` (handshake status) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L986-L1010)
| Result | `validation.benchmark_pass_fail` | `finalize_suite()` (handshake status) | [core/metrics_aggregator.py](core/metrics_aggregator.py#L986-L1010)

---

## 3) Full Metric Inventory (Per Suite)
Rendered in: [dashboard/frontend/src/pages/SuiteDetail.tsx](dashboard/frontend/src/pages/SuiteDetail.tsx#L330-L460)
Generation: [dashboard/backend/analysis.py](dashboard/backend/analysis.py#L200-L290)

Inventory rows are derived from the `ComprehensiveSuiteMetrics` instance (flattened) and the truth table. The inventory therefore only shows values actually present in the suite object plus GCS validation payloads exposed as `suite.gcs_validation`.

---

## 4) Overview Aggregates
Rendered in: [dashboard/frontend/src/pages/Overview.tsx](dashboard/frontend/src/pages/Overview.tsx#L1-L200)
Aggregation logic: [dashboard/backend/analysis.py](dashboard/backend/analysis.py#L460-L535)

Aggregated fields used by the charts:
- `handshake.handshake_total_duration_ms` → `handshake_handshake_total_duration_ms_mean`
- `power_energy.power_avg_w` → `power_energy_power_avg_w_mean`
- `data_plane.goodput_mbps` → `data_plane_goodput_mbps_mean`
- `data_plane.packet_loss_ratio` → `data_plane_packet_loss_ratio_mean`
- `latency_jitter.one_way_latency_avg_ms` → `latency_jitter_one_way_latency_avg_ms_mean`
- `latency_jitter.rtt_avg_ms` → `latency_jitter_rtt_avg_ms_mean`

All are pulled from `ComprehensiveSuiteMetrics` and depend on the same collection sources listed above.

---

## 5) Verified Wiring Gaps (Resolved)
1) **System Resources (GCS) card population**
   - Mapped from `gcs_validation.jsonl.system_gcs` into `suite.system_gcs` when primary fields are missing.
   - Source: [dashboard/backend/ingest.py](dashboard/backend/ingest.py#L396-L455)

2) **Latency/Jitter and MAVLink Validation visibility**
   - Mapped from `gcs_validation.jsonl.latency_jitter` into `suite.latency_jitter` when primary fields are missing.
   - Mapped from `gcs_validation.jsonl.mavlink_validation` into `suite.mavproxy_gcs` fields when missing.
   - Source: [dashboard/backend/ingest.py](dashboard/backend/ingest.py#L396-L468)

3) **Proxy counters fallback**
   - If `proxy_status.counters` is available and drone data is missing, counters are applied to `suite.data_plane`.
   - Source: [dashboard/backend/ingest.py](dashboard/backend/ingest.py#L456-L468)
