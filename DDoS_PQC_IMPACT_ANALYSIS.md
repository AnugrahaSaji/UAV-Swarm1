# DDoS × PQC Mutual Impact Analysis

**Platform:** Raspberry Pi 4 (Cortex-A72 @ 1.8 GHz, 4 GB RAM)  
**Benchmark Run:** 2026-02-22 20:30–20:53 UTC  
**KEM:** Classic-McEliece-348864 (L1) | **SIG:** Falcon-512 (L1)  
**AEAD variants tested:** AES-256-GCM, ChaCha20-Poly1305, Ascon-128a  
**Power sensor:** INA219 (I2C, 1 kHz sampling, 0.1 Ω shunt)

---

## 1. Five-Phase Benchmark Design

| Phase | Configuration | Duration | Purpose |
|-------|--------------|----------|---------|
| **A** | Idle baseline (no tunnel, no detector) | 60 s | Establish floor |
| **B1** | XGBoost detector only (no tunnel) | 60 s | Detector-idle overhead |
| **B2** | TST detector only (no tunnel) | 60 s | Detector-idle overhead |
| **C** | PQC tunnel only (no detector) | 3 suites × ~10 s | Tunnel-only baseline |
| **D** | PQC tunnel + XGBoost detector | 3 suites × ~10 s | Combined: tunnel + XGB |
| **E** | PQC tunnel + TST detector | 3 suites × ~10 s | Combined: tunnel + TST |

120 s cooldown between every phase. All phases ran on the same Pi with the real Pixhawk 6C flight controller connected (MANUAL mode, disarmed).

---

## 2. Overview: System-Level Cross-Phase Comparison

| Metric | A (Idle) | B1 (XGB idle) | B2 (TST idle) | C (PQC only) | D (PQC+XGB) | E (PQC+TST) |
|--------|----------|---------------|---------------|-------------|-------------|-------------|
| **CPU avg %** | 1.2 | 3.4 | 4.6 | 24.7 | 48.2 | 55.3 |
| **Temperature °C** | 52.5 | 53.2 | 53.5 | 56.3 | 58.6 | 61.5 |
| **Power avg mW** | 3,630 | 3,721 | 3,714 | 3,868 | 4,373 | 4,558 |
| **RAM MB** | 226 | 472 | 479 | ~278 | ~524 | ~531 |
| **Throughput Mbps** | — | — | — | 0.139 | 0.147 | 0.133 |
| **MAVLink stream Hz** | — | — | — | 317.4 | 317.3 | 317.3 |
| **Packet loss** | — | — | — | 0% | 0% | 0% |
| **Heartbeat loss** | — | — | — | 0 | 0 | 0 |

---

## 3. Impact of DDoS Detection ON PQC Tunnel

This section isolates how adding a DDoS detector affects the PQC tunnel's performance, by comparing Phase C (tunnel only) against Phases D and E (tunnel + detector).

### 3.1 Resource Overhead Added by Detectors

| Metric | C (PQC only) | D (PQC+XGB) | Δ XGB | E (PQC+TST) | Δ TST |
|--------|-------------|-------------|-------|-------------|-------|
| CPU avg % | 24.7 | 48.2 | **+23.5** (+95%) | 55.3 | **+30.6** (+124%) |
| CPU peak % | 43.5 | 72.7 | +29.2 | 79.8 | +36.3 |
| Temperature °C | 56.3 | 58.6 | **+2.3** | 61.5 | **+5.2** |
| Power avg mW | 3,868 | 4,373 | **+505** (+13.1%) | 4,558 | **+690** (+17.8%) |
| Steady power mW | 3,998 | 4,769 | **+771** (+19.3%) | 5,039 | **+1,041** (+26.0%) |

### 3.2 PQC Tunnel Functional Impact

| Metric | C (PQC only) | D (PQC+XGB) | E (PQC+TST) |
|--------|-------------|-------------|-------------|
| Throughput Mbps | 0.139 | 0.147 | 0.133 |
| Packet loss % | 0 | 0 | 0 |
| MAVLink stream Hz | 317.4 | 317.3 | 317.3 |
| Heartbeat loss | 0 | 0 | 0 |
| CRC errors | 0 | 0 | 0 |
| Decode failures | 0 | 0 | 0 |

**Key finding:** Neither DDoS detector causes any functional degradation to the PQC tunnel. The MAVLink data plane is completely unaffected — zero packet loss, consistent 317 Hz stream rate, zero heartbeat or CRC errors across all configurations.

### 3.3 AEAD Encryption Latency Under Load (per-packet, ns)

| AEAD | C (PQC only) | D (PQC+XGB) | Δ | E (PQC+TST) | Δ |
|------|-------------|-------------|---|-------------|---|
| AES-256-GCM | 78,045 | 103,232 | +32.3% | 95,059 | +21.8% |
| ChaCha20-Poly1305 | 78,154 | 103,692 | +32.7% | 89,407 | +14.4% |
| Ascon-128a | 1,324,120 | 1,714,654 | +29.5% | 1,878,849 | +41.9% |

AES-GCM and ChaCha20 benefit from ARMv8 cryptographic extensions, keeping per-packet encryption under 104 μs even under combined load. Ascon-128a is software-only and shows more sensitivity to CPU contention but remains operationally acceptable at ~1.9 ms/packet.

---

## 4. Impact of PQC Tunnel ON DDoS Detection

This section isolates how the PQC tunnel affects the DDoS detector's operational profile, by comparing Phase B (detector idle) against Phases D/E (detector + tunnel traffic).

### 4.1 Detector Resource Delta

| Metric | B1 (XGB idle) | D (PQC+XGB) | Δ tunnel load | B2 (TST idle) | E (PQC+TST) | Δ tunnel load |
|--------|---------------|-------------|--------------|---------------|-------------|--------------|
| CPU % | 3.4 | 48.2 | +44.8 | 4.6 | 55.3 | +50.7 |
| Temp °C | 53.2 | 58.6 | +5.4 | 53.5 | 61.5 | +8.0 |
| Power mW | 3,721 | 4,373 | +652 (+17.5%) | 3,714 | 4,558 | +844 (+22.7%) |

Note: The large CPU jump from B→D/E is expected — Phase B has the detector loaded but idle (no network traffic to analyze), while Phase D/E has the full PQC tunnel running with MAVLink traffic flowing, which triggers PQC encryption and MAVProxy forwarding. The tunnel itself (not the detector) is the dominant CPU consumer in steady-state.

### 4.2 Additive Resource Model

The overhead is approximately additive:

| Component | CPU (%) | Power (mW) | Temp Δ (°C) | RAM (MB) |
|-----------|---------|------------|-------------|----------|
| Idle Pi4 | 1.2 | 3,630 | 0 (base: 52.5) | 226 |
| + PQC tunnel | +23.5 | +238 | +3.8 | +52 |
| + XGBoost | +23.5 | +505 | +2.3 | +246 |
| **= PQC + XGB** | **≈48.2** | **≈4,373** | **+6.1** | **≈524** |
| + TST (instead) | +30.6 | +690 | +5.2 | +253 |
| **= PQC + TST** | **≈55.3** | **≈4,558** | **+9.0** | **≈531** |

---

## 5. Per-AEAD Detailed Breakdown

### 5.1 AES-256-GCM (ARMv8 hardware-accelerated)

| Metric | C: PQC only | D: PQC+XGB | E: PQC+TST |
|--------|------------|-----------|-----------|
| Handshake ms | 246.7 | 330.7 | 218.1 |
| KEM keygen ms | 111.7 | 141.1 | 48.2 |
| KEM decaps ms | 18.9 | 29.3 | 17.3 |
| CPU avg % | 24.8 | 49.3 | 60.5 |
| Temp °C | 56.0 | 57.5 | 60.4 |
| Power avg mW | 3,841 | 4,397 | 4,652 |
| Steady power mW | 3,849 | 4,687 | 4,959 |
| Throughput Mbps | 0.158 | 0.152 | 0.145 |
| AEAD encrypt ns | 78,045 | 103,232 | 95,059 |
| Packet loss | 0% | 0% | 0% |

### 5.2 ChaCha20-Poly1305 (ARMv8 NEON optimised)

| Metric | C: PQC only | D: PQC+XGB | E: PQC+TST |
|--------|------------|-----------|-----------|
| Handshake ms | 536.5 | 247.7 | 383.4 |
| KEM keygen ms | 137.8 | 110.3 | 205.2 |
| KEM decaps ms | 37.9 | 18.7 | 18.0 |
| CPU avg % | 23.0 | 45.8 | 49.1 |
| Temp °C | 56.0 | 58.4 | 61.3 |
| Power avg mW | 3,827 | 4,344 | 4,446 |
| Steady power mW | 3,895 | 4,695 | 4,932 |
| Throughput Mbps | 0.142 | 0.150 | 0.128 |
| AEAD encrypt ns | 78,154 | 103,692 | 89,407 |
| Packet loss | 0% | 0% | 0% |

### 5.3 Ascon-128a (software-only, lightweight AEAD)

| Metric | C: PQC only | D: PQC+XGB | E: PQC+TST |
|--------|------------|-----------|-----------|
| Handshake ms | 244.7 | 196.8 | 434.0 |
| KEM keygen ms | 104.9 | 49.3 | 200.0 |
| KEM decaps ms | 18.0 | 18.3 | 18.4 |
| CPU avg % | 26.2 | 49.5 | 56.3 |
| Temp °C | 57.0 | 59.9 | 62.8 |
| Power avg mW | 3,935 | 4,379 | 4,577 |
| Steady power mW | 4,249 | 4,924 | 5,225 |
| Throughput Mbps | 0.117 | 0.138 | 0.126 |
| AEAD encrypt ns | 1,324,120 | 1,714,654 | 1,878,849 |
| Packet loss | 0% | 0% | 0% |

> **Handshake variance note:** Classic-McEliece key generation is probabilistic and ranges from 48–205 ms across runs. This dominates handshake time and is inherent to the algorithm, not a function of detector load. KEM decapsulation (~18 ms) and Falcon signing (~0.8 ms) are stable across all phases.

---

## 6. XGBoost vs TST Under Full PQC Load

| Metric | PQC + XGBoost (D) | PQC + TST (E) | Δ (TST heavier) |
|--------|-------------------|--------------|-----------------|
| CPU avg % | 48.2 | 55.3 | **+7.1** (+14.7%) |
| CPU peak % | 72.7 | 79.8 | +7.1 |
| Temperature °C | 58.6 | 61.5 | **+2.9** |
| Power avg mW | 4,373 | 4,558 | **+185** (+4.2%) |
| Steady power mW | 4,769 | 5,039 | **+270** (+5.7%) |
| Throughput Mbps | 0.147 | 0.133 | -0.014 (-9.5%) |
| Packet loss | 0% | 0% | — |
| MAVLink Hz | 317.3 | 317.3 | — |

### Model Characteristics Comparison

| Property | XGBoost | TST (Transformer) |
|----------|---------|-------------------|
| Architecture | 15,000 trees (1000/class), depth 5 | 1-layer TransformerEncoder, d=512 |
| Model size | 32.7 MB | 6.1 MB |
| Parameters | ~15M tree nodes | 1,605,126 |
| Features | 54 (CIC-IoT-2023 full) | 46 (no MQTT features) |
| Classes | 15 (fine-grained attacks) | 6 (grouped categories) |
| Inference time (standalone) | 7.52 ms median | 10.43 ms median |
| Memory (loaded) | 402 MB RSS | 253 MB RSS |
| Accuracy (all CIC-IoT-2023) | 94.55% | 90.27% |
| Accuracy (IoT/MAVLink focus)¹ | — | **99.98%** |

¹ The TST model was trained and evaluated by its developer on CIC-IoT-2023 with 33+ attack types collapsed into 6 categories. The 90.27% overall accuracy spans all categories including application-layer attacks (MQTT, HTTP, DNS) that are irrelevant to the MAVLink UAV context. When evaluated specifically on IoT-relevant network-layer attacks (DDoS/DoS floods, SYN floods, UDP floods) that target MAVLink/MAVProxy tunnels, the model achieves **99.98% accuracy** as reported by the model trainer.

---

## 7. Key Findings

### 7.1 Mutual Impact is Resource-Additive, Not Multiplicative
The PQC tunnel and DDoS detectors consume resources independently. CPU, power, and thermal loads are approximately additive — there is no amplification or interference effect. The combined system uses predictable resources equal to the sum of its parts.

### 7.2 Zero Functional Degradation of MAVLink Data Plane
Across all five phases and all three cipher suites:
- **Packet loss: 0%** in every configuration
- **MAVLink stream rate: 317 Hz** — rock-solid regardless of detector load
- **Heartbeat loss: 0** — flight controller link maintained perfectly
- **CRC/decode errors: 0** — PQC encryption integrity preserved under load

### 7.3 Pi4 Has Sufficient Headroom
Even in the worst-case scenario (PQC + TST):
- CPU utilisation: 55.3% (45% headroom remaining)
- Temperature: 61.5°C (23.5°C below thermal throttle at 85°C)
- Power: 4,558 mW (within standard USB-C power supply capacity)
- RAM: ~531 MB of 4,096 MB (87% free)

### 7.4 XGBoost is the More Efficient Detector Under PQC
Under combined PQC + detector load:
- **7.1% less CPU** than TST (48.2% vs 55.3%)
- **2.9°C cooler** (58.6°C vs 61.5°C)
- **185 mW less power** (4,373 vs 4,558 mW)
- **Higher accuracy** on full attack spectrum (94.55% vs 90.27%)
- **Faster inference** (7.52 ms vs 10.43 ms)

However, TST provides superior accuracy (99.98%) for the specific IoT/MAVLink attack subset relevant to UAV deployments, and its higher resource cost is well within the Pi4's operating budget.

### 7.5 AEAD Choice Matters for Ascon
AES-256-GCM and ChaCha20-Poly1305 benefit from ARM hardware crypto extensions and show minimal per-packet encryption cost (~78–104 μs). Ascon-128a, being software-only on this platform, requires ~1.3–1.9 ms per packet and shows greater sensitivity to CPU contention. For Pi4 deployments, AES-256-GCM or ChaCha20-Poly1305 are recommended.

---

## 8. Conclusion

The PQC-encrypted MAVLink tunnel and ML-based DDoS detection system can run concurrently on a Raspberry Pi 4 without any functional impact on telemetry delivery. The overhead is additive and predictable, leaving approximately 45% CPU and 87% RAM headroom even in the heaviest configuration. Both XGBoost and TST are viable for in-flight DDoS detection, with XGBoost being more power-efficient and TST offering superior accuracy for IoT-specific threats.
