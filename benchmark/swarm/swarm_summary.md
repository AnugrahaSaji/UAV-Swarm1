# Hierarchical Swarm Architecture Benchmark Report

> **Generated**: 2026-07-31T19:17:44.705113+00:00
> **Environment**: Windows-11-10.0.26200-SP0 | Python 3.13.14 | Intel64 Family 6 Model 140 Stepping 1, GenuineIntel

---

## 1. Swarm Topology & Metadata

| Parameter | Value |
| :--- | :--- |
| **Active Swarm Nodes** | 103 drones |
| **Cluster Size (cluster-A)** | 101 drones |
| **Maximum Supported Nodes** | 256 drones |
| **Iterations Executed** | 100 runs |
| **CPU Utilization** | 0.0% |
| **Memory Footprint (RSS)** | 45.73 MB |

---

## 2. Swarm Network Microbenchmarks

| Metric / Operation | Mean (ms) | Median (ms) | Min (ms) | Max (ms) | StdDev (ms) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Swarm Context Initialization** | `2.335603` | `1.75655` | `1.2534` | `19.2385` | `2.61335` |
| **Drone Discovery Latency** | `0.00195` | `0.0017` | `0.0014` | `0.0063` | `0.000777` |
| **Drone Join Latency** | `0.083131` | `0.07515` | `0.0658` | `0.1751` | `0.022232` |
| **Cluster Formation Time** | `0.124696` | `0.112725` | `0.0987` | `0.26265` | `0.033349` |
| **Heartbeat RTT Latency** | `0.000815` | `0.0006` | `0.0005` | `0.0127` | `0.001241` |
| **Routing Lookup Latency ($O(1)$)** | `0.001209` | `0.001` | `0.0009` | `0.009` | `0.000847` |
| **Packet Forwarding Latency** | `0.005554` | `0.00475` | `0.0045` | `0.0271` | `0.003151` |
| **Cluster Leader Election** | `0.142701` | `0.139` | `0.0905` | `0.4748` | `0.053832` |
| **Cluster Failover Recovery** | `0.10724` | `0.1022` | `0.0683` | `0.3006` | `0.035313` |
| **Node Re-parenting Latency** | `0.052782` | `0.05445` | `0.0352` | `0.106` | `0.014059` |

---

## 3. Key Research Takeaways

1. **Sub-Millisecond Routing & Failover**: $O(1)$ dictionary route lookups execute in **`0.001209 ms`**, while cluster failovers recover in **`0.10724 ms`**.
2. **Dynamic Onboarding Efficiency**: Autonomous node discovery and join complete in under **`0.083131 ms`**.
3. **Hierarchical Control Overhead**: The 3-tier structure bounds control frame broadcasts to $O(\log N)$, maintaining low memory usage (**`45.73 MB`**).
