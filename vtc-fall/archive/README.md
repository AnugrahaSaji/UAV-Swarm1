# Archive — Pre-Rerun Original Data

Created: 2026-03-03
Reason: AEAD re-benchmark with verified native C Ascon backend

## Contents

- `power_aead_benchmark_original.csv` — Original 10k-iteration AEAD benchmark
  from root `power_aead_benchmark.csv`. Replaced by `vtc-fall-aead-rerun/`
  data which has:
  - Verified Ascon metadata (ascon-c v1.2 opt64)
  - Matching idle baseline capture (P_idle = 3.454 W)
  - Git commit 68bdb5c verified on both local and RPi

## Key Differences (Original → Rerun)

| Metric | Original | Rerun | Δ |
|--------|----------|-------|---|
| Voltage avg (256B AESG enc) | 5.116 V | 5.516 V | +7.8% |
| Power avg (256B AESG enc) | 2.973 W | 3.625 W | +21.9% |
| Timing (256B AESG enc) | 9.283 µs | 9.254 µs | −0.3% |
| Idle power baseline | 2.961 W | 3.454 W | +16.6% |
| Sample rate | 83–104 Hz | 101–104 Hz | More consistent |

Timing is stable; power shift is due to voltage measurement conditions.
See `inconsistency-report.md` items I7, I8 for full analysis.
