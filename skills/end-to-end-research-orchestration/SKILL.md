---
description: Orchestrate the full secure-tunnel research workflow across code, scheduler behavior, metrics, datasets, and paper artifacts. Use when Codex needs to run an end-to-end repo-backed validation or professor-review preparation flow without losing evidence traceability.
---

# End-to-End Research Orchestration

## Purpose
Coordinate the repo's existing secure-tunnel skills into one evidence-first workflow for:
- end-to-end repo understanding
- paper-to-code reconciliation
- benchmark and dataset extraction
- final review prep for VTC / IEEE submission work

## Default Scope
- Code truth: `core/`, `sscheduler/`
- Execution truth: `logs/`, `zfinal/raw/`, benchmark outputs, CSV/JSON artifacts
- Paper truth: prefer `zfinal/draft-final-v8.tex` when present; use `zfinal/draft-final-v7-redo.tex` for lineage, comparison, or evidence recovery

## Required Inputs To Lock Early
1. Active draft target
2. Active scheduler family
3. Allowed evidence scope
4. Whether live lab execution is allowed

If any of these are unknown, state the assumption explicitly before proceeding.

## Skills To Compose
- `secure-tunnel/skills/repo-analysis/SKILL.md`
- `secure-tunnel/skills/core-transport-validation/SKILL.md`
- `secure-tunnel/skills/metrics-truth-reconciliation/SKILL.md`
- `secure-tunnel/skills/scheduler-analysis/SKILL.md`
- `secure-tunnel/skills/scheduler-control-validation/SKILL.md`
- `secure-tunnel/skills/benchmark-extraction/SKILL.md`
- `secure-tunnel/skills/manuscript-validation/SKILL.md`
- `secure-tunnel/skills/manuscript-writing/SKILL.md`
- `secure-tunnel/skills/latex-code-review/SKILL.md`
- `secure-tunnel/skills/latex-tables/SKILL.md`
- `secure-tunnel/skills/tikz-diagrams/SKILL.md`
- `secure-tunnel/skills/ip-consistency-gate/SKILL.md`

Load only the skills needed for the current phase.

## Workflow
1. Lock the authoritative draft, scheduler family, and artifact scope.
2. Build a code-path summary from `core/` and `sscheduler/`.
3. Reconcile metrics semantics before using any derived ratios in paper prose.
4. Reconcile manuscript claims against code paths and on-disk artifacts.
5. Generate or refresh tables and figures only from canonical datasets.
6. Produce a concise verdict with unsupported claims clearly marked.

## Evidence Rules
- Do not merge archived benchmark evidence and March 2026 revalidation evidence without labeling the distinction.
- Do not present `packet_loss_ratio` as total drop ratio unless all drop classes are included in the cited formula.
- Do not call a scheduler path “current” unless the entrypoint and execution family are proven from code.

## Expected Output
Produce a compact handoff containing:
- `active_targets`
- `skills_used`
- `evidence_sources`
- `validated_claims`
- `unsupported_claims`
- `next_actions`
