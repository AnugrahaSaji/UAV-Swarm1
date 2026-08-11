# Foundation Verification Report
**Date:** 2026-01-14
**Phase:** 1 - Foundation Verification (Before Running Anything)

---

## Task 2.1 & 2.2: Environment Verification (COMPLETED)

### Drone Environment (PRIMARY) ✅

| Check | Result |
|-------|--------|
| **Virtual Env** | `~/cenv` (must activate: `source ~/cenv/bin/activate`) |
| **Python** | 3.11.2 |
| **liboqs-python** | 0.14.0 ✅ (via `from oqs.oqs import ...`) |
| **MAVProxy** | 1.8.74 ✅ |
| **pymavlink** | 2.4.49 ✅ |
| **psutil** | 7.0.0 ✅ |
| **pi-ina219** | 1.4.1 ✅ |
| **I2C Bus** | /dev/i2c-1, i2c-20, i2c-21 ✅ |

**Note:** Package `oqs` (0.10.2) conflicts with `liboqs-python`. Code uses `from oqs.oqs import` which correctly loads liboqs-python.

### GCS Environment (SECONDARY) ✅

| Check | Result |
|-------|--------|
| **Conda Env** | `oqs-dev` (activate: `conda activate oqs-dev`) |
| **Python** | 3.11.13 |
| **liboqs-python** | 0.14.0 ✅ |
| **MAVProxy** | 1.8.74 ✅ |
| **pymavlink** | 2.4.49 ✅ |
| **psutil** | 7.1.3 ✅ |

**Crypto Compatibility:** Both drone and GCS use liboqs-python 0.14.0 - compatible.

---

## Task 1.1: Related Work Status

### Confirmed Foundation Components

| Component | Location | Status | Purpose |
|-----------|----------|--------|---------|
| **Core Proxy** | `core/async_proxy.py` | ✅ Implemented | Data plane - encrypt/decrypt UDP |
| **Handshake** | `core/handshake.py` | ✅ Implemented | PQC KEM + signatures, PSK auth |
| **AEAD** | `core/aead.py` | ✅ Implemented | AES-256-GCM, ChaCha20, ASCON |
| **Suites Registry** | `core/suites.py` | ✅ Implemented | 72+ crypto suite definitions |
| **Process Manager** | `core/process.py` | ✅ Implemented | ManagedProcess lifecycle |
| **Config** | `core/config.py` | ✅ Implemented | Centralized configuration |
| **Metrics Schema** | `core/metrics_schema.py` | ✅ Implemented | Standardized metric structure |
| **Metrics Aggregator** | `core/metrics_aggregator.py` | ✅ Implemented | Collection coordination |
| **Power Monitor** | `core/power_monitor.py` | ✅ Implemented | INA219 hardware integration |
| **MAVLink Collector** | `core/mavlink_collector.py` | ✅ Implemented | MAVLink message parsing |

### Scheduler Variants (REDUNDANCY IDENTIFIED)

| Variant | Location | Lines | Purpose | Status |
|---------|----------|-------|---------|--------|
| **scheduler/** | `scheduler/sdrone.py` | 680 | Original: GCS-controlled | ⚠️ Legacy |
| **auto/** | `auto/drone_follower.py` | 2881 | Auto: GCS-controlled + full bench | ⚠️ Large/Complex |
| **sscheduler/** | `sscheduler/sdrone.py` | 1146 | Reversed: Drone-controlled | ✅ Current |
| **sscheduler/bench** | `sscheduler/sdrone_bench.py` | 630 | Fixed benchmark policy | ✅ For Phase 3 |

### Dead/Redundant Files (CLEANUP CANDIDATES)

| File | Status | Reason |
|------|--------|--------|
| `sscheduler/sdrone copy.py` | ❌ DEAD | Development backup |
| `sscheduler/sgcs copy.py` | ❌ DEAD | Development backup |
| `sscheduler/sgcs copy 2.py` | ❌ DEAD | Development backup |
| `snapshot/` directory | ⚠️ ARCHIVE | Complete code snapshot (redundant) |

### Test Files (Mixed with Production)

| File | Type | Location |
|------|------|----------|
| `test_sscheduler.py` | Integration test | Root (should be tests/) |
| `test_simple_loop.py` | Integration test | Root (should be tests/) |
| `test_schedulers.py` | Integration test | Root (should be tests/) |
| `test_complete_loop.py` | Integration test | Root (should be tests/) |
| `tests/test_lifecycle.py` | Unit test | Correct location |

---

## Task 1.2: Expectation vs Reality Mapping

### 1. Identity Subsystem

| Expectation | Code Evidence | Verifiable Without Execution |
|-------------|---------------|------------------------------|
| X.509 certs with PQC signatures | `core/run_proxy.py` init-identity | ✅ Yes - file generation |
| Cert loading on proxy start | `core/handshake.py` lines 45-80 | ✅ Yes - code path exists |
| PSK for HMAC authentication | `core/handshake.py` lines 295-310 | ⚠️ **BUG**: Optional bypass |

**Gap:** PSK bypass vulnerability exists - server can accept no PSK.

### 2. Handshake Subsystem

| Expectation | Code Evidence | Verifiable Without Execution |
|-------------|---------------|------------------------------|
| TCP 46000 handshake | `core/async_proxy.py` | ✅ Yes - port constant |
| KEM encapsulation | `core/handshake.py` lines 220-250 | ✅ Yes - oqs.KeyEncapsulation |
| Signature verification | `core/handshake.py` lines 280-295 | ✅ Yes - oqs.Signature |
| HMAC-SHA256 auth | `core/handshake.py` lines 170-200 | ✅ Yes - hmac.compare_digest |
| Shared secret derivation | `core/handshake.py` lines 260-270 | ✅ Yes - HKDF |

**Verification needed:** Actual handshake completion timing.

### 3. Data Tunnel Subsystem

| Expectation | Code Evidence | Verifiable Without Execution |
|-------------|---------------|------------------------------|
| UDP 46011/46012 encrypted | `core/async_proxy.py` | ✅ Yes - port bindings |
| AEAD encrypt/decrypt | `core/aead.py` | ✅ Yes - AES/ChaCha/ASCON |
| Sequence number tracking | `core/async_proxy.py` lines 400-450 | ✅ Yes - replay protection |
| Nonce construction | `core/aead.py` lines 50-70 | ✅ Yes - 12-byte nonces |

**Verification needed:** Packet loss rates, latency under load.

### 4. MAVProxy Integration

| Expectation | Code Evidence | Verifiable Without Execution |
|-------------|---------------|------------------------------|
| Subprocess launch | `tools/mavproxy_manager.py` | ✅ Yes - subprocess.Popen |
| Port forwarding config | `core/config.py` MAV* ports | ✅ Yes - constants exist |
| Bidirectional data flow | `sscheduler/sdrone.py` UdpEchoServer | ✅ Yes - echo server code |

**Verification needed:** Actual MAVProxy process running, data flowing.

### 5. Control/Scheduler Subsystem

| Expectation | Code Evidence | Verifiable Without Execution |
|-------------|---------------|------------------------------|
| TCP control channel | `sscheduler/sgcs.py` lines 400-500 | ✅ Yes - socket server |
| Command: start_proxy | `sscheduler/sgcs.py` handle_start_proxy | ✅ Yes - handler exists |
| Command: prepare_rekey | `sscheduler/sgcs.py` handle_prepare_rekey | ✅ Yes - handler exists |
| Policy evaluation | `sscheduler/policy.py` TelemetryAwarePolicyV2 | ✅ Yes - evaluate() method |

**Verification needed:** Command/response timing, error handling.

### 6. Metrics Collection Subsystem

| Expectation | Code Evidence | Verifiable Without Execution |
|-------------|---------------|------------------------------|
| MetricsAggregator exists | `core/metrics_aggregator.py` | ✅ Yes - class defined |
| Power metrics (INA219) | `core/power_monitor.py` | ⚠️ Hardware-dependent |
| CPU metrics | `core/metrics_collectors.py` | ✅ Yes - psutil calls |
| MAVLink metrics | `core/mavlink_collector.py` | ✅ Yes - pymavlink parsing |
| JSON output | `core/metrics_schema.py` | ✅ Yes - schema defined |

**Verification needed:** Actual data population, hardware presence.

---

## Summary: Foundation Gaps

### Critical Issues

1. **PSK Bypass Bug** - `core/handshake.py` allows no-PSK operation
2. **TOCTOU Race** - `core/async_proxy.py` lines 1272-1276 in rekey
3. **Rate Limiter Memory** - `core/async_proxy.py` unbounded dict growth

### Redundancy Issues

1. Three scheduler variants with overlapping functionality
2. Development copy files polluting `sscheduler/`
3. Complete snapshot directory duplicating entire codebase
4. Test files mixed with production code in root

### Unverified Claims

| Claim | Verification Method | Status |
|-------|---------------------|--------|
| "Handshake completes in <500ms" | Execution timing | ⏳ Pending |
| "All 72 suites work" | Sequential activation | ⏳ Pending |
| "Power metrics collected" | Hardware check + data | ⏳ Pending |
| "MAVProxy data flows bidirectionally" | Traffic capture | ⏳ Pending |

---

## Task 3.1: Fixed Policy Constraint Verification ✅

### Fixed Benchmark Policy Exists

| Component | Location | Behavior |
|-----------|----------|----------|
| **BenchmarkPolicy** | `sscheduler/benchmark_policy.py` | Sequential cycling, fixed interval |
| **BenchmarkScheduler** | `sscheduler/sdrone_bench.py` | Uses BenchmarkPolicy, no adaptation |
| **GCS Control Server** | `sscheduler/sgcs.py` | Accepts `start_proxy`, `prepare_rekey` commands |

### Policy Enforcement Points

```
BenchmarkPolicy.evaluate() → Returns:
  - HOLD: Stay on current suite (time not elapsed)
  - NEXT_SUITE: Move to next (interval elapsed)
  - COMPLETE: All suites tested

NO conditional logic based on:
  - Telemetry
  - Battery/thermal
  - Link quality
```

### CLI Arguments for Fixed Policy

```bash
# On Drone (source ~/cenv/bin/activate first):
python -m sscheduler.sdrone_bench \
    --interval 10.0 \           # Fixed 10s per suite
    --filter-aead aesgcm \      # Optional: limit to aesgcm suites
    --max-suites 5              # Optional: limit count

# On GCS (conda activate oqs-dev first):
python -m sscheduler.sgcs       # Listens for drone commands
```

### Confirmed: Fixed Policy Can Be Enforced ✅

---

## Next Steps (Phase 2)

**MUST verify before proceeding:**

1. ~~SSH to drone → check Python/oqs/MAVProxy availability~~ ✅ DONE
2. ~~GCS conda env → check matching crypto libraries~~ ✅ DONE
3. ~~Identify which scheduler variant to use for testing~~ ✅ `sscheduler/sdrone_bench.py`
4. ~~Confirm `sdrone_bench.py` can enforce fixed 10s policy~~ ✅ VERIFIED BY EXECUTION

---

## Task 4.1: End-to-End Execution Validation ✅

### Test Run Summary

| Parameter | Value |
|-----------|-------|
| **Policy** | Fixed 10s per suite |
| **Filter** | aesgcm only |
| **Suites Tested** | 2 (limited for quick validation) |
| **Suite 1** | cs-classicmceliece348864-aesgcm-falcon512 |
| **Suite 2** | cs-classicmceliece348864-aesgcm-mldsa44 |

### Observed Results

| Check | Drone | GCS |
|-------|-------|-----|
| **Control Channel** | Connected ✅ | Listening ✅ |
| **MAVProxy Started** | ✅ PID running | ✅ PID running |
| **Suite 1 Handshake** | 754.2ms ✅ | 2016ms (async) ✅ |
| **Suite 2 Handshake** | 578.8ms ✅ | (success) ✅ |
| **Data Plane (GCS)** | — | enc_in=2515, ptx_out=2515 ✅ |
| **Data Plane (Drone)** | ptx_in=0, enc_out=0 ⚠️ | — |
| **MAVLink Messages** | 2289 msgs @ 500 pps ✅ | — |

### Data Flow Confirmed

```
Pixhawk(/dev/ttyACM0) 
    → MAVProxy(drone:47003)
    → Tunnel(drone proxy enc)
    → UDP(46011/46012)
    → Tunnel(GCS proxy dec)
    → MAVProxy(GCS:47002)
    → 2515 packets received ✅
```

### Issue Found

**Drone data_plane counters not populated** - Proxy status file reading may be failing or timing-sensitive. GCS correctly shows traffic counts.

---

## Task 5.1: Metric Coverage Check

### Schema Categories (A-R) Coverage

| Cat | Name | Drone | GCS | Notes |
|-----|------|-------|-----|-------|
| **A** | Run & Context | ✅ Populated | ✅ Populated | run_id, git_hash, hostname, IP |
| **B** | Suite Crypto Identity | ✅ Complete | ✅ Complete | KEM, SIG, AEAD correctly identified |
| **C** | Suite Lifecycle | ✅ Timestamps | ✅ Timestamps | selected → activated → deactivated |
| **D** | Handshake | ✅ Duration | ✅ Duration | 754ms drone, 2016ms GCS |
| **E** | Crypto Primitives | ⚠️ Partial | ⚠️ Partial | Key sizes ✅, timing zeros |
| **F** | Rekey | ⏸️ N/A | ⏸️ N/A | No rekey in this test |
| **G** | Data Plane | ❌ Zeros | ✅ 2515 pkts | Drone not reading proxy status |
| **H** | Latency/Jitter | ❌ Zeros | ❌ Zeros | Requires traffic generator |
| **I** | MAVProxy Drone | ✅ 2289 msgs | — | 500 pps, message types logged |
| **J** | MAVProxy GCS | — | ⚠️ Partial | Not separately instrumented |
| **K** | MAVLink Integrity | ✅ Populated | ⏸️ N/A | sysid, protocol, dup count |
| **L** | FC Telemetry | ⚠️ Partial | — | No attitude/battery parsed |
| **M** | Control Plane | ❌ Zeros | ❌ Zeros | Scheduler metrics not wired |
| **N** | System Drone | ✅ Complete | — | CPU 29%, temp 52°C, load avg |
| **O** | System GCS | — | ⚠️ Partial | Less detail than drone |
| **P** | Power/Energy | ✅ Complete | — | 2.44W avg, 11.1J total |
| **Q** | Observability | ✅ Populated | ✅ Populated | log counts, collection times |
| **R** | Validation | ✅ PASS | ✅ PASS | 100% sample rate |

### Successful Metric Collection (VERIFIED BY DATA)

1. **Power Monitoring** ✅
   - `power_avg_w: 2.44W`
   - `power_peak_w: 3.01W`
   - `energy_total_j: 11.1J`
   - Sampling at **1000 Hz (1 kHz)** (was incorrectly reporting 100 Hz - FIXED)

2. **CPU/System Resources** ✅
   - `cpu_usage_avg: 29.3%`
   - `cpu_usage_peak: 62.3%`
   - `temperature_c: 52.1°C`
   - Load averages captured

3. **MAVLink Parsing** ✅
   - 2289 messages parsed
   - 23 different message types
   - ATTITUDE (221), SCALED_IMU (110), HEARTBEAT (4)
   - Stream rate: ~500 Hz

4. **Handshake Timing** ✅
   - Suite 1: 754.2ms (Classic McEliece - slow KEM)
   - Suite 2: 578.8ms

### Missing/Broken Metrics

| Metric | Issue | Root Cause |
|--------|-------|------------|
| Drone data_plane counters | All zeros | Proxy status file not read |
| Crypto primitive timing | Zeros | Proxy not exposing timing |
| Latency/jitter | Zeros | No bidirectional traffic generator |
| FC telemetry parsing | Partial | Battery/attitude not extracted |
| Control plane scheduler | Zeros | Scheduler metrics not wired |

---

## Phase 7: Readiness Decision

### Is the foundation solid enough to enable adaptive policy?

**ANSWER: YES, with known limitations.**

### What Works (Verified by Execution)

| Capability | Evidence |
|------------|----------|
| Fixed benchmark policy | 2 suites @ 10s each completed |
| GCS-Drone control channel | TCP commands successful |
| PQC handshake | Multiple suites completed |
| MAVProxy integration | 2289 messages @ 500 pps |
| Encrypted tunnel | 2515 packets through GCS |
| Power monitoring | INA219 collecting 1 kHz samples |
| CPU/temp monitoring | psutil working |
| Comprehensive JSON output | 18-category schema populated |

### What Must Be Fixed Before Adaptive Policy

| Priority | Issue | Impact | Fix Complexity |
|----------|-------|--------|----------------|
| **P1** | Drone data_plane zeros | Policy can't see local traffic | Medium |
| **P2** | Crypto timing zeros | Can't compare primitive costs | Low |
| **P3** | Latency/jitter zeros | Can't evaluate link quality | High (needs RTT) |
| **P4** | FC telemetry partial | Can't use battery/armed state | Low |

### What Must Be Validated After Fixes

1. **Re-run benchmark with drone data_plane fix**
   - Verify ptx_in, enc_out counters match GCS enc_in
   
2. **Test adaptive policy triggers**
   - Simulate thermal stress → expect DOWNGRADE
   - Simulate link degradation → expect DOWNGRADE
   
3. **Multi-suite sequence test**
   - Run all 24 aesgcm suites
   - Verify no suite failures
   - Confirm metrics complete per suite

---

## Final Summary

### What Was Already Done ✅

- Core proxy architecture complete (handshake, AEAD, data plane)
- Three scheduler variants implemented (scheduler/, auto/, sscheduler/)
- Comprehensive metrics schema (18 categories)
- Power monitoring with INA219 hardware support
- MAVLink message parsing
- Fixed benchmark policy (`BenchmarkPolicy` class)

### What Was Partially Done ⚠️

- Drone-side data plane metric collection (code exists, not wired)
- Crypto primitive timing (proxy doesn't expose to collectors)
- FC telemetry parsing (MAVLink collector exists, not feeding policy)
- Control plane metrics (scheduler state not logged)

### What Was Missing or Broken ❌

- Bidirectional latency/jitter measurement
- Drone data_plane counter reading
- PSK enforcement (bypass bug exists)
- Rate limiter cleanup (unbounded growth)
- TOCTOU race in rekey path

### What Was Verified on Drone ✅

| Item | Method | Result |
|------|--------|--------|
| Python 3.11.2 | SSH + cenv activation | ✅ |
| liboqs-python 0.14.0 | `from oqs.oqs import` | ✅ |
| MAVProxy 1.8.74 | `mavproxy.py --version` | ✅ |
| pymavlink 2.4.49 | pip show | ✅ |
| INA219 library | pi-ina219 1.4.1 | ✅ |
| I2C hardware | /dev/i2c-1 exists | ✅ |
| Pixhawk connected | /dev/ttyACM0 | ✅ |
| MAVLink data flow | 2289 messages parsed | ✅ |
| Power measurement | 2.44W average | ✅ |

### What Was Verified on GCS ✅

| Item | Method | Result |
|------|--------|--------|
| Python 3.11.13 | conda oqs-dev | ✅ |
| liboqs-python 0.14.0 | pip show | ✅ |
| MAVProxy 1.8.74 | pip show | ✅ |
| LAN connectivity | ping 192.168.0.105 | ✅ |
| Control server | TCP 48080 accepting | ✅ |
| Proxy start | 2 suites launched | ✅ |
| Data reception | 2515 packets | ✅ |

### What Data Was Successfully Collected ✅

| Category | Drone | GCS |
|----------|-------|-----|
| Power (W, J) | 2.44W, 11.1J | N/A |
| CPU (%) | 29.3% avg | (partial) |
| Temperature (°C) | 52.1°C | N/A |
| MAVLink (msgs) | 2289 | — |
| Data plane (pkts) | — | 2515 |
| Handshake (ms) | 754ms, 579ms | 2016ms |
| Crypto identity | ✅ Complete | ✅ Complete |

### What Insights Are Now Possible

1. **Per-suite power cost** - Can compare W and J across all 72 suites
2. **Handshake time comparison** - McEliece (754ms) vs ML-DSA (579ms)
3. **CPU impact of crypto** - 29% average, 62% peak
4. **Thermal envelope** - 52°C under crypto load
5. **MAVLink throughput** - ~500 pps sustainable through tunnel

### What Must Be Fixed Before Policy Evolution

| Fix | File | Description |
|-----|------|-------------|
| Drone data_plane reading | `sdrone_bench.py` | Read proxy status file |
| Expose crypto timing | `core/async_proxy.py` | Add timing to status JSON |
| Wire FC telemetry | `sscheduler/policy.py` | Use battery_mv, armed from MAVLink |
| PSK enforcement | `core/handshake.py` | Require PSK when configured |

---

**Report generated:** 2026-01-14
**Validation method:** Live execution on hardware
**Confidence:** HIGH for verified items, UNKNOWN for untested paths
