# VTC2026-Fall Paper — Aggressive Build Plan

## Alias System (used everywhere)

### KEM Aliases
| Alias | Algorithm | NIST | Family |
|-------|-----------|------|--------|
| K1 | ML-KEM-512 | L1 | Lattice |
| K3 | ML-KEM-768 | L3 | Lattice |
| K5 | ML-KEM-1024 | L5 | Lattice |
| H1 | HQC-128 | L1 | Code |
| H3 | HQC-192 | L3 | Code |
| H5 | HQC-256 | L5 | Code |
| M1 | McEliece-348864 | L1 | Code |
| M3 | McEliece-460896 | L3 | Code |
| M5 | McEliece-8192128 | L5 | Code |

### DSA Aliases
| Alias | Algorithm | NIST | Family |
|-------|-----------|------|--------|
| D1 | ML-DSA-44 | L1 | Lattice |
| D3 | ML-DSA-65 | L3 | Lattice |
| D5 | ML-DSA-87 | L5 | Lattice |
| F1 | Falcon-512 | L1 | Lattice-NTRU |
| F5 | Falcon-1024 | L5 | Lattice-NTRU |
| S1 | SPHINCS+-128s | L1 | Hash |
| S3 | SPHINCS+-192s | L3 | Hash |
| S5 | SPHINCS+-256s | L5 | Hash |

### AEAD Aliases
| Alias | Algorithm |
|-------|-----------|
| AG | AES-256-GCM |
| CP | ChaCha20-Poly1305 |
| As | Ascon-128a |

### DDoS Aliases
| Alias | Detector |
|-------|----------|
| Ø | No DDoS |
| XG | XGBoost |
| TS | TST (Transformer) |

## Section Structure (5-page target, IEEE 2-column)

### Page 1 (cols 1-2)
- **Abstract** (150 words max)
- **I. Introduction** — slowly introduce: UAV → MAVLink → quantum threat → our solution
  - Right-side bottom: **Figure 1** — System architecture (TikZ)

### Page 2 (cols 3-4)
- **II. Experimental Framework**
  - A. Testbed — RPi4, INA219, Pixhawk, locked 1.8GHz
  - B. Measurement Methodology — N=100, perf_counter_ns, 1kHz power
  - C. Baseline — P_idle = 3.309W (subtract from all power)

### Page 2-3 (cols 4-5)
- **III. Results & Analysis**
  - A. Key Encapsulation Mechanisms
    - Descriptive intro to KEM concept
    - **Table I** — KEM: 9 algos × {keygen, encaps, decaps} → time(µs), ΔP(mW), E(µJ), pk|sk|ct|ss sizes
  - B. Digital Signatures
    - Descriptive intro to DSA concept
    - **Table II** — DSA: 8 algos × {sign, verify} → time(µs), ΔP(mW), E(µJ), pk|sk|sig sizes
  - C. Authenticated Encryption
    - Descriptive intro to AEAD concept
    - **Table III** — AEAD: 3 algos × {enc, dec} × 4 payloads → time(µs), ΔP(mW), E(µJ), throughput(MB/s)

### Page 3-4 (cols 5-7)
  - D. Suite Composition & Handshake
    - Alias definition table (compact, referenced everywhere after)
    - Formula: T_hs = T_keygen + T_sign + T_RTT + T_verify + T_encap + T_RTT + T_decap + 2*T_kdf
    - Suite space: (9+6+9) × 3 = 72 suites
    - **Table IV** — 24 KEM×SIG handshake combos: alias, T_hs(ms), E_hs(mJ), wire(B), RTT, p95
  - E. DDoS Detection Overhead
    - **Table V** — DDoS effect on PQC: {Ø, XG, TS} × key metrics (ΔP, ΔCPU%, ΔT°C, latency, F1)
    - PQC effect on DDoS: combined cost analysis

### Page 4-5 (cols 7-9)
  - F. Graceful Degradation
    - Best combo: K3+D3+CP+XG vs K1+F1+As+Ø
    - Edge cases: M5+S5+AG+TS (worst) — should scheduler avoid?
    - Decision space analysis
    - **Figure 2** — Graceful degradation (pgfplots: grouped bars or radar chart)
    - **Table VI** — Scheduler decision boundaries

### Page 5 (cols 9-10)
- **IV. Discussion**
  - Key findings, feasibility statement, comparison to related work
- **V. Conclusion**
- **References** (20-25 entries, compact)

## Tables Summary (8 tables, 2 figures)
1. Table I: KEM benchmarks (9 rows)
2. Table II: DSA benchmarks (8 rows)
3. Table III: AEAD benchmarks (3×4×2 compressed to ~12 rows)
4. Table IV: Suite handshake (24 rows, aliases)
5. Table V: DDoS impact (3 rows × many columns)
6. Table VI: Scheduler decision space
7. Figure 1: Architecture (TikZ)
8. Figure 2: Graceful degradation (pgfplots)

## Baseline Power
P_idle = 3.309 W (measured)
All ΔP values = P_measured - P_idle
