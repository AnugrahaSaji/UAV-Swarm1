# PQC Performance & Power Benchmarking

**THIS IS A MEASUREMENT-ONLY SYSTEM.**

No analysis. No conclusions. No optimization recommendations.

## Overview

This benchmarking system measures raw performance and power consumption of post-quantum cryptographic primitives and full cryptographic suites used in the secure-tunnel system.

## What Is Measured

### A. KEMs (Key Encapsulation Mechanisms)
- **keygen**: Keypair generation time
- **encapsulate**: Encapsulation time
- **decapsulate**: Decapsulation time

Measured algorithms (when available):
- ML-KEM-512, ML-KEM-768, ML-KEM-1024
- Classic-McEliece-348864, -460896, -8192128
- HQC-128, HQC-192, HQC-256

### B. Signatures
- **keygen**: Keypair generation time
- **sign**: Signature generation time
- **verify**: Signature verification time

Measured algorithms (when available):
- ML-DSA-44, ML-DSA-65, ML-DSA-87
- Falcon-512, Falcon-1024
- SPHINCS+-SHA2-128s, -192s, -256s

### C. AEADs (Authenticated Encryption)
- **encrypt**: Encryption time
- **decrypt**: Decryption time

Payload sizes: 64B, 256B, 1024B, 4096B

Measured algorithms:
- AES-256-GCM
- ChaCha20-Poly1305
- Ascon-128a

### D. Full Suites
- **full_handshake**: Complete handshake time (keygen + sign + verify + encap + decap + KDF)

## Iteration Requirements

- **200 iterations** per measurement
- Each iteration is independently timed
- **NO warm-up iterations are discarded**
- **NO outliers are removed**
- Failures are recorded, not retried

## Measured Metrics

### Timing
- `wall_time_ns`: Wall-clock time (nanoseconds)
- `perf_time_ns`: High-resolution performance counter (nanoseconds)
- `timestamp_ns`: Absolute timestamp of measurement start

### Power (via INA219)
- `voltage_v`: Voltage (Volts)
- `current_ma`: Current (milliamps)
- `power_mw`: Power (milliwatts)
- `energy_mj`: Energy per operation (millijoules)
- `power_samples`: Array of samples taken during operation

### Artifact Sizes
- `public_key_bytes`: Public key size
- `secret_key_bytes`: Secret key size
- `ciphertext_bytes`: Ciphertext/encapsulation size
- `signature_bytes`: Signature size
- `shared_secret_bytes`: Shared secret size

## Output Structure

```
bench_results_YYYYMMDD_HHMMSS/
├── environment.json              # Execution environment metadata
├── raw/
│   ├── kem/
│   │   ├── ML_KEM_512_keygen.json
│   │   ├── ML_KEM_512_encapsulate.json
│   │   ├── ML_KEM_512_decapsulate.json
│   │   └── ...
│   ├── sig/
│   │   ├── ML_DSA_44_keygen.json
│   │   ├── ML_DSA_44_sign.json
│   │   ├── ML_DSA_44_verify.json
│   │   └── ...
│   ├── aead/
│   │   ├── AES_256_GCM_encrypt_64B.json
│   │   ├── AES_256_GCM_decrypt_64B.json
│   │   └── ...
│   └── suites/
│       ├── cs_mlkem512_aesgcm_mldsa44_full_handshake.json
│       └── ...
└── summary/
    ├── kem_summary.json
    ├── kem_summary.csv
    ├── sig_summary.json
    ├── sig_summary.csv
    ├── aead_summary.json
    ├── aead_summary.csv
    ├── suites_summary.json
    └── suites_summary.csv
```

## Usage

### On Raspberry Pi (via SSH)

```bash
# SSH into drone
ssh dev@100.101.93.23

# Navigate to project
cd secure-tunnel

# Pull latest code
git pull origin main
git status  # Ensure clean state

# Run full benchmark
sudo ./bench/run_benchmarks.sh --iterations 200

# Or run manually with more control
sudo bash bench/prepare_bench_env.sh
taskset -c 0 python bench/benchmark_pqc.py --iterations 200 --output-dir my_results
```

### Quick Test Run

```bash
# Quick test with fewer iterations
python bench/benchmark_pqc.py --iterations 10 --output-dir quick_test
```

### Skip Specific Categories

```bash
# Skip slow algorithms
python bench/benchmark_pqc.py --skip-suites --iterations 200
```

## Environment Preparation

Before benchmarking, the `prepare_bench_env.sh` script:

1. Sets CPU governor to "performance"
2. Locks CPU frequency (disables scaling)
3. Checks for conflicting services (MAVProxy, scheduler, proxy)
4. Verifies INA219 power sensor availability
5. Enables perf counters for non-root users
6. Logs git status for traceability

## Data Traceability

Every measurement includes:
- Algorithm name
- Algorithm type (KEM/SIG/AEAD/SUITE)
- Operation name
- Iteration number
- Absolute timestamp
- Git commit hash
- Device hostname

## Failure Handling

If any measurement:
- Crashes
- Times out
- Returns invalid output

The system:
- Records the failure with error message
- Continues benchmarking remaining items
- Does NOT retry silently
- Does NOT discard the data

## Summary Statistics

Summaries are **DERIVED** from raw data and include:
- Mean
- Median
- Min
- Max
- Standard deviation

Summaries are clearly labeled as derived and include reference to raw data.

## CSV Format (Excel Compatible)

Summary CSV files are formatted for direct import into Excel/LibreOffice with columns:
- algorithm_name
- operation
- payload_size (for AEAD)
- total_iterations
- successful_iterations
- failed_iterations
- wall_time_mean_ns, median, min, max, stdev
- perf_time_mean_ns, median, min, max, stdev
- energy_mean_mj, median, min, max, stdev (if available)
- Artifact sizes

## Requirements

### Python Dependencies
- oqs-python (liboqs Python bindings)
- cryptography (for AES-GCM, ChaCha20)
- ina219 (optional, for power measurements)

### System Requirements
- Linux (for perf counters)
- I2C enabled (for INA219)
- Root access (for CPU governor control)

## No Analysis Policy

This benchmarking system:
- **DOES** measure raw data
- **DOES** record all iterations
- **DOES** compute basic statistics

This benchmarking system:
- **DOES NOT** compare algorithms
- **DOES NOT** recommend configurations
- **DOES NOT** draw conclusions
- **DOES NOT** optimize anything

Analysis and conclusions must be performed separately from measurement.
