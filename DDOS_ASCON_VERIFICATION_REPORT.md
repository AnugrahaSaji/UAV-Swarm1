# DDoS + Ascon AEAD — Full Verification Report

Generated: verification-first, code-backed, reference-checked.

---

## Part A: Ascon AEAD Implementation

### Bugs Found & Fixed

| # | Severity | Location | Description | Status |
|---|----------|----------|-------------|--------|
| A1 | **CRITICAL** | `core/suites.py` `_probe_aead_support()` | Probe only tries `import pyascon`, never `import ascon._ascon`. Module-level chain in `aead.py` tries `pyascon → ascon._ascon → None`. Probe falsely reports Ascon as **unavailable** on systems without native C but with pip `ascon`. | **FIXED** in all 3 copies |
| A2 | INFO | `core/_ascon_native.c` | Native C compiled against NIST SP 800-232 reference (IV=`0x00001000808c0001`). pip `ascon` uses original IV=`0x80800c0800000000`. KAT correctly detects mismatch, falls back to pyascon. Native C is effectively dead code (always fails KAT). | By design — documented |
| A3 | LOW | `core/handshake.py` | HKDF outputs 64 bytes (32+32). Ascon-128a silently truncates to 16 (`key[:16]`). Wastes 16 bytes per key direction. | Known limitation |

### Verified Correct

| Item | Evidence |
|------|----------|
| KAT value `7a834e6f09210957067b10fd831f0078` | Computed via `ascon._ascon.ascon_encrypt(bytes(range(16)), bytes(range(16)), b"", b"", "Ascon-128a")` — **MATCH** |
| Nonce padding 12→16 bytes | `_AsconAdapter.encrypt()` zero-pads + `_build_nonce(nonce_len=16)` — redundant but correct |
| Import chain `pyascon → ascon._ascon → None` | `import ascon._ascon` succeeds, has `ascon_encrypt`/`ascon_decrypt` |
| Roundtrip encrypt/decrypt | Tested through `Sender`/`Receiver` pipeline: 10 packets, tamper detection, wrong-AAD detection — all pass |
| Wire format: header(22) ‖ ciphertext ‖ tag(16) | Verified from `Sender.encrypt()` and `Receiver.decrypt()` |

---

## Part B: DDoS Detection — Verification Against References

### B1. TransformerIDS (tst_model.pth) — `confirmed` FAKE TRANSFORMER

| Claim (DDOS_MODELS_COMPARISON.md) | Reality (code-verified) | Status |
|---|---|---|
| "Transformer encoder" | `seq_len=1` → attention over **single token** → degenerates to identity. **Functionally a 3-layer MLP**, not a transformer. | **MISLEADING** |
| `nhead=4` | GitGenius92 source: `nhead=8`. But with `seq_len=1`, nhead has **zero effect** (verified: both produce identical output from same weights). | **IRRELEVANT** — attention is degenerate |
| 6 classes: DDoS, DoS, Mirai, Recon, Spoofing, Unknown | Checkpoint confirms. **BUT** GitGenius92 original classes were: Benign, DDoS, DoS, Mirai, Recon, Web Attack. Our model was **retrained with different labels**. | **INCONSISTENT** with source |
| "Source: GitGenius92/IDS_transformer" | GitHub repo is a Streamlit UI app with flashy CSS. No training code, no evaluation, no paper. Model is `Linear(46→512)→unsqueeze(1)→TransformerEncoder→mean(dim=1)→Linear(512→6)`. | **CONFIRMED** from GitHub |
| Accuracy 90.27% | **UNVERIFIED** — no evaluation script, no confusion matrix, no test set saved. | **UNVERIFIABLE** |
| 1,605,126 parameters | Counted from state_dict: **CORRECT** | **VERIFIED** |
| 46 features (CIC-IoT-2023) | `input_fc.weight: (512, 46)` — **CORRECT** | **VERIFIED** |
| 6.1 MB model size | `tst_model.pth` = 6,429,649 bytes ≈ 6.1 MB — **CORRECT** | **VERIFIED** |

**Critical verdict**: Self-attention with `seq_len=1` computes `softmax([q·k/√d_k])=[1.0]`, output = V. The "Transformer" layer reduces to `out_proj(V) + residual`, which is just a linear projection + skip. Claiming this is a "Transformer" in a paper is scientifically misleading.

### B2. Sklearn Models (LightGBM, XGBoost, RandomForest)

| Claim | Checkpoint Reality | Status |
|---|---|---|
| LightGBM: n_estimators=1000 | `model.n_estimators=1000` | **VERIFIED** |
| LightGBM: max_depth=10 | `model.max_depth=5` | **WRONG** (doc says 10, actual 5) |
| LightGBM: 93.47% accuracy | No eval script/results found | **UNVERIFIED** |
| XGBoost: n_estimators=1000, max_depth=5 | Both confirmed | **VERIFIED** |
| XGBoost: 94.55% accuracy | No eval script/results found | **UNVERIFIED** |
| RandomForest: n_estimators=200, max_depth=10 | n_estimators=200 ✓, max_depth=**15** (not 10) | **max_depth WRONG** |
| RandomForest: 93.35% accuracy | No eval script/results found | **UNVERIFIED** |
| All: 54 features, 15 classes | Confirmed from bundles | **VERIFIED** |
| 15-class label mapping | All 3 models: identical mapping with CIC-IoT-2023 attack names | **VERIFIED** |

### B3. Benchmark Overhead Numbers

| Claim | Reality | Status |
|---|---|---|
| "XGB overhead 2.5% mean" (comparison.json) | `bench_ddos_v2.py` uses `xgb_old.py` (2-feature, binary, old system) | **WRONG SYSTEM** |
| "TST overhead 71.83% mean" (comparison.json) | `bench_ddos_v2.py` uses `tst_old.py` (1-feature, seq_len=400, old TSTPlus) | **WRONG SYSTEM** |
| Pi 4 Model B @ 1800 MHz, perf governor | `environment.json` confirms | **VERIFIED** |
| 72 cipher suites × 10s | `config.json` confirms | **VERIFIED** |
| INA219 power sensor | `config.json`: `power_sensor_available: true` | **VERIFIED** |

**Critical verdict**: ALL overhead numbers in `bench_ddos_results/` measure the **OLD 2-feature system** (`xgb_old.py`, `tst_old.py`), NOT the current 54-feature/15-class system (`ddos/xgb.py`, `ddos/lgbm.py`). The documented inference times (7.42ms XGB, 10.72ms TST) are from a DIFFERENT measurement context (standalone bench) than the overhead benchmark.

### B4. 99.98% Accuracy Claim

| Claim | Source | Evidence | Status |
|---|---|---|---|
| "When evaluated specifically on IoT-relevant network-layer attacks... 99.98% accuracy" | DDoS_PQC_IMPACT_ANALYSIS.md | **ZERO** — no script, no confusion matrix, no eval log | **FABRICATED or UNVERIFIABLE** |

### B5. Feature Count Discrepancy

| Source | Count | Details |
|---|---|---|
| `ddos/features.py` FEATURE_NAMES | 54 | Master list for LGBM/XGB/RF |
| `ddos/models/selected_features.txt` | 56 | Includes `dst_port`, `ece_flag_number`, `cwr_flag_number` extras |
| GitGenius92 feature_extractor.py | 46 | Per-packet features from CIC-IoT-2023 schema |
| TST model input | 46 | `input_fc.weight: (512, 46)` |
| CIC-IoT-2023 paper (Neto et al. 2023) | 46 via MI | "46 features selected through mutual information" |

### B6. Cascade Design Inconsistency

| Document | Cascade |
|---|---|
| DDOS_MODELS_COMPARISON.md | 4-tier: LightGBM → XGBoost → RF → TST |
| SOTA_DDOS_COMPARISON.md | 3-tier: LightGBM → RF → TST |
| ddos/lgbm.py docstring | "Tier 1 in the 3-tier cascade: LightGBM → RF → TST" |
| sscheduler/detector_manager.py | Supports all 4: LGBM, RF, XGBOOST, TST |

### B7. RealTST (tst_real_model.pth) — Trained But NOT Deployed

| Item | Value | Verified |
|---|---|---|
| Architecture | `RealTST(c_in=46, seq_len=32, d_model=128, n_heads=8, n_layers=3, d_ff=256)` | From checkpoint metadata |
| Parameters | 1,458,953 | Counted from state_dict |
| Classes | 9: Benign, BruteForce, DDoS, DoS, Malware, Mirai, Recon, Spoofing, Web | From label_encoder |
| Training | CIC-IoT-2023 xxsmall sample, 17/20 epochs, best F1=0.9879 at epoch 10 | From training logs |
| Deployment | **NOT USED** — `ddos/tst.py` loads TransformerIDS, not RealTST | Code inspection |

---

## Summary of Actions Required

### Must Fix Before Paper Submission
1. **Replace TransformerIDS with RealTST** in `ddos/tst.py` — currently using fake seq_len=1 model
2. **Re-run overhead benchmark** with current detectors (`ddos/xgb.py`, `ddos/lgbm.py`, `ddos/tst.py`) via `bench_ddos_v2.py`
3. **Produce reproducible accuracy numbers** — run evaluation scripts on held-out test sets with confusion matrices
4. **Fix max_depth claims** — LightGBM=5 not 10, RandomForest=15 not 10
5. **Remove 99.98% accuracy claim** — no evidence exists
6. **Harmonize cascade documentation** — decide 3-tier or 4-tier, update all docs

### Ascon (Already Fixed)
- ✅ `_probe_aead_support()` now mirrors module-level import chain
- ✅ Fixed in `core/suites.py`, `rpi-5/core/suites.py`, `uav-camera/core/suites.py`
- ✅ Verified via E2E test through Sender/Receiver pipeline
