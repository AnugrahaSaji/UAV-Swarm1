# State-of-the-Art DDoS Detection for IoT Edge Devices
## Comparison with Our XGBoost & TST Detectors on Raspberry Pi 4

**Date**: 2026-02-11  
**Platform**: Raspberry Pi 4 Model B Rev 1.5 (ARM Cortex-A72, 4×1.8 GHz, 4 GB RAM)  
**Context**: Post-quantum cryptographic drone tunnel with live DDoS detection  

---

## 1. Our Current System

| Property | XGBoost (`xgb.py`) | TST Transformer (`tst.py`) |
|---|---|---|
| **Model** | XGBClassifier (scikit-learn API) | TSTPlus (tsai/PyTorch) |
| **Features** | 2 (MAVLink pkt count + total bytes) | 2 (same, but 400-window sequence) |
| **Window** | 0.6 s × 5 lookback = 3 s context | 0.6 s × 400 lookback = 240 s context |
| **Inference** | ~40–60 μs | ~100 ms |
| **Accuracy** | ~90% | Higher (not formally benchmarked) |
| **CPU overhead** | +0.02 pp (negligible) | −0.01 pp (within noise) |
| **Duty cycle** | 0.06 ms / 600 ms = 0.01% | 100 ms / 600 ms = 17% (one core) |
| **Dependencies** | scapy, xgboost | scapy, torch, tsai |
| **RAM** | ~50 MB | ~300–500 MB |
| **Capture** | scapy sniffing, MAVLink v2 magic byte 0xfd | Same |

### Strengths
- ✅ Near-zero latency overhead on PQC tunnel handshakes
- ✅ Domain-specific (MAVLink-aware packet counting)
- ✅ XGBoost is extremely lightweight for edge
- ✅ TST provides deep temporal pattern detection

### Weaknesses
- ❌ Only 2 features → limited discrimination capability
- ❌ 90% accuracy is below SOTA (most achieve 95–99.9%)
- ❌ TST requires 240 s (4 min) to fill initial buffer
- ❌ No unsupervised/anomaly component → can't detect zero-day attacks
- ❌ Static models → no concept drift adaptation
- ❌ No ONNX optimization → leaving ARM NEON performance on the table

---

## 2. SOTA Algorithms Comparison

### 2.1 Tree-Based Models (Drop-in Replacements)

| Algorithm | Paper/Source | Dataset | Accuracy/F1 | Inference (RPi4 est.) | RAM |
|---|---|---|---|---|---|
| **Our XGBoost** | — | Custom MAVLink | 90% | 40–60 μs | ~50 MB |
| **LightGBM** | Yang et al., LCCDE, IEEE GLOBECOM 2022 | CICIDS2017 | **99.6% F1** | **25–45 μs** | ~40 MB |
| **CatBoost** | Yang et al., LCCDE, IEEE GLOBECOM 2022 | CICIDS2017 | **99.5% F1** | ~50–80 μs | ~60 MB |
| **Extra Trees** | Yang et al., MTH-IDS, IEEE IoT-J 2022 | CICIDS2017 | **99.3% F1** | ~80–120 μs | ~80 MB |
| **Random Forest** | Breno et al., DDoS-Detector 2025 | CICDDoS2019 | **100% F1** | ~100–200 μs | ~200 MB |
| **LCCDE Ensemble** | Yang et al., XGB+LGB+CatBoost leaders | CICIDS2017 | **99.7% F1** | ~100–150 μs | ~150 MB |

**Key insight**: LightGBM is ~20–40% faster than XGBoost with typically higher accuracy. It's a **direct drop-in replacement** (`lgb.LGBMClassifier` has the same API pattern).

**GitHub**: [Western-OC2-Lab/Intrusion-Detection-System-Using-Machine-Learning](https://github.com/Western-OC2-Lab/Intrusion-Detection-System-Using-Machine-Learning) ★561

### 2.2 Deep Learning Models

| Algorithm | Paper/Source | Dataset | Accuracy/F1 | Inference (RPi4 est.) | RAM |
|---|---|---|---|---|---|
| **Our TST** | — | Custom MAVLink | >90% | 100 ms | ~400 MB |
| **1D-CNN (tiny, 3 layers)** | Yang & Shami, IEEE ICC 2022 | CICIDS2017 | **99.25% F1** | **5–15 ms** | ~20 MB |
| **GRU (64 units, seq=5)** | Various 2023–2025 | CICIDS2017 | **97–99% F1** | **2–5 ms** | ~10 MB |
| **LSTM (128 units, seq=10)** | Various 2023–2025 | CICIDS2017 | **97–99% F1** | 5–10 ms | ~20 MB |
| **DNN (3-layer, 128-64-32)** | Rahul et al., ICCCNT 2018 | KDDCup'99 | **98%+ F1** | 1–3 ms | ~5 MB |
| **VGG16 Transfer** | Yang & Shami, ICC 2022 | Car-Hacking | 99.9% F1 | 200–500 ms ❌ | ~500 MB ❌ |

**Key insight**: A small **GRU (64 units, 5-window lookback)** could replace TST at **2–5 ms** instead of 100 ms — that's **20–50× faster** with similar accuracy.

**GitHub**: [Western-OC2-Lab/Intrusion-Detection-System-Using-CNN-and-Transfer-Learning](https://github.com/Western-OC2-Lab/Intrusion-Detection-System-Using-CNN-and-Transfer-Learning) ★198  
**GitHub**: [rahulvigneswaran/Intrusion-Detection-Systems](https://github.com/rahulvigneswaran/Intrusion-Detection-Systems) ★292

### 2.3 Unsupervised / Anomaly Detection

| Algorithm | Paper/Source | Dataset | Accuracy/F1 | Inference (RPi4 est.) | RAM |
|---|---|---|---|---|---|
| **Autoencoder (32-16-32)** | Chianfa et al., SBRC 2026 | Real ISP NetFlow | **99.92% acc, 0.85 F1** | **0.5–2 ms** | ~10 MB |
| **Isolation Forest** | Chianfa et al. | Real ISP NetFlow | 0.25 F1 | ~1 ms | ~30 MB |
| **One-Class SVM** | Chianfa et al. | Real ISP NetFlow | 0.63 F1 | ~5 ms | ~50 MB |
| **LOF** | Chianfa et al. | Real ISP NetFlow | 0.29 F1 | ~2 ms | ~50 MB |

**Key insight**: Autoencoders clearly dominate unsupervised DDoS detection. Train on **normal traffic only** → no attack labels needed. Use reconstruction error as anomaly score. Can detect **zero-day attacks** that supervised models miss.

**GitHub**: [MuriloChianfa/isp-ddos-auto-detector](https://github.com/MuriloChianfa/isp-ddos-auto-detector)

### 2.4 Lightweight CNN for DDoS (LIDS)

| Property | Detail |
|---|---|
| **Paper** | LIDS, Wiley Security & Privacy, 2025 (DOI: 10.1002/spy2.70148) |
| **Model** | Conv1D → BatchNorm → ReLU → MaxPool → FC → Dropout |
| **Datasets** | CICDDoS2019, BoT-IoT, TON_IoT |
| **Features** | PCA-reduced from full flow features |
| **Inference** | ~5–15 ms (estimated on RPi4 with CPU) |
| **Key feature** | Class-weighted CrossEntropyLoss + AdamW + early stopping |
| **Explainability** | SHAP KernelExplainer for per-class feature importance |

**GitHub**: [vanlalruata/LIDS](https://github.com/vanlalruata/LIDS-A-Novel-Light-weight-Intrusion-Detection-System-for-DDoS-Attacks)

### 2.5 Online Learning & Concept Drift

| Algorithm | Paper/Source | Approach | Inference | Key Benefit |
|---|---|---|---|---|
| **PWPAE Ensemble** | Yang et al., IEEE GLOBECOM 2021 | ADWIN + Adaptive RF + Hoeffding Trees | **<1 ms** | Self-adapts to attack pattern changes |
| **River Hoeffding Tree** | River library | Incremental tree learning | **<0.5 ms** | Learns from each sample, no retraining |
| **Streaming Random Patches** | River library | Online ensemble | **<1 ms** | Robust to concept drift |

**Key insight**: Your XGBoost is a **static model** trained once. Attack patterns evolve. ADWIN drift detection + online model fallback is essential for production.

**GitHub**: [Western-OC2-Lab/PWPAE-Concept-Drift-Detection-and-Adaptation](https://github.com/Western-OC2-Lab/PWPAE-Concept-Drift-Detection-and-Adaptation) ★219

### 2.6 Production-Grade IPS (Reference Architecture)

| System | Description | RPi Tested? | Stars |
|---|---|---|---|
| **Slips** | Behavioral ML + 40+ threat intel feeds + Zeek | ✅ Yes (dedicated RPi docs) | 857 |
| **Suricata** | Rule-based NIDS/IPS, signature matching | ✅ Yes (ARM builds) | 7000+ |

**GitHub**: [stratosphereips/StratosphereLinuxIPS](https://github.com/stratosphereips/StratosphereLinuxIPS)

---

## 3. ONNX Runtime Optimization (Free Speedup)

Converting existing models to ONNX and running with ONNX Runtime on ARM provides free acceleration via NEON SIMD instructions.

| Model | Native Python | ONNX Runtime | Speedup |
|---|---|---|---|
| XGBoost | 40–60 μs | **15–25 μs** | 2–3× |
| LightGBM | 25–45 μs | **10–20 μs** | 2–3× |
| GRU (small) | 5–10 ms | **1–3 ms** | 3–5× |
| 1D-CNN (tiny) | 10–20 ms | **3–8 ms** | 2–3× |
| Autoencoder | 1–3 ms | **0.5–1 ms** | 2× |
| TST (our current) | 100 ms | **25–40 ms** | 2.5–4× |

```bash
pip install onnxmltools onnxruntime  # ARM64 wheels available
```

---

## 4. Feature Engineering Gap (Biggest Accuracy Win)

Our system uses only **2 features**: `mavlink_count` and `total_bytes` per 0.6 s window.

SOTA systems typically use **20–80 features**. Adding even 5–10 more features can dramatically improve accuracy:

| Feature | Category | Computation Cost | Expected Impact |
|---|---|---|---|
| Packet inter-arrival time (mean, std) | Temporal | Low | High |
| Bytes per packet ratio | Volumetric | Negligible | Medium |
| SYN/ACK/FIN flag counts | Protocol | Low | High |
| Source IP entropy (Shannon) | Statistical | Medium | Very High |
| Destination port entropy | Statistical | Medium | High |
| Unique source IP count | Flow | Low | High |
| Packet size variance | Volumetric | Low | Medium |
| TCP window size stats | Protocol | Low | Medium |
| MAVLink message type distribution | Domain-specific | Low | Very High |
| Non-MAVLink packet ratio | Domain-specific | Negligible | Very High |

**Priority features**: Source IP entropy + packet inter-arrival time std + non-MAVLink packet ratio. These three alone could push accuracy from 90% → 96%+.

---

## 5. Recommended Architecture: 3-Model Ensemble

```
┌─────────────────────────────────────────────────┐
│              scapy Packet Capture                │
│         (MAVLink v2 magic byte 0xfd)             │
└──────────────┬──────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────┐
│          Feature Extractor (0.6 s window)        │
│  mavlink_count, total_bytes, iat_std, entropy,   │
│  syn_ratio, non_mavlink_ratio, pkt_size_var      │
└──────┬──────────┬───────────────┬───────────────┘
       │          │               │
       ▼          ▼               ▼
┌──────────┐ ┌──────────┐ ┌─────────────────┐
│ LightGBM │ │ GRU-64   │ │ Autoencoder     │
│ (ONNX)   │ │ (ONNX)   │ │ (unsupervised)  │
│ ~20 μs   │ │ ~2 ms    │ │ ~0.5 ms         │
│ 7 feat   │ │ 5×7 seq  │ │ 7 feat          │
│ Primary  │ │ Temporal │ │ Anomaly         │
└────┬─────┘ └────┬─────┘ └───────┬─────────┘
     │            │               │
     ▼            ▼               ▼
┌─────────────────────────────────────────────────┐
│          Confidence-Weighted Voting              │
│  w_lgbm=0.5  w_gru=0.3  w_ae=0.2               │
│  Total latency: ~3 ms (well within 600 ms)      │
└──────────────────────┬──────────────────────────┘
                       │
                       ▼
                 [ALERT / LOG]
```

### Expected Performance

| Metric | Current (XGB only) | Current (TST) | Proposed Ensemble |
|---|---|---|---|
| **Accuracy** | ~90% | ~92–95% (est.) | **97–99%** |
| **Inference** | 40–60 μs | 100 ms | **~3 ms** |
| **Zero-day detection** | ❌ No | ❌ No | ✅ Yes (autoencoder) |
| **Drift adaptation** | ❌ No | ❌ No | ✅ (add ADWIN) |
| **CPU overhead** | ~0.01% | ~4.25% | **~0.5%** |
| **First detection** | 3 s | 240 s (4 min) | **3 s** |
| **RAM** | ~50 MB | ~400 MB | **~80 MB** |

---

## 6. Datasets for Benchmarking

| Dataset | Year | Attacks | Size | Best For |
|---|---|---|---|---|
| **CICDDoS2019** | 2019 | 13 DDoS types | ~50 GB | DDoS-specific evaluation |
| **CICIDS2017** | 2017 | DoS, DDoS, BruteForce, XSS | ~8 GB | General IDS comparison |
| **BoT-IoT** | 2019 | IoT Botnet, DDoS, DoS | ~70 GB | IoT-specific scenarios |
| **TON_IoT** | 2020 | IoT attacks (9 types) | ~3 GB | Lightweight IoT evaluation |
| **UNSW-NB15** | 2015 | 9 attack families | ~2 GB | Baseline comparison |
| **IoTID20** | 2020 | IoT Anomaly, Botnet, Mirai | ~600 MB | Concept drift evaluation |
| **Our MAVLink dataset** | 2024 | DDoS on MAVLink tunnel | Custom | Domain-specific ground truth |

**⚠️ Warning**: CIC-IDS-2018 has known issues with CIC flowmeter artifacts (Lanvin et al., IEEE 2022). Avoid for final evaluation.

---

## 7. Key Papers & References

1. **Yang, Moubayed, Shami** — *"Tree-Based Intelligent IDS for IoV"*, IEEE GLOBECOM 2019
   - DT, RF, ET, XGBoost comparison; XGBoost best at 99.6% on CICIDS2017
   
2. **Yang, Moubayed, Shami** — *"MTH-IDS: Multi-Tiered Hybrid IDS for IoV"*, IEEE IoT Journal 2022
   - 4-tier: supervised trees → stacking → k-means (zero-day) → biased classifiers
   
3. **Yang, Shami, Stevens, DeRusett** — *"LCCDE: Decision-Based Ensemble for IDS"*, IEEE GLOBECOM 2022
   - XGBoost + LightGBM + CatBoost per-class leaders; 99.7% F1
   
4. **Yang, Shami** — *"CNN + Transfer Learning IDS for IoV"*, IEEE ICC 2022
   - VGG16/ResNet on CICIDS2017; 1D-CNN achieves 99.25% F1
   
5. **Yang, Manias, Shami** — *"PWPAE: Ensemble for Concept Drift in IoT"*, IEEE GLOBECOM 2021
   - ADWIN + Adaptive RF; addresses model staleness in production
   
6. **Vanlalruata** — *"LIDS: Lightweight IDS for DDoS Attacks"*, Wiley Security & Privacy 2025
   - PCA + Conv1D pipeline; tested on CICDDoS2019, BoT-IoT, TON_IoT
   
7. **Chianfa, Miani, Zarpelão** — *"Unsupervised DDoS Detection in High-Speed Networks"*, SBRC 2026
   - Autoencoder beats IF/LOF/OCSVM; multi-window feature extraction
   
8. **Rahul et al.** — *"Evaluating Shallow and Deep NNs for NIDS"*, ICCCNT 2018
   - DNN outperforms classical ML on KDDCup'99; basis for deeper architectures
   
9. **Breno Farias da Silva** — *"DDoS-Detector: GA/RFE/PCA Feature Selection"*, 2025
   - 100% F1 with 36 GA-selected features + RF; WGAN-GP augmentation

---

## 8. Implementation Priority Roadmap

### Phase 1: Quick Wins (1–2 days)
- [ ] Convert XGBoost to ONNX Runtime (2–3× speedup, zero accuracy change)
- [ ] Add 3 features: `iat_std`, `non_mavlink_ratio`, `src_entropy`
- [ ] Replace XGBoost with LightGBM (faster, typically better accuracy)
- [ ] Retrain and measure accuracy improvement

### Phase 2: Architecture Upgrade (1 week)
- [ ] Replace TST with small GRU (64 units, 5-window, ONNX)
- [ ] Add autoencoder anomaly detector (parallel, unsupervised)
- [ ] Implement confidence-weighted voting
- [ ] Benchmark 3-model ensemble on RPi4

### Phase 3: Production Hardening (2 weeks)
- [ ] Add ADWIN drift detection (River library)
- [ ] Implement Hoeffding Tree as online fallback
- [ ] Knowledge distill TST → LightGBM (optional)
- [ ] GA-based feature selection optimization
- [ ] Comprehensive benchmark: accuracy, latency, power, CPU

### Phase 4: Academic Comparison (for thesis)
- [ ] Test on CICDDoS2019 + BoT-IoT for standardized comparison
- [ ] Generate ROC/PR curves for all models
- [ ] Measure inference × accuracy Pareto frontier
- [ ] Compare with LIDS, LCCDE, MTH-IDS results

---

## 9. Conclusion

Our current system is **competitively positioned** in terms of latency overhead (near-zero impact on PQC handshakes), which is the primary goal. However, significant improvements are possible:

| Gap | Current | Achievable | Method |
|---|---|---|---|
| **Accuracy** | 90% | 97–99% | +features + LightGBM |
| **Inference** | 100 ms (TST) | 3 ms | GRU replacement |
| **Zero-day** | Not possible | Possible | Autoencoder |
| **Drift** | Not handled | Self-healing | ADWIN + online learning |
| **Speed** | Native Python | 2–3× faster | ONNX Runtime |

The **most impactful single change** is adding 3–5 more features to the packet capture window. The current 2-feature approach (pkt count + bytes) is the main bottleneck for accuracy, not the model architecture itself.
