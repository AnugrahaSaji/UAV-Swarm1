# IEEE Results Pattern Analysis — VTC Fall 2026

Generated: 2026-03-03
Purpose: Structural alignment guide for Results & Analysis section

---

## 1. Reference Corpus

The following references from vtc-fall/references/ inform the IEEE VTC style:

| Ref# | Document | Type | Relevance |
|------|----------|------|-----------|
| 19 | pqm4 ARM Cortex-M4 | Benchmark paper | Table layout, primitive evaluation, energy metrics |
| 20 | PQC TLS Benchmarking | Protocol benchmark | Handshake timing, suite-level evaluation |
| 21 | Rosenpass PQC VPN | System paper | VPN overlay benchmarks, WireGuard integration |
| 06 | CRYSTALS-Kyber | Algorithm spec | KEM parameter tables |
| 07 | CRYSTALS-Dilithium | Algorithm spec | Signature parameter tables |
| 12 | Ascon Lightweight | AEAD spec | Lightweight cipher evaluation |

## 2. Extracted Structural Patterns

### 2.1 Results Section Ordering (IEEE VTC/RTSS/ISORC consensus)

1. **Experimental Platform** — hardware specs, measurement methodology, iteration counts
2. **Primitive-level evaluation** — KEM then SIG then AEAD (separation mandatory)
3. **Composite/suite-level evaluation** — aggregated handshake timing
4. **Overhead analysis** — rekey cost, derived metrics
5. **Adversarial scenario evaluation** — DDoS, stress conditions
6. **System-level behavioral results** — scheduler, degradation

### 2.2 Table Density Pattern

- IEEE VTC two-column format: max 8–10 columns per table
- Preferred: 6–8 columns with units in headers
- Algorithm names shortened to aliases after first-use mapping
- One table per primitive family (KEM, SIG, AEAD separate)
- Suite tables cluster by NIST level, not exhaustive 72-row dump

### 2.3 Column Ordering Convention

Standard order observed in pqm4, PQC-TLS benchmarks:

```
Alias | Level | Operation_1 | Operation_2 | ... | Power | Energy
```

- Time before power before energy (left to right)
- Operations in protocol order (keygen → encaps → decaps)
- Units always in column header parentheses
- Derived metrics (ratios, deltas) in rightmost columns

### 2.4 Alias Naming Conventions

Observed patterns from IEEE embedded/crypto literature:

- **Short prefix + parameter**: K512, K768, K1024 (Kyber → ML-KEM)
- **Family initial + level number**: D44, D65, D87 (Dilithium → ML-DSA)
- **Two-letter codes**: F5, F10 (Falcon-512/1024)
- **Subscript-style in LaTeX**: $\text{ML}_{512}$, $\text{DSA}_{65}$

Selected scheme for this paper (balancing readability and space):

| Alias | Full Name |
|-------|-----------|
| ML512 | ML-KEM-512 |
| ML768 | ML-KEM-768 |
| ML1024 | ML-KEM-1024 |
| HQ128 | HQC-128 |
| HQ192 | HQC-192 |
| HQ256 | HQC-256 |
| MC348 | Classic-McEliece-348864 |
| MC460 | Classic-McEliece-460896 |
| MC8192 | Classic-McEliece-8192128 |
| DSA44 | ML-DSA-44 |
| DSA65 | ML-DSA-65 |
| DSA87 | ML-DSA-87 |
| F512 | Falcon-512 |
| F1024 | Falcon-1024 |
| SP128 | SPHINCS+-SHA2-128s-simple |
| SP192 | SPHINCS+-SHA2-192s-simple |
| SP256 | SPHINCS+-SHA2-256s-simple |
| AESG | AES-256-GCM |
| CH20 | ChaCha20-Poly1305 |
| ASC | Ascon-128a |

### 2.5 Derived Metric Presentation

IEEE pattern: state formula inline or as numbered equation, then populate table.

- Energy per bit: equation, then table column
- Rekey overhead: equation, then numerical example
- Relative slowdown: expressed as "×" factor versus baseline (e.g., "92× vs ML512")
- Power delta: ΔP = P_operation − P_idle (stated whether subtracted or not)

### 2.6 Style Rules Observed

- No first-person ("We measured..." → "Measurements were obtained...")
- No superlatives ("fastest" → "lowest latency among tested algorithms")
- Units always present: ms, µs, W, µJ, mJ, bytes
- Iteration count stated once in methodology, referenced in tables via footnote
- Platform described in a single compact table (not paragraphs)
- Figures referenced as "Fig. N" not "Figure N"
- Tables referenced as "Table N" or "TABLE N" (IEEE caps style)

---

## 3. Dataset Compatibility Verification

| Property | v2-1.8ghz | power_aead_benchmark | bench_ddos_results |
|----------|-----------|---------------------|-------------------|
| Platform | RPi4 B Rev 1.5 | RPi4 B Rev 1.5 | RPi4 B Rev 1.5 |
| CPU freq | 1800 MHz | 1800 MHz | 1800 MHz |
| Governor | performance | performance | performance |
| INA219 Hz | 1000 | ~88–101 | INA219 present |
| Iterations | 100 | 10,000 | 72 suites × 10s |
| Idle sub? | No | No | No |

**Verdict**: All three datasets were collected on the same platform with the same
governor. They are compatible for cross-referencing.

**individual_benchmarks**: Governor is `ondemand` — EXCLUDED per constraint.

---

## 4. Data Source Assignment per Section (Verified 2026-03-03)

| Section | Primary Source | Iterations | Notes |
|---------|---------------|------------|-------|
| KEM Evaluation | v2-1.8ghz/raw_data/raw/kem/ | 100 | 1000 Hz INA219, per-op timing+power |
| SIG Evaluation | v2-1.8ghz/raw_data/raw/sig/ | 100 | 1000 Hz INA219, per-op timing+power |
| AEAD Evaluation | vtc-fall-aead-rerun/power_aead_benchmark.csv | 10,000 | Re-benchmarked 2026-03-03, native C Ascon confirmed, 30s baseline |
| Suite Evaluation | bench_ddos_results/20260302_135859/baseline.json | 72 suites × 10s | LOCAL crypto-only handshake (no network), INA219 power, sub-timings |
| DDoS on PQC | bench_ddos_results/20260302_135859/{baseline,xgb,tst}.json | 72 suites × 3 phases | 2-feature MAVLink-count detectors (xgb_old/tst_old) — label correctly |
| PQC on DDoS | bench_ddos_results/power_20260222_193509/results.json | 1398–2229 | 54-feature CIC-IoT-2023 models, standalone inference latency+power |
| Scheduler | NO MEASURED DATA | — | Code constants only (sscheduler/policy.py); no runtime logs exist |

**EXCLUDED**: individual_benchmarks/ — uses ondemand governor
**EXCLUDED**: DDoS_PQC_IMPACT_ANALYSIS.md phase A–E tables — no backing JSON artifacts
**EXCLUDED**: DDoS accuracy claims — unverifiable from this repository
**EXCLUDED**: benchmark_full_table_20260220.csv — network-dominated handshakes, no power data

---

## 5. Critical Warnings for LaTeX Embedding (Updated 2026-03-03)

| ID | Severity | Description |
|----|----------|-------------|
| W1 | CRITICAL | bench_ddos_v2.py uses old 2-feature MAVLink-count detectors → label as "lightweight MAVLink-count" not "CIC-IoT-2023" |
| W2 | CRITICAL | DDoS accuracy claims (94.55%, 93.47%, 93.35%, 90.27%) UNVERIFIABLE → cite as "reported by model developers" |
| W3 | HIGH | RPi4 Cortex-A72 has NO ARMv8 Crypto Extensions → AES-256-GCM runs in software-only mode |
| W4 | HIGH | INA219 measures board-level power; idle ~3.32 W (re-run baseline) NOT subtracted unless explicitly stated |
| W5 | HIGH | Section 7 (Scheduler) has ZERO measured runtime data → must be architectural description only |
| W6 | MEDIUM | AEAD does NOT affect handshake duration → data-plane only, separate from HS metrics |
| W7 | LOW | 20/72 suites show power ordering violations in bench_ddos_results → measurement noise |

## 6. Derived Metric Formulas

| Metric | Formula | Unit |
|--------|---------|------|
| Handshake crypto cost | $T_{HS} = t_{keygen} + t_{encaps} + t_{decaps} + t_{sign} + t_{verify}$ | ms |
| Energy per operation | $E_{op} = P_{avg} \times t_{op}$ | µJ |
| Energy per bit (AEAD) | $E_{bit} = P_{avg} \times (t_{enc} + t_{dec}) / (n_{bytes} \times 8)$ | nJ/bit |
| Relative slowdown | $\rho = t_{alg} / t_{fastest}$ | × |
| Rekey overhead fraction | $\Phi(R) = T_{HS} / (R + T_{HS})$ | — |
| DDoS detector overhead | $\Delta = (m_{with} - m_{without}) / m_{without} \times 100$ | % |
| MDEAS cost | $C = w_1 \cdot E_{bit} + w_2 \cdot T_{HS} + w_3 \cdot \Delta T + w_4 \cdot D$ | — |

---

*Analysis complete. Proceed to results-analysis.tex generation.*
