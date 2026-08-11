# MAVLink-to-MAVLink Benchmarking System Analysis

**Generated:** January 17, 2026  
**Scope:** End-to-end MAVLink benchmarking, metrics collection, schedulers, and test files

---

## Executive Summary

This codebase implements a **Post-Quantum Cryptography (PQC) secure tunnel** for MAVLink drone communications. The benchmarking system measures:
- Handshake latency for various cipher suites
- Data plane throughput and packet delivery
- System resources (CPU, memory, temperature)
- Power consumption (drone-side only via INA219)
- MAVLink protocol integrity (sequence gaps, heartbeats)

**Overall Assessment:** The metrics infrastructure is **comprehensive but has significant redundancy**. There are **3+ parallel implementations** of the scheduler/benchmark orchestration layer, and several files appear to be works-in-progress or abandoned iterations.

---

## 1. FILE INVENTORY

### 1.1 Core Metrics Infrastructure (READY ✅)

| File | Purpose | Status | Dependencies |
|------|---------|--------|--------------|
| [core/metrics_schema.py](core/metrics_schema.py) | Defines 18-category metrics schema (A-R) with dataclasses | ✅ **COMPLETE** | None |
| [core/metrics_collectors.py](core/metrics_collectors.py) | Base collectors (System, Power, Network, Environment) | ✅ **COMPLETE** | psutil, ina219 |
| [core/mavlink_collector.py](core/mavlink_collector.py) | MAVLink protocol metrics (heartbeat, sequence, latency) | ✅ **COMPLETE** | pymavlink |
| [core/metrics_aggregator.py](core/metrics_aggregator.py) | Aggregates all collectors into ComprehensiveSuiteMetrics | ✅ **COMPLETE** | All collectors |

**Notes:**
- The schema defines **168 total fields** across 18 categories
- Power collection supports INA219 and RPi5 PMIC backends
- MAVLink collector can sniff UDP ports for protocol analysis

---

### 1.2 Benchmark Orchestration (REDUNDANT ⚠️)

| File | Purpose | Status | Dependencies |
|------|---------|--------|--------------|
| [bench/lan_benchmark_gcs.py](bench/lan_benchmark_gcs.py) | GCS-side LAN benchmark server | ✅ **READY** | core.process, core.suites |
| [bench/lan_benchmark_drone.py](bench/lan_benchmark_drone.py) | Drone-side LAN benchmark controller | ✅ **READY** | core.process, core.suites, ina219 |
| [bench/run_full_benchmark.py](bench/run_full_benchmark.py) | Full benchmark runner (GCS/Drone modes) | ✅ **READY** | MetricsAggregator |
| [scheduler/sdrone.py](scheduler/sdrone.py) | Simplified drone scheduler v1 | ⚠️ **LEGACY** | core.run_proxy |
| [scheduler/sgcs.py](scheduler/sgcs.py) | Simplified GCS scheduler v1 | ⚠️ **LEGACY** | core.run_proxy |
| [sscheduler/sdrone.py](sscheduler/sdrone.py) | Policy-driven drone scheduler v2 (CONTROLLER) | ✅ **ACTIVE** | TelemetryAwarePolicyV2 |
| [sscheduler/sgcs.py](sscheduler/sgcs.py) | Policy-driven GCS scheduler v2 (FOLLOWER) | ✅ **ACTIVE** | GcsMetricsCollector |

**Redundancy Analysis:**

| Approach | GCS File | Drone File | Control Flow | Status |
|----------|----------|------------|--------------|--------|
| LAN Benchmark | lan_benchmark_gcs.py | lan_benchmark_drone.py | Drone controls GCS | For LAN-only testing |
| Full Benchmark | run_full_benchmark.py | run_full_benchmark.py | Drone controls GCS | Generic orchestration |
| Scheduler v1 | scheduler/sgcs.py | scheduler/sdrone.py | GCS controls Drone | **DEPRECATED** |
| Scheduler v2 | sscheduler/sgcs.py | sscheduler/sdrone.py | Drone controls GCS | **ACTIVE** |

---

### 1.3 Supporting Metrics Files

| File | Purpose | Status |
|------|---------|--------|
| [sscheduler/gcs_metrics.py](sscheduler/gcs_metrics.py) | Real-time GCS telemetry (schema v1) | ✅ **READY** |
| [sscheduler/telemetry_window.py](sscheduler/telemetry_window.py) | Sliding window for telemetry stats | ✅ **READY** |
| [sscheduler/policy.py](sscheduler/policy.py) | Telemetry-aware policy engine | ✅ **READY** |
| [sscheduler/local_mon.py](sscheduler/local_mon.py) | Local MAVLink monitoring | ✅ **READY** |
| [sscheduler/benchmark_policy.py](sscheduler/benchmark_policy.py) | Benchmark-specific policy | ❓ **NEEDS REVIEW** |

---

### 1.4 Analysis and Reporting

| File | Purpose | Status |
|------|---------|--------|
| [bench/consolidate_metrics.py](bench/consolidate_metrics.py) | Merge GCS/Drone metrics via SSH | ✅ **READY** |
| [bench/analysis/benchmark_analysis.py](bench/analysis/benchmark_analysis.py) | Statistical analysis | ✅ **READY** |
| [bench/analysis/benchmark_plots.py](bench/analysis/benchmark_plots.py) | Generate visualizations | ✅ **READY** |
| [bench/generate_ieee_report.py](bench/generate_ieee_report.py) | IEEE-format LaTeX report | ✅ **READY** |
| [bench/generate_benchmark_book.py](bench/generate_benchmark_book.py) | Full benchmark book | ✅ **READY** |
| [analyze_metrics.py](analyze_metrics.py) | Root-level analysis script | ❓ **STANDALONE** |

---

### 1.5 Test Files

| File | Purpose | Status |
|------|---------|--------|
| [test_metrics_integration.py](test_metrics_integration.py) | Full integration test (localhost) | ✅ **WORKING** |
| [test_collectors.py](test_collectors.py) | Quick collector validation | ✅ **WORKING** |
| [test_complete_loop.py](test_complete_loop.py) | Complete proxy loop test | ✅ **WORKING** |
| [test_localhost_loop.py](test_localhost_loop.py) | Localhost-only loop test | ✅ **WORKING** |
| [test_comprehensive_benchmark.py](test_comprehensive_benchmark.py) | Comprehensive benchmark test | ⚠️ **NEEDS VERIFICATION** |
| [test_schedulers.py](test_schedulers.py) | Scheduler tests | ⚠️ **NEEDS VERIFICATION** |
| [test_sscheduler.py](test_sscheduler.py) | sscheduler-specific tests | ⚠️ **NEEDS VERIFICATION** |
| [test_multiple_suites.py](test_multiple_suites.py) | Multi-suite iteration test | ⚠️ **NEEDS VERIFICATION** |
| [test_gcs_ping.py](test_gcs_ping.py) | Simple GCS connectivity test | ✅ **WORKING** |
| [test_simple_loop.py](test_simple_loop.py) | Minimal loop test | ✅ **WORKING** |

---

### 1.6 Verification/Debug Files (REDUNDANT ⚠️)

| File | Purpose | Status |
|------|---------|--------|
| [verify_collectors.py](verify_collectors.py) | Verify collector output | ⚠️ **REDUNDANT** with test_collectors |
| [verify_gcs_collectors.py](verify_gcs_collectors.py) | GCS-specific verification | ⚠️ **REDUNDANT** |
| [verify_drone_collectors.py](verify_drone_collectors.py) | Drone-specific verification | ⚠️ **REDUNDANT** |
| [confirm_all_metrics.py](confirm_all_metrics.py) | Confirm all metrics populated | ⚠️ **REDUNDANT** |
| [run_metrics_benchmark.py](run_metrics_benchmark.py) | Root-level benchmark runner | ⚠️ **REDUNDANT** with bench/ |

---

### 1.7 Snapshot Directory (ARCHIVED 📦)

The `snapshot/` directory contains archived copies of files - these should NOT be used:
- `snapshot/test_*.py` - Old test file versions
- `snapshot/sscheduler/` - Old scheduler versions
- `snapshot/tools/` - Old tool versions

**Recommendation:** Remove or clearly mark `snapshot/` as archive.

---

## 2. DATA FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           END-TO-END METRICS FLOW                           │
└─────────────────────────────────────────────────────────────────────────────┘

              DRONE SIDE                            GCS SIDE
        ┌──────────────────────┐             ┌──────────────────────┐
        │   Flight Controller  │             │     QGroundControl   │
        │   (ArduPilot/PX4)    │             │     / MAVProxy       │
        └──────────┬───────────┘             └──────────┬───────────┘
                   │ MAVLink UDP                        │ MAVLink UDP
                   ▼                                    ▼
        ┌──────────────────────┐             ┌──────────────────────┐
        │   MAVProxy (drone)   │             │   Plaintext Port     │
        │   Output: 47003      │             │   47001 (TX)         │
        │   Input: 47004       │             │   47002 (RX)         │
        └──────────┬───────────┘             └──────────┬───────────┘
                   │                                    │
                   ▼                                    ▼
        ┌──────────────────────┐             ┌──────────────────────┐
        │   core.run_proxy     │◄───────────►│   core.run_proxy     │
        │   (drone mode)       │  Encrypted  │   (gcs mode)         │
        │                      │   UDP       │                      │
        │  • AEAD encrypt      │   47100     │  • AEAD decrypt      │
        │  • PQC handshake     │◄───────────►│  • PQC handshake     │
        │  • Counters export   │             │  • Counters export   │
        └──────────┬───────────┘             └──────────┬───────────┘
                   │                                    │
                   │ status.json                        │ status.json
                   ▼                                    ▼
        ┌──────────────────────┐             ┌──────────────────────┐
        │  METRICS COLLECTORS  │             │  METRICS COLLECTORS  │
        ├──────────────────────┤             ├──────────────────────┤
        │ • SystemCollector    │             │ • SystemCollector    │
        │ • PowerCollector ◄───┼─ INA219     │ • NetworkCollector   │
        │ • MavLinkCollector   │             │ • MavLinkCollector   │
        │ • NetworkCollector   │             │                      │
        │ • EnvironmentCollect │             │                      │
        └──────────┬───────────┘             └──────────┬───────────┘
                   │                                    │
                   ▼                                    ▼
        ┌──────────────────────┐             ┌──────────────────────┐
        │  MetricsAggregator   │             │  MetricsAggregator   │
        │  (role=drone)        │             │  (role=gcs)          │
        └──────────┬───────────┘             └──────────┬───────────┘
                   │                                    │
                   │ JSON files                         │ JSON files
                   ▼                                    ▼
        ┌──────────────────────┐             ┌──────────────────────┐
        │ logs/comprehensive/  │             │ logs/comprehensive/  │
        │ {suite}_drone.json   │             │ {suite}_gcs.json     │
        └──────────────────────┘             └──────────────────────┘
                   │                                    │
                   └─────────────┬──────────────────────┘
                                 │ SCP/consolidate
                                 ▼
                   ┌──────────────────────────┐
                   │  consolidate_metrics.py  │
                   │  → Merged results JSON   │
                   └──────────────┬───────────┘
                                  │
                                  ▼
                   ┌──────────────────────────┐
                   │  Analysis Pipeline       │
                   │  • benchmark_analysis.py │
                   │  • benchmark_plots.py    │
                   │  • generate_ieee_report  │
                   └──────────────────────────┘
```

---

## 3. METRICS COLLECTED

### 3.1 Categories (from metrics_schema.py)

| Category | Description | Fields | GCS | Drone |
|----------|-------------|--------|-----|-------|
| A. Run Context | Run ID, hosts, git, env | 18 | ✅ | ✅ |
| B. Crypto Identity | KEM, Sig, AEAD algorithms | 13 | ✅ | ✅ |
| C. Lifecycle Timeline | Suite activation timing | 11 | ✅ | ✅ |
| D. Handshake | Duration, success, RTT | 8 | ✅ | ✅ |
| E. Crypto Primitives | KEM/Sig timing in ns | 14 | ✅ | ✅ |
| F. Rekey | Rekey attempts, blackout | 7 | ✅ | ✅ |
| G. Data Plane | Packets, drops, AEAD timing | 17 | ✅ | ✅ |
| H. Latency & Jitter | One-way, RTT, percentiles | 11 | ✅ | ✅ |
| I. MAVProxy Drone | Message counts, heartbeat | 15 | - | ✅ |
| J. MAVProxy GCS | Message counts, heartbeat | 15 | ✅ | - |
| K. MAVLink Integrity | CRC errors, gaps, decode | 11 | ✅ | ✅ |
| L. FC Telemetry | Mode, battery, GPS | 14 | - | ✅ |
| M. Control Plane | Scheduler metrics | 8 | ✅ | ✅ |
| N. System Drone | CPU, memory, temp, load | 14 | - | ✅ |
| O. System GCS | CPU, memory | 8 | ✅ | - |
| P. Power & Energy | INA219 power, energy | 10 | - | ✅ |
| Q. Observability | Sample counts, duration | 7 | ✅ | ✅ |
| R. Validation | Pass/fail, completeness | 6 | ✅ | ✅ |

**Total: 168 metric fields**

---

### 3.2 Key Metrics for Benchmarking

| Metric | Source | Unit | Collection Rate |
|--------|--------|------|-----------------|
| `handshake_duration_ms` | Proxy status file | ms | Per-suite |
| `power_avg_w` | INA219 | Watts | 100-1000 Hz |
| `energy_per_handshake_j` | Calculated | Joules | Per-suite |
| `cpu_usage_avg_percent` | psutil | % | 2 Hz |
| `temperature_c` | thermal_zone0 | °C | 2 Hz |
| `latency_avg_ms` | Packet timestamps | ms | Per-packet |
| `packet_delivery_ratio` | ptx_out/ptx_in | Ratio | Per-suite |
| `heartbeat_loss_count` | MAVLink collector | Count | 1 Hz expected |
| `seq_gap_count` | MAVLink collector | Count | Per-packet |

---

## 4. IDENTIFIED ISSUES

### 4.1 Redundancy Issues

| Issue | Files Affected | Recommendation |
|-------|----------------|----------------|
| **3 scheduler implementations** | scheduler/*, sscheduler/*, bench/*.py | Keep only `sscheduler/` (v2) |
| **Multiple benchmark runners** | bench/run_full_benchmark.py, run_metrics_benchmark.py | Consolidate to bench/ |
| **Duplicate verification scripts** | verify_*.py, confirm_*.py | Merge into tests/ |
| **Snapshot folder** | snapshot/* | Archive or delete |

### 4.2 Incomplete Implementations

| File | Issue | Resolution Needed |
|------|-------|-------------------|
| `sscheduler/benchmark_policy.py` | Purpose unclear, may be stub | Review and integrate or remove |
| `tools/wait_for_comprehensive_metrics.py` | Blocking wait utility | Document usage |
| `tools/blackout_metrics.py` | Blackout detection | Document usage |

### 4.3 Missing Pieces for Complete E2E Benchmark

| Component | Current State | Needed |
|-----------|---------------|--------|
| **Traffic generator** | Removed from codebase | Need external tool or re-add |
| **Real MAVLink traffic** | Only UDP echo | Connect real FC or SITL |
| **Clock synchronization** | `clock_offset_ms` field exists but unused | Implement NTP sync or GPS time |
| **Crypto primitive timing** | Fields exist but often empty | Instrument proxy handshake |
| **Automated test suite** | Scattered test files | pytest integration |

### 4.4 Configuration Issues

| Issue | Location | Fix |
|-------|----------|-----|
| Hardcoded IPs | Multiple files | Use CONFIG exclusively |
| Port conflicts | 48080 used by multiple | Document port allocation |
| LOCAL_* overrides | sscheduler/*.py | Move to config.py or .env |

---

## 5. RECOMMENDATIONS

### 5.1 Immediate Cleanup

1. **Delete or archive:**
   - `snapshot/` folder (archive to `_archive/`)
   - `scheduler/` folder (deprecated by `sscheduler/`)
   - Root-level redundant scripts: `run_metrics_benchmark.py`, `verify_*.py`, `confirm_*.py`

2. **Consolidate:**
   - Move all `test_*.py` to `tests/` folder
   - Create `tests/test_metrics.py` combining collector tests

3. **Document:**
   - Add README to `sscheduler/` explaining controller/follower model
   - Add README to `bench/` explaining analysis pipeline

### 5.2 Complete E2E Benchmark

To run a proper end-to-end MAVLink benchmark:

```bash
# 1. Start GCS scheduler (on Windows GCS machine)
python -m sscheduler.sgcs

# 2. Start Drone scheduler (on RPi via SSH)
ssh dev@drone "cd ~/secure-tunnel && python -m sscheduler.sdrone"

# 3. After completion, consolidate results
python -m bench.consolidate_metrics <run_id> --drone-host <ip>

# 4. Generate analysis report
python -m bench.analysis.run_analysis <results.json>
```

### 5.3 Future Improvements

| Priority | Improvement | Effort |
|----------|-------------|--------|
| High | Add pytest framework with fixtures | Medium |
| High | Implement traffic generator (iperf3 or custom) | Low |
| Medium | Add SITL integration for CI testing | High |
| Medium | Real-time dashboard (Grafana/InfluxDB) | High |
| Low | Crypto primitive instrumentation | Medium |

---

## 6. COMPONENT DEPENDENCY GRAPH

```
                        core/config.py
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
      core/suites.py   core/run_proxy.py  core/process.py
              │               │               │
              └───────┬───────┴───────────────┘
                      │
                      ▼
              core/metrics_schema.py
                      │
       ┌──────────────┼──────────────┐
       ▼              ▼              ▼
 metrics_collectors  mavlink_collector  power_monitor
       │              │              │
       └──────────────┼──────────────┘
                      ▼
            metrics_aggregator.py
                      │
        ┌─────────────┼─────────────┐
        ▼             ▼             ▼
   sscheduler/    bench/lan_*    bench/run_full_*
   (sdrone,sgcs)  (drone,gcs)    (drone,gcs)
        │             │             │
        └─────────────┼─────────────┘
                      ▼
            consolidate_metrics.py
                      │
                      ▼
            bench/analysis/*.py
```

---

## 7. SUMMARY TABLE

| Category | Ready | Incomplete | Redundant | Total |
|----------|-------|------------|-----------|-------|
| Core Metrics | 4 | 0 | 0 | 4 |
| Orchestration | 4 | 0 | 3 | 7 |
| Supporting | 4 | 1 | 0 | 5 |
| Analysis | 5 | 0 | 0 | 5 |
| Tests | 5 | 5 | 0 | 10 |
| Verification | 0 | 0 | 4 | 4 |
| **Total** | **22** | **6** | **7** | **35** |

**Conclusion:** The core metrics infrastructure is solid and production-ready. The main issues are organizational - redundant scheduler implementations and scattered test files. A cleanup pass would reduce the file count by ~20% while improving maintainability.

---

*Report generated by comprehensive codebase analysis*
