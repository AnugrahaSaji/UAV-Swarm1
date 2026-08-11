---
description: Produce TikZ/pgfplots figures for the secure-tunnel paper while keeping every labeled element traceable to code or datasets
---

# TikZ Diagrams Skill

**Scope:** `zfinal/*.tex`, `paper/**/*.tex`, `**/*.tikz`, datasets under `paper/**/datasets/`

## Non-Negotiables
- Do not hard-code venue-specific dimensions (column widths, page limits) unless they are defined in the active LaTeX class/template used by the paper.
- Any plotted value must come from a dataset file; any architectural arrow must correspond to a code-level dataflow.

## Workflow
1) Inventory existing figures and their `\label{...}` usage.
2) For architecture diagrams:
   - derive blocks/arrows from the actual entrypoints and modules
3) For plots:
   - derive series from canonical datasets
4) Compile-check the paper to ensure the figure renders.

## Output
- TikZ figure code committed alongside the paper sources
- A short note linking each figure element to:
  - code paths (for architecture)
  - dataset paths (for plots)

