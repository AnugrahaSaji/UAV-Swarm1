# Scheduler Policy Brainstorm

## Scope and Evidence Rules

This document is a scheduler-policy design exploration derived strictly from verified code and measured benchmark artifacts in the repository. It does not assume behavior that is not supported by the current code or benchmark data. The core protocol baseline is frozen at `PROTOCOL_VERSION = 1.0`; scheduler discussion here is therefore limited to runtime policy above the frozen transport semantics.

Primary evidence base:

- `sscheduler/policy.py`
- `sscheduler/sdrone.py`
- `sscheduler/sgcs.py`
- `sscheduler/sdrone_bench.py`
- `sscheduler/sgcs_bench.py`
- `mavlink-benchmark-report/`
- `gcs-e2e-report/`
- `drone-e2e-report/`

## Verified Scheduler Architecture

### Control Roles

The scheduler is asymmetric.

- `sscheduler/sdrone.py` contains the controlling scheduler loop on the drone side.
- `sscheduler/sgcs.py` is the follower. It starts and stops the GCS proxy, batches telemetry, and serves clock-sync and control requests, but it does not decide suite transitions.

### Policy Entry Points

The main decision points in `sscheduler/policy.py` are:

- `TelemetryAwarePolicyV2.evaluate(inp)`
- `EnergyAwarePolicy.evaluate(inp)`
- `BenchmarkPolicy.evaluate(now)` in `sscheduler/benchmark_policy.py`

The main scheduler execution loops in `sscheduler/sdrone.py` are:

- `MavTunnelScheduler._run_intelligent()`
- `MavTunnelScheduler._run_energy_aware()`
- `MavTunnelScheduler._build_decision_input()`
- `MavTunnelScheduler._switch_suite()`

### Inputs Already Modeled in Code

`DecisionInput` in `sscheduler/policy.py` already exposes most of the runtime inputs needed for policy work:

- telemetry freshness and sample count
- packet-rate and gap statistics: `rx_pps_median`, `gap_p95_ms`, `silence_max_ms`, `jitter_ms`, `blackout_count`
- local battery and thermal state: `battery_mv`, `battery_roc`, `temp_c`, `temp_roc`
- current suite and epoch state
- proxy crypto costs: `aead_encrypt_avg_ns`, `aead_decrypt_avg_ns`
- packet counters and drop totals
- CPU utilization
- detector state

This means a scheduler policy can be discussed as an extension of code that already exists, not as an unrelated design proposal.

## Measured Benchmark Observations Relevant to Policy

### 1. AEAD latency characteristics

From `mavlink-benchmark-report/aead-metrics-extracted.json`:

| AEAD | NIST | Mean RTT us | P95 us | Packet loss % |
| --- | --- | ---: | ---: | ---: |
| aesccm128 | L1 | 707.13 | 1067.74 | 0.00 |
| aesgcm128 | L1 | 768.06 | 1213.44 | 41.89 |
| ascon128 | L1 | 794.85 | 1190.52 | 0.00 |
| aesccm192 | L3 | 743.98 | 1122.63 | 0.00 |
| aesgcm192 | L3 | 712.91 | 1112.14 | 0.00 |
| aesccm256 | L5 | 813.74 | 1430.61 | 0.00 |
| aesgcm256 | L5 | 698.15 | 1068.24 | 0.00 |
| chacha20poly1305 | L5 | 668.74 | 1045.75 | 0.00 |

What this supports:

- NIST level alone is not the dominant RTT driver in this dataset.
- `chacha20poly1305` is the lowest-latency AEAD in the measured MAVLink campaign.
- `aesgcm256` is also strong in mean and tail latency.
- `ascon128` and `aesccm256` are comparatively tail-heavier in this environment.
- `aesgcm128` cannot be treated as a normal low-cost candidate without explicitly accounting for its anomaly status in this specific campaign.

### 2. Continuous per-packet CPU cost of cryptographic primitives

From `_AEAD_BENCHMARK_SEED` in `sscheduler/policy.py`:

- `chacha20poly1305`: ~63.5 us encrypt, ~70.7 us decrypt
- `aesgcm`: ~66.9 us encrypt, ~73.6 us decrypt
- `ascon128` / `ascon128a`: far higher software cost on the measured ARM platform

What this supports:

- The code already treats AEAD selection as a first-class runtime axis.
- On the measured Raspberry Pi class ARM environment, ChaCha20 and AES-GCM are close enough that other constraints such as anomaly status, rekey stability, CPU pressure, or battery slope can legitimately decide between them.
- Ascon should not be assumed to be energy-favorable on this platform merely because it is lightweight in some other contexts. The repository's own measurements show the opposite for this implementation environment.

### 3. Rekey impact on telemetry

From `mavlink-benchmark-report/rekey-events.md` and `mavlink-benchmark-report/anomaly-investigation.md`:

- Seven AEADs preserved 100% delivery before, during, and after rekey.
- Stable runs show rekey durations near 20 ms and blackout spikes near 1 ms.
- `aesgcm128` preserved 100% delivery before and during rekey but dropped to 14.81% delivery after rekey.

What this supports:

- Rekey is usually safe enough to be treated as an operational control action.
- Rekey budgets and cooldowns in `sscheduler/policy.py` are conceptually justified.
- Any policy that includes `aesgcm128` as an automatically selected runtime target must carry explicit anomaly caveats based on the measured MAVLink data.

### 4. Packet-loss behavior under continuous traffic

The MAVLink campaign shows zero packet loss for all tested AEADs except `aesgcm128`. This matters because a scheduler policy must distinguish between low-latency and reliable-latency candidates. The dataset does not support a policy that optimizes purely on mean RTT and ignores continuity through rekey.

## What the Existing Policies Already Do

### TelemetryAwarePolicyV2

`TelemetryAwarePolicyV2.evaluate()` already implements a conservative gate sequence:

1. hold on stale telemetry
2. emergency downgrade on critical battery or temperature
3. rollback and blacklist on blackout shortly after a switch
4. hold during cooldown
5. downgrade on persistent link degradation
6. downgrade on thermal or battery stress
7. proactive rekey once stable
8. conservative upgrade only when disarmed and stable

Evidence-supported reading: this policy is designed for safety and rollback, not for aggressive AEAD optimization.

### EnergyAwarePolicy

`EnergyAwarePolicy.evaluate()` extends the architecture into three axes:

- Axis 1: AEAD selection
- Axis 2: security-level selection
- Axis 3: detector-level selection

It also maintains `AeadCostProfile` objects and uses benchmark-seeded initialization. This is important because the policy does not start from zero knowledge. It already consumes measured crypto cost and refines that estimate online.

## Evidence-Supported Scheduler Policy Concepts

### Policy Concept A: Stable preferred set by platform class

Supported input dimensions:

- hardware platform
- measured crypto cost
- packet loss behavior
- NIST level requirement

Evidence-supported idea:

- On Raspberry Pi 4 class ARM hardware, the preferred AEAD set should start from `chacha20poly1305` and `aesgcm*` variants, not Ascon.
- The scheduler can encode a platform-specific initial preference order because the repository already contains measured seed data and a benchmark-seeded cost model.

What this document does not claim:

- It does not claim the same order on x86 with AES acceleration.
- It does not claim that one single AEAD is globally optimal across all platforms.

### Policy Concept B: Reliability-first candidate filtering

Supported input dimensions:

- packet loss
- rekey continuity
- blackout counts

Evidence-supported idea:

- Candidate AEADs should be filtered by continuity evidence before latency ranking.
- In the current measured dataset, `aesgcm128` should be marked as a cautionary or excluded candidate for automatic runtime switching in MAVLink mode until its anomaly is resolved or disproven in a controlled rerun.

Concrete scheduler implication:

- Use `proxy_drop_total`, blackout counts, and observed rekey outcomes as a hard gate before applying mean-cost ranking.

### Policy Concept C: Break-even rekey control

Supported input dimensions:

- measured AEAD cost profiles
- packet rate
- average rekey cost
- battery and thermal slope

Evidence-supported idea:

- The existing `EnergyAwarePolicy._compute_break_even_s()` structure is aligned with the benchmark evidence because the repository contains both measured per-packet crypto cost and measured rekey event durations.
- A runtime switch is more defensible when packet rate is high enough for AEAD savings to amortize rekey cost.

What remains unsupported:

- The exact threshold constants have not been validated by a dedicated study in the current artifact set.

### Policy Concept D: Thermal pressure should prefer cheaper stable AEADs before level changes

Supported input dimensions:

- `temp_c`, `temp_roc`, `cpu_pct`
- live AEAD cost observations
- benchmark-seeded thermal deltas in `sscheduler/policy.py`

Evidence-supported idea:

- Under thermal stress, a scheduler should first try reducing per-packet crypto cost within the same security level before changing NIST level, because the benchmark evidence shows that the continuous AEAD data-plane cost dominates handshake-plane cost over time.

Why the data supports this:

- KEM and signature cost is paid at handshake/rekey time.
- AEAD cost is paid on every packet.
- The repository's policy comments and seed table explicitly encode this asymmetry.

### Policy Concept E: Security level should be mission- and policy-driven, not RTT-driven alone

Supported input dimensions:

- NIST requirement
- armed state
- mission criticality
- stable link quality

Evidence-supported idea:

- Because the measured RTT means for L3 and L5 are close in the MAVLink dataset, security level should not be reduced solely to chase small RTT gains.
- Level changes should remain conservative and tied to explicit mission or safety requirements.

### Policy Concept F: Detector-aware crypto scheduling

Supported input dimensions:

- detector level
- CPU utilization
- temperature
- cross-axis compatibility constraints

Evidence-supported idea:

- The code already encodes detector overhead tables and forbids or discourages some combinations.
- A scheduler policy should use detector activation as a budget signal and prefer cheaper stable AEADs when detector load is elevated.

This is supported by code and measured seed data, not only by design intent.

## Candidate Policy Shapes

### 1. Conservative flight policy

Use when:

- armed flight is active
- telemetry is healthy
- thermal and battery conditions are nominal

Policy shape:

- avoid frequent AEAD exploration
- keep a stable AEAD chosen from the reliability-filtered set
- allow proactive rekey only within budget
- permit downgrade only on persistent degradation

Evidence support: strong

### 2. Ground-test optimization policy

Use when:

- disarmed state
- stable link
- no thermal or battery stress

Policy shape:

- permit more aggressive same-level AEAD switching for measurement and adaptation
- log comparative live profiles using `AeadCostProfile`

Evidence support: moderate

Reason for caution:

- the dataset contains static benchmark comparisons but not a dedicated repeated switching study under operational MAVLink load.

### 3. Emergency resource policy

Use when:

- battery critical
- temperature critical
- detector overhead is unsafe

Policy shape:

- kill expensive detector modes first if necessary
- move to lowest acceptable security level only when required by policy constraints
- choose the cheapest measured stable AEAD for the current platform

Evidence support: moderate to strong for the architecture, weaker for exact numeric thresholds.

## Unsupported Claims This Document Avoids

The current data does not support claiming any of the following:

- a universally optimal AEAD across all hardware classes
- a validated numerical break-even threshold for all traffic regimes
- predictive thermal accuracy under arbitrary transient loads
- proven DDoS resilience of the full scheduler stack under adversarial traffic
- safe automatic use of `aesgcm128` in MAVLink mode after the observed anomaly

## Practical Design Recommendations From the Current Evidence

1. Treat AEAD selection as a platform-dependent runtime decision, not a static cryptographic preference.
2. Rank candidates only after filtering for rekey continuity and packet-loss behavior.
3. Keep NIST level switching conservative because the measured RTT gains are smaller than the risk of unnecessary control-plane churn.
4. Use same-level AEAD switching first for thermal or CPU pressure because continuous per-packet cost dominates handshake cost over time.
5. Carry an explicit anomaly quarantine rule for `aesgcm128` in MAVLink-mode scheduler experiments until a future run captures the missing counters and either reproduces or clears the issue.

## Evidence Gaps and Future Research Questions

These are valid future research questions, but they are not answered by the current artifacts:

- How quickly do live `AeadCostProfile` estimates converge under real flight traffic rather than benchmark traffic?
- What is the best rekey budget under long-duration missions?
- How should platform identifiers such as Pi4 versus Pi5 be normalized into scheduler seed profiles?
- Can thermal and battery-rate hysteresis values be tuned from data rather than policy heuristics?
- Does the `aesgcm128` anomaly reproduce under controlled instrumentation with preserved final runtime counters?

## Bottom Line

The repository already contains the skeleton of a data-driven scheduler. The benchmark evidence supports a reliability-first, platform-aware, AEAD-selection policy with conservative security-level switching and explicit rekey budgeting. The strongest immediate policy implication from the current dataset is not that the scheduler should switch more aggressively, but that it should switch selectively: favor measured stable AEADs, preserve safety gates, and treat anomaly-bearing candidates as ineligible for automatic promotion.