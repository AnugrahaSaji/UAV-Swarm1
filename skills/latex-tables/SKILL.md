---
description: Convert canonical datasets into LaTeX tables using repo tooling; never embed illustrative numbers as real results
---

# LaTeX Tables Skill

**Scope:** `skills/latex-tables/scripts/generate_tables.py`, `paper/**/datasets/`, `paper/**/tables/`, `zfinal/*.tex`

## Non-Negotiables
- Tables must be generated from datasets (CSV/JSON) that have provenance.
- Never paste “example” numbers into paper tables unless explicitly marked `LAYOUT`.

## Purpose
Generate publication-ready LaTeX tables from the canonical datasets produced by the benchmark extraction pipeline.

## Primary Command
- `python skills/latex-tables/scripts/generate_tables.py`

## Workflow
1) Confirm the input datasets exist (and were recently regenerated if needed).
2) Run the generator script.
3) Verify the paper compiles and that labels referenced in text exist.

## `LAYOUT` Policy
If a table is being mocked for structure only:
- include a visible `LAYOUT` marker in the caption or a footnote
- use placeholders like `X.XX` rather than plausible-looking “real” numbers

## Output
- Generated table files in the locations written by the generator script

