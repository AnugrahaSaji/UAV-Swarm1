MEASUREMENT INTEGRITY AUDIT (CODE + PIPELINE)

Scope (files audited)
- [core/metrics_schema.py](core/metrics_schema.py)
- [core/metrics_aggregator.py](core/metrics_aggregator.py)
- [core/metrics_collectors.py](core/metrics_collectors.py)
- [core/async_proxy.py](core/async_proxy.py)
- [core/handshake.py](core/handshake.py)
- [core/mavlink_collector.py](core/mavlink_collector.py)
- [core/clock_sync.py](core/clock_sync.py)
- [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py)
- [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py)
- [dashboard/backend/ingest.py](dashboard/backend/ingest.py)
- [dashboard/backend/analysis.py](dashboard/backend/analysis.py)
- [dashboard/backend/routes/suites.py](dashboard/backend/routes/suites.py)
- [dashboard/backend/reliability.py](dashboard/backend/reliability.py)
- [dashboard/frontend/src/pages/*.tsx](dashboard/frontend/src/pages)
- [bench/analyze_power_benchmark.py](bench/analyze_power_benchmark.py)
- [bench/analysis/benchmark_plots.py](bench/analysis/benchmark_plots.py)
- [bench/analysis/comprehensive_plots.py](bench/analysis/comprehensive_plots.py)
- [suite_benchmarks/generate_report.py](suite_benchmarks/generate_report.py)
- [suite_benchmarks/generate_ieee_report.py](suite_benchmarks/generate_ieee_report.py)
- [tools/verify_dashboard_truth.py](tools/verify_dashboard_truth.py)
- [tools/verify_metrics_truth.py](tools/verify_metrics_truth.py)
- [fix_dashboard_data.py](fix_dashboard_data.py)

Benchmark data sources (database paths used in code)
- Comprehensive metrics JSON (per-suite): logs/benchmarks/comprehensive/*.json via [dashboard/backend/ingest.py](dashboard/backend/ingest.py).
- JSONL summaries (fallback): logs/benchmarks/benchmark_*.jsonl via [dashboard/backend/ingest.py](dashboard/backend/ingest.py).
- GCS JSONL suite metrics: logs/benchmarks/*/gcs_suite_metrics.jsonl is NOT consumed by the dashboard ingestion code (dashboard README lists it, but ingest does not read it).
- Dashboard/data/*.json is NOT consumed by the dashboard ingestion code (ingest only reads logs/benchmarks). It is a separate artifact store.
- Crypto/power benchmark analysis uses bench_results*/raw/*.json via [bench/analyze_power_benchmark.py](bench/analyze_power_benchmark.py), [bench/analysis/comprehensive_plots.py](bench/analysis/comprehensive_plots.py), and [bench/analysis/benchmark_plots.py](bench/analysis/benchmark_plots.py). This is a separate pipeline from comprehensive suite metrics.

Classification keys
- Implemented + collected + pipelined: populated at runtime and written to comprehensive JSON (and/or JSONL), with at least one visualization consuming it.
- Implemented but conditionally collected: runtime population depends on prerequisites (MAVLink timestamps, power backend, status file, etc.).
- Defined but never implemented: field exists in schema but no population path found.
- Implemented but never pipelined: populated at runtime but not written to output or not forwarded to visualization.

=====================================================
LAYER 1: CRYPTO (Handshake + Primitive breakdown)
=====================================================

Schema metrics (D + E) and pipeline verification

| Metric | Implemented (file/function) | Runtime population | JSONL | Comprehensive JSON | Visualization consumption | Status |
|---|---|---|---|---|---|---|
| `handshake.handshake_start_time_drone` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_handshake_start()` | Called in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) when suite starts; in GCS bench in [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | No | Yes | Dashboard SuiteDetail (run context only; handshake timings displayed) | Implemented but conditionally collected (only if scheduler calls) |
| `handshake.handshake_end_time_drone` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_handshake_end()` | Called after handshake OK in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) and [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | No | Yes | Not displayed directly | Implemented but conditionally collected |
| `handshake.handshake_total_duration_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_handshake_end()` | Requires `handshake_start_time_drone` | Yes (`handshake_ms` in benchmark_*.jsonl) | Yes | Dashboard Overview, SuiteExplorer, SuiteDetail, Comparison, PowerAnalysis, BucketComparison | Implemented + collected + pipelined (conditional on handshake) |
| `handshake.handshake_success` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_handshake_end()` | Set on success/failure | No | Yes | Dashboard SuiteDetail, IntegrityMonitor | Implemented but conditionally collected |
| `handshake.handshake_failure_reason` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_handshake_end()` | Set on failure | No | Yes | Dashboard SuiteDetail | Implemented but conditionally collected |
| `crypto_primitives.kem_keygen_time_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics from proxy status | JSONL: `kem_keygen_ms` | Yes | Not directly visualized | Implemented but conditionally collected |
| `crypto_primitives.kem_encapsulation_time_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | JSONL: `kem_encaps_ms` | Yes | Not directly visualized | Implemented but conditionally collected |
| `crypto_primitives.kem_decapsulation_time_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | JSONL: `kem_decaps_ms` | Yes | Not directly visualized | Implemented but conditionally collected |
| `crypto_primitives.signature_sign_time_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | JSONL: `sig_sign_ms` | Yes | Not directly visualized | Implemented but conditionally collected |
| `crypto_primitives.signature_verify_time_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | JSONL: `sig_verify_ms` | Yes | Not directly visualized | Implemented but conditionally collected |
| `crypto_primitives.total_crypto_time_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Only when all primitive timings present | No | Yes | Not visualized | Implemented but conditionally collected |
| `crypto_primitives.kem_keygen_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | No | Yes | Not visualized | Implemented but conditionally collected |
| `crypto_primitives.kem_encaps_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | No | Yes | Not visualized | Implemented but conditionally collected |
| `crypto_primitives.kem_decaps_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | No | Yes | Not visualized | Implemented but conditionally collected |
| `crypto_primitives.sig_sign_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | No | Yes | Not visualized | Implemented but conditionally collected |
| `crypto_primitives.sig_verify_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | No | Yes | Not visualized | Implemented but conditionally collected |
| `crypto_primitives.pub_key_size_bytes` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | JSONL: `pub_key_size_bytes` | Yes | Not visualized | Implemented but conditionally collected |
| `crypto_primitives.ciphertext_size_bytes` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | JSONL: `ciphertext_size_bytes` | Yes | Not visualized | Implemented but conditionally collected |
| `crypto_primitives.sig_size_bytes` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | JSONL: `sig_size_bytes` | Yes | Not visualized | Implemented but conditionally collected |
| `crypto_primitives.shared_secret_size_bytes` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_crypto_primitives()` | Requires handshake metrics | No | Yes | Not visualized | Implemented but conditionally collected |

Integrity risks (Crypto)
- `crypto_primitives.*` fields are NULL if proxy handshake metrics are missing from status file; no explicit warning in JSONL outputs (only `metric_status` in comprehensive JSON).

=====================================================
LAYER 2: DATA PLANE (Proxy counters + AEAD timings)
=====================================================

Schema metrics (G) and pipeline verification

| Metric | Implemented (file/function) | Runtime population | JSONL | Comprehensive JSON | Visualization consumption | Status |
|---|---|---|---|---|---|---|
| `data_plane.achieved_throughput_mbps` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `finalize_suite()` | Requires proxy counters + duration | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.goodput_mbps` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `finalize_suite()` | Requires plaintext bytes | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.wire_rate_mbps` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `finalize_suite()` | Requires encrypted bytes | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.packets_sent` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Dashboard SuiteDetail, Comparison | Implemented but conditionally collected |
| `data_plane.packets_received` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Dashboard SuiteDetail, Comparison | Implemented but conditionally collected |
| `data_plane.packets_dropped` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Dashboard SuiteDetail | Implemented but conditionally collected |
| `data_plane.packet_loss_ratio` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.packet_delivery_ratio` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Dashboard SuiteDetail | Implemented but conditionally collected |
| `data_plane.replay_drop_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.decode_failure_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.ptx_in` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.ptx_out` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.enc_in` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.enc_out` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.drop_replay` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.drop_auth` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.drop_header` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.bytes_sent` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.bytes_received` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.aead_encrypt_avg_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.aead_decrypt_avg_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.aead_encrypt_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |
| `data_plane.aead_decrypt_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_data_plane_metrics()` | Proxy counters | No | Yes | Not visualized | Implemented but conditionally collected |

Integrity risks (Data Plane)
- Data plane metrics are NULL when proxy status file is missing or counters are empty; only `metric_status` flags this in comprehensive JSON.

=====================================================
LAYER 3: SCHEDULER / CONTROL PLANE
=====================================================

Schema metrics (M) and pipeline verification

| Metric | Implemented (file/function) | Runtime population | JSONL | Comprehensive JSON | Visualization consumption | Status |
|---|---|---|---|---|---|---|
| `control_plane.scheduler_tick_interval_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_control_plane_metrics()` | Called in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `control_plane.scheduler_action_type` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_control_plane_metrics()` | Called in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `control_plane.scheduler_action_reason` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_control_plane_metrics()` | Called in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `control_plane.policy_name` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_control_plane_metrics()` | Called in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `control_plane.policy_state` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_control_plane_metrics()` | Called in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `control_plane.policy_suite_index` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_control_plane_metrics()` | Called in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `control_plane.policy_total_suites` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `record_control_plane_metrics()` | Called in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | No | Yes | SuiteDetail | Implemented but conditionally collected |

Integrity risks (Scheduler)
- No schema fields record offered traffic rate or suite duration targets; those exist only in scheduler runtime (not persisted).

=====================================================
LAYER 4: MAVLink (Transport + Application)
=====================================================

Schema metrics (H, I, J, K, L) and pipeline verification

| Metric | Implemented (file/function) | Runtime population | JSONL | Comprehensive JSON | Visualization consumption | Status |
|---|---|---|---|---|---|---|
| `latency_jitter.one_way_latency_avg_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) `get_metrics()` | Requires timestamped MAVLink + SYSTEM_TIME | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `latency_jitter.one_way_latency_p95_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | Same as above | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `latency_jitter.jitter_avg_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | Same as above | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `latency_jitter.jitter_p95_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | Same as above | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `latency_jitter.latency_sample_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | Same as above | No | Yes | Not visualized | Implemented but conditionally collected |
| `latency_jitter.latency_invalid_reason` | [core/mavlink_collector.py](core/mavlink_collector.py) | Same as above | No | Yes | Not visualized | Implemented but conditionally collected |
| `latency_jitter.rtt_avg_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | Requires COMMAND_LONG/ACK | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `latency_jitter.rtt_p95_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | Requires COMMAND_LONG/ACK | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `latency_jitter.rtt_sample_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | Requires COMMAND_LONG/ACK | No | Yes | Not visualized | Implemented but conditionally collected |
| `latency_jitter.rtt_invalid_reason` | [core/mavlink_collector.py](core/mavlink_collector.py) | Requires COMMAND_LONG/ACK | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_start_time` | [core/mavlink_collector.py](core/mavlink_collector.py) `populate_schema_metrics()` | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_end_time` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_tx_pps` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_rx_pps` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_total_msgs_sent` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_total_msgs_received` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_msg_type_counts` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_heartbeat_interval_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_heartbeat_loss_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_seq_gap_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_cmd_sent_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_cmd_ack_received_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_cmd_ack_latency_avg_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active; invalid if no commands | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_cmd_ack_latency_p95_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active; invalid if no commands | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_drone.mavproxy_drone_stream_rate_hz` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_gcs.mavproxy_gcs_total_msgs_received` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `_merge_peer_data()` | GCS metrics merged | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavproxy_gcs.mavproxy_gcs_seq_gap_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `_merge_peer_data()` | GCS metrics merged | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavlink_integrity.mavlink_sysid` | [core/mavlink_collector.py](core/mavlink_collector.py) `populate_mavlink_integrity()` | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavlink_integrity.mavlink_compid` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavlink_integrity.mavlink_protocol_version` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavlink_integrity.mavlink_packet_crc_error_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `mavlink_integrity.mavlink_decode_error_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `mavlink_integrity.mavlink_msg_drop_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `mavlink_integrity.mavlink_out_of_order_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `mavlink_integrity.mavlink_duplicate_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `mavlink_integrity.mavlink_message_latency_avg_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | Requires timestamped messages | No | Yes | Not visualized | Implemented but conditionally collected |
| `fc_telemetry.fc_mode` | [core/mavlink_collector.py](core/mavlink_collector.py) `get_flight_controller_metrics()` | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `fc_telemetry.fc_armed_state` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `fc_telemetry.fc_heartbeat_age_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `fc_telemetry.fc_attitude_update_rate_hz` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `fc_telemetry.fc_position_update_rate_hz` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `fc_telemetry.fc_battery_voltage_v` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `fc_telemetry.fc_battery_current_a` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `fc_telemetry.fc_battery_remaining_percent` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `fc_telemetry.fc_cpu_load_percent` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |
| `fc_telemetry.fc_sensor_health_flags` | [core/mavlink_collector.py](core/mavlink_collector.py) | Collector active | No | Yes | Not visualized | Implemented but conditionally collected |

Integrity risks (MAVLink)
- One-way latency is invalid when SYSTEM_TIME mapping is missing; status only recorded via `latency_invalid_reason`, which is not shown in most visualizations.

=====================================================
LAYER 5: SYSTEM RESOURCES
=====================================================

Schema metrics (N + O) and pipeline verification

| Metric | Implemented (file/function) | Runtime population | JSONL | Comprehensive JSON | Visualization consumption | Status |
|---|---|---|---|---|---|---|
| `system_drone.cpu_usage_avg_percent` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `finalize_suite()` | Requires system sampling thread | No | Yes | SuiteDetail, Comparison | Implemented but conditionally collected |
| `system_drone.cpu_usage_peak_percent` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Requires system sampling thread | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `system_drone.cpu_freq_mhz` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Requires system sampling thread | No | Yes | Not visualized | Implemented but conditionally collected |
| `system_drone.memory_rss_mb` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Requires system sampling thread | No | Yes | SuiteDetail, Comparison | Implemented but conditionally collected |
| `system_drone.memory_vms_mb` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Requires system sampling thread | No | Yes | Not visualized | Implemented but conditionally collected |
| `system_drone.thread_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Requires system sampling thread | No | Yes | Not visualized | Implemented but conditionally collected |
| `system_drone.temperature_c` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Requires system sampling thread | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `system_drone.uptime_s` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Requires system sampling thread | No | Yes | Not visualized | Implemented but conditionally collected |
| `system_drone.load_avg_1m` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Requires system sampling thread | No | Yes | Not visualized | Implemented but conditionally collected |
| `system_drone.load_avg_5m` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Requires system sampling thread | No | Yes | Not visualized | Implemented but conditionally collected |
| `system_drone.load_avg_15m` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Requires system sampling thread | No | Yes | Not visualized | Implemented but conditionally collected |
| `system_gcs.*` (all fields) | [core/metrics_aggregator.py](core/metrics_aggregator.py) `_merge_peer_data()` | Only if GCS metrics merged from `stop_suite` | No | Yes | SuiteDetail | Implemented but conditionally collected |

Integrity risks (System)
- GCS system metrics depend on `stop_suite` response; if GCS bench is not used or fails, fields remain NULL.

=====================================================
LAYER 6: POWER & ENERGY
=====================================================

Schema metrics (P) and pipeline verification

| Metric | Implemented (file/function) | Runtime population | JSONL | Comprehensive JSON | Visualization consumption | Status |
|---|---|---|---|---|---|---|
| `power_energy.power_sensor_type` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `finalize_suite()` | PowerCollector backend available | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `power_energy.power_sampling_rate_hz` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | PowerCollector active | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `power_energy.voltage_avg_v` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | PowerCollector active | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `power_energy.current_avg_a` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | PowerCollector active | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `power_energy.power_avg_w` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | PowerCollector active | No | Yes | SuiteExplorer, SuiteDetail, Overview, Comparison, PowerAnalysis, BucketComparison | Implemented + collected + pipelined (conditional on backend) |
| `power_energy.power_peak_w` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | PowerCollector active | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `power_energy.energy_total_j` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | PowerCollector active | No | Yes | SuiteExplorer, SuiteDetail, Comparison, PowerAnalysis, BucketComparison | Implemented + collected + pipelined (conditional on backend) |
| `power_energy.energy_per_handshake_j` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | PowerCollector + handshake duration | No | Yes | SuiteDetail | Implemented but conditionally collected |

Integrity risks (Power)
- Power metrics are NULL if INA219 or hwmon backends are unavailable; dashboards still compute aggregated charts without explicit per-point invalid warnings.

=====================================================
LAYER 7: CLOCK SYNC
=====================================================

Schema metrics (A) and pipeline verification

| Metric | Implemented (file/function) | Runtime population | JSONL | Comprehensive JSON | Visualization consumption | Status |
|---|---|---|---|---|---|---|
| `run_context.clock_offset_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `set_clock_offset()` | Chronos RPC in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | No | Yes | Not visualized | Implemented but conditionally collected |
| `run_context.clock_offset_method` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `set_clock_offset()` | Chronos RPC in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | No | Yes | Not visualized | Implemented but conditionally collected |

Integrity risks (Clock Sync)
- Clock sync affects only `run_context` fields; MAVLink latency uses system timestamps, not chronos offset.

=====================================================
RUN CONTEXT + SUITE IDENTITY + LIFECYCLE + OBSERVABILITY + VALIDATION
=====================================================

Schema metrics (A + B + C + Q + R)

| Metric | Implemented (file/function) | Runtime population | JSONL | Comprehensive JSON | Visualization consumption | Status |
|---|---|---|---|---|---|---|
| `run_context.run_id` | [core/metrics_aggregator.py](core/metrics_aggregator.py) `start_suite()` | Scheduler sets run ID | JSONL (run_id inferred in dashboard ingest) | Yes | SuiteExplorer, SuiteDetail, Overview | Implemented + collected + pipelined |
| `run_context.suite_id` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite activation | JSONL `suite_id` | Yes | SuiteExplorer, SuiteDetail | Implemented + collected + pipelined |
| `run_context.suite_index` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite activation | JSONL uses index from run in dashboard ingest | Yes | SuiteExplorer, SuiteDetail | Implemented + collected + pipelined |
| `run_context.git_commit_hash` | [core/metrics_collectors.py](core/metrics_collectors.py) `EnvironmentCollector.collect()` | Suite activation | No | Yes | SuiteDetail, Overview | Implemented but conditionally collected |
| `run_context.git_dirty_flag` | [core/metrics_collectors.py](core/metrics_collectors.py) | Suite activation | No | Yes | Not visualized | Implemented but conditionally collected |
| `run_context.gcs_hostname` | [core/metrics_collectors.py](core/metrics_collectors.py) | Suite activation (GCS) | No | Yes | Overview, SuiteDetail | Implemented but conditionally collected |
| `run_context.drone_hostname` | [core/metrics_collectors.py](core/metrics_collectors.py) | Suite activation (drone) | No | Yes | Overview, SuiteDetail | Implemented but conditionally collected |
| `run_context.gcs_ip` | [core/metrics_collectors.py](core/metrics_collectors.py) | Suite activation | No | Yes | Not visualized | Implemented but conditionally collected |
| `run_context.drone_ip` | [core/metrics_collectors.py](core/metrics_collectors.py) | Suite activation | No | Yes | Not visualized | Implemented but conditionally collected |
| `run_context.python_env_gcs` | [core/metrics_collectors.py](core/metrics_collectors.py) | Suite activation | No | Yes | Not visualized | Implemented but conditionally collected |
| `run_context.python_env_drone` | [core/metrics_collectors.py](core/metrics_collectors.py) | Suite activation | No | Yes | Not visualized | Implemented but conditionally collected |
| `run_context.liboqs_version` | [core/metrics_collectors.py](core/metrics_collectors.py) | Suite activation | No | Yes | Not visualized | Implemented but conditionally collected |
| `run_context.kernel_version_gcs` | [core/metrics_collectors.py](core/metrics_collectors.py) | Suite activation | No | Yes | Not visualized | Implemented but conditionally collected |
| `run_context.kernel_version_drone` | [core/metrics_collectors.py](core/metrics_collectors.py) | Suite activation | No | Yes | Not visualized | Implemented but conditionally collected |
| `run_context.run_start_time_wall` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite activation | JSONL `ts` (not a direct mapping) | Yes | Overview | Implemented + collected + pipelined |
| `run_context.run_end_time_wall` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite completion | No | Yes | Not visualized | Implemented but conditionally collected |
| `run_context.run_start_time_mono` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite activation | No | Yes | Not visualized | Implemented but conditionally collected |
| `run_context.run_end_time_mono` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite completion | No | Yes | Not visualized | Implemented but conditionally collected |
| `crypto_identity.kem_algorithm` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite config | JSONL `kem_name` | Yes | SuiteExplorer, SuiteDetail | Implemented + collected + pipelined |
| `crypto_identity.kem_family` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite config | No | Yes | SuiteDetail/filters | Implemented but conditionally collected |
| `crypto_identity.kem_nist_level` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite config | JSONL `nist_level` | Yes | SuiteExplorer/filters | Implemented + collected + pipelined |
| `crypto_identity.sig_algorithm` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite config | JSONL `sig_name` | Yes | SuiteExplorer, SuiteDetail | Implemented + collected + pipelined |
| `crypto_identity.sig_family` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite config | No | Yes | SuiteDetail/filters | Implemented but conditionally collected |
| `crypto_identity.sig_nist_level` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite config | JSONL `nist_level` | Yes | Not visualized | Implemented but conditionally collected |
| `crypto_identity.aead_algorithm` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite config | JSONL `aead` | Yes | SuiteExplorer, SuiteDetail, Buckets | Implemented + collected + pipelined |
| `crypto_identity.suite_security_level` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite config | JSONL `nist_level` | Yes | SuiteExplorer, Buckets | Implemented + collected + pipelined |
| `lifecycle.suite_selected_time` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite activation | No | Yes | Not visualized | Implemented but conditionally collected |
| `lifecycle.suite_activated_time` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Handshake end | No | Yes | Not visualized | Implemented but conditionally collected |
| `lifecycle.suite_deactivated_time` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite completion | No | Yes | Not visualized | Implemented but conditionally collected |
| `lifecycle.suite_total_duration_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite completion | No | Yes | Not visualized | Implemented but conditionally collected |
| `lifecycle.suite_active_duration_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Suite completion | No | Yes | Not visualized | Implemented but conditionally collected |
| `observability.log_sample_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Background system sampling | No | Yes | Not visualized | Implemented but conditionally collected |
| `observability.metrics_sampling_rate_hz` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Background system sampling | No | Yes | Not visualized | Implemented but conditionally collected |
| `observability.collection_start_time` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Background system sampling | No | Yes | Not visualized | Implemented but conditionally collected |
| `observability.collection_end_time` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Background system sampling | No | Yes | Not visualized | Implemented but conditionally collected |
| `observability.collection_duration_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Background system sampling | No | Yes | Not visualized | Implemented but conditionally collected |
| `validation.expected_samples` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Background system sampling | No | Yes | Not visualized | Implemented but conditionally collected |
| `validation.collected_samples` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Background system sampling | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `validation.lost_samples` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Background system sampling | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `validation.success_rate_percent` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Handshake status | No | Yes | SuiteDetail | Implemented but conditionally collected |
| `validation.benchmark_pass_fail` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Handshake status | JSONL `success` (mapped in dashboard minimal suite) | Yes | SuiteExplorer, SuiteDetail, IntegrityMonitor | Implemented + collected + pipelined |
| `validation.metric_status` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Set during finalize | No | Yes | SuiteDetail (via status map) | Implemented + collected + pipelined |

Integrity risks (Context/Validation)
- JSONL fallback (benchmark_*.jsonl) does not include most schema fields; dashboard uses a minimal suite constructor which marks missing fields as `not_collected` but omits metrics that are not referenced by the UI.

=====================================================
VISUALIZATION + PIPELINE AUDIT
=====================================================

Dashboard visualization and API pipeline
- Ingestion: [dashboard/backend/ingest.py](dashboard/backend/ingest.py) reads logs/benchmarks/comprehensive/*.json and falls back to logs/benchmarks/benchmark_*.jsonl.
- API: [dashboard/backend/routes/suites.py](dashboard/backend/routes/suites.py) exposes /api/suites, /api/suite/{key}, /api/aggregate/kem-family, /api/buckets.
- Frontend pages and fields:
  - Overview: uses aggregated `crypto_identity.kem_family` + `handshake.handshake_total_duration_ms` + `power_energy.power_avg_w` via /api/aggregate/kem-family in [dashboard/frontend/src/pages/Overview.tsx](dashboard/frontend/src/pages/Overview.tsx).
  - SuiteExplorer: uses `kem_algorithm`, `sig_algorithm`, `aead_algorithm`, `suite_security_level`, `handshake_total_duration_ms`, `power_avg_w`, `energy_total_j`, `benchmark_pass_fail` from SuiteSummary in [dashboard/frontend/src/pages/SuiteExplorer.tsx](dashboard/frontend/src/pages/SuiteExplorer.tsx).
  - SuiteDetail: uses multiple categories (run_context, crypto_identity, handshake, control_plane, data_plane, latency_jitter, mavlink_integrity, system, power, validation) in [dashboard/frontend/src/pages/SuiteDetail.tsx](dashboard/frontend/src/pages/SuiteDetail.tsx).
  - ComparisonView: uses `handshake_total_duration_ms`, `power_avg_w`, `energy_total_j`, `cpu_usage_avg_percent` in [dashboard/frontend/src/pages/ComparisonView.tsx](dashboard/frontend/src/pages/ComparisonView.tsx).
  - PowerAnalysis: uses `power_avg_w`, `energy_total_j`, `handshake_total_duration_ms` in [dashboard/frontend/src/pages/PowerAnalysis.tsx](dashboard/frontend/src/pages/PowerAnalysis.tsx).
  - BucketComparison: uses `handshake_ms`, `power_w`, `energy_j`, and suite identity fields returned by /api/buckets in [dashboard/frontend/src/pages/BucketComparison.tsx](dashboard/frontend/src/pages/BucketComparison.tsx).
  - IntegrityMonitor: uses `benchmark_pass_fail`, `handshake_success`, `power_avg_w`, `handshake_total_duration_ms` (summary-only) in [dashboard/frontend/src/pages/IntegrityMonitor.tsx](dashboard/frontend/src/pages/IntegrityMonitor.tsx).

Plots that may silently include invalid/biased data
- Dashboard Overview and PowerAnalysis aggregate across suites without excluding `metric_status` invalid fields. Missing power or latency data can skew averages if many suites are NULL.
- BucketComparison and ComparisonView plot raw `handshake_ms`/`power_w`/`energy_j` without checking `metric_status` (NULLs are possible with JSONL-only ingest).
- SuiteDetail uses `metric_status` for some fields but not all; e.g., `latency_jitter.*` invalid reasons are not surfaced unless explicitly referenced.

Bench analysis visualizations (separate pipeline)
- [bench/analyze_power_benchmark.py](bench/analyze_power_benchmark.py), [bench/analysis/benchmark_plots.py](bench/analysis/benchmark_plots.py), and [bench/analysis/comprehensive_plots.py](bench/analysis/comprehensive_plots.py) consume bench_results*/raw/*.json (crypto/power microbench). These are not derived from comprehensive suite metrics.
- [suite_benchmarks/generate_report.py](suite_benchmarks/generate_report.py) and [suite_benchmarks/generate_ieee_report.py](suite_benchmarks/generate_ieee_report.py) consume `benchmark_results.json` style data (suite-level) with fields like `handshake_ms`, `kem_encaps_ms`, `sig_verify_ms`, `pub_key_size_bytes`.

Metrics collected but never visualized (dashboard)
- Most fields in `crypto_primitives`, `data_plane`, `mavproxy_*`, `mavlink_integrity` (beyond small subset), `observability`, and `validation` (except pass/fail) are not visualized.

Metrics visualized but often NULL/conditional
- `latency_jitter.*` and `mavlink_integrity.*` depend on MAVLink timestamps and collector availability; may be NULL or invalid without warning on overview/aggregate pages.
- `power_energy.*` is NULL when power backend unavailable; aggregate charts still compute averages without explicit exclusion flags.

=====================================================
MEASUREMENT INTEGRITY RISKS (EXPLICIT)
=====================================================
- Blackout measurement bias: `rekey_blackout_duration_ms` ends on first post-rekey packet, so sparse traffic inflates blackout in [core/async_proxy.py](core/async_proxy.py).
- Latency validity: MAVLink latency depends on SYSTEM_TIME/timestamped messages; invalid reasons are stored but not consistently surfaced in visualizations.
- Clock sync drift: only `clock_offset_ms` is stored; no drift/uncertainty; MAVLink latencies do not use Chronos offset.
- Dashboard ingestion mismatch: README lists forensic_metrics.jsonl and validation_metrics_fixed.jsonl, but ingest ignores them; UI can silently show incomplete metrics when only JSONL data exists.
- JSONL fallback lacks most schema fields; minimal suite builder marks some `metric_status` paths but cannot guarantee coverage.
