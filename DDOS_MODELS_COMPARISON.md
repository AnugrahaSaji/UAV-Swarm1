# DDoS Detection Models — Comprehensive Comparison & Architecture

## Executive Summary

The secure-tunnel project employs a **4-tier adaptive DDoS detection cascade** running
on Raspberry Pi 4 (Cortex-A72 @ 1.8 GHz, 4 GB RAM). Three sklearn models are trained on the
same CIC-IoT-2023 dataset with identical feature pipelines (54 features, 15 attack classes)
but use fundamentally different learning paradigms — gradient boosting (leaf-wise vs level-wise)
and bagging. A fourth model, a **Transformer encoder** (TST), trained on the same dataset
with 46 core features and 6 coarse classes, adds a neural-network perspective for
**ensemble diversity through both algorithmic and architectural diversity**.

| Metric | LightGBM | XGBoost | RandomForest | TST (Transformer) |
|---|---|---|---|---|
| **Accuracy** | 93.47% | 94.55% | 93.35% | 90.27% |
| **F1-macro** | 0.937 | 0.947 | 0.935 | 0.80 |
| **Inference (Pi4)** | 6.72 ms | 7.42 ms | 74.68 ms | 10.72 ms |
| **Power delta** | +999 mW | +951 mW | +594 mW | +1973 mW |
| **Energy/inference** | 29.0 mJ | 31.7 mJ | 291.4 mJ | 56.7 mJ |
| **Model size** | 13.5 MB | 32.7 MB | 198.3 MB | 6.1 MB |

---

## 1. Storyline: Why Three Models?

### The Problem
A PQC-encrypted UAV tunnel must detect DDoS attacks **on-board** (no cloud round-trip)
while keeping CPU and power overhead low enough to preserve flight-critical MAVLink telemetry
at 10 Hz. A single model faces a dilemma:
- **Fast models** (LightGBM) may produce false positives that trigger unnecessary mitigation.
- **Accurate models** (XGBoost) cost more per inference.
- **Robust models** (RandomForest) are too slow for always-on duty.

### The Solution: Energy-Aware Escalation Cascade

```
      ┌─────────────────────────────────────┐
      │        MDEAS Scheduler (Axis 3)      │
      │     energy-aware threat escalation   │
      └────────────┬────────────────────────┘
                   │
    ┌──────────────▼──────────────────┐
    │  Tier 1: LightGBM (Always-On)   │  ← 6.7 ms, +1.0 W
    │  Leaf-wise GBDT, 1000 trees     │
    │  Runs every MAVLink cycle       │
    └──────────────┬──────────────────┘
                   │ anomaly detected?
    ┌──────────────▼──────────────────┐
    │  Tier 2: XGBoost (Confirmer)    │  ← 7.4 ms, +1.0 W
    │  Level-wise GBDT, 1000 trees    │
    │  Different growth ⟹ different   │
    │  decision boundaries            │
    └──────────────┬──────────────────┘
                   │ both agree?
    ┌──────────────▼──────────────────┐
    │  Tier 3: RandomForest (Arbiter) │  ← 75 ms, +0.6 W
    │  Bagging, 200 independent trees │
    │  Decorrelated from boosting     │
    └──────────────┬──────────────────┘
                   │ ambiguous? neural perspective needed?
    ┌──────────────▼──────────────────┐
    │  Tier 4: TST (Deep Arbitrator)  │  ← 10.7 ms, +2.0 W
    │  Transformer encoder, 1.6M      │
    │  params, 6 coarse classes       │
    │  Orthogonal neural-net view     │
    └─────────────────────────────────┘
```

**Why this ordering works:**

1. **LightGBM** uses **leaf-wise (best-first)** tree growth — it splits the leaf with the
   largest loss reduction first. This produces deeper, more specialized trees that are fast
   to evaluate (fewer nodes visited per sample). At 6.7 ms it fits within a single 10 Hz
   MAVLink cycle.

2. **XGBoost** uses **level-wise (breadth-first)** tree growth — it expands all leaves at
   each depth before going deeper. This produces shallower, more balanced trees that
   generalize slightly better (94.55% accuracy vs 93.47%). When LightGBM flags a threat,
   XGBoost provides a **second opinion from a different inductive bias** at negligible extra
   latency (+0.9 ms).

3. **RandomForest** uses **bagging** — 200 independent trees trained on bootstrap samples.
   Its errors are **uncorrelated** with the boosting models (boosting errors are correlated
   because each tree corrects the previous). When boosting and bagging agree, the detection
   is highly reliable. Used only for confirmed or ambiguous cases.

4. **TST (Transformer)** uses a **Transformer encoder** with learned positional embedding.
   It is a completely different model family (neural network vs tree ensemble). With
   `d_model=512`, `nhead=4`, 1 encoder layer, and 1.6M parameters, it provides an
   **orthogonal decision surface** that no tree-based model can replicate. Though its
   90.27% accuracy is lower than the sklearn models, it classifies into 6 coarse classes
   (DDoS, DoS, Mirai, Recon, Spoofing, Unknown) which can break ties when tree models
   disagree on fine-grained attack types. At 10.7 ms it is still real-time capable.

**The key novelty**: No existing PQC UAV/IoT project combines multiple ML classifiers
(tree ensembles + Transformer) with an energy-aware scheduler that adapts detection
depth based on threat level and battery state. This is the first **runtime adaptive
multi-model DDoS detection** for post-quantum encrypted drone telemetry.

---

## 2. Training Procedure

All three models were trained on the **CIC-IoT-2023** dataset using an identical pipeline
from the IA02_CAPSTONE project.

### 2.1 Dataset
- **Source**: CIC-IoT-2023 (Canadian Institute for Cybersecurity)
- **Total samples**: 3,415,181 (after deduplication and cleaning)
- **Train/Test split**: 80/20 stratified
  - Train: 2,732,144 samples (with Gaussian noise injection for robustness)
  - Test: 683,037 samples (clean, no augmentation)

### 2.2 Feature Engineering
- **54 features** selected via mutual information classification (`mutual_info_classif`)
- Feature categories:
  - **Flow statistics**: `flow_duration`, `Rate`, `Srate`, `Drate`, `IAT`
  - **Packet size metrics**: `Tot sum`, `Min`, `Max`, `AVG`, `Std`, `Tot size`
  - **TCP flags**: `fin_flag_number`, `syn_flag_number`, `rst_flag_number`, `ack_flag_number`, etc.
  - **Protocol indicators**: `TCP`, `UDP`, `ICMP`, `HTTP`, `HTTPS`, `DNS`, `SSH`, etc.
  - **Two-stream metrics**: `Magnitude`, `Radius`, `Covariance`, `Variance`, `Weight`
  - **MQTT indicators**: 8 features (zero-filled for MAVLink/UDP traffic)

### 2.3 Preprocessing
1. **Label encoding**: Sorted unique labels → integer mapping (15 classes)
2. **StandardScaler**: Fit on training set only, applied to both train and test
3. **Gaussian noise injection**: Applied to training features for regularization
4. Scaler saved inside each model pickle as a bundle: `{'model', 'scaler', 'features', 'mapping'}`

### 2.4 Label Mapping (15 Classes)

| ID | Attack Type | Test Samples |
|---|---|---|
| 0 | ACK Fragmentation | 59,728 |
| 1 | Benign Traffic | 70,422 |
| 2 | CONNECT Attack | 22,884 |
| 3 | DELAY CONNECT Attack | 34,568 |
| 4 | ICMP Flood | 58,043 |
| 5 | ICMP Fragmentation | 73,295 |
| 6 | PSHACK Flood | 50,722 |
| 7 | RST/FIN Flood | 53,029 |
| 8 | SYN Flood | 52,550 |
| 9 | Subscription Attack | 31,543 |
| 10 | SynonymousIP Flood | 41,355 |
| 11 | TCP ACK Flood | 31,520 |
| 12 | UDP Flood | 47,117 |
| 13 | UDP Fragmentation | 35,785 |
| 14 | WILL Payload Attack | 20,476 |

---

## 3. Model Specifications

### 3.1 LightGBM (Tier 1 Sentinel)

| Parameter | Value |
|---|---|
| Algorithm | Gradient Boosted Decision Trees (leaf-wise/best-first) |
| `boosting_type` | `gbdt` |
| `n_estimators` | 1000 |
| `learning_rate` | 0.01 |
| `num_leaves` | 7 |
| `max_depth` | 10 |
| `reg_alpha` | 5.0 |
| `reg_lambda` | 10.0 |
| `class_weight` | balanced |
| `objective` | `multiclass` |
| Model file | `lgbm_model.pkl` (13.5 MB) |
| Training time | 995 s |

### 3.2 XGBoost (Tier 2 Confirmer)

| Parameter | Value |
|---|---|
| Algorithm | Gradient Boosted Decision Trees (level-wise/depth-first) |
| `objective` | `multi:softmax` |
| `n_estimators` | 1000 |
| `learning_rate` | 0.01 |
| `max_depth` | 5 |
| `reg_alpha` | 5.0 |
| `reg_lambda` | 10.0 |
| `class_weight` | balanced (via `sample_weight`) |
| `tree_method` | `hist` |
| Model file | `xgb_model.pkl` (32.7 MB) |
| Training time | 3394 s |

### 3.3 RandomForest (Tier 3 Arbitrator)

| Parameter | Value |
|---|---|
| Algorithm | Bagging (bootstrap aggregating) |
| `n_estimators` | 200 |
| `max_depth` | 10 |
| `max_features` | `sqrt` |
| `min_samples_leaf` | 5 |
| `class_weight` | balanced |
| `criterion` | `gini` |
| Model file | `rf_model.pkl` (198.3 MB) |
| Training time | 1417 s |

### 3.4 TST — Transformer Encoder (Tier 4 Deep Arbitrator)

| Parameter | Value |
|---|---|
| Algorithm | Transformer Encoder (attention-based) |
| Architecture | `Linear(46→512) → TransformerEncoder → Linear(512→6)` |
| `input_dim` | 46 (CIC-IoT-2023 core, no MQTT features) |
| `d_model` | 512 |
| `nhead` | 4 |
| `num_layers` | 1 |
| `dim_feedforward` | 512 |
| `num_classes` | 6 (DDoS, DoS, Mirai, Recon, Spoofing, Unknown) |
| Parameters | 1,605,126 |
| Preprocessing | StandardScaler (bundled in checkpoint) |
| Model file | `tst_model.pth` (6.1 MB) |
| Training dataset | CIC-IoT-2023 (7,845,673 samples) |
| Training epochs | 7 (batch_size=2048) |
| Source | GitGenius92/IDS_transformer |

**Note on nhead bug**: The original deployment repo uses `nhead=8`, but the training
notebook (GitGenius92/Transformer_Model) uses `nhead=4`. Since `MultiHeadAttention`
reshapes Q/K/V based on `nhead`, using the wrong value produces incorrect inference.
Our wrapper uses the correct `nhead=4`.

---

## 4. Classification Performance

### 4.1 Overall Accuracy & F1

| Model | Accuracy | F1-macro | F1-weighted | Features | Classes |
|---|---|---|---|---|---|
| **XGBoost** | **94.55%** | **0.947** | 0.944 | 54 | 15 |
| LightGBM | 93.47% | 0.937 | 0.934 | 54 | 15 |
| RandomForest | 93.35% | 0.935 | 0.934 | 54 | 15 |
| TST (Transformer) | 90.27% | 0.80 | 0.89 | 46 | 6 |

XGBoost is the most accurate overall. LightGBM and RandomForest are within ~1% of each other.
TST has lower metrics partly because it uses 46 features (no MQTT) and classifies into 6
coarse categories vs 15 fine-grained classes. Its value is architectural diversity, not
raw accuracy.

### 4.2 Per-Class F1 Scores

| Attack Type | LightGBM | XGBoost | RandomForest |
|---|---|---|---|
| ACK Fragmentation | 0.99 | 0.99 | **1.00** |
| Benign Traffic | **1.00** | **1.00** | **1.00** |
| CONNECT Attack | 0.94 | 0.94 | 0.93 |
| DELAY CONNECT Attack | 0.96 | 0.96 | 0.95 |
| ICMP Flood | 0.87 | 0.87 | 0.87 |
| ICMP Fragmentation | 0.91 | 0.91 | 0.91 |
| PSHACK Flood | **1.00** | **1.00** | **1.00** |
| RST/FIN Flood | **1.00** | **1.00** | **1.00** |
| SYN Flood | 0.78 | **0.88** | 0.78 |
| Subscription Attack | **1.00** | **1.00** | **1.00** |
| SynonymousIP Flood | 0.79 | 0.83 | 0.79 |
| TCP ACK Flood | 0.98 | 0.98 | 0.98 |
| UDP Flood | 0.93 | 0.93 | 0.93 |
| UDP Fragmentation | 0.89 | **0.90** | **0.90** |
| WILL Payload Attack | **1.00** | **1.00** | **1.00** |

**Key observations:**
- All three sklearn models achieve **perfect detection** (F1 = 1.00) for Benign, PSHACK Flood,
  RST/FIN Flood, Subscription Attack, and WILL Payload Attack.
- XGBoost significantly outperforms the others on **SYN Flood** (0.88 vs 0.78) and
  **SynonymousIP Flood** (0.83 vs 0.79) — these are the hardest attack types.
- The models are complementary: where one struggles, the others may provide correct
  predictions through different decision boundaries.

### 4.3 TST Per-Class Performance (6 Coarse Classes)

The Transformer model groups CIC-IoT-2023 attacks into 6 broader categories:

| Class | Precision | Recall | F1-Score | Test Samples |
|---|---|---|---|---|
| **DDoS** | 0.93 | 0.95 | **0.94** | 476,327 |
| **DoS** | 0.64 | 0.71 | 0.67 | 261,504 |
| **Mirai** | 0.98 | 1.00 | **0.99** | 410,458 |
| **Recon** | 0.81 | 0.51 | 0.62 | 148,449 |
| **Spoofing** | 0.55 | 0.90 | 0.69 | 202,117 |
| **Unknown** | 0.95 | 0.82 | 0.88 | 70,280 |

Tested on 1,569,135 samples (20% of 7.8M). Macro avg F1=0.80, Weighted avg F1=0.89.
Mirai and DDoS achieve near-perfect detection. DoS and Spoofing are harder to distinguish
at this coarse granularity.

---

## 5. Raspberry Pi 4 Benchmark Results

**Platform**: Raspberry Pi 4 Model B (Cortex-A72 @ 1.8 GHz, 4 GB RAM)  
**OS**: Debian 12, Linux 6.12.47+rpt-rpi-v8 (aarch64)  
**Power sensor**: INA219 (Adafruit, I2C bus 1, 0x40, 0.1 Ω shunt)  
**Duration**: 15 seconds per phase, 100 warmup iterations  
**Governor**: performance (1800 MHz locked)

### 5.1 Inference Latency

| Model | Mean | Median | P95 | P99 | Min | Max | σ | Throughput |
|---|---|---|---|---|---|---|---|---|
| **LightGBM** | **6.72 ms** | **6.77 ms** | 7.06 ms | 8.59 ms | — | — | — | **148.6/s** |
| XGBoost | 7.42 ms | 7.30 ms | 8.45 ms | 9.52 ms | — | — | — | 134.6/s |
| RandomForest | 74.68 ms | 73.78 ms | 87.77 ms | 102.63 ms | — | — | — | 13.4/s |
| TST (Transformer) | 10.72 ms | 10.11 ms | 13.16 ms | 26.12 ms | — | — | — | 93.2/s |

**Speedup ratios** (relative to fastest):
- LightGBM: **1.0x** (reference)
- XGBoost: 1.1x slower
- TST: **1.6x** slower
- RandomForest: **11.1x** slower

**Interpretation**: LightGBM and XGBoost are both fast enough for real-time 10 Hz MAVLink
processing (6.7 ms and 7.4 ms fit within the 100 ms MAVLink cycle). TST at 10.7 ms is also
real-time capable (fits within one MAVLink cycle). RandomForest at 75 ms is usable only as
an occasional confirmer, not always-on.

### 5.2 Power Consumption

| Phase | Avg Power | Δ Baseline | Current | Voltage |
|---|---|---|---|---|
| **BASELINE (idle)** | **3309 mW** | — | 638 mA | 5.11 V |
| + LightGBM | 4308 mW | **+999 mW** | — | — |
| + XGBoost | 4259 mW | **+951 mW** | — | — |
| + RandomForest | 3902 mW | **+594 mW** | — | — |
| + TST (Transformer) | 5282 mW | **+1973 mW** | — | — |

**Interpretation**: LightGBM and XGBoost draw similar power (~+1 W above baseline)
because they both saturate one CPU core at ~37% utilization with continuous inference.
RandomForest draws less continuous power (+0.6 W) because each inference takes 75 ms with
idle gaps between inferences — but **per-inference energy is 10x higher**.
TST draws the most power (+2.0 W) because PyTorch Transformer inference saturates
all four CPU cores at 93% utilization (BLAS matrix operations), but per-inference energy
is only 2x that of LightGBM due to the additional throughput.

### 5.3 Energy Per Inference

| Model | Energy/Inference | Total Energy (15s) | Iterations |
|---|---|---|---|
| **LightGBM** | **29.0 mJ** | 64,636 mJ | 2,229 |
| XGBoost | 31.7 mJ | 63,905 mJ | 2,019 |
| TST (Transformer) | 56.7 mJ | 79,238 mJ | 1,398 |
| RandomForest | 291.4 mJ | 58,579 mJ | 201 |

**Key insight**: RandomForest costs **10.0x more energy per inference** than LightGBM.
TST costs **2.0x more** — a reasonable premium for a completely orthogonal neural-network
perspective. The cascade architecture ensures TST is invoked only when needed.

### 5.4 CPU & System Impact

| Phase | CPU avg | CPU peak | Temperature | RAM (RSS) |
|---|---|---|---|---|
| BASELINE | 2.2% | 12.2% | 53.1 °C | 212.1 MB |
| + LightGBM | 36.9% | 51.0% | 57.9 °C | 245.9 MB |
| + XGBoost | 37.0% | 51.0% | 57.9 °C | 338.3 MB |
| + RandomForest | 25.6% | 34.0% | 56.5 °C | 674.1 MB |
| + TST (Transformer) | **93.0%** | **95.1%** | **63.8 °C** | 474.6 MB |

**Observations**:
- XGBoost uses +93 MB more RAM than LightGBM (338 vs 246 MB) due to larger model size.
- RandomForest uses +462 MB above baseline (674 MB) — the 198 MB model unpickles into
  200 scikit-learn `DecisionTree` objects stored in memory.
- **TST saturates all four CPU cores** (93% avg) because PyTorch uses OpenBLAS for the
  `Linear` and `MultiHeadAttention` matrix multiplications. This makes it the highest
  thermal load (+10.7 °C above baseline) but still within Pi4 limits.
- TST RAM (475 MB) sits between XGBoost and RandomForest — PyTorch runtime + 1.6M params.

---

## 6. Cascade Decision Logic

The MDEAS scheduler (Axis 3: threat level) controls model activation:

```
State: LEVEL_NONE
  └─ Threat score = 0 → no detection running, minimum power
  └─ Transition: network anomaly counter > threshold → LEVEL_LGBM

State: LEVEL_LGBM (always-on sentinel)
  └─ LightGBM runs on every flow window
  └─ If prediction == BenignTraffic → stay in LEVEL_LGBM
  └─ If prediction == attack type with confidence > τ₁ → LEVEL_XGBOOST

State: LEVEL_XGBOOST (confirmer)
  └─ XGBoost runs on the same flow window
  └─ If both LightGBM and XGBoost agree on attack type → CONFIRMED
  └─ If they disagree → LEVEL_RF (arbitration needed)
  └─ If no attack for N consecutive windows → back to LEVEL_LGBM

State: LEVEL_RF (deep arbitrator)
  └─ RandomForest provides third vote
  └─ Majority vote across all three models determines classification
  └─ Additional cooldown before de-escalation
```

**Confidence threshold**: All models use temperature-scaled softmax (T = 1.5) instead of
raw softmax to prevent overconfident predictions. The temperature smooths the probability
distribution so that models report lower confidence when uncertain.

---

## 7. Model Comparison Summary

### 7.1 At a Glance

| Dimension | LightGBM | XGBoost | RandomForest | TST (Transformer) |
|---|---|---|---|---|
| **Role** | Sentinel | Confirmer | Arbitrator | Deep Arbitrator |
| **Algorithm** | Leaf-wise GBDT | Level-wise GBDT | Bagging | Transformer Encoder |
| **Complexity** | 1000 trees | 1000 trees | 200 trees | 1.6M params |
| **Accuracy** | 93.47% | **94.55%** | 93.35% | 90.27% |
| **F1-macro** | 0.937 | **0.947** | 0.935 | 0.80 |
| **Latency (mean)** | **6.72 ms** | 7.42 ms | 74.68 ms | 10.72 ms |
| **Latency (P99)** | **8.59 ms** | 9.52 ms | 102.63 ms | 26.12 ms |
| **Power delta** | +999 mW | +951 mW | **+594 mW** | +1973 mW |
| **Energy/infer** | **29.0 mJ** | 31.7 mJ | 291.4 mJ | 56.7 mJ |
| **CPU usage** | 36.9% | 37.0% | **25.6%** | 93.0% |
| **RAM** | **246 MB** | 338 MB | 674 MB | 475 MB |
| **Model size** | **13.5 MB** | 32.7 MB | 198.3 MB | 6.1 MB |
| **Load time** | **0.27 s** | 0.78 s | 0.78 s | **0.05 s** |
| **Features** | 54 | 54 | 54 | 46 |
| **Classes** | 15 | 15 | 15 | 6 |

### 7.2 Strengths & Weaknesses

**LightGBM** — Best for always-on duty
- ✅ Fastest inference (6.72 ms)
- ✅ Smallest model (13.5 MB)
- ✅ Lowest RAM footprint (246 MB)
- ⚠️ Weakest on SYN Flood (F1 = 0.78) and SynonymousIP Flood (F1 = 0.79)

**XGBoost** — Best accuracy
- ✅ Highest accuracy (94.55%) and F1-macro (0.947)
- ✅ Best on hard attacks: SYN Flood (F1 = 0.88), SynonymousIP Flood (F1 = 0.83)
- ✅ Still real-time capable (7.42 ms)
- ⚠️ 2.4x larger model than LightGBM

**RandomForest** — Best decorrelation
- ✅ Uncorrelated errors with boosting models (bagging vs boosting)
- ✅ Lowest continuous power draw (+594 mW)
- ✅ Most stable predictions (lowest CPU peak 34%)
- ⚠️ 11.1x slower than LightGBM
- ⚠️ Highest RAM (674 MB) and model size (198 MB)
- ⚠️ Weakest on same attacks as LightGBM (SYN Flood, SynonymousIP Flood)

**TST (Transformer)** — Orthogonal neural-network perspective
- ✅ Smallest model file (6.1 MB) and fastest loading (0.05 s)
- ✅ Completely different architecture: attention-based neural network vs tree ensembles
- ✅ Real-time capable (10.72 ms)
- ✅ Excels at Mirai (F1 = 0.99) and DDoS (F1 = 0.94)
- ⚠️ Highest power draw (+1973 mW) due to BLAS-saturated CPU cores (93%)
- ⚠️ Coarser classification (6 classes vs 15)
- ⚠️ Lower overall accuracy (90.27%) than tree models
- ⚠️ P99 tail latency (26 ms) has occasional spikes

---

## 8. Benchmark Reproduction

### On the Raspberry Pi 4:

```bash
cd ~/secure-tunnel/ddos
~/nenv/bin/python bench_power_inference.py --duration 10 --warmup 100
```

### Options:

```
--duration N    Seconds per phase (default: 10)
--warmup N      Warmup iterations per model (default: 100)
--models M [M]  Subset of models: LightGBM XGBoost RandomForest TST
```

### Output:

Results are saved as JSON in `bench_ddos_results/power_YYYYMMDD_HHMMSS/results.json`.

### Requirements:

- Python 3.11+ with: `lightgbm`, `xgboost`, `scikit-learn`, `pandas`, `numpy`
- For TST: `torch` (PyTorch 2.x)
- INA219 sensor: `adafruit-circuitpython-ina219` or `pi-ina219`
- Model files in `ddos/models/`: `lgbm_model.pkl`, `xgb_model.pkl`, `rf_model.pkl`, `tst_model.pth`

---

## 9. Files Reference

| File | Purpose |
|---|---|
| `ddos/lgbm.py` | LightGBM live detector (Tier 1) |
| `ddos/xgb.py` | XGBoost live detector (Tier 2) |
| `ddos/rf.py` | RandomForest live detector (Tier 3) |
| `ddos/tst.py` | Transformer live detector (Tier 4) |
| `ddos/features.py` | FlowFeatureExtractor (54 CIC-IoT-2023 features) |
| `ddos/severity.py` | SeverityReporter (JSON output to `/tmp/ddos_severity.json`) |
| `ddos/bench_inference.py` | Inference-only latency benchmark |
| `ddos/bench_power_inference.py` | Comprehensive power + inference benchmark |
| `ddos/models/lgbm_model.pkl` | LightGBM model bundle (13.5 MB) |
| `ddos/models/xgb_model.pkl` | XGBoost model bundle (32.7 MB) |
| `ddos/models/rf_model.pkl` | RandomForest model bundle (198.3 MB) |
| `ddos/models/tst_model.pth` | Transformer checkpoint (6.1 MB) |
| `sscheduler/detector_manager.py` | Detector process lifecycle manager |
