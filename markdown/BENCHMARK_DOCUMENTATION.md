# Post-Quantum Cryptography Benchmark Documentation

## Secure-Tunnel PQC Performance Benchmarks

**Document Version:** 1.0  
**Benchmark Date:** January 10, 2026  
**Documentation Date:** January 11, 2026

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Test Environment](#2-test-environment)
3. [Benchmark Methodology](#3-benchmark-methodology)
4. [Algorithm Coverage](#4-algorithm-coverage)
5. [KEM Benchmark Results](#5-kem-benchmark-results)
6. [Signature Benchmark Results](#6-signature-benchmark-results)
7. [AEAD Benchmark Results](#7-aead-benchmark-results)
8. [Full Suite Benchmark Results](#8-full-suite-benchmark-results)
9. [Size Metrics Summary](#9-size-metrics-summary)
10. [Data Integrity Verification](#10-data-integrity-verification)
11. [Raw Data Location](#11-raw-data-location)
12. [Appendix: Algorithm Specifications](#appendix-algorithm-specifications)

---

## 1. Executive Summary

This document provides comprehensive documentation of post-quantum cryptography (PQC) benchmarks executed on an embedded ARM platform (Raspberry Pi 4). The benchmarks measure real-world performance of NIST-standardized and candidate PQC algorithms as implemented in liboqs.

### Key Findings

| Metric | Value |
|--------|-------|
| Total Benchmark Files | 98 |
| Total Iterations Executed | 19,600 |
| Overall Success Rate | **100.00%** |
| Benchmark Duration | ~63 minutes |
| KEM Algorithms Tested | 9 (27 files) |
| Signature Algorithms Tested | 8 (24 files) |
| AEAD Algorithms Tested | 3 (24 files) |
| Full Handshake Suites Tested | 23 |

### Fastest Algorithms by Category

| Category | Algorithm | Operation | Median Time |
|----------|-----------|-----------|-------------|
| KEM | ML-KEM-512 | encapsulate | 0.0617 ms |
| KEM | ML-KEM-512 | decapsulate | 0.0668 ms |
| Signature | Falcon-512 | verify | 0.1097 ms |
| Signature | ML-DSA-44 | verify | 0.2462 ms |
| AEAD | Ascon-128a | encrypt | 0.0041 ms |

---

## 2. Test Environment

### Hardware Platform

| Component | Specification |
|-----------|---------------|
| **Device** | Raspberry Pi 4 Model B Rev 1.5 |
| **CPU** | Broadcom BCM2711, Quad-core Cortex-A72 (ARM v8) |
| **CPU Architecture** | ARMv8-A (64-bit) |
| **CPU Frequency** | Up to 1.8 GHz |
| **CPU Features** | fp asimd evtstrm crc32 cpuid |
| **Memory** | 4 GB LPDDR4-3200 |
| **CPU Frequency Governor** | ondemand |
| **Hostname** | uavpi |

### Software Environment

| Component | Version |
|-----------|---------|
| **Operating System** | Debian GNU/Linux (Bookworm) |
| **Kernel** | 6.12.47+rpt-rpi-v8 |
| **Python** | 3.11.2 |
| **GCC** | 12.2.0 |
| **liboqs-python** | 0.14.0 |
| **liboqs (native)** | 0.14.1-dev |
| **cryptography** | 46.0.2 |
| **ascon** | 0.0.9 |

### Git Repository State

| Attribute | Value |
|-----------|-------|
| **Commit** | `49ed2123523748810d04664ff2a27cb43a0c1d86` |
| **Branch** | main |
| **Clean State** | No (uncommitted changes present) |

---

## 3. Benchmark Methodology

### Measurement Approach

The benchmark script (`bench/benchmark_pqc.py`) implements a rigorous measurement methodology:

1. **Dual Timing Measurement**
   - `time.perf_counter_ns()` → High-resolution monotonic clock (perf_time_ns)
   - `time.time_ns()` → Wall clock time (wall_time_ns)

2. **Iteration Count**
   - 200 iterations per measurement
   - No warm-up iterations discarded
   - All iterations recorded for statistical analysis

3. **Data Recording**
   - Individual iteration timestamps
   - Success/failure status per iteration
   - Key/ciphertext/signature sizes (where applicable)
   - Power monitoring fields (prepared but not populated in this run)
   - Performance counter fields (prepared but not populated in this run)

### Timing Methodology

```
for iteration in range(200):
    start_wall = time.time_ns()
    start_perf = time.perf_counter_ns()
    
    # Execute cryptographic operation
    result = operation()
    
    end_perf = time.perf_counter_ns()
    end_wall = time.time_ns()
    
    wall_time_ns = end_wall - start_wall
    perf_time_ns = end_perf - start_perf
```

### Statistical Metrics

For each algorithm/operation, the following statistics are computed:
- **Mean**: Average execution time
- **Median**: 50th percentile (robust to outliers)
- **Min**: Fastest execution
- **Max**: Slowest execution (captures worst-case)
- **Standard Deviation**: Timing variability

---

## 4. Algorithm Coverage

### 4.1 Key Encapsulation Mechanisms (KEMs)

| Algorithm | NIST Level | Family | Operations |
|-----------|------------|--------|------------|
| ML-KEM-512 | L1 | Lattice (MLWE) | keygen, encapsulate, decapsulate |
| ML-KEM-768 | L3 | Lattice (MLWE) | keygen, encapsulate, decapsulate |
| ML-KEM-1024 | L5 | Lattice (MLWE) | keygen, encapsulate, decapsulate |
| Classic-McEliece-348864 | L1 | Code-based | keygen, encapsulate, decapsulate |
| Classic-McEliece-460896 | L3 | Code-based | keygen, encapsulate, decapsulate |
| Classic-McEliece-8192128 | L5 | Code-based | keygen, encapsulate, decapsulate |
| HQC-128 | L1 | Code-based (MDPC) | keygen, encapsulate, decapsulate |
| HQC-192 | L3 | Code-based (MDPC) | keygen, encapsulate, decapsulate |
| HQC-256 | L5 | Code-based (MDPC) | keygen, encapsulate, decapsulate |

**Total KEM Files:** 9 algorithms × 3 operations = 27 files

### 4.2 Digital Signature Algorithms

| Algorithm | NIST Level | Family | Operations |
|-----------|------------|--------|------------|
| ML-DSA-44 | L1 | Lattice (MLWE) | keygen, sign, verify |
| ML-DSA-65 | L3 | Lattice (MLWE) | keygen, sign, verify |
| ML-DSA-87 | L5 | Lattice (MLWE) | keygen, sign, verify |
| Falcon-512 | L1 | Lattice (NTRU) | keygen, sign, verify |
| Falcon-1024 | L5 | Lattice (NTRU) | keygen, sign, verify |
| SPHINCS+-SHA2-128s-simple | L1 | Hash-based | keygen, sign, verify |
| SPHINCS+-SHA2-192s-simple | L3 | Hash-based | keygen, sign, verify |
| SPHINCS+-SHA2-256s-simple | L5 | Hash-based | keygen, sign, verify |

**Total SIG Files:** 8 algorithms × 3 operations = 24 files

### 4.3 Authenticated Encryption (AEAD)

| Algorithm | Type | Payload Sizes | Operations |
|-----------|------|---------------|------------|
| AES-256-GCM | Block cipher | 64, 256, 1024, 4096 B | encrypt, decrypt |
| ChaCha20-Poly1305 | Stream cipher | 64, 256, 1024, 4096 B | encrypt, decrypt |
| Ascon-128a | Lightweight | 64, 256, 1024, 4096 B | encrypt, decrypt |

**Total AEAD Files:** 3 algorithms × 4 sizes × 2 operations = 24 files

### 4.4 Full Handshake Suites

23 cipher suite combinations tested for full handshake performance:

**L1 Suites (9):**
- Classic-McEliece-348864 + (AES-GCM | ChaCha20-Poly1305 | Ascon-128a) + (Falcon-512 | ML-DSA-44 | SPHINCS+-128s)

**L3 Suites (6):**
- Classic-McEliece-460896 + (AES-GCM | ChaCha20-Poly1305 | Ascon-128a) + (ML-DSA-65 | SPHINCS+-192s)

**L5 Suites (8):**
- Classic-McEliece-8192128 + (AES-GCM | ChaCha20-Poly1305 | Ascon-128a) + (Falcon-1024 | ML-DSA-87 | SPHINCS+-256s)

---

## 5. KEM Benchmark Results

### 5.1 ML-KEM (NIST FIPS 203 Standardized)

#### ML-KEM-512 (NIST Level 1)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 0.1160 | 0.0817 | 0.0800 | 6.4350 | 200 |
| encapsulate | 0.0658 | 0.0617 | 0.0602 | 0.3408 | 200 |
| decapsulate | 0.0706 | 0.0668 | 0.0654 | 0.3549 | 200 |

**Key Sizes:** Public key: 800 B, Secret key: 1,632 B, Ciphertext: 768 B

#### ML-KEM-768 (NIST Level 3)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 0.1113 | 0.1073 | 0.1059 | 0.6638 | 200 |
| encapsulate | 0.0890 | 0.0860 | 0.0850 | 0.3614 | 200 |
| decapsulate | 0.0965 | 0.0941 | 0.0934 | 0.3479 | 200 |

**Key Sizes:** Public key: 1,184 B, Secret key: 2,400 B, Ciphertext: 1,088 B

#### ML-KEM-1024 (NIST Level 5)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 0.1425 | 0.1362 | 0.1344 | 0.5097 | 200 |
| encapsulate | 0.1208 | 0.1177 | 0.1167 | 0.3940 | 200 |
| decapsulate | 0.1443 | 0.1363 | 0.1315 | 0.5510 | 200 |

**Key Sizes:** Public key: 1,568 B, Secret key: 3,168 B, Ciphertext: 1,568 B

### 5.2 Classic McEliece (Code-Based)

#### Classic-McEliece-348864 (NIST Level 1)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 333.3880 | 228.6231 | 151.1239 | 1,524.7559 | 200 |
| encapsulate | 0.2676 | 0.2598 | 0.2476 | 0.6503 | 200 |
| decapsulate | 55.4461 | 55.4279 | 55.3719 | 56.1860 | 200 |

**Key Sizes:** Public key: 261,120 B (255 KB), Secret key: 6,492 B, Ciphertext: 96 B

#### Classic-McEliece-460896 (NIST Level 3)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 1,114.6660 | 911.5174 | 465.0085 | 5,149.9653 | 200 |
| encapsulate | 0.6612 | 0.6399 | 0.5950 | 1.1128 | 200 |
| decapsulate | 89.4028 | 89.3768 | 89.3269 | 91.1989 | 200 |

**Key Sizes:** Public key: 524,160 B (512 KB), Secret key: 13,608 B, Ciphertext: 156 B

#### Classic-McEliece-8192128 (NIST Level 5)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 8,834.7432 | 7,065.8118 | 2,467.1104 | 36,617.4157 | 200 |
| encapsulate | 2.0100 | 1.9907 | 1.9041 | 2.4335 | 200 |
| decapsulate | 209.0644 | 208.9991 | 208.8759 | 212.1821 | 200 |

**Key Sizes:** Public key: 1,357,824 B (1.3 MB), Secret key: 14,120 B, Ciphertext: 208 B

### 5.3 HQC (Code-Based, MDPC)

#### HQC-128 (NIST Level 1)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 22.0975 | 22.0581 | 21.9925 | 24.8252 | 200 |
| encapsulate | 44.6651 | 44.5368 | 44.4740 | 46.8946 | 200 |
| decapsulate | 73.0474 | 73.0288 | 72.8733 | 73.8298 | 200 |

**Key Sizes:** Public key: 2,249 B, Secret key: 2,305 B, Ciphertext: 4,433 B

#### HQC-192 (NIST Level 3)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 67.4492 | 67.3574 | 67.2642 | 72.6780 | 200 |
| encapsulate | 135.3864 | 135.2640 | 135.1001 | 140.4957 | 200 |
| decapsulate | 211.1887 | 211.1353 | 210.8480 | 213.3543 | 200 |

**Key Sizes:** Public key: 4,522 B, Secret key: 4,586 B, Ciphertext: 8,978 B

#### HQC-256 (NIST Level 5)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 123.5944 | 123.5352 | 123.3974 | 126.3154 | 200 |
| encapsulate | 248.7902 | 248.6750 | 248.4578 | 252.9277 | 200 |
| decapsulate | 392.3100 | 392.1528 | 391.6466 | 401.1519 | 200 |

**Key Sizes:** Public key: 7,245 B, Secret key: 7,317 B, Ciphertext: 14,421 B

---

## 6. Signature Benchmark Results

### 6.1 ML-DSA (NIST FIPS 204 Standardized)

#### ML-DSA-44 (NIST Level 1)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 0.2566 | 0.2517 | 0.2476 | 0.7191 | 200 |
| sign | 1.0330 | 0.8516 | 0.4164 | 4.1128 | 200 |
| verify | 0.2487 | 0.2462 | 0.2454 | 0.4667 | 200 |

**Key Sizes:** Public key: 1,312 B, Secret key: 2,560 B, Signature: 2,420 B

#### ML-DSA-65 (NIST Level 3)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 0.4190 | 0.4147 | 0.4117 | 0.7982 | 200 |
| sign | 1.5910 | 1.2882 | 0.6091 | 6.8907 | 200 |
| verify | 0.3842 | 0.3824 | 0.3806 | 0.5270 | 200 |

**Key Sizes:** Public key: 1,952 B, Secret key: 4,032 B, Signature: 3,309 B

#### ML-DSA-87 (NIST Level 5)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 0.6140 | 0.6096 | 0.6013 | 0.9624 | 200 |
| sign | 1.7686 | 1.4805 | 0.9194 | 6.1680 | 200 |
| verify | 0.6128 | 0.6105 | 0.6068 | 0.7609 | 200 |

**Key Sizes:** Public key: 2,592 B, Secret key: 4,896 B, Signature: 4,627 B

### 6.2 Falcon (NTRU Lattice-Based)

#### Falcon-512 (NIST Level 1)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 18.8718 | 17.6348 | 13.6429 | 41.6204 | 200 |
| sign | 0.6486 | 0.6413 | 0.6264 | 1.3606 | 200 |
| verify | 0.1117 | 0.1097 | 0.1087 | 0.3072 | 200 |

**Key Sizes:** Public key: 897 B, Secret key: 1,281 B, Signature: 659 B

#### Falcon-1024 (NIST Level 5)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 51.0148 | 47.2922 | 41.5969 | 111.8695 | 200 |
| sign | 1.3071 | 1.2956 | 1.2689 | 1.7990 | 200 |
| verify | 0.1952 | 0.1931 | 0.1925 | 0.4175 | 200 |

**Key Sizes:** Public key: 1,793 B, Secret key: 2,305 B, Signature: 1,267 B

### 6.3 SPHINCS+ (Hash-Based, Stateless)

#### SPHINCS+-SHA2-128s-simple (NIST Level 1)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 193.2574 | 193.1087 | 192.9034 | 197.6758 | 200 |
| sign | 1,460.8702 | 1,460.2866 | 1,459.3653 | 1,470.5768 | 200 |
| verify | 1.4905 | 1.4883 | 1.4834 | 1.6471 | 200 |

**Key Sizes:** Public key: 32 B, Secret key: 64 B, Signature: 7,856 B

#### SPHINCS+-SHA2-192s-simple (NIST Level 3)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 280.8795 | 280.5527 | 280.2563 | 287.3639 | 200 |
| sign | 2,611.1025 | 2,598.4655 | 2,596.1748 | 4,807.1272 | 200 |
| verify | 2.1999 | 2.1891 | 2.1808 | 2.3759 | 200 |

**Key Sizes:** Public key: 48 B, Secret key: 96 B, Signature: 16,224 B

#### SPHINCS+-SHA2-256s-simple (NIST Level 5)

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | Iterations |
|-----------|-----------|-------------|----------|----------|------------|
| keygen | 186.0523 | 186.0045 | 185.6673 | 187.6280 | 200 |
| sign | 2,308.3556 | 2,307.4613 | 2,305.9156 | 2,325.3317 | 200 |
| verify | 3.1179 | 3.0906 | 3.0797 | 3.5139 | 200 |

**Key Sizes:** Public key: 64 B, Secret key: 128 B, Signature: 29,792 B

---

## 7. AEAD Benchmark Results

### 7.1 AES-256-GCM

| Payload Size | Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) |
|--------------|-----------|-----------|-------------|----------|----------|
| 64 B | encrypt | 0.0079 | 0.0073 | 0.0071 | 0.0902 |
| 64 B | decrypt | 0.0079 | 0.0077 | 0.0075 | 0.0261 |
| 256 B | encrypt | 0.0691 | 0.0669 | 0.0659 | 0.1855 |
| 256 B | decrypt | 0.0678 | 0.0638 | 0.0628 | 0.1976 |
| 1024 B | encrypt | 0.0873 | 0.0826 | 0.0813 | 0.2093 |
| 1024 B | decrypt | 0.0827 | 0.0796 | 0.0786 | 0.2054 |
| 4096 B | encrypt | 0.1402 | 0.1355 | 0.1341 | 0.2951 |
| 4096 B | decrypt | 0.1367 | 0.1331 | 0.1320 | 0.2522 |

### 7.2 ChaCha20-Poly1305

| Payload Size | Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) |
|--------------|-----------|-----------|-------------|----------|----------|
| 64 B | encrypt | 0.0323 | 0.0067 | 0.0065 | 5.0820 |
| 64 B | decrypt | 0.0075 | 0.0071 | 0.0069 | 0.0526 |
| 256 B | encrypt | 0.0631 | 0.0595 | 0.0586 | 0.1776 |
| 256 B | decrypt | 0.0598 | 0.0573 | 0.0565 | 0.1861 |
| 1024 B | encrypt | 0.0685 | 0.0647 | 0.0638 | 0.1947 |
| 1024 B | decrypt | 0.0653 | 0.0625 | 0.0615 | 0.1889 |
| 4096 B | encrypt | 0.0796 | 0.0753 | 0.0744 | 0.1999 |
| 4096 B | decrypt | 0.0781 | 0.0741 | 0.0732 | 0.2318 |

### 7.3 Ascon-128a (Lightweight)

| Payload Size | Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) |
|--------------|-----------|-----------|-------------|----------|----------|
| 64 B | encrypt | 0.0044 | 0.0041 | 0.0039 | 0.0256 |
| 64 B | decrypt | 0.0044 | 0.0042 | 0.0040 | 0.0207 |
| 256 B | encrypt | 0.0052 | 0.0048 | 0.0046 | 0.0329 |
| 256 B | decrypt | 0.0060 | 0.0052 | 0.0049 | 0.0306 |
| 1024 B | encrypt | 0.0091 | 0.0083 | 0.0081 | 0.0947 |
| 1024 B | decrypt | 0.0102 | 0.0088 | 0.0086 | 0.0982 |
| 4096 B | encrypt | 0.0212 | 0.0204 | 0.0202 | 0.1162 |
| 4096 B | decrypt | 0.0223 | 0.0213 | 0.0210 | 0.1216 |

---

## 8. Full Suite Benchmark Results

Full handshake benchmarks measure the complete cryptographic suite performance including:
- KEM key generation
- KEM encapsulation
- KEM decapsulation
- Signature generation
- Signature verification
- AEAD encryption/decryption

### 8.1 NIST Level 1 Suites (Classic-McEliece-348864)

| Suite | Mean (ms) | Median (ms) | Min (ms) | Max (ms) |
|-------|-----------|-------------|----------|----------|
| McEliece-348864 + AES-GCM + Falcon-512 | 402.18 | 358.16 | 213.59 | 1,369.79 |
| McEliece-348864 + AES-GCM + ML-DSA-44 | 396.70 | 287.50 | 213.41 | 1,441.80 |
| McEliece-348864 + AES-GCM + SPHINCS+-128s | 1,839.14 | 1,754.72 | 1,675.81 | 2,398.43 |
| McEliece-348864 + ChaCha20 + Falcon-512 | 364.35 | 287.16 | 213.50 | 1,156.17 |
| McEliece-348864 + ChaCha20 + ML-DSA-44 | 399.69 | 358.43 | 213.43 | 1,155.34 |
| McEliece-348864 + ChaCha20 + SPHINCS+-128s | 1,848.63 | 1,789.63 | 1,675.68 | 3,122.71 |
| McEliece-348864 + Ascon + Falcon-512 | 419.55 | 358.04 | 213.49 | 1,456.03 |
| McEliece-348864 + Ascon + ML-DSA-44 | 373.72 | 288.72 | 213.39 | 1,732.16 |
| McEliece-348864 + Ascon + SPHINCS+-128s | 1,872.90 | 1,820.93 | 1,675.76 | 3,413.38 |

### 8.2 NIST Level 3 Suites (Classic-McEliece-460896)

| Suite | Mean (ms) | Median (ms) | Min (ms) | Max (ms) |
|-------|-----------|-------------|----------|----------|
| McEliece-460896 + AES-GCM + ML-DSA-65 | 1,279.33 | 1,091.04 | 574.99 | 6,623.37 |
| McEliece-460896 + AES-GCM + SPHINCS+-192s | 3,839.37 | 3,701.47 | 3,177.08 | 7,263.49 |
| McEliece-460896 + ChaCha20 + ML-DSA-65 | 1,309.58 | 1,099.99 | 576.21 | 6,399.93 |
| McEliece-460896 + ChaCha20 + SPHINCS+-192s | 3,859.93 | 3,480.29 | 3,175.11 | 8,208.80 |
| McEliece-460896 + Ascon + ML-DSA-65 | 1,262.72 | 1,095.85 | 574.26 | 5,076.95 |
| McEliece-460896 + Ascon + SPHINCS+-192s | 3,807.31 | 3,697.99 | 3,173.01 | 5,889.15 |

### 8.3 NIST Level 5 Suites (Classic-McEliece-8192128)

| Suite | Mean (ms) | Median (ms) | Min (ms) | Max (ms) |
|-------|-----------|-------------|----------|----------|
| McEliece-8192128 + AES-GCM + Falcon-1024 | 9,283.75 | 7,591.18 | 2,580.85 | 38,487.10 |
| McEliece-8192128 + AES-GCM + ML-DSA-87 | 8,897.82 | 7,645.65 | 2,746.67 | 36,728.97 |
| McEliece-8192128 + AES-GCM + SPHINCS+-256s | 12,377.19 | 9,948.37 | 5,093.30 | 63,136.68 |
| McEliece-8192128 + ChaCha20 + Falcon-1024 | 9,010.98 | 6,436.44 | 2,556.11 | 34,145.39 |
| McEliece-8192128 + ChaCha20 + ML-DSA-87 | 8,944.76 | 5,428.84 | 2,497.54 | 41,307.07 |
| McEliece-8192128 + ChaCha20 + SPHINCS+-256s | 10,801.76 | 9,823.78 | 5,037.77 | 45,936.41 |
| McEliece-8192128 + Ascon + Falcon-1024 | 8,446.91 | 5,437.86 | 2,550.29 | 34,295.25 |
| McEliece-8192128 + Ascon + ML-DSA-87 | 8,461.18 | 5,356.60 | 2,825.84 | 36,583.80 |

---

## 9. Size Metrics Summary

### 9.1 KEM Sizes

| Algorithm | Public Key | Secret Key | Ciphertext | Shared Secret |
|-----------|------------|------------|------------|---------------|
| ML-KEM-512 | 800 B | 1,632 B | 768 B | 32 B |
| ML-KEM-768 | 1,184 B | 2,400 B | 1,088 B | 32 B |
| ML-KEM-1024 | 1,568 B | 3,168 B | 1,568 B | 32 B |
| McEliece-348864 | 261,120 B | 6,492 B | 96 B | 32 B |
| McEliece-460896 | 524,160 B | 13,608 B | 156 B | 32 B |
| McEliece-8192128 | 1,357,824 B | 14,120 B | 208 B | 32 B |
| HQC-128 | 2,249 B | 2,305 B | 4,433 B | 32 B |
| HQC-192 | 4,522 B | 4,586 B | 8,978 B | 32 B |
| HQC-256 | 7,245 B | 7,317 B | 14,421 B | 32 B |

### 9.2 Signature Sizes

| Algorithm | Public Key | Secret Key | Signature |
|-----------|------------|------------|-----------|
| ML-DSA-44 | 1,312 B | 2,560 B | 2,420 B |
| ML-DSA-65 | 1,952 B | 4,032 B | 3,309 B |
| ML-DSA-87 | 2,592 B | 4,896 B | 4,627 B |
| Falcon-512 | 897 B | 1,281 B | 659 B |
| Falcon-1024 | 1,793 B | 2,305 B | 1,267 B |
| SPHINCS+-128s | 32 B | 64 B | 7,856 B |
| SPHINCS+-192s | 48 B | 96 B | 16,224 B |
| SPHINCS+-256s | 64 B | 128 B | 29,792 B |

---

## 10. Data Integrity Verification

### 10.1 Validation Results

| Category | Files | Total Iterations | Successful | Failed | Success Rate |
|----------|-------|------------------|------------|--------|--------------|
| KEM | 27 | 5,400 | 5,400 | 0 | **100.00%** |
| SIG | 24 | 4,800 | 4,800 | 0 | **100.00%** |
| AEAD | 24 | 4,800 | 4,800 | 0 | **100.00%** |
| Suites | 23 | 4,600 | 4,600 | 0 | **100.00%** |
| **Total** | **98** | **19,600** | **19,600** | **0** | **100.00%** |

### 10.2 Consistency Checks

| Check | Status |
|-------|--------|
| All files have same git commit | ✅ PASS |
| All files have same hostname | ✅ PASS |
| All files have 200 iterations | ✅ PASS |
| No empty JSON files | ✅ PASS |
| All JSON files properly terminated | ✅ PASS |
| Timestamps in sequential order | ✅ PASS |

### 10.3 Execution Timeline

| Phase | Start Time (UTC) | Duration |
|-------|------------------|----------|
| Environment Init | 05:44:22 | - |
| KEM Benchmarks | 05:44:23 | ~40 min |
| SIG Benchmarks | 06:24:24 | ~24 min |
| AEAD Benchmarks | 06:48:18 | ~1 min |
| Suite Benchmarks | 06:48:18+ | Concurrent |

---

## 11. Raw Data Location

All benchmark data is stored on the target system:

```
~/secure-tunnel/bench_results/
├── environment.json           # System metadata
├── summary/
│   ├── aead_summary.csv       # AEAD aggregate statistics
│   └── aead_summary.json      # AEAD aggregate statistics (JSON)
└── raw/
    ├── kem/                   # 27 KEM benchmark files
    │   ├── ML_KEM_512_keygen.json
    │   ├── ML_KEM_512_encapsulate.json
    │   ├── ML_KEM_512_decapsulate.json
    │   └── ...
    ├── sig/                   # 24 signature benchmark files
    │   ├── ML_DSA_44_keygen.json
    │   ├── ML_DSA_44_sign.json
    │   ├── ML_DSA_44_verify.json
    │   └── ...
    ├── aead/                  # 24 AEAD benchmark files
    │   ├── AES_256_GCM_encrypt_64B.json
    │   ├── AES_256_GCM_decrypt_64B.json
    │   └── ...
    └── suites/                # 23 full handshake files
        ├── cs_classicmceliece348864_aesgcm_falcon512_full_handshake.json
        └── ...
```

**Total Data Size:** 9.9 MB

---

## Appendix: Algorithm Specifications

### A.1 NIST Security Levels

| Level | Classical Security | Quantum Security | Equivalent AES |
|-------|-------------------|------------------|----------------|
| L1 | 128-bit | 64-bit | AES-128 |
| L2 | 160-bit | 80-bit | SHA-256/SHA3-256 |
| L3 | 192-bit | 96-bit | AES-192 |
| L4 | 224-bit | 112-bit | SHA-384/SHA3-384 |
| L5 | 256-bit | 128-bit | AES-256 |

### A.2 Algorithm Standards Status

| Algorithm | Standard | Status |
|-----------|----------|--------|
| ML-KEM | FIPS 203 | Standardized (August 2024) |
| ML-DSA | FIPS 204 | Standardized (August 2024) |
| SLH-DSA (SPHINCS+) | FIPS 205 | Standardized (August 2024) |
| Falcon | NIST Round 4 | Under standardization |
| Classic-McEliece | NIST Round 4 | Under standardization |
| HQC | NIST Round 4 | Under standardization |

### A.3 Algorithm Families

| Family | Algorithms | Hard Problem |
|--------|------------|--------------|
| Lattice (Module-LWE) | ML-KEM, ML-DSA | Learning With Errors |
| Lattice (NTRU) | Falcon | NTRU assumption |
| Code-based (Goppa) | Classic-McEliece | Syndrome Decoding |
| Code-based (MDPC) | HQC | QC-MDPC Syndrome Decoding |
| Hash-based | SPHINCS+ | Hash function properties |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-11 | Benchmark Engineer | Initial comprehensive documentation |

---

**END OF DOCUMENT**
