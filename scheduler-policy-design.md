# Scheduler Policy Design: Measurement-Driven Adaptive Resource Management for Secure UAV Communications

---
**Document Status:** Approved & Finalized for Thesis  
**Target Platform:** Raspberry Pi 4 Model B (Broadcom BCM2711 quad-core ARM Cortex-A72)  
**Control Framework:** Measurement-Driven Energy-Aware Scheduling (MDEAS)  
---

## Executive Summary

This document presents the formal specification of the **Measurement-Driven Energy-Aware Scheduling (MDEAS)** layer. Rather than a heuristic "trial-and-error" loop, the MDEAS scheduler operates as a user-level control layer positioned directly above the secure UAV communication workflow. It coordinates edge cryptographic execution, Time Series Transformer (TST) DDoS anomaly detection, and operating system resource knobs. By continuously observing environmental metrics (battery, CPU load, latency, and temperature) and real-measured power draw, the scheduler dynamically dynamically manages cryptographic profiles, active core counts, frequency scaling policies, and IDS intensity to guarantee mission-critical MAVLink telemetry while preventing hardware throttling and minimizing energy consumption.

---

## 1. Hardware Environment and DVFS Constraints

The companion computer on the UAV is a **Raspberry Pi 4 Model B**, which features a **Broadcom BCM2711 system-on-chip** equipped with a **quad-core ARM Cortex-A72 64-bit processor** specified up to **1.8 GHz**. 

For resource-aware scheduling, the following physical and operating system control mechanisms are exposed:
*   **CPU Frequency Scaling (DVFS)**: Linux CPU frequency scaling (`cpufreq`) manages operating frequencies to balance performance and power. In our hardware environment, all CPU cores share a single hardware frequency domain and voltage regulator. Thus, frequency scaling is managed as a **unified frequency-policy** rather than independent per-core frequencies.
*   **Active Core Control (CPU Hotplug)**: Operating system cores can be taken offline or brought online at runtime using the Linux CPU hotplug interface (`/sys/devices/system/cpu/cpu*/online`), directly reducing baseline leakage power.
*   **Task Placement (CPU Affinity)**: Thread execution and process placement are bound to specific cores via CPU affinity masks (`sched_setaffinity`), avoiding context-switching overhead and cache invalidation.

Therefore, the scheduling layer is formally defined as a **core-count, frequency-policy, and task-affinity aware user-level adaptive resource controller**.

---

## 2. The Three-Axis Multi-Dimensional Formulation

The MDEAS scheduling design models system operation along three orthogonal control axes, separating execution planes to maximize optimization efficiency:

```
                  [ Axis 2: Security Level (L1, L3, L5 KEM/SIG) ]
                                      ▲
                                      │
                                      │
   [ Axis 1: AEAD Crypto ] ◄──────────┼──────────► [ Axis 3: DDoS Detector ]
   (ChaCha20, AES-GCM, Ascon)         │             (None, XGBoost, TST)
                                      ▼
                      [ System Telemetry Constraints ]
```

### Axis 1: Cryptographic Profile (Data-Plane, Per-Packet)
*   **Driven by**: Measured per-packet `aead_encrypt_avg_ns`, `aead_decrypt_avg_ns`, instantaneous packet rate, temperature rate-of-change, and battery discharge rate.
*   **Controls**: Symmetric encryption algorithm selection (ChaCha20-Poly1305, AES-GCM, or software-based Ascon-128a).
*   **Rationale**: Data-plane encryption runs on *every* packet, accounting for up to 99.5% of continuous cryptographic power on ARM cores without dedicated hardware AES instructions.

### Axis 2: Security Level (Control-Plane, Per-Handshake)
*   **Driven by**: Core arming state, mission criticality, and wireless link quality (packet gaps, blackout counts).
*   **Controls**: NIST Post-Quantum Cryptography security level (L1, L3, or L5), corresponding to specific KEM × Signature pairings (e.g., ML-KEM-768 × ML-DSA-65).
*   **Rationale**: Asymmetric key agreement and signature checks only run during handshakes. This axis dictates session initialization latency and key size overhead, but has negligible continuous power draw.

### Axis 3: DDoS Detection Intensity (Compute-Plane)
*   **Driven by**: Real-time threat level, queue delays, CPU load, and thermal headroom.
*   **Controls**: Active Intrusion Detection System (IDS) mode: `NONE`, `XGBOOST` (lightweight), or `TST` (high-accuracy Time Series Transformer).
*   **Rationale**: Running deep-learning TST models continuously is power-hungry (+1.97W baseline draw, +10.7°C thermal increase). Managing this as a discrete third axis allows the scheduler to restrict heavy execution to periods of active threat.

---

## 3. Seven Control Knobs

The MDEAS controller manages seven key system parameters to align performance with real-time energy constraints:

| Control Knob | Mechanism / API | Operational Value | Impact on UAV Workflow |
| :--- | :--- | :--- | :--- |
| **1. CPU Governor / Freq** | `cpufreq` user-space governor | 600 MHz, 900 MHz, 1.2 GHz, 1.5 GHz, 1.8 GHz | Controls operating voltage and clock speed; reduces thermal load |
| **2. Active Core Count** | Linux CPU hotplug interface | 1, 2, 3, or 4 active cores | Adjusts available parallel capacity and limits leakage current |
| **3. CPU Task Affinity** | `taskset` / `sched_setaffinity` | Core-pinning masks (e.g., bind proxy to Core 1) | Prevents thread preemption and stabilizes telemetry latency |
| **4. IDS Detector Mode** | Subprocess management | `NONE`, `XGBOOST` only, `TST` only, or `HYBRID` | Controls compute overhead and accuracy of threat screening |
| **5. Symmetric Cipher** | Proxy runtime configuration | AES-256-GCM or ChaCha20-Poly1305 | Optimizes packet round-trip time based on edge measurements |
| **6. PQC Handshake Suite** | oqs-python key exchange | NIST Level 1, Level 3, or Level 5 | Manages security level, key length, and rekey CPU spikes |
| **7. Rekey Interval** | Session key epoch timer | Dynamic interval (60s to 3600s) | Balances forward secrecy against handshake energy cost |

---

## 4. Three-Tier Task Priority Hierarchy

To ensure safety-critical operation, the scheduler divides companion computer workloads into a strict three-tier priority hierarchy:

```
┌─────────────────────────────────────────────────────────────┐
│ LEVEL 1: Mission-Critical (Always Enabled, Guarded CPU)     │
│ - MAVLink secure proxy   - Telemetry/command forwarding    │
│ - Encrypt/Decrypt path   - Pixhawk flight-controller comms  │
├─────────────────────────────────────────────────────────────┤
│ LEVEL 2: Security-Enhancement (Adaptive under stress)       │
│ - XGBoost DDoS screener  - Time Series Transformer (TST)    │
│ - Frequent rekeys        - High-security PQC suites (L5)    │
├─────────────────────────────────────────────────────────────┤
│ LEVEL 3: Non-Critical Support (Disabled under pressure)     │
│ - Detailed file logging  - Debug print / Verbose stdout     │
│ - High-frequency polling - Non-essential telemetry records  │
└─────────────────────────────────────────────────────────────┘
```

1.  **Level 1: Mission-Critical Tasks**: Must never be degraded, suspended, or preempted under any operational condition. The scheduler guarantees sufficient core capacity, CPU cycles, and memory allocation to this level to protect telemetry flow and piloting commands.
2.  **Level 2: Security-Enhancement Tasks**: Optimize security posture against attacks. The scheduler can degrade, delay, or selectively disable these components when battery capacity is low or CPU temperature is high.
3.  **Level 3: Non-Critical Support Tasks**: Auxiliary scripts and debug monitoring. These are immediately deactivated, suspended, or heavily throttled when the system encounters energy, thermal, or computing stress.

---

## 5. Scheduler State Observers

The MDEAS engine maintains a structured **Decision Context** consisting of ten observed state variables updated at a 1 Hz sampling rate:

1.  **Battery Voltage (`battery_mv`)**: Real-time battery status in millivolts, indicating total remaining energy.
2.  **Battery Rate-of-Change (`battery_roc`)**: Slope of battery voltage over a sliding 60-second window, identifying sudden current draw spikes.
3.  **CPU Temperature (`temp_c`)**: CPU die temperature read from `thermal_zone0`, preventing thermal throttling.
4.  **Temperature Rate-of-Change (`temp_roc`)**: Rate of thermal rise (or fall) in °C/minute to proactively anticipate throttling.
5.  **Throttling Status (`throttled_flag`)**: Read from `vcgencmd get_throttled`, flagging critical hardware thermal or under-voltage limits.
6.  **Per-Process CPU Utilization (`cpu_pct`)**: CPU resource utilization of the proxy, IDS, and background tasks.
7.  **Measured Power Draw (`power_w`)**: Real-time telemetry in Watts received from the physical high-sampling-rate power meter.
8.  **Telemetry Packet Loss (`loss_pct`)**: Missing sequence numbers in telemetry, protecting link reliability.
9.  **Round-Trip Time (`rtt_ms`)**: Communication latency, protecting command responsiveness.
10. **IDS Threat Level (`threat_level`)**: Anomaly score generated by the active DDoS detectors, determining security intensity.

---

## 6. Operating Modes and Transition Matrix

The scheduler translates these observer inputs into six distinct operating modes:

```
                 ┌───────────────────────────┐
                 │     Performance Mode      │
                 └─────────────▲─────────────┘
                               │ High Battery,
                               │ High Threat
                 ┌─────────────▼─────────────┐
                 │    Balanced Mode (Def)    │
                 └──────┬──────────────┬─────┘
        DDoS     │      │              │ Temp > 70°C
        Detected │      │              │ OR ROC High
   ┌─────────────▼──────┐              │ ┌───────────────────────────┐
   │  Threat-Response   │              └─►    Thermal-Protection     │
   └────────────────────┘                └───────────────────────────┘
         Temp > 75°C │                      │ Temp < 60°C
                     ▼                      ▼
                 ┌───────────────────────────┐
                 │    Energy-Saving Mode     │
                 └─────────────┬─────────────┘
                               │ Battery < 20%
                               ▼
                 ┌───────────────────────────┐
                 │      Emergency Mode       │
                 └───────────────────────────┘
```

### 1. Performance Mode
*   **Trigger**: High battery (>80%) AND high threat level or manual override.
*   **Configuration**: 4 active cores @ 1.8 GHz; full hybrid IDS (XGBoost + TST) active; Level 5 PQC suite enabled; short rekey interval.
*   **Objective**: Maximum security and minimal latency when energy is abundant.

### 2. Balanced Mode (Default)
*   **Trigger**: Normal battery (40% - 80%) and normal temperature (<70°C).
*   **Configuration**: 2 to 3 active cores @ 1.2 or 1.5 GHz; XGBoost active with conditional TST trigger; Level 3 PQC suite.
*   **Objective**: Optimal trade-off between security, link latency, and power draw.

### 3. Energy-saving Mode
*   **Trigger**: Battery decreasing (20% - 40%) OR temperature rising (>70°C with negative battery slope).
*   **Configuration**: 1 to 2 active cores @ 900 MHz - 1.2 GHz; XGBoost active, TST completely disabled; Level 3 PQC suite; longer rekey intervals (e.g., 300s).
*   **Objective**: Extended flight times with defensive security active.

### 4. Emergency Mode (Survival)
*   **Trigger**: Battery falls below **20%** OR temperature exceeds **80°C**.
*   **Configuration**: 1 active core @ 600 MHz User-Space governor; all IDS modules (both XGBoost and TST) completely disabled; baseline Level 1 PQC suite + cheapest measured data-plane AEAD; all Level 3 logging/debug disabled.
*   **Objective**: Preservation of critical flight telemetry and GCS commands when companion hardware is at high risk of shutting down.

### 5. Threat-response Mode
*   **Trigger**: DDoS threat suspected by XGBoost screener, high packet rate, or packet loss anomalies.
*   **Configuration**: Cores and frequency temporarily boosted to maximum (4 cores @ 1.8 GHz); TST activated continuously; cryptographic profile locked to the cheapest measured AEAD to avoid explorer thrashing.
*   **Objective**: Rapid, high-accuracy threat verification and packet filtering under attack.

### 6. Thermal-protection Mode
*   **Trigger**: CPU temperature exceeds **70°C** OR `temp_roc` predicts threshold crossing within 60 seconds.
*   **Configuration**: Frequency scaled down; TST disabled; secure proxy thread isolated on a dedicated core via CPU affinity; strict temperature rate-of-change monitoring.
*   **Objective**: Prevention of hardware thermal throttling events which introduce unpredictable CPU-scheduler spikes and packet delays.

---

## 7. Core Cryptographic Optimization: Break-Even and Deltas

A core mechanism of the MDEAS layer is its ability to perform **amortized energy break-even analysis** before switching cryptographic algorithms or changing NIST levels.

### The Rekey vs. AEAD Trade-Off
A suite change or key rotation requires a PQC handshake, consuming a known amount of energy and introducing a temporary communication blackout window:
$$\text{Handshake Duration} \approx 13.45\text{ ms}$$
$$\text{Rekey Energy Cost } (E_{\text{rekey}}) \approx \text{Average Rekey Power} \times \text{Handshake Time}$$

Symmetric AEAD encryption runs per-packet. Switching to a cheaper AEAD (e.g., ChaCha20-Poly1305 over software-based Ascon) saves a small amount of energy per packet ($e_{\text{saved}}$):
$$e_{\text{saved}} = (\text{Cost}_{\text{current\_aead}} - \text{Cost}_{\text{target\_aead}}) \times \text{Payload Size}$$

The scheduler calculates the **Break-Even Time** ($T_{\text{break\_even}}$) at the current packet rate ($R_{\text{pkt}}$):
$$T_{\text{break\_even}} = \frac{E_{\text{rekey}}}{e_{\text{saved}} \times R_{\text{pkt}}}$$

**Optimization Rule**: The scheduler only triggers an AEAD switch if the predicted flight time remaining under the current battery level exceeds $T_{\text{break\_even}}$ (with a minimum safety threshold of **30 seconds**). This prevents "micro-switching," where the system wastes more energy during handshakes than it saves on the data plane.

---

## 8. Evaluated Task-to-Core Mapping

Rather than relying on the general-purpose Linux kernel scheduler (which distributes tasks dynamically to balance heat, leading to context-switch latency spikes), the MDEAS scheduler enforces a dedicated, measured core-affinity mapping:

| Core | Workload Assignment | Priority | Configuration Rationale |
| :--- | :--- | :--- | :--- |
| **Core 0** | Linux OS background, system interrupts, networking stack, MAVLink raw UDP sockets | Low / System | Isolates operating system jitter, background logging, and I/O interrupts from the security logic |
| **Core 1** | Secure MAVLink Proxy, post-quantum key exchange thread, AEAD encrypt/decrypt loop | Critical (Level 1) | Dedicated entirely to flight control traffic, ensuring stable packet round-trip times and preventing telemetry lag |
| **Core 2** | XGBoost DDoS detection module, lightweight packet feature extraction | High (Level 2) | Continuous screening of incoming traffic metrics without introducing compute noise to Core 1 |
| **Core 3** | TST (Time Series Transformer) DDoS deep-learning model | High (Level 2) | Kept offline or throttled to save power; active only during Threat-Response mode to run heavy model evaluations |

*Thesis Note*: This mapping is presented as an **evaluated configuration** representing a structured thesis contribution, demonstrating that isolating the secure proxy and IDS workloads reduces tail latency (p95 RTT) and improves overall energy efficiency compared to default Linux scheduling.

---

## 9. Core Thesis Contribution Statement

To conclude, the contributions of the scheduling layer are summarized below:

> This thesis proposes a UAV-specific, measurement-driven adaptive scheduling layer (MDEAS) that jointly optimizes cryptographic selection, Intrusion Detection (IDS) intensity, CPU operating frequency, active core counts, and task placement based on measured battery state, thermal behavior, and communication quality. By dividing companion computer tasks into a strict three-tier priority hierarchy and applying a joint thermal-energy model with amortized break-even analysis, the scheduler reduces average power draw and prevents hardware throttling while guaranteeing mission-critical secure MAVLink communication as the highest-priority service.
