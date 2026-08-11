# AEAD Comparison Table

Source: mavlink-benchmark-report/raw-mavlink-log.json and per-AEAD *_gcs_status.json

| AEAD algorithm | NIST level | mean RTT (us) | p95 RTT (us) | p99 RTT (us) | packet loss (%) | rekey interruption duration (ms) |
|---|---:|---:|---:|---:|---:|---:|
| aesgcm128 | L1 | 768.06 | 1213.44 | 1838.72 | 41.89 | 0.000 |
| aesccm128 | L1 | 707.13 | 1067.74 | 1803.70 | 0.00 | 0.753 |
| ascon128 | L1 | 794.85 | 1190.52 | 2471.07 | 0.00 | 1.025 |
| aesgcm192 | L3 | 712.91 | 1112.14 | 1815.41 | 0.00 | 1.111 |
| aesccm192 | L3 | 743.98 | 1122.63 | 1860.78 | 0.00 | 0.998 |
| aesgcm256 | L5 | 698.15 | 1068.24 | 1619.44 | 0.00 | 0.946 |
| aesccm256 | L5 | 813.74 | 1430.61 | 2454.77 | 0.00 | 1.003 |
| chacha20poly1305 | L5 | 668.74 | 1045.75 | 1827.46 | 0.00 | 0.978 |

## Notes

- Packet loss (%) is computed from the continuous rekey phase total window: 100 - total_delivery_pct.
- Rekey interruption duration uses rekey_blackout_duration_ms from GCS status counters.
- All AEADs had during-rekey delivery = 100.0% and rekey trigger at warmup_s = 300.0.
- aesgcm128 shows a post-rekey collapse (post_delivery_pct = 14.81%) despite during-rekey success, so it requires follow-up root-cause analysis before scheduler use.
