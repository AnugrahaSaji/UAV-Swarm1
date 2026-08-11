---
description: Generate research paper section drafts from verified data, integrating tables, figures, and algorithm descriptions
---

# Manuscript Writing Skill

**Scope:** `zfinal/*.tex`, `paper/vtc_fall/sections/*.tex`, `vtc-fall/*.tex`

## Purpose
Generate well-structured research paper sections from verified experimental data and system analysis, following IEEE conference conventions.

## Trigger Conditions
- Paper section draft needed (introduction, methods, results, discussion)
- Tables/figures need narrative integration
- Algorithm description needs formal writeup
- Threat model or security analysis section required

## Execution Workflow

### Step 1 — Section Planning
Map paper structure to data sources:

| Section | Data Source | Tables/Figures |
|---------|------------|----------------|
| Introduction | Literature, threat model | — |
| System Architecture | `core/`, `sscheduler/` code analysis | fig:architecture |
| PQC Suite Design | `core/suites.py`, `core/handshake.py` | tab:aliases, tab:suite |
| AEAD Evaluation | `aead_benchmark*.csv`, `power_aead_benchmark.*` | tab:aead, tab:aead_scaling, fig:aead_scaling |
| KEM/SIG Evaluation | `benchmark_full_table_20260220.csv` | tab:kem, tab:sig |
| Scheduler (MDEAS) | `sscheduler/policy.py` analysis | Algorithm 1, tab:sched_trace |
| DDoS Detection | `ddos/` analysis, `bench_ddos_results/` | tab:detector_compare, tab:detector_overhead |
| Security Analysis | Threat model, cost equations | tab:security_cost, eq:cost |
| Results & Discussion | All datasets | All tables/figures |

### Step 2 — Writing Rules
1. **No fabrication:** Every numerical claim must trace to a CSV/JSON source file
2. **Passive voice:** IEEE convention for methods sections
3. **Precision:** Use exact numbers from datasets, not rounded approximations
4. **Citations:** Reference existing BibTeX entries from `references.bib`
5. **Cross-references:** Use `\ref{tab:...}`, `\ref{fig:...}`, `\ref{eq:...}`
6. **Equations:** Use `align` or `equation` environments with `\label{eq:...}`

### Step 3 — Integration Pattern
Each section follows:
1. Context sentence (why this matters)
2. Method description (what was measured/analyzed)
3. Table/figure reference with interpretation
4. Key finding statement
5. Comparison to related work (if applicable)

### Step 4 — Verified Data Integration
Before writing any result:
- Read the source CSV/JSON
- Extract the exact numbers
- Cross-reference against `vtc-fall/inconsistency-report.md`
- Tag any unverified data as LAYOUT (gray cells in tables)

## Key Equations
```latex
% Thermal headroom threshold
T_{\text{hs}} = T_{\text{warn}} - \Delta T_{\text{detector}} - \Delta T_{\text{aead}} \label{eq:ths}

% Rekey cost-benefit
t_{\text{rekey}} = \frac{C_{\text{hs}}}{(\delta_{\text{aead}} \cdot r_{\text{pkt}} \cdot 2)} \label{eq:rekey}

% Security cost function
\mathcal{C} = \alpha \cdot P_{\text{aead}} + \beta \cdot T_{\text{hs}} + \gamma \cdot L_{\text{rekey}} \label{eq:cost}
```

## Output Artifacts
Primary target: `zfinal/` (active paper directory)
Archive: `paper/vtc_fall/sections/`

Sections:
- `introduction.tex`
- `system_architecture.tex`
- `evaluation.tex`
- `results.tex`
- `conclusion.tex`
