# Deep Dive Understandings

This document interprets the empirical findings from the benchmark comparisons (Baseline vs. XGBoost vs. Time Series Transformer) into deeper technical understandings regarding the intersection of Post-Quantum Cryptography (PQC), Machine Learning-based Intrusion Detection (DDoS), and edge computing constraints.

---

## 1. The PQC vs. ML Resource Collision

The fundamental tension in this architecture is that both advanced post-quantum secure communications and deep learning inference vie for the identical pool of scalar processing resources on the edge device (Raspberry Pi 4).

- **The "Overhead" is non-linear**: When the Time Series Transformer (TST) model runs concurrently with a heavyweight cryptographic suite (like `cs-classicmceliece8192128-ascon128a-sphincs256s`), the system does not simply sum their independent execution times. Cache thrashing, context-switching overhead, and CPU pipeline stalls compound to create super-linear latency degradation.
- **Thermal Velocity**: Sustaining a 90%+ CPU load (induced by TST) forces the SoC temperature to nearly 80°C. In this regime, the BCM2711 DVFS frequency scaling **is empirically confirmed**: the CSV `cpu_freq` column shows drops from **1800 MHz to 1520 MHz** during several TST runs. This creates a negative feedback loop: thermal throttling → slower crypto → longer run → more heat.
- **Load Average as a Saturation Indicator**: When `drone_load_1m` exceeds 4.0 (the core count), the OS run queue is oversubscribed. Under TST, load averages of 7.0–8.3 indicate that processes are spending significant time waiting for CPU, not executing. This directly explains the stochastic RTT spikes observed in the TST scenario.

## 2. Ascon's Disproportionate Vulnerability

A critical finding is that software-based AEADs (Ascon) degrade significantly worse under load than hardware-accelerated ciphers (AES-GCM).

- **Why?** AES-GCM benefits from ARMv8 Cryptography Extensions (CE), specifically the `AESE`, `AESMC`, and `PMULL` instructions. These execute in dedicated hardware execution units within the core pipeline. Ascon-128a, being a newer lightweight cipher without CE support on Cortex-A72, runs purely via generic ALU arithmetic (bitwise XOR, rotations, permutations).
- **The Quantitative Result**: When TST starves the ALU, Ascon takes a disproportionate latency hit. Baseline Ascon encrypt times are 1.32–1.40ms per packet, which is already 18x slower than AES-GCM's 70–77µs. Under TST load, Ascon degrades to 2.0–2.35ms (+48–76%), while AES-GCM only degrades to 97–132µs (+38–90% of a much smaller base).
- **The implication for MAVLink**: At a typical MAVLink telemetry rate of 200 pps (5ms inter-packet interval), Ascon encryption alone consumes 40–47% of the available inter-packet budget under TST. This explains why Ascon suites show lower `packets_sent` counts under load — the proxy simply cannot encrypt fast enough to keep up with the incoming telemetry stream.

## 3. The PQC Handshake (Re-keying) Hazard

PQC KEM generation or Signature verification during an active flight is risky.

- **Fast PQC (ML-KEM + Falcon/ML-DSA)**: Total crypto time is 1.8–5.3ms in baseline. This is entirely within a single MAVLink telemetry gap (~5ms at 200pps), making rekeying seamless and non-disruptive.
- **Moderate PQC (HQC)**: Total crypto time ranges 52–287ms. At L3/L5 security with HQC-256, the handshake occupies 250–490ms. During this window, the data plane continues operating under the old key, so there is no blackout, but the control plane thread is blocked.
- **Heavy PQC (McEliece + SPHINCS+)**: Total crypto time can exceed 1–4 seconds. Under TST load, `cs-classicmceliece8192128-ascon128a-falcon1024` took 3,824ms for a single handshake. During this 3.8-second window, the control plane is unresponsive. If the old session key expires or the nonce counter wraps, the data plane will stall until the new key material is established.
- **The McEliece-460896+SPHINCS-192s Hard Failure**: This combination consistently times out at ~48 seconds across all scenarios. The combined cost of McEliece-460896 key generation (~311ms baseline) plus SPHINCS-192s signing (~1293ms baseline) totals ~1600ms just for the cryptographic operations. However, the GCS-side McEliece key generation takes much longer (~3200–5200ms), and this cascading delay causes the TCP handshake protocol to exceed its 50-second timeout. This is an inherent algorithm incompatibility for this platform.

## 4. Understanding Power Signatures

The energy per handshake (`E/HS`) metric reveals the true cost of PQC.

- **Instantaneous Power is Deceptive**: While instantaneous power only rises from ~3.9W to ~5.6W under TST load (+43%), the *time* it takes to complete a handshake multiplies that power factor significantly. Energy = Power × Time.
- **Fast suites**: ML-KEM-512+Falcon consumes 0.063 J/handshake baseline, rising to 0.098 J/handshake under TST. This is millijoules — effectively invisible in a battery budget.
- **Heavy suites**: McEliece-8192128+SPHINCS-256s+Ascon consumes 11.09 J/handshake in baseline and 23.81 J/handshake under TST. For a typical drone battery (e.g., 3S 2200mAh = ~24.4Wh = ~87,840 J), a single handshake under TST load consumes 0.027% of total battery capacity. At a 30-second rekey interval, this amounts to 2,857 J/hr (3.25% battery/hr just for rekeying).
- **Battery Exhaustion Attack**: An adversary who can trigger constant rekeying (e.g., by jamming the data plane to force the proxy's circuit breaker to trigger new handshakes) could weaponize the heavy crypto cost. With McEliece-8192128+SPHINCS suites under DDoS, each forced rekey consumes 23.81J. Triggering one rekey per 10 seconds would drain the drone's battery at 8,571 J/hr — approximately 10% of total capacity per hour, on top of normal flight power.

## 5. The XGBoost vs. TST Overhead Dichotomy

The benchmarks reveal a clear bifurcation between the two DDoS detection approaches:

- **XGBoost (ddos-xgboost)**: Adds a consistent +25pp to CPU utilization and +20-25% to power consumption. The impact on crypto latency is modest (+5–30ms handshake, +14–40% AEAD encrypt). XGBoost's tree-based inference is computationally lightweight and scales sub-linearly with feature count.
- **TST (ddos-txt)**: Adds +60–65pp to CPU and +38–48% to power. The impact on crypto latency is severe and variable (+30–300% handshake, +48–90% AEAD encrypt). The Transformer's multi-head attention mechanism requires dense matrix multiplications that monopolize all four cores.
- **The key insight**: XGBoost provides DDoS detection at an acceptable cost — the system remains functional for all viable crypto suites. TST provides potentially better detection accuracy but pushes the system into a regime where only the lightest crypto suites (ML-KEM-512 + Falcon + AES-GCM/ChaCha20) remain viable for real-time telemetry.

## 6. Memory is NOT the Bottleneck

A notable non-finding: memory is entirely stable across scenarios.

- **RSS Stability**: The proxy's resident set size (51.5–60.2 MB) does not increase under DDoS load. This is because the ML detectors run as separate OS processes — they have their own RSS. The proxy's own memory footprint is dominated by Python's runtime, the OQS library, and the socket buffers.
- **KEM Key Size vs. RSS**: McEliece-8192128 measures 53–57 MB RSS in E2E runs — only ~9 MB more than ML-KEM suites (48–49 MB). The modest increase is consistent with the 1.36 MB public key being held in memory. *Note: the book claims 1.45 GB for McEliece-8192128 during isolated keygen micro-benchmarks, but this is NOT observed in E2E proxy data, likely because the GCS performs keygen and/or Python releases memory before measurement.*
- **VMS Constancy**: Virtual memory (~649–657 MB) is dominated by shared libraries (liboqs, Python, numpy). The ML scenario does not link additional libraries into the proxy process.

## 7. Zero Loss — The Proxy's Defensive Architecture Works

Across all 214 successful runs:
- `packet_loss_ratio` = 0.0
- `drop_replay` = 0
- `drop_auth` = 0
- `mavlink_crc_errors` = 0

This means the proxy's defensive mechanisms (sequence validation, AEAD authentication tag verification, replay window checking) never falsely reject legitimate traffic, even under extreme CPU/thermal stress. The quality degradation is purely latency-based, not integrity-based. This is a critical design validation: the system degrades gracefully (higher RTT, lower throughput) rather than catastrophically (dropped packets, corrupted telemetry).

## 8. RTT Outliers Reveal OS Scheduler Interference

Several runs show extreme RTT outlier behavior that cannot be explained by crypto cost alone:

- `cs-mlkem1024-aesgcm-mldsa87` baseline: 59.98ms avg, 202.82ms p95. ML-KEM+ML-DSA crypto takes <3ms total. The 200ms p95 RTT implies the proxy's UDP receive/send loop was preempted by the OS scheduler for ~200ms.
- Under XGBoost: `cs-classicmceliece460896-aesgcm-mldsa65` hit 120.77ms avg, 465.37ms p95. The 465ms p95 indicates the scheduler held the proxy off-CPU for nearly half a second.
- These outliers are stochastic and not consistently reproducible — they depend on OS scheduling decisions, background processes, and Python's GIL contention with garbage collection pauses.

The implication: **real-time guarantees cannot be provided with Linux's CFS scheduler + Python's GIL**. For safety-critical deployments, the proxy would need to be ported to C/Rust with SCHED_FIFO priority or deployed on an RTOS.
