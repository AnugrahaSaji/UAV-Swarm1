# MAVLink Secure Tunnel Forensic Investigation

Date: 2026-03-16
Scope: Post-benchmark forensic analysis only (no new benchmark execution, no protocol/core code changes)

## 1) Evidence Map

Analyzed artifact sets:
- mavlink-benchmark-report/
- gcs-e2e-report/
- drone-e2e-report/

Primary files used:
- mavlink-benchmark-report/raw-mavlink-log.json
- mavlink-benchmark-report/rekey-events.md
- mavlink-benchmark-report/heartbeat-stability.md
- mavlink-benchmark-report/mavlink-latency.md
- mavlink-benchmark-report/aead-metrics-extracted.json
- mavlink-benchmark-report/aead-comparison-table.md

Additional forensic extractions generated from existing logs:
- mavlink-benchmark-report/_forensic_computed.json
- mavlink-benchmark-report/_forensic_crypto_breakdown.json

## 2) Phase 1: AEAD Performance Analysis

### 2.1 Verified RTT and Jitter Metrics (PING burst)

Standard deviation is computed from raw-mavlink-log `ping_rtt_burst.rtt_us.stdev_ms * 1000`.

| AEAD | NIST | Mean RTT (us) | Median (us) | P95 (us) | P99 (us) | Stddev/Jitter (us) |
|---|---|---:|---:|---:|---:|---:|
| aesgcm128 | L1 | 768.06 | 642.07 | 1213.44 | 1838.72 | 259.00 |
| aesccm128 | L1 | 707.13 | 631.52 | 1067.74 | 1803.70 | 253.00 |
| ascon128 | L1 | 794.85 | 712.91 | 1190.52 | 2471.07 | 345.00 |
| aesgcm192 | L3 | 712.91 | 614.01 | 1112.14 | 1815.41 | 282.00 |
| aesccm192 | L3 | 743.98 | 661.28 | 1122.63 | 1860.78 | 236.00 |
| aesgcm256 | L5 | 698.15 | 612.79 | 1068.24 | 1619.44 | 233.00 |
| aesccm256 | L5 | 813.74 | 713.33 | 1430.61 | 2454.77 | 375.00 |
| chacha20poly1305 | L5 | 668.74 | 565.03 | 1045.75 | 1827.46 | 296.00 |

### 2.2 Cross-Level Summary

| Level | AEAD set | Mean of Mean RTT (us) | Mean of P95 (us) | Mean of P99 (us) | Mean of Stddev (us) |
|---|---|---:|---:|---:|---:|
| L1 | aesgcm128, aesccm128, ascon128 | 756.68 | 1157.23 | 2037.83 | 285.67 |
| L3 | aesgcm192, aesccm192 | 728.44 | 1117.39 | 1838.10 | 259.00 |
| L5 | aesgcm256, aesccm256, chacha20poly1305 | 726.88 | 1181.53 | 1967.22 | 301.33 |

Finding:
- L3 and L5 means are very close (728.44 vs 726.88 us), so suite level alone is not the dominant latency driver.
- L1 dispersion is wider because ascon128 has higher tails and aesgcm128 has post-rekey anomaly in continuous traffic.

### 2.3 Attribution of Performance Differences

Using per-packet primitive timings from status counters (`primitive_metrics`) for stable AEADs, estimated round-trip crypto component:
- `crypto_rt_est_us ~= gcs_enc + gcs_dec + drone_enc + drone_dec`

Representative examples:

| AEAD | Mean RTT (us) | Estimated Crypto RT (us) | Residual Pipeline (us) |
|---|---:|---:|---:|
| chacha20poly1305 | 668.74 | 162.18 | 506.56 |
| aesgcm192 | 712.91 | 164.71 | 548.20 |
| ascon128 | 794.85 | 237.67 | 557.18 |
| aesccm256 | 813.74 | 195.53 | 618.21 |

Interpretation:
- Cryptographic cost differences are real and visible (especially ascon128 and aesccm256 vs chacha20poly1305/aesgcm*).
- A larger constant residual remains across all AEADs (roughly 500-620 us), consistent with proxy transport + MAVProxy scheduling/pipeline overhead.
- Suite pairing contributes less than crypto implementation and pipeline behavior for this dataset.

## 3) Phase 2: Rekey Event Reconstruction

Rekey trigger target is `warmup_s = 300.0` in raw log.

### 3.1 Reconstructed Rekey Timeline

From GCS status counters (`last_rekey_ms`, `rekey_duration_ms`, `rekey_blackout_duration_ms`) where available:

| AEAD | Rekey Start (relative s) | Rekey Complete (relative s) | Duration (ms) | Blackout/Spike (ms) |
|---|---:|---:|---:|---:|
| aesccm128 | 299.979 | 300.000 | 20.562 | 0.753 |
| aesccm192 | 299.980 | 300.000 | 19.855 | 0.998 |
| aesccm256 | 299.980 | 300.000 | 20.079 | 1.003 |
| aesgcm192 | 299.980 | 300.000 | 19.936 | 1.111 |
| aesgcm256 | 299.980 | 300.000 | 20.079 | 0.946 |
| ascon128 | 299.980 | 300.000 | 20.125 | 1.025 |
| chacha20poly1305 | 299.980 | 300.000 | 19.904 | 0.978 |
| aesgcm128 | not recoverable from final status | trigger at ~300 by raw run config | not recoverable | recorded 0.000 in extracted table |

### 3.2 Delivery Before/During/After Rekey

From raw-mavlink-log window counters:

| AEAD | Pre-Rekey Delivery | During-Rekey Delivery | Post-Rekey Delivery |
|---|---:|---:|---:|
| aesgcm128 | 100.0% | 100.0% | 14.81% |
| all other 7 AEADs | 100.0% | 100.0% | 100.0% |

Computed interruption/loss:
- During-rekey packet loss: 0 for all AEADs (including aesgcm128)
- aesgcm128 post-rekey loss: `14750 - 2184 = 12566` packets
- aesgcm128 continuous-window loss: `30001 - 17435 = 12566` packets (41.89%)

Rekey-transition behavior:
- No collapse inside the 5-second during-rekey window.
- Collapse appears immediately after transition to post-rekey window (first observable point: start of post window, approx T+305 s).

## 4) Phase 3: aesgcm128 Failure Analysis

## 4.1 What is directly observable

- Rekey command acknowledged as success:
  - `rekey_ok = true`
  - response includes matching suite: `cs-mlkem512-mldsa44`
- Pre and during windows are both perfect delivery.
- Post window collapses to 14.81% delivery.

## 4.2 Requested fields around transition

Requested: epoch values, sequence numbers, drop/auth/replay counters around transition.

Observed limitation in artifacts for aesgcm128 specifically:
- `cs_mlkem512_mldsa44__aesgcm128_gcs_status.json` and `_drone_status.json` ended in `handshake_ok` state and do not contain final runtime counters.
- corresponding `.tmp` status snapshot contains zero traffic counters and no rekey activity.

Result:
- Exact epoch and sequence values around the failure point are not present in saved aesgcm128 status artifacts.
- Exact replay/auth/session-epoch drop deltas for the failing interval cannot be directly extracted from available files.

## 4.3 Most likely failure mechanism (evidence-based)

Most probable cause: post-commit epoch synchronization failure specific to aesgcm128 data-plane state.

Reasoning chain:
1. During-rekey window is 100% delivery, indicating rekey command path and immediate swap path were operational.
2. Collapse starts only in post window, which is consistent with grace-window expiration and strict epoch acceptance afterward.
3. Other AEADs show normal operation with occasional single `drop_session_epoch` during transition and then full recovery; aesgcm128 uniquely does not recover.
4. Suite mismatch is unlikely:
   - rekey response suite matches configured suite,
   - other L1 algorithms (aesccm128, ascon128) succeed with same suite.
5. Pure auth-failure hypothesis is weaker here because the characteristic timing aligns more strongly with post-window epoch acceptance boundary; however auth/replay counters are missing for definitive proof.

Conclusion for aesgcm128 root cause:
- Primary: epoch-state divergence after rekey commit (high confidence, constrained by missing final counters).
- Secondary alternatives not proven with current artifacts: AEAD auth failure or replay-window rejection.

## 5) Phase 4: Cross-Dataset Comparison (MAVLink vs earlier baselines)

Baseline E2E artifacts:
- gcs-e2e-report/raw-results.json (aesgcm192, L3): mean RTT 864.57 us
- drone-e2e-report/raw-results.json (aesgcm, L3): mean RTT 818.63 us

MAVLink campaign reference (same AEAD family/level):
- mavlink aesgcm192 mean RTT: 712.91 us

Interpretation:
- Absolute RTT values are not directly additive across these campaigns due to different run harnesses and host states.
- Both baseline and MAVLink datasets consistently show that per-packet AEAD primitive time is a minority of RTT, while transport/proxy/scheduler pipeline dominates.
- From MAVLink status counters, estimated crypto round-trip for stable AEADs is ~160-240 us, leaving ~500-620 us residual pipeline time.

Relative contribution estimate (MAVLink, stable AEADs):
- AEAD encryption/decryption: roughly 23-30% of RTT
- Secure tunnel proxy + transport framing/queues: roughly 70-77% of RTT
- MAVProxy scheduling effects: visible mostly in tail metrics (P95/P99 spread and jitter), not in mean alone

## 6) Phase 5: Final Root-Cause Statement

### Why AEADs differ in latency
- Differences are primarily driven by AEAD primitive cost and implementation behavior (ascon128 and aesccm256 are slower/tail-heavier in this run; chacha20poly1305 and aesgcm* are faster).
- A substantial constant pipeline component dominates all AEADs, so crypto choice shifts but does not fully determine RTT.
- NIST suite level is a secondary effect in this dataset.

### What caused aesgcm128 post-rekey collapse
- The collapse is consistent with an epoch transition failure that manifests after the rekey overlap window, not during command execution.
- Post-rekey acceptance fell to 14.81% (loss 12566 packets) despite 100% during-rekey delivery.

### Is it isolated to Level-1 pairing?
- Not generally: other Level-1 runs (aesccm128, ascon128) are stable through rekey.
- The anomaly is specific to aesgcm128 in this campaign.

### Is it reproducible?
- Not yet proven from this artifact set alone.
- Existing artifacts are sufficient to confirm the observed failure, but insufficient to conclusively extract epoch/sequence/auth/replay counters for aesgcm128 because its final status logs are incomplete.

## 7) Inconsistency Notes in Generated Reports

Several generated markdown summaries mark aesgcm128 as "continuous/grade A" despite explicit post-rekey collapse (14.81% post-delivery, 58.11% total). The numeric raw JSON should be treated as source of truth.
