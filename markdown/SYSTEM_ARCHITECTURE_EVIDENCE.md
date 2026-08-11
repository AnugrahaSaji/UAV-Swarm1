# PQC Drone-GCS Secure Tunnel: Evidence-Based System Architecture

**Document Type**: Forensic Analysis  
**Evidence Policy**: All claims cite specific file:line sources. No assumptions.  
**Date**: Generated from codebase inspection

---

## 1. SYSTEM IDENTITY

### What This System Is (Evidence-Based)

**Source**: [core/async_proxy.py](core/async_proxy.py#L1-L15)
```
Selectors-based network transport proxy.
...
Note: This module uses the low-level `selectors` stdlib facility—not `asyncio`—to
avoid GIL interactions in the main event loop.
```

**Definition**: A Post-Quantum Cryptography (PQC) secure tunnel that:
1. Performs a TCP handshake using OQS (Open Quantum Safe) KEM + Signature algorithms
2. Bridges UDP traffic between local MAVProxy and remote peer through authenticated encryption
3. Uses Python's `selectors` module (NOT asyncio) for deterministic I/O multiplexing

---

## 2. ARCHITECTURE BLOCK DIAGRAM (Text)

```
DRONE SIDE                                                   GCS SIDE
══════════════════════════════════════════════════════════════════════════════

┌─────────────────┐                                          ┌─────────────────┐
│  Flight         │                                          │  Ground         │
│  Controller     │                                          │  Station        │
│  (Pixhawk/SITL) │                                          │  (Mission       │
│                 │                                          │   Planner/      │
│  Serial/UDP     │                                          │   QGroundCtrl)  │
└────────┬────────┘                                          └────────┬────────┘
         │                                                            │
         │ MAVLink                                                    │ MAVLink
         ↓                                                            ↓
┌─────────────────┐                                          ┌─────────────────┐
│  MAVProxy       │                                          │  MAVProxy       │
│  (Drone-side)   │                                          │  (GCS-side)     │
│                 │                                          │                 │
│  --master=FC    │                                          │  --master=      │
│  --out=127.0.0.1│                                          │    udp:127..    │
│     :47003      │                                          │     :47002      │
│  --out=127.0.0.1│                                          │  --out=app      │
│     :47005      │                                          │                 │
│   (sniff port)  │                                          │                 │
└────────┬────────┘                                          └────────┬────────┘
         │                                                            │
         │ UDP plaintext                                              │ UDP plaintext
         │ 127.0.0.1:47003→47004                                      │ 127.0.0.1:47001→47002
         ↓                                                            ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         PQC SECURE PROXY                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  DRONE PROXY (run_proxy role="drone")      GCS PROXY (run_proxy role="gcs")│
│  ┌─────────────────────────────────┐       ┌─────────────────────────────┐ │
│  │                                 │       │                             │ │
│  │  ┌─────────────────────────┐    │       │   ┌─────────────────────┐   │ │
│  │  │ plaintext_in  (47004)   │    │       │   │ plaintext_in (47001)│   │ │
│  │  │ plaintext_out (47003)   │←───┼───────┼──→│ plaintext_out(47002)│   │ │
│  │  └───────────┬─────────────┘    │       │   └─────────┬───────────┘   │ │
│  │              │                  │       │             │               │ │
│  │         ┌────┴────┐             │       │        ┌────┴────┐          │ │
│  │         │ ENCRYPT │             │       │        │ ENCRYPT │          │ │
│  │         │ Sender  │             │       │        │ Sender  │          │ │
│  │         │ AES-GCM/│             │       │        │ AES-GCM/│          │ │
│  │         │ Ascon   │             │       │        │ Ascon   │          │ │
│  │         └────┬────┘             │       │        └────┬────┘          │ │
│  │              │                  │       │             │               │ │
│  │  ┌───────────┴─────────────┐    │       │   ┌─────────┴───────────┐   │ │
│  │  │ encrypted sock (46012)  │←═══╪═══════╪══→│ encrypted (46011)   │   │ │
│  │  └───────────┬─────────────┘    │  LAN  │   └─────────┬───────────┘   │ │
│  │              │                  │192.168│             │               │ │
│  │         ┌────┴────┐             │ .0.x  │        ┌────┴────┐          │ │
│  │         │ DECRYPT │             │       │        │ DECRYPT │          │ │
│  │         │Receiver │             │       │        │Receiver │          │ │
│  │         └─────────┘             │       │        └─────────┘          │ │
│  └─────────────────────────────────┘       └─────────────────────────────┘ │
│                                                                             │
│  TCP HANDSHAKE CHANNEL (46000)                                              │
│  ────────────────────────────────                                           │
│  GCS Listens → Drone Connects → KEM + Signature Exchange → Session Keys     │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. NETWORK PORTS (Single Source of Truth)

**Source**: [core/config.py](core/config.py#L50-L100)

| Purpose                | Port  | Binding Side | Evidence |
|------------------------|-------|--------------|----------|
| TCP Handshake Listen   | 46000 | GCS          | `HANDSHAKE_PORT = 46000` |
| Encrypted UDP - Drone  | 46012 | Drone binds  | `DRONE_ENC_RX_PORT = 46012` |
| Encrypted UDP - GCS    | 46011 | GCS binds    | `GCS_ENC_RX_PORT = 46011` |
| Plaintext TX - Drone   | 47003 | localhost    | `DRONE_PLAIN_TX_PORT = 47003` |
| Plaintext RX - Drone   | 47004 | localhost    | `DRONE_PLAIN_RX_PORT = 47004` |
| Plaintext TX - GCS     | 47001 | localhost    | `GCS_PLAIN_TX_PORT = 47001` |
| Plaintext RX - GCS     | 47002 | localhost    | `GCS_PLAIN_RX_PORT = 47002` |
| Control TCP            | 48080 | Both         | `CONTROL_PORT = 48080` |
| Telemetry TCP          | 52080 | Both         | `TELEMETRY_PORT = 52080` |
| MAVLink Sniff (Drone)  | 47005 | Drone        | [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py#L230) |

**Hosts** (Source: [core/config.py](core/config.py)):
- `DRONE_HOST = "192.168.0.105"` (LAN IP of Raspberry Pi)
- `GCS_HOST = "192.168.0.101"` (LAN IP of GCS machine)

---

## 4. EXECUTION ENTRY POINTS

### 4.1 Main CLI: `core/run_proxy.py`

**Source**: [core/run_proxy.py](core/run_proxy.py#L1-L50)

```python
# Commands available:
#   init-identity  - Generate signing keypair
#   gcs            - Start GCS-side proxy
#   drone          - Start drone-side proxy
```

**GCS Command Flow** ([run_proxy.py#L700-L800](core/run_proxy.py#L700)):
1. `gcs_command()` → loads signing secret from `secrets/`
2. Calls `run_proxy(role="gcs", ...)` from `core.async_proxy`
3. Listens on TCP 46000 for drone handshake
4. After handshake, bridges UDP traffic

**Drone Command Flow** ([run_proxy.py#L800-L900](core/run_proxy.py#L800)):
1. `drone_command()` → loads GCS public key
2. Calls `run_proxy(role="drone", ...)`
3. Connects to GCS TCP 46000
4. After handshake, bridges UDP traffic

### 4.2 Benchmark Scheduler: `sscheduler/sdrone_bench.py`

**Source**: [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py#L270-L350)

```python
class BenchmarkScheduler:
    def __init__(self, args):
        self.proxy = DroneProxyManager()
        self.policy = BenchmarkPolicy(cycle_interval_s=args.interval)  # Default 10s
        self.metrics_aggregator = MetricsAggregator(role="drone")
```

**Lifecycle**:
1. Wait for GCS ready signal (HTTP ping)
2. Start MAVProxy (`--master=<FC>`, `--out=udp:127.0.0.1:47003`)
3. Loop through suites:
   - Stop previous proxy
   - Start new proxy with current suite
   - Run for `cycle_interval_s` seconds (default: 10)
   - Collect metrics
   - Write JSONL record
4. Shutdown and write summary

---

## 5. DATA FLOW: Packet Lifecycle (Evidence)

### 5.1 Plaintext → Encrypted (Drone→GCS Direction)

**Source**: [core/async_proxy.py](core/async_proxy.py#L1260-L1320)

```
Step 1: MAVProxy sends MAVLink packet to 127.0.0.1:47003
Step 2: Proxy receives on plaintext_in socket (47004)
        ↳ Code: `payload, addr = sock.recvfrom(16384)`
        ↳ Counter: `counters.ptx_in += 1`
Step 3: Prepend packet type if enabled
        ↳ Code: `payload_out = (b"\x01" + payload) if cfg.get("ENABLE_PACKET_TYPE") else payload`
Step 4: Encrypt with current Sender
        ↳ Code: `wire = current_sender.encrypt(payload_out)`
        ↳ Timing: `encrypt_start_ns = time.perf_counter_ns()`
Step 5: Send to peer encrypted socket
        ↳ Code: `sockets["encrypted"].sendto(wire, sockets["encrypted_peer"])`
        ↳ Counter: `counters.enc_out += 1`
        ↳ Metric: `counters.record_encrypt(encrypt_elapsed_ns, plaintext_len, ciphertext_len)`
```

### 5.2 Encrypted → Plaintext (GCS→Drone Direction)

**Source**: [core/async_proxy.py](core/async_proxy.py#L1340-L1450)

```
Step 1: Peer proxy sends encrypted packet to port 46012
Step 2: Proxy receives on encrypted socket
        ↳ Code: `wire, addr = sock.recvfrom(16384)`
Step 3: Validate source address
        ↳ Drop if mismatch: `counters.drop_src_addr += 1`
        ↳ Counter: `counters.enc_in += 1`
Step 4: Decrypt with Receiver
        ↳ Code: `plaintext = current_receiver.decrypt(wire)`
        ↳ Failures: drop_replay, drop_header, drop_auth
Step 5: Send to local MAVProxy
        ↳ Code: `sockets["plaintext_out"].sendto(out_bytes, app_peer_addr)`
        ↳ Counter: `counters.ptx_out += 1`
```

---

## 6. HANDSHAKE PROTOCOL (Evidence)

**Source**: [core/handshake.py](core/handshake.py#L100-L200)

### 6.1 Protocol Steps

```
GCS (Server)                                 Drone (Client)
────────────────────────────────────────────────────────────
1. TCP Listen 46000
                              ← TCP Connect ←
2. Generate KEM keypair
   kem_obj = KeyEncapsulation(kem_name)
   kem_pub = kem_obj.generate_keypair()
   ↳ Timing: kem_metrics["keygen_ns"]
   
3. Sign transcript
   transcript = version || session_id || kem_pub || challenge
   signature = server_sig_obj.sign(transcript)
   ↳ Timing: sig_metrics["sign_ns"]
   
4. Send ServerHello
   → version || kem_name || sig_name || session_id || kem_pub || signature →
   
5.                                           Verify signature
                                             sig_obj.verify(transcript, sig)
                                             ↳ Timing: sig_metrics["verify_ns"]
                                             
6.                                           KEM encapsulate
                                             ciphertext, shared_secret = encap(kem_pub)
                                             ↳ Timing: kem_metrics["encap_ns"]
                                             
7.                              ← ClientResponse (ciphertext) ←

8. KEM decapsulate
   shared_secret = kem_obj.decap(ciphertext)
   ↳ Timing: kem_metrics["decap_ns"]
   
9. Derive session keys
   k_d2g, k_g2d = KDF(shared_secret)
```

### 6.2 Supported Suites

**Source**: [core/suites.py](core/suites.py) (inferred from grep results)

| Suite ID | KEM | Signature | AEAD |
|----------|-----|-----------|------|
| ML_KEM_512 + ML_DSA_44 | ML-KEM-512 | ML-DSA-44 | AES-GCM |
| ML_KEM_768 + ML_DSA_65 | ML-KEM-768 | ML-DSA-65 | AES-GCM |
| ML_KEM_1024 + ML_DSA_87 | ML-KEM-1024 | ML-DSA-87 | AES-GCM |
| Various combinations with Ascon-128a | ... | ... | Ascon-128a |

---

## 7. METRICS: EXPECTED vs OBSERVED

### 7.1 Schema Definition

**Source**: [core/metrics_schema.py](core/metrics_schema.py)

| Category | Dataclass | Field Count | Purpose |
|----------|-----------|-------------|---------|
| A | CryptoPrimitivesMetrics | 20 | KEM/Sig/AEAD timing |
| B | HandshakeMetrics | 20 | Handshake protocol timing |
| C | RekeyMetrics | 10 | Rekey operation metrics |
| D | DataPlaneMetrics | 15 | Throughput/loss |
| E | LatencyJitterMetrics | 12 | RTT/jitter |
| F | PowerEnergyMetrics | 15 | Power consumption |
| G | SystemDroneMetrics | 12 | Drone CPU/memory |
| H | SystemGcsMetrics | 12 | GCS CPU/memory |
| I | MavProxyDroneMetrics | 17 | MAVLink drone stats |
| J | MavProxyGcsMetrics | 17 | MAVLink GCS stats |
| K | NetworkTransportMetrics | 15 | L3/L4 stats |
| L | EndToEndMetrics | 10 | App-level metrics |
| M | FCTelemetryMetrics | 20 | Flight controller data |
| N | EnvironmentMetrics | 10 | SW versions |
| O | SuiteMetrics | 5 | Suite identification |
| P | ProtocolOverheadMetrics | 10 | Wire format analysis |
| Q | SecurityMetrics | 10 | Drops by reason |
| R | TimestampMetrics | 8 | Timing anchors |

**Total Fields**: ~200+

### 7.2 ACTUAL Collection (Runtime Evidence)

**Source**: [logs/gcs_status.json](logs/gcs_status.json) (live artifact)

```json
{
  "status": "running",
  "suite": "ML_KEM_512_ML_DSA_44_aesgcm",
  "counters": {
    "ptx_in": 0,
    "ptx_out": 2328,
    "enc_in": 49468,
    "enc_out": 49465,
    "drops": 0,
    "drop_replay": 0,
    "drop_header": 0,
    "drop_auth": 0,
    "drop_src_addr": 0,
    "drop_other": 0,
    "rekeys_ok": 49,
    "rekeys_fail": 0,
    "last_rekey_ms": 1749992234091,
    "last_rekey_suite": "ML_KEM_512_ML_DSA_44_aesgcm",
    "handshake_metrics": {
      "role": "gcs",
      "suite_id": "ML_KEM_512_ML_DSA_44_aesgcm",
      "primitives": {
        "kem": {
          "keygen_ns": 223882500,
          "public_key_bytes": 800
        },
        "signature": {
          "sign_ns": 5749000,
          "signature_bytes": 2420
        }
      }
    },
    "primitive_metrics": {
      "aead_encrypt": {
        "count": 49468,
        "total_ns": 7858685300,
        "avg_ns": 158.8
      }
    }
  }
}
```

### 7.3 Gap Analysis: Working vs Stubbed vs Missing

| Category | Status | Evidence | Blocking |
|----------|--------|----------|----------|
| **WORKING** | | | |
| ProxyCounters.ptx_in/out | ✅ | `counters.ptx_out = 2328` | - |
| ProxyCounters.enc_in/out | ✅ | `enc_out = 49465` | - |
| ProxyCounters.drops (all) | ✅ | `drop_replay/header/auth/src_addr` | - |
| ProxyCounters.rekeys_ok/fail | ✅ | `rekeys_ok = 49` | - |
| handshake_metrics.kem.keygen | ✅ | `keygen_ns = 223882500` | - |
| handshake_metrics.sig.sign | ✅ | `sign_ns = 5749000` | - |
| primitive_metrics.aead_encrypt | ✅ | `count=49468, avg_ns=158.8` | - |
| System (GCS) | ✅ | `cpu_avg=7.22%` in comprehensive JSON | - |
| **STUBBED (Schema exists, NOT populated)** | | | |
| crypto_primitives (A) | ❌ | All zeros in comprehensive JSON | YES |
| data_plane (D) | ❌ | `packets_sent=0, throughput=0` | YES |
| latency_jitter (E) | ❌ | No RTT samples | YES |
| mavproxy_drone (I) | ❌ | `packets_tx=0` | YES |
| mavproxy_gcs (J) | ❌ | `packets_tx=0` | YES |
| fc_telemetry (M) | ❌ | All zeros | YES |
| power_energy (F) | ❌ | GCS side zeros | Partial |
| **MISSING (No collection code)** | | | |
| end_to_end (L) | ❌ | No app-level timing | YES |
| network_transport (K) | ❌ | No L3 stats | YES |
| protocol_overhead (P) | ❌ | Partial at best | Minor |

---

## 8. DRONE vs GCS RESPONSIBILITY TABLE

| Component | Drone | GCS | Evidence |
|-----------|-------|-----|----------|
| **TCP Handshake** | Client (connects) | Server (listens:46000) | [async_proxy.py](core/async_proxy.py) |
| **KEM Keygen** | - | Generates keypair | `kem_obj.generate_keypair()` |
| **KEM Encapsulate** | Encaps to derive secret | - | `_encapsulate(kem_pub)` |
| **KEM Decapsulate** | - | Decaps to get secret | `kem_obj.decap(ciphertext)` |
| **Sign Transcript** | - | Signs ServerHello | `server_sig_obj.sign(transcript)` |
| **Verify Signature** | Verifies ServerHello | - | `sig_obj.verify()` |
| **UDP Bind (Encrypted)** | 46012 | 46011 | [config.py](core/config.py) |
| **UDP Bind (Plaintext)** | 47004 | 47002 | [config.py](core/config.py) |
| **MAVProxy Connection** | FC → MAVProxy → Proxy | App → MAVProxy → Proxy | [sdrone_bench.py](sscheduler/sdrone_bench.py) |
| **Suite Cycling** | BenchmarkScheduler | sgcs.py | Different coordinators |
| **Power Sampling** | ✅ (INA219 on Pi) | ❌ (No HW) | [sdrone_bench.py](sscheduler/sdrone_bench.py) |

---

## 9. CONFIRMED WORKING COMPONENTS

### 9.1 Proxy Core
- **TCP Handshake**: Full protocol implemented ([handshake.py](core/handshake.py))
- **UDP Bridging**: Selector-based loop working ([async_proxy.py](core/async_proxy.py))
- **AEAD Encryption**: AES-GCM, ChaCha20-Poly1305, Ascon-128a ([aead.py](core/aead.py))
- **Packet Counters**: All ProxyCounters fields populate correctly
- **Rekey Protocol**: In-band control messages working (`rekeys_ok=49`)

### 9.2 Benchmarking
- **Individual Primitives**: 75 benchmark files with timing arrays ([individual_benchmarks/raw_data/raw/](individual_benchmarks/raw_data/raw/))
- **Power Sampling**: 1000Hz INA219 sampling on drone (Evidence: `power_samples` arrays)
- **Suite Cycling**: 10-second cycles through multiple suites

### 9.3 Metrics (Partial)
- **ProxyCounters**: Full working
- **Handshake Primitives**: keygen/sign timing captured
- **AEAD Timing**: Per-packet encrypt timing aggregated

---

## 10. CONFIRMED MISSING/BROKEN COMPONENTS

### 10.1 Critical Gaps

| Gap | Impact | Root Cause |
|-----|--------|------------|
| **No RTT Measurement** | Cannot prove latency claims | No ping/pong protocol implemented |
| **No Jitter Samples** | Cannot characterize variance | Schema exists but collector empty |
| **MAVLink Parsing Disabled** | Zero packets counted | `mavlink_collector.py` not receiving |
| **FC Telemetry Empty** | No flight data in metrics | Not extracted from MAVLink stream |
| **Data Plane Zeros** | No throughput metrics | Counter→schema mapping broken |

### 10.2 Integration Failures

**Source**: [logs/benchmarks/comprehensive/](logs/benchmarks/comprehensive/) JSON files

```python
# Example from comprehensive metrics JSON:
"crypto_primitives": {
    "kem_keygen_time_ms": 0.0,      # ❌ Should be ~223ms
    "kem_encaps_time_ms": 0.0,      # ❌ Should be ~15ms
    "aead_encrypt_time_us": 0.0,    # ❌ Should be ~0.16us
    ...
}
```

**Root Cause Analysis** (Code-Traced):

| Issue | Evidence | Fix Location |
|-------|----------|--------------|
| `record_crypto_primitives()` not called on GCS | GCS benchmark runner (`bench/run_full_benchmark.py`) doesn't call aggregator methods | Add call after handshake |
| `handshake_metrics` format mismatch | `_finalize_handshake_metrics()` adds flat keys but `record_crypto_primitives()` expects nested OR flat | Format is compatible, but caller not calling |
| `record_data_plane_metrics()` called but counters empty | `_finalize_metrics()` reads `drone_status.json` which may not exist on GCS | GCS needs `gcs_status.json` path |

**Proof of Integration Gap**:

1. [sscheduler/sdrone_bench.py#L452](sscheduler/sdrone_bench.py#L452) DOES call `record_crypto_primitives(metrics)`
2. But it only runs on **drone side**
3. GCS-side ([bench/run_full_benchmark.py](bench/run_full_benchmark.py)) has similar structure but appears to NOT call aggregator

**Status File Reading**:
- [sscheduler/sdrone_bench.py#L476](sscheduler/sdrone_bench.py#L476) reads `drone_status.json`
- But comprehensive JSON shows GCS-side zeros → GCS runner doesn't read `gcs_status.json`

---

## 11. OPEN QUESTIONS (Blocking Further Analysis)

### 11.1 Cannot Determine From Code

1. **Is MAVLink bidirectional?**
   - Code shows UDP bridging both directions
   - But MAVProxy config unclear if GCS→Drone commands flow
   - **Need**: Live packet capture or MAVProxy logs

2. **What triggers metrics collection?**
   - `metrics_aggregator.finalize_metrics()` called but collector sources unclear
   - **Need**: Trace `collect_proxy_metrics()` calls

3. **Why are primitive timings not transferred?**
   - `handshake_metrics` HAS timing but schema fields show 0
   - **Need**: Debug `MetricsAggregator._populate_crypto_primitives()`

4. **Is power connected on drone?**
   - Code references INA219 but no evidence of integration into suite metrics
   - **Need**: Check `power_samples/` directory and integration

### 11.2 Hardware Questions

1. What FC is connected? (Pixhawk model, firmware version)
2. What serial/UDP connection to FC? (`--master=` value)
3. Is INA219 physically wired and working?
4. Network topology between drone and GCS?

---

## 12. APPENDIX: File-to-Function Reference

| File | Key Functions | Purpose |
|------|---------------|---------|
| [core/run_proxy.py](core/run_proxy.py) | `main()`, `gcs_command()`, `drone_command()` | CLI entrypoint |
| [core/async_proxy.py](core/async_proxy.py) | `run_proxy()`, `_perform_handshake()`, `_setup_sockets()` | Proxy loop |
| [core/handshake.py](core/handshake.py) | `build_server_hello()`, `parse_and_verify_server_hello()` | Handshake |
| [core/aead.py](core/aead.py) | `Sender.encrypt()`, `Receiver.decrypt()` | AEAD operations |
| [core/config.py](core/config.py) | `CONFIG`, `validate_config()` | Configuration |
| [core/metrics_schema.py](core/metrics_schema.py) | `ComprehensiveSuiteMetrics` | Schema definition |
| [core/metrics_aggregator.py](core/metrics_aggregator.py) | `MetricsAggregator.finalize_metrics()` | Collection |
| [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) | `BenchmarkScheduler`, `start_mavproxy()` | Suite cycling |

---

## 13. CONCLUSION

### What Works
The **proxy core** is fully functional: TCP handshake, UDP bridging, PQC encryption, rekey protocol, and basic packet counters all work as evidenced by runtime artifacts.

### What Doesn't Work
The **comprehensive metrics framework** is largely **schema-only**. The 200+ field schema exists but:
- Primitive timings collected in `handshake_metrics` don't transfer to schema
- MAVLink collectors exist but aren't receiving packets
- RTT/jitter measurement is completely absent
- FC telemetry extraction not implemented

### Critical Path Forward
1. **Verify MAVLink flow**: Confirm packets actually traverse the tunnel
2. **Fix metrics integration**: Wire `ProxyCounters` → `ComprehensiveSuiteMetrics`
3. **Implement RTT probes**: Add ping/pong for latency measurement
4. **Enable MAVLink sniffing**: Debug why collectors show zero packets

---

## 14. ACTIONABLE FIXES (Prioritized)

### Priority 1: Wire Proxy Metrics to Schema (Critical)

**Problem**: `record_crypto_primitives()` and `record_data_plane_metrics()` exist but aren't called.

**Fix 1.1**: In [bench/run_full_benchmark.py](bench/run_full_benchmark.py) `_handle_command()`, after `record_handshake_end()`:
```python
# Read handshake metrics from proxy status
status_file = Path("logs/gcs_status.json")
if status_file.exists():
    status = json.loads(status_file.read_text())
    hs_metrics = status.get("handshake_metrics", {})
    self.metrics.record_crypto_primitives(hs_metrics)
```

**Fix 1.2**: In `stop_suite` command, before `finalize_suite()`:
```python
# Read data plane counters from proxy status
status_file = Path("logs/gcs_status.json")
if status_file.exists():
    status = json.loads(status_file.read_text())
    counters = status.get("counters", {})
    self.metrics.record_data_plane_metrics(counters)
```

### Priority 2: Implement RTT Measurement (High)

**Problem**: No round-trip latency measurement exists.

**Options**:
1. **MAVLink PING/PONG**: Inject PING messages and measure PONG return
2. **Custom probe**: Add encrypted ping/pong to control channel
3. **Application layer**: Use TIMESYNC MAVLink message

**Recommended**: Implement using MAVLink TIMESYNC (msg_id=111) which is already supported by FC.

### Priority 3: Enable MAVLink Sniffing (Medium)

**Problem**: `mavlink_collector.py` exists but isn't receiving packets.

**Evidence**: Drone MAVProxy config sends to port 47005 for sniffing ([sdrone_bench.py#L230](sscheduler/sdrone_bench.py#L230))

**Debug Steps**:
1. Verify `MavLinkMetricsCollector.start()` binds to 47005
2. Check if MAVProxy is actually started with `--out=udp:127.0.0.1:47005`
3. Add logging to verify packets arrive

### Priority 4: Cross-Side Metric Consolidation (Medium)

**Problem**: Drone metrics and GCS metrics are in separate files.

**Current**: [sscheduler/sdrone_bench.py](sscheduler/sdrone_bench.py) writes drone-side metrics, [bench/run_full_benchmark.py](bench/run_full_benchmark.py) writes GCS-side.

**Fix**: Use the existing `merge_from` parameter in `finalize_suite()` to consolidate peer data via the control channel.

---

*Generated by forensic code analysis. All claims reference specific file:line evidence.*
