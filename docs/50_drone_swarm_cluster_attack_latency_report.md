# 50-Drone Swarm Multi-Cluster Attack & SMT Recovery Latency Benchmark Report

## 1. Executive Summary

This report documents the empirical evaluation of Sparse Merkle Tree (SMT) structure recovery latency ($T_{\text{recovery}}$) across a hierarchical UAV swarm scaling from $N = 5$ to $N = 50$ drones organized into dynamic multi-cluster topologies. The swarm security system was evaluated against two major attack vectors:
1. **Sybil Identity Injection Attack**: Rogue identity attempting unauthenticated telemetry insertion.
2. **DDoS Telemetry Flooding Burst Attack**: High-volume telemetry payload flooding aimed at compromising state integrity.

Measurements were conducted separately across three distinct node target roles:
- **Root Node** (Global Swarm Leader)
- **Intermediate Node** (Cluster Leader / Cluster Head)
- **Leaf Node** (Follower Drone)

---

## 2. Multi-Cluster Hierarchical Swarm Architecture

The 50-drone swarm is partitioned into 5 dynamic clusters ($C_1 \dots C_5$), each containing up to 10 drones:

$$\text{Swarm Size } N \in \{5, 10, 15, 20, 25, 30, 35, 40, 45, 50\}$$

### Cluster Assignment:
- **Cluster 1 ($C_1$)**: Node `drone-1` (Global Root Leader) + Follower nodes `drone-2` $\dots$ `drone-10`.
- **Cluster 2 ($C_2$)**: Node `drone-11` (Cluster Head / Intermediate) + Follower nodes `drone-12` $\dots$ `drone-20`.
- **Cluster 3 ($C_3$)**: Node `drone-21` (Cluster Head / Intermediate) + Follower nodes `drone-22` $\dots$ `drone-30`.
- **Cluster 4 ($C_4$)**: Node `drone-31` (Cluster Head / Intermediate) + Follower nodes `drone-32` $\dots$ `drone-40`.
- **Cluster 5 ($C_5$)**: Node `drone-41` (Cluster Head / Intermediate) + Follower nodes `drone-42` $\dots$ `drone-50`.

```
                      ┌────────────────────────┐
                      │ drone-1 (Root Leader)  │
                      └───────────┬────────────┘
         ┌────────────────────────┼────────────────────────┐
         │                        │                        │
┌────────┴─────────┐    ┌─────────┴────────┐    ┌──────────┴─────────┐
│  drone-11 (CH2)  │    │  drone-21 (CH3)  │    │   drone-31 (CH4)   │ ...
└────────┬─────────┘    └─────────┬────────┘    └──────────┬─────────┘
   ┌─────┴─────┐           ┌──────┴──────┐          ┌──────┴──────┐
┌──┴───┐    ┌──┴───┐    ┌──┴───┐      ┌──┴───┐   ┌──┴───┐      ┌──┴───┐
│d-12  │    │d-20  │    │d-22  │      │d-30  │   │d-32  │      │d-40  │
└──────┘    └──────┘    └──────┘      └──────┘   └──────┘      └──────┘
```

---

## 3. Cryptographic State Recovery Protocol ($T_{\text{recovery}}$)

The recovery latency $T_{\text{recovery}}$ measures the exact duration from attack detection to Sparse Merkle Tree structural restoration and surviving node verification:

$$T_{\text{recovery}} = T_{\text{detection trigger}} \rightarrow T_{\text{leaf revocation}} \rightarrow T_{\text{Merkle path update}} \rightarrow T_{\text{surviving root verified}}$$

### Algorithmic Complexity:
Sparse Merkle Tree updates operate in $O(\log N)$ depth ($H = 256$), recomputing only the affected authentication path rather than rebuilding the entire tree state.

---

## 4. Attack Mitigation Workflows

### A. Sybil Identity Injection Attack
1. **Detection**: `SMTVerifier.verify_non_membership(root_hash, rogue_proof)` detects unauthenticated key.
2. **Mitigation**: Instant socket rejection and key blacklisting.
3. **State Recovery**: Leaf zeroed in SMT (`EMPTY_HASH`), root hash updated, surviving node proof validated.

### B. DDoS Flooding Burst Attack
1. **Detection**: `SMTVerifier.verify_membership(root_hash, flooded_proof)` identifies state/hash mismatch.
2. **Mitigation**: Immediate revocation of compromised leaf hash (`EMPTY_HASH = 0x00...00`).
3. **Topological Ejection**: Pruning node from cluster tree.
4. **State Recovery**: 256-depth Merkle path recomputed, global SMT root updated, surviving node proof validated.

---

## 5. Empirical Benchmark Result Tables (30 Measured Repetitions per Config)

### A. Sybil Attack SMT Recovery Latency ($T_{\text{Sybil}}$ in ms)

| Swarm Size ($N$) | Target Role | Median Latency (ms) | Mean Latency (ms) | Min Latency (ms) | Max Latency (ms) | Std Dev (ms) | Safety Limit |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **N = 5** | Root Node | `7.0401` | `6.8961` | `2.2780` | `13.0501` | `2.5606` | < 20 ms |
| **N = 5** | Intermediate Node | `6.7513` | `6.7503` | `3.4569` | `11.8891` | `1.8174` | < 20 ms |
| **N = 5** | Leaf Node | `5.6864` | `6.1903` | `3.2864` | `14.6340` | `2.2157` | < 20 ms |
| **N = 10** | Root Node | `6.4248` | `7.3954` | `2.3319` | `38.9386` | `6.0664` | < 20 ms |
| **N = 10** | Intermediate Node | `6.6404` | `6.7006` | `4.2704` | `11.0343` | `1.5343` | < 20 ms |
| **N = 10** | Leaf Node | `6.2058` | `6.6958` | `3.7834` | `11.7223` | `2.0312` | < 20 ms |
| **N = 25** | Root Node | `4.0315` | `4.6944` | `2.0275` | `9.3377` | `1.9440` | < 20 ms |
| **N = 25** | Intermediate Node | `4.4308` | `5.1296` | `2.2610` | `11.2302` | `1.9474` | < 20 ms |
| **N = 25** | Leaf Node | `3.2789` | `3.9855` | `1.6946` | `9.0220` | `1.8714` | < 20 ms |
| **N = 50** | Root Node | `3.3180` | `3.6663` | `1.9583` | `8.0991` | `1.3588` | < 20 ms |
| **N = 50** | Intermediate Node | `4.1838` | `4.3603` | `1.8707` | `8.5185` | `1.5585` | < 20 ms |
| **N = 50** | Leaf Node | `3.3256` | `3.8727` | `1.6856` | `9.0892` | `1.7992` | < 20 ms |

### B. DDoS Flooding Attack SMT Recovery Latency ($T_{\text{DDoS}}$ in ms)

| Swarm Size ($N$) | Target Role | Median Latency (ms) | Mean Latency (ms) | Min Latency (ms) | Max Latency (ms) | Std Dev (ms) | Safety Limit |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **N = 5** | Root Node | `5.4771` | `6.4797` | `3.1144` | `28.1781` | `4.4610` | < 20 ms |
| **N = 5** | Intermediate Node | `5.3350` | `5.2346` | `2.3319` | `7.8915` | `1.1157` | < 20 ms |
| **N = 5** | Leaf Node | `5.4499` | `5.6306` | `2.9999` | `9.5968` | `1.2572` | < 20 ms |
| **N = 10** | Root Node | `5.3379` | `5.3078` | `2.9073` | `7.7297` | `1.1463` | < 20 ms |
| **N = 10** | Intermediate Node | `5.5434` | `6.6738` | `3.4283` | `16.1431` | `2.9452` | < 20 ms |
| **N = 10** | Leaf Node | `8.3297` | `9.8163` | `3.3401` | `23.2041` | `5.2279` | < 20 ms |
| **N = 25** | Root Node | `3.1179` | `3.4832` | `1.5511` | `8.1856` | `1.4905` | < 20 ms |
| **N = 25** | Intermediate Node | `3.3740` | `3.8833` | `2.0664` | `6.9560` | `1.2072` | < 20 ms |
| **N = 25** | Leaf Node | `4.2715` | `4.2646` | `2.2609` | `10.6890` | `1.5553` | < 20 ms |
| **N = 50** | Root Node | `2.8512` | `3.0722` | `1.4753` | `5.4180` | `0.9757` | < 20 ms |
| **N = 50** | Intermediate Node | `2.7625` | `3.0407` | `1.4428` | `5.5235` | `1.0322` | < 20 ms |
| **N = 50** | Leaf Node | `2.8784` | `3.7473` | `1.6666` | `17.7875` | `3.0896` | < 20 ms |

---

## 6. Generated Figures & Output Datasets

- **Raw JSON Dataset**: [smt_recovery_latency_windows_gcs_x86.json](file:///c:/Users/TOSHIBA/Documents/iiit%20internship/IIIt%20UAV/Project%20new%20code/logs/benchmarks/smt_recovery_latency_windows_gcs_x86.json)
- **CSV Summary**: [smt_recovery_latency_summary.csv](file:///c:/Users/TOSHIBA/Documents/iiit%20internship/IIIt%20UAV/Project%20new%20code/logs/benchmarks/smt_recovery_latency_summary.csv)
- **Combined 6-Panel Figure**: [combined_6panel_latency_benchmark.png](file:///c:/Users/TOSHIBA/Documents/iiit%20internship/IIIt%20UAV/Project%20new%20code/suite_benchmarks/ieee_report_output/figures/combined_6panel_latency_benchmark.png)
- **Individual Figures**:
  - `graph1_sybil_leader.png` (Sybil - Root Leader)
  - `graph2_sybil_intermediate.png` (Sybil - Intermediate Cluster Head)
  - `graph3_sybil_leaf.png` (Sybil - Leaf Follower)
  - `graph4_ddos_leader.png` (DDoS - Root Leader)
  - `graph5_ddos_intermediate.png` (DDoS - Intermediate Cluster Head)
  - `graph6_ddos_leaf.png` (DDoS - Leaf Follower)

