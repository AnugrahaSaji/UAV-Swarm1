# Structural Analysis of PQC/Embedded Security Benchmarking Papers

> **Analysis date:** 2026-03-03  
> **Scope:** Structure-only analysis — no LaTeX, no copied tables, no replicated phrasing  
> **Purpose:** Inform section planning for IEEE VTC2026-Fall submission

---

## 1. Per-Paper Structural Observations

### 1.1 Paquin, Stebila, Tamvada — PQCrypto 2020
**"Benchmarking post-quantum cryptography in TLS"**  
*Venue: PQCrypto 2020 (Springer LNCS), pp. 72–91 → ~20 pages (full version)*

| Attribute | Observation |
|---|---|
| Section count | ~7 top-level sections |
| Generic structure | Introduction → Background → Experimental Setup → Emulation Results → Real-Network Results → Related Work → Conclusion |
| Benchmarking layers | **Two-tier:** (1) primitive-level parameter comparison, (2) protocol-level (TLS handshake latency under emulated network conditions) |
| Discussion/Limitations | Woven into results sections; no standalone "Limitations" section |
| Contributions stated | Abstract (implicitly), Introduction (explicit bullet list) |
| Figures/Tables | ~8–10 figures (line plots of handshake time vs. latency/loss), ~3–4 tables (algorithm parameters) |
| Energy measurement | **No** |
| Results proportion | ~50–55% of body (two full results sections) |

**Key structural pattern:** Separates emulated results from real-world results as distinct sections. Background covers both PQC algorithm families AND TLS protocol mechanics.

---

### 1.2 Sikeridis, Kampanakis, Devetsikiotis — NDSS 2020
**"Post-Quantum Authentication in TLS 1.3: A Performance Study"**  
*Venue: NDSS 2020 (top-tier security)*

| Attribute | Observation |
|---|---|
| Section count | ~8 top-level sections (numbered I through VIII) |
| Generic structure | Introduction → Background/Related Work → Algorithm Overview → Experimental Methodology → Standalone Benchmarks → Protocol-level Results → Discussion & Alternatives → Conclusion |
| Benchmarking layers | **Three-tier:** (1) standalone cryptographic operations, (2) TLS handshake latency, (3) server throughput under load |
| Discussion/Limitations | **Yes — dedicated Discussion section** covering integration challenges, TCP window tuning, certificate chain alternatives |
| Contributions stated | End of Introduction as numbered list |
| Figures/Tables | ~10–12 figures, ~5–6 tables |
| Energy measurement | **No** |
| Results proportion | ~45–50% of body |

**Key structural pattern:** Has an explicit "Discussion" section that goes beyond results interpretation — covers practical deployment challenges, TCP initcwnd optimization, and mixed-algorithm certificate chains. This is a strong model for papers that want to address "so what?" questions.

---

### 1.3 Sikeridis et al. — CoNEXT 2020
**"Assessing the overhead of post-quantum cryptography in TLS 1.3 and SSH"**  
*Venue: ACM CoNEXT 2020*

| Attribute | Observation |
|---|---|
| Section count | ~7–8 top-level sections |
| Generic structure | Introduction → Background → System Design/Integration → Evaluation Setup → Results (TLS) → Results (SSH) → Related Work → Conclusion |
| Benchmarking layers | **Three-tier:** (1) primitive benchmarks, (2) protocol handshake (TLS + SSH separately), (3) application-level throughput |
| Discussion/Limitations | Integrated into conclusion; brief limitations acknowledgment |
| Contributions stated | Introduction, final paragraph before section break |
| Figures/Tables | ~8–10 figures, ~4–5 tables |
| Energy measurement | **No** |
| Results proportion | ~50% of body (split across two protocols) |

**Key structural pattern:** Evaluates two different protocols (TLS and SSH) side-by-side, using a common primitive benchmarking layer. Results are split by protocol rather than by metric.

---

### 1.4 Sosnowski et al. — CoNEXT 2023
**"The Performance of Post-Quantum TLS 1.3"**  
*Venue: ACM CoNEXT 2023*

| Attribute | Observation |
|---|---|
| Section count | ~7 top-level sections |
| Generic structure | Introduction → Background → Measurement Setup → Results → Analysis/Discussion → Related Work → Conclusion |
| Benchmarking layers | **Three-tier:** (1) algorithm parameters/sizes, (2) handshake performance, (3) real-world Internet measurement |
| Discussion/Limitations | Separate discussion subsection within results |
| Contributions stated | Introduction (explicit enumeration) |
| Figures/Tables | ~6–8 figures (CDFs, bar charts), ~3–4 tables |
| Energy measurement | **No** |
| Results proportion | ~40–45% of body |

**Key structural pattern:** Emphasizes Internet-scale measurement methodology. Uses CDFs prominently for latency distributions.

---

### 1.5 Rosenpass — Whitepaper
**WireGuard + PQC key exchange**  
*Format: Technical whitepaper (not traditional conference paper)*

| Attribute | Observation |
|---|---|
| Section count | ~6–7 major sections |
| Generic structure | Introduction/Motivation → Threat Model → Protocol Design → Security Analysis (formal) → Implementation → Performance/Benchmarks → Future Work |
| Benchmarking layers | **Two-tier:** (1) KEM operation benchmarks, (2) key exchange protocol overhead |
| Discussion/Limitations | Future Work section covers limitations |
| Contributions stated | Introduction |
| Figures/Tables | ~3–5 figures (protocol diagrams, timing), ~2–3 tables |
| Energy measurement | **No** |
| Results proportion | ~20–25% (security analysis dominates) |

**Key structural pattern:** Protocol design and formal security analysis dominate. Benchmarking is compact. Strong emphasis on threat model articulation before any design choices.

---

### 1.6 pqm4 — Kannwischer et al. (ePrint 2019/844)
**"pqm4: Testing and Benchmarking NIST PQC on ARM Cortex-M4"**  
*Venue: ePrint / accompanying paper for the framework*

| Attribute | Observation |
|---|---|
| Section count | ~5–6 top-level sections |
| Generic structure | Introduction → Framework Design → Benchmarking Methodology → Results → Discussion/Observations → Conclusion |
| Benchmarking layers | **Primitive-level only:** keygen/encaps/decaps/sign/verify cycle counts, stack usage, code size — all at the operation level |
| Discussion/Limitations | Brief observations section; limitations are implicit (memory constraints, board specifics) |
| Contributions stated | Introduction, as framework design goals |
| Figures/Tables | ~2–3 figures, **heavy table use** (~4–8 large tables of cycle counts) |
| Energy measurement | **No** (cycle counts serve as proxy) |
| Results proportion | ~60–70% — this is primarily a benchmark-results paper |

**Key structural pattern:** Dominated by tabular results. The framework itself is the contribution, so methodology IS the paper. Uses cycle counts at a fixed frequency (24 MHz) as the primary metric. Tables show min/max/average across multiple executions.

---

## 2. IEEE VTC2026-Fall Format Constraints

| Parameter | Value |
|---|---|
| Conference | IEEE 104th Vehicular Technology Conference |
| Location | Boston, MA, USA |
| Dates | September 6–9, 2026 |
| **Paper length** | **5 pages** without overlength charge |
| Maximum length | **7 pages** (2 extra pages at $100/page) |
| Deadline | **March 7, 2026** (extended) |
| Notification | May 2, 2026 |
| Camera-ready | May 30, 2026 |
| Format | IEEE conference template (two-column) |
| Relevant track | Track 6: "Protocols, Security and Services for Wireless Networks" |
| Presentation | Hybrid (virtual + in-person) |

**Implication for structure:** At 5–7 pages in IEEE two-column, you have ~3,500–5,000 words of text + figures/tables. This forces extreme compression compared to the 15–20 page papers analyzed above.

---

## 3. Consolidated Structural Patterns

### 3.1 Common Section Structure Across PQC Benchmarking Papers

The canonical structure observed across 6 sources (ordered by frequency):

```
I.   Introduction                          [present in 6/6]
II.  Background / Preliminaries            [present in 6/6]
III. System Design / Methodology           [present in 5/6]
IV.  Experimental Setup                    [present in 6/6]
V.   Results / Evaluation                  [present in 6/6]
VI.  Discussion (or integrated)            [standalone in 2/6, integrated in 4/6]
VII. Related Work                          [present in 4/6, sometimes in §II]
VIII.Conclusion                            [present in 6/6]
```

**For a 5-page IEEE VTC paper**, the recommended compression:

```
I.   Introduction (with contributions)     ~0.6 page
II.  Background & Related Work (merged)    ~0.7 page
III. System Architecture                   ~0.8 page
IV.  Evaluation Methodology & Setup        ~0.5 page
V.   Results                               ~1.8 pages
VI.  Discussion & Limitations              ~0.3 page
VII. Conclusion                            ~0.3 page
     References                            ~0.5–0.7 page
```

### 3.2 Typical Figure and Table Counts

| Paper length | Figures | Tables | Total visuals |
|---|---|---|---|
| 20-page full paper (LNCS) | 8–12 | 3–6 | 11–18 |
| 12–15 page conference paper (NDSS/CoNEXT) | 8–10 | 4–6 | 12–16 |
| 5-page IEEE conference paper | **3–5** | **2–3** | **5–7** |

**For 5-page VTC:** Target **4 figures + 2 tables** (6 total visuals). Each figure/table consumes ~0.25–0.4 column-widths of space.

### 3.3 How Results Are Layered

All surveyed papers use a **hierarchical benchmarking model**. The layers observed:

```
Layer 1: Primitive-level benchmarks
         ├── Key generation time/cycles
         ├── Encapsulation/signing time/cycles  
         ├── Decapsulation/verification time/cycles
         ├── Key/ciphertext/signature sizes
         └── Memory footprint (stack, code size)

Layer 2: Protocol-level benchmarks
         ├── Handshake latency (with/without network effects)
         ├── Connection establishment overhead vs. baseline
         ├── Impact of packet fragmentation
         └── Throughput under realistic conditions

Layer 3: System-level benchmarks (when present)
         ├── Server throughput under load
         ├── Real-world page load times
         ├── End-to-end application latency
         └── Energy/power consumption (RARE in surveyed papers)
```

**Paper coverage by layer:**

| Paper | Layer 1 | Layer 2 | Layer 3 |
|---|---|---|---|
| Paquin et al. (PQCrypto'20) | ✓ (parametric) | ✓✓ (primary) | ✓ (page load) |
| Sikeridis et al. (NDSS'20) | ✓✓ | ✓✓ | ✓ (throughput) |
| Sikeridis et al. (CoNEXT'20) | ✓ | ✓✓ | ✓ |
| Sosnowski et al. (CoNEXT'23) | ✓ | ✓✓ | ✓ (Internet-scale) |
| Rosenpass | ✓ | ✓ | — |
| pqm4 | ✓✓✓ (exhaustive) | — | — |

**Recommendation for VTC paper:** Cover Layers 1 + 2 thoroughly. Layer 3 (system-level) adds distinctiveness, especially if it includes **energy measurement** — which NONE of the six surveyed papers cover, making it a differentiator.

### 3.4 Where Mathematical Modeling Appears

| Location | Frequency | What's modeled |
|---|---|---|
| Background section | Common | TLS handshake message flow equations, round-trip formulas |
| Methodology section | Occasional | Overhead calculation formulas, throughput models |
| Results section | Rare | Regression models, prediction equations |
| Standalone Modeling section | Very rare | Only in papers with significant analytical contribution |

**Typical mathematical content in PQC benchmarking papers:**
- Handshake latency as function of RTT and computational overhead: $T_{handshake} = f(RTT, t_{KEM}, t_{sign}, n_{fragments})$
- Overhead ratio: $\Delta = \frac{T_{PQ} - T_{classical}}{T_{classical}} \times 100\%$
- Throughput degradation formulas
- Packet fragmentation threshold calculations

**For VTC:** Keep math lightweight. 2–4 equations max. Place in methodology section. Focus on defining metrics precisely.

### 3.5 How Limitations Are Stated

| Pattern | Papers using it | Description |
|---|---|---|
| Dedicated "Discussion & Limitations" subsection | NDSS'20 | Explicit, thorough, covers deployment challenges |
| Woven into conclusion | PQCrypto'20, CoNEXT'20 | Brief paragraph before future work |
| "Future Work" framing | Rosenpass | Limitations cast as opportunities |
| Implicit in methodology | pqm4 | Constraints stated when describing setup |
| Absent | CoNEXT'23 | Not prominently featured |

**Best practice for VTC (5 pages):** Dedicate 2–3 sentences at the start of the Conclusion to acknowledge limitations explicitly. Frame as: "Our study measures X on platform Y; extending to Z remains future work." This is more honest and reviewers appreciate it.

### 3.6 Best Practices for Plot Types in Systems Benchmarking

Based on the surveyed papers, the most effective visualization choices:

| Plot type | When to use | Papers using it |
|---|---|---|
| **Grouped bar chart** | Comparing discrete algorithms across a metric (latency, throughput, cycles) | All 6/6 |
| **CDF (cumulative distribution)** | Showing latency distributions; reveals tail behavior | Sosnowski'23, Paquin'20 |
| **Line plot (parametric)** | Showing metric vs. a continuous variable (latency vs. packet loss, RTT) | Paquin'20, Sikeridis NDSS'20 |
| **Stacked bar chart** | Decomposing latency into components (crypto, network, overhead) | Sikeridis NDSS'20 |
| **Heatmap / matrix** | Comparing many algorithms × many metrics simultaneously | Rare (more common in survey papers) |
| **Box/violin plot** | Showing measurement variance across repetitions | Increasingly common, not dominant in surveyed set |
| **Table** | Exact numeric comparisons; algorithm parameter listings | All 6/6; pqm4 uses tables as primary format |

**Recommended for a 5-page VTC paper (4 figures + 2 tables):**

1. **Table 1:** Algorithm parameters and sizes (KEM + signature + AEAD) — compact reference
2. **Table 2:** Experimental platform specifications (embedded board details, SW versions)
3. **Figure 1:** Grouped bar chart — primitive-level benchmark comparison (keygen/encaps/sign times)
4. **Figure 2:** Grouped or stacked bar — protocol-level overhead decomposition (handshake components)
5. **Figure 3:** Bar or line chart — energy/power consumption comparison (differentiator!)
6. **Figure 4:** Comparative summary or overhead ratio visualization

**Plot design rules observed in high-quality papers:**
- Always include error bars or confidence intervals
- Use log scale for metrics spanning orders of magnitude (common with PQC sizes)
- Include a classical baseline (e.g., ECDH+ECDSA or AES-GCM) for reference
- Label axes with units; include algorithm security level (NIST Level 1/3/5)
- Prefer grayscale-compatible color schemes for IEEE publication

---

## 4. Structural Recommendations for VTC2026-Fall Submission

### 4.1 Optimal Section Plan (5 pages + up to 2 extra)

For a paper benchmarking PQC + AEAD on embedded platforms with energy measurement:

```
Abstract                                        (~150 words)
I.   Introduction                               (~0.6 page)
     - Motivation: PQ threat to IoT/vehicular
     - Gap: no energy-aware embedded PQC benchmarks
     - Contributions: 3 bullets
     
II.  Background & Related Work                  (~0.7 page)
     - PQC landscape (NIST standards, 1 paragraph)
     - AEAD primitives (1 paragraph)
     - Related benchmarking work (1 paragraph)
     - Key gap identification (1-2 sentences)
     
III. System Design & Methodology                (~0.8 page)
     - Tunnel architecture diagram (Figure 1)
     - Benchmarking approach (layers, metrics defined)
     - Platform description (Table 1)
     - 2-3 equations defining key metrics
     
IV.  Experimental Results                       (~2.0 pages)  ← largest section
     A. Primitive-Level Performance (Figure 2, Table 2)
     B. Protocol-Level Overhead (Figure 3)
     C. Energy Analysis (Figure 4)             ← differentiator
     
V.   Discussion & Limitations                   (~0.3 page)
     - Key findings (2-3 sentences)
     - Practical implications
     - Limitations acknowledgment
     
VI.  Conclusion                                 (~0.3 page)
     - Summary + future directions, 1 paragraph
     
References                                      (~0.5 page, ~15-20 refs)
```

**Total: ~5.2 pages** (fits within 5 without overlength, or comfortably in 7 with expanded results).

### 4.2 What Sets Your Paper Apart

Based on analysis of the surveyed papers, the following elements would be **novel** and strengthen positioning:

1. **Energy measurement on embedded platform** — None of the 6 surveyed papers measure power/energy. This is a clear gap.
2. **AEAD benchmarking alongside KEM/signature** — Most papers focus on KEM+signature; AEAD comparison adds a layer.
3. **Embedded/constrained device focus** — Most papers target server-class or desktop; pqm4 targets Cortex-M4 but without protocol integration.
4. **VPN/tunnel protocol context** — Rosenpass does WireGuard+PQC but without embedded benchmarking or energy analysis.

### 4.3 Reference Distribution Pattern

Observed in surveyed papers (~20–35 references in full-length papers):

| Category | Percentage | For VTC (~18 refs) |
|---|---|---|
| PQC algorithm specifications (NIST, CRYSTALS, etc.) | ~25% | ~4–5 refs |
| Prior benchmarking papers | ~25% | ~4–5 refs |
| Protocol specifications (TLS, WireGuard, etc.) | ~15% | ~3 refs |
| Embedded/IoT security | ~15% | ~3 refs |
| Tools/frameworks (OQS, pqm4, etc.) | ~10% | ~2 refs |
| General crypto/security background | ~10% | ~2 refs |

---

## 5. Summary of Key Findings

| Finding | Evidence strength |
|---|---|
| 7–8 sections is the norm for full papers; 5–6 for short papers | Strong (6/6 papers) |
| Results section is 40–55% of paper body | Strong (5/6 papers) |
| Contributions listed in Introduction as bullets/numbers | Strong (5/6 papers) |
| Standalone Discussion section is optional but valued | Moderate (2/6 standalone) |
| Energy/power measurement is a gap in PQC benchmarking literature | Strong (0/6 papers) |
| Tables are preferred for exact comparisons; bar charts for visual impact | Strong (6/6 papers) |
| Three-tier benchmarking (primitive→protocol→system) is the gold standard | Strong (4/6 papers use ≥2 tiers) |
| Classical baseline inclusion is mandatory for credibility | Strong (6/6 papers) |
| Formal security analysis is separate from benchmarking | Strong (Rosenpass model) |
| CDF plots signal methodological sophistication | Moderate (2/6 papers) |
