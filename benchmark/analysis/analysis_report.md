# Comprehensive Research Benchmark Analysis Report

> **Generated**: 2026-07-31T19:38:24.882649+00:00
> **Target OS**: Windows-11-10.0.26200-SP0 | Python 3.13.14 | Intel64 Family 6 Model 140 Stepping 1, GenuineIntel

---

## 1. Executive Summary & Methodology

This report presents a formal empirical evaluation of the two research contributions:
1. **Sparse Merkle Tree (SMT)**: Fixed 256-level zero-knowledge membership state verification engine.
2. **Hierarchical Swarm Architecture**: Autonomous 3-tier drone topology management and packet routing.

All timing samples were collected using high-precision runtime hardware timers (`time.perf_counter()`). The statistics include **Mean**, **Median**, **Min**, **Max**, **Standard Deviation**, **Variance**, and **95% Confidence Intervals** computed over 100 iterations.

---

## 2. Sparse Merkle Tree (SMT) Empirical Performance

### **A. Experiment Parameters**
- **Tree Depth**: 256 levels (SHA-256)
- **Registered Drones**: 8 nodes
- **Root Hash Size**: 32 bytes
- **Average Proof Size**: 248 bytes

### **B. SMT Statistical Metrics Table**

| Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | StdDev (ms) | Variance | 95% CI (+/-) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Tree Initialization** | `0.000348` | `0.0003` | `0.0002` | `0.0034` | `0.000373` | `1.4e-07` | `±7.4e-05` |
| **Node Registration** | `0.570387` | `0.54955` | `0.5127` | `0.7088` | `0.060889` | `0.00370747` | `±0.012082` |
| **Proof Generation** | `0.18142` | `0.1708` | `0.162` | `0.489` | `0.034975` | `0.00122325` | `±0.00694` |
| **Proof Verification** | `0.253677` | `0.23145` | `0.2214` | `0.6608` | `0.061975` | `0.0038409` | `±0.012297` |
| **Invalid Proof Rejection** | `0.246444` | `0.23605` | `0.2232` | `0.437` | `0.032888` | `0.00108162` | `±0.006526` |

---

## 3. Hierarchical Swarm Architecture Performance

### **A. Experiment Parameters**
- **Active Swarm Nodes**: 103 drones
- **Cluster Size**: 101 drones
- **Max Supported Nodes**: 256 drones

### **B. Swarm Statistical Metrics Table**

| Operation / Metric | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | StdDev (ms) | Variance | 95% CI (+/-) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Swarm Initialization** | `2.335603` | `1.75655` | `1.2534` | `19.2385` | `2.61335` | `6.82959822` | `±0.518545` |
| **Drone Discovery Latency** | `0.00195` | `0.0017` | `0.0014` | `0.0063` | `0.000777` | `6e-07` | `±0.000154` |
| **Drone Join Latency** | `0.083131` | `0.07515` | `0.0658` | `0.1751` | `0.022232` | `0.00049426` | `±0.004411` |
| **Cluster Formation Time** | `0.124696` | `0.112725` | `0.0987` | `0.26265` | `0.033349` | `0.00111216` | `±0.006617` |
| **Heartbeat Rtt** | `0.000815` | `0.0006` | `0.0005` | `0.0127` | `0.001241` | `1.54e-06` | `±0.000246` |
| **Routing Lookup Latency** | `0.001209` | `0.001` | `0.0009` | `0.009` | `0.000847` | `7.2e-07` | `±0.000168` |
| **Packet Forwarding Latency** | `0.005554` | `0.00475` | `0.0045` | `0.0271` | `0.003151` | `9.93e-06` | `±0.000625` |
| **Cluster Leader Election** | `0.142701` | `0.139` | `0.0905` | `0.4748` | `0.053832` | `0.00289788` | `±0.010681` |
| **Cluster Failover Latency** | `0.10724` | `0.1022` | `0.0683` | `0.3006` | `0.035313` | `0.00124701` | `±0.007007` |
| **Re Parenting Latency** | `0.052782` | `0.05445` | `0.0352` | `0.106` | `0.014059` | `0.00019766` | `±0.00279` |

---

## 4. Key Findings & Research Conclusions

1. **Sub-Millisecond Zero-Knowledge Verification**: SMT membership proof verification executes in sub-millisecond latency, bounding identity validation to constant $O(\text{depth})$ complexity.
2. **Deterministic $O(1)$ Swarm Routing**: Routing table lookups in the 3-tier hierarchy complete in microsecond latency, enabling fast packet forwarding.
3. **Low-Overhead Dynamic Failover**: Cluster failover and leader election re-parenting complete without interrupting swarm telemetry streams.

---

## 5. Generated Visualizations

All 300 DPI plots are available under `benchmark/analysis/plots/` in **PNG**, **PDF**, and **SVG** formats:
- `smt_bar_chart` & `swarm_bar_chart` — Mean Latency & 95% Confidence Intervals
- `smt_line_chart` & `swarm_line_chart` — Iteration Trajectory Curves
- `smt_box_plot` & `swarm_box_plot` — Quartile Distribution & Outliers
- `smt_histogram` & `swarm_histogram` — Probability Density Distributions
- `smt_cdf` & `swarm_cdf` — Cumulative Distribution Functions
- `smt_errorbar` & `swarm_errorbar` — Confidence Interval Error Bars
