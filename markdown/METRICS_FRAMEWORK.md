# Comprehensive Metrics Collection Framework

## Overview

This framework implements aggressive JSON logging with **231 metrics across 18 categories** (A-R) for PQC cipher suite benchmarking.

## Files Created

### Core Framework

| File | Purpose |
|------|---------|
| `core/metrics_schema.py` | 18 dataclass schemas for all metric categories (A-R) |
| `core/metrics_collectors.py` | Platform-aware collectors: Environment, System, Power, Network, Latency |
| `core/metrics_aggregator.py` | Aggregates all collectors into ComprehensiveSuiteMetrics |
| `test_collectors.py` | Quick test of all collectors |
| `test_comprehensive_benchmark.py` | Full benchmark runner for all 72 suites |
| `test_metrics_integration.py` | Integration test (requires network between GCS/drone) |

## Metric Categories

| Category | # Fields | Description |
|----------|----------|-------------|
| A. Run & Context | 20 | Run ID, git commit, hostnames, IPs, timestamps |
| B. Suite Crypto Identity | 13 | KEM/Sig/AEAD algorithms, NIST levels |
| C. Suite Lifecycle Timeline | 11 | Selection, activation, traffic, deactivation times |
| D. Handshake Metrics | 8 | Start/end times, duration, success/failure |
| E. Crypto Primitive Breakdown | 17 | Keygen, encaps, decaps, sign, verify timing (ms + ns) |
| F. Rekey Metrics | 7 | Attempts, success, failure, interval |
| G. Data Plane | 24 | Throughput, packets, drops, AEAD timing |
| H. Latency & Jitter | 11 | One-way, RTT, p50/p95/p99 percentiles |
| I. MAVProxy Drone | 17 | TX/RX packets, msg counts, heartbeat |
| J. MAVProxy GCS | 17 | Same as I but GCS side |
| K. MAVLink Integrity | 10 | CRC errors, decode errors, duplicates |
| L. Flight Controller | 14 | FC mode, battery, GPS, attitude |
| M. Control Plane | 11 | Scheduler tick, decision latency |
| N. System Drone | 15 | CPU, memory, temperature, throttling |
| O. System GCS | 8 | CPU, memory for GCS |
| P. Power & Energy | 11 | Voltage, current, power, energy per handshake |
| Q. Observability | 9 | Log counts, trace paths, sampling rate |
| R. Validation | 8 | Expected/collected samples, pass/fail |
| **TOTAL** | **231** | |

## Testing

### Test Collectors Locally

```bash
# On GCS (Windows)
conda activate oqs-dev
python test_collectors.py

# On Drone (Raspberry Pi)
source ~/cenv/bin/activate
python test_collectors.py
```

### Run Full Benchmark (Requires Network)

The benchmark requires both GCS and Drone proxies running on separate machines:

```bash
# On Drone (start first, waits for GCS):
source ~/cenv/bin/activate
python test_comprehensive_benchmark.py --role drone

# On GCS (Windows):
conda activate oqs-dev
python test_comprehensive_benchmark.py --role gcs --filter mlkem768  # Filter optional
```

### Using Existing Scheduler

The existing scheduler (`scheduler/sgcs.py` and `scheduler/sdrone.py`) can be modified to integrate the metrics aggregator.

## Output

Per-suite JSON files are saved to `logs/comprehensive_benchmark/{run_id}/`:

```
logs/comprehensive_benchmark/
└── bench_20260112_120000/
    ├── cs-mlkem512-aesgcm-falcon512_gcs.json
    ├── cs-mlkem512-aesgcm-falcon512_drone.json
    ├── benchmark_results_gcs.json
    └── benchmark_results_drone.json
```

## API Usage

```python
from core.metrics_aggregator import MetricsAggregator
from core.suites import get_suite

# Create aggregator
agg = MetricsAggregator(role="gcs")  # or "drone"
agg.set_run_id("bench_20260112_120000")

# Start suite
suite_config = get_suite("cs-mlkem768-aesgcm-mldsa65")
agg.start_suite("cs-mlkem768-aesgcm-mldsa65", suite_config)

# Record events
agg.record_handshake_start()
# ... handshake happens ...
agg.record_handshake_end(success=True)

agg.record_crypto_primitives({
    "kem_encaps_ns": 500000,
    "sig_verify_ns": 1200000,
})

agg.record_traffic_start()
# ... traffic phase ...
agg.record_traffic_end()

agg.record_data_plane_metrics({
    "ptx_in": 1000,
    "enc_out": 1000,
})

# Finalize and save
final_metrics = agg.finalize_suite()
print(f"Total metrics fields: {len(final_metrics.to_dict())}")
```

## Verified Functionality

- ✅ GCS collectors: Environment, System, Network all working
- ✅ Drone collectors: CPU 31.9%, temp 63.8°C, load avg 1.25
- ✅ Role detection: GCS on Windows (AMD64), Drone on RPi (aarch64)
- ✅ 72 cipher suites available for benchmarking
- ✅ 231 metric fields across 18 categories

## Next Steps

1. Run actual GCS-Drone benchmark over network
2. Generate per-suite JSON files with all 231 metrics
3. Create comprehensive LaTeX report with new data
