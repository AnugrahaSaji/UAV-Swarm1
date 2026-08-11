---
description: Evidence-first DDoS research — analyze detector codepaths and measure overhead without embedding made-up numbers
---

# DDoS Research Skill

**Scope:** `ddos/**/*.py`, `sscheduler/detector_manager.py`, `bench_ddos_results/`, `ddos/bench_inference.py`, `ddos/bench_power_inference.py`

## Non-Negotiables
- Do not claim a “tier” architecture, feature count, class count, parameter count, or overhead numbers unless:
  - the code defines it (and you link to the defining symbol), or
  - a benchmark artifact contains it (and you link to the artifact path).

## Purpose
Analyze the DDoS detection components and produce overhead/behavior claims that are traceable to code and benchmark artifacts.

## Workflow
1) **Inventory detector components (code-backed)**
   - Identify runnable detector entrypoints under `ddos/`.
   - Identify orchestration/lifecycle logic in `sscheduler/detector_manager.py`.

2) **Map dataflow**
   - Where do packets come from?
   - Where are features computed?
   - How are severity/results emitted and consumed?

3) **Measure overhead (artifact-backed)**
   - Prefer existing bench scripts (`ddos/bench_inference.py`, `ddos/bench_power_inference.py`) and stored outputs under `bench_ddos_results/`.
   - For any reported metric, record:
     - exact command line
     - environment (host role, profile)
     - produced artifact paths (JSON/CSV/log)

4) **Paper integration**
   - Any manuscript claim must include the artifact path(s) and the code path responsible for collection.

## Output
- `skills/ddos-research/references/detection_map.md` (what code runs, how it’s wired)
- `skills/ddos-research/references/overhead_summary.md` (only numbers that exist in artifacts)

