# SITL End-to-End System Validation Report (Native Flight-Controller SITL Validation (Level 2))

**Project Title**: An Adaptive Trust-Aware Post-Quantum Secure MAVLink Communication System for Wi-Fi-Based UAV Swarms  
**Research Group**: Computer Systems Group, IIIT Hyderabad  
**Execution Mode**: `SITL`  
**Date**: 2026-08-29 16:06:37

---

## Executive Summary

## Operational Latency Metrics Definitions

- **$T_{detection}$**: Attack identification latency (time required to identify root mismatch or signature invalidity).
- **$T_{recovery} = T_{root_verified} - T_{mitigation_start}$**: Primary core SMT computational state-recovery latency following mitigation for DDoS/Tampering attacks.
- **$T_{sybil_rejection}$**: SMT non-membership verification and rejection latency for Sybil attacks (requires zero SMT mutation).
- **$T_{e2e}$**: Total end-to-end time measured from the defined attack event/mitigation trigger until the corresponding recovery confirmation is received at the intended endpoint (measured independently).
- **$T_{network}$**: Recorded separately as network transport delay.

---

## Key Performance Summary

| Metric / Parameter | Measured Result | Benchmark Criterion | Compliance Status |
| :--- | :---: | :---: | :---: |
| **Average SMT State-Recovery Latency Following Mitigation ($T_{recovery}$)** | **0.5242 ms** (Min: 0.3101 ms, Max: 1.1991 ms) | PASS/FAIL Target: $< 20.0\text{ ms}$ | **PASS (100.0%)** |
| **Average Detection Latency ($T_{detection}$)** | **0.3255 ms** | Sub-millisecond | **PASS** |
| **Average Operational E2E Latency ($T_{e2e}$)** | **3.9182 ms** | Real-Time Telemetry | **PASS** |
| **Sustained DDoS Throughput** | **10,995,467.9 pps** | $> 50,000\text{ pps}$ | **PASS** |
| **System Resource Footprint** | **< 1.0% CPU / ~42.5 MB RAM** | Low-overhead Companion PC | **PASS** |
| **Overall $T_{recovery} < 20\text{ms}$ Target Assessment** | **18/18 Trials (100.0%)** | PASS/FAIL Target | **FULLY COMPLIANT** |

---

## Scalability Matrix: 6 Primary Latency Plot Categories

Below are the empirical metric breakdowns across node roles and attack scenarios:

### 1. Sybil Attack Non-Membership Verification and Rejection Latency ($T_{rejection}$)
> *Scientific Note: Sybil UAVs were never registered in the SMT, so rejection measures SMT non-membership proof verification with zero SMT leaf mutation or re-rooting.*

| Swarm Size ($N$) | Root Leader (ms) | Cluster Head (ms) | Leaf Follower (ms) |
| :---: | :---: | :---: | :---: |
| 5 | 0.0013 | 0.0011 | 0.0018 |
| 10 | 0.0005 | 0.0006 | 0.0006 |
| 20 | 0.0007 | 0.0007 | 0.0009 |
| 30 | 0.0008 | 0.0007 | 0.0007 |
| 40 | 0.0009 | 0.0006 | 0.0005 |
| 50 | 0.0006 | 0.0007 | 0.0006 |

### 2. DDoS/Tampering SMT State-Recovery Latency Following Mitigation ($T_{{recovery}}$)
> *Scientific Note: SMT state-recovery latency measures the exact computational time taken by the SMT to compute leaf withdrawal and re-root a valid state following attack mitigation.*

| Swarm Size ($N$) | Root Leader (ms) | Cluster Head (ms) | Leaf Follower (ms) | Target ($<20\text{{ms}}$) |
| :---: | :---: | :---: | :---: | :---: |
| 5 | 1.1991 | 1.1941 | 0.3813 | **PASS** |
| 10 | 0.3215 | 0.3238 | 0.3206 | **PASS** |
| 20 | 0.3242 | 0.6660 | 0.9831 | **PASS** |
| 30 | 0.3550 | 0.3193 | 0.3702 | **PASS** |
| 40 | 1.0257 | 0.3324 | 0.3101 | **PASS** |
| 50 | 0.3309 | 0.3358 | 0.3419 | **PASS** |

---

## Multi-Level Validation Progression

```
 Level 1 — Software MAVLink Emulation  -->  Level 2 — Native Flight-Controller SITL Validation  -->  Level 3 — Networked Wi-Fi/IP End-to-End Validation
 (Synthetic MAVLink Telemetry Benchmark)    (ArduPilot / PX4 SITL Telemetry Streams)                (Wi-Fi Network & GCS Integration)
```

---

## Conclusion & Next Steps

1. **Validation Target**: Empirical SMT state-recovery latency $T_{{recovery}} = T_{{state_verified}} - T_{{mitigation_start}}$ was evaluated against the $20\text{{ ms}}$ target across evaluated swarm sizes ($N = 5$ to $50$) and hierarchical node roles (Root Leader, Cluster Head, Leaf Follower).
2. **Next Milestone**: Level 3 Wi-Fi-based physical companion computer deployment (Raspberry Pi 4 / Pixhawk 2.4.8) over hardware Wi-Fi AP topologies.
