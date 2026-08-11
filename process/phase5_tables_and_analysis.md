# Phase 5 Tables and Analysis
## Consolidated Core Validation + 3-Device Benchmark Snapshot

Date: 2026-03-14  
Scope: `core/` implementation status, validation evidence, and latest multi-device benchmark run

---

## 1) Evidence Sources Used

1. `process/phase2_core_iteration2_journal.md`
2. `process/phase3.md`
3. `process/phase4.md`
4. Benchmark run folders:
   - `benchmarks/core_all_remaining_local_20260314`
   - `C:\Users\burak\ptojects\secure-tunnel\benchmarks\core_all_remaining_burak_20260314`
   - `/home/dev/secure-tunnel/benchmarks/core_all_remaining_pi_20260314`

---

## 2) Core Validation Status (Phase 2-4)

| Validation Block | Reported Result | Interpretation |
|---|---:|---|
| Compile gate (core target modules) | Pass | Core modules compile cleanly in recorded phase checks. |
| `tests/test_core_quality.py` | 42 / 42 pass | No unit-level regressions reported in that snapshot. |
| Runtime rekey matrix handshake checks (Phase 3) | 16 / 16 pass | All runtime-visible suites on that host completed handshake checks. |
| Runtime AEAD-only ratchet checks (Phase 3) | 80 / 80 pass | AEAD ratchet derivation logic and key-length mapping passed in matrix validation. |
| Runtime negotiation checks (Phase 3) | 1936 / 1936 pass | Capability selection respected level-aware policy for tested runtime states. |
| Live loopback E2E rekey cases (Phase 4) | 4 / 6 pass | Full-handshake paths stable; AEAD-only had partial failures under active traffic. |

---

## 3) 3-Device Benchmark Execution Table (Latest Run)

Command family used on each host:

```bash
python bench/benchmark_pqc.py --iterations 5 --output-dir <device-specific-dir>
```

| Device | Hostname | Runtime Env | Git Commit | HQC Availability During Run | Discovered KEM/SIG/AEAD/Suites | Run Status |
|---|---|---|---|---|---|---|
| Local workstation | `CSG_DRONES` | `conda: oqs-dev` | `44af93c8a4bb...` | Not available (auto-pruned) | `6 / 8 / 4 / 16` | Complete |
| Remote Windows (`burak`) | `lappy` | `conda: oqs-dev` | `44af93c8a4bb...` | Available | `9 / 8 / 4 / 24` | Complete |
| Raspberry Pi (`dev`) | `uavpi` | `~/cenv` | `44af93c8a4bb...` | Available | `9 / 8 / 4 / 24` | Complete |

Note: This satisfies "ignore HQC unavailability and continue remaining" because local runtime automatically removed HQC-dependent suites and still completed the full remaining set.

---

## 4) Benchmark Output Artifact Table

These are summary result counts written by `bench/benchmark_pqc.py` for the latest run.

| Device | KEM Summary Rows | SIG Summary Rows | AEAD Summary Rows | Suite Handshake Summary Rows | Output Folder |
|---|---:|---:|---:|---:|---|
| Local workstation | 18 | 24 | 32 | 16 | `benchmarks/core_all_remaining_local_20260314` |
| Remote Windows (`burak`) | 27 | 24 | 32 | 24 | `C:\Users\burak\ptojects\secure-tunnel\benchmarks\core_all_remaining_burak_20260314` |
| Raspberry Pi (`dev`) | 27 | 24 | 32 | 24 | `/home/dev/secure-tunnel/benchmarks/core_all_remaining_pi_20260314` |

---

## 5) Loopback Rekey Stability Table (From Phase 4)

| Case ID | Category | Result | Continuity Summary |
|---|---|---|---|
| `same_suite_same_aead_l3` | same-suite same-AEAD | Pass | Stable pre/during/post traffic continuity |
| `same_suite_aead_only_l3_gcm_to_ccm` | AEAD-only | Fail | Post window collapsed (`post=0`) |
| `same_suite_aead_only_l1_gcm_to_ascon` | AEAD-only | Pass (degraded) | Post continuity minimal but non-zero |
| `same_suite_aead_only_l5_gcm_to_chacha` | AEAD-only | Fail | Post window collapsed (`post=0`) |
| `diff_suite_same_level_l1` | full handshake | Pass | Stable continuity |
| `diff_suite_cross_level_l1_to_l5` | full handshake | Pass | Stable continuity |

---

## 6) Analysis

### 6.1 What is strong right now

1. Core compile/test quality is stable in the Phase 2 evidence set.
2. Runtime matrix validation (Phase 3) is internally consistent for handshake, negotiation, and ratchet derivation logic.
3. Full-handshake rekey transitions are stable in live loopback traffic (Phase 4).
4. Multi-device benchmark command path is operational across all 3 targets and produces complete artifacts.

### 6.2 What is not yet fully production-stable

1. AEAD-only rekey under live traffic is still not uniformly reliable (`2/3` AEAD-only shifts showed hard post-window drops in Phase 4).
2. Cross-device comparability can be affected by runtime capability asymmetry:
   - Local host currently lacks HQC runtime support.
   - Burak + Pi support HQC.

### 6.3 Practical interpretation for paper claims

1. You can claim strong foundation for:
   - PQC handshake/data-plane implementation
   - Multi-device benchmarkability
   - Stable full-handshake rekey behavior
2. You should not yet claim AEAD-only rekey path as universally robust under active traffic until AEAD-only synchronization issues are closed and Phase 4 loopback reaches 6/6 pass.

### 6.4 Immediate next technical target

1. Prioritize AEAD-only rekey convergence hardening in `core/async_proxy.py` + `core/policy_engine.py`.
2. Re-run the same Phase 4 loopback suite and require:
   - `6/6` pass
   - non-zero `post` continuity for all AEAD-only cases
   - no follower-side timeout failure in AEAD-only transitions

---

## 7) Final Snapshot Verdict

- Core is benchmarkable and operational on all three devices.
- Full-handshake rekey behavior is in good shape.
- AEAD-only live-transition reliability remains the last high-impact blocker before "rock solid" end-to-end claim.

