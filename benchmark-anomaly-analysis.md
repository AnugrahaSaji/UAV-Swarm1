# Benchmark Anomaly Analysis

## Scope

This document is a strict evidence-based forensic analysis of anomalies in the MAVLink end-to-end benchmark dataset, with primary focus on the `aesgcm128` post-rekey failure. No new benchmarks were run and no protocol-core files were modified for this analysis.

Primary evidence sources:

- `mavlink-benchmark-report/raw-mavlink-log.json`
- `mavlink-benchmark-report/rekey-events.md`
- `mavlink-benchmark-report/heartbeat-stability.md`
- `mavlink-benchmark-report/aead-metrics-extracted.json`
- `mavlink-benchmark-report/_forensic_computed.json`
- `mavlink-benchmark-report/_forensic_crypto_breakdown.json`
- per-AEAD status files under `mavlink-benchmark-report/aesgcm128/`

## Evidence Map

### Source-of-truth artifacts

- `raw-mavlink-log.json`: authoritative raw benchmark summary and phase-level counters
- `rekey-events.md`: pre/during/post rekey delivery table
- `aead-metrics-extracted.json`: normalized comparison metrics including packet loss and post-rekey delivery

### Supporting forensic artifacts

- `_forensic_computed.json`: derived summary of verified RTT statistics, level summaries, timeline reconstruction, and status summaries
- `_forensic_crypto_breakdown.json`: extracted per-role primitive timing and counter snapshots from saved status files

### Potentially contradictory generated summaries

- `mavlink-benchmark-report/all-aead-summary.md`
- `mavlink-benchmark-report/link-quality.md`
- `mavlink-benchmark-report/aesgcm128/benchmark-summary.md`
- `mavlink-benchmark-report/aesgcm128/rekey-continuity.md`

These generated markdown summaries are not treated as source of truth when they conflict with raw numeric evidence.

## Rekey Timeline Reconstruction

The benchmark artifacts indicate a rekey trigger at approximately `T = 300 s`.

The window structure is consistent across the campaign:

- pre-rekey window: 15,001 packets
- during-rekey window: 250 packets
- post-rekey window: 14,750 packets

For stable AEAD runs, `_forensic_computed.json` reconstructs rekey start times around `299.979 s` to `299.980 s` and durations around `19.855 ms` to `20.125 ms`, with blackout spikes around `0.753 ms` to `1.111 ms`.

For `aesgcm128`, the exact final rekey timing fields are not recoverable from the saved runtime status files.

## Confirmed Delivery Rates Around Rekey

### aesgcm128

From `rekey-events.md` and `aead-metrics-extracted.json`:

| Phase | Sent | Received | Delivery % | Loss |
| --- | ---: | ---: | ---: | ---: |
| Pre-rekey | 15001 | 15001 | 100.00 | 0 |
| During-rekey | 250 | 250 | 100.00 | 0 |
| Post-rekey | 14750 | 2184 | 14.81 | 12566 |
| Total | 30001 | 17435 | 58.11 | 12566 |

### All other AEADs

All seven other AEAD runs show:

- 100% delivery before rekey
- 100% delivery during rekey
- 100% delivery after rekey

This is the most important comparative result in the dataset.

## Confirmed Latency and Loss Characteristics

From `aead-metrics-extracted.json` and `raw-mavlink-log.json`:

- `aesgcm128` mean RTT: `768.06 us`
- median RTT: `642.07 us`
- P95 RTT: `1213.44 us`
- P99 RTT: `1838.72 us`
- total packet loss: `41.89%`
- post-rekey delivery: `14.81%`

The critical point is that the failure is not preceded by a visibly abnormal RTT collapse in earlier phases. The same `aesgcm128` run passes:

- heartbeat continuity
- ping RTT burst
- high-rate stress
- during-rekey overlap

The collapse is therefore a post-transition continuity defect, not a general inability to carry traffic.

## Runtime Counter Evidence

### What is available for stable AEADs

For successful runs such as `aesccm128`, final status files contain runtime counters including:

- `drops`
- `drop_replay`
- `drop_auth`
- `drop_session_epoch`
- `rekeys_ok`
- `rekeys_fail`
- `last_rekey_ms`
- `rekey_duration_ms`
- `rekey_blackout_duration_ms`
- primitive metrics for encrypt and decrypt operations

This confirms that the artifact format is capable of preserving the information needed for a strong forensic conclusion.

### What is missing for aesgcm128

For `aesgcm128`, the final saved `*_status.json` files remain at `handshake_ok` and do not preserve the runtime counters needed for the failure interval. The available saved snapshots do not provide definitive values for:

- `drop_replay`
- `drop_auth`
- `drop_session_epoch`
- `rekeys_ok`
- `rekeys_fail`
- final `rekey_duration_ms`
- final `rekey_blackout_duration_ms`
- per-packet epoch/sequence trace at the transition boundary

This is the primary evidence gap in the anomaly investigation.

## Confirmed Observations

The following statements are directly supported by the saved artifacts.

1. The `aesgcm128` run successfully completes all phases before the post-rekey interval.
2. The rekey command itself reports success.
3. Delivery remains 100% during the explicit overlap window.
4. Delivery collapses immediately in the post-rekey window and stays degraded throughout that window.
5. The anomaly is isolated to `aesgcm128` in this campaign; other L1 runs and other AES-GCM runs remain continuous.
6. The saved runtime counters for `aesgcm128` are incomplete, preventing definitive classification of the exact drop reason.
7. Some generated markdown summaries incorrectly report `aesgcm128` as continuous or grade-A even though the raw numeric evidence contradicts that conclusion.

## Hypotheses

The following hypotheses are plausible interpretations of the evidence, but they are not proven at counter level by the saved artifacts.

### Hypothesis 1: post-commit epoch-state divergence

This is the strongest hypothesis.

Why it fits the evidence:

- perfect delivery before and during overlap indicates the initial rekey machinery was operating
- collapse begins after overlap ends, which is exactly where strict post-transition epoch acceptance becomes decisive
- other successful AEADs show normal transition through the same structural window

Why it is not proven:

- the final `aesgcm128` `drop_session_epoch` counters were not preserved

### Hypothesis 2: replay-window rejection after transition

This remains possible.

Why it fits part of the evidence:

- replay protection is sequence-sensitive and stateful
- a receiver state divergence could cause systematic post-window rejection

Why it is weaker than Hypothesis 1:

- the timing aligns more directly with transition boundary semantics than with a generic replay defect
- no supporting saved `drop_replay` counter exists for the affected run

### Hypothesis 3: systematic AEAD authentication failure after activation

This is possible but less supported.

Why it cannot be ruled out:

- missing `drop_auth` counters prevent exclusion

Why it is not the leading hypothesis:

- the sharp boundary at the end of overlap is more naturally explained by acceptance-state mismatch than by a generic authentication instability

## Contradictory Artifact Assessment

Several generated markdown reports mark `aesgcm128` as continuous even though the raw evidence shows:

- `post_rekey_delivery_percent = 14.81`
- `continuous_total_delivery_percent = 58.11`
- `packet_loss_percent = 41.89`

For anomaly analysis, `raw-mavlink-log.json` and `aead-metrics-extracted.json` should therefore be treated as authoritative over these derived markdown summaries.

## Root-Cause Assessment

### Confirmed root-cause statement

The dataset confirms a severe post-rekey continuity failure in the `aesgcm128` MAVLink run. The failure begins after a successful overlap window and persists throughout the post-rekey interval. This is a real benchmark anomaly, not a reporting artifact.

### Best-supported causal interpretation

The strongest evidence-supported interpretation is that the failure is consistent with a post-commit state divergence, most likely involving epoch acceptance after the grace-window period.

### Required caveat

The current artifacts do not preserve the exact drop-reason counters needed to prove whether the rejecting condition was epoch mismatch, replay rejection, or authentication failure. Any stronger claim would exceed the evidence.

## Evidence Gaps

The current repository artifacts do not allow recovery of the following items for the failing interval:

- exact epoch values on both peers after activation
- exact sequence-number progression at the transition boundary
- definitive `drop_session_epoch` counts
- definitive `drop_replay` counts
- definitive `drop_auth` counts
- exact timing of the first rejected post-window packet

These gaps should be stated explicitly in any paper or report using this anomaly.

## Bottom Line

The anomaly investigation supports three firm conclusions.

1. The `aesgcm128` MAVLink run experienced a genuine and severe post-rekey delivery collapse.
2. The defect is isolated within this campaign to `aesgcm128`, not to the benchmark framework as a whole.
3. The most likely explanation is a post-transition state divergence, but the exact rejection mechanism cannot be proven from the saved counters because the final runtime status for the affected run is incomplete.