---
description: Review LaTeX source quality (compile health, refs/cites, tables/figures) for the secure-tunnel paper without inventing results
---

# LaTeX Code Review (Paper Quality Gate)

## Purpose
Review and improve LaTeX *source quality* for the secure-tunnel paper without inventing claims.

## Scope
- Primary paper: `secure-tunnel/zfinal/draft-final-v7-redo.tex`
- Inputs (when needed): `paper/vtc_fall/datasets/`, `individual_benchmarks/`, `bench_ddos_results/`, `zfinal/raw/`

## Non-Negotiables (Truth + Traceability)
- No fabricated numbers. Every quantitative claim must trace to a concrete artifact (CSV/log) in this repo.
- If evidence is missing, mark as `TODO(EVIDENCE)` and list the minimum run/artifact required.
- Prefer fixing **paper text** over changing code unless the user explicitly requests code changes.

## Review Checklist
1) **Compile health**
   - Must compile cleanly (or with explained, known warnings).
   - Watch for: undefined refs/cites, overfull/underfull boxes, missing figures, missing file includes.

2) **Cross-references + citations**
   - All `\ref{}` targets exist and are unique.
   - All `\cite{}` keys exist in the bib file used by the paper.

3) **Tables**
   - Use `booktabs`-style rules and consistent numeric formatting.
   - Ensure each table caption matches the dataset it was built from.
   - If the table was derived from logs/CSVs, include a short provenance line in the working notes (file path + script + command).

4) **Figures (TikZ/pgfplots)**
   - Axis labels/units match the dataset columns.
   - Colors/markers are consistent across related figures.
   - No rasterization regressions for IEEE (prefer vector output).

5) **Clarity (simple human language)**
   - Prefer short sentences.
   - Avoid hype words ("unbreakable", "guaranteed", etc.).
   - If text is too polished, rewrite to be natural and direct — but never introduce factual errors.

## Outputs
- A short review note (what changed + why).
- If edits are made: a compile check result (command + exit status/output snippet) or a clear TODO to compile.