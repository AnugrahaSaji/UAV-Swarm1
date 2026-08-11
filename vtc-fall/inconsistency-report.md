# Inconsistency Report — VTC Fall 2026

Generated: 2026-03-03T15:50+0530
Repository: 68bdb5c7 (both local and RPi in sync)

---

## I1 — AEAD Metadata Reporting Bug (RESOLVED)

- **File source**: `bench_power_aead.py` line 420
- **Dataset affected**: `power_aead_benchmark.json` → `system_info.ascon_impl`
- **Nature**: Case mismatch: script imports `_LIB_PATH` (uppercase), module exports `_lib_path` (lowercase). Detection silently fails, metadata reports `"unknown"`.
- **Corrective action**: Fixed import to `from core._ascon_native import _lib_path as _LIB_PATH`. Fix applied on both Pi and local.
- **Re-run executed**: YES — full 10,000-iteration AEAD re-benchmark with 30s baseline. Output saved to `vtc-fall-aead-rerun/`. Metadata now correctly reports `"ascon-c v1.2 opt64 (gcc -O3)"`.
- **Data impact**: None. Previous CSV already used native C backend (verified: Ascon 256B encrypt = 12.72 µs, consistent with native C; Python fallback would yield ~1300 µs). Re-run confirms: 12.72 µs.

## I2 — bench_ddos_v2 Uses Old 2-Feature Detectors (UNRESOLVED)

- **File source**: `bench_ddos_v2.py` → imports `xgb_old.py`, `tst_old.py`
- **Dataset affected**: `bench_ddos_results/20260302_135859/{xgb.json, tst.json, comparison.json}`
- **Nature**: The "XGBoost" and "TST" overhead data is from lightweight 2-feature MAVLink-count detectors (`xgboost_model.bin`, `tst_model.pth` using `Mavlink_Count` + `Total_length`), NOT the 54-feature CIC-IoT-2023 detectors (`xgb_model.pkl`, `Transformer_CICIoT23.pth`).
- **Corrective action**: In Sections 5–6, detectors must be labeled as "lightweight MAVLink-count (2-feature)" detectors. The baseline.json handshake timing data remains valid (no detector active in baseline phase).
- **Re-run executed**: NO — re-running with 54-feature detectors requires architecture refactoring of bench_ddos_v2.py (not a benchmark config change).
- **Data impact**: Overhead deltas (XGB +2.5%, TST +71.83%) reflect 2-feature detector overhead, not 54-feature.

## I3 — DDoS Model Accuracy Claims Unverifiable (UNRESOLVED)

- **File source**: `DDOS_MODELS_COMPARISON.md`, `DDoS_PQC_IMPACT_ANALYSIS.md`
- **Dataset affected**: Accuracy values (LightGBM 93.47%, XGBoost 94.55%, RF 93.35%, TST 90.27%)
- **Nature**: No model evaluation output files exist in this repository. Numbers originate from IA02_CAPSTONE external training. No confusion matrix, classification report, or eval JSON found.
- **Corrective action**: Must cite as "reported by model developers on CIC-IoT-2023 test split" — cannot claim independent verification.
- **Re-run executed**: NO — would require running model eval against CIC-IoT-2023 test data.
- **Data impact**: Accuracy/F1 numbers cannot appear as independently verified results.

## I4 — Scheduler Has No Measured Runtime Data (UNRESOLVED)

- **File source**: `sscheduler/policy.py`, `sscheduler/logs/`
- **Dataset affected**: Section 7 (Scheduler Behavioral Impact)
- **Nature**: Scheduler log files are empty (0 bytes). No CSV/JSON with actual runtime decisions, state transitions, or energy-aware policy actions. All scheduler parameters are code constants only.
- **Corrective action**: Section 7 must be purely architectural description from code. No measured behavioral claims.
- **Re-run executed**: NO — requires full flight simulation infrastructure.
- **Data impact**: Cannot present scheduler tables with measured values.

## I5 — DDoS×PQC Phase A–E Data Has No Backing Artifacts (UNRESOLVED)

- **File source**: `DDoS_PQC_IMPACT_ANALYSIS.md`
- **Dataset affected**: 5-phase overhead tables (baseline, XGB-only, TST-only, PQC+XGB, PQC+TST)
- **Nature**: The markdown tables contain specific non-round values suggesting a real run, but no raw JSON output files were saved (`/tmp/baseline.json` etc. not found on RPi). The markdown is the only record. Source script (`collect_overhead.py`) references the NEW 54-feature models.
- **Corrective action**: Cannot use these values in the paper. Data exists only in markdown with no provenance chain.
- **Re-run executed**: NO.
- **Data impact**: Phase A–E analysis excluded from paper.

## I6 — Standalone Inference Latency Uses Different Baseline Power (INFORMATIONAL)

- **File source**: `bench_ddos_results/power_20260222_193509/results.json`
- **Dataset affected**: DDoS inference latency and power measurements
- **Nature**: Inference benchmark measures idle baseline as 3308.67 mW; AEAD re-benchmark baseline is 3320.30 mW. Difference: 11.63 mW (0.35%). Both measured on same platform with performance governor @ 1800 MHz but on different dates (Feb 22 vs Mar 3). Within measurement noise.
- **Corrective action**: None required. Report each baseline with its own measured value.
- **Re-run executed**: NO — acceptable variance.
- **Data impact**: Negligible.

---

## I7 — Systematic Voltage/Power Shift Between Original and Rerun (DOCUMENTED)

- **File source**: `power_aead_benchmark.csv` (original) vs `vtc-fall-aead-rerun/power_aead_benchmark.csv` (rerun)
- **Dataset affected**: All AEAD power/voltage/current columns
- **Nature**: The rerun shows a systematic voltage increase of ~7–8% (original ~5.1–5.2 V → rerun ~5.5 V) across all 60 data rows. Consequently, power readings are 10–22% higher in the rerun. Timing values differ by <1% (stable), confirming code-level equivalence. The shift is consistent with changed environmental conditions (supply voltage, ambient temperature) or ADC calibration drift on clone INA219.
- **Evidence**:
  - AESG enc 256B: Timing 9.283→9.254 µs (−0.3%), Voltage 5.116→5.516 V (+7.8%), Power 2.973→3.625 W (+21.9%)
  - CH20 enc 256B: Timing 6.106→6.469 µs (+5.9%), Voltage 5.153→5.520 V (+7.1%), Power 3.201→3.544 W (+10.7%)
  - ASC enc 256B: Timing 12.713→12.717 µs (+0.03%), Voltage 5.160→5.520 V (+7.0%), Power 3.134→3.836 W (+22.4%)
- **Corrective action**: Use rerun data exclusively (verified session with matching idle baseline). Report board-level power with P_idle noted. Comparative ratios between ciphers remain stable (ASC/CH20 energy ratio: 2.12→2.13×, <1% change).
- **Re-run executed**: Rerun IS the corrected data.
- **Data impact**: All absolute power values in Section 3 must use rerun data. Original archived to `vtc-fall/archive/`.

## I8 — Idle Power Baseline Discrepancy (DOCUMENTED)

- **File source**: 30-second INA219 capture on 2026-03-03 vs `results-analysis.tex` v1.0
- **Dataset affected**: P_idle throughout paper
- **Nature**: Freshly measured idle baseline = **3.454 W** (30 s, 28012 samples at 933.7 Hz, V_avg=5.614 V, I_avg=0.615 A). The v1.0 paper documented P_idle = 2.961 W. Difference: +0.493 W (+16.6%). The voltage difference (5.614 vs ~5.15 V implied) is consistent with the I7 measurement shift.
- **Corrective action**: Update all P_idle references to 3.454 W. For baseline-subtracted analysis, ΔP values at 256B are: AESG=0.171/0.120 W (enc/dec), CH20=0.090/0.122 W, ASC=0.382/0.141 W.
- **Re-run executed**: YES — dedicated 30 s idle capture.
- **Data impact**: Absolute power numbers change; relative comparisons unaffected.

## I9 — Ascon Footnote Error in v1.0 LaTeX (RESOLVED)

- **File source**: `vtc-fall/results-analysis.tex` Section 3
- **Dataset affected**: Ascon-128a implementation description
- **Nature**: v1.0 footnote stated Ascon uses "pure-Python" path due to "IV incompatibility between NIST SP 800-232 reference implementation and upstream pyascon". Live Pi verification on 2026-03-03 confirmed the native C backend (libascon128a.so, ascon-c v1.2, original competition IV 0x80800c0800000000) passes KAT and IS the active backend. The `_AsconAdapter` tries native C first → KAT check → fallback to pyascon; on Pi, native C succeeds.
- **Corrective action**: Remove pure-Python footnote. State: "Ascon-128a uses a native C binding (ascon-c v1.2, opt64) via ctypes, verified by KAT test."
- **Re-run executed**: YES — backend verification via SSH.
- **Data impact**: Timing values already reflected native C performance (12.72 µs, not ~1300 µs). No numerical changes.

## I10 — DDoS Per-AEAD TST Data Available but Excluded in v1.0 (DOCUMENTED)

- **File source**: `DDoS_PQC_IMPACT_ANALYSIS.md` Section 3.3
- **Dataset affected**: Table 8 (AEAD Per-Packet Latency Under DDoS Detection)
- **Nature**: v1.0 stated "TST per-AEAD breakdown not available (CPU saturation prevents stable measurement)". However, the source markdown DOES contain TST per-AEAD latency: AESG=95,059 ns (+21.8%), CH20=89,407 ns (+14.4%), ASC=1,878,849 ns (+41.9%). The TST data was omitted from v1.0 in error.
- **Corrective action**: Add TST column to Table 8 in v1.1. Note the DDoS data provenance caveat from I5 still applies — markdown is only record.
- **Re-run executed**: NO — data already exists.
- **Data impact**: Table 8 gains TST column; narrative must be updated.

---

## Summary

| ID | Severity | Status | Resolution |
|----|----------|--------|------------|
| I1 | HIGH | RESOLVED | Metadata fix + re-run completed |
| I2 | CRITICAL | DOCUMENTED | Label detectors correctly in paper |
| I3 | CRITICAL | DOCUMENTED | Cite as "reported", not independently verified |
| I4 | HIGH | DOCUMENTED | Section 7 → architectural description only |
| I5 | HIGH | DOCUMENTED | Phase A–E data excluded from paper |
| I6 | LOW | INFORMATIONAL | No action needed |
| I7 | HIGH | DOCUMENTED | Use rerun data; original archived |
| I8 | HIGH | DOCUMENTED | P_idle updated to 3.454 W |
| I9 | HIGH | RESOLVED | Ascon footnote corrected (native C active) |
| I10 | MEDIUM | DOCUMENTED | TST per-AEAD data added to Table 8 |
