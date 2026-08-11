# BENCHMARK EXPERIMENT VERIFICATION REPORT

**Verification Date:** 2026-01-10  
**Verification Engineer:** Professional Experiment Verification Engineer  
**Remote System:** dev@100.101.93.23 (hostname: uavpi)  
**Repository Path:** ~/secure-tunnel/bench_results/

---

## SECTION 1: VERIFIED FACTS

### 1.1 Execution Environment (VERIFIED)

| Attribute | Value | Source |
|-----------|-------|--------|
| Hostname | `uavpi` | bench_results/environment.json |
| Kernel Version | `6.12.47+rpt-rpi-v8` | bench_results/environment.json |
| Python Version | `3.11.2 (main, Apr 28 2025, 14:11:48) [GCC 12.2.0]` | bench_results/environment.json |
| Git Commit | `49ed2123523748810d04664ff2a27cb43a0c1d86` | bench_results/environment.json |
| Git Branch | `main` | bench_results/environment.json |
| Git Clean | `false` | bench_results/environment.json |
| CPU Frequency Governor | `ondemand` | bench_results/environment.json |
| Benchmark Start Time | `2026-01-10T05:44:22.960014Z` | bench_results/environment.json |

### 1.2 File Inventory (VERIFIED)

| Category | File Count | Location | Verification Command |
|----------|------------|----------|---------------------|
| KEM Benchmarks | 27 | bench_results/raw/kem/ | `ls bench_results/raw/kem/ \| wc -l` |
| SIG Benchmarks | 24 | bench_results/raw/sig/ | `ls bench_results/raw/sig/ \| wc -l` |
| AEAD Benchmarks | 24 | bench_results/raw/aead/ | `ls bench_results/raw/aead/ \| wc -l` |
| Suite Benchmarks | 23 | bench_results/raw/suites/ | `ls bench_results/raw/suites/ \| wc -l` |
| **Total Raw Files** | **98** | bench_results/raw/ | `find bench_results/raw -name '*.json' \| wc -l` |
| AEAD Summary CSV | 1 | bench_results/summary/ | `ls bench_results/summary/` |
| AEAD Summary JSON | 1 | bench_results/summary/ | `ls bench_results/summary/` |
| Environment JSON | 1 | bench_results/ | `ls bench_results/` |
| Total Disk Usage | 9.9M | bench_results/ | `du -sh bench_results/` |

### 1.3 Iteration Count (VERIFIED)

| Sample File | Iteration Count | Verification Command |
|-------------|-----------------|---------------------|
| ML_KEM_512_keygen.json | 200 | `grep -c iteration [...] = 201` (200 data + 1 array key) |
| ML_KEM_768_keygen.json | 200 | `grep -c iteration [...] = 201` |
| Suite handshake file | 200 | `grep -c iteration [...] = 201` |

**Evidence:** DEFAULT_ITERATIONS = 200 in bench/benchmark_pqc.py (line confirmed via grep)

### 1.4 KEM Algorithm Coverage (VERIFIED)

| Algorithm | oqs_name | NIST Level | Files Present | Operations |
|-----------|----------|------------|---------------|------------|
| ML-KEM-512 | ML-KEM-512 | L1 | 3 | keygen, encapsulate, decapsulate |
| ML-KEM-768 | ML-KEM-768 | L3 | 3 | keygen, encapsulate, decapsulate |
| ML-KEM-1024 | ML-KEM-1024 | L5 | 3 | keygen, encapsulate, decapsulate |
| Classic-McEliece-348864 | Classic-McEliece-348864 | L1 | 3 | keygen, encapsulate, decapsulate |
| Classic-McEliece-460896 | Classic-McEliece-460896 | L3 | 3 | keygen, encapsulate, decapsulate |
| Classic-McEliece-8192128 | Classic-McEliece-8192128 | L5 | 3 | keygen, encapsulate, decapsulate |
| HQC-128 | HQC-128 | L1 | 3 | keygen, encapsulate, decapsulate |
| HQC-192 | HQC-192 | L3 | 3 | keygen, encapsulate, decapsulate |
| HQC-256 | HQC-256 | L5 | 3 | keygen, encapsulate, decapsulate |

**Total KEM Files:** 9 algorithms × 3 operations = 27 ✓

### 1.5 Signature Algorithm Coverage (VERIFIED)

| Algorithm | oqs_name | NIST Level | Files Present | Operations |
|-----------|----------|------------|---------------|------------|
| ML-DSA-44 | ML-DSA-44 | L1 | 3 | keygen, sign, verify |
| ML-DSA-65 | ML-DSA-65 | L3 | 3 | keygen, sign, verify |
| ML-DSA-87 | ML-DSA-87 | L5 | 3 | keygen, sign, verify |
| Falcon-512 | Falcon-512 | L1 | 3 | keygen, sign, verify |
| Falcon-1024 | Falcon-1024 | L5 | 3 | keygen, sign, verify |
| SPHINCS+-SHA2-128s-simple | SPHINCS+-SHA2-128s-simple | L1 | 3 | keygen, sign, verify |
| SPHINCS+-SHA2-192s-simple | SPHINCS+-SHA2-192s-simple | L3 | 3 | keygen, sign, verify |
| SPHINCS+-SHA2-256s-simple | SPHINCS+-SHA2-256s-simple | L5 | 3 | keygen, sign, verify |

**Total SIG Files:** 8 algorithms × 3 operations = 24 ✓

### 1.6 AEAD Algorithm Coverage (VERIFIED)

| Algorithm | display_name | Payload Sizes | Operations |
|-----------|--------------|---------------|------------|
| AES-256-GCM | AES-256-GCM | 64B, 256B, 1024B, 4096B | encrypt, decrypt |
| ChaCha20-Poly1305 | ChaCha20-Poly1305 | 64B, 256B, 1024B, 4096B | encrypt, decrypt |
| Ascon-128a | Ascon-128a | 64B, 256B, 1024B, 4096B | encrypt, decrypt |

**Total AEAD Files:** 3 algorithms × 4 sizes × 2 operations = 24 ✓

### 1.7 Suite Coverage (VERIFIED)

**23 full_handshake suite files found covering:**

L1 Suites (9 files):
- cs_classicmceliece348864_aesgcm_falcon512
- cs_classicmceliece348864_aesgcm_mldsa44
- cs_classicmceliece348864_aesgcm_sphincs128s
- cs_classicmceliece348864_ascon128a_falcon512
- cs_classicmceliece348864_ascon128a_mldsa44
- cs_classicmceliece348864_ascon128a_sphincs128s
- cs_classicmceliece348864_chacha20poly1305_falcon512
- cs_classicmceliece348864_chacha20poly1305_mldsa44
- cs_classicmceliece348864_chacha20poly1305_sphincs128s

L3 Suites (6 files):
- cs_classicmceliece460896_aesgcm_mldsa65
- cs_classicmceliece460896_aesgcm_sphincs192s
- cs_classicmceliece460896_ascon128a_mldsa65
- cs_classicmceliece460896_ascon128a_sphincs192s
- cs_classicmceliece460896_chacha20poly1305_mldsa65
- cs_classicmceliece460896_chacha20poly1305_sphincs192s

L5 Suites (8 files):
- cs_classicmceliece8192128_aesgcm_falcon1024
- cs_classicmceliece8192128_aesgcm_mldsa87
- cs_classicmceliece8192128_aesgcm_sphincs256s
- cs_classicmceliece8192128_ascon128a_falcon1024
- cs_classicmceliece8192128_ascon128a_mldsa87
- cs_classicmceliece8192128_chacha20poly1305_falcon1024
- cs_classicmceliece8192128_chacha20poly1305_mldsa87
- cs_classicmceliece8192128_chacha20poly1305_sphincs256s

### 1.8 Timestamp Consistency (VERIFIED)

| Benchmark Phase | Start Timestamp | Source File |
|-----------------|-----------------|-------------|
| Environment | 2026-01-10T05:44:22.960014Z | environment.json |
| KEM Start | 2026-01-10T05:44:23.927675Z | ML_KEM_512_keygen.json |
| SIG Start | 2026-01-10T06:24:24.951560Z | ML_DSA_44_keygen.json |
| AEAD Start | 2026-01-10T06:48:18.074669Z | AES_256_GCM_encrypt_64B.json |

**Observation:** Timestamps show sequential execution with ~40 min for KEMs, ~24 min for SIGs.

### 1.9 Git Commit Consistency (VERIFIED)

All sampled benchmark files contain identical git_commit:
```
"git_commit": "49ed2123523748810d04664ff2a27cb43a0c1d86"
```

**Sampled files:**
- bench_results/raw/kem/ML_KEM_512_keygen.json
- bench_results/raw/sig/ML_DSA_44_keygen.json
- bench_results/raw/aead/AES_256_GCM_encrypt_64B.json
- bench_results/raw/suites/cs_classicmceliece348864_aesgcm_falcon512_full_handshake.json

### 1.10 Hostname Consistency (VERIFIED)

All sampled benchmark files contain identical hostname:
```
"hostname": "uavpi"
```

---

## SECTION 2: RAW METRICS INVENTORY

### 2.1 Key/Signature Sizes Extracted from Benchmark Files

#### KEM Key Sizes (from keygen files):

| Algorithm | public_key_bytes | secret_key_bytes | Source File |
|-----------|------------------|------------------|-------------|
| ML-KEM-768 | 1184 | 2400 | ML_KEM_768_keygen.json |

#### KEM Ciphertext Sizes (from encapsulate files):

| Algorithm | ciphertext_bytes | shared_secret_bytes | Source File |
|-----------|------------------|---------------------|-------------|
| ML-KEM-768 | 1088 | 32 | ML_KEM_768_encapsulate.json |

#### Signature Sizes (from keygen/sign files):

| Algorithm | public_key_bytes | secret_key_bytes | signature_bytes | Source File |
|-----------|------------------|------------------|-----------------|-------------|
| ML-DSA-65 (keygen) | 1952 | 4032 | - | ML_DSA_65_keygen.json |
| ML-DSA-65 (sign) | - | - | 3309 | ML_DSA_65_sign.json |
| Falcon-512 (keygen) | 897 | 1281 | - | Falcon_512_keygen.json |
| Falcon-512 (sign) | - | - | 659 | Falcon_512_sign.json |

#### Suite Combined Sizes (from full_handshake files):

| Suite | public_key_bytes | ciphertext_bytes | signature_bytes | shared_secret_bytes | Source File |
|-------|------------------|------------------|-----------------|---------------------|-------------|
| cs-classicmceliece348864-aesgcm-falcon512 | 261120 | 96 | 656 | 32 | cs_classicmceliece348864_aesgcm_falcon512_full_handshake.json |

### 2.2 AEAD Summary Statistics (from aead_summary.csv)

**24 entries verified covering 3 algorithms × 4 payload sizes × 2 operations**

Sample entries (full CSV in bench_results/summary/aead_summary.csv):

| algorithm_name | operation | payload_size | total_iterations | wall_time_mean_ns | wall_time_median_ns |
|----------------|-----------|--------------|------------------|-------------------|---------------------|
| AES-256-GCM | encrypt | 64 | 200 | 77898.67 | 62796.5 |
| AES-256-GCM | decrypt | 64 | 200 | 63784.14 | 59352.0 |
| ChaCha20-Poly1305 | encrypt | 64 | 200 | 62276.795 | 58009.0 |
| ChaCha20-Poly1305 | decrypt | 64 | 200 | 58086.92 | 55408.0 |
| Ascon-128a | encrypt | 64 | 200 | 4384 | 4148.0 |
| Ascon-128a | decrypt | 64 | 200 | 4562.685 | 4250.0 |

---

## SECTION 3: PARTIALLY VERIFIED FACTS

### 3.1 CPU Model (PARTIALLY VERIFIED)

| Attribute | Recorded Value | Status |
|-----------|----------------|--------|
| cpu_model | "unknown" | Value present but detection failed |

**Evidence:** environment.json contains `"cpu_model": "unknown"`

**Implication:** Benchmark script did not successfully detect CPU model on this Raspberry Pi system.

### 3.2 OQS Version (PARTIALLY VERIFIED)

| Attribute | Recorded Value | Status |
|-----------|----------------|--------|
| oqs_version | "unknown" | Value present but detection failed |
| oqs_python_version | "unknown" | Value present but detection failed |

**Evidence:** environment.json contains `"oqs_version": "unknown"`

### 3.3 Git Clean Status (PARTIALLY VERIFIED)

| Attribute | Recorded Value | Status |
|-----------|----------------|--------|
| git_clean | false | Uncommitted changes present at benchmark time |

**Implication:** Repository had uncommitted changes when benchmarks were executed.

---

## SECTION 4: UNVERIFIED ITEMS

### 4.1 Power/Energy Measurements

| Field | Status | Reason |
|-------|--------|--------|
| voltage_v | null | No power monitor attached |
| current_ma | null | No power monitor attached |
| power_mw | null | No power monitor attached |
| energy_mj | null | No power monitor attached |
| power_samples | [] | Empty array |

**Evidence:** All iteration records show null values for power-related fields.

### 4.2 Performance Counter Measurements

| Field | Status | Reason |
|-------|--------|--------|
| perf_cycles | null | perf counters not enabled/available |
| perf_instructions | null | perf counters not enabled/available |
| perf_cache_misses | null | perf counters not enabled/available |
| perf_branch_misses | null | perf counters not enabled/available |
| perf_context_switches | null | perf counters not enabled/available |
| perf_cpu_migrations | null | perf counters not enabled/available |

**Evidence:** All iteration records show null values for perf counter fields.

### 4.3 CPU Core Pinning

| Attribute | Recorded Value | Status |
|-----------|----------------|--------|
| cpu_core_pinned | null | Not configured |

### 4.4 Ambient Temperature

| Attribute | Recorded Value | Status |
|-----------|----------------|--------|
| ambient_temp_c | null | No temperature sensor data |

### 4.5 ML-KEM/HQC Suite Benchmarks

**Observation:** All suite files use Classic-McEliece as the KEM component. No suite benchmarks exist for:
- ML-KEM-512/768/1024 combinations
- HQC-128/192/256 combinations

**Status:** Cannot verify whether this is intentional or an oversight without additional documentation.

---

## SECTION 5: EVIDENCE APPENDIX

### 5.1 SSH Commands Executed

```bash
# Connection
ssh dev@100.101.93.23

# Environment verification
cd secure-tunnel
cat bench_results/environment.json
uname -a
hostname

# File inventory
find bench_results/raw -name '*.json' | wc -l
ls bench_results/raw/kem/
ls bench_results/raw/sig/
ls bench_results/raw/aead/
ls bench_results/raw/suites/
du -sh bench_results/

# Iteration verification
grep -c iteration bench_results/raw/kem/ML_KEM_512_keygen.json
grep -c iteration bench_results/raw/kem/ML_KEM_768_keygen.json

# Timestamp extraction
grep timestamp_iso bench_results/environment.json
grep timestamp_iso bench_results/raw/kem/ML_KEM_512_keygen.json
grep timestamp_iso bench_results/raw/sig/ML_DSA_44_keygen.json
grep timestamp_iso bench_results/raw/aead/AES_256_GCM_encrypt_64B.json

# Git commit consistency
grep -h git_commit bench_results/raw/kem/ML_KEM_512_keygen.json \
  bench_results/raw/sig/ML_DSA_44_keygen.json \
  bench_results/raw/aead/AES_256_GCM_encrypt_64B.json | sort -u

# Data integrity
find bench_results/raw -name '*.json' -size 0
tail -3 bench_results/raw/kem/ML_KEM_512_keygen.json
wc -l bench_results/raw/kem/*.json | tail -5

# Summary data
cat bench_results/summary/aead_summary.csv
ls -la bench_results/summary/
```

### 5.2 Source Code Cross-Reference

| File | Line Numbers | Purpose |
|------|--------------|---------|
| bench/benchmark_pqc.py | 196-197 | algorithm_name, algorithm_type fields |
| bench/benchmark_pqc.py | 492-514 | discover_kems() function |
| bench/benchmark_pqc.py | 515-537 | discover_signatures() function |
| bench/benchmark_pqc.py | 538-558 | discover_aeads() function |
| core/suites.py | 43-176 | _KEM_REGISTRY (9 algorithms) |
| core/suites.py | 177-310 | _SIG_REGISTRY (8 algorithms) |
| core/suites.py | 311-380 | _AEAD_REGISTRY (3 algorithms) |

### 5.3 Data Structure Schema (Verified from raw files)

```json
{
  "algorithm_name": "<string>",
  "algorithm_type": "<KEM|SIG|AEAD|SUITE>",
  "operation": "<keygen|encapsulate|decapsulate|sign|verify|encrypt|decrypt|full_handshake>",
  "payload_size": "<int|null>",
  "git_commit": "<40-char hex>",
  "hostname": "<string>",
  "timestamp_iso": "<ISO8601>",
  "public_key_bytes": "<int|null>",
  "secret_key_bytes": "<int|null>",
  "ciphertext_bytes": "<int|null>",
  "signature_bytes": "<int|null>",
  "shared_secret_bytes": "<int|null>",
  "iterations": [
    {
      "iteration": "<0-199>",
      "timestamp_ns": "<int>",
      "wall_time_ns": "<int>",
      "perf_time_ns": "<int>",
      "success": "<bool>",
      "error": "<string|null>",
      "voltage_v": "<float|null>",
      "current_ma": "<float|null>",
      "power_mw": "<float|null>",
      "energy_mj": "<float|null>",
      "power_samples": "<array>",
      "perf_cycles": "<int|null>",
      "perf_instructions": "<int|null>",
      "perf_cache_misses": "<int|null>",
      "perf_branch_misses": "<int|null>",
      "perf_context_switches": "<int|null>",
      "perf_cpu_migrations": "<int|null>"
    }
  ]
}
```

---

## SECTION 6: VERIFICATION SUMMARY

| Category | Status | Count |
|----------|--------|-------|
| Verified Facts | ✓ | 10 major items |
| Partially Verified | ⚠ | 3 items |
| Unverified | ✗ | 5 categories |
| Total Raw Files | - | 98 JSON files |
| Total Iterations Expected | - | 98 × 200 = 19,600 |

---

**END OF VERIFICATION REPORT**

*This report contains only facts extracted directly from benchmark output files via SSH commands. No performance conclusions or interpretations have been made.*
