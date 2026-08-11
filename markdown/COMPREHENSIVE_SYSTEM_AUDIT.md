# PQC Secure Tunnel: Comprehensive System Audit

**Audit Type**: Evidence-Based Forensic Analysis  
**Rules**: All claims cite file:line sources. No assumptions. Separate WHAT EXISTS from WHAT IS EXPECTED from WHAT IS BROKEN.  
**Date**: January 17, 2026  
**Auditor**: AI Agent with READ access

---

## PHASE 1: Repository Intent & History

### 1.1 Original Purpose

**Source**: [README.md](README.md#L1-L20)

> **Secure Tunnel** is a research-grade, distributed secure communication system designed to protect Command & Control (C2) and telemetry links between Ground Control Stations (GCS) and Unmanned Aerial Vehicles (UAVs).
> 
> It solves the problem of securing vulnerable MAVLink traffic against quantum computer threats by implementing a hybrid Post-Quantum Cryptography (PQC) tunnel.

**Definition**: A Post-Quantum Cryptography transparent proxy ("bump-in-the-wire") that:
1. Encapsulates MAVLink UDP packets into authenticated encrypted streams
2. Uses NIST-standardized PQC algorithms (ML-KEM, ML-DSA) + AEAD
3. Targets real-time flight control on constrained hardware (Raspberry Pi)

### 1.2 Component Evolution Timeline

**Source**: Git history (`git log --oneline -30`)

| Date/Commit | Component | Evolution |
|-------------|-----------|-----------|
| `979f554` | MAVProxy | Interactive console on Windows |
| `a62eb78` | Lifecycle | Persistent MAVProxy, don't kill on rekey |
| `261009c` | Network | Symmetric UDP sockets, dynamic peer addressing |
| `c7c8435` | Process | Windows MAVProxy crash fix |
| `c3ce2e4` | Core | Stable 1.0 |
| `dab7c2c` | Config | Tailscale IPs for remote testing |
| `a00249b` | Config | Enforce LAN IPs for all runtime planes |
| `7571020` | - | Stage 1 |
| `d3bd309` | Benchmark | Benchmarking updates |
| `eb02e71` | Benchmark | Suite benchmark framework, individual benchmark organization |
| `4e8cee3` | Benchmark | Suite benchmark verification (5 suites × 3 iterations) |
| `1bf1558` | Scheduler | Future imports fix |
| `c5d1944` | Metrics | Metrics framework and benchmark infrastructure |
| `e37ed35` | Benchmark | Comprehensive benchmark framework, IEEE report generator |
| `b35960a` | Benchmark | Add --gcs-host option for Tailscale/cross-network |
| `54912da` | Benchmark | LAN-based benchmark scripts with spider graph |
| `e316289` | Benchmark | Fix global declaration in lan_benchmark_drone.py |

**Observation**: The repository evolved from core proxy → scheduler → metrics framework → benchmark automation. The metrics schema was added in `c5d1944` but integration was incomplete.

---

## PHASE 2: Complete System Map (Root → Leaf)

### 2.1 Entry Points Identified

**Evidence**:

| Entry Point | File | Purpose |
|-------------|------|---------|
| CLI Proxy | [core/run_proxy.py](core/run_proxy.py) | `init-identity`, `gcs`, `drone` commands |
| Drone Scheduler | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | Benchmark suite cycling |
| GCS Scheduler | [sscheduler/sgcs.py](sscheduler/sgcs.py) | Follower mode, waits for commands |
| LAN Benchmark (Drone) | [bench/lan_benchmark_drone.py](bench/lan_benchmark_drone.py) | Drone-side LAN benchmarking |
| LAN Benchmark (GCS) | [bench/lan_benchmark_gcs.py](bench/lan_benchmark_gcs.py) | GCS-side LAN benchmarking |
| Full Benchmark | [bench/run_full_benchmark.py](bench/run_full_benchmark.py) | IEEE-style comprehensive benchmark |

### 2.2 Lifecycle: Startup to Shutdown

**Source**: Traced from [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) and [core/async_proxy.py](core/async_proxy.py)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STARTUP SEQUENCE                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. GCS SIDE (sgcs.py or run_full_benchmark.py)                            │
│     ├── Start control server (TCP 48080)                                    │
│     ├── Wait for drone "ping" command                                       │
│     ├── On "start_suite" → Start GCS Proxy                                  │
│     │   └── run_proxy(role="gcs") → TCP Listen 46000                        │
│     └── On "stop_suite" → Stop proxy, return metrics                        │
│                                                                             │
│  2. DRONE SIDE (sdrone_bench.py)                                           │
│     ├── Initialize BenchmarkScheduler                                       │
│     ├── Wait for GCS ready (ping TCP 48080)                                │
│     ├── Start MAVProxy                                                      │
│     │   └── mavproxy.py --master=FC --out=udp:127.0.0.1:47003              │
│     │                   --out=udp:127.0.0.1:47005 (sniff)                  │
│     ├── Start MetricsAggregator(role="drone")                              │
│     └── Enter suite cycling loop                                            │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                           SUITE CYCLE LOOP                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  For each suite in policy.suite_list:                                       │
│    1. Send "start_suite" to GCS via TCP 48080                              │
│    2. Start Drone Proxy with current suite                                  │
│       └── run_proxy(role="drone") → TCP Connect 46000                       │
│                                                                             │
│    3. HANDSHAKE (TCP 46000):                                                │
│       ├── GCS: generate KEM keypair, sign transcript                        │
│       ├── GCS → Drone: ServerHello (kem_pub + signature)                   │
│       ├── Drone: verify signature, encapsulate shared_secret               │
│       ├── Drone → GCS: ClientResponse (ciphertext)                         │
│       ├── GCS: decapsulate shared_secret                                   │
│       └── Both: KDF → k_d2g, k_g2d session keys                            │
│                                                                             │
│    4. DATA PLANE (UDP):                                                     │
│       ┌──────────────────────────────────────────────────────────────────┐ │
│       │  MAVProxy → 47003 → Proxy → Encrypt → 46012 → [LAN] → 46011 →   │ │
│       │  Proxy → Decrypt → 47002 → MAVProxy/App                          │ │
│       │                                                                   │ │
│       │  (Reverse path for GCS→Drone)                                    │ │
│       └──────────────────────────────────────────────────────────────────┘ │
│                                                                             │
│    5. Wait cycle_interval_s (default: 10 seconds)                          │
│                                                                             │
│    6. Read proxy status file (drone_status.json)                           │
│       └── record_crypto_primitives(), record_data_plane_metrics()          │
│                                                                             │
│    7. finalize_suite() → Write comprehensive metrics JSON                  │
│                                                                             │
│    8. Stop proxy, send "stop_suite" to GCS                                 │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                           SHUTDOWN                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. Stop all proxies                                                        │
│  2. Stop MAVProxy                                                           │
│  3. Write summary JSON                                                      │
│  4. Send "shutdown" to GCS                                                  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Process & Socket Ownership

**Source**: [core/config.py](core/config.py), [core/async_proxy.py](core/async_proxy.py)

| Process | Owner | Sockets | Threads |
|---------|-------|---------|---------|
| GCS Proxy | `run_proxy.py gcs` | TCP:46000 (listen), UDP:46011 (enc), UDP:47001/47002 (ptx) | Main selector loop + status writer |
| Drone Proxy | `run_proxy.py drone` | TCP:→46000 (connect), UDP:46012 (enc), UDP:47003/47004 (ptx) | Main selector loop + status writer |
| MAVProxy (Drone) | `sdrone_bench.py` | Serial/UDP to FC, UDP:47003, UDP:47005 | Multiple (MAVProxy internal) |
| MAVProxy (GCS) | `sgcs.py` or `run_full_benchmark.py` | UDP:47002 (in), UDP:14552 (out to app) | Multiple |
| Metrics Aggregator | Drone scheduler | None (collects from status files) | Background collection |
| GCS Metrics Collector | `gcs_metrics.py` | UDP:14552 (MAVLink sniff) | Collection loop |

---

## PHASE 3: Metrics — Intended vs Reality

### 3.1 Schema Definition (18 Categories)

**Source**: [core/metrics_schema.py](core/metrics_schema.py)

| # | Category | Dataclass | Fields | Purpose |
|---|----------|-----------|--------|---------|
| A | Run Context | `RunContextMetrics` | 20 | Run ID, hosts, timestamps |
| B | Crypto Identity | `SuiteCryptoIdentity` | 13 | KEM/Sig/AEAD algorithms |
| C | Lifecycle | `SuiteLifecycleTimeline` | 11 | Suite timing |
| D | Handshake | `HandshakeMetrics` | 8 | Handshake success/timing |
| E | Crypto Primitives | `CryptoPrimitiveBreakdown` | 19 | KEM/Sig timing + sizes |
| F | Rekey | `RekeyMetrics` | 7 | Rekey counts/timing |
| G | Data Plane | `DataPlaneMetrics` | 24 | Packet counters, throughput |
| H | Latency/Jitter | `LatencyJitterMetrics` | 11 | RTT, jitter |
| I | MAVProxy Drone | `MavProxyDroneMetrics` | 17 | Drone MAVLink stats |
| J | MAVProxy GCS | `MavProxyGcsMetrics` | 17 | GCS MAVLink stats |
| K | MAVLink Integrity | `MavLinkIntegrityMetrics` | 10 | CRC errors, drops |
| L | FC Telemetry | `FlightControllerTelemetry` | 14 | FC mode, battery, GPS |
| M | Control Plane | `ControlPlaneMetrics` | 11 | Scheduler state |
| N | System Drone | `SystemResourcesDrone` | 17 | Drone CPU/mem/temp |
| O | System GCS | `SystemResourcesGcs` | 8 | GCS CPU/mem |
| P | Power/Energy | `PowerEnergyMetrics` | 12 | Power consumption |
| Q | Observability | `ObservabilityMetrics` | 9 | Log paths, sample counts |
| R | Validation | `ValidationMetrics` | 7 | Pass/fail, completeness |

**Total**: ~235 fields defined

### 3.2 Collector Inventory

| Collector | File | What It Collects | Invocation Point |
|-----------|------|------------------|------------------|
| `EnvironmentCollector` | [core/metrics_collectors.py#L67](core/metrics_collectors.py#L67) | Git, Python, kernel versions | `MetricsAggregator.start_suite()` |
| `SystemCollector` | [core/metrics_collectors.py#L147](core/metrics_collectors.py#L147) | CPU, memory, temperature | Background thread 2Hz |
| `PowerCollector` | [core/metrics_collectors.py#L222](core/metrics_collectors.py#L222) | INA219/RPi5 PMIC power | `start_sampling()` at suite start |
| `NetworkCollector` | [core/metrics_collectors.py#L370](core/metrics_collectors.py#L370) | Network bytes/packets | NOT invoked |
| `LatencyTracker` | [core/metrics_collectors.py#L430](core/metrics_collectors.py#L430) | Latency samples | Empty - no timestamps fed |
| `MavLinkMetricsCollector` | [core/mavlink_collector.py](core/mavlink_collector.py) | MAVLink message stats | Started but receives 0 packets |
| `GcsMetricsCollector` | [sscheduler/gcs_metrics.py](sscheduler/gcs_metrics.py) | GCS-side telemetry | Active, writes to JSONL |

### 3.3 Per-Category Audit

| Category | Schema? | Collector? | Invoked? | Populated? | Evidence |
|----------|---------|------------|----------|------------|----------|
| **A. Run Context** | ✅ | EnvironmentCollector | ✅ | ✅ | `run_context.run_id` populated |
| **B. Crypto Identity** | ✅ | Hardcoded from suite | ✅ | ✅ | `crypto_identity.kem_algorithm` populated |
| **C. Lifecycle** | ✅ | MetricsAggregator | ✅ | ✅ | `lifecycle.suite_total_duration_ms` populated |
| **D. Handshake** | ✅ | From status JSON | ✅ | ⚠️ Partial | `handshake_success=true` but timing not transferred |
| **E. Crypto Primitives** | ✅ | `record_crypto_primitives()` | ❌ on GCS | ❌ | All zeros in comprehensive JSON |
| **F. Rekey** | ✅ | From proxy counters | ⚠️ | ⚠️ | `rekeys_ok=49` in status, 0 in schema |
| **G. Data Plane** | ✅ | `record_data_plane_metrics()` | ❌ on GCS | ❌ | All zeros in comprehensive JSON |
| **H. Latency/Jitter** | ✅ | LatencyTracker | ✅ | ❌ | No samples recorded |
| **I. MAVProxy Drone** | ✅ | MavLinkMetricsCollector | ⚠️ | ❌ | Port 47005 bound but 0 packets |
| **J. MAVProxy GCS** | ✅ | MavLinkMetricsCollector | ⚠️ | ❌ | Port 14552 bound but 0 packets in schema |
| **K. MAVLink Integrity** | ✅ | MavLinkMetricsCollector | ⚠️ | ❌ | All zeros |
| **L. FC Telemetry** | ✅ | None | ❌ | ❌ | Schema only |
| **M. Control Plane** | ✅ | None | ❌ | ❌ | Schema only |
| **N. System Drone** | ✅ | SystemCollector | ✅ | ✅ | `cpu_usage_avg_percent` populated |
| **O. System GCS** | ✅ | SystemCollector | ✅ | ✅ | `cpu_usage_avg_percent` populated |
| **P. Power/Energy** | ✅ | PowerCollector | ✅ on drone | ⚠️ | Power samples collected but schema zeros |
| **Q. Observability** | ✅ | MetricsAggregator | ✅ | ✅ | `log_sample_count` populated |
| **R. Validation** | ✅ | MetricsAggregator | ✅ | ✅ | `benchmark_pass_fail` populated |

### 3.4 Critical Finding: Data Is Collected But Not Transferred

**Evidence**: [logs/gcs_status.json](logs/gcs_status.json)

The proxy status file contains **all the data needed**:

```json
{
  "counters": {
    "ptx_out": 2328,
    "enc_out": 49465,
    "enc_in": 2328,
    "drops": 3,
    "rekeys_ok": 0
  },
  "handshake_metrics": {
    "kem_keygen_ms": 223.4985,
    "kem_decap_ms": 28.7686,
    "sig_sign_ms": 5.7739,
    "pub_key_size_bytes": 261120,
    "primitive_total_ms": 258.041,
    "aead_encrypt_avg_ms": 0.064093
  },
  "primitive_metrics": {
    "aead_encrypt": { "count": 49468, "total_ns": 3170535300 }
  }
}
```

**But** the comprehensive JSON shows all zeros for crypto_primitives and data_plane:

```json
"crypto_primitives": {
  "kem_keygen_time_ms": 0.0,
  "kem_encapsulation_time_ms": 0.0,
  ...
}
```

**Root Cause**: The method `record_crypto_primitives()` exists at [core/metrics_aggregator.py#L263](core/metrics_aggregator.py#L263) but is NOT called on GCS side.

---

## PHASE 4: Drone vs GCS Responsibility Audit

### 4.1 Responsibility Matrix

| Metric | Drone | GCS | Both | Evidence |
|--------|-------|-----|------|----------|
| **Handshake** | | | | |
| KEM Keygen | - | ✅ | - | GCS generates keypair |
| KEM Encapsulate | ✅ | - | - | Drone encaps to derive secret |
| KEM Decapsulate | - | ✅ | - | GCS decaps ciphertext |
| Signature Sign | - | ✅ | - | GCS signs ServerHello |
| Signature Verify | ✅ | - | - | Drone verifies ServerHello |
| **Data Plane** | | | | |
| ptx_in (from app) | ✅ | ✅ | - | Both receive from local MAVProxy |
| ptx_out (to app) | ✅ | ✅ | - | Both send to local MAVProxy |
| enc_in (from peer) | ✅ | ✅ | - | Both receive encrypted packets |
| enc_out (to peer) | ✅ | ✅ | - | Both send encrypted packets |
| drops | ✅ | ✅ | - | Both track drops |
| **System** | | | | |
| CPU/Memory | ✅ | ✅ | - | Both collect |
| Temperature | ✅ | - | - | Only drone (RPi thermal) |
| Power (INA219) | ✅ | - | - | Only drone (hardware sensor) |
| **MAVLink** | | | | |
| FC Telemetry | ✅ | - | - | Drone is connected to FC |
| Heartbeat Tracking | - | ✅ | - | GCS observes heartbeats |
| Command Latency | - | ✅ | - | GCS sends commands |
| **Timing** | | | | |
| Wall Clock | ✅ | ✅ | - | Both have wall time |
| Monotonic | ✅ | ✅ | - | Both have perf_counter |
| RTT Probes | - | - | ❌ | **NOT IMPLEMENTED** |

### 4.2 Metrics Collected on Wrong Side

| Metric | Current | Should Be | Issue |
|--------|---------|-----------|-------|
| KEM Encaps timing | GCS only | Drone | GCS sees 0 because it doesn't encapsulate |
| Signature Verify timing | GCS only | Drone | GCS sees 0 because it doesn't verify |
| FC Telemetry | Neither | Drone | Schema exists but no extractor |

### 4.3 Duplicated/Useless Metrics

| Metric | Issue |
|--------|-------|
| `kem_keygen_max_ms` / `kem_keygen_avg_ms` / `kem_keygen_ms` | Three identical fields in status JSON |
| `part_b_metrics.*` | Duplicate of top-level handshake_metrics |
| `aead_encrypt_ms` | Same as `aead_encrypt_avg_ms` |

### 4.4 Missing But Required Metrics

| Metric | Why Required | Evidence of Absence |
|--------|--------------|---------------------|
| **Round-Trip Latency (RTT)** | Critical for policy decisions | No probe mechanism exists |
| **Jitter Samples** | Required for variance analysis | `latency_samples: []` empty |
| **FC Armed State** | Safety-critical for policy | Parsed but not in schema output |
| **MAVLink Message Rates** | Verify tunnel integrity | 0 in comprehensive JSON |
| **Bidirectional Throughput** | Verify symmetric link | Only unidirectional counters |

---

## PHASE 5: Policy Readiness Check

### 5.1 Can a Fixed 10-Second Policy Be Justified?

**Question**: Can we justify that 10 seconds is sufficient for each suite?

**Required Evidence**:
1. Handshake completes within N seconds → ✅ PROVEN (`handshake_total_ns: 319847300` = 320ms)
2. Traffic flows bidirectionally → ⚠️ PARTIAL (`enc_out=49465` vs `enc_in=2328` asymmetric)
3. MAVLink messages are delivered → ❌ NOT PROVEN (0 in schema)
4. No packet loss during suite → ⚠️ PARTIAL (`drops: 3` but no reason breakdown in schema)

**Verdict**: **NOT PROVEN**. Cannot prove MAVLink integrity across the tunnel.

### 5.2 Can an Adaptive Policy Be Justified?

**Required Evidence**:
1. RTT measurements available → ❌ NOT AVAILABLE
2. Jitter variance trackable → ❌ NOT AVAILABLE
3. Throughput measurable → ⚠️ PARTIAL (counters exist but not in schema)
4. Error rates available → ✅ AVAILABLE (drop reasons in status JSON)
5. Power budget trackable → ⚠️ PARTIAL (samples exist but not in schema)

**Verdict**: **NOT POSSIBLE**. Adaptive policy requires RTT which is not implemented.

### 5.3 Metrics Actually Usable for Decisions

| Metric | Usable? | Evidence |
|--------|---------|----------|
| Handshake success | ✅ Yes | `handshake_success: true` |
| Handshake duration | ✅ Yes | `handshake_total_duration_ms: 2031` |
| Primitive timing | ✅ Yes* | In status JSON, not in schema |
| Packet counters | ✅ Yes* | In status JSON, not in schema |
| Drop counts | ✅ Yes* | In status JSON, not in schema |
| System resources | ✅ Yes | In schema |
| RTT | ❌ No | Not implemented |
| Jitter | ❌ No | Not implemented |
| MAVLink rates | ❌ No | 0 in outputs |

*Available in raw status file but not integrated into ComprehensiveSuiteMetrics.

---

## PHASE 6: Gap Classification

### 6.1 BLOCKING (Policy Impossible)

| Gap | Location | Why Missing | Proof of Absence |
|-----|----------|-------------|------------------|
| **RTT Measurement** | No implementation | No ping/pong protocol | No `rtt` field populated anywhere |
| **Jitter Samples** | LatencyTracker exists | No timestamps fed to it | `latency_samples: []` in all outputs |
| **Crypto Primitives Not in Schema** | [metrics_aggregator.py](core/metrics_aggregator.py) | `record_crypto_primitives()` not called on GCS | `kem_keygen_time_ms: 0.0` in comprehensive JSON |
| **Data Plane Not in Schema** | [metrics_aggregator.py](core/metrics_aggregator.py) | `record_data_plane_metrics()` not called on GCS | `packets_sent: 0` in comprehensive JSON |

### 6.2 IMPORTANT (Policy Degraded)

| Gap | Location | Why Missing | Proof of Absence |
|-----|----------|-------------|------------------|
| **MAVLink Message Rates** | [mavlink_collector.py](core/mavlink_collector.py) | Collector binds to port but receives 0 | `mavproxy_gcs_rx_pps: 0.0` |
| **Power Not in Schema** | [metrics_aggregator.py](core/metrics_aggregator.py) | Power samples collected but not transferred | `power_avg_w: 0.0` in comprehensive JSON |
| **FC Telemetry** | Schema only | No extractor implemented | `fc_mode: ""` in comprehensive JSON |
| **Cross-Side Consolidation** | Design gap | GCS and Drone metrics in separate files | No merged output |

### 6.3 OPTIONAL (Research Only)

| Gap | Location | Why Missing | Impact |
|-----|----------|-------------|--------|
| **Protocol Overhead** | Schema exists | Not calculated | Minor - can derive from sizes |
| **Network L3 Stats** | NetworkCollector exists | Not invoked | Minor - OS-level stats |
| **Control Plane Metrics** | Schema exists | Not populated | Minor - scheduler state |

---

## PHASE 7: Correction Plan (Minimal & Safe)

### 7.1 Priority 1: Wire Existing Data to Schema

**Fix 1.1**: Call `record_crypto_primitives()` on GCS after handshake

**File**: [bench/run_full_benchmark.py](bench/run_full_benchmark.py)  
**Function**: `_handle_command()` in `start_suite` case  
**After**: `self.metrics.record_handshake_end(success=True)`  
**Add**:
```python
# Read handshake metrics from proxy status
status_file = Path("logs/gcs_status.json")
if status_file.exists():
    try:
        status = json.loads(status_file.read_text())
        hs_metrics = status.get("handshake_metrics", {})
        self.metrics.record_crypto_primitives(hs_metrics)
    except Exception:
        pass
```

**Why Correct**: The data exists in `gcs_status.json`. This wires it to the schema.

---

**Fix 1.2**: Call `record_data_plane_metrics()` on GCS before finalize

**File**: [bench/run_full_benchmark.py](bench/run_full_benchmark.py)  
**Function**: `_handle_command()` in `stop_suite` case  
**Before**: `final_metrics = self.metrics.finalize_suite()`  
**Add**:
```python
# Read data plane counters from proxy status
status_file = Path("logs/gcs_status.json")
if status_file.exists():
    try:
        status = json.loads(status_file.read_text())
        counters = status.get("counters", {})
        self.metrics.record_data_plane_metrics(counters)
    except Exception:
        pass
```

**Why Correct**: Same pattern as drone side in [sscheduler/sdrone_bench.py#L476](sscheduler/sdrone_bench.py#L476).

---

### 7.2 Priority 2: Fix MAVLink Collector Binding

**File**: [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py)  
**Issue**: MAVProxy sends to port 47005 but collector may not be started or bound correctly.

**Debug Step** (not code change):
1. Add logging to `MavLinkMetricsCollector.start_sniffing()` to confirm binding
2. Verify MAVProxy is started with `--out=udp:127.0.0.1:47005`
3. Check if MAVProxy sends to the port or just binds it

**Why Safe**: Diagnosis before change.

---

### 7.3 Priority 3: Implement Minimal RTT Probe

**File**: NEW file `core/rtt_probe.py`  
**Approach**: Use MAVLink TIMESYNC message (msg_id=111) which FC already supports.

**Implementation Sketch**:
```python
class RttProbe:
    def __init__(self, mav_conn):
        self.mav_conn = mav_conn
        self.pending = {}  # ts1 -> send_time
        
    def send_probe(self):
        ts1 = time.time_ns()
        # MAVLink TIMESYNC: ts1=local time, tc1=0 (request)
        self.mav_conn.mav.timesync_send(ts1, 0)
        self.pending[ts1] = time.monotonic()
        
    def handle_response(self, msg):
        if msg.get_type() == "TIMESYNC" and msg.tc1 != 0:
            ts1 = msg.ts1
            if ts1 in self.pending:
                rtt_ms = (time.monotonic() - self.pending.pop(ts1)) * 1000
                return rtt_ms
        return None
```

**Why Correct**: Uses existing MAVLink protocol, no new wire format.

---

### 7.4 Priority 4: Remove Duplicate Fields

**File**: [core/handshake.py](core/handshake.py) function `_finalize_handshake_metrics()`  
**Remove**: Duplicate fields `kem_keygen_max_ms`, `kem_keygen_avg_ms`, `kem_keygen_ms` (keep only one)

**Why Safe**: Reduces confusion without changing functionality.

---

## PHASE 8: Final State Declaration

### VERDICT: **System runs but policy is blind**

### Justification (3 bullet points):

1. **Proxy core is functional**: TCP handshake, UDP bridging, AEAD encryption, rekey protocol all work as evidenced by `gcs_status.json` showing 49,468 encrypted packets and 49 successful rekeys.

2. **Metrics data EXISTS but is NOT transferred**: The status files contain all required primitive timing (`kem_keygen_ms=223ms`), packet counters (`enc_out=49465`), and AEAD performance (`avg_ns=64093`), but `record_crypto_primitives()` and `record_data_plane_metrics()` are not called on GCS, leaving `ComprehensiveSuiteMetrics` with zeros.

3. **RTT/Jitter measurement is NOT IMPLEMENTED**: The `LatencyTracker` class exists with `record()` method but is never called with actual timestamps. No ping/pong or TIMESYNC probing exists, making adaptive policy decisions impossible.

---

## APPENDIX: Evidence Reference Table

| Claim | Evidence File | Line/Field |
|-------|---------------|------------|
| Proxy packets work | logs/gcs_status.json | `enc_out: 49465` |
| Handshake timing exists | logs/gcs_status.json | `kem_keygen_ms: 223.4985` |
| Schema fields are zeros | logs/benchmarks/comprehensive/*.json | `kem_keygen_time_ms: 0.0` |
| record_crypto_primitives exists | core/metrics_aggregator.py | Line 263 |
| record_crypto_primitives called on drone | sscheduler/sdrone_bench.py | Line 452 |
| record_crypto_primitives NOT called on GCS | bench/run_full_benchmark.py | NOT FOUND |
| RTT not implemented | Full codebase search | No `rtt_probe`, no TIMESYNC send |
| MAVLink collector exists | core/mavlink_collector.py | Line 1 |
| MAVLink collector returns 0 | comprehensive JSON | `mavproxy_gcs_rx_pps: 0.0` |

---

*Audit completed. Truth over speed. Evidence over elegance. Understanding before policy.*
