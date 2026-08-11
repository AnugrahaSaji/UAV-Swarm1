METRICS AUDIT (CODE-BASED, IMPLEMENTATION ONLY)

Scope (files audited)
- [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py)
- [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py)
- [sscheduler/sdrone.py](sscheduler/sdrone.py)
- [sscheduler/sgcs.py](sscheduler/sgcs.py)
- [core/metrics_schema.py](core/metrics_schema.py)
- [core/metrics_aggregator.py](core/metrics_aggregator.py)
- [core/mavlink_collector.py](core/mavlink_collector.py)
- [core/power_monitor.py](core/power_monitor.py)
- [core/power_monitor_full.py](core/power_monitor_full.py)
- [core/async_proxy.py](core/async_proxy.py)
- [core/handshake.py](core/handshake.py)
- [core/clock_sync.py](core/clock_sync.py)
- [core/config.py](core/config.py)
- [core/metrics_collectors.py](core/metrics_collectors.py)

=====================================================
1) IMPLEMENTED METRICS TABLE
=====================================================

1.1 sdrone_bench.py (Drone benchmark scheduler)

1.1.1 JSONL: benchmark_{run_id}.jsonl

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `ts` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Suite activation ends with handshake status read | Yes | None (wall time always set) | Timestamp of result emission |
| `suite_id` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Same as above | Yes | None | Suite identifier |
| `nist_level` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Same as above | Yes | Missing suite config -> empty string | Suite security level (from suite registry) |
| `kem_name` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Same as above | Yes | Missing suite config -> empty string | KEM algorithm name (registry) |
| `sig_name` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Same as above | Yes | Missing suite config -> empty string | Signature algorithm name (registry) |
| `aead` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Same as above | Yes | Missing suite config -> empty string | AEAD algorithm token (registry) |
| `success` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Handshake success/timeout | Yes | False on handshake timeout | Handshake success indicator |
| `error` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Handshake failure or activation failure | Conditional | Empty when success | Failure reason string |
| `handshake_ms` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Handshake status file has `handshake_metrics` | Conditional | 0 if `handshake_metrics` missing | Handshake duration derived from proxy metrics (`rekey_ms`) |
| `kem_keygen_ms` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Handshake metrics present | Conditional | 0 if missing | KEM keygen time (max) from proxy metrics |
| `kem_encaps_ms` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Handshake metrics present | Conditional | 0 if missing | KEM encapsulation time (max) |
| `kem_decaps_ms` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Handshake metrics present | Conditional | 0 if missing | KEM decapsulation time (max) |
| `sig_sign_ms` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Handshake metrics present | Conditional | 0 if missing | Signature sign time (max) |
| `sig_verify_ms` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Handshake metrics present | Conditional | 0 if missing | Signature verify time (max) |
| `pub_key_size_bytes` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Handshake metrics present | Conditional | 0 if missing | KEM public key size |
| `ciphertext_size_bytes` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Handshake metrics present | Conditional | 0 if missing | KEM ciphertext size |
| `sig_size_bytes` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_log_result()` | Handshake metrics present | Conditional | 0 if missing | Signature size |

1.1.2 JSONL: benchmark_gcs_{run_id}.jsonl

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `ts` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_collect_gcs_metrics()` | After `stop_suite` response | Yes | None | Timestamp of GCS metrics capture |
| `suite_id` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `_collect_gcs_metrics()` | After `stop_suite` response | Yes | None | Suite identifier |
| `gcs_info.hostname` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `GcsBenchmarkServer._handle_command(get_info)` | `get_info` RPC | Conditional | Empty if RPC fails | GCS hostname |
| `gcs_info.ip` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `get_info` | `get_info` RPC | Conditional | Empty if RPC fails | GCS IP address |
| `gcs_info.kernel_version` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `get_info` | `get_info` RPC | Conditional | Empty if RPC fails | GCS OS/kernel version |
| `gcs_info.python_env` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `get_info` | `get_info` RPC | Conditional | Empty if RPC fails | GCS Python runtime version |
| `gcs_metrics.status` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | `stop_suite` RPC | Conditional | Error if proxy stop fails | Status of stop_suite |
| `gcs_metrics.suite` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | `stop_suite` RPC | Conditional | Missing if stop_suite fails | Suite id at GCS |
| `gcs_metrics.mavlink_validation.total_msgs_received` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | `MavLinkMetricsCollector.stop()` | Conditional | None if MAVLink collector unavailable | GCS-side MAVLink total messages received |
| `gcs_metrics.mavlink_validation.seq_gap_count` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | `MavLinkMetricsCollector.stop()` | Conditional | None if MAVLink collector unavailable | GCS-side MAVLink sequence gap count |
| `gcs_metrics.latency_jitter.one_way_latency_avg_ms` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | `MavLinkMetricsCollector.stop()` | Conditional | None if no timestamped messages or SYSTEM_TIME missing | One-way latency average |
| `gcs_metrics.latency_jitter.one_way_latency_p95_ms` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | Same as above | Conditional | None if invalid | One-way latency p95 |
| `gcs_metrics.latency_jitter.jitter_avg_ms` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | Same as above | Conditional | None if invalid | One-way latency jitter average |
| `gcs_metrics.latency_jitter.jitter_p95_ms` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | Same as above | Conditional | None if invalid | One-way latency jitter p95 |
| `gcs_metrics.latency_jitter.latency_sample_count` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | Same as above | Conditional | 0/None if invalid | Latency sample count |
| `gcs_metrics.latency_jitter.latency_invalid_reason` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | Same as above | Conditional | Populated when invalid | Invalid reason string |
| `gcs_metrics.latency_jitter.rtt_avg_ms` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | COMMAND_LONG/ACK tracking | Conditional | None if no command sent/ack | RTT average |
| `gcs_metrics.latency_jitter.rtt_p95_ms` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | Same as above | Conditional | None if invalid | RTT p95 |
| `gcs_metrics.latency_jitter.rtt_sample_count` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | Same as above | Conditional | 0/None if invalid | RTT sample count |
| `gcs_metrics.latency_jitter.rtt_invalid_reason` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` response | Same as above | Conditional | Populated when invalid | RTT invalid reason |
| `gcs_metrics.system_gcs.*` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `GcsSystemMetricsCollector.stop()` | `start_proxy` → `stop_suite` | Conditional | Empty dict if sampling not started | GCS system resource snapshot (avg/peak + last sample) |
| `gcs_metrics.proxy_status.*` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `_read_proxy_status()` | `stop_suite` | Conditional | `{}` if status file missing | GCS proxy status from status file |

1.1.3 gcs_metrics.proxy_status (fields from core/async_proxy.py status writer)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `proxy_status.status` | [core/async_proxy.py](core/async_proxy.py) | `run_proxy()` status writer | Proxy running | Conditional | Missing if status file disabled | Proxy state string |
| `proxy_status.suite` | [core/async_proxy.py](core/async_proxy.py) | `run_proxy()` status writer | Proxy running | Conditional | Missing if status file disabled | Suite id |
| `proxy_status.ts_ns` | [core/async_proxy.py](core/async_proxy.py) | `run_proxy()` status writer | Proxy running | Conditional | Missing if status file disabled | Status sample time (ns) |
| `proxy_status.counters.ptx_in` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no plaintext ingress | Plaintext packets in |
| `proxy_status.counters.ptx_out` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no plaintext egress | Plaintext packets out |
| `proxy_status.counters.enc_in` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no encrypted ingress | Encrypted packets in |
| `proxy_status.counters.enc_out` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no encrypted egress | Encrypted packets out |
| `proxy_status.counters.ptx_bytes_in` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no plaintext ingress | Plaintext bytes in |
| `proxy_status.counters.ptx_bytes_out` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no plaintext egress | Plaintext bytes out |
| `proxy_status.counters.enc_bytes_in` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no encrypted ingress | Encrypted bytes in |
| `proxy_status.counters.enc_bytes_out` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no encrypted egress | Encrypted bytes out |
| `proxy_status.counters.bytes_in` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | Mirrors `enc_bytes_in` | Encrypted bytes in (alias) |
| `proxy_status.counters.bytes_out` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | Mirrors `enc_bytes_out` | Encrypted bytes out (alias) |
| `proxy_status.counters.drops` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no drops | Total drops |
| `proxy_status.counters.drop_replay` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no replay drops | Replay drops |
| `proxy_status.counters.drop_auth` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no auth failures | Auth/tag failures |
| `proxy_status.counters.drop_header` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no header mismatch | Header mismatch drops |
| `proxy_status.counters.drop_session_epoch` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no epoch/session drops | Session/epoch drops |
| `proxy_status.counters.drop_other` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no other drops | Other drops |
| `proxy_status.counters.drop_src_addr` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Proxy running | Conditional | 0 if no mismatch | Strict peer mismatch drops |
| `proxy_status.counters.rekeys_ok` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Rekey attempts | Conditional | 0 if no rekey | Rekey successes |
| `proxy_status.counters.rekeys_fail` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Rekey attempts | Conditional | 0 if no rekey | Rekey failures |
| `proxy_status.counters.last_rekey_ms` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Rekey attempts | Conditional | 0 if no rekey | Last rekey duration (ms) |
| `proxy_status.counters.last_rekey_suite` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Rekey attempts | Conditional | Empty string if no rekey | Last rekey target suite |
| `proxy_status.counters.rekey_interval_ms` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.to_dict()` | Rekey attempts | Conditional | 0 if no prior rekey | Interval between rekeys |
| `proxy_status.counters.rekey_duration_ms` | [core/async_proxy.py](core/async_proxy.py) | `_finalize_rekey()` | Rekey completion | Conditional | 0 if no rekey | Rekey duration |
| `proxy_status.counters.rekey_blackout_duration_ms` | [core/async_proxy.py](core/async_proxy.py) | `_finalize_rekey()` | Rekey completion | Conditional | 0 if no rekey | Blackout duration (traffic-dependent) |
| `proxy_status.counters.rekey_trigger_reason` | [core/async_proxy.py](core/async_proxy.py) | `_launch_rekey()` | Rekey initiation | Conditional | Empty string if none | Rekey trigger reason |
| `proxy_status.counters.handshake_metrics.*` | [core/async_proxy.py](core/async_proxy.py) | `_perform_handshake()` + `handshake.py` | Handshake complete | Conditional | Empty if handshake metrics not produced | Handshake timing + artifact sizes (nested) |
| `proxy_status.counters.primitive_metrics.aead_encrypt.*` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.record_encrypt()` | Each encrypt | Conditional | All zeros if no traffic | AEAD encrypt count/total/min/max/time/bytes |
| `proxy_status.counters.primitive_metrics.aead_decrypt_ok.*` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.record_decrypt_ok()` | Each decrypt success | Conditional | All zeros if no traffic | AEAD decrypt OK stats |
| `proxy_status.counters.primitive_metrics.aead_decrypt_fail.*` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters.record_decrypt_fail()` | Each decrypt failure | Conditional | All zeros if no failures | AEAD decrypt fail stats |
| `proxy_status.counters.part_b_metrics.*` | [core/async_proxy.py](core/async_proxy.py) | `ProxyCounters._part_b_metrics()` | Handshake metrics present | Conditional | Absent if handshake metrics missing | Flattened handshake/crypto fields for legacy output |

1.1.4 Comprehensive JSON: logs/benchmarks/comprehensive (drone role)

Source: [core/metrics_aggregator.py](core/metrics_aggregator.py) with `MetricsAggregator` invoked from [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py). The following schema paths are populated or explicitly nulled per suite.

Run & context (A)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `run_context.run_id` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Yes | None | Run identifier |
| `run_context.suite_id` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Yes | None | Suite identifier |
| `run_context.suite_index` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Yes | None | Suite index in run |
| `run_context.git_commit_hash` | [core/metrics_collectors.py](core/metrics_collectors.py) | `EnvironmentCollector.collect()` | Suite activation | Conditional | None if git unavailable | Code version fingerprint |
| `run_context.git_dirty_flag` | [core/metrics_collectors.py](core/metrics_collectors.py) | `EnvironmentCollector.collect()` | Suite activation | Conditional | None if git unavailable | Dirty tree indicator |
| `run_context.drone_hostname` | [core/metrics_collectors.py](core/metrics_collectors.py) | `EnvironmentCollector.collect()` | Suite activation | Conditional | None if env unavailable | Drone hostname |
| `run_context.drone_ip` | [core/metrics_collectors.py](core/metrics_collectors.py) | `EnvironmentCollector.get_ip_address()` | Suite activation | Conditional | None if IP resolution fails | Drone IP |
| `run_context.python_env_drone` | [core/metrics_collectors.py](core/metrics_collectors.py) | `EnvironmentCollector.collect()` | Suite activation | Conditional | None if env unavailable | Python env identifier |
| `run_context.kernel_version_drone` | [core/metrics_collectors.py](core/metrics_collectors.py) | `EnvironmentCollector.collect()` | Suite activation | Conditional | None if env unavailable | Drone kernel version |
| `run_context.liboqs_version` | [core/metrics_collectors.py](core/metrics_collectors.py) | `EnvironmentCollector.collect()` | Suite activation | Conditional | None if liboqs missing | liboqs version |
| `run_context.clock_offset_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `set_clock_offset()` | Chronos RPC success | Conditional | None if chronos sync fails | GCS-Drone clock offset |
| `run_context.clock_offset_method` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `set_clock_offset()` | Chronos RPC success | Conditional | None if chronos sync fails | Offset method name |
| `run_context.run_start_time_wall` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Yes | None | Start wall clock |
| `run_context.run_end_time_wall` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Suite completion | Yes | None | End wall clock |
| `run_context.run_start_time_mono` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Yes | None | Start monotonic |
| `run_context.run_end_time_mono` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Suite completion | Yes | None | End monotonic |

Suite crypto identity (B)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `crypto_identity.kem_algorithm` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Conditional | None if suite config missing | KEM name |
| `crypto_identity.kem_family` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Conditional | None if suite config missing | KEM family label |
| `crypto_identity.kem_nist_level` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Conditional | None if suite config missing | KEM NIST level |
| `crypto_identity.sig_algorithm` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Conditional | None if suite config missing | Signature name |
| `crypto_identity.sig_family` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Conditional | None if suite config missing | Signature family |
| `crypto_identity.sig_nist_level` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Conditional | None if suite config missing | Signature NIST level |
| `crypto_identity.aead_algorithm` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Conditional | None if suite config missing | AEAD token |
| `crypto_identity.suite_security_level` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Conditional | None if suite config missing | Suite security level |

Suite lifecycle (C)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `lifecycle.suite_selected_time` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` | Suite activation | Yes | None | Suite selection time (monotonic) |
| `lifecycle.suite_activated_time` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_handshake_end()` | Handshake end | Conditional | 0 if handshake not recorded | Time suite becomes active |
| `lifecycle.suite_deactivated_time` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Suite completion | Yes | None | Suite end time |
| `lifecycle.suite_total_duration_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Suite completion | Yes | None | Total suite duration |
| `lifecycle.suite_active_duration_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Suite completion | Conditional | 0 if activation time missing | Active duration |

Handshake (D)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `handshake.handshake_start_time_drone` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_handshake_start()` | Suite activation | Conditional | None if not called | Handshake start (monotonic) |
| `handshake.handshake_end_time_drone` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_handshake_end()` | Handshake completion | Conditional | None if handshake not recorded | Handshake end (monotonic) |
| `handshake.handshake_total_duration_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_handshake_end()` | Handshake completion | Conditional | None if start time missing | Handshake duration |
| `handshake.handshake_success` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_handshake_end()` | Handshake completion | Conditional | None if not called | Success flag |
| `handshake.handshake_failure_reason` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_handshake_end()` | Handshake failure | Conditional | None if success | Failure reason |

Crypto primitives (E)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `crypto_primitives.kem_keygen_time_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if handshake metrics missing | KEM keygen time (ms) |
| `crypto_primitives.kem_encapsulation_time_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | KEM encapsulation time (ms) |
| `crypto_primitives.kem_decapsulation_time_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | KEM decapsulation time (ms) |
| `crypto_primitives.signature_sign_time_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | Signature sign time (ms) |
| `crypto_primitives.signature_verify_time_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | Signature verify time (ms) |
| `crypto_primitives.total_crypto_time_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | All sub-parts present | Conditional | None if any part missing | Sum of primitives |
| `crypto_primitives.kem_keygen_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | KEM keygen time (ns) |
| `crypto_primitives.kem_encaps_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | KEM encap time (ns) |
| `crypto_primitives.kem_decaps_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | KEM decap time (ns) |
| `crypto_primitives.sig_sign_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | Signature sign time (ns) |
| `crypto_primitives.sig_verify_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | Signature verify time (ns) |
| `crypto_primitives.pub_key_size_bytes` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | KEM public key size |
| `crypto_primitives.ciphertext_size_bytes` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | KEM ciphertext size |
| `crypto_primitives.sig_size_bytes` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | Signature size |
| `crypto_primitives.shared_secret_size_bytes` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` | Handshake metrics parsed | Conditional | None if missing | Shared secret size |

Rekey (F) and data plane (G)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `rekey.rekey_attempts` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Rekey attempts count |
| `rekey.rekey_success` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Rekey success count |
| `rekey.rekey_failure` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Rekey failure count |
| `rekey.rekey_interval_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Interval between rekeys |
| `rekey.rekey_duration_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Rekey duration |
| `rekey.rekey_blackout_duration_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Rekey blackout duration |
| `rekey.rekey_trigger_reason` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Rekey trigger reason |
| `data_plane.ptx_in` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Plaintext packets in |
| `data_plane.ptx_out` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Plaintext packets out |
| `data_plane.enc_in` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Encrypted packets in |
| `data_plane.enc_out` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Encrypted packets out |
| `data_plane.drop_replay` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Replay drops |
| `data_plane.drop_auth` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Auth drops |
| `data_plane.drop_header` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Header drops |
| `data_plane.replay_drop_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Replay drop count |
| `data_plane.decode_failure_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if drop counters missing | Decode failure count |
| `data_plane.packets_sent` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Encrypted packets sent |
| `data_plane.packets_received` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Encrypted packets received |
| `data_plane.packets_dropped` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Total packet drops |
| `data_plane.packet_loss_ratio` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if sent/dropped missing | Loss ratio |
| `data_plane.packet_delivery_ratio` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if sent/dropped missing | Delivery ratio |
| `data_plane.bytes_sent` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Plaintext bytes sent |
| `data_plane.bytes_received` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if counters missing | Plaintext bytes received |
| `data_plane.aead_encrypt_avg_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if no AEAD stats | AEAD encrypt avg time |
| `data_plane.aead_decrypt_avg_ns` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if no AEAD stats | AEAD decrypt avg time |
| `data_plane.aead_encrypt_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if no AEAD stats | AEAD encrypt count |
| `data_plane.aead_decrypt_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` | Proxy counters read | Conditional | None if no AEAD stats | AEAD decrypt count |
| `data_plane.goodput_mbps` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Duration + byte counters present | Conditional | None if counters missing | Goodput (plaintext bytes) |
| `data_plane.achieved_throughput_mbps` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Duration + byte counters present | Conditional | None if counters missing | Achieved throughput |
| `data_plane.wire_rate_mbps` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Duration + encrypted bytes present | Conditional | None if counters missing | Wire rate (encrypted bytes) |

Latency & MAVLink (H, I, J, K, L)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `latency_jitter.one_way_latency_avg_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_metrics()` | MAVLink sniffing active | Conditional | None if no SYSTEM_TIME/timestamp | One-way latency avg |
| `latency_jitter.one_way_latency_p95_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_metrics()` | MAVLink sniffing active | Conditional | None if invalid | One-way latency p95 |
| `latency_jitter.jitter_avg_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_metrics()` | MAVLink sniffing active | Conditional | None if invalid | Jitter average |
| `latency_jitter.jitter_p95_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_metrics()` | MAVLink sniffing active | Conditional | None if invalid | Jitter p95 |
| `latency_jitter.latency_sample_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_metrics()` | MAVLink sniffing active | Conditional | 0/None if invalid | Latency sample count |
| `latency_jitter.latency_invalid_reason` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_metrics()` | MAVLink sniffing active | Conditional | Populated when invalid | Invalid reason |
| `latency_jitter.rtt_avg_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_metrics()` | COMMAND_LONG/ACK present | Conditional | None if no command sent/ack | RTT average |
| `latency_jitter.rtt_p95_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_metrics()` | COMMAND_LONG/ACK present | Conditional | None if invalid | RTT p95 |
| `latency_jitter.rtt_sample_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_metrics()` | COMMAND_LONG/ACK present | Conditional | 0/None if invalid | RTT sample count |
| `latency_jitter.rtt_invalid_reason` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_metrics()` | COMMAND_LONG/ACK present | Conditional | Populated when invalid | RTT invalid reason |
| `mavproxy_drone.mavproxy_drone_start_time` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | MAVProxy start time (mono) |
| `mavproxy_drone.mavproxy_drone_end_time` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | MAVProxy end time (mono) |
| `mavproxy_drone.mavproxy_drone_tx_pps` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | MAVLink TX rate |
| `mavproxy_drone.mavproxy_drone_rx_pps` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | MAVLink RX rate |
| `mavproxy_drone.mavproxy_drone_total_msgs_sent` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | MAVLink sent count |
| `mavproxy_drone.mavproxy_drone_total_msgs_received` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | MAVLink received count |
| `mavproxy_drone.mavproxy_drone_msg_type_counts` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | MAVLink message histogram |
| `mavproxy_drone.mavproxy_drone_heartbeat_interval_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if no heartbeat | Heartbeat interval |
| `mavproxy_drone.mavproxy_drone_heartbeat_loss_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if no heartbeat | Heartbeat loss count |
| `mavproxy_drone.mavproxy_drone_seq_gap_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | Sequence gap count |
| `mavproxy_drone.mavproxy_drone_cmd_sent_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | Commands sent count |
| `mavproxy_drone.mavproxy_drone_cmd_ack_received_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | Command ACK count |
| `mavproxy_drone.mavproxy_drone_cmd_ack_latency_avg_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | Invalid if no commands | Command ACK latency avg |
| `mavproxy_drone.mavproxy_drone_cmd_ack_latency_p95_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | Invalid if no commands | Command ACK latency p95 |
| `mavproxy_drone.mavproxy_drone_stream_rate_hz` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_schema_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | Stream rate (Hz) |
| `mavproxy_gcs.mavproxy_gcs_total_msgs_received` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `_merge_peer_data()` | GCS metrics merged | Conditional | None if GCS metrics missing | GCS total messages received |
| `mavproxy_gcs.mavproxy_gcs_seq_gap_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `_merge_peer_data()` | GCS metrics merged | Conditional | None if GCS metrics missing | GCS sequence gaps |
| `mavlink_integrity.mavlink_sysid` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_mavlink_integrity()` | MAVLink sniffing active | Conditional | None if collector unavailable | MAVLink sysid |
| `mavlink_integrity.mavlink_compid` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_mavlink_integrity()` | MAVLink sniffing active | Conditional | None if collector unavailable | MAVLink compid |
| `mavlink_integrity.mavlink_protocol_version` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_mavlink_integrity()` | MAVLink sniffing active | Conditional | None if collector unavailable | MAVLink protocol version |
| `mavlink_integrity.mavlink_packet_crc_error_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_mavlink_integrity()` | MAVLink sniffing active | Conditional | None if collector unavailable | CRC errors |
| `mavlink_integrity.mavlink_decode_error_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_mavlink_integrity()` | MAVLink sniffing active | Conditional | None if collector unavailable | Decode errors |
| `mavlink_integrity.mavlink_msg_drop_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_mavlink_integrity()` | MAVLink sniffing active | Conditional | None if collector unavailable | Message drop count |
| `mavlink_integrity.mavlink_out_of_order_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_mavlink_integrity()` | MAVLink sniffing active | Conditional | None if collector unavailable | Out-of-order count |
| `mavlink_integrity.mavlink_duplicate_count` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_mavlink_integrity()` | MAVLink sniffing active | Conditional | None if collector unavailable | Duplicate count |
| `mavlink_integrity.mavlink_message_latency_avg_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | `populate_mavlink_integrity()` | MAVLink sniffing active | Conditional | None if latency invalid | MAVLink message latency avg |
| `fc_telemetry.fc_mode` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_flight_controller_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | FC mode string |
| `fc_telemetry.fc_armed_state` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_flight_controller_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | FC armed state |
| `fc_telemetry.fc_heartbeat_age_ms` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_flight_controller_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | Heartbeat staleness |
| `fc_telemetry.fc_attitude_update_rate_hz` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_flight_controller_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | Attitude rate |
| `fc_telemetry.fc_position_update_rate_hz` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_flight_controller_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | Position rate |
| `fc_telemetry.fc_battery_voltage_v` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_flight_controller_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | Battery voltage |
| `fc_telemetry.fc_battery_current_a` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_flight_controller_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | Battery current |
| `fc_telemetry.fc_battery_remaining_percent` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_flight_controller_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | Battery remaining % |
| `fc_telemetry.fc_cpu_load_percent` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_flight_controller_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | FC CPU load |
| `fc_telemetry.fc_sensor_health_flags` | [core/mavlink_collector.py](core/mavlink_collector.py) | `get_flight_controller_metrics()` | MAVLink sniffing active | Conditional | None if collector unavailable | Sensor health flags |

Control plane (M)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `control_plane.scheduler_tick_interval_ms` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `record_control_plane_metrics()` | Policy evaluation loop | Conditional | None if metrics_aggregator missing | Scheduler tick interval |
| `control_plane.scheduler_action_type` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `record_control_plane_metrics()` | Policy state change | Conditional | None if metrics_aggregator missing | Action type |
| `control_plane.scheduler_action_reason` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `record_control_plane_metrics()` | Policy state change | Conditional | None if metrics_aggregator missing | Action reason |
| `control_plane.policy_name` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `record_control_plane_metrics()` | Policy state change | Conditional | None if metrics_aggregator missing | Policy name |
| `control_plane.policy_state` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `record_control_plane_metrics()` | Policy state change | Conditional | None if metrics_aggregator missing | Policy state |
| `control_plane.policy_suite_index` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `record_control_plane_metrics()` | Policy state change | Conditional | None if metrics_aggregator missing | Suite index |
| `control_plane.policy_total_suites` | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `record_control_plane_metrics()` | Policy state change | Conditional | None if metrics_aggregator missing | Suite count |

System resources (N/O), Power & energy (P), Observability (Q), Validation (R)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `system_drone.cpu_usage_avg_percent` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `_start_background_collection()` + `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | Avg CPU usage |
| `system_drone.cpu_usage_peak_percent` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | Same as above | 2 Hz sampling | Conditional | None if no samples | Peak CPU usage |
| `system_drone.cpu_freq_mhz` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | CPU frequency |
| `system_drone.memory_rss_mb` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | RSS memory |
| `system_drone.memory_vms_mb` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | VMS memory |
| `system_drone.thread_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | Thread count |
| `system_drone.temperature_c` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | CPU temperature |
| `system_drone.uptime_s` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | System uptime |
| `system_drone.load_avg_1m` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | Load avg 1m |
| `system_drone.load_avg_5m` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | Load avg 5m |
| `system_drone.load_avg_15m` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | Load avg 15m |
| `system_gcs.*` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `_merge_peer_data()` | GCS metrics merged | Conditional | None if GCS metrics missing | GCS resource snapshot |
| `power_energy.power_sensor_type` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Power collector active | Conditional | None if backend unavailable | Power sensor backend |
| `power_energy.power_sampling_rate_hz` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Power collector active | Conditional | None if backend unavailable | Sampling rate |
| `power_energy.voltage_avg_v` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Power collector active | Conditional | None if backend unavailable | Avg voltage |
| `power_energy.current_avg_a` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Power collector active | Conditional | None if backend unavailable | Avg current |
| `power_energy.power_avg_w` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Power collector active | Conditional | None if backend unavailable | Avg power |
| `power_energy.power_peak_w` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Power collector active | Conditional | None if backend unavailable | Peak power |
| `power_energy.energy_total_j` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Power collector active | Conditional | None if backend unavailable | Total energy |
| `power_energy.energy_per_handshake_j` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Power collector active + handshake duration | Conditional | None if duration missing | Energy per handshake |
| `observability.log_sample_count` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | System sample count |
| `observability.metrics_sampling_rate_hz` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | Sampling rate |
| `observability.collection_start_time` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | Sampling start time |
| `observability.collection_end_time` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | Sampling end time |
| `observability.collection_duration_ms` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | 2 Hz sampling | Conditional | None if no samples | Sampling duration |
| `validation.expected_samples` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Observability available | Conditional | None if no samples | Expected sample count |
| `validation.collected_samples` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Observability available | Conditional | None if no samples | Collected sample count |
| `validation.lost_samples` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Observability available | Conditional | None if no samples | Lost sample count |
| `validation.success_rate_percent` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Handshake status present | Conditional | None if handshake not recorded | Suite pass rate |
| `validation.benchmark_pass_fail` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `finalize_suite()` | Handshake status present | Conditional | None if handshake not recorded | PASS/FAIL flag |
| `validation.metric_status.*` | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `_mark_metric_status()` | Any missing/invalid metric | Conditional | Empty if none | Metric status reasons |

1.2 sgcs_bench.py (GCS benchmark server)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `get_info.hostname` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `get_info` | Drone RPC | Conditional | None if request fails | GCS host name |
| `get_info.ip` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `get_info` | Drone RPC | Conditional | None if request fails | GCS IP |
| `get_info.kernel_version` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `get_info` | Drone RPC | Conditional | None if request fails | GCS OS/kernel version |
| `get_info.python_env` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `get_info` | Drone RPC | Conditional | None if request fails | Python runtime version |
| `stop_suite.mavlink_validation.*` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` | MAVLink collector stop | Conditional | None if collector unavailable | GCS validation metrics |
| `stop_suite.latency_jitter.*` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `stop_suite` | MAVLink collector stop | Conditional | None if invalid | Latency/jitter/RTT |
| `stop_suite.system_gcs.*` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `GcsSystemMetricsCollector.stop()` | Suite stop | Conditional | `{}` if sampling not started | GCS system resources |
| `stop_suite.proxy_status.*` | [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py) | `_read_proxy_status()` | Suite stop | Conditional | `{}` if status file missing | GCS proxy counters |
| `MetricsAggregator` JSON | [core/metrics_aggregator.py](core/metrics_aggregator.py) | `start_suite()` + `finalize_suite()` | start_proxy/stop_suite | Conditional | MAVLink port conflict or missing collector | GCS-side comprehensive metrics (subset) |

1.3 sdrone.py (simplified scheduler)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `echo_rx` | [sscheduler/sdrone.py](sscheduler/sdrone.py) | `UdpEchoServer.get_stats()` | After traffic completion | Conditional | 0 if no traffic | Echo RX packet count |
| `echo_tx` | [sscheduler/sdrone.py](sscheduler/sdrone.py) | `UdpEchoServer.get_stats()` | After traffic completion | Conditional | 0 if no traffic | Echo TX packet count |
| `result.status` | [sscheduler/sdrone.py](sscheduler/sdrone.py) | `run_suite()` | Suite execution | Yes | Error string on failure | Suite pass/fail state |

1.4 sgcs.py (simplified scheduler)

| Metric | File | Function | Trigger | Collected Always? | Failure Mode | Scientific Meaning |
|---|---|---|---|---|---|---|
| `traffic_stats.tx_count` | [sscheduler/sgcs.py](sscheduler/sgcs.py) | `TrafficGenerator.get_stats()` | During status RPC | Conditional | 0 if no traffic | TX packets |
| `traffic_stats.rx_count` | [sscheduler/sgcs.py](sscheduler/sgcs.py) | `TrafficGenerator.get_stats()` | During status RPC | Conditional | 0 if no traffic | RX packets |
| `traffic_stats.tx_bytes` | [sscheduler/sgcs.py](sscheduler/sgcs.py) | `TrafficGenerator.get_stats()` | During status RPC | Conditional | 0 if no traffic | TX bytes |
| `traffic_stats.rx_bytes` | [sscheduler/sgcs.py](sscheduler/sgcs.py) | `TrafficGenerator.get_stats()` | During status RPC | Conditional | 0 if no traffic | RX bytes |
| `traffic_stats.complete` | [sscheduler/sgcs.py](sscheduler/sgcs.py) | `TrafficGenerator.get_stats()` | During status RPC | Conditional | False if generator not finished | Traffic completion flag |

=====================================================
2) REQUIRED VS IMPLEMENTED GAP TABLE
=====================================================

| Policy Requirement | Implemented Metrics (code) | Missing Metrics / Gaps | Where to Modify |
|---|---|---|---|
| A) Highest/lowest power-consuming suite | `power_energy.energy_total_j`, `power_energy.power_avg_w` from [core/metrics_aggregator.py](core/metrics_aggregator.py) | None in code; ranking requires post-processing | None (analysis layer) |
| B) Highest/lowest latency suite | `latency_jitter.one_way_latency_avg_ms/p95` from [core/mavlink_collector.py](core/mavlink_collector.py) | Conditional on SYSTEM_TIME/timestamped MAVLink; no fallback latency source | [core/mavlink_collector.py](core/mavlink_collector.py) for alternative timestamping or explicit invalid logging |
| C) Highest/lowest blackout suite | `rekey.rekey_blackout_duration_ms` from [core/async_proxy.py](core/async_proxy.py) | Only populated on rekey; suite rotation in sdrone_bench does not trigger rekey | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) or [core/policy_engine.py](core/policy_engine.py) to trigger rekey per suite |
| D) Highest/lowest handshake time | `handshake.handshake_total_duration_ms`, JSONL `handshake_ms` | None | None |
| E) Per-KEM / Per-SIG / Per-AEAD breakdown | `crypto_identity.*` + `crypto_primitives.*` + `data_plane.aead_*` | No per-AEAD energy or latency attribution beyond suite-level | [core/metrics_aggregator.py](core/metrics_aggregator.py) (derive per-AEAD energy/latency) |
| F) Front-end ISD level comparisons | None found in code | Entire metric family missing | Add collector + schema fields in [core/metrics_schema.py](core/metrics_schema.py) and write in schedulers |
| G) AEAD family impact on latency + energy | `crypto_identity.aead_algorithm`, `latency_jitter.*`, `power_energy.*` | No explicit AEAD family tag beyond algorithm token | None (post-processing) |
| H) Rekey impact and blackout impact | `rekey.*` from proxy counters | No explicit rekey trigger in sdrone_bench; rekey impact often empty | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) or [core/control_tcp.py](core/control_tcp.py) to exercise rekey |
| I) Goodput vs wire rate vs packet loss | `data_plane.goodput_mbps`, `data_plane.wire_rate_mbps`, `data_plane.packet_loss_ratio` | Offered load / target rate not stored in comprehensive metrics | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) to record `rate_mbps` into control_plane or context |
| J) MAVLink channel health vs crypto suite | `mavproxy_*`, `mavlink_integrity.*`, `latency_jitter.*` | Conditional on MAVLink collector availability | None (availability issue) |
| K) Energy per MB transferred | Not collected | Missing derived metric | [core/metrics_aggregator.py](core/metrics_aggregator.py) to compute from `energy_total_j` and `data_plane.bytes_*` |
| L) Clock sync accuracy and drift impact | `run_context.clock_offset_ms` only | No drift tracking, no uncertainty | [core/clock_sync.py](core/clock_sync.py) + [core/metrics_schema.py](core/metrics_schema.py) |
| M) Traffic sparsity impact on blackout measurement | None | No explicit “traffic sparse” indicator for blackout bias | [core/async_proxy.py](core/async_proxy.py) to log blackout end cause and packet counts |

=====================================================
3) BLACKOUT MEASUREMENT AUDIT
=====================================================

Definition in code (no assumptions)
- Blackout start: set when `_launch_rekey()` marks `_rekey_blackout_start_mono` in [core/async_proxy.py](core/async_proxy.py).
- Blackout end: set to first observed packet time after rekey start (any plaintext/encrypted send/receive) by updating `_rekey_blackout_end_mono` in [core/async_proxy.py](core/async_proxy.py).
- Final blackout duration: computed in `_finalize_rekey()` as either `(blackout_end - blackout_start)` or `(rekey_end - blackout_start)` if no post-rekey packet was observed in [core/async_proxy.py](core/async_proxy.py).

Traffic dependence and bias (code-based)
- Blackout end is traffic-coupled; if traffic is sparse, blackout can extend until the next packet. If no packet occurs, blackout duration equals rekey duration.
- No explicit marker is emitted for “end due to traffic” vs “end due to rekey completion.”

Collected metrics
- `rekey.rekey_blackout_duration_ms` in comprehensive metrics (via proxy counters) in [core/metrics_aggregator.py](core/metrics_aggregator.py).
- `proxy_status.counters.rekey_blackout_duration_ms` in proxy status (GCS side) in [core/async_proxy.py](core/async_proxy.py).

=====================================================
4) LATENCY + MAVLINK MEASUREMENT AUDIT
=====================================================

Latency sourcing (one-way)
- Uses `time_usec` when present and plausible; otherwise uses `time_boot_ms` + SYSTEM_TIME offset from `SYSTEM_TIME` messages in [core/mavlink_collector.py](core/mavlink_collector.py).
- No Chronos offset is applied to MAVLink latency calculations; chronos only updates run context in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py).

Invalid conditions (explicit)
- `latency_invalid_reason = "missing_system_time_reference"` when no SYSTEM_TIME mapping exists.
- `latency_invalid_reason = "no_timestamped_messages"` when no timestamped MAVLink messages were observed.
- `rtt_invalid_reason = "no_command_sent"` or `"no_command_ack"` when COMMAND_LONG/ACK tracking is absent.

Collected metrics
- One-way latency avg/p95, jitter avg/p95, sample counts in [core/mavlink_collector.py](core/mavlink_collector.py), merged by [core/metrics_aggregator.py](core/metrics_aggregator.py).
- MAVProxy metrics (tx/rx rates, heartbeats, seq gaps) in [core/mavlink_collector.py](core/mavlink_collector.py).
- MAVLink integrity (CRC, decode, drop, duplicates, out-of-order) in [core/mavlink_collector.py](core/mavlink_collector.py).

=====================================================
5) POWER + ENERGY MEASUREMENT AUDIT
=====================================================

Power collection path (comprehensive metrics)
- Power sampling is started in `MetricsAggregator.start_suite()` (drone role only) and stopped in `finalize_suite()` in [core/metrics_aggregator.py](core/metrics_aggregator.py).
- Power backend selected in [core/metrics_collectors.py](core/metrics_collectors.py) (`PowerCollector` with INA219 or RPi5 hwmon). If backend unavailable, metrics are set to None.

Collected power metrics
- `power_energy.power_avg_w`, `power_energy.power_peak_w`, `power_energy.energy_total_j`, `power_energy.voltage_avg_v`, `power_energy.current_avg_a`, `power_energy.power_sensor_type`, `power_energy.power_sampling_rate_hz`, `power_energy.energy_per_handshake_j` in [core/metrics_aggregator.py](core/metrics_aggregator.py).

Failure modes
- If backend is `none` or sampling fails, `power_energy.*` is nulled and `validation.metric_status` is marked in [core/metrics_aggregator.py](core/metrics_aggregator.py).

=====================================================
6) HANDSHAKE + REKEY MEASUREMENT AUDIT
=====================================================

Handshake collection
- Handshake primitive timings and artifact sizes are measured in [core/handshake.py](core/handshake.py) and embedded in `handshake_metrics` passed back to [core/async_proxy.py](core/async_proxy.py).
- The proxy status writer exports `handshake_metrics` and flattened `part_b_metrics` in [core/async_proxy.py](core/async_proxy.py).
- Drone benchmark (`sdrone_bench.py`) reads `handshake_metrics` from status file and writes JSONL fields and `crypto_primitives.*` in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) and [core/metrics_aggregator.py](core/metrics_aggregator.py).

Rekey collection
- Rekey durations, interval, blackout duration, and trigger reason are tracked in [core/async_proxy.py](core/async_proxy.py) and mapped to `rekey.*` in [core/metrics_aggregator.py](core/metrics_aggregator.py).
- No scheduler in this audit explicitly triggers rekey per suite; rekey metrics remain unset unless in-band control triggers or sequence overflow occurs.

=====================================================
7) FINAL GAP SUMMARY WITH CODE POINTERS
=====================================================

Missing or conditional metrics that block policy proofs
- Energy per MB: not collected; add derivation in [core/metrics_aggregator.py](core/metrics_aggregator.py) using `power_energy.energy_total_j` and `data_plane.bytes_sent/received`.
- Clock drift/accuracy: only one offset stored; add drift metrics in [core/clock_sync.py](core/clock_sync.py) and extend schema in [core/metrics_schema.py](core/metrics_schema.py).
- Front-end ISD metrics: no collector or schema fields exist; must be added in [core/metrics_schema.py](core/metrics_schema.py) and set by schedulers.
- Blackout bias tagging: no indicator of “end due to traffic vs rekey completion”; add explicit cause and packet counters in [core/async_proxy.py](core/async_proxy.py).
- Offered load (target rate) absent from comprehensive metrics; add in [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) into `control_plane` or `run_context`.

Conditional metrics that can be NULL today
- MAVLink latency/jitter: NULL when no SYSTEM_TIME/timestamped messages in [core/mavlink_collector.py](core/mavlink_collector.py).
- Power metrics: NULL when power backend unavailable in [core/metrics_collectors.py](core/metrics_collectors.py).
- Data plane metrics: NULL when proxy status file is missing or counters absent in [core/async_proxy.py](core/async_proxy.py).
- GCS system metrics: NULL when `GcsSystemMetricsCollector` not started or stop_suite fails in [sscheduler/sgcs_bench.py](sscheduler/sgcs_bench.py).

Proxy, MAVLink, and scheduler touchpoints for remediation
- Proxy counters and blackout handling: [core/async_proxy.py](core/async_proxy.py)
- MAVLink latency validity and timestamps: [core/mavlink_collector.py](core/mavlink_collector.py)
- Scheduler injection of rate/traffic metadata: [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py)
- Schema extensions for new policy proofs: [core/metrics_schema.py](core/metrics_schema.py)

