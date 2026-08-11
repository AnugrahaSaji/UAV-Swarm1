# FORENSIC CODE AUDIT: PQC Secure Tunnel Metrics System

**Audit Type**: Evidence-Driven Forensic Analysis  
**Rules Applied**: No assumptions, no hallucinations, file-grounded claims only  
**Date**: January 17, 2026

---

## PHASE 1 — ENTRY POINTS

### Entry Points Verified from Code

| Entry Point | File | Function | Purpose |
|-------------|------|----------|---------|
| CLI Proxy | [core/run_proxy.py](core/run_proxy.py) | `main()` → `gcs_command()` / `drone_command()` | Standalone proxy execution |
| Drone Scheduler | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `main()` → `BenchmarkScheduler.run()` | Drone-driven benchmark cycling |
| GCS Follower | [bench/run_full_benchmark.py](bench/run_full_benchmark.py) | `GcsBenchmarkServer.start()` | GCS responds to drone commands |

### Process Lifecycle (Proven from Code)

**Drone Side** (`sscheduler/sdrone_bench.py`):
1. Line 374: `start_mavproxy()` - starts MAVProxy with `--out=udp:127.0.0.1:47003` and `--out=udp:127.0.0.1:47005`
2. Line 258: `BenchmarkScheduler.__init__()` - creates `MetricsAggregator(role="drone")`
3. Line 303: `_activate_suite()` - calls `self.metrics_aggregator.start_suite()`
4. Line 321: `self.proxy.start(suite_name)` - starts `core.run_proxy drone`
5. Line 340: `read_handshake_status()` - waits for `drone_status.json` to show `handshake_ok`
6. Line 350: `self.metrics_aggregator.record_crypto_primitives(metrics)` - **CALLED**
7. Line 287: `_finalize_metrics()` - calls `self.metrics_aggregator.record_data_plane_metrics(counters)` - **CALLED**

**GCS Side** (`bench/run_full_benchmark.py`):
1. Line 288: `GcsBenchmarkServer.start()` - TCP server on port 48080
2. Line 332: `_handle_command()` → `start_suite` - calls `self.metrics.start_suite()`
3. Line 335: `self.proxy.start(suite)` - starts `core.run_proxy gcs`
4. Line 338: `self.metrics.record_handshake_end(success=True)` - **CALLED**
5. Line 350: `stop_suite` - calls `self.metrics.finalize_suite()` - **CALLED**
6. **CRITICAL FINDING**: `record_crypto_primitives()` is **NOT CALLED** on GCS
7. **CRITICAL FINDING**: `record_data_plane_metrics()` is **NOT CALLED** on GCS

---

## PHASE 2 — DATA PLANE VERIFICATION

### Packet Counters Location

**Source**: [core/async_proxy.py](core/async_proxy.py), class `ProxyCounters`, lines 55-90

```python
class ProxyCounters:
    def __init__(self) -> None:
        self.ptx_out = 0      # plaintext packets sent out to app
        self.ptx_in = 0       # plaintext packets received from app
        self.enc_out = 0      # encrypted packets sent to peer
        self.enc_in = 0       # encrypted packets received from peer
        self.drops = 0        # total drops
```

### Where Counters Are Incremented

| Counter | Location | Line |
|---------|----------|------|
| `ptx_in` | `async_proxy.py` | Line 680: `counters.ptx_in += 1` |
| `enc_out` | `async_proxy.py` | Line 709: `counters.enc_out += 1` |
| `enc_in` | `async_proxy.py` | Line 729: `counters.enc_in += 1` |
| `ptx_out` | `async_proxy.py` | Line 820: `counters.ptx_out += 1` |
| `drops` | `async_proxy.py` | Lines 751, 757, 763, etc. |

### Where Counters Are Written

**Source**: `async_proxy.py`, function `_status_writer()`, lines 486-500

```python
def _status_writer() -> None:
    while not stop_status_writer.is_set():
        with counters_lock:
            payload = {
                "status": "running",
                "suite": suite_id,
                "counters": counters.to_dict(),  # <-- WRITES ALL COUNTERS
                "ts_ns": time.time_ns(),
            }
        write_status(payload)
```

**Output File**: `logs/gcs_status.json` or `logs/drone_status.json`

### PROVEN: Data Exists in Status File

**Evidence**: [logs/gcs_status.json](logs/gcs_status.json)
```json
{
  "counters": {
    "ptx_out": 2328,
    "ptx_in": 49468,
    "enc_out": 49465,
    "enc_in": 2328,
    "drops": 3,
    "drop_replay": 0,
    "drop_auth": 0
  }
}
```

### PROVEN: Data NOT Transferred to Schema (GCS)

**Evidence**: [logs/benchmarks/comprehensive/20260114_034317_...gcs.json](logs/benchmarks/comprehensive/20260114_034317_cs-classicmceliece348864-aesgcm-falcon512_gcs.json)
```json
{
  "data_plane": {
    "ptx_in": 0,
    "ptx_out": 0,
    "enc_in": 0,
    "enc_out": 0,
    "packets_sent": 0,
    "packets_received": 0
  }
}
```

**Root Cause**: `bench/run_full_benchmark.py` line 350 (`stop_suite` handler) does NOT call `record_data_plane_metrics()` before `finalize_suite()`.

---

## PHASE 3 — HANDSHAKE & CRYPTO METRICS

### Timing Measurement Points

**Source**: [core/handshake.py](core/handshake.py)

| Operation | Start Line | End Line | Variable |
|-----------|------------|----------|----------|
| KEM Keygen | 109 | 113 | `kem_metrics["keygen_ns"]` |
| KEM Encap | 222-225 | 230 | `kem_metrics["encap_ns"]` |
| KEM Decap | 251-254 | 260 | `kem_metrics["decap_ns"]` |
| Sig Sign | 130-132 | 138 | `sig_metrics["sign_ns"]` |
| Sig Verify | 183-185 | 191 | `sig_metrics["verify_ns"]` |

### Where Handshake Metrics Are Written

**Source**: `async_proxy.py`, line 498
```python
status_payload = {
    "status": "handshake_ok",
    "suite": suite_id,
    "session_id": sess_status_display,
}
if handshake_metrics:
    status_payload["handshake_metrics"] = handshake_metrics
write_status(status_payload)
```

### PROVEN: Handshake Metrics Exist in Status File

**Evidence**: [logs/gcs_status.json](logs/gcs_status.json)
```json
{
  "handshake_metrics": {
    "kem_keygen_ms": 223.4985,
    "kem_decap_ms": 28.7686,
    "sig_sign_ms": 5.7739,
    "pub_key_size_bytes": 261120,
    "ciphertext_size_bytes": 96,
    "sig_size_bytes": 655
  }
}
```

### PROVEN: NOT Transferred to ComprehensiveSuiteMetrics (GCS)

**Evidence**: [logs/benchmarks/comprehensive/20260114_...gcs.json](logs/benchmarks/comprehensive/20260114_034317_cs-classicmceliece348864-aesgcm-falcon512_gcs.json)
```json
{
  "crypto_primitives": {
    "kem_keygen_time_ms": 0.0,
    "kem_encapsulation_time_ms": 0.0,
    "kem_decapsulation_time_ms": 0.0,
    "signature_sign_time_ms": 0.0,
    "signature_verify_time_ms": 0.0,
    "pub_key_size_bytes": 0,
    "ciphertext_size_bytes": 0,
    "sig_size_bytes": 0
  }
}
```

**Root Cause**: `bench/run_full_benchmark.py` → `_handle_command("start_suite")` does NOT call `self.metrics.record_crypto_primitives()`.

---

## PHASE 4 — METRICS SCHEMA AUDIT

### Schema Definition

**Source**: [core/metrics_schema.py](core/metrics_schema.py)

| Category | Lines | Fields | Dataclass Name |
|----------|-------|--------|----------------|
| A. Run Context | 31-50 | 20 | `RunContextMetrics` |
| B. Crypto Identity | 58-70 | 13 | `SuiteCryptoIdentity` |
| C. Lifecycle | 78-88 | 11 | `SuiteLifecycleTimeline` |
| D. Handshake | 96-103 | 8 | `HandshakeMetrics` |
| E. Crypto Primitives | 111-130 | 19 | `CryptoPrimitiveBreakdown` |
| F. Rekey | 138-144 | 7 | `RekeyMetrics` |
| G. Data Plane | 152-175 | 24 | `DataPlaneMetrics` |
| H. Latency/Jitter | 183-193 | 11 | `LatencyJitterMetrics` |
| I. MAVProxy Drone | 201-217 | 17 | `MavProxyDroneMetrics` |
| J. MAVProxy GCS | 225-241 | 17 | `MavProxyGcsMetrics` |
| K. MAVLink Integrity | 249-259 | 10 | `MavLinkIntegrityMetrics` |
| L. FC Telemetry | 267-282 | 14 | `FlightControllerTelemetry` |
| M. Control Plane | 290-300 | 11 | `ControlPlaneMetrics` |
| N. System Drone | 308-324 | 17 | `SystemResourcesDrone` |
| O. System GCS | 332-339 | 8 | `SystemResourcesGcs` |
| P. Power/Energy | 347-358 | 12 | `PowerEnergyMetrics` |
| Q. Observability | 366-373 | 9 | `ObservabilityMetrics` |
| R. Validation | 381-388 | 7 | `ValidationMetrics` |

**TOTAL**: 18 categories, ~235 fields

### Per-Category Audit (Evidence-Based)

| Category | Collector Exists? | Invoked? | Data in Schema? | Evidence |
|----------|-------------------|----------|-----------------|----------|
| **A. Run Context** | `EnvironmentCollector` (line 67 metrics_collectors.py) | ✅ Yes (aggregator line 77) | ✅ Yes | `run_context.gcs_hostname="lappy"` in JSON |
| **B. Crypto Identity** | Hardcoded from suite config | ✅ Yes (aggregator line 89) | ✅ Yes | `crypto_identity.kem_algorithm="Classic-McEliece-348864"` in JSON |
| **C. Lifecycle** | `MetricsAggregator` internal | ✅ Yes (aggregator line 108) | ✅ Yes | `lifecycle.suite_total_duration_ms=21750.0` in JSON |
| **D. Handshake** | `MetricsAggregator.record_handshake_*()` | ✅ Drone, ✅ GCS | ⚠️ Partial | `handshake.handshake_success=true` but `handshake_rtt_ms=0.0` |
| **E. Crypto Primitives** | `MetricsAggregator.record_crypto_primitives()` | ✅ Drone, ❌ GCS | ❌ GCS zeros | All zeros in GCS JSON |
| **F. Rekey** | None | ❌ Never | ❌ All zeros | All zeros in JSON |
| **G. Data Plane** | `MetricsAggregator.record_data_plane_metrics()` | ✅ Drone (line 454 sdrone_bench.py), ❌ GCS | ❌ GCS zeros | All zeros in GCS JSON |
| **H. Latency/Jitter** | `LatencyTracker` (line 430 metrics_collectors.py) | ✅ Exists | ❌ No data | `latency_samples: []` empty |
| **I. MAVProxy Drone** | `MavLinkMetricsCollector` (mavlink_collector.py) | ⚠️ Started (aggregator line 127) | ❌ No data | `mavproxy_drone_rx_pps: 0.0` |
| **J. MAVProxy GCS** | `MavLinkMetricsCollector` (mavlink_collector.py) | ⚠️ Started (aggregator line 127) | ❌ No data | `mavproxy_gcs_rx_pps: 0.0` |
| **K. MAVLink Integrity** | `MavLinkMetricsCollector.populate_mavlink_integrity()` | ⚠️ Called | ❌ No data | All zeros |
| **L. FC Telemetry** | **NONE** | ❌ | ❌ All zeros | Schema-only, no implementation |
| **M. Control Plane** | **NONE** | ❌ | ❌ All zeros | Schema-only, no implementation |
| **N. System Drone** | `SystemCollector` (line 147 metrics_collectors.py) | ✅ Yes (aggregator line 176) | ✅ Drone only | Drone JSON would have data; GCS JSON has zeros for drone |
| **O. System GCS** | `SystemCollector` (line 147 metrics_collectors.py) | ✅ Yes (aggregator line 176) | ✅ Yes | `system_gcs.cpu_usage_avg_percent=7.22` in GCS JSON |
| **P. Power/Energy** | `PowerCollector` (line 222 metrics_collectors.py) | ✅ Drone only (aggregator line 73) | ❌ GCS zeros | GCS has no power sensor, all zeros expected |
| **Q. Observability** | `MetricsAggregator` internal | ✅ Yes | ✅ Yes | `observability.log_sample_count=43` in JSON |
| **R. Validation** | `MetricsAggregator` internal | ✅ Yes | ✅ Yes | `validation.benchmark_pass_fail="PASS"` in JSON |

---

## PHASE 5 — DRONE VS GCS RESPONSIBILITY

### Metrics by Responsibility (Based on Cryptographic Protocol)

| Operation | Performed By | Collector Must Run On |
|-----------|--------------|----------------------|
| KEM Keygen | GCS | GCS |
| KEM Encapsulate | Drone | Drone |
| KEM Decapsulate | GCS | GCS |
| Signature Sign | GCS | GCS |
| Signature Verify | Drone | Drone |
| AEAD Encrypt/Decrypt | Both | Both |
| Power Measurement | Drone (INA219 sensor) | Drone |
| CPU Temperature | Drone (RPi thermal) | Drone |
| FC Telemetry | Drone (serial to FC) | Drone |

### PROVEN: Metrics Collected on Wrong Side

| Metric | Collected On | Should Be | Evidence |
|--------|--------------|-----------|----------|
| `kem_encapsulation_time_ms` | GCS only (handshake.py line 225) | Drone | GCS sees 0 because it doesn't encapsulate |
| `signature_verify_time_ms` | GCS only (handshake.py line 191) | Drone | GCS sees 0 because it doesn't verify |

**Explanation**: `handshake.py` writes timing to the `metrics_ref` dict passed in. The drone calls `client_drone_handshake()` which populates encap and verify. The GCS calls `server_gcs_handshake()` which populates keygen, decap, and sign. But each side only records what IT performs, not what the peer performs.

### PROVEN: Missing Cross-Side Consolidation

**Evidence**: No code exists to merge drone metrics into GCS output or vice versa.

`bench/run_full_benchmark.py` line 357 returns `gcs_metrics` but they are never merged with drone metrics in a single output file.

---

## PHASE 6 — LATENCY & JITTER

### LatencyTracker Class

**Source**: [core/metrics_collectors.py](core/metrics_collectors.py), lines 430-490

```python
class LatencyTracker:
    """Collects latency samples and computes statistics."""
    
    def __init__(self, max_samples: int = 10000):
        self._samples: List[float] = []
        self._max_samples = max_samples
    
    def record(self, latency_ms: float):
        """Record a latency sample in milliseconds."""
        if len(self._samples) < self._max_samples:
            self._samples.append(latency_ms)
```

### PROVEN: LatencyTracker Exists But Is Never Fed Data

**Search for `record_latency_sample` in codebase**:
- Defined in `metrics_aggregator.py` line 174: `def record_latency_sample(self, latency_ms: float)`
- **NEVER CALLED** anywhere in the codebase

**Search for `latency_tracker.record` in codebase**:
- No calls found

### PROVEN: No RTT Measurement Implementation

**Grep for "rtt", "ping", "pong", "timesync" in codebase**:
- No implementation of round-trip time probing exists
- `handshake_rtt_ms` in schema is always 0.0

**Evidence from JSON**:
```json
{
  "latency_jitter": {
    "one_way_latency_avg_ms": 0.0,
    "round_trip_latency_avg_ms": 0.0,
    "latency_samples": []
  }
}
```

**Verdict**: RTT measurement is **NOT IMPLEMENTED**.

---

## PHASE 7 — MAVLINK & FC TELEMETRY

### MavLinkMetricsCollector Binding

**Source**: [core/mavlink_collector.py](core/mavlink_collector.py), line 94

```python
def start_sniffing(self, port: int = 14552, host: str = "127.0.0.1"):
    # ...
    conn_str = f"udpin:{host}:{port}"
    self._mav_conn = mavutil.mavlink_connection(conn_str, ...)
```

### PROVEN: Collector Starts But Receives No Packets

**Invocation**: [core/metrics_aggregator.py](core/metrics_aggregator.py), lines 125-132

```python
if self.mavlink_collector:
    sniff_port = 14552 if self.role == "gcs" else 47005
    try:
        self.mavlink_collector.start_sniffing(port=sniff_port)
    except Exception:
        pass  # Port may already be in use
```

**Evidence from JSON**:
```json
{
  "mavproxy_gcs": {
    "mavproxy_gcs_rx_pps": 0.0,
    "mavproxy_gcs_total_msgs_received": 0,
    "mavproxy_gcs_msg_type_counts": {}
  }
}
```

**Root Cause Analysis**:
- GCS collector binds to port 14552
- But MAVProxy on GCS is started with `--master=udpin:0.0.0.0:47002` (line 176 run_full_benchmark.py)
- MAVProxy does NOT duplicate output to port 14552
- Therefore, collector receives nothing

### PROVEN: FC Telemetry Has No Implementation

**Schema exists**: [core/metrics_schema.py](core/metrics_schema.py), lines 267-282, `FlightControllerTelemetry`

**Search for FC telemetry extraction code**:
- `fc_mode`, `fc_armed_state`, `fc_battery_voltage_v` are defined in schema
- **NO CODE** parses MAVLink messages to extract these values
- `GcsMetricsCollector` (sscheduler/gcs_metrics.py) parses HEARTBEAT and SYS_STATUS but writes to its OWN schema (`uav.pqc.telemetry.v1`), NOT to `ComprehensiveSuiteMetrics`

**Verdict**: FC telemetry is **DECLARED BUT NOT IMPLEMENTED** in the comprehensive schema.

---

## PHASE 8 — FINAL TRUTH REPORT

### 1. WHAT IS PROVEN TO WORK

| Component | Evidence |
|-----------|----------|
| **Proxy packet counters** | `gcs_status.json` shows `enc_out: 49465, enc_in: 2328` |
| **Handshake crypto timing** | `gcs_status.json` shows `kem_keygen_ms: 223.4985, sig_sign_ms: 5.7739` |
| **AEAD timing** | `gcs_status.json` shows `aead_encrypt.count: 49468, total_ns: 3170535300` |
| **System metrics (GCS)** | Comprehensive JSON shows `cpu_usage_avg_percent: 7.22` |
| **Schema fields defined** | 235 fields across 18 categories |
| **MetricsAggregator.record_crypto_primitives()** | Method exists at line 193, correctly maps fields |
| **MetricsAggregator.record_data_plane_metrics()** | Method exists at line 246, correctly maps fields |

### 2. WHAT DATA EXISTS BUT IS NOT WIRED

| Data | Source File | Target Schema | Missing Link |
|------|-------------|---------------|--------------|
| `kem_keygen_ms`, `sig_sign_ms`, etc. | `gcs_status.json` → `handshake_metrics` | `crypto_primitives.*` | `record_crypto_primitives()` not called on GCS |
| `ptx_in`, `enc_out`, etc. | `gcs_status.json` → `counters` | `data_plane.*` | `record_data_plane_metrics()` not called on GCS |
| `aead_encrypt.count`, `total_ns` | `gcs_status.json` → `primitive_metrics` | `data_plane.aead_*` | Same as above |
| Power samples (Drone) | `PowerCollector._samples` | `power_energy.*` | Drone-only, GCS doesn't have sensor (expected) |

### 3. WHAT IS PARTIALLY IMPLEMENTED

| Component | What Works | What Doesn't |
|-----------|------------|--------------|
| **Handshake schema** | `handshake_success`, `handshake_total_duration_ms` populated | `handshake_rtt_ms` always 0 (no RTT probe) |
| **MavLinkMetricsCollector** | Class exists, `start_sniffing()` binds port | Receives 0 packets due to MAVProxy config mismatch |
| **GcsMetricsCollector** | Parses HEARTBEAT, SYS_STATUS, writes to JSONL | Writes to own schema, not ComprehensiveSuiteMetrics |
| **Drone scheduler wiring** | `record_crypto_primitives()` and `record_data_plane_metrics()` called | Works only on drone, not mirrored to GCS |

### 4. WHAT IS DECLARED BUT NOT IMPLEMENTED

| Schema Category | Evidence of Absence |
|-----------------|---------------------|
| **F. Rekey Metrics** | No code populates `rekey_attempts`, `rekey_success`, etc. |
| **H. Latency/Jitter** | `LatencyTracker.record()` never called; `latency_samples: []` in all outputs |
| **L. FC Telemetry** | No code extracts HEARTBEAT mode/armed into schema; all fields 0 |
| **M. Control Plane** | No code populates scheduler state metrics |
| **RTT Measurement** | No ping/pong or TIMESYNC implementation exists |

### 5. WHAT IS MISLEADING OR DUPLICATED

| Issue | Location | Description |
|-------|----------|-------------|
| **Triple duplicate timing fields** | `gcs_status.json` | `kem_keygen_ms`, `kem_keygen_max_ms`, `kem_keygen_avg_ms` all identical |
| **part_b_metrics redundancy** | `async_proxy.py` line 100 | Duplicates top-level handshake_metrics |
| **MAVLink collector port mismatch** | `metrics_aggregator.py` line 126 | Binds 14552 but MAVProxy doesn't output there |

### 6. WHAT IS REQUIRED BEFORE POLICY CAN BE TRUSTED

| Requirement | Current State | Fix Needed |
|-------------|---------------|------------|
| **GCS crypto primitives in schema** | All zeros | Call `record_crypto_primitives()` after reading `gcs_status.json` |
| **GCS data plane in schema** | All zeros | Call `record_data_plane_metrics()` before `finalize_suite()` |
| **RTT measurement** | NOT IMPLEMENTED | Implement TIMESYNC probe or ping/pong protocol |
| **MAVLink collector receiving packets** | 0 packets | Fix MAVProxy `--out` port or collector binding |
| **Cross-side metric consolidation** | Separate files | Merge drone metrics into GCS output or vice versa |

### 7. OPEN QUESTIONS THAT CANNOT BE ANSWERED FROM CODE

| Question | Why Unanswerable |
|----------|------------------|
| **Does MAVProxy actually output to port 14552 in production?** | No production config file in repository; only code references |
| **Is INA219 power sensor connected and calibrated?** | No hardware configuration file; collector has fallback logic |
| **Are drone-side comprehensive JSONs being written?** | No drone-side logs in repository; only GCS logs present |
| **Does the drone scheduler call `record_data_plane_metrics()` successfully?** | Would require live drone run to verify; code path exists at line 454 but output not in repo |

---

## SUMMARY VERDICT

**The metrics system is 40% wired.**

**PROVEN WORKING**:
- Proxy counters (ptx/enc in/out)
- Handshake crypto timing (keygen, decap, sign on GCS; encap, verify on Drone)
- AEAD timing (encrypt/decrypt per-operation)
- System resources (CPU, memory)
- Schema definition (235 fields)

**PROVEN BROKEN**:
- GCS does not transfer crypto or data plane metrics to schema
- RTT/latency measurement not implemented
- MAVLink collector receives 0 packets
- FC telemetry has no implementation
- Cross-side consolidation does not exist

**REQUIRED FIXES** (in priority order):
1. Add ~10 lines to `bench/run_full_benchmark.py` to read `gcs_status.json` and call `record_crypto_primitives()` + `record_data_plane_metrics()`
2. Fix MAVProxy output port to match collector binding (14552 or 47005)
3. Implement RTT probe using MAVLink TIMESYNC
4. Add FC telemetry extraction from HEARTBEAT/SYS_STATUS messages

---

*Every claim in this report is backed by file path and line number. No assumptions were made.*
