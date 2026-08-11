# Secure-Tunnel Architecture Summary — VTC Fall 2026

Generated: 2026-03-03
Source: Deterministic codebase analysis (no runtime inference)

---

## 1. Functional Architecture

### 1.1 System Overview

The secure-tunnel system implements a post-quantum cryptographic (PQC)
overlay for UAV command-and-control (C2) links. It operates as a
userspace UDP proxy encrypting MAVLink telemetry between a drone
(Raspberry Pi 4) and a Ground Control Station (GCS).

```
+----------------+     +----------------+     +----------------+
|  MAVProxy /    | UDP |  Drone Proxy   | UDP |   GCS Proxy    | UDP +----------+
|  Flight Ctrl   |---->|  (core/)       |---->|  (core/)       |---->| GCS App  |
|                |<----|  encrypt       |<----|  decrypt       |<----+          |
+----------------+     +----------------+     +----------------+     +----------+
                          ^                    ^
                          | TCP control        | TCP control
                       +--+--------------------+--+
                       |     sscheduler/          |
                       |   sdrone.py <-> sgcs.py  |
                       |   (suite selection,      |
                       |    rekey orchestration,   |
                       |    DDoS detector mgmt)    |
                       +--------------------------+
```

### 1.2 Module Map

| Module | Path | Role |
|--------|------|------|
| **Transport Proxy** | `core/async_proxy.py` | Selectors-based UDP proxy; encrypt/decrypt pipeline; rekey execution |
| **AEAD Cipher Layer** | `core/aead.py` | AES-256-GCM, ChaCha20-Poly1305, Ascon-128a; wire framing; replay detection |
| **Handshake Protocol** | `core/handshake.py` | 3-round PQC authenticated key exchange (KEM + Signature) over TCP |
| **HKDF Key Derivation** | `core/handshake.py` (L407-442) | HKDF-SHA256: salt=`pq-drone-gcs|hkdf|v1`, produces 2x32-byte directional keys |
| **Suite Registry** | `core/suites.py` | Combinatorial KEM x SIG x AEAD matrix (72+ suites) |
| **Rekey State Machine** | `core/policy_engine.py` | Two-phase commit (PREPARE -> COMMIT) for live suite switching |
| **Scheduler (Drone)** | `sscheduler/sdrone.py` | Policy-driven suite selection loop @ 1 Hz |
| **Scheduler (GCS)** | `sscheduler/sgcs.py` | Follower: starts/stops proxy on drone command |
| **Decision Engines** | `sscheduler/policy.py` | TelemetryAwarePolicyV2 (single-axis), EnergyAwarePolicy (MDEAS 3-axis) |
| **Benchmark Policy** | `sscheduler/benchmark_policy.py` | Deterministic sequential suite cycling for measurement |
| **Power Monitor** | `core/power_monitor.py` | INA219 I2C, RPi5 PMIC sysfs, synthetic backends |
| **Metrics Aggregator** | `core/metrics_aggregator.py` | 18-category schema (A-R), per-suite collection |
| **MAVLink Collector** | `core/mavlink_collector.py` | UDP sniffing, heartbeat/sequence/jitter tracking |
| **DDoS Detection** | `ddos/` | XGBoost, TST, LightGBM, RF classifiers on CICIoT-2023 features |
| **Detector Manager** | `sscheduler/detector_manager.py` | Subprocess lifecycle for detector models |

---

## 2. Cryptographic Primitive Inventory

### 2.1 KEM Primitives (via liboqs)

| Algorithm | NIST Level | OQS Binding | Pub Key (B) | Ciphertext (B) |
|-----------|-----------|-------------|-------------|-----------------|
| ML-KEM-512 | L1 | ML-KEM-512 | 800 | ~768 |
| ML-KEM-768 | L3 | ML-KEM-768 | 1,184 | ~1,088 |
| ML-KEM-1024 | L5 | ML-KEM-1024 | 1,568 | ~1,568 |
| HQC-128 | L1 | HQC-128 | variable | variable |
| HQC-192 | L3 | HQC-192 | variable | variable |
| HQC-256 | L5 | HQC-256 | variable | variable |
| Classic-McEliece-348864 | L1 | Classic-McEliece-348864 | ~262 KB | variable |
| Classic-McEliece-460896 | L3 | Classic-McEliece-460896 | ~525 KB | variable |
| Classic-McEliece-8192128 | L5 | Classic-McEliece-8192128 | ~1.3 MB | variable |

### 2.2 Signature Primitives (via liboqs)

| Algorithm | NIST Level | OQS Binding | Sig Size (B) |
|-----------|-----------|-------------|--------------|
| ML-DSA-44 | L1 | ML-DSA-44 | ~1,458 |
| ML-DSA-65 | L3 | ML-DSA-65 | ~2,420 |
| ML-DSA-87 | L5 | ML-DSA-87 | ~3,293 |
| Falcon-512 | L1 | Falcon-512 | ~666 |
| Falcon-1024 | L5 | Falcon-1024 | ~1,236 |
| SPHINCS+-SHA2-128s | L1 | SPHINCS+-SHA2-128s-simple | ~17,088 |
| SPHINCS+-SHA2-192s | L3 | SPHINCS+-SHA2-192s-simple | ~35,664 |
| SPHINCS+-SHA2-256s | L5 | SPHINCS+-SHA2-256s-simple | ~49,856 |

### 2.3 AEAD Ciphers

| Algorithm | Key (B) | Nonce (B) | Tag (B) | Backend |
|-----------|---------|-----------|---------|---------|
| AES-256-GCM | 32 | 12 | 16 | OpenSSL 3.5.4 (software on RPi4, no AES-NI) |
| ChaCha20-Poly1305 | 32 | 12 | 16 | OpenSSL 3.5.4 (NEON vectorized on RPi4) |
| Ascon-128a | 16 | 16 | 16 | Native C (ascon-c v1.2 opt64) via ctypes |

---

## 3. Data Flow Description

### 3.1 Handshake Flow (3-Round)

```
 +--------+                           +--------+
 |  GCS   |                           | Drone  |
 |(Server)|                           |(Client)|
 +---+----+                           +---+----+
     |                                    |
     |  (1) ServerHello (TCP)             |
     |  - KEM pub key (keygen)            |
     |  - Challenge (8B random)           |
     |  - Signature over transcript       |
     | ---------------------------------> |
     |                                    |
     |                                    | Verify signature
     |                                    | KEM encapsulate -> (ct, ss)
     |                                    |
     |  (2) ClientEphemeral (TCP)         |
     |  - KEM ciphertext                  |
     | <--------------------------------- |
     |                                    |
     | KEM decapsulate -> ss              |
     |                                    |
     |  (3) Both derive transport keys:   |
     |     HKDF-SHA256(ss, salt, info)    |
     |     -> k_d2g (32B) + k_g2d (32B)  |
     |                                    |
     |  UDP tunnel active                 |
     +------------------------------------+
```

### 3.2 Data Plane Encryption Pipeline

```
Plaintext (MAVLink) ->
  Sender.encrypt(plaintext):
    seq++
    header = pack(version, kem_id, sig_id, session_id, seq, epoch)  [22 bytes]
    nonce  = derive(epoch, seq)  [12 bytes; zero-padded to 16 for Ascon]
    ct     = AEAD.encrypt(nonce, plaintext, AAD=header)
    wire   = header || ct
-> UDP send(wire)
-> UDP recv(wire)
-> Receiver.decrypt(wire):
    header = wire[0:22]
    verify session_id, epoch, version
    check_replay(seq)  [sliding window, default 1024]
    nonce = derive(epoch, seq)
    plaintext = AEAD.decrypt(nonce, wire[22:], AAD=header)
-> Forward to local application
```

### 3.3 Rekey Pipeline

```
Scheduler loop (1 Hz) -> policy.evaluate() -> action
  if action == SWITCH_SUITE or SWITCH_AEAD:
    1. send_gcs_command("prepare_rekey")
    2. stop local proxy
    3. start GCS proxy with new suite
    4. start local proxy with new suite
    5. new TCP handshake executes (3-round)
    6. new AEAD keys installed atomically
    7. epoch incremented; seq reset to 0
```

---

## 4. Measurement Pipeline Description

### 4.1 Timing Measurement

**Primitive-level (v2-1.8ghz benchmarks):**
- Per-operation: `time.perf_counter_ns()` before/after each call
- Arrays of 100 individual timing samples per algorithm x operation
- Warmup: first iteration is warmup (not explicitly discarded in data)
- GC: not documented as disabled for v2-1.8ghz

**AEAD-level (power_aead_benchmark):**
- Two-pass methodology (process-aead-benchmark.md):
  - Pass 1 (TIMING): `gc.disable()`, 10,000 iterations, `perf_counter_ns`
  - Pass 2 (POWER): `gc.enable()`, 10,000 iterations, background INA219 sampling
- Warmup: 500 iterations discarded before each pass
- Platform: RPi4 @ 1.8 GHz, CPU governor: performance

### 4.2 Power Measurement

**INA219 Configuration:**
- I2C address: 0x40
- Bus: 1
- Shunt resistor: 0.1 ohm
- Gain correction: VBUS_GAIN = 1.22 (clone chip ADC drift compensation)
- Sampling: ~88-101 Hz during AEAD benchmarks; 1000 Hz for v2-1.8ghz

**Idle Baseline:**
- Measured: 10s, 1000 samples at ~100 Hz
- Baseline power: 2.961 W (5.157V, 0.574A)
- **NOT subtracted** from reported values -- raw board-level power reported

**Energy Calculation:**
```
E_op = (P_avg * T_total) / N * 10^6   [uJ]
```
Where P_avg = mean INA219 power during Pass 2, T_total = wall-clock, N = iterations.

### 4.3 DDoS Overhead Measurement

**Three-phase design (bench_ddos_v2.py):**
1. BASELINE: 72 suites x 10s each, no detector
2. +XGBoost: same with XGBoost subprocess active
3. +TST: same with TST subprocess active (5-min warmup)

**Per-suite metrics:** handshake timing, throughput, CPU%, power (INA219), temperature

### 4.4 Telemetry Pipeline (Flight Operations)

```
Drone:
  LocalMonitor (1 Hz): battery, temp, CPU, armed state
  MAVLinkCollector: heartbeat count, seq gaps, jitter
  ProxyCounters: enc/dec timing (ns), packet counts, drop counts

GCS:
  GcsMetrics: MAVLink rx_pps, gap_p95, jitter
  -> Batched UDP reports -> TelemetryWindow on drone

Scheduler:
  DecisionInput (28 fields) -> policy.evaluate() -> action + reasons
```

---

## 5. Verified Dataset Inventory

| Dataset | Iterations | Power Hz | Platform | Idle Sub | Date |
|---------|-----------|----------|----------|----------|------|
| power_aead_benchmark.csv | 10,000 | ~88-101 | RPi4 1.8GHz | No | 2026 |
| v2-1.8ghz (KEM/SIG/AEAD) | 100 | 1,000 | RPi4 1.8GHz | No | 2026-01-16 |
| bench_ddos_results (latest) | 72 suites x 10s | INA219 | RPi4 1.8GHz | No | 2026-03-02 |
| suite_benchmarks | ~200/suite | INA219 | RPi4 1.8GHz | No | 2026 |
| ddos model inference | 1,398-2,229 | 15s window | RPi4 1.8GHz | Measured | 2026 |

---

## 6. Identified Data Limitations

1. **Suite handshake timing (3005 ms) is network-dominated**: Measured over Tailscale VPN with ~1s RTT. Does not represent local or edge deployment latency. Crypto-only handshake time must be reconstructed from primitive benchmarks.

2. **v2-1.8ghz uses only 100 iterations**: Lower statistical power than the 10,000-iteration AEAD benchmarks. Coefficient of variation for some operations (e.g., McEliece keygen) exceeds 60%.

3. **INA219 measures board-level power**: Includes CPU + DRAM + GPU + I/O. Single-core crypto operations add only 0.08-0.21W above baseline. Energy-per-operation is the meaningful metric.

4. **INA219 clone chip**: Documented -16% ADC drift compensated by VBUS_GAIN=1.22 correction factor.

5. **Ascon-128a native vs. pip interop bug**: BUG-ASCON-COMPAT (2026-02-17) -- NIST SP 800-232 reference C code and pip pyascon use different algorithms. Cross-node decrypt fails if backends mismatch.

6. **No AES hardware acceleration**: RPi4 Cortex-A72 lacks ARMv8 Crypto Extensions. AES-256-GCM runs in software table-lookup mode. ChaCha20-Poly1305 benefits from NEON.

7. **Idle power NOT subtracted**: All reported power/energy values include baseline board draw (~2.96W). This is consistent across datasets but must be noted.

8. **DDoS overhead power ordering violations**: 20/72 suites show power ordering violations (baseline > xgb or xgb > tst not satisfied), suggesting measurement noise at these power deltas.

---

## 7. Scheduler Decision Architecture

### 7.1 MDEAS (Multi-Dimensional Energy-Aware Scheduling)

Three independent decision axes, evaluated at 1 Hz:

| Axis | Controls | Switching Cost | Decision Rate |
|------|----------|---------------|---------------|
| AEAD Selection | Data-plane cipher | Low (same-suite AEAD swap) | Per-stress event |
| Security Level | L1/L3/L5 (KEM+SIG tier) | High (full rekey) | Conservative |
| DDoS Detector | NONE/XGBOOST/TST process | Medium (subprocess lifecycle) | Per-thermal/CPU event |

### 7.2 Break-Even Analysis

Before switching AEAD, the scheduler computes:
```
break_even_s = rekey_cost_ns / (saving_per_pkt_ns * pkt_rate_hz * 2)
```
Switch permitted if break_even <= 120s (stress) or >= 30s (normal).

### 7.3 AEAD Cost Profiles (Benchmark-Seeded)

| AEAD | encrypt_ns | decrypt_ns | power_w | temp_delta_c |
|------|-----------|-----------|---------|-------------|
| aesgcm | 66,900 | 73,600 | 3.595 | -0.1 |
| chacha20poly1305 | 63,200 | 70,100 | 3.580 | 0.0 |
| ascon128a | 1,327,100 | 960,500 | 3.558 | +1.5 |

---

*End of architecture summary. Awaiting confirmation to proceed to Phase 4 (Results and Analysis LaTeX generation).*
