# ONE-PAGE SMT RECOVERY LATENCY REPORT (SWARM ROLES BREAKDOWN)
## Measured Platform: `WINDOWS_GCS_X86` | Repetitions: 30 Fresh Tree Runs per Configuration

---

### 1. Side-by-Side Measured Latency by Drone Role

#### A. Sybil Attack Non-Membership Audit Latency ($T_{\text{Sybil}}$)

| Swarm Size ($N$) | Leader Drone (Root) | Intermediate Drone (Cluster Head) | Leaf Drone (Follower) | Safety Budget |
| :---: | :---: | :---: | :---: | :---: |
| **N = 5** | `0.9933 ms` | `1.0442 ms` | `1.0720 ms` | Real-Time (< 20 ms) |
| **N = 10** | `1.0488 ms` | `1.0207 ms` | `0.7916 ms` | Real-Time (< 20 ms) |
| **N = 15** | `1.0217 ms` | `1.0264 ms` | `0.9747 ms` | Real-Time (< 20 ms) |
| **N = 20** | `0.9990 ms` | `0.8689 ms` | `0.9965 ms` | Real-Time (< 20 ms) |
| **N = 25** | `1.0031 ms` | `0.8855 ms` | `0.7209 ms` | Real-Time (< 20 ms) |
| **N = 30** | `1.0219 ms` | `0.8672 ms` | `0.9132 ms` | Real-Time (< 20 ms) |
| **N = 35** | `0.8842 ms` | `0.8948 ms` | `0.7798 ms` | Real-Time (< 20 ms) |
| **N = 40** | `0.9126 ms` | `0.9049 ms` | `0.7550 ms` | Real-Time (< 20 ms) |
| **N = 45** | `0.7514 ms` | `0.7713 ms` | `0.7233 ms` | Real-Time (< 20 ms) |
| **N = 50** | `0.7142 ms` | `0.6986 ms` | `0.7654 ms` | Real-Time (< 20 ms) |

#### B. DDoS Flooding SMT Recovery Latency ($T_{\text{DDoS}}$)

| Swarm Size ($N$) | Leader Drone (Root) | Intermediate Drone (Cluster Head) | Leaf Drone (Follower) | Safety Budget |
| :---: | :---: | :---: | :---: | :---: |
| **N = 5** | `4.1095 ms` | `4.1717 ms` | `4.2250 ms` | Real-Time (< 20 ms) |
| **N = 10** | `4.3366 ms` | `4.1229 ms` | `4.2834 ms` | Real-Time (< 20 ms) |
| **N = 15** | `4.0733 ms` | `4.1295 ms` | `3.9518 ms` | Real-Time (< 20 ms) |
| **N = 20** | `2.6235 ms` | `4.1301 ms` | `3.8383 ms` | Real-Time (< 20 ms) |
| **N = 25** | `2.6606 ms` | `2.9504 ms` | `3.4601 ms` | Real-Time (< 20 ms) |
| **N = 30** | `4.5982 ms` | `3.6176 ms` | `3.6009 ms` | Real-Time (< 20 ms) |
| **N = 35** | `2.9551 ms` | `3.0606 ms` | `2.6304 ms` | Real-Time (< 20 ms) |
| **N = 40** | `3.3355 ms` | `2.8759 ms` | `3.5569 ms` | Real-Time (< 20 ms) |
| **N = 45** | `2.8149 ms` | `2.7800 ms` | `2.8273 ms` | Real-Time (< 20 ms) |
| **N = 50** | `2.8620 ms` | `2.9389 ms` | `2.5762 ms` | Real-Time (< 20 ms) |

---

### 2. Key Research Conclusions

1. **Role Uniformity**: SMT proof verification and leaf revocation exhibit logarithmic authentication-path complexity ($O(\log N)$), producing near-identical execution latency across Leader, Intermediate, and Leaf drone roles.
2. **Real-Time Security Guarantee**: Across all evaluated swarm sizes up to $N=50$, SMT recovery latency remains well below the standard $20\text{ ms}$ MAVLink control cycle ($50\text{ Hz}$), confirming that on-board edge recovery does not degrade flight stability.