# Scheduler Policy V2

## 1. Purpose

This document defines the scheduler policy for the implemented PQC MAVLink tunnel in this repository.

The goal is not to invent a new tunnel. The goal is to turn the current tunnel, benchmark harness, and scheduler code into a defensible, benchmark-driven, platform-adaptive policy for Raspberry Pi based UAV deployment and paper publication.

This policy is written against the code that already exists in:

- `core/async_proxy.py`
- `core/handshake.py`
- `core/aead.py`
- `core/policy_engine.py`
- `core/control_tcp.py`
- `core/suites.py`
- `sscheduler/benchmark_policy.py`
- `sscheduler/policy.py`
- `sscheduler/sdrone.py`
- `sscheduler/sgcs.py`
- `sscheduler/detector_manager.py`

## 2. Verified Current State

The repository already implements the following:

- A real authenticated PQC tunnel with OQS KEM + OQS signature + PSK-bound HKDF.
- A real AEAD data plane with replay protection, deterministic nonce construction, and rekey support.
- In-band rekey coordination through `prepare_rekey`, `commit_rekey`, and `status`.
- A benchmark mode that can cycle the 24 canonical `KEM x SIG` benchmark suites and collect timing and energy-related artifacts.
- A split registry model in `core/suites.py` with:
  - 24 benchmark suite IDs
  - 3 scheduler-approved runtime suite IDs
  - 8 approved AEAD profiles across `L1`, `L3`, and `L5`
- A drone-side scheduler with three policy styles:
  - `BenchmarkPolicy` for deterministic benchmarking.
  - `TelemetryAwarePolicyV2` for simpler flight adaptation.
  - `EnergyAwarePolicy` for three-axis adaptation.
- A detector manager with two relevant detector levels:
  - `XGBOOST` as the lighter detector.
  - `TST` as the heavier detector.

This means Policy V2 should be an evolution of the current scheduler stack, not a replacement from zero.

## 3. Corrections to the Current Framing

### 3.1 TLS claim

The current implementation is not TLS 1.3. It is a custom authenticated MAVLink tunnel.

That matters for the paper. You can say:

- "custom PQC-authenticated MAVLink tunnel"
- "industry-aligned control-plane and data-plane design"
- "benchmark-driven secure tunnel for UAV telemetry and command traffic"

You should not say the current implementation is TLS 1.3 unless you actually replace or wrap the tunnel with an OQS-enabled TLS stack.

Also, TLS 1.4 is not a standard. If you want an industry-standard comparison baseline, use:

- TLS 1.3 with OQS/OpenSSL provider
- QUIC with TLS 1.3
- WireGuard/IPsec hybrid migration baselines

as comparison systems, not as claims about the current code.

### 3.2 "Unbreakable" or "unhackable"

Do not use "unbreakable tunnel" or "unhackable tunnel" in the paper.

That is not a defensible scientific claim. A correct claim is:

- quantum-resistant authenticated tunnel
- post-quantum secure tunnel prototype
- benchmark-driven adaptive PQC tunnel

### 3.3 Standard-aligned deployed suites

The codebase currently exposes ML-KEM, ML-DSA, Falcon, SPHINCS+, HQC, and Classic McEliece families.

For deployment-oriented policy, these must not all be treated equally.

Policy V2 should classify suites as:

- Operational baseline inside this research prototype:
  - ML-KEM-512 + ML-DSA-44
  - ML-KEM-768 + ML-DSA-65
  - ML-KEM-1024 + ML-DSA-87
- Research and benchmark only:
  - Falcon
  - HQC
  - SPHINCS+ or SLH-DSA migration candidates
  - Classic McEliece

Reason:

- NIST finalized ML-KEM in FIPS 203 on August 13, 2024.
- NIST finalized ML-DSA in FIPS 204 on August 13, 2024.
- NIST finalized SLH-DSA in FIPS 205 on August 13, 2024.
- HQC was selected by NIST on March 11, 2025 as a backup KEM track, but it is not yet a final FIPS standard.
- Classic McEliece was not selected for NIST standardization.
- OQS and liboqs remain prototype-oriented and recommend caution for production use.

### 3.4 Ascon naming and deployment claim

The active code now treats `Ascon-AEAD128` / `ascon128` as the only supported
Ascon path.

Therefore Policy V2 should treat the current Ascon path as:

- standardized operational candidate:
  - `ascon128` / `Ascon-AEAD128`

This is now aligned with the latest code updates and NIST SP 800-232.

### 3.5 DDoS reaction

The current `EnergyAwarePolicy` already avoids the older "attack means weakest
crypto" mistake.

For Policy V2, DDoS should not automatically imply a drop to the weakest security level.

Correct behavior is:

- keep at least the operator-required minimum NIST level
- lock to the cheapest safe AEAD on the current platform
- scale detector level according to thermal and CPU headroom
- reduce exploration and rekey churn
- only downgrade NIST level if safety constraints force it

Attack pressure is primarily a compute and availability problem, not by itself a reason to lower cryptographic assurance.

The current code is already closer to this corrected behavior than earlier
iterations: it primarily locks to the cheapest safe AEAD first.

### 3.6 Latency interpretation

End-to-end latency is mostly a data-plane and queueing issue during steady state.

KEM and signature choices matter mainly:

- at first handshake
- at rekey time
- during suite transitions

Therefore:

- AEAD selection should be the primary runtime latency lever.
- NIST level selection should be a mission-level and rekey-level decision.
- link degradation should not cause frequent level flapping.

### 3.7 Benchmarking strategy

Old "72-suite" wording is stale for the current code model.

The current benchmark model is:

- 24 canonical `KEM x SIG` suite IDs
- AEAD benchmarked as a separate runtime axis
- operational runtime scheduling restricted to the 3 scheduler-approved suites

So Policy V2 must talk about:

- 24 handshake suites for the benchmark registry
- 8 approved AEAD profiles across the three NIST levels
- full matrix benchmarking as a lab/publication mechanism, not a deployment scheduler

Policy V2 must separate:

- offline or pre-flight profiling
- online mission scheduling

The scheduler should not benchmark every suite during flight.

## 4. Policy V2 Summary

Policy V2 is a deterministic, benchmark-driven, platform-adaptive, three-axis scheduler with operator-constrained crypto agility.

The three axes are:

- Axis A: Security level selection
  - L1, L3, L5
- Axis B: AEAD selection
  - runtime data-plane choice
- Axis C: DDoS detector level
  - `NONE`, `XGBOOST`, `TST`

The scheduler is:

- platform-independent by capability detection plus cached benchmark profiles
- benchmark-driven by pre-flight ranking, not online brute-force testing
- safety-first by thermal, battery, and throttling gates
- operator-aware by authenticated GCS policy intents
- standards-aligned by separating deployable suites from research suites

## 5. Design Principles

### 5.1 Deterministic over black-box ML

For a UAV security path, a deterministic expert policy is preferable to a learned controller.

Reasons:

- easier to validate
- easier to explain in a paper
- safer under sparse or noisy telemetry
- easier to audit against mission constraints

### 5.2 Benchmark-seeded, telemetry-corrected

Pre-flight benchmarks establish the initial ranking.

In-flight telemetry adjusts within the safe region but does not replace the benchmark profile.

### 5.3 Safety dominates performance

The scheduler must never optimize security or throughput by crossing into unstable thermal or power states.

### 5.4 Operator intent is bounded by safety

The GCS can request a higher or lower minimum NIST level.

The drone should honor this only if:

- the requested level is supported by the local platform profile
- the transition budget allows it
- thermal, battery, and throttling gates do not block it

### 5.5 Crypto agility with bounded churn

Rekey is a valuable tool, but it must be budgeted. Policy V2 keeps the current windowed transition budgets and makes them central to the control logic.

## 6. Recommended Suite Taxonomy

### 6.1 Deployable suite set

Use only these for runtime operational policy in this research prototype:

- `cs-mlkem512-mldsa44`
- `cs-mlkem768-mldsa65`
- `cs-mlkem1024-mldsa87`

AEAD is a separate runtime axis. The approved AEAD profile matrix is:

- `L1`
  - `aesgcm128`
  - `aesccm128`
  - `ascon128`
- `L3`
  - `aesgcm192`
  - `aesccm192`
- `L5`
  - `aesgcm256`
  - `aesccm256`
  - `chacha20poly1305`

Benchmark-only AEAD tokens still present in the codebase for research comparison:

- `aegis256`

### 6.2 Research suite set

Keep these for evaluation and paper comparison only:

- Falcon-based suites
- HQC-based suites
- SPHINCS+ based suites
- Classic McEliece based suites

### 6.3 Default runtime recommendation

For current Pi 4 operation, the most defensible default is:

- Start at L3
- Use the locally cheapest deployable AEAD profile from the platform profile
- In the absence of a generated profile, use the measured default from the current
  `EnergyAwarePolicy` seed data, but describe this honestly as a Pi-class seeded
  default, not as platform-independent policy

## 7. Platform Independence

Platform independence must not mean static hard-coded rankings.

Platform independence should mean:

1. Detect the platform.
2. Measure its crypto behavior.
3. Cache the profile.
4. Reuse the profile for mission scheduling.

### 7.1 Platform detection inputs

At startup, collect:

- board model
- CPU architecture
- CPU features such as AES or NEON support
- memory size
- cooling type if known
- current firmware and kernel
- whether power sensor support is available
- throttling support through `vcgencmd get_throttled`

For Pi-class devices, thermal and throttling awareness should explicitly use:

- SoC temperature
- throttled flags
- arm frequency state if available

### 7.2 Platform profile artifact

On first run or when invalidated, generate:

- `logs/sscheduler/platform_profiles/<platform_id>.json`

Suggested schema:

```json
{
  "platform_id": "rpi4b-bcm2711-a72",
  "created_utc": "2026-03-14T00:00:00Z",
  "cooling": "active",
  "telemetry": {
    "supports_throttled_flags": true,
    "supports_power_sensor": false
  },
  "constraints": {
    "temp_warn_c": 70.0,
    "temp_hard_c": 75.0,
    "temp_critical_c": 80.0
  },
  "aead_rank_by_level": {
    "L1": ["aesgcm128", "aesccm128", "ascon128"],
    "L3": ["aesgcm192", "aesccm192"],
    "L5": ["chacha20poly1305", "aesgcm256", "aesccm256"]
  },
  "deployable_profiles": {
    "L1": {
      "suite_id": "cs-mlkem512-mldsa44",
      "aead_token": "aesgcm128"
    },
    "L3": {
      "suite_id": "cs-mlkem768-mldsa65",
      "aead_token": "aesgcm192"
    },
    "L5": {
      "suite_id": "cs-mlkem1024-mldsa87",
      "aead_token": "chacha20poly1305"
    }
  },
  "metrics": {
    "cs-mlkem768-mldsa65::chacha20poly1305": {
      "handshake_ms": 24.1,
      "aead_encrypt_ns": 950.0,
      "aead_decrypt_ns": 980.0,
      "energy_per_bit_nj": 1.42,
      "temp_rise_c": 3.8
    }
  }
}
```

### 7.3 When to re-profile

Re-profile when:

- platform ID changes
- firmware or kernel changes substantially
- cooling changes
- OQS or liboqs version changes
- benchmark cache is missing or stale

## 8. Two-Phase Operation Model

Policy V2 separates operation into two phases.

### 8.1 Phase 1: Profiling and ranking

This phase uses benchmark tooling and should happen:

- offline in the lab
- at first deployment
- after major software or hardware changes
- optionally pre-flight when time permits

This phase should use `BenchmarkPolicy` and the benchmark scripts, but filtered to:

- 24 benchmark suites for full publication-space characterization
- 3 deployable runtime suites for operational ranking
- AEAD profiles benchmarked as a separate axis over those suites
- research suite set retained only for publication experiments

### 8.2 Phase 2: Mission scheduling

This phase uses a runtime scheduler based on:

- cached benchmark profile
- live drone telemetry
- live GCS telemetry
- detector state
- operator policy commands

This phase should be based on the current `EnergyAwarePolicy`, not on the round-robin benchmark policy.

## 9. Inputs Required by Policy V2

### 9.1 Inputs already present in code

- temperature and temperature rate
- CPU utilization
- battery voltage and rate
- armed state
- telemetry age
- packet rate, silence, gap, jitter, blackout count
- proxy AEAD timing
- detector level, active state, warmup state
- rekey history

Policy note:
The current runtime does not yet ingest live power, throttle flags, battery
percentage, or explicit e2e latency percentiles into `DecisionInput`. Those
remain implementation gaps, not already-finished features.

### 9.2 Inputs missing or incomplete

Policy V2 should add:

- end-to-end latency percentiles from the telemetry path
- live power if INA219 is available
- `vcgencmd get_throttled` state
- current CPU frequency
- battery percentage as a first-class policy signal
- explicit operator mission mode
- explicit operator minimum NIST level

This is important for scientific honesty: the current runtime policy is benchmark-seeded and telemetry-aware, but not yet fully live-power-aware or explicit e2e-latency-aware.

Another important honesty note:
the current `EnergyAwarePolicy` still uses hard-coded Pi-derived AEAD seed values
and detector overhead constants. That is useful as a seeded policy baseline, but
it is not yet equivalent to the platform-profile architecture proposed here.

If the paper wants an industry migration story, benchmark comparison against a hybrid classical plus PQC baseline should be added as future work. That is consistent with current OQS deployment guidance.

## 10. Policy State Machine

Policy V2 should operate with these scheduler states:

- `BOOTSTRAP`
  - detect platform and load profile
- `PREFLIGHT_PROFILE`
  - run reduced benchmark if profile missing or stale
- `NOMINAL`
  - normal mission operation
- `OPERATOR_TRANSITION`
  - pending operator-requested level change
- `ATTACK_RESPONSE`
  - DDoS-aware constrained mode
- `THERMAL_GUARD`
  - pre-throttle protective mode
- `POWER_GUARD`
  - battery and power protective mode
- `EMERGENCY`
  - minimum safe crypto and detector off
- `RECOVERY`
  - gradual return after stress

The scheduler should log transitions between these states for publication analysis.

## 11. Core Decision Logic

The runtime policy should be lexicographic and constrained.

### 11.1 Gate order

1. Validate telemetry freshness.
2. Check hard safety gates.
3. Apply operator constraints.
4. Apply DDoS response.
5. Apply thermal management.
6. Apply power and battery management.
7. Apply latency optimization.
8. Consider conservative upgrades.
9. Otherwise hold.

### 11.2 Hard safety gates

If any of the following are true:

- temperature at or above critical threshold
- throttling currently active
- undervoltage detected
- battery critical

then:

- detector -> `NONE`
- target suite -> cheapest deployable suite at L1
- execute emergency rekey if transition budget permits
- freeze upgrades until recovery hysteresis clears

### 11.3 Operator constraint gate

The GCS may send:

- minimum NIST level
- allowed detector ceiling
- mission mode such as `balanced`, `latency`, `endurance`, `high_security`

The drone does not directly obey a raw suite request.

Instead it:

1. updates policy constraints
2. selects the best locally valid suite from the benchmark profile
3. executes a bounded rekey through the existing control-plane flow

Code-alignment note:
this `update_policy` command model is still a proposed next step. The current
runtime does not yet implement an authenticated policy-intent command carrying
`min_nist_level`, `mission_mode`, and `detector_ceiling`.

### 11.4 DDoS gate

If attack is suspected or confirmed:

- freeze AEAD exploration
- pick the cheapest safe AEAD from the platform profile
- keep current NIST level if it satisfies operator minimum
- raise detector level only if thermal and CPU headroom allow it
- if `TST` is unsafe, use `XGBOOST`
- if even `XGBOOST` is unsafe, use `NONE`

This is a key Policy V2 change from the current "attack implies emergency downgrade" tendency.

### 11.5 Thermal gate

Thermal control should act before hard throttling.

Suggested thresholds on Pi 4 and Pi 5:

- warning at 70 C
- hard-protect around 75 C
- critical at 80 C

Actions:

- first reduce detector level
- then move to a cooler AEAD
- then block level upgrades
- only then consider level downgrade

The scheduler should prefer keeping the CPU below the point where firmware-level throttling begins.

### 11.6 Power and battery gate

Power-aware control order:

1. detector down
2. cheaper AEAD
3. lower level only if mission policy allows

This ordering is correct because:

- detector cost is additive and often avoidable
- AEAD cost is continuous and dominates steady-state crypto cost
- KEM and signature cost is mostly transition cost

### 11.7 Latency gate

Latency policy should focus on the data plane.

Actions:

- prefer the locally fastest safe AEAD within the current required level
- defer expensive level upgrades during poor link conditions
- avoid unnecessary different-level rekeys during transient latency spikes

### 11.8 Recovery gate

Recovery requires:

- stable telemetry
- no active throttle flags
- temperature below warning threshold minus hysteresis
- battery stable

Recovery order:

1. upgrade detector if needed
2. restore preferred AEAD
3. restore higher NIST level only after sufficient stability

## 12. Rekey Policy

Policy V2 keeps the current budgeted rekey concept and formalizes it.

### 12.1 Rekey classes

- same-suite rekey
  - rotate keys only
- same-level different-AEAD rekey
  - same `KEM x SIG` suite ID, different runtime AEAD profile
- different-level rekey
  - mission or safety transition

### 12.2 Rekey priority

Prefer:

1. same-suite rekey
2. same-level AEAD switch
3. different-level rekey

### 12.3 Rekey triggers

- sequence safety limit
- operator-requested minimum level change
- thermal or power protection
- recovery after stable window

### 12.4 Rekey flow

Policy V2 uses the already implemented flow:

1. select target suite
2. `prepare_rekey`
3. switch local and follower proxies
4. `commit_rekey`
5. collect `status`
6. update epoch and transition log

## 13. DDoS Detector Policy

### 13.1 Detector tiers

- `NONE`
  - lowest resource use
- `XGBOOST`
  - default light detector
- `TST`
  - heavy detector with high thermal sensitivity

### 13.2 Detector escalation rules

- `NONE` -> `XGBOOST` when attack suspicion exists and headroom is sufficient
- `XGBOOST` -> `TST` only if:
  - platform profile explicitly allows it
  - temperature is comfortably below hard threshold
  - CPU headroom is sufficient
  - mission mode is not endurance-critical

### 13.3 Detector de-escalation rules

Always de-escalate detector before lowering security level when the problem is compute or thermal stress.

This matches the structure already present in `EnergyAwarePolicy` and should remain central in V2.

## 14. Ranking Method

Policy V2 should not choose suites with a single weighted score at all times.

Use this approach:

### 14.1 First, filter

Remove suites that violate:

- operator minimum NIST level
- deployable-suite whitelist
- detector cross-axis constraints
- current thermal safety
- current transition budget

### 14.2 Then, rank lexicographically

Rank remaining candidates by:

1. satisfies operator minimum level
2. no thermal-risk increase
3. lowest detector burden
4. lowest AEAD steady-state cost
5. lowest expected handshake cost
6. best observed stability on this platform

This avoids unstable behavior from trying to compress all mission tradeoffs into one fragile scalar score.

## 15. GCS Command Model

Policy V2 needs an explicit policy command, not only raw suite orchestration.

This is a proposed extension, not a description of already-implemented command
handling in the current scheduler runtime.

Recommended command shape:

```json
{
  "cmd": "update_policy",
  "min_nist_level": "L5",
  "mission_mode": "high_security",
  "detector_ceiling": "XGBOOST",
  "allow_research_suites": false
}
```

### 15.1 Security requirement

This should be carried over the authenticated control path, not trusted as plain unauthenticated scheduler JSON.

Best practical path:

- use the authenticated tunnel control path for policy intents
- keep the current TCP scheduler channel for orchestration and legacy tooling only

### 15.2 Drone behavior on receipt

On receiving an update:

1. validate fields
2. persist policy intent
3. compute the best valid target suite from the platform profile
4. if target differs from current and budgets allow, start rekey
5. acknowledge result and reason

## 16. Mapping to Current Code

### 16.1 Keep

- `BenchmarkPolicy` for measurement runs
- `EnergyAwarePolicy` as the basis of runtime logic
- `DetectorManager`
- `DecisionInput`
- `prepare_rekey` / `commit_rekey` / `status`
- rekey event logging and epoch tracking

### 16.2 Demote

- `TelemetryAwarePolicyV2` should remain as a simpler baseline, not the main deployment scheduler
- full-suite deterministic cycling should remain benchmark-only

Also demote conceptually:

- old generic AEAD naming assumptions such as `aesgcm` as a final runtime policy
  token, because the latest codebase is now level-profile aware
- stale suite examples that embed AEAD into the suite id

### 16.3 Add

Implement these next:

1. platform profile generator and cache loader
2. replace hard-coded AEAD seed and detector-overhead tables with generated per-platform artifacts
3. authenticated `update_policy` command
4. explicit runtime throttle signal ingestion
5. explicit e2e latency metrics in `DecisionInput`
6. optional live power ingestion when INA219 is present
7. mission-mode aware ranking
8. detector feedback signal stronger than the current local drop/flood heuristic
9. remove stale generic-AEAD defaults from the simpler policy path

## 17. What This Means for the Paper

### 17.1 Stronger claim

The strong and defensible research claim is not:

- "we built an unhackable tunnel"

It is:

- "we built and benchmarked a post-quantum secure MAVLink tunnel with a benchmark-driven, policy-based adaptive scheduler"

### 17.2 Real contribution

The actual contribution is the combination of:

- real PQC tunnel implementation
- real in-band rekeying
- real Pi-class deployment constraints
- benchmark-driven suite selection
- three-axis scheduling across security, AEAD, and detector overhead

That is already a good paper direction.

### 17.3 Better title

A better title than the current draft is:

**Flying Into the Quantum Era: A Benchmark-Driven, Policy-Based Post-Quantum Secure MAVLink Tunnel for UAVs**

Alternative:

**Flying Into the Quantum Era: Platform-Adaptive Scheduling for a Post-Quantum Secure MAVLink Tunnel on UAV Companion Computers**

These titles are more precise and more defensible than "unbreakable" language.

## 18. Final Policy Recommendation

The best scheduler for this codebase and paper is:

- deterministic
- benchmark-seeded
- platform-profile driven
- three-axis
- operator-constrained
- safety-first

In practice that means:

- use full benchmarking to characterize the research space
- use only standard-aligned deployable suites for operational policy
- let AEAD be the main online latency and energy lever
- let NIST level be a mission and rekey lever
- let detector level be the first knob to turn down under thermal stress
- keep GCS security-level updates as policy intent, not raw suite forcing

## 19. Immediate Implementation Priorities

Priority order:

1. Keep runtime operational selection bound to the scheduler-approved suite subset in `core/suites.py`.
2. Add platform profile cache generation from benchmark outputs.
3. Replace hard-coded Pi seed tables in `EnergyAwarePolicy` with generated profile data.
4. Extend `DecisionInput` with throttle flags, battery percentage, live power, and e2e latency.
5. Add authenticated `update_policy` handling for minimum NIST level and mission mode.
6. Strengthen DDoS policy input from detector feedback rather than only proxy drop/flood heuristics.
7. Keep `BenchmarkPolicy` only for lab characterization, not flight adaptation.

## 20. References

- NIST FIPS 203, ML-KEM: https://csrc.nist.gov/pubs/fips/203/final
- NIST FIPS 204, ML-DSA: https://csrc.nist.gov/pubs/fips/204/final
- NIST FIPS 205, SLH-DSA: https://csrc.nist.gov/pubs/fips/205/final
- NIST SP 800-232, Ascon lightweight cryptography: https://csrc.nist.gov/pubs/sp/800/232/final
- NIST PQC standardization project: https://csrc.nist.gov/Projects/post-quantum-cryptography
- NIST HQC announcement, March 11, 2025: https://www.nist.gov/news-events/news/2025/03/nist-selects-hqc-backup-algorithm-general-encryption-protect-against-future
- Open Quantum Safe FAQ: https://openquantumsafe.org/faq.html
- Open Quantum Safe TLS integrations: https://openquantumsafe.org/applications/tls.html
- liboqs: https://github.com/open-quantum-safe/liboqs
- liboqs-python: https://github.com/open-quantum-safe/liboqs-python
- IETF draft, PQC for engineers: https://www.ietf.org/archive/id/draft-ietf-pquip-pqc-engineers-04.html
- Hasan et al., "A Framework for Migrating to Post-Quantum Cryptography": https://arxiv.org/abs/2307.06520
- Liu et al., "Post-Quantum Cryptography for Internet of Things: A Survey on Performance and Optimization": https://arxiv.org/abs/2401.17538
- Khan et al., "Future-Proofing Security for UAVs With Post-Quantum Cryptography: A Review": https://repository.essex.ac.uk/39966/1/Future-Proofing_Security_for_UAVs_With_Post-Quantum_Cryptography_A_Review.pdf
- Raspberry Pi `vcgencmd get_throttled` documentation: https://www.raspberrypi.com/documentation/raspbian/applications/vcgencmd.md
- Raspberry Pi thermal testing for Pi 4: https://www.raspberrypi.com/news/thermal-testing-raspberry-pi-4/
- Raspberry Pi thermal behavior for Pi 5: https://www.raspberrypi.com/news/heating-and-cooling-raspberry-pi-5/
- Raspberry Pi cooling guidance: https://pip-assets.raspberrypi.com/categories/685-app-notes-guides-whitepapers/documents/RP-003608-WP/Cooling-a-Raspberry-Pi-device
