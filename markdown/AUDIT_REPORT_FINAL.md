# FAANG-Level Audit Report: Secure Tunnel System

**Date:** 2024-10-26
**Auditor:** GitHub Copilot
**Target:** `secure-tunnel` Repository

---

## 1. Code-Proven Port & Plane Map

This map is derived strictly from the codebase "source of truth" (`core/config.py`) and operational scripts (`sscheduler/`).

### **Control Plane (TCP)**
*Reliable, low-bandwidth channel for handshake, rekeying, and orchestration.*

| Port | Protocol | Direction | Component | Source of Truth | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **46000** | TCP | Bidirectional | Handshake | `core/config.py` | TLS-like PQC Handshake (Kyber/Dilithium exchange). |
| **48080** | TCP | Drone -> GCS | Scheduler | `sscheduler/sgcs.py` | GCS Control Server. Drone connects here to issue commands. |

### **Data Plane (UDP)**
*High-bandwidth, encrypted channel for MAVLink and payload traffic.*

| Port | Protocol | Direction | Component | Source of Truth | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **46011** | UDP | -> GCS | Encrypted Rx | `core/config.py` | GCS listens here for encrypted packets from Drone. |
| **46012** | UDP | -> Drone | Encrypted Rx | `core/config.py` | Drone listens here for encrypted packets from GCS. |
| **47001** | UDP | GCS Internal | Plaintext Tx | `sscheduler/sgcs.py` | GCS apps send plaintext here; Proxy encrypts -> 46012. |
| **47002** | UDP | GCS Internal | Plaintext Rx | `sscheduler/sgcs.py` | Proxy decrypts 46011 -> here for GCS apps (MAVProxy). |
| **47003** | UDP | Drone Internal | Plaintext Tx | `sscheduler/sdrone.py` | Drone apps send plaintext here; Proxy encrypts -> 46011. |
| **47004** | UDP | Drone Internal | Plaintext Rx | `sscheduler/sdrone.py` | Proxy decrypts 46012 -> here for Drone apps (MAVProxy). |

### **Telemetry Plane (UDP)**
*Dedicated side-channel for link quality metrics (GCS -> Drone).*

| Port | Protocol | Direction | Component | Source of Truth | Description |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **52080** | UDP | GCS -> Drone | Telemetry | `sscheduler/sgcs.py` | GCS sends JSON metrics snapshots to Drone. |
| **14552** | UDP | Local (GCS) | Sniffing | `sscheduler/sgcs.py` | MAVProxy mirrors traffic here for `GcsMetricsCollector`. |

---

## 2. Telemetry Pipeline Verification

**Claim:** "GCS computes metrics ... and sends UDP telemetry to Drone; Drone receives ... for scheduler decisions."

**Code Evidence:**

1.  **Acquisition (GCS):**
    *   File: `sscheduler/gcs_metrics.py`
    *   Class: `GcsMetricsCollector`
    *   Mechanism: Binds to UDP 14552 (Sniff Port). Parses MAVLink packets using `pymavlink`.
    *   Metrics: Calculates `rx_pps`, `jitter_ms`, `gap_p95_ms`, and system stats (`cpu_pct`).

2.  **Transmission (GCS):**
    *   File: `sscheduler/sgcs.py`
    *   Class: `TelemetrySender`
    *   Mechanism: Serializes metrics to JSON. Sends via UDP to `DRONE_HOST:52080`.
    *   Code: `self.sock.sendto(payload, self.target_addr)`

3.  **Reception (Drone):**
    *   File: `sscheduler/sdrone.py`
    *   Class: `TelemetryListener`
    *   Mechanism: Binds UDP 52080. Validates JSON schema `uav.pqc.telemetry.v1`.
    *   Storage: Maintains a sliding window history (`deque`) of the last 50 packets.

4.  **Decision (Drone):**
    *   File: `sscheduler/sdrone.py`
    *   Class: `DecisionContext`
    *   Mechanism: `get_summary()` computes aggregate stats (median CPU, max silence) from the history for the `DroneScheduler` to use.

**Verdict:** **VERIFIED.** The telemetry pipeline is fully implemented and operational as described.

---

## 3. Simulation Audit & "Fake" Code

The following components were identified as "simulation" or "test harness" artifacts. They are **NOT** part of the core secure tunnel but are used for testing/benchmarking.

| File | Component | Type | Risk Level | Description |
| :--- | :--- | :--- | :--- | :--- |
| `auto/drone_follower.py` | `SyntheticKinematicsModel` | **Simulation** | **HIGH** | Generates fake flight physics (velocity, heading, altitude). **Must be disabled for flight.** |
| `auto/gcs_scheduler.py` | `Blaster` | Traffic Gen | Low | UDP packet generator for load testing. |
| `sscheduler/sgcs.py` | `TrafficGenerator` | Traffic Gen | Low | Generates "X" payloads for link saturation testing. |
| `sscheduler/sdrone.py` | `UdpEchoServer` | Echo Server | Low | Echoes packets back to sender. Used for round-trip testing. |

**Recommendation:**
The `sscheduler` (Secure Scheduler) implementation appears to be the "Production" path. It does **NOT** import or use `SyntheticKinematicsModel`. It relies on `MAVProxy` connected to real hardware (default `/dev/ttyACM0`).
*   **Action:** Ensure `auto/` scripts are never deployed to a production drone. Use `sscheduler/` scripts for operations.

---

## 4. Cryptographic Suite Verification

The system uses `liboqs` (Open Quantum Safe) for all cryptography.

*   **Key Exchange (KEM):** ML-KEM (Kyber) - Levels 1, 3, 5.
*   **Signatures (SIG):** ML-DSA (Dilithium) - Levels 2, 3, 5.
*   **Symmetric (AEAD):** AES-256-GCM, ChaCha20-Poly1305, Ascon-128a.

**Source:** `core/suites.py`
**Status:** **VERIFIED.** The registry is comprehensive and maps correctly to NIST standards.
