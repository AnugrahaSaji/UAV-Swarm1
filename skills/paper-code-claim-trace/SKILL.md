---
description: Trace secure-tunnel manuscript claims to exact code paths and evidence files. Use when reconciling `zfinal/` drafts with `core/`, `sscheduler/`, and benchmark artifacts before reviewer or professor feedback.
---

# Paper-Code Claim Trace

## Purpose
Build a clean mapping from manuscript statements to:
- code paths that define intended behavior
- logs/CSV/JSON artifacts that prove measured behavior
- remaining unsupported or fragile claims

## Primary Targets
- `zfinal/draft-final-v8.tex`
- `zfinal/draft-final-v7-redo.tex`
- `core/`
- `sscheduler/`
- `reports/`
- `analysis/`
- `zfinal/raw/`

## Workflow
1. Extract claims from the draft section under review.
2. Classify each claim as:
   - code-backed behavior claim
   - artifact-backed quantitative claim
   - interpretation / framing claim
3. For behavior claims, point to the exact file and function.
4. For quantitative claims, point to the exact artifact and, when possible, the producing script.
5. Mark anything unproven as `TODO(EVIDENCE)` or `unsupported`.

## Special Checks
- Distinguish archived benchmark corpus from hardened-core revalidation.
- Distinguish scheduler lineage claims from claims about the currently exercised path.
- Distinguish control-plane RTT from data-plane latency.
- Distinguish partial drop formulas from total loss claims.

## Output
Produce:
- `claim`
- `claim_type`
- `source_of_truth`
- `file_paths`
- `status`
- `notes`
