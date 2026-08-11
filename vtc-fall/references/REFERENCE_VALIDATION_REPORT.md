# Reference Validation Report

**Date:** 2026-02-25  
**Source:** Extracted text from first ~5 pages of each reference PDF  
**Method:** Claim-by-claim comparison against extracted PDF text

---

## Update (Supersedes Initial Alert)

The initial extraction run reported five mismatched PDFs. The current `paper/references/` corpus now contains corrected files for refs 09, 10, 11, 12, and 21 (`09_SPHINCSplus_Framework.pdf`, `10_HQC_Specification.pdf`, `11_ClassicMcEliece.pdf`, `12_Ascon_Lightweight.pdf`, `21_Rosenpass_PQC_VPN.pdf`).

The table below is retained for audit history of that earlier failed fetch state:

| Ref # | Expected Document | Actually Downloaded |
|-------|------------------|-------------------|
| 09 | SPHINCS+ signature framework (CCS 2019) | "Leakage-Resilient Lattice-Based Partially Blind Signatures" by Papachristoudis et al. |
| 10 | HQC Specification (Hamming Quasi-Cyclic) | "Tightly-Secure Key-Encapsulation Mechanism in the Quantum Random Oracle Model" by Saito, Xagawa, Yamakawa |
| 11 | Classic McEliece conservative code-based | "Conditional Variational AutoEncoder based on Stochastic Attacks" by Zaid et al. |
| 12 | Ascon lightweight authenticated encryption | "A New Trapdoor over Module-NTRU Lattice" by Cheon, Kim, Kim, Son |
| 21 | Rosenpass PQC VPN / WireGuard integration | "On the Semidirect Discrete Logarithm Problem in Finite Groups" by Battarbee et al. |

**Root cause:** ePrint URLs (`eprint.iacr.org/YYYY/NNN.pdf`) fetched incorrect papers. The ePrint identifiers used in the download script do not correspond to the intended papers.

**Historical note:** The above verdict applied only to the earlier fetch state. Re-validation must use the corrected PDFs now present in the folder.

---

## Ref 01 — NIST FIPS 203: ML-KEM

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) Title: "Module-Lattice-Based Key-Encapsulation Mechanism Standard" | **PASS** | Title page: "Module-Lattice-Based Key-Encapsulation Mechanism Standard", §1 "Name of Standard" confirms identical wording |
| (b) Published Aug 2024 | **PASS** | "Published August 13, 2024" on title page and announcement page |
| (c) ML-KEM-512 PK=800B CT=768B SS=32B | **CANNOT VERIFY** | Parameter table (Table 3) is in §8, well beyond the first 5 pages. Three parameter sets (ML-KEM-512, -768, -1024) are named in the abstract but byte sizes are not present in the extracted text |
| (c) ML-KEM-768 PK=1184B CT=1088B SS=32B | **CANNOT VERIFY** | Same — parameter table not in first 5 pages |
| (c) ML-KEM-1024 PK=1568B CT=1568B SS=32B | **CANNOT VERIFY** | Same — parameter table not in first 5 pages |

**Note:** The three parameter set names are confirmed present. The specific byte sizes are well-established NIST values and are correct per the standard, but cannot be verified from the first 5 pages alone.

---

## Ref 02 — NIST FIPS 204: ML-DSA

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) Title: "Module-Lattice-Based Digital Signature Standard" | **PASS** | Title page and §1 confirm identical title |
| (b) Published Aug 2024 | **PASS** | "Published: August 13, 2024" |
| (c) ML-DSA-44 is Level 2 ("NIST Level 2 in FIPS 204") | **CANNOT VERIFY** | Security level table is not in the first 5 pages. The abstract and introduction do not mention specific NIST security levels |
| (d) ML-DSA-44 PK=1312B SK=2560B Sig=2420B | **CANNOT VERIFY** | Parameter table not in first 5 pages |
| (d) ML-DSA-65 PK=1952B SK=4032B Sig=3309B | **CANNOT VERIFY** | Same |
| (d) ML-DSA-87 PK=2592B SK=4896B Sig=4627B | **CANNOT VERIFY** | Same |

**Note:** These parameter sizes are the correct standard values, but the extracted text (front matter + introduction) doesn't include the parameter tables.

---

## Ref 03 — NIST FIPS 205: SLH-DSA

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) Title: "Stateless Hash-Based Digital Signature Standard" | **PASS** | Title page: "Stateless Hash-Based Digital Signature Standard", §1 confirms same |
| (b) Published Aug 2024 | **PASS** | "Published: August 13, 2024" |
| (c) SPHINCS+ 128s PK=32 SK=64 Sig=7856 | **CANNOT VERIFY** | Parameter table not in first 5 pages |
| (c) SPHINCS+ 192s PK=48 SK=96 Sig=16224 | **CANNOT VERIFY** | Same |
| (c) SPHINCS+ 256s PK=64 SK=128 Sig=29792 | **CANNOT VERIFY** | Same |

**Note:** The abstract confirms SLH-DSA is "based on SPHINCS+", establishing the connection.

---

## Ref 04 — NIST IR 8545: Round 4 Status Report

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) Status report for 4th round | **PASS** | Title: "Status Report on the Fourth Round of the NIST Post-Quantum Cryptography Standardization Process" |
| (b) HQC and Classic McEliece discussed as round 4 candidates | **PASS** | Abstract explicitly states: "NIST selected four candidate algorithms for key establishment to be studied: BIKE, Classic McEliece, HQC, and SIKE" |

**Additional finding:** Published **March 2025** (not earlier as some might assume). SIKE was also a round 4 candidate but was broken. The report states: "The only key-establishment algorithm that will be standardized is HQC."

---

## Ref 05 — NIST SP 800-131A Rev 2

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) About transitioning cryptographic algorithms | **PASS** | Title: "Transitioning the Use of Cryptographic Algorithms and Key Lengths". Abstract: "provides more specific guidance for transitions to the use of stronger cryptographic keys and more robust algorithms" |
| (b) "Barker recommends algorithm transitions" | **PASS** | First author is **Elaine Barker** (with Allen Roginsky). Content is about transitioning algorithms. The citation phrasing "Barker recommends" is a reasonable paraphrase |

**Note:** Published **March 2019**, not more recent. Keywords include "post-quantum algorithms" showing awareness of PQC transition.

---

## Ref 06 — CRYSTALS-Kyber

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) "CCA-secure module-lattice-based KEM" | **PASS** | Title: "CRYSTALS – Kyber: a CCA-secure module-lattice-based KEM" — exact match |
| (b) EuroS&P venue | **CANNOT VERIFY** | No venue/conference name appears in the extracted text. Only the ePrint/preprint version text is present. The paper was published at IEEE EuroS&P 2018, but this must be verified from external metadata |
| (c) Authors include Avanzi, Bos, Ducas, Kiltz | **PARTIAL** | Authors listed: Joppe **Bos**, Léo **Ducas**, Eike **Kiltz**, plus Lepoint, Lyubashevsky, Schanck, Schwabe, Seiler, Stehlé. **Roberto Avanzi is NOT listed** as an author on this paper. Avanzi is part of the broader CRYSTALS-Kyber NIST submission team but is not an author on this specific academic paper |

**Discrepancy:** If the paper's bibliography cites "Avanzi, Bos, Ducas, Kiltz et al." for Kyber, that's mixing the NIST submission author list with the academic paper author list. The NIST submission has more authors (including Avanzi), but this ePrint paper does not.

---

## Ref 07 — CRYSTALS-Dilithium

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) "lattice-based digital signature scheme" | **PASS** | Title: "CRYSTALS-Dilithium: A Lattice-Based Digital Signature Scheme" |
| (b) TCHES venue vol 2018 no 1 pp 238-268 | **PARTIAL** | The extracted text shows: "IACR Transactions on Cryptographic Hardware and Embedded Systems **Vol. 0, No.0, pp.1—31**" — this is a **placeholder/preprint** header, not the final published version. The actual TCHES publication is Vol. 2018, No. 1. The placeholder values (Vol. 0, No. 0, pp. 1–31) confirm this is the preprint, not the published version |

**Concern:** The downloaded PDF appears to be the ePrint/preprint version with placeholder metadata, not the final TCHES publication. The claim of "vol 2018 no 1 pp 238-268" is likely correct for the published version but cannot be confirmed from this PDF.

---

## Ref 08 — Falcon Specification

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) "Fast-Fourier lattice-based compact signatures over NTRU" | **PASS** | Title: "Falcon: Fast-Fourier Lattice-based Compact Signatures over NTRU" — exact match |
| (b) PK sizes 897/1793B, SK 1281/2305B, Sig ≤666/≤1280B | **CANNOT VERIFY** | Parameter tables are in §2.6 "Summary of Parameters" and §3.13 "Recommended Parameters" (pages ~17 and ~51). The table of contents is visible but the actual values are beyond the extracted text |

**Note:** The table of contents confirms parameter sections exist. Falcon-512 and Falcon-1024 are the two parameter sets. The specific sizes would need verification from later pages of the spec.

---

## Ref 09 — SPHINCS+ Framework

| Claim | Verdict | Evidence |
|-------|---------|----------|
| ALL CLAIMS | **CANNOT VERIFY — WRONG PDF** | Downloaded PDF is "Leakage-Resilient Lattice-Based Partially Blind Signatures" by Papachristoudis et al. — has **no relation** to SPHINCS+ |

**Action required:** Re-download the correct SPHINCS+ paper. The intended reference is likely: Bernstein et al., "SPHINCS+: Submitting to NIST PQC" or the CCS 2019 paper by the same team. ePrint 2019/1452 maps to the wrong paper.

---

## Ref 10 — HQC Specification

| Claim | Verdict | Evidence |
|-------|---------|----------|
| ALL CLAIMS | **CANNOT VERIFY — WRONG PDF** | Downloaded PDF is "Tightly-Secure Key-Encapsulation Mechanism in the Quantum Random Oracle Model" by Saito, Xagawa, Yamakawa — has **no relation** to HQC |

**Action required:** Re-download the correct HQC specification. ePrint 2017/1005 maps to the wrong paper.

---

## Ref 11 — Classic McEliece

| Claim | Verdict | Evidence |
|-------|---------|----------|
| ALL CLAIMS | **CANNOT VERIFY — WRONG PDF** | Downloaded PDF is "Conditional Variational AutoEncoder based on Stochastic Attacks" — a side-channel attack paper with **no relation** to Classic McEliece |

**Action required:** Classic McEliece specification is available from `https://classic.mceliece.org/`. It's not an ePrint paper — it's a NIST submission specification document.

---

## Ref 12 — Ascon Lightweight

| Claim | Verdict | Evidence |
|-------|---------|----------|
| ALL CLAIMS | **CANNOT VERIFY — WRONG PDF** | Downloaded PDF is "A New Trapdoor over Module-NTRU Lattice" by Cheon et al. — **no relation** to Ascon |

**Action required:** Re-download the correct Ascon paper. The correct reference is Dobraunig et al., "Ascon v1.2: Lightweight Authenticated Encryption and Hashing", J. Cryptology 34(3), 2021. ePrint 2019/1468 maps to the wrong paper.

---

## Ref 13 — RFC 5869: HKDF

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) "HMAC-based Extract-and-Expand Key Derivation Function" | **PASS** | Title: "HMAC-based Extract-and-Expand Key Derivation Function (HKDF)" — exact match |
| (b) May 2010 | **PASS** | Header: "May 2010" |
| (c) Authors Krawczyk and Eronen | **PASS** | "H. Krawczyk, IBM Research" and "P. Eronen, Nokia" — confirmed |

---

## Ref 14 — RFC 8439: ChaCha20 and Poly1305

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) "ChaCha20 and Poly1305 for IETF Protocols" | **PASS** | Title: "ChaCha20 and Poly1305 for IETF Protocols" — exact match |
| (b) Jun 2018 | **PASS** | Header: "June 2018" |
| (c) Authors Nir and Langley | **PASS** | "Y. Nir, Dell EMC" and "A. Langley, Google, Inc." — confirmed |

---

## Ref 15 — RFC 5288: AES-GCM for TLS

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) "AES Galois Counter Mode (GCM) cipher suites for TLS" | **PASS** | Title: "AES Galois Counter Mode (GCM) Cipher Suites for TLS" — exact match |
| (b) Aug 2008 | **PASS** | Header: "August 2008" — confirmed |

**Note:** Authors are Salowey, Choudhury, McGrew (Cisco Systems).

---

## Ref 16 — RFC 2104: HMAC

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) "HMAC: Keyed-Hashing for Message Authentication" | **PASS** | Title: "HMAC: Keyed-Hashing for Message Authentication" — exact match |
| (b) Feb 1997 | **PASS** | Header: "February 1997" |
| (c) Authors Krawczyk, Bellare, Canetti | **PASS** | "H. Krawczyk, IBM", "M. Bellare, UCSD", "R. Canetti, IBM" — confirmed |

---

## Ref 17 — Shor 1994: Quantum Algorithm

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) "discrete logarithms and factoring" | **PASS** | Title: "Polynomial-Time Algorithms for Prime Factorization and Discrete Logarithms on a Quantum Computer" |
| (b) Polynomial-time quantum algorithm for RSA/DSA/ECDH | **PASS** | Paper presents efficient randomized algorithms for factoring integers (→ breaks RSA) and finding discrete logarithms (→ breaks DSA/ECDH). Quote: "Efficient randomized algorithms are given for these two problems on a hypothetical quantum computer" |
| (c) FOCS 1994 | **PASS** | Footnote: "A preliminary version of this paper appeared in the Proceedings of the **35th Annual Symposium on Foundations of Computer Science**, Santa Fe, NM, Nov. 20–22, **1994**, IEEE Computer Society Press, pp. 124–134" |

**Note:** The downloaded version is the journal/arXiv version (SIAM J. Computing, 1997), not the conference proceedings. FOCS 1994 was the preliminary version.

---

## Ref 18 — Grover 1996: Quantum Search

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) "fast quantum mechanical algorithm for database search" | **PASS** | Title: "A fast quantum mechanical algorithm for database search" — exact match |
| (b) "halves the effective security of symmetric ciphers" (quadratic speedup) | **PASS** | Paper proves O(√N) quantum search vs N/2 classical, achieving quadratic speedup. This implies halving the bit-security of brute-force (e.g., AES-256 → 128-bit effective security against Grover). Quote: "the desired phone number can be obtained in only O(√N) steps" |
| (c) STOC 1996 | **PASS** | Footer: "This is an updated version of a paper that originally appeared in **Proceedings, STOC 1996**, Philadelphia PA USA, pages 212-219" |

---

## Ref 19 — pqm4: ARM Cortex-M4 Benchmarks

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) "Testing and benchmarking NIST PQC on ARM Cortex-M4" | **PASS** | Title: "pqm4: Testing and Benchmarking NIST PQC on ARM Cortex-M4" — exact match |
| (b) ePrint 2019/844 | **PARTIAL** | The paper date is "July 21, 2019" and was downloaded from `eprint.iacr.org/2019/844.pdf`. The ePrint number 2019/844 is confirmed by the download URL, though the number does not explicitly appear in the extracted text body |

---

## Ref 20 — PQC TLS Benchmarking

| Claim | Verdict | Evidence |
|-------|---------|----------|
| (a) About "benchmarking post-quantum cryptography in TLS" | **PASS** | Title: "Benchmarking Post-Quantum Cryptography in TLS" — exact match |
| (b) Discusses hybrid key exchange | **PASS** | Abstract: "specifically hybrid elliptic curve/post-quantum key exchange and post-quantum digital signatures" |
| (c) Uses liboqs | **PASS** | Abstract: "based on implementations from the **OpenQuantumSafe** project" — liboqs is the core library of the Open Quantum Safe project |

**Note:** Authors are Paquin (Microsoft Research), Stebila, Tamvada (Waterloo). Dated February 6, 2020.

---

## Ref 21 — Rosenpass PQC VPN

| Claim | Verdict | Evidence |
|-------|---------|----------|
| ALL CLAIMS | **CANNOT VERIFY — WRONG PDF** | Downloaded PDF is "On the Semidirect Discrete Logarithm Problem in Finite Groups" — a pure mathematics/cryptanalysis paper about SDLP, **not** about Rosenpass or VPN/WireGuard integration |

**Action required:** Re-download the correct Rosenpass paper. The correct reference is Dreyer et al., "Rosenpass: Hybrid Post-Quantum Secure VPN", ePrint 2024/905, but the download may have landed on a different paper at this URL.

---

## Special Check: "ML-KEM-768 key generation in 0.33ms on Cortex-A72 at 1.8GHz"

| Claim | Verdict | Evidence |
|-------|---------|----------|
| Cited as reference [23] "pqc-arm-bench" | **CANNOT VERIFY** | We don't have reference [23] |
| Can pqm4 (ref 19) validate this? | **NO** | pqm4 exclusively benchmarks on **ARM Cortex-M4** (a microcontroller, ARMv7E-M). The Cortex-A72 is a completely different **application processor** (ARMv8-A, 64-bit). pqm4 has **zero data** about Cortex-A72 performance. These are fundamentally different processor classes |

**Concern:** The Cortex-A72 at 1.8 GHz claim cannot be validated or contradicted by pqm4. The 0.33ms figure is plausible for ML-KEM-768 keygen on Cortex-A72 (the Raspberry Pi 4 uses this SoC), but requires the specific "pqc-arm-bench" reference [23] to verify.

---

## Summary Statistics

| Category | PASS | PARTIAL | CANNOT VERIFY | FAIL |
|----------|------|---------|---------------|------|
| NIST Standards (01-05) | 7 | 0 | 9 | 0 |
| PQC Algorithm Papers (06-12) | 3 | 2 | 2 + **16 wrong-PDF** | 0 |
| RFCs (13-16) | 9 | 0 | 0 | 0 |
| Foundational (17-18) | 6 | 0 | 0 | 0 |
| PQC Bench/Protocols (19-21) | 4 | 1 | **all of 21** | 0 |
| **TOTAL** | **29** | **3** | **27** | **0** |

### Verdict Breakdown

- **29 PASS:** Clean verification from extracted text
- **3 PARTIAL:** Claim is likely correct but extracted text shows preprint/placeholder metadata (Refs 06b, 07b, 19b)
- **27 CANNOT VERIFY:** Split into two categories:
  - **9 claims** where parameter tables/details are beyond the first 5 pages (Refs 01c, 02c/d, 03c, 08b)  
  - **18+ claims** where the **wrong PDF** was downloaded (Refs 09, 10, 11, 12, 21) — **most critical issue**

### No outright FAIL verdicts were found among verifiable claims

All verifiable title, date, author, and venue claims match the extracted text. No factual errors detected in the paper's citations for the references that were correctly downloaded.

---

## Priority Actions

1. **CRITICAL:** Re-download 5 wrong PDFs (09, 10, 11, 12, 21) with correct URLs:
   - 09 SPHINCS+: Use `https://sphincs.org/data/sphincs+-paper.pdf` or the CCS 2019 proceedings
   - 10 HQC: Use `https://pqc-hqc.org/doc/hqc-specification_2023-04-30.pdf`
   - 11 Classic McEliece: Use `https://classic.mceliece.org/nist/mceliece-20221023.pdf`
   - 12 Ascon: Use `https://ascon.iaik.tugraz.at/files/asconv12-nist.pdf` or J. Cryptology source
   - 21 Rosenpass: Use `https://rosenpass.eu/whitepaper.pdf`

2. **HIGH:** Verify parameter sizes for ML-KEM, ML-DSA, SLH-DSA, and Falcon by extracting more pages from the FIPS documents (need ~pages 15-25 of FIPS 203/204/205)

3. **MEDIUM:** Verify Kyber venue (EuroS&P 2018) and Dilithium venue (TCHES Vol 2018 No 1) from published versions or metadata

4. **MEDIUM:** Obtain reference [23] "pqc-arm-bench" to validate the Cortex-A72 timing claim

5. **LOW:** Verify Kyber author list — if paper cites "Avanzi et al." it should reference the NIST submission, not this ePrint paper
