# DDoS Detection Analysis — secure-tunnel

## Executive Summary
The secure-tunnel implements a 4-tier DDoS detection cascade designed for edge deployment on Raspberry Pi 4/5, integrated with the MDEAS scheduler via Axis 3 (detector management).

## Current Detection Method

### 4-Tier Cascade Architecture
```
Tier 1: LightGBM   (Sentinel)    — 54 features, 15 classes, 6.72ms inference
Tier 2: XGBoost    (Confirmer)   — 54 features, 15 classes, 7.42ms inference
Tier 3: RandomForest (Arbitrator) — 54 features, 15 classes, 74.68ms inference
Tier 4: TST        (Deep)        — 46 features, 6 classes, 10.72ms inference
```

### Feature Pipeline
- **FlowFeatureExtractor** (ddos/features.py): 54 CIC-IoT-2023 features
- Packet capture via scapy sniffing on wlan0
- Per-flow state tracking (FlowState: timestamps, packet counts, byte counts)
- Window-based aggregation (default 100 packets per window)
- MAVLink v2 detection (0xFD magic byte filtering)
- MQTT features zero-filled for UAV compatibility

### Model Accuracy (CIC-IoT-2023)
| Model | F1-macro | F1-weighted | Best At |
|-------|----------|-------------|---------|
| XGBoost | **0.947** | 0.944 | SYN Flood (0.88), SynonymousIP (0.83) |
| LightGBM | 0.937 | 0.934 | Speed (6.72ms) |
| RandomForest | 0.935 | 0.934 | ACK Fragmentation (1.00) |
| TST | 0.80 | — | Mirai (0.99 F1 on coarse class) |

## Computational Overhead (RPi4 @ 1.8 GHz)

| Detector | Δ Power | Δ Temp | CPU% | Inference | Energy/Inf |
|----------|---------|--------|------|-----------|------------|
| LightGBM | +999 mW | +4.8°C | 36.9% | 6.72 ms | 29.0 mJ |
| XGBoost | +951 mW | +4.8°C | 37.0% | 7.42 ms | 31.7 mJ |
| TST | +1,973 mW | +10.7°C | 93.0% | 10.72 ms | 56.7 mJ |
| RandomForest | +594 mW | +3.4°C | 25.6% | 74.68 ms | 291.4 mJ |

### PQC Co-execution Overhead (72 suites)
- **XGBoost + PQC**: mean +2.5% latency overhead, zero packet loss
- **TST + PQC**: mean +71.8% latency overhead, zero packet loss
- CPU additivity confirmed: PQC(25%) + XGB(37%) ≈ 48% measured

## Edge Compatibility Assessment

### RPi4 Worst Case (PQC + TST)
| Resource | Used | Capacity | Headroom |
|----------|------|----------|----------|
| CPU | 55.3% | 100% | 44.7% |
| Temperature | 61.5°C | 85°C | 23.5°C |
| RAM | 531 MB | 4096 MB | 87.0% |
| Power | 4.558 W | 5 W | 0.442 W |

**Verdict**: Fully compatible even in worst-case configuration.

## Identified Gaps

1. **Feature count mismatch**: SOTA comparison uses 2-feature simplified detector vs 54-feature full pipeline
2. **Accuracy unverifiable**: No eval scripts shipped for reproducing F1 scores (I3)
3. **TST dim_feedforward**: Set to 512 (1× d_model) rather than typical 2-4×
4. **RF memory**: 198 MB model inflates to ~462 MB RSS — may pressure RPi4 under load

## Improvement Proposals

### P1: Quantized XGBoost (ONNX Runtime)
- Convert XGBoost to ONNX format for ARM NEON acceleration
- Expected: 30-50% inference speedup, same accuracy
- Implementation: `skl2onnx` → `onnxruntime` (ARM64 wheels available)

### P2: Feature Reduction (54 → 20)
- Apply mutual information ranking to identify top-20 features
- Expected: 15-25% inference speedup with <1% accuracy loss
- Reduces scapy processing overhead per window

### P3: TST Architecture Optimization
- Increase dim_feedforward to 1024 (2× d_model)
- Reduce hidden_dim to 256 with nhead=4
- Expected: 50% parameter reduction, ~0.5% accuracy improvement
- Smaller model fits better in L1/L2 cache on ARM

### P4: Adaptive Window Sizing
- Under DDoS: reduce window from 100 → 25 packets for faster response
- Normal: keep 100-packet windows for accuracy
- Integrate with MDEAS Axis 3 escalation logic
