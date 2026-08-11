# PQC Suite-Wise Benchmark Parameter Specification

## Document Metadata
- **Version**: 1.0
- **Date**: 2026-01-12
- **Scope**: Suite-wise end-to-end benchmark parameters
- **Pipeline**: MAVProxy (Drone) → secure-tunnel → secure-tunnel → MAVProxy (GCS)

---

## EXECUTIVE SUMMARY

### Current Benchmark Data Coverage

| Parameter Group | VERIFIED | PARTIALLY VERIFIED | UNVERIFIED |
|-----------------|----------|-------------------|------------|
| Suite Identity & Context | 8 | 0 | 2 |
| Cryptographic Lifecycle | 12 | 3 | 2 |
| Data Plane (AEAD) | 8 | 4 | 3 |
| System Resources | 4 | 2 | 3 |
| Power & Energy | 0 | 6 | 4 |
| Time & Causality | 4 | 2 | 2 |
| Application Layer (MAVProxy) | 0 | 2 | 6 |
| Control Plane | 3 | 2 | 2 |
| **TOTALS** | **39** | **21** | **24** |

---

## GROUP 1 — SUITE IDENTITY & CONTEXT

### VERIFIED PARAMETERS

| Parameter | Layer | Source | Method | Units | Evidence |
|-----------|-------|--------|--------|-------|----------|
| `suite_id` | Config | `core/suites.py` | Lookup | string | `get_suite(suite_id)` returns dict |
| `kem_name` | Config | `core/suites.py` | Lookup | string | `suite["kem_name"]` field |
| `sig_name` | Config | `core/suites.py` | Lookup | string | `suite["sig_name"]` field |
| `aead` | Config | `core/suites.py` | Lookup | string | `suite["aead"]` or `aead_token` field |
| `nist_level` | Config | `core/suites.py` | Lookup | L1/L3/L5 | `suite["nist_level"]` field |
| `run_id` | System | `benchmark_policy.py` | Generated | YYYYMMDD_HHMMSS | `datetime.now().strftime()` |
| `iteration` | System | `sdrone_bench.py` | Counter | int | Sequential per suite |
| `timestamp_iso` | System | `sdrone_bench.py` | Clock | ISO 8601 | `datetime.utcnow().isoformat()` |

### UNVERIFIED PARAMETERS

| Parameter | Layer | Reason | Required For |
|-----------|-------|--------|--------------|
| `git_commit_hash` | System | Not captured in benchmark | Reproducibility |
| `clock_offset_ms` | System | No NTP sync instrumented | Cross-node correlation |

---

## GROUP 2 — APPLICATION LAYER (MAVProxy)

### PARTIALLY VERIFIED PARAMETERS

| Parameter | Layer | Source | Status | Notes |
|-----------|-------|--------|--------|-------|
| `packets_sent` | App | `LatencyTracker` | One-sided | Only drone-side counted |
| `packets_received` | App | `LatencyTracker` | One-sided | Only drone-side counted |

### UNVERIFIED PARAMETERS

| Parameter | Layer | Reason | Potential Source |
|-----------|-------|--------|------------------|
| `mavlink_msg_rate_pps` | App | MAVProxy logs not parsed | pymavlink counters |
| `message_types_observed` | App | Not instrumented | MAVProxy message handler |
| `heartbeat_interval_ms` | App | Not extracted | MAVLink HEARTBEAT timing |
| `sequence_gaps_count` | App | Not tracked | MAVLink sequence field |
| `mavproxy_send_ts` | App | Not timestamped | Would need MAVProxy hook |
| `command_ack_latency_ms` | App | Not instrumented | MAVLink COMMAND_ACK timing |

---

## GROUP 3 — CONTROL PLANE (Scheduler / TCP)

### VERIFIED PARAMETERS

| Parameter | Layer | Source | Method | Units | Evidence |
|-----------|-------|--------|--------|-------|----------|
| `gcs_control_port` | Control | `CONFIG` | Config | int | `GCS_CONTROL_PORT=48080` |
| `scheduler_decision_ts` | Control | `benchmark_policy.py` | Clock | ns | `time.monotonic()` in evaluate() |
| `rekey_trigger_ts` | Control | `sdrone_bench.py` | Clock | ns | Logged before handshake |

### PARTIALLY VERIFIED PARAMETERS

| Parameter | Layer | Source | Status | Notes |
|-----------|-------|--------|--------|-------|
| `control_channel_rtt_ms` | Control | Estimated | Partial | Socket timeout, not measured |
| `start_proxy_duration_ms` | Control | `sdrone_bench.py` | GCS only | Only GCS-side measured |

### UNVERIFIED PARAMETERS

| Parameter | Layer | Reason | Potential Source |
|-----------|-------|--------|------------------|
| `scheduler_failures_count` | Control | Not tracked | Error counter in policy |
| `retry_count` | Control | Not instrumented | TCP reconnect logic |

---

## GROUP 4 — CRYPTOGRAPHIC LIFECYCLE

### VERIFIED PARAMETERS (Handshake Timing)

| Parameter | Layer | Source | Method | Units | Evidence |
|-----------|-------|--------|--------|-------|----------|
| `handshake_ms` | Crypto | `handshake.py` | `time.perf_counter_ns()` | ms | `handshake_total_ns / 1e6` |
| `kem_keygen_ms` | Crypto | `handshake.py` | `time.perf_counter_ns()` | ms | `kem_metrics["keygen_ns"]` |
| `kem_encaps_ms` | Crypto | `handshake.py` | `time.perf_counter_ns()` | ms | `kem_metrics["encap_ns"]` |
| `kem_decaps_ms` | Crypto | `handshake.py` | `time.perf_counter_ns()` | ms | `kem_metrics["decap_ns"]` |
| `sig_sign_ms` | Crypto | `handshake.py` | `time.perf_counter_ns()` | ms | `sig_metrics["sign_ns"]` |
| `sig_verify_ms` | Crypto | `handshake.py` | `time.perf_counter_ns()` | ms | `sig_metrics["verify_ns"]` |
| `kdf_derive_ns` | Crypto | `handshake.py` | `time.perf_counter_ns()` | ns | `kdf_{role}_ns` |

### VERIFIED PARAMETERS (Artifact Sizes)

| Parameter | Layer | Source | Method | Units | Evidence |
|-----------|-------|--------|--------|-------|----------|
| `pub_key_size_bytes` | Crypto | `handshake.py` | `len()` | bytes | `kem_metrics["public_key_bytes"]` |
| `ciphertext_size_bytes` | Crypto | `handshake.py` | `len()` | bytes | `kem_metrics["ciphertext_bytes"]` |
| `sig_size_bytes` | Crypto | `handshake.py` | `len()` | bytes | `sig_metrics["signature_bytes"]` |
| `shared_secret_size_bytes` | Crypto | `handshake.py` | `len()` | bytes | `kem_metrics["shared_secret_bytes"]` |
| `server_hello_bytes` | Crypto | `handshake.py` | `len()` | bytes | `artifacts["server_hello_bytes"]` |

### PARTIALLY VERIFIED PARAMETERS

| Parameter | Layer | Source | Status | Notes |
|-----------|-------|--------|--------|-------|
| `rekey_ms` | Crypto | `async_proxy.py` | Captured | Via rekey handler |
| `rekey_blackout_ms` | Crypto | `suite_bench_drone.py` | Framework only | Not in main scheduler |
| `handshake_wall_start_ns` | Crypto | `handshake.py` | Available | `time.time_ns()` |

### UNVERIFIED PARAMETERS

| Parameter | Layer | Reason | Potential Source |
|-----------|-------|--------|------------------|
| `hkdf_time_ns` | Crypto | Embedded in derive_transport_keys | Split instrumentation |
| `transcript_hash_time_ns` | Crypto | Not isolated | Would need added timers |

---

## GROUP 5 — DATA PLANE (SECURE TUNNEL / AEAD)

### VERIFIED PARAMETERS

| Parameter | Layer | Source | Method | Units | Evidence |
|-----------|-------|--------|--------|-------|----------|
| `ptx_in` | Tunnel | `async_proxy.py` | Counter | packets | `counters.ptx_in` |
| `ptx_out` | Tunnel | `async_proxy.py` | Counter | packets | `counters.ptx_out` |
| `enc_in` | Tunnel | `async_proxy.py` | Counter | packets | `counters.enc_in` |
| `enc_out` | Tunnel | `async_proxy.py` | Counter | packets | `counters.enc_out` |
| `drop_replay` | Tunnel | `async_proxy.py` | Counter | packets | `counters.drop_replay` |
| `drop_auth` | Tunnel | `async_proxy.py` | Counter | packets | `counters.drop_auth` |
| `drop_header` | Tunnel | `async_proxy.py` | Counter | packets | `counters.drop_header` |
| `aead_encrypt_ns` | Tunnel | `async_proxy.py` | `time.perf_counter_ns()` | ns | `primitive_metrics["aead_encrypt"]` |

### PARTIALLY VERIFIED PARAMETERS

| Parameter | Layer | Source | Status | Notes |
|-----------|-------|--------|--------|-------|
| `aead_decrypt_avg_ms` | Tunnel | `async_proxy.py` | Computed | `total_ns / count` |
| `total_in_bytes` | Tunnel | `async_proxy.py` | Partial | Per-primitive, not global |
| `total_out_bytes` | Tunnel | `async_proxy.py` | Partial | Per-primitive, not global |
| `queue_depth` | Tunnel | Not instrumented | N/A | Would need selector tracking |

### UNVERIFIED PARAMETERS

| Parameter | Layer | Reason | Potential Source |
|-----------|-------|--------|------------------|
| `throughput_mbps` | Tunnel | **NOT COMPUTED** | `(enc_out * avg_pkt_size * 8) / duration_s / 1e6` |
| `latency_ms` | Tunnel | **NOT INSTRUMENTED** | Requires echo/timestamp protocol |
| `goodput_vs_wire_ratio` | Tunnel | Not computed | `ptx_out / enc_out` ratio |

### CRITICAL GAP: Throughput Calculation

**Current State**: `throughput_mbps = 0.0` (hardcoded)

**Required Instrumentation**:
```python
# In async_proxy.py or benchmark collector:
def compute_throughput(enc_out: int, avg_pkt_size: int, duration_s: float) -> float:
    """Compute throughput in Mbps."""
    if duration_s <= 0:
        return 0.0
    total_bits = enc_out * avg_pkt_size * 8
    return total_bits / duration_s / 1_000_000
```

**Source**: `counters.enc_out`, `counters.total_out_bytes`, benchmark duration

### CRITICAL GAP: Latency Measurement

**Current State**: `latency_ms = 0.0` (hardcoded)

**Framework Status**: `suite_bench_drone.py` has `LatencyTracker` class with:
- `latency_mean_us`, `latency_min_us`, `latency_max_us`
- `latency_p50_us`, `latency_p95_us`, `latency_p99_us`

**Problem**: Framework exists but is not connected to main benchmark scheduler.

**Required Instrumentation**: Sequence-numbered probe packets with timestamps.

---

## GROUP 6 — SYSTEM & RESOURCE METRICS

### VERIFIED PARAMETERS

| Parameter | Layer | Source | Method | Units | Evidence |
|-----------|-------|--------|--------|-------|----------|
| `cpu_percent` | System | `psutil` | `cpu_percent()` | % | `suite_bench_drone.py` |
| `memory_mb` | System | `psutil` | `memory_info().rss` | MB | `suite_bench_drone.py` |
| `temp_c` | System | `/sys/class/thermal` | File read | °C | Raspberry Pi thermal zone |
| `hostname` | System | `socket.gethostname()` | Syscall | string | Not currently logged |

### PARTIALLY VERIFIED PARAMETERS

| Parameter | Layer | Source | Status | Notes |
|-----------|-------|--------|--------|-------|
| `process_cpu` | System | `psutil.Process()` | Available | Not in main benchmark |
| `process_rss_mb` | System | `psutil.Process()` | Available | In framework only |

### UNVERIFIED PARAMETERS

| Parameter | Layer | Reason | Potential Source |
|-----------|-------|--------|------------------|
| `context_switches` | System | Not instrumented | `psutil.Process().num_ctx_switches()` |
| `freq_mhz` | System | Not instrumented | `/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq` |
| `throttle_count` | System | Not instrumented | `vcgencmd get_throttled` |

---

## GROUP 7 — POWER & ENERGY (DRONE)

### PARTIALLY VERIFIED PARAMETERS

| Parameter | Layer | Source | Status | Notes |
|-----------|-------|--------|--------|-------|
| `power_mean_w` | Power | `power_monitor.py` | Framework only | INA219/Rpi5 backends |
| `power_peak_w` | Power | `power_monitor.py` | Framework only | Max sample value |
| `voltage_mean_v` | Power | `power_monitor.py` | Framework only | Bus voltage |
| `current_mean_a` | Power | `power_monitor.py` | Framework only | Shunt current |
| `energy_total_j` | Power | `power_monitor.py` | Framework only | `P_avg * duration_s` |
| `power_sample_rate_hz` | Power | `power_monitor.py` | Framework only | ~1kHz for INA219 |

**CRITICAL GAP**: Power monitoring exists but is **NOT CONNECTED** to main `sdrone_bench.py` scheduler.

### UNVERIFIED PARAMETERS

| Parameter | Layer | Reason | Potential Source |
|-----------|-------|--------|------------------|
| `power_w` (per packet) | Power | Not instrumented | Sync power samples with packet times |
| `energy_mj` (per suite) | Power | Not connected | Integrate `PowerCollector` |
| `handshake_energy_mj` | Power | Not instrumented | Window around handshake_start/end |
| `rekey_energy_mj` | Power | Not instrumented | Window around rekey_start/end |

### Power Monitor Backends Available

| Backend | Platform | Source File | Sampling Rate |
|---------|----------|-------------|---------------|
| `Ina219PowerMonitor` | Pi 4 + INA219 | `power_monitor.py` | 1000 Hz |
| `Rpi5PowerMonitor` | Pi 5 hwmon | `power_monitor.py` | 100 Hz |
| `Rpi5PmicPowerMonitor` | Pi 5 vcgencmd | `power_monitor.py` | 10 Hz |

---

## GROUP 8 — TIME & CAUSALITY

### VERIFIED PARAMETERS

| Parameter | Layer | Source | Method | Units | Evidence |
|-----------|-------|--------|--------|-------|----------|
| `handshake_wall_start_ns` | Time | `handshake.py` | `time.time_ns()` | ns | Wall clock |
| `handshake_wall_end_ns` | Time | `handshake.py` | `time.time_ns()` | ns | Wall clock |
| `handshake_perf_start_ns` | Time | `handshake.py` | `time.perf_counter_ns()` | ns | Monotonic |
| `handshake_total_ns` | Time | `handshake.py` | Difference | ns | `perf_end - perf_start` |

### PARTIALLY VERIFIED PARAMETERS

| Parameter | Layer | Source | Status | Notes |
|-----------|-------|--------|--------|-------|
| `ts_ns` (status file) | Time | `async_proxy.py` | Written | In periodic status updates |
| `monotonic_to_wall_offset` | Time | Computable | Not stored | `time.time_ns() - time.perf_counter_ns()` |

### UNVERIFIED PARAMETERS

| Parameter | Layer | Reason | Potential Source |
|-----------|-------|--------|------------------|
| `clock_drift_during_run_us` | Time | Not measured | Compare start/end offsets |
| `cross_node_correlation` | Time | No NTP instrumented | PTP or GPS time sync |

---

## MISSING INSTRUMENTATION SUMMARY

### CRITICAL (Required for Complete Benchmark)

| Parameter | Current Value | Required Action |
|-----------|---------------|-----------------|
| `throughput_mbps` | 0.0 | Compute from `enc_out * avg_size / duration` |
| `latency_ms` | 0.0 | Integrate `LatencyTracker` or timestamp probes |
| `power_w` | 0.0 | Connect `PowerCollector` to main scheduler |
| `energy_mj` | 0.0 | Integrate `power_monitor.py` capture |

### RECOMMENDED (For Complete Analysis)

| Parameter | Priority | Effort |
|-----------|----------|--------|
| Per-packet power correlation | Medium | High |
| MAVLink message rate | Medium | Medium |
| Cross-node timestamp sync | Low | High |
| Git commit hash logging | Low | Low |
| Context switch counting | Low | Low |

---

## EVIDENCE LOCATIONS

### Primary Source Files

| File | Parameters Provided |
|------|---------------------|
| `core/handshake.py` | All cryptographic timing, artifact sizes |
| `core/async_proxy.py` | Packet counters, drop reasons, AEAD timing |
| `core/aead.py` | Nonce structure, replay window |
| `core/power_monitor.py` | Power/energy (framework) |
| `sscheduler/sdrone_bench.py` | Benchmark orchestration |
| `sscheduler/benchmark_policy.py` | Suite cycling policy |
| `suite_benchmarks/framework/suite_bench_drone.py` | Extended metrics (framework) |

### Status Files

| File | Contents |
|------|----------|
| `logs/benchmarks/drone_status.json` | Runtime handshake metrics |
| `logs/benchmarks/benchmark_results_*.json` | Final consolidated results |

### Configuration Files

| File | Purpose |
|------|---------|
| `settings.json` | Runtime config (ports, hosts, intervals) |
| `core/suites.py` | Suite definitions, NIST levels |

---

## PARAMETER COLLECTION LIFECYCLE

### Per-Suite Lifecycle

```
1. SUITE START
   ├── Record: suite_id, kem_name, sig_name, aead, nist_level, iteration
   ├── Record: run_id, timestamp_iso
   └── Start: PowerCollector.start_collection()

2. HANDSHAKE
   ├── Record: handshake_wall_start_ns, handshake_perf_start_ns
   ├── Execute: TCP connect, ServerHello, client_encapsulate, derive_keys
   ├── Measure: kem_keygen_ns, kem_encaps_ns, kem_decaps_ns
   ├── Measure: sig_sign_ns, sig_verify_ns
   ├── Measure: pub_key_size_bytes, ciphertext_size_bytes, sig_size_bytes
   └── Record: handshake_wall_end_ns, handshake_total_ns

3. DATA PLANE (10 seconds)
   ├── Count: ptx_in, ptx_out, enc_in, enc_out
   ├── Count: drop_replay, drop_auth, drop_header
   ├── Measure: aead_encrypt_ns, aead_decrypt_ns per packet
   ├── Measure: latency_samples (if instrumented)
   └── Sample: power_w, voltage_v, current_a (if connected)

4. SUITE STOP
   ├── Stop: PowerCollector.stop_collection()
   ├── Compute: throughput_mbps, latency_mean_us, power_mean_w, energy_total_j
   ├── Capture: cpu_percent, memory_mb, temp_c
   └── Persist: benchmark_results_*.json

5. NEXT SUITE → Repeat from step 1
```

### Rekey Event Lifecycle

```
1. REKEY TRIGGER
   ├── Record: rekey_start_ns, blackout_start_ns
   └── Send: control_tcp "prepare_rekey"

2. NEW HANDSHAKE
   ├── Execute: Stop old proxy, start new proxy
   ├── Measure: All handshake parameters (same as initial)
   └── Record: rekey_end_ns, blackout_end_ns

3. REKEY COMPLETE
   ├── Compute: rekey_ms = rekey_end - rekey_start
   ├── Compute: blackout_ms = blackout_end - blackout_start
   └── Increment: rekeys_ok or rekeys_fail
```

---

## RECOMMENDATIONS FOR COMPLETE INSTRUMENTATION

### Immediate (Required for IEEE Report)

1. **Throughput**: Add to `sdrone_bench.py`:
   ```python
   throughput_mbps = (counters.enc_out * avg_packet_bytes * 8) / (duration_s * 1e6)
   ```

2. **Latency**: Integrate `LatencyTracker` from framework:
   - Send timestamped probe packets
   - Measure RTT for each probe
   - Report min/mean/max/p50/p95/p99

3. **Power**: Connect `PowerCollector` to main scheduler:
   - Call `start_collection()` at suite start
   - Call `stop_collection()` at suite end
   - Compute energy = ∫ power dt

### Medium-Term (For Complete Analysis)

4. **MAVLink Metrics**: Parse MAVProxy logs for message rates

5. **Cross-Node Sync**: Add NTP offset logging at suite boundaries

6. **Per-Primitive Energy**: Window power samples around each operation

---

## APPENDIX: Current Benchmark Results Schema

```json
{
  "suite_id": "cs-mlkem768-aesgcm-mldsa65",
  "iteration": 0,
  "nist_level": "L3",
  "kem_name": "ML-KEM-768",
  "sig_name": "ML-DSA-65",
  "aead": "AES-256-GCM",
  
  "handshake_ms": 15.2,
  "kem_keygen_ms": 0.0,
  "kem_encaps_ms": 0.28,
  "kem_decaps_ms": 0.0,
  "sig_sign_ms": 0.0,
  "sig_verify_ms": 0.95,
  
  "pub_key_size_bytes": 1184,
  "ciphertext_size_bytes": 1088,
  "sig_size_bytes": 3309,
  
  "throughput_mbps": 0.0,      // ❌ NOT COMPUTED
  "latency_ms": 0.0,           // ❌ NOT INSTRUMENTED
  "power_w": 0.0,              // ❌ NOT CONNECTED
  "energy_mj": 0.0,            // ❌ NOT CONNECTED
  
  "success": true,
  "error_message": ""
}
```

---

*End of Parameter Specification Document*
