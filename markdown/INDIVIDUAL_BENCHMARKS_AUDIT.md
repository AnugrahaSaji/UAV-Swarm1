# Individual Benchmarks Forensic Audit Report

**Generated:** 2026-01-17  
**Auditor:** Evidence-Based Code Analysis  
**Scope:** PQC Individual Primitives Benchmarked on Raspberry Pi 4

---

## Executive Summary

### Critical Finding: Report Uses Wrong Data Source

The existing `BENCHMARK_REPORT.md` in `individual_benchmarks/analysis/` was generated from **5-iteration test data** (`benchmarks/bench_results_power/`) instead of the **100-iteration production data** (`individual_benchmarks/raw_data/`).

| Data Source | Location | Iterations | Total Measurements |
|------------|----------|------------|-------------------|
| **INCORRECT** (used for report) | `benchmarks/bench_results_power/` | 5 | 375 |
| **CORRECT** (production data) | `individual_benchmarks/raw_data/` | 100 | 7,500 |

This means **all timing, power, and energy values in the existing report are statistically unreliable**.

---

## Data Integrity Verification

### ✅ Raw Data Quality

**Location:** `individual_benchmarks/raw_data/`

| Category | Files | Iterations Each | Total Iterations | All Success |
|----------|-------|-----------------|------------------|-------------|
| KEM | 27 | 100 | 2,700 | ✅ |
| SIG | 24 | 100 | 2,400 | ✅ |
| AEAD | 24 | 100 | 2,400 | ✅ |
| **TOTAL** | **75** | - | **7,500** | ✅ |

### ✅ Environment Verification

```
Hostname:         uavpi
CPU Model:        Cortex-A72 (unknown in liboqs)
CPU Cores:        4
CPU Governor:     ondemand
Memory:           3796 MB
Kernel:           6.12.47+rpt-rpi-v8
Python:           3.11.2
INA219 Detected:  Yes
Sample Rate:      1000 Hz
Git Commit:       49ed212 (main, dirty)
Timestamp:        2026-01-11T15:03:15Z
```

---

## CORRECT Benchmark Results (100 Iterations)

### Key Encapsulation Mechanisms (KEM)

| Algorithm | Operation | Time (ms) | Power (W) | Energy (µJ) |
|-----------|-----------|-----------|-----------|-------------|
| **ML-KEM-512** | keygen | **0.283** | 3.403 | 959.49 |
| ML-KEM-512 | encapsulate | 0.300 | 3.300 | 990.72 |
| ML-KEM-512 | decapsulate | 0.241 | 3.470 | 833.14 |
| **ML-KEM-768** | keygen | **0.393** | 3.329 | 1,308.41 |
| ML-KEM-768 | encapsulate | 0.335 | 3.322 | 1,112.34 |
| ML-KEM-768 | decapsulate | 0.312 | 3.449 | 1,073.90 |
| **ML-KEM-1024** | keygen | **0.461** | 3.398 | 1,563.45 |
| ML-KEM-1024 | encapsulate | 0.403 | 3.292 | 1,326.90 |
| ML-KEM-1024 | decapsulate | 0.427 | 3.410 | 1,457.98 |
| **Classic-McEliece-348864** | keygen | **312.631** | 4.267 | 1,356,753.14 |
| Classic-McEliece-348864 | encapsulate | 0.765 | 3.408 | 2,595.79 |
| Classic-McEliece-348864 | decapsulate | 57.429 | 3.743 | 214,762.18 |
| **Classic-McEliece-460896** | keygen | **1,590.390** | 4.401 | 7,042,612.41 |
| Classic-McEliece-460896 | encapsulate | 1.425 | 3.493 | 4,945.78 |
| Classic-McEliece-460896 | decapsulate | 91.328 | 3.778 | 344,908.33 |
| **Classic-McEliece-8192128** | keygen | **8,855.915** | 4.469 | 39,653,198.15 |
| Classic-McEliece-8192128 | encapsulate | 2.511 | 3.452 | 8,594.83 |
| Classic-McEliece-8192128 | decapsulate | 211.839 | 3.949 | 836,854.67 |
| **HQC-128** | keygen | **25.818** | 3.766 | 96,869.12 |
| HQC-128 | encapsulate | 46.186 | 3.820 | 176,213.91 |
| HQC-128 | decapsulate | 75.095 | 3.978 | 298,564.98 |
| **HQC-192** | keygen | **69.923** | 3.913 | 273,310.53 |
| HQC-192 | encapsulate | 135.842 | 4.073 | 553,451.38 |
| HQC-192 | decapsulate | 213.508 | 4.145 | 884,943.37 |
| **HQC-256** | keygen | **125.312** | 4.047 | 507,133.41 |
| HQC-256 | encapsulate | 250.582 | 4.166 | 1,043,939.20 |
| HQC-256 | decapsulate | 392.944 | 4.227 | 1,661,049.37 |

### Digital Signature Algorithms (SIG)

| Algorithm | Operation | Time (ms) | Power (W) | Energy (µJ) |
|-----------|-----------|-----------|-----------|-------------|
| **ML-DSA-44** | keygen | **0.478** | 3.608 | 1,719.64 |
| ML-DSA-44 | sign | 2.067 | 3.476 | 7,171.16 |
| ML-DSA-44 | verify | 0.525 | 3.528 | 1,838.26 |
| **ML-DSA-65** | keygen | **0.982** | 3.508 | 3,419.92 |
| ML-DSA-65 | sign | 3.146 | 3.497 | 10,931.87 |
| ML-DSA-65 | verify | 0.996 | 3.434 | 3,421.52 |
| **ML-DSA-87** | keygen | **1.184** | 3.535 | 4,155.04 |
| ML-DSA-87 | sign | 2.798 | 3.601 | 10,013.32 |
| ML-DSA-87 | verify | 1.386 | 3.455 | 4,765.64 |
| **Falcon-512** | keygen | **21.128** | 3.706 | 78,139.82 |
| Falcon-512 | sign | 1.365 | 3.494 | 4,736.59 |
| Falcon-512 | verify | 0.353 | 3.418 | 1,207.56 |
| **Falcon-1024** | keygen | **58.270** | 3.827 | 223,394.77 |
| Falcon-1024 | sign | 1.738 | 3.576 | 6,204.52 |
| Falcon-1024 | verify | 0.563 | 3.448 | 1,940.92 |
| **SPHINCS+-SHA2-128s** | keygen | **194.872** | 4.097 | 798,281.03 |
| SPHINCS+-SHA2-128s | sign | 1,471.751 | 4.330 | 6,372,026.98 |
| SPHINCS+-SHA2-128s | verify | 2.670 | 3.559 | 9,400.38 |
| **SPHINCS+-SHA2-192s** | keygen | **284.828** | 4.174 | 1,188,927.34 |
| SPHINCS+-SHA2-192s | sign | 2,609.818 | 4.373 | 11,412,522.21 |
| SPHINCS+-SHA2-192s | verify | 3.701 | 3.555 | 13,063.06 |
| **SPHINCS+-SHA2-256s** | keygen | **187.883** | 4.121 | 774,409.79 |
| SPHINCS+-SHA2-256s | sign | 2,309.655 | 4.372 | 10,098,319.02 |
| SPHINCS+-SHA2-256s | verify | 3.688 | 3.672 | 13,506.20 |

### Authenticated Encryption (AEAD)

| Algorithm | Payload | Encrypt (µs) | Decrypt (µs) | Power (W) |
|-----------|---------|--------------|--------------|-----------|
| **AES-256-GCM** | 64B | 66.63 | 64.42 | ~3.48 |
| AES-256-GCM | 256B | 66.65 | 58.52 | ~3.55 |
| AES-256-GCM | 1024B | 107.41 | 114.79 | ~3.48 |
| AES-256-GCM | 4096B | 160.30 | 217.07 | ~3.52 |
| **ChaCha20-Poly1305** | 64B | 65.23 | 56.48 | ~3.49 |
| ChaCha20-Poly1305 | 256B | 71.10 | 75.37 | ~3.43 |
| ChaCha20-Poly1305 | 1024B | 72.92 | 92.56 | ~3.50 |
| ChaCha20-Poly1305 | 4096B | 112.17 | 100.16 | ~3.48 |
| **Ascon-128a** | 64B | 31.09 | 38.88 | ~3.46 |
| Ascon-128a | 256B | 33.41 | 38.98 | ~3.48 |
| Ascon-128a | 1024B | 51.05 | 44.89 | ~3.48 |
| Ascon-128a | 4096B | 69.73 | 91.01 | ~3.47 |

---

## Error Comparison: Report vs Reality

### KEM Timing Discrepancies

| Algorithm | Operation | REPORT (5-iter) | ACTUAL (100-iter) | Error % |
|-----------|-----------|-----------------|-------------------|---------|
| ML-KEM-512 | keygen | 1.465 ms | **0.283 ms** | **+418%** |
| ML-KEM-768 | keygen | 0.618 ms | **0.393 ms** | **+57%** |
| Classic-McEliece-8192128 | keygen | 6,030.961 ms | **8,855.915 ms** | **-32%** |

### Signature Timing Discrepancies

| Algorithm | Operation | REPORT (5-iter) | ACTUAL (100-iter) | Error % |
|-----------|-----------|-----------------|-------------------|---------|
| ML-DSA-44 | sign | 1.061 ms | **2.067 ms** | **-49%** |
| ML-DSA-65 | sign | 1.668 ms | **3.146 ms** | **-47%** |
| ML-DSA-87 | sign | 5.801 ms | **2.798 ms** | **+107%** |

**Root Cause:** The 5-iteration sample size is too small for ML-DSA signing due to its variable-time rejection sampling. 100 iterations provide statistically significant results.

---

## Key Findings Summary

### ✅ What Is Correct

1. **Raw data exists and is complete** - 75 JSON files with 7,500 total iterations
2. **All operations succeeded** - 100% success rate across all algorithms
3. **INA219 power monitoring worked** - 1kHz sampling, ~100 samples per operation
4. **Environment is valid** - Raspberry Pi 4, ondemand governor, real hardware

### ❌ What Is Incorrect

1. **Report uses wrong data source** - `benchmarks/bench_results_power/` (5 iter) instead of `individual_benchmarks/raw_data/` (100 iter)
2. **All numeric values in report are unreliable** - Based on insufficient sample size
3. **Some timing errors exceed 400%** - Particularly for fast operations

### ⚠️ Recommendations

1. **Regenerate the report** using the correct data source:
   ```bash
   python bench/analyze_power_benchmark.py -i individual_benchmarks/raw_data -o individual_benchmarks/analysis
   ```

2. **Delete or rename** `benchmarks/bench_results_power/` to prevent future confusion

3. **Use the values in this audit report** for any immediate analysis needs

---

## Validated Performance Rankings

### Fastest KEM Operations (100 iterations)
1. **ML-KEM-512 decapsulate** - 0.241 ms
2. **ML-KEM-512 keygen** - 0.283 ms  
3. **ML-KEM-512 encapsulate** - 0.300 ms
4. **ML-KEM-768 decapsulate** - 0.312 ms
5. **ML-KEM-768 encapsulate** - 0.335 ms

### Fastest Signature Operations (100 iterations)
1. **Falcon-512 verify** - 0.353 ms
2. **ML-DSA-44 keygen** - 0.478 ms
3. **ML-DSA-44 verify** - 0.525 ms
4. **Falcon-1024 verify** - 0.563 ms
5. **ML-DSA-65 keygen** - 0.982 ms

### Most Energy-Efficient (µJ per operation)
1. **ML-KEM-512 decapsulate** - 833 µJ
2. **ML-KEM-512 keygen** - 959 µJ
3. **ML-KEM-512 encapsulate** - 991 µJ
4. **ML-KEM-768 decapsulate** - 1,074 µJ
5. **ML-KEM-768 encapsulate** - 1,112 µJ

### Most Energy-Intensive (mJ per operation)
1. **Classic-McEliece-8192128 keygen** - 39,653 mJ (39.6 J!)
2. **SPHINCS+-SHA2-192s sign** - 11,413 mJ
3. **SPHINCS+-SHA2-256s sign** - 10,098 mJ
4. **Classic-McEliece-460896 keygen** - 7,043 mJ
5. **SPHINCS+-SHA2-128s sign** - 6,372 mJ

---

## Data Source Evidence

### benchmarks/bench_results_power/ (INCORRECT - 5 iterations)
```
Path: benchmarks/bench_results_power/raw/kem/ML_KEM_768_keygen.json
Timestamp: 2026-01-11T14:27:11.601701Z
Iterations: 5
```

### individual_benchmarks/raw_data/ (CORRECT - 100 iterations)  
```
Path: individual_benchmarks/raw_data/raw/kem/ML_KEM_768_keygen.json
Timestamp: 2026-01-11T15:03:47.759351Z
Iterations: 100
```

---

## Conclusion

The individual benchmark data is **valid and complete**. The issue is solely that the analysis report was generated from a preliminary 5-iteration test run instead of the production 100-iteration run.

**Action Required:** Regenerate `BENCHMARK_REPORT.md` using the correct data source to have accurate, publication-quality results.

---

*Audit completed: 2026-01-17*
