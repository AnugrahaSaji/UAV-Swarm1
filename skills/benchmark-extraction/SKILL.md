---
description: Parse benchmark artifacts into reproducible datasets and validate them without inventing units, ranges, or “expected” results
---

# Benchmark Extraction Skill

**Scope:** `skills/benchmark-extraction/scripts/*.py`, `paper/**/datasets/`, `bench*_results/`, `chronos_runs/`, `individual_benchmarks/`

## Non-Negotiables
- Do not “normalize” units by assumption. Only convert when the script explicitly does so, and document the conversion.
- Do not validate against “known” hardware limits unless you have a code/config source for that limit.
- Every dataset row must trace back to a concrete source file and parsing rule.

## Purpose
Turn raw run artifacts (CSVs, JSONs, logs) into canonical datasets suitable for tables/figures, with validation that catches schema drift.

## Primary Pipeline
Use the repo’s existing pipeline driver:
- `python skills/benchmark-extraction/scripts/run_pipeline.py --stage all`

Stages:
- `extract` — parses raw artifacts into canonical CSVs
- `validate` — checks schema + basic integrity constraints
- `tables` — generates LaTeX tables via `skills/latex-tables/scripts/generate_tables.py`

## What “Validation” Means Here
Validation is about *internal consistency* and *traceability*, not “expected performance”:
- required columns present
- no impossible values per schema (e.g., negative durations)
- stable identifiers (suite ids, algorithm names) match the code registry where applicable
- every output dataset includes a provenance note (which sources were read)

## Output
- Canonical datasets written by the extraction scripts (see script output for exact paths)
- A short provenance note listing:
  - input files consumed
  - output files produced
  - any conversions applied

