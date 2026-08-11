---
description: Derive scheduler behavior from sscheduler code (policy + lifecycle) and validate against actual run artifacts (not assumed gate counts)
---

# Scheduler Analysis Skill

**Scope:** `sscheduler/*.py`, `settings.json`, `core/config.py`, `core/policy_engine.py`

## Non-Negotiables
- Do not state the number of “gates”, thresholds, timers, or “axes” unless you extract them from code/config.
- Treat different scheduler variants (`*_bench`, `*_mav`, non-bench) as different execution paths until proven equivalent.

## Purpose
Produce a correct description of scheduler logic and control-plane behavior, grounded in:
- `sscheduler/policy.py` (decision logic)
- `sscheduler/sgcs*.py` / `sscheduler/sdrone*.py` (lifecycle + orchestration)
- `settings.json` / env (configuration)

## Workflow
1) **Lock the execution path**
   - Identify which pair is being used: `sgcs_bench+sdrone_bench`, `sgcs_mav+sdrone_mav`, or another pair.
   - Identify the benchmark/control mode resolution (see `sscheduler/common.py`).

2) **Extract policy behavior from code**
   - Summarize decisions as code-backed rules: “if condition X in function Y then action Z”.
   - Any threshold value must be cited to the exact config key or literal in code.

3) **Validate lifecycle ordering**
   - What must start first (control server, proxy, traffic, MAVProxy)?
   - What is the shutdown ordering and failure recovery behavior?

4) **Produce pseudocode only as a projection of code**
   - Pseudocode must be derivable from named functions/branches.

## Output
A compact report containing:
- `execution_path`
- `policy_rules` (each rule links to code)
- `config_keys_used`
- `lifecycle_invariants`
- `unknowns`

