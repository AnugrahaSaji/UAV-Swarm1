# Secure Tunnel Repo Understanding - 2026-03-18

## Active Assumptions

- Active paper target: `secure-tunnel/zfinal/draft-final-v8.tex`
- Lineage draft: `secure-tunnel/zfinal/draft-final-v7-redo.tex`
- Code truth: `secure-tunnel/core/` and `secure-tunnel/sscheduler/`
- Execution truth: `secure-tunnel/logs/`, `secure-tunnel/zfinal/raw/`, benchmark CSV/JSON artifacts
- Historical branches unless a claim requires them: `secure-tunnel/vtc/`, `secure-tunnel/final-draft/`, `context/`

These assumptions are the best fit for the current repo state because `secure-tunnel/skills/end-to-end-research-orchestration/SKILL.md` explicitly prefers `draft-final-v8.tex` when present, and `v8` matches the March 2026 hardened-core framing better than `v7-redo`.

## Skill Inventory

### Codex system skills

- `C:\Users\burak\.codex\skills\.system\openai-docs`
- `C:\Users\burak\.codex\skills\.system\skill-creator`
- `C:\Users\burak\.codex\skills\.system\skill-installer`

### Repo-native secure-tunnel skills

- `secure-tunnel/skills/repo-analysis`
- `secure-tunnel/skills/core-transport-validation`
- `secure-tunnel/skills/metrics-truth-reconciliation`
- `secure-tunnel/skills/scheduler-analysis`
- `secure-tunnel/skills/scheduler-control-validation`
- `secure-tunnel/skills/paper-code-claim-trace`
- `secure-tunnel/skills/professor-review-prep`
- `secure-tunnel/skills/public-sense-review`
- `secure-tunnel/skills/manuscript-validation`
- `secure-tunnel/skills/manuscript-writing`
- `secure-tunnel/skills/latex-code-review`
- `secure-tunnel/skills/latex-tables`
- `secure-tunnel/skills/tikz-diagrams`
- `secure-tunnel/skills/benchmark-extraction`
- `secure-tunnel/skills/end-to-end-research-orchestration`

### New Codex-native wrapper skills created in this session

- `C:\Users\burak\.codex\skills\secure-tunnel-research`
- `C:\Users\burak\.codex\skills\secure-tunnel-paper-review`
- `C:\Users\burak\.codex\skills\secure-tunnel-scheduler-analysis`

All three new Codex-native skills validate with `quick_validate.py`.

## Codebase Spine

### Core transport

- Main transport CLI: `secure-tunnel/core/run_proxy.py`
- Long-lived encrypted UDP proxy: `secure-tunnel/core/async_proxy.py`
- Authenticated PQC handshake: `secure-tunnel/core/handshake.py`
- Rekey/control state machine: `secure-tunnel/core/policy_engine.py`
- Optional external TCP control server: `secure-tunnel/core/control_tcp.py`
- Config and env loading: `secure-tunnel/core/config.py`, `secure-tunnel/core/env_loader.py`
- Metrics and benchmark evidence aggregation: `secure-tunnel/core/metrics_aggregator.py`
- Suite and AEAD registry: `secure-tunnel/core/suites.py`

### Scheduler families

- Benchmark/orchestration family:
  - `secure-tunnel/sscheduler/sdrone_bench.py`
  - `secure-tunnel/sscheduler/sgcs_bench.py`
  - `secure-tunnel/sscheduler/benchmark_policy.py`
- Adaptive/runtime family:
  - `secure-tunnel/sscheduler/sdrone.py`
  - `secure-tunnel/sscheduler/sgcs.py`
  - `secure-tunnel/sscheduler/policy.py`
- Secondary lineage:
  - `secure-tunnel/sscheduler/sdrone_mav.py`
  - `secure-tunnel/sscheduler/sgcs_mav.py`

### Registry truth

- Suite identity is KEM + SIG only; AEAD is a separate runtime axis.
- Runtime default KEMs are ML-KEM only.
- Runtime default signatures are ML-DSA only.
- HQC, Classic McEliece, Falcon, and SPHINCS+ remain important benchmark evidence, but they are not all runtime-allowed.

## Confirmed Findings

### 1. The benchmark family and the adaptive MDEAS family are different code paths

- Benchmark evidence path:
  - `sscheduler/sdrone_bench.py` + `sscheduler/sgcs_bench.py`
  - uses `BenchmarkPolicy`
  - supports `cold_restart` and `in_band_rekey`
- Adaptive/runtime path:
  - `sscheduler/sdrone.py` + `sscheduler/sgcs.py`
  - uses `TelemetryAwarePolicyV2` or `EnergyAwarePolicy`
  - current `_switch_suite()` does `prepare_rekey`, stops the local proxy, and stands up the new suite

Paper claims must not blur these two paths together.

### 2. `v7-redo` still overstates the current scheduler story

`secure-tunnel/zfinal/draft-final-v7-redo.tex` still describes `sscheduler/sdrone.py` as the live scheduler entry point and presents the broader MDEAS runtime story as the current path. That is not the cleanest representation of the code and evidence state on 2026-03-18.

`secure-tunnel/zfinal/draft-final-v8.tex` is narrower and stronger:

- archived benchmark corpus justifies ranking and policy priors
- March 2026 hardened-core revalidation justifies transport correctness and scheduler-readiness

That framing is materially closer to the repo's current state.

### 3. `packet_loss_ratio` is a partial drop formula, not a total loss formula

In `secure-tunnel/core/metrics_aggregator.py`, `packet_loss_ratio` is derived from:

- `drop_replay`
- `drop_auth`
- `drop_header`

It excludes at least:

- `drop_session_epoch`
- `drop_other`
- `drop_src_addr`
- `sniff_drop`
- MAVLink sequence-gap observations from `core/mavlink_collector.py`

So any paper or review note that presents `packet_loss_ratio` as total drop ratio is overstated.

### 4. `settings.json` has a schema mismatch against `policy.py`

`secure-tunnel/sscheduler/policy.py` reads keys such as:

- `mission_criticality`
- `max_nist_level`
- `initial_level`
- `preferred_aead`

at the top level.

`secure-tunnel/settings.json` stores at least some of these under nested `policy.*`.

That means paper prose or review notes must not assume the nested `policy.*` section is the active runtime source of truth without confirming the actual key path used by code.

### 5. The scheduler mode name `BENCHMARK_MODE` is overloaded

- In `sscheduler/common.py`, scheduler mode resolution expects only `MAVPROXY`.
- In `core/config.py`, `BENCHMARK_MODE` refers to suite-switch behavior such as `cold_restart` vs `in_band_rekey`.

Operator-facing instructions and paper text must keep those two meanings separate.

### 6. Stale review artifacts exist

Some existing `secure-tunnel/zfinal/raw/` review artifacts do not reflect the current draft or current code state. They are useful as historical notes, but they should not be treated as final truth without revalidation against the active draft.

## Paper-Alignment Guidance

### Safe, code-backed framing

- The codebase provides a hardened split-plane transport:
  - TCP control plane for authenticated handshake and rekey coordination
  - UDP data plane for encrypted MAVLink forwarding
- The codebase exposes scheduler-relevant hooks:
  - explicit rekey orchestration
  - AEAD agility
  - runtime policy surfaces
- Archived benchmark evidence supports broader design choices and ranking.
- March 2026 revalidation supports the narrower claim that the current hardened code path is scheduler-ready.

### Claims that need careful wording

- End-to-end MDEAS evaluation on the current runtime path
- Any claim that the adaptive scheduler currently uses the benchmark family's in-band rekey machinery
- Any claim that `packet_loss_ratio` is total loss
- Any claim that `settings.json.policy.*` directly drives runtime policy without qualification

## Next Actions

1. Use `draft-final-v8.tex` as the main review target unless redirected.
2. Compare `v8` section-by-section against:
   - `core/run_proxy.py`
   - `core/async_proxy.py`
   - `core/handshake.py`
   - `core/policy_engine.py`
   - `core/metrics_aggregator.py`
   - `core/suites.py`
   - `sscheduler/policy.py`
   - `sscheduler/sdrone.py`
   - `sscheduler/sdrone_bench.py`
3. Treat `v7-redo` as lineage and mine it only for salvageable text or evidence links.
4. Refresh or replace stale `zfinal/raw/` review notes if they are needed for professor review.
