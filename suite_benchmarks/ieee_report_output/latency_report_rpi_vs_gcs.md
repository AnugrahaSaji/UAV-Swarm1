# ONE-PAGE SMT RECOVERY LATENCY REPORT (SWARM ROLES BREAKDOWN)
## Measured Platform: `WINDOWS_GCS_X86` | Repetitions: 30 Fresh Tree Runs per Configuration

---

### 1. Side-by-Side Measured Latency by Drone Role

#### A. Sybil Attack Non-Membership Audit Latency ($T_{\text{Sybil}}$)

| Swarm Size ($N$) | Leader Drone (Root) | Intermediate Drone (Cluster Head) | Leaf Drone (Follower) | Safety Budget |
| :---: | :---: | :---: | :---: | :---: |
| **N = 5** | `1.0672 ms` | `1.1387 ms` | `1.0286 ms` | Real-Time (< 20 ms) |
| **N = 10** | `0.9852 ms` | `1.0097 ms` | `0.8258 ms` | Real-Time (< 20 ms) |
| **N = 15** | `0.9936 ms` | `0.9874 ms` | `0.9694 ms` | Real-Time (< 20 ms) |
| **N = 20** | `0.9027 ms` | `0.9898 ms` | `0.8299 ms` | Real-Time (< 20 ms) |
| **N = 25** | `0.7509 ms` | `0.9642 ms` | `1.1604 ms` | Real-Time (< 20 ms) |
| **N = 30** | `0.9196 ms` | `1.0288 ms` | `0.7475 ms` | Real-Time (< 20 ms) |
| **N = 35** | `0.9326 ms` | `0.7504 ms` | `0.8096 ms` | Real-Time (< 20 ms) |
| **N = 40** | `0.6976 ms` | `0.7684 ms` | `0.7537 ms` | Real-Time (< 20 ms) |
| **N = 45** | `0.7299 ms` | `0.7750 ms` | `0.9275 ms` | Real-Time (< 20 ms) |
| **N = 50** | `0.7356 ms` | `0.7077 ms` | `0.7151 ms` | Real-Time (< 20 ms) |

#### B. DDoS Flooding SMT Recovery Latency ($T_{\text{DDoS}}$)

| Swarm Size ($N$) | Leader Drone (Root) | Intermediate Drone (Cluster Head) | Leaf Drone (Follower) | Safety Budget |
| :---: | :---: | :---: | :---: | :---: |
| **N = 5** | `4.0638 ms` | `4.1491 ms` | `4.0358 ms` | Real-Time (< 20 ms) |
| **N = 10** | `4.1236 ms` | `3.9373 ms` | `4.0252 ms` | Real-Time (< 20 ms) |
| **N = 15** | `3.3639 ms` | `4.1142 ms` | `4.0555 ms` | Real-Time (< 20 ms) |
| **N = 20** | `3.6830 ms` | `3.7899 ms` | `3.7044 ms` | Real-Time (< 20 ms) |
| **N = 25** | `4.1773 ms` | `4.3554 ms` | `4.4235 ms` | Real-Time (< 20 ms) |
| **N = 30** | `4.4930 ms` | `4.1196 ms` | `3.1826 ms` | Real-Time (< 20 ms) |
| **N = 35** | `2.9306 ms` | `3.4074 ms` | `3.5608 ms` | Real-Time (< 20 ms) |
| **N = 40** | `2.7655 ms` | `3.8992 ms` | `2.7347 ms` | Real-Time (< 20 ms) |
| **N = 45** | `2.6640 ms` | `2.7365 ms` | `3.2503 ms` | Real-Time (< 20 ms) |
| **N = 50** | `3.0643 ms` | `2.7902 ms` | `2.9176 ms` | Real-Time (< 20 ms) |

---

### 2. Key Research Conclusions

1. **Role Uniformity**: SMT proof verification and leaf revocation exhibit logarithmic authentication-path complexity ($O(\log N)$), producing near-identical execution latency across Leader, Intermediate, and Leaf drone roles.
2. **Real-Time Security Guarantee**: Across all evaluated swarm sizes up to $N=50$, SMT recovery latency remains well below the standard $20\text{ ms}$ MAVLink control cycle ($50\text{ Hz}$), confirming that on-board edge recovery does not degrade flight stability.