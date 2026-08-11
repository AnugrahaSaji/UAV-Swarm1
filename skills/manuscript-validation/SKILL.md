---
description: Validate manuscript quality — LaTeX compilation, reference integrity, and claim verification with strict traceability
---

# Manuscript Validation Skill

**Scope:** `zfinal/*.tex`, `paper/**/*.tex`, `vtc-fall/*.tex`, `*.bib`

## Non-Negotiables
- Do not assume venue constraints (page limits, formatting) unless confirmed by the active template/class in the repo.
- For numerical claims: no “tolerance” rules by default — match the artifact exactly unless the manuscript explicitly states rounding.

## Workflow
1) **LaTeX compilation check**
   - Use the repo’s current paper entrypoint (see `secure-tunnel/zfinal/`).
   - Capture compile output (warnings/errors) as an artifact.

2) **Reference integrity**
   - Every `\cite{key}` must exist.
   - Flag unused BibTeX entries only if the repo enforces that policy.

3) **Claim verification (the core of this skill)**
   For each quantitative claim:
   - identify the claim text
   - locate the supporting artifact (CSV/JSON/log)
   - locate the producing script and command
   - verify the number matches the artifact
   - if missing evidence: mark `unsupported` and request the minimal run needed

4) **Table/Figure consistency**
   - every `\ref{fig:...}` and `\ref{tab:...}` resolves
   - any `LAYOUT` content is clearly labeled and cannot be mistaken for results

## Output
- `skills/manuscript-validation/references/validation_report.md`
- `skills/manuscript-validation/references/claim_trace.csv`

