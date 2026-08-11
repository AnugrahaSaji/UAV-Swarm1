---
description: Codebase intelligence — map secure-tunnel architecture and execution paths using code as the only source of truth
---

# Repo Analysis Skill

**Scope:** `core/**/*.py`, `sscheduler/**/*.py`, `ddos/**/*.py`, `tools/**/*.py`, `bench/**/*.py`

## Non-Negotiables
- Code is truth. Logs/CSVs are execution truth.
- No imagination: do not assert counts, thresholds, or “tiers” unless you can point to the exact code/artifact that defines them.
- Search-first discipline: grep before reading whole files.

## Purpose
Build a reliable mental model of the repo: module roles, entrypoints, and cross-module dependencies.

## Workflow
1) **Locate real entrypoints (do not guess)**
   - Proxy CLI: `core/run_proxy.py`
   - Scheduler variants (pick the one actually used): `sscheduler/sgcs*.py`, `sscheduler/sdrone*.py`

2) **Trace execution paths with evidence links**
   - For each path you describe (startup, handshake, data-plane, rekey, metrics), provide:
     - the starting entrypoint
     - the key call chain (function/symbol names)
     - what artifact proves runtime behavior (tests/log output) *if available*

3) **Build an import/dependency map (cheap, high-signal)**
   - Enumerate imports and identify “spines” (modules with many inbound edges).

4) **Extract invariants (only if code states them)**
   - Prefer “this invariant is enforced here” over “the system should”.
   - If an invariant is assumed but not enforced, mark it explicitly as a risk.

## Output
A compact report containing:
- `entrypoints`
- `module_map`
- `execution_paths`
- `invariants_enforced`
- `invariants_assumed`
- `open_unknowns`

