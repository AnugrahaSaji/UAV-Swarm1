# Deep Analysis & Security Audit Report

**Date:** 2024-05-22
**Auditor:** Jules (AI Software Engineer)
**Scope:** `core/`, `sscheduler/`, `bench/`, `individual_benchmarks/`

## 1. Executive Summary

The "Secure Tunnel" project implements a sophisticated Post-Quantum Cryptography (PQC) link for UAVs. The cryptographic data plane (`core/`) is well-designed with defense-in-depth mechanisms (DoS protection, Replay protection, Authenticated Encryption). However, the **Control Plane (`sscheduler/`)** has a critical security vulnerability: the TCP command channel is unauthenticated, allowing potential attackers to disrupt operations or force suite downgrades.

The codebase has been cleaned of redundant "copy" files. The benchmarking infrastructure (`run_metrics_benchmark.py`, `bench/benchmark_power_perf.py`) is comprehensive and capable of providing high-resolution power and performance data.

## 2. Current State Analysis

### 2.1 Codebase Structure
*   **Active Development:** `sscheduler/` (Reversed Control: Drone drives GCS).
*   **Legacy:** `scheduler/` (GCS drives Drone).
*   **Core:** `core/` (Crypto engine, Handshake, Proxy).
*   **Benchmarks:** `individual_benchmarks/` (Analysis) and `bench/` (Drivers).

### 2.2 Cleanup Actions
Duplicate files (`sdrone copy.py`, `sgcs copy.py`, etc.) were identified and moved to `legacy_archive/` to reduce technical debt and confusion.

## 3. Security Audit Findings

### 3.1 ✅ Strengths (The Good)
*   **PQC Handshake (`core/handshake.py`):**
    *   **Hybrid Security:** Correctly combines PQC KEM/Sig with classical primitives.
    *   **DoS Mitigation:** Uses `HMAC-SHA256` with a `DRONE_PSK` to authenticate the first packet *before* performing expensive PQC operations. This effectively neutralizes computation exhaustion attacks on the KEM.
    *   **Downgrade Protection:** Explicitly checks `expected_kem` vs `negotiated_kem` inside the encrypted/signed payload.
*   **Data Plane (`core/async_proxy.py`):**
    *   **Replay Protection:** Implements a sliding window for sequence numbers.
    *   **Strict Matching:** `STRICT_UDP_PEER_MATCH` ensures encrypted packets only come from the authenticated IP.
    *   **Rate Limiting:** `_TokenBucket` limits handshake attempts per IP.

### 3.2 ❌ Vulnerabilities (The Bad)
*   **Unauthenticated Control Channel (`sscheduler/sgcs.py`):**
    *   **Severity:** **CRITICAL**
    *   **Description:** The GCS listens on a TCP port (default 48080) for JSON commands (`start`, `stop`, `prepare_rekey`). There is **zero authentication** on this socket.
    *   **Impact:** An attacker on the local network (LAN/VPN) can connect and send `{"cmd": "stop"}` to kill the link, or `{"cmd": "start", "suite": "weak-suite"}` to force a configuration change.
    *   **Recommendation:** Implement the same `DRONE_PSK` HMAC mechanism for the control channel, or wrap it in TLS/SSH.

*   **Shared Secret Management (`core/config.py`):**
    *   **Severity:** Medium
    *   **Description:** The `DRONE_PSK` is a single static key shared across all deployments.
    *   **Impact:** Compromise of one drone reveals the key for all.
    *   **Recommendation:** Move to per-device keys or certificate-based authentication if possible.

## 4. Robustness & Code Quality

*   **Error Handling:** The proxy (`async_proxy.py`) is robust, with extensive `try-except` blocks around socket I/O to prevent crashes during network instability.
*   **Dependency Management:** The reliance on `liboqs` and `oqs-python` (which are not standard pip packages) makes deployment and testing brittle. The `tests/` failed in the review environment due to missing dependencies.
*   **Configuration:** `core/config.py` is the Single Source of Truth, which is good practice. Validation logic is strict.

## 5. Benchmark Insights ("Individual Benchmarks")

The "Individual Benchmarks" phase appears to be driven by `bench/benchmark_power_perf.py`.
*   **Methodology:** It isolates KEM, Sig, and AEAD operations.
*   **Metrics:** It captures:
    *   **Timing:** `perf_time_ns` (CPU time) vs `wall_time_ns` (Real time).
    *   **Power:** High-frequency (1kHz) sampling via INA219.
    *   **Hardware Counters:** Cycles, Instructions, Cache Misses (via Linux `perf`).
*   **Status:** The code is complete and capable of generating detailed JSON reports in `benchmarks/bench_results_power/`.

## 6. Recommendations for "End-to-End MAV to MAV"

To move to the next phase (End-to-End):
1.  **Fix the Control Channel:** Secure the TCP port in `sgcs.py` before field deployment.
2.  **Traffic Simulation:** `run_metrics_benchmark.py` contains a `TrafficGenerator`. Ensure this generator mimics real MAVLink traffic patterns (bursty, small packets) rather than just constant bitrate.
3.  **Telemetry Sync:** Ensure the `sscheduler/sdrone.py` telemetry listener is correctly parsing the `uav.pqc.telemetry.v1` schema from the GCS to make intelligent rekeying decisions.
