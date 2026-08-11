# Secure Tunnel: Post-Quantum Cryptographic Link for UAVs

## Freeze Baseline

- PROTOCOL_VERSION = 1.0
- Core transport and cryptographic protocol baseline is frozen for the experimental phase.
- Frozen core components: core/handshake.py, core/aead.py, core/async_proxy.py, core/control_tcp.py, core/policy_engine.py, core/suites.py.
- Frozen protocol rules: packet header format, nonce generation logic, HKDF input schedule, replay window algorithm, and epoch progression rules.
- Experimental work must operate on this frozen baseline unless an explicit protocol revision is approved.

## 1. Abstract

**Secure Tunnel** is a research-grade, distributed secure communication system designed to protect Command & Control (C2) and telemetry links between Ground Control Stations (GCS) and Unmanned Aerial Vehicles (UAVs).

It solves the problem of securing vulnerable MAVLink traffic against quantum computer threats by implementing a hybrid Post-Quantum Cryptography (PQC) tunnel. The system encapsulates standard MAVLink UDP packets into an authenticated, encrypted stream using cutting-edge NIST-standardized algorithms (ML-KEM, ML-DSA) alongside classical primitives.

This project is critical for future-proofing autonomous systems against "store now, decrypt later" attacks and ensuring the integrity of flight control in contested environments.

---

## 2. High-Level Architecture

The system operates as a transparent "bump-in-the-wire" proxy. Applications (like Mission Planner or MAVProxy) communicate with a local plaintext port, unaware of the complex crypto-tunnel bridging the physical network.

```ascii
      [ GCS SIDE (Windows) ]                       [ DRONE SIDE (Raspberry Pi) ]
+-----------------------------+                 +-----------------------------+
|  Mission Planner / QGC      |                 |      Pixhawk Autopilot      |
|       (MAVLink App)         |                 |      (Flight Controller)    |
+-------------+---------------+                 +--------------+--------------+
              | UDP Plaintext                                  | Serial / UDP
              v                                                v
+-------------+---------------+                 +--------------+--------------+
|      GCS Proxy (Core)       |                 |      Drone Proxy (Core)     |
|  [Plaintext Listener]       |                 |   [Plaintext Listener]      |
|  [Encrypted Sender]         |                 |   [Encrypted Sender]        |
+-------------+---------------+                 +--------------+--------------+
              |                                                |
              |  <=== TCP Authenticated Handshake (PQC) ===>   |
              |                                                |
              |  <=== UDP Encrypted Data Plane (AEAD) =====>   |
              |                                                |
+-------------+---------------+                 +--------------+--------------+
|      Physical Network       |                 |      Physical Network       |
|      (WiFi / Radio)         |                 |      (WiFi / Radio)         |
+-----------------------------+                 +-----------------------------+
```

### Components
1.  **GCS Proxy:** Runs on the ground station. Acts as the server for TCP handshakes and a peer for UDP traffic.
2.  **Drone Proxy:** Runs on the companion computer (Pi). Connects to GCS via TCP to establish keys, then bridges traffic.
3.  **Schedulers:** Orchestration layers (`scheduler` and `sscheduler`) that automate test cycles, suite rotation, and re-keying.

---

## 3. Network Topology

The system assumes a flat IP network (LAN or VPN) where GCS and Drone can reach each other.

| Role | Interface | Protocol | Port (Default) | Description |
|------|-----------|----------|----------------|-------------|
| **GCS** | 0.0.0.0 | TCP | 46000 | **Handshake Server**. Listens for Drone connections. |
| **GCS** | 0.0.0.0 | UDP | 46011 | **Encrypted RX**. Receives encrypted frames from Drone. |
| **GCS** | 127.0.0.1 | UDP | 47001 | **Plaintext TX**. App sends MAVLink here to enter tunnel. |
| **GCS** | 127.0.0.1 | UDP | 47002 | **Plaintext RX**. Tunnel delivers decrypted MAVLink here. |
| **Drone** | (Connects) | TCP | -> GCS:46000 | **Handshake Client**. Initiates key exchange. |
| **Drone** | 0.0.0.0 | UDP | 46012 | **Encrypted RX**. Receives encrypted frames from GCS. |
| **Drone** | 127.0.0.1 | UDP | 47003 | **Plaintext TX**. MAVProxy sends MAVLink here to enter tunnel. |
| **Drone** | 127.0.0.1 | UDP | 47004 | **Plaintext RX**. Tunnel delivers decrypted MAVLink here. |

**Note:** The GCS is the TCP *Listener* (Server), but the Drone is the TCP *Initiator* (Client). This allows the Drone to be behind a NAT if the GCS has a public/reachable IP, though typically both are on the same LAN.

---

## 4. Cryptographic Design

Security is provided by **Suites**, which define a specific combination of algorithms.

### Components of a Suite
1.  **KEM (Key Encapsulation Mechanism):** Used during TCP handshake to establish a shared secret.
    *   *Examples:* ML-KEM-768, Kyber512, HQC-192.
2.  **Signature:** Used to authenticate the handshake (prevent Man-in-the-Middle).
    *   *Examples:* ML-DSA-65, Falcon-512, SPHINCS+.
3.  **AEAD (Authenticated Encryption with Associated Data):** Used for the high-speed UDP data plane.
    *   *Examples:* AES-GCM, ChaCha20-Poly1305, ASCON-128.

### Protocol Flow
1.  **Handshake (TCP):**
    *   Drone connects to GCS.
    *   GCS sends `ServerHello` (Public Key + Signature).
    *   Drone verifies Signature against stored GCS public key.
    *   Drone encapsulates a shared secret using KEM and sends ciphertext.
    *   Both sides derive session keys (`K_d2g`, `K_g2d`) and Session ID.
2.  **Data Plane (UDP):**
    *   Traffic is encrypted using the derived session keys.
    *   Each packet includes a header with Session ID, Sequence Number, and AEAD Tag.
    *   Replay protection is enforced via a sliding window.

---

## 5. Core Modules

The `core/` directory contains the engine of the tunnel.

*   **`core/config.py`**: The **Single Source of Truth**. Defines all ports, IP addresses, and feature flags.
*   **`core/handshake.py`**: Implements the PQC handshake logic. Handles key generation, signing, verification, and encapsulation using `liboqs`.
*   **`core/async_proxy.py`**: The main event loop (selector-based).
    *   Manages UDP sockets (plaintext & encrypted).
    *   Handles packet encryption/decryption.
    *   Enforces rate limits and strict peer checking.
*   **`core/run_proxy.py`**: The CLI entrypoint. Parses arguments and launches the `async_proxy` engine.

---

## 6. Scheduler Systems

The project supports two orchestration modes for automated testing.

### A. `scheduler/` (Legacy / GCS-Driven)
*   **Philosophy:** GCS is the "Master". It tells the Drone what to do via SSH or RPC.
*   **Use Case:** Lab benchmarking where the operator sits at the GCS.

### B. `sscheduler/` (Simplified / Drone-Driven)
*   **Philosophy:** Drone is the "Controller". GCS is a passive "Follower".
*   **Entrypoints:**
    *   `sscheduler/sgcs.py`: Runs on GCS. Starts a control server and waits.
    *   `sscheduler/sdrone.py`: Runs on Drone. Decides which suite to run and commands the GCS to start.
*   **Use Case:** Field tests where the Drone determines the test plan (e.g., "run these 5 suites in flight"). **This is the currently active development branch.**

---

## 7. End-to-End Data Flow

1.  **Source:** Pixhawk sends MAVLink serial data to Raspberry Pi.
2.  **Bridge:** `MAVProxy` on Pi reads serial, forwards UDP packet to `127.0.0.1:47003`.
3.  **Ingress:** `Drone Proxy` receives packet on `47003`.
4.  **Encryption:** Proxy encrypts payload with `K_d2g` (Drone-to-GCS key). Adds header.
5.  **Transmission:** Encrypted packet sent from Drone `wlan0` to GCS IP `46011`.
6.  **Reception:** `GCS Proxy` receives packet on `46011`.
7.  **Decryption:** Proxy validates header/tag, decrypts using `K_d2g`.
8.  **Egress:** Plaintext packet sent to `127.0.0.1:47002`.
9.  **Sink:** GCS Application (Mission Planner) listens on `47002` and parses MAVLink.

*Return traffic follows the inverse path.*

---

## 8. Environments & Setup

### GCS (Windows)
*   **Manager:** Conda
*   **Env Name:** `oqs-dev`
*   **Key Dep:** `oqs-python` (must be compiled with PQC support).

### Drone (Raspberry Pi / Linux)
*   **Manager:** venv
*   **Path:** `~/cenv`
*   **Activation:** `source ~/cenv/bin/activate`
*   **Key Dep:** `liboqs` built from source, `oqs-python`.

**Compatibility:** Both sides MUST run compatible versions of `oqs-python` and the `secure-tunnel` codebase.

---

## 9. Installation

1.  **Clone Repository:**
    ```bash
    git clone https://github.com/project/secure-tunnel.git
    cd secure-tunnel
    ```
2.  **Install Dependencies:**
    *   Follow `liboqs` installation guide for your platform.
    *   `pip install -r requirements.txt`
    *   Ensure `import oqs` works in Python.

---

## 10. Running the System

**CRITICAL RULE:** Before *any* test run, enforce a sterile state to prevent configuration drift or residue.

### Step 1: Sterile Cleanup (Both Sides)
```bash
git reset --hard HEAD
git clean -fdx
```

### Step 2: Start GCS (Follower)
```powershell
conda activate oqs-dev
cd secure-tunnel
python -m sscheduler.sgcs
```
*GCS will wait for commands.*

### Step 3: Start Drone (Controller)
```bash
ssh dev@drone-ip
source ~/cenv/bin/activate
cd ~/secure-tunnel
sudo -E ~/cenv/bin/python -m sscheduler.sdrone
```
*Drone will connect to GCS, negotiate keys, and start traffic.*

---

## 11. Testing

*   **Unit Tests:** `pytest tests/` - Verifies crypto logic and packet framing.
*   **Loop Tests:** `python test_simple_loop.py` - Runs a local mock of both sides to verify logic without network.
*   **Integration:** Running `sdrone.py` performs a full system test with real network traffic.

---

## 12. Debugging & Observability

*   **Logs:**
    *   GCS: `logs/sscheduler/gcs/`
    *   Drone: `logs/sscheduler/drone/`
*   **Status JSON:** Proxies write `status.json` with real-time counters (packets in/out, drops, rekeys).
*   **Common Errors:**
    *   `HandshakeVerifyError`: Signature mismatch. Check `secrets/` keys.
    *   `ConnectionRefused`: GCS proxy not running or firewall blocking port 46000.
    *   `Decryption Fail (Auth)`: Wrong key or packet corruption.
    *   `Decryption Fail (Replay)`: Duplicate packet or sequence window issue.

---

## 13. Common Pitfalls

1.  **Residue:** Old `__pycache__` or `.pyc` files can cause baffling logic errors. **Always `git clean -fdx`**.
2.  **Sudo Environment:** On Linux, `sudo python` does not inherit user env vars. Use `sudo -E`.
3.  **Strict Peer Match:** The config `STRICT_UDP_PEER_MATCH = True` drops packets if the source IP doesn't match the handshake IP. Disable this if testing across complex NATs.
4.  **Time Sync:** PQC signatures and logs depend on reasonable time synchronization. Ensure NTP is active.

---

## 14. Design Lessons

*   **Strictness is Safety:** We enforce strict IP matching and sequence checking. It makes debugging harder initially but prevents security holes.
*   **Sterile State:** Distributed systems drift. The only way to trust a result is to destroy the environment and rebuild it (clean git state) before every run.

---

## 15. Extending the Project

*   **New Suites:** Add entries to `core/suites.py`. Ensure `liboqs` supports the primitives.
*   **New Schedulers:** Implement the `ControlServer` interface to drive the proxies via the JSON control plane.

---

## 16. Reproducibility Checklist

1.  [ ] **GCS:** `git status` is clean.
2.  [ ] **Drone:** `git status` is clean.
3.  [ ] **GCS:** `git clean -fdx` executed.
4.  [ ] **Drone:** `git clean -fdx` executed.
5.  [ ] **Network:** Both devices pingable.
6.  [ ] **Config:** `core/config.py` IPs match `ipconfig`/`ip addr`.
7.  [ ] **Run:** Start GCS, then Start Drone.

---

## 17. Credits & Motivation

Developed for research into **Post-Quantum UAV Security**.
The goal is to demonstrate that PQC is viable on constrained embedded hardware (Raspberry Pi) for real-time flight control.

": 5.0, "sample_count": 481, "rx_pps": 96.2, "rx_bps": 7317.8, "silence_ms": 78.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 5.9, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 15.1, "mem_pct": 88.8, "cpu_freq_mhz": 1520.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25096, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 281.00000000267755, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3176, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.6}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 96.2, "msg_rate_critical": 0.6, "msg_rate_high": 21.0}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1863}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047640772.4849, "mono_ms": 102533875.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102533796.0, "collector_loop_lag_ms": 0.0}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 546, "rx_pps": 109.2, "rx_bps": 8299.4, "silence_ms": 79.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 5.9, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 20.9, "mem_pct": 88.8, "cpu_freq_mhz": 2000.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25161, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 485.0000000005821, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3170, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.6}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 109.2, "msg_rate_critical": 0.8, "msg_rate_high": 23.8}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1864}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047640973.7188, "mono_ms": 102534078.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102534000.0, "collector_loop_lag_ms": 0.0}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 613, "rx_pps": 122.6, "rx_bps": 9318.2, "silence_ms": 78.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 5.9, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 15.5, "mem_pct": 88.8, "cpu_freq_mhz": 2000.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25228, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 687.9999999946449, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3170, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.6}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 122.6, "msg_rate_critical": 0.8, "msg_rate_high": 26.8}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1865}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047641174.5085, "mono_ms": 102534281.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102534203.0, "collector_loop_lag_ms": 0.0}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 677, "rx_pps": 135.4, "rx_bps": 10295.4, "silence_ms": 78.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 5.9, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 9.4, "mem_pct": 88.8, "cpu_freq_mhz": 2000.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25292, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 891.0000000032596, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3170, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.6}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 135.4, "msg_rate_critical": 0.8, "msg_rate_high": 29.6}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1866}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047641375.44, "mono_ms": 102534484.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102534406.0, "collector_loop_lag_ms": 0.0}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 741, "rx_pps": 148.2, "rx_bps": 11265.4, "silence_ms": 78.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 5.9, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 8.2, "mem_pct": 88.8, "cpu_freq_mhz": 2000.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25356, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 77.99999999406282, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3170, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.6}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 148.2, "msg_rate_critical": 1.0, "msg_rate_high": 32.4}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1867}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047641576.811, "mono_ms": 102534687.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102534609.0, "collector_loop_lag_ms": 0.0}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 806, "rx_pps": 161.2, "rx_bps": 12297.6, "silence_ms": 78.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 6.0, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 15.4, "mem_pct": 88.8, "cpu_freq_mhz": 2000.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25421, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 281.00000000267755, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3170, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.6}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 161.2, "msg_rate_critical": 1.0, "msg_rate_high": 35.2}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1868}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047641777.7058, "mono_ms": 102534890.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102534812.0, "collector_loop_lag_ms": 0.0}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 874, "rx_pps": 174.8, "rx_bps": 13313.6, "silence_ms": 78.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 5.9, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 21.6, "mem_pct": 88.8, "cpu_freq_mhz": 2000.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25489, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 483.99999999674037, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3176, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.5}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 174.8, "msg_rate_critical": 1.2, "msg_rate_high": 38.0}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1869}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047641978.7478, "mono_ms": 102535078.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102535015.0, "collector_loop_lag_ms": 16.00000000325963}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 939, "rx_pps": 187.8, "rx_bps": 14309.4, "silence_ms": 47.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 6.0, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 21.9, "mem_pct": 88.8, "cpu_freq_mhz": 2000.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25554, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 671.9999999913853, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3176, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.5}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 187.8, "msg_rate_critical": 1.2, "msg_rate_high": 41.0}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1870}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047642180.0332, "mono_ms": 102535281.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102535203.0, "collector_loop_lag_ms": 14.999999999417923}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 999, "rx_pps": 199.8, "rx_bps": 15192.6, "silence_ms": 63.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 6.0, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 20.8, "mem_pct": 88.8, "cpu_freq_mhz": 2000.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25614, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 875.0, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3176, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.5}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 199.8, "msg_rate_critical": 1.2, "msg_rate_high": 43.6}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1871}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047642381.1323, "mono_ms": 102535484.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102535406.0, "collector_loop_lag_ms": 0.0}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 1062, "rx_pps": 212.4, "rx_bps": 16153.6, "silence_ms": 78.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 6.0, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 21.5, "mem_pct": 88.9, "cpu_freq_mhz": 2000.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25677, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 77.99999999406282, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3176, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.5}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 212.4, "msg_rate_critical": 1.4, "msg_rate_high": 46.4}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1872}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047642583.1526, "mono_ms": 102535687.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102535609.0, "collector_loop_lag_ms": 0.0}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 1126, "rx_pps": 225.2, "rx_bps": 17127.8, "silence_ms": 78.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 6.0, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 5.4, "mem_pct": 88.9, "cpu_freq_mhz": 1520.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25741, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 281.00000000267755, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3176, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.5}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 225.2, "msg_rate_critical": 1.4, "msg_rate_high": 49.2}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1873}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047642784.779, "mono_ms": 102535890.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102535812.0, "collector_loop_lag_ms": 0.0}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 1191, "rx_pps": 238.2, "rx_bps": 18109.2, "silence_ms": 78.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 6.0, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 9.4, "mem_pct": 88.9, "cpu_freq_mhz": 2000.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25806, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 483.99999999674037, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3193, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.5}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 238.2, "msg_rate_critical": 1.6, "msg_rate_high": 52.0}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1874}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047642986.0776, "mono_ms": 102536093.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102536015.0, "collector_loop_lag_ms": 0.0}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 1254, "rx_pps": 250.8, "rx_bps": 19079.6, "silence_ms": 78.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 6.0, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 7.2, "mem_pct": 88.8, "cpu_freq_mhz": 2000.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25869, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 686.9999999908032, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3193, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.5}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 250.8, "msg_rate_critical": 1.6, "msg_rate_high": 54.8}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1875}
{"schema": "uav.pqc.telemetry.v1", "schema_ver": 1, "sender": {"role": "gcs", "node_id": "lappy", "pid": 22852}, "t": {"wall_ms": 1767047643187.1743, "mono_ms": 102536296.0, "boot_id": 1767047265}, "caps": {"pymavlink": true, "psutil": true, "proxy_status_file": false}, "state": {"gcs": {"mavproxy_alive": true, "mavproxy_pid": 12984, "qgc_alive": false, "collector_alive": true, "collector_last_tick_mono_ms": 102536218.0, "collector_loop_lag_ms": 0.0}, "suite": {"active_suite": "cs-classicmceliece348864-aesgcm-sphincs128s", "suite_epoch": 0, "pending_suite": null}}, "metrics": {"sniff": {"bind": "127.0.0.1:14552", "window_s": 5.0, "sample_count": 1320, "rx_pps": 264.0, "rx_bps": 20120.8, "silence_ms": 78.0, "gap_max_ms": 110.0, "gap_p95_ms": 0.0, "jitter_ms": 6.0, "burst_gap_count": 0, "burst_gap_threshold_ms": 200.0}, "sys": {"cpu_pct": 5.1, "mem_pct": 88.8, "cpu_freq_mhz": 2000.0, "temp_c": 0.0}}, "mav": {"decode": {"ok": 25935, "parse_errors": 0, "reason": null}, "heartbeat": {"age_ms": 889.9999999994179, "armed": false, "mode": 65536, "sysid": 1, "compid": 1}, "sys_status": {"battery_remaining_pct": 0, "voltage_battery_mv": 3193, "drop_rate_comm": 0, "errors_count": [0, 0, 0, 0], "load_pct": 54.5}, "radio_status": null, "rates": {"window_s": 5.0, "msg_rate_total": 264.0, "msg_rate_critical": 1.6, "msg_rate_high": 57.6}, "failsafe": {"flags": 0, "last_statustext": null}}, "tunnel": {"proxy_alive": true, "proxy_pid": 20672, "status_file_age_ms": 0, "counters": null}, "events": [], "seq": 1876}