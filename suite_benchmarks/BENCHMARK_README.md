# PQC Suite Benchmark Framework

## Overview

This framework provides comprehensive benchmarking of Post-Quantum Cryptographic (PQC) suites for the secure drone-GCS communication tunnel. It cycles through all registered suites, collecting detailed performance metrics suitable for academic research and technical documentation.

## Quick Start

### Step 1: Start GCS (Windows)

```powershell
cd c:\Users\burak\ptojects\secure-tunnel
conda activate oqs-dev
python -m sscheduler.sgcs
```

### Step 2: Start Benchmark (Raspberry Pi)

```bash
cd ~/secure-tunnel
source ~/cenv/bin/activate

# Benchmark all 24 AESGCM suites (~4 minutes)
python -m sscheduler.sdrone_bench --interval 10 --filter-aead aesgcm

# Or benchmark ALL 72 suites (~12 minutes)
python -m sscheduler.sdrone_bench --interval 10
```

### Step 3: Analyze Results

```bash
python suite_benchmarks/analyze_benchmarks.py
```

## Suite Coverage

| NIST Level | Suites | KEMs | Signatures |
|------------|--------|------|------------|
| L1 | 27 | ML-KEM-512, Classic-McEliece-348864, HQC-128 | ML-DSA-44, Falcon-512, SPHINCS+-128s |
| L3 | 18 | ML-KEM-768, Classic-McEliece-460896, HQC-192 | ML-DSA-65, SPHINCS+-192s |
| L5 | 27 | ML-KEM-1024, Classic-McEliece-8192128, HQC-256 | ML-DSA-87, Falcon-1024, SPHINCS+-256s |

## Metrics Collected

For each suite, the benchmark collects:

### Timing Metrics
- **Handshake Time**: Total end-to-end handshake duration
- **KEM Key Generation**: Time to generate ephemeral key pair
- **KEM Encapsulation**: Time to encapsulate shared secret
- **KEM Decapsulation**: Time to decapsulate shared secret
- **Signature Generation**: Time to sign handshake transcript
- **Signature Verification**: Time to verify peer signature

### Size Metrics
- **Public Key Size**: Bytes for KEM public key
- **Ciphertext Size**: Bytes for KEM ciphertext
- **Signature Size**: Bytes for digital signature

### Energy Metrics (if INA219 available)
- **Power**: Average power consumption during handshake
- **Energy**: Total energy consumed per handshake

## Output Files

After running the benchmark, results are saved to `logs/benchmarks/`:

- `benchmark_<timestamp>.jsonl` - Raw results (JSONL format)
- `benchmark_summary_<timestamp>.json` - Summary statistics

After running analysis, outputs are in `suite_benchmarks/analysis_output/`:

- `handshake_by_nist_level.png/pdf` - Bar chart by security level
- `kem_comparison.png/pdf` - KEM family performance
- `signature_comparison.png/pdf` - Signature scheme performance  
- `artifact_sizes.png/pdf` - Communication cost comparison
- `heatmap_kem_sig.png/pdf` - KEM × Signature matrix
- `scatter_time_vs_size.png/pdf` - Time vs. communication cost
- `results_table.tex` - LaTeX table for papers
- `analysis_report.txt` - Comprehensive text report

## Configuration

Edit `settings.json` to customize benchmark behavior:

```json
{
    "benchmark_mode": {
        "enabled": true,
        "cycle_interval_s": 10.0,
        "sequential_cycling": true,
        "collect_metrics": true
    },
    "rekey": {
        "min_stable_s": 10.0,
        "max_per_window": 500,
        "window_s": 7200
    }
}
```

## Command-Line Options

### sdrone_bench.py

```
--interval SECS     Seconds per suite (default: 10)
--filter-aead AEAD  Only benchmark: aesgcm, chacha, or ascon
--max-suites N      Limit number of suites
--dry-run           Show plan without executing
--mav-master DEV    MAVLink device (default: /dev/ttyACM0)
```

### analyze_benchmarks.py

```
python suite_benchmarks/analyze_benchmarks.py [input_file.json]
```

If no input file specified, automatically finds latest results.

## Example Results

```
OVERALL STATISTICS
----------------------------------------
Total suites analyzed: 24
Handshake Time (ms):
  Min: 45.23
  Max: 1523.67
  Mean: 312.45
  Median: 198.32

BY NIST SECURITY LEVEL
----------------------------------------
Level L1: 9 suites
  Mean handshake: 156.78 ms
Level L3: 6 suites
  Mean handshake: 298.45 ms
Level L5: 9 suites
  Mean handshake: 498.23 ms

TOP PERFORMERS (Fastest Handshake)
----------------------------------------
 1. cs-mlkem512-aesgcm-mldsa44: 45.23 ms (L1)
 2. cs-mlkem768-aesgcm-mldsa65: 67.89 ms (L3)
 3. cs-mlkem1024-aesgcm-mldsa87: 89.12 ms (L5)
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     Benchmark Framework                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐       ┌──────────────────┐                │
│  │  sdrone_bench.py │       │     sgcs.py      │                │
│  │  (Drone/RPi)     │◄─────►│    (GCS/Win)     │                │
│  │                  │  TCP  │                  │                │
│  │  BenchmarkPolicy │ ctrl  │  ControlServer   │                │
│  │  DroneProxy      │       │  GcsProxy        │                │
│  │  MetricsCollect  │       │  MetricsCollect  │                │
│  └──────────────────┘       └──────────────────┘                │
│           │                          │                           │
│           ▼                          ▼                           │
│  ┌──────────────────┐       ┌──────────────────┐                │
│  │  logs/benchmarks │       │  logs/gcs_telem  │                │
│  │  benchmark_*.json│       │  gcs_telemetry.* │                │
│  └──────────────────┘       └──────────────────┘                │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────────────────────────────┐                   │
│  │         analyze_benchmarks.py            │                   │
│  │  ┌────────────┐  ┌────────────┐          │                   │
│  │  │ matplotlib │  │  pandas    │          │                   │
│  │  │ charts     │  │ analysis   │          │                   │
│  │  └────────────┘  └────────────┘          │                   │
│  └──────────────────────────────────────────┘                   │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────────────────────────────┐                   │
│  │     suite_benchmarks/analysis_output/    │                   │
│  │  • PNG/PDF charts                        │                   │
│  │  • LaTeX tables                          │                   │
│  │  • Text reports                          │                   │
│  └──────────────────────────────────────────┘                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Requirements

### GCS (Windows)
- Python 3.11+
- oqs-python (liboqs)
- MAVProxy

### Drone (Raspberry Pi)
- Python 3.11+
- oqs-python (liboqs)
- MAVProxy
- smbus2 (for INA219 power monitoring)

### Analysis
- matplotlib
- numpy
- pandas (optional)

## Troubleshooting

### "GCS not available"
Ensure sgcs.py is running on the Windows GCS and network connectivity is working:
```bash
ping 100.101.93.23  # GCS IP
```

### "Missing key" errors
Regenerate keys for the suite:
```bash
python scripts/regenerate_matrix_keys.py --suite <suite_id>
```

### MAVProxy connection issues
Check serial device permissions:
```bash
sudo chmod 666 /dev/ttyACM0
```

## Citation

If you use this benchmark framework in research, please cite:

```bibtex
@software{pqc_drone_benchmark,
  title = {PQC Suite Benchmark Framework for Drone-GCS Communication},
  year = {2024},
  url = {https://github.com/example/secure-tunnel}
}
```
