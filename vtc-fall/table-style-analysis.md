# IEEE VTC-Grade Table Engineering — Style Analysis & Design Rules

**Agent A Output — Phase 1: Literature Pattern Mining**
Generated: 2026-03-03 | Repository: 68bdb5c | Target: IEEE VTC Fall 2026

---

## 1. IEEE VTC Table Conventions (from Proceedings Style Guide)

### 1.1 Structural Rules
- **Column limit**: ≤10 data columns per table (single-column: ≤6, double-column: ≤10)
- **Row density**: 6–20 data rows per table; beyond 20 → split or appendix
- **Font**: `\footnotesize` mandatory for IEEE conference tables; `\scriptsize` only if overflow
- **Number alignment**: Right-align all numeric columns via `r` specifier
- **Unit placement**: In column header, NOT repeated per cell — e.g., `(µs)` not `9.28 µs`
- **Rule style**: `\toprule`, `\midrule`, `\bottomrule` (booktabs); NO vertical rules
- **Grouping**: Use `\multicolumn` or `\textit{NIST Level X}` separator rows
- **Precision**: Match measurement resolution — timing to 2 decimal places (µs), power to 2 dp (W), energy to 1 dp (µJ), percentages to 1 dp

### 1.2 Caption & Notes
- Caption ABOVE table (`\caption{...}` before `\begin{tabular}`)
- Table notes via `\begin{tablenotes}` BELOW table body
- Define ALL symbols in notes (first occurrence)
- Cross-reference pattern: `Table~\ref{tab:X}` with non-breaking space

### 1.3 Comparative Table Patterns (from PQC/IoT Literature)

| Pattern | When to Use | Example |
|---------|------------|---------|
| **Horizontal comparison** | Same metric across N algorithms | AEAD timing per payload |
| **Vertical grouping** | Algorithms grouped by category/level | KEM by NIST level |
| **Delta columns** | Before/after or with/without | `Δ%` for DDoS overhead |
| **Pareto markers** | Highlight best-in-class | Bold best, underline 2nd |
| **Ratio column** | Normalize to reference | `ρ = cost / cost_ref` |

---

## 2. Data Dimension Reduction (Agent B)

### 2.1 Available Data Dimensions

| Dimension | Values | Source |
|-----------|--------|--------|
| NIST Level | L1, L3, L5 | Suite combination |
| KEM family | ML-KEM, HQC, McEliece | v2-1.8ghz |
| SIG family | ML-DSA, Falcon, SPHINCS+ | v2-1.8ghz |
| AEAD cipher | AESG, CH20, ASC | power_aead_benchmark (rerun) |
| Payload size | 9, 28, 33, 42, 54, 64, 256, 263, 1024, 4096 B | rerun CSV |
| Operation | encrypt, decrypt | rerun CSV |
| DDoS detector | None, XGBoost, TST | bench_ddos_results/comparison.json, policy.py |
| Metric type | timing, power, energy, throughput, temperature | Multiple |

### 2.2 Reduction Strategy

**For Table A (Security-Cost Tradeoff):** Collapse payload to 256B reference. Collapse operation to enc+dec sum. Show representative best/worst suite per level.

**For Table B (AEAD×DDoS):** Fix payload at 256B and 263B (MAVLink default). Show 3 AEAD × 3 detector states. Metrics: latency, ΔP, E_bit.

**For Table C (Scheduler):** Abstract to scenario-trigger-decision triples. No raw metrics — architectural trace.

---

## 3. New Table Designs

### 3.1 Table A: Security-Cost Tradeoff Under Adversarial Load

**Purpose**: Cross-reference security level, suite choice, and detector state in a single compressed table. Answers: "What is the total operational cost of a given security posture?"

**Layout** (double-column `table*`):

```
Rows:     3 NIST levels × 2 suites (best + worst) = 6 rows
          × 3 detector states = 18 rows (grouped)
Columns:  Level | Suite | Detector | T_HS(ms) | ΔP(W) | E_HS(mJ) | T_peak(°C) | CPU(%)
```

**Compression**: Group by NIST level with `\textit{Level X}` separators. Merge repeated T_HS values (same for all detectors since DDoS doesn't affect crypto timing). Use `—` for cells that are the same as the row above.

**Data source mapping**:
- T_HS: from Table 6 (suite-level, reconstructed)
- ΔP: `_DETECTOR_OVERHEAD` from policy.py
- CPU: `_DETECTOR_OVERHEAD` from policy.py
- T_peak: `_DETECTOR_OVERHEAD.delta_temp_c` from policy.py

**Status**: DDoS/Scheduler still improving → LAYOUT for detector columns.

### 3.2 Table B: AEAD Sensitivity to DDoS Load

**Purpose**: Show how each symmetric cipher degrades under concurrent detection. Key insight: NEON-optimized CH20 is least affected.

**Layout** (single-column `table`):

```
Rows:     3 AEADs × 2 operations (enc/dec) = 6 rows
          OR 3 AEADs (enc only) = 3 rows
Columns:  AEAD | t_baseline(µs) | t_XGB(µs) | Δ_XGB(%) | t_TST(µs) | Δ_TST(%) | E_bit_base | E_bit_TST
```

**Compression**: Collapse enc/dec to combined (enc+dec)/2 for single metric row per AEAD. Use `Δ%` columns instead of absolute values where space is tight.

**Data source mapping**:
- t_baseline: rerun CSV at 256B
- t_XGB, t_TST: NOT AVAILABLE — per-packet AEAD×DDoS interaction not measured (I5)
- E_bit: derived metric

**Status**: LAYOUT — DDoS interaction data has provenance gap (I5). Values populated from available markdown but flagged.

### 3.3 Table C: Scheduler Decision Trace

**Purpose**: Show MDEAS state machine decisions across representative operational scenarios. Architectural table — no measured runtime data (I4).

**Layout** (double-column `table*`):

```
Rows:     5 scenarios:
          1. Nominal (cold start)
          2. Thermal stress (T > 70°C)
          3. DDoS alert (threat detected)
          4. Battery critical (P > 4W sustained)
          5. High-security escalation (external trigger)
Columns:  Scenario | Trigger | AEAD_before → AEAD_after | Level_before → Level_after |
          Detector_before → Detector_after | Constraint Applied
```

**Compression**: Use arrows (→) for state transitions. Omit unchanged axes with `—`.

**Data source mapping**:
- All values from `sscheduler/policy.py` code constants and constraint rules
- Trigger thresholds from policy.py `_DETECTOR_OVERHEAD`, `_FORBIDDEN_*` sets
- No measured runtime decisions (I4)

**Status**: LAYOUT — scheduler has no measured behavioral log data.

---

## 4. Graph Strategy

### 4.1 Recommended Figures

| Figure | Type | Data | Priority |
|--------|------|------|----------|
| AEAD scaling curves | Line plot, 3 series | rerun CSV, 10 payload sizes | HIGH — shows NEON advantage |
| KEM cost vs security level | Grouped bar | v2-1.8ghz KEM data | MEDIUM — compact summary |
| Suite Pareto frontier | Scatter (T_HS vs E_HS) | Reconstructed suite data | HIGH — motivates default choice |
| DDoS thermal envelope | Heatmap 2×3 | Detector × CPU state | LOW — LAYOUT only |

### 4.2 Figure–Table Relationship

- Fig. AEAD scaling → complements Table 5 (scaling)
- Fig. Suite Pareto → complements Table A (security-cost) by showing the full 72-suite space
- Fig. KEM bars → replaces detailed KEM table if page budget is tight

---

## 5. LaTeX Integration Checklist

- [ ] All new tables pass `\usepackage{booktabs}` rules (no `\hline`)
- [ ] Double-column tables use `table*` environment
- [ ] Table notes define formulas and caveats
- [ ] LAYOUT tables have `[LAYOUT]` in caption and gray placeholder cells
- [ ] Cross-references use `~\ref{tab:X}` consistently
- [ ] Number formatting: comma thousands separator via `\,` (e.g., `1\,327`)
- [ ] Version stamp in header comments updated to v1.1

---

## 6. Provenance Constraints

| Table | Data Source | Verified? | Caveat |
|-------|-----------|-----------|--------|
| Tab 2 (KEM) | v2-1.8ghz JSON | YES — 100 iter, perf gov | Power from same session |
| Tab 3 (SIG) | v2-1.8ghz JSON | YES — 100 iter, perf gov | Power from same session |
| Tab 4 (AEAD 256B) | vtc-fall-aead-rerun CSV | YES — rerun verified | P_idle=3.320W |
| Tab 5 (AEAD scaling) | vtc-fall-aead-rerun CSV | YES — rerun verified | Timing only |
| Tab 6 (Suite) | Reconstructed from Tab 2+3 | YES — algebraic | No measured E2E |
| Tab 7 (DDoS overhead) | bench_ddos_results/comparison.json | YES — measured | 72 suites, 2-feature models |
| Tab 8 (detector inference) | bench_ddos_results/results.json | YES — measured | Baseline 3.309W |
| Tab A (Security-Cost) | Cross-ref Tab 2+3+7 | LAYOUT — DDoS columns pending | |
| Tab B (AEAD×DDoS) | DDoS_PQC_IMPACT_ANALYSIS.md (excluded) | LAYOUT — I5 applies, no backing data | |
| Tab C (Scheduler) | policy.py code constants | LAYOUT — no runtime data (I4) | |
