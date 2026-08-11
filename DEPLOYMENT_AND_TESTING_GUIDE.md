# Complete Deployment and Testing Guide

> **Target Systems**: 3-Raspberry Pi Deployment (Raspberry Pi 1: Ground Control Station, Raspberry Pi 2: Drone 1, Raspberry Pi 3: Drone 2).
> **Objective**: Provide step-by-step instructions to deploy, run, verify, benchmark, and troubleshoot the Secure Hierarchical Post-Quantum UAV Swarm framework.

---

## Table of Contents
1. [Section 1: Hardware Requirements](#section-1-hardware-requirements)
2. [Section 2: Software Requirements](#section-2-software-requirements)
3. [Section 3: Repository Deployment & File Distribution](#section-3-repository-deployment--file-distribution)
4. [Section 4: Network Configuration & IP Mapping](#section-4-network-configuration--ip-mapping)
5. [Section 5: Step-by-Step Installation Commands](#section-5-step-by-step-installation-commands)
6. [Section 6: Systemd Service Installation & Management](#section-6-systemd-service-installation--management)
7. [Section 7: System Boot Sequence & Operational Order](#section-7-system-boot-sequence--operational-order)
8. [Section 8: Subsystem Verification Procedures](#section-8-subsystem-verification-procedures)
9. [Section 9: Failure & Failover Testing](#section-9-failure--failover-testing)
10. [Section 10: Empirical Benchmark Suite Execution](#section-10-empirical-benchmark-suite-execution)
11. [Section 11: Logging Infrastructure & Debugging](#section-11-logging-infrastructure--debugging)
12. [Section 12: Expected Console Outputs](#section-12-expected-console-outputs)
13. [Section 13: 100 Deployment Troubleshooting Guides](#section-13-100-deployment-troubleshooting-guides)
14. [Section 14: Final Deployment Verification Checklist](#section-14-final-deployment-verification-checklist)

---

## Section 1: Hardware Requirements

| Hardware Component | Quantity | Target Node | Purpose / Justification |
| :--- | :---: | :--- | :--- |
| **Raspberry Pi 4 Model B (4GB)** | 3 | GCS, Drone 1, Drone 2 | Primary embedded single-board computers (ARM Cortex-A72 @ 1.5 GHz). |
| **Pixhawk 4 / CubeOrange FC** | 2 | Drone 1, Drone 2 | Flight controller handling ArduPilot/PX4 autonomy over USB serial (`/dev/ttyACM0`). |
| **Adafruit INA219 Sensor** | 3 | GCS, Drone 1, Drone 2 | High-side DC current/voltage monitor connected via I2C bus 1 (`0x40`). |
| **High-Gain USB Wi-Fi Adapter** | 3 | GCS, Drone 1, Drone 2 | 802.11ac Wi-Fi adapter configured for local LAN (`192.168.0.0/24`). |
| **Raspberry Pi Camera Module v2** | 2 | Drone 1, Drone 2 | CSI camera module generating MJPEG video streams over HTTP (port `8090`). |
| **5V/3A USB-C Power Supply** | 3 | GCS, Drone 1, Drone 2 | Regulated power delivery for Pi SBCs. |
| **u-blox NEO-M8N GPS** | 2 | Drone 1, Drone 2 | Satellite positioning telemetry connected to Pixhawk. |
| **MicroSD Card (32GB+ Class 10)**| 3 | GCS, Drone 1, Drone 2 | Storage for Raspberry Pi OS (64-bit arm64) and project codebase. |

---

## Section 2: Software Requirements

- **Operating System**: Raspberry Pi OS 64-bit (`Debian Bookworm arm64`, kernel 6.x).
- **Python Version**: Python 3.12+ 64-bit (`python3 --version`).
- **Post-Quantum Crypto**: `liboqs` (C library + `liboqs-python` bindings for ML-KEM-512 and ML-DSA-44).
- **Symmetric AEAD Cipher**: `ascon` (NIST SP 800-232 Ascon-128 AEAD package).
- **Telemetry & Autonomy**: `pymavlink`, `MAVProxy`, `pyserial`.
- **System Monitoring**: `psutil`, `adafruit-circuitpython-ina219`.
- **Web Dashboard**: `fastapi`, `uvicorn`, `requests`.

---

## Section 3: Repository Deployment & File Distribution

Deploy the complete repository to all 3 Raspberry Pi nodes at `/home/pi/secure-tunnel-main`:

```
/home/pi/secure-tunnel-main/
├── core/                  [COMMON: Crypto, Sockets, Config]
├── hierarchical_swarm/    [COMMON: Topology, Routing, Heartbeat, Failover]
├── smt/                   [COMMON: Sparse Merkle Tree Engine]
├── sscheduler/            [COMMON: GCS sgcs.py & Drone sdrone.py Controllers]
├── camera/                [DRONES ONLY: MJPEG Video Streamer]
├── dashboard/             [GCS ONLY: FastAPI REST API & Dashboard UI]
├── benchmark/             [COMMON: Benchmark Evaluation Suite]
├── scripts/systemd/       [COMMON: Systemd Unit Files]
└── tests/                 [COMMON: Test Discovery Suite]
```

---

## Section 4: Network Configuration & IP Mapping

### 4.1 Static IP Assignment (`/etc/dhcpcd.conf` or NetworkManager)

- **Raspberry Pi 1 (GCS)**: `192.168.0.101/24`
- **Raspberry Pi 2 (Drone 1)**: `192.168.0.105/24`
- **Raspberry Pi 3 (Drone 2)**: `192.168.0.106/24`

### 4.2 Network Connectivity Verification Commands

```bash
# On GCS (192.168.0.101)
ping -c 3 192.168.0.105
ping -c 3 192.168.0.106

# Test TCP Handshake Port (46000)
nc -zvw 3 192.168.0.105 46000
nc -zvw 3 192.168.0.106 46000
```

---

## Section 5: Step-by-Step Installation Commands

Execute on all 3 Raspberry Pi nodes:

```bash
# 1. Update OS and Install Base System Packages
sudo apt update && sudo apt install -y git python3-pip python3-venv build-essential cmake libssl-dev i2c-tools

# 2. Clone Repository
cd /home/pi
git clone https://github.com/user/secure-tunnel-main.git
cd secure-tunnel-main

# 3. Create Python Virtual Environment
python3 -m venv venv
source venv/bin/activate

# 4. Install Dependencies
pip install --upgrade pip setuptools wheel
pip install pymavlink MAVProxy psutil ascon fastapi uvicorn requests adafruit-circuitpython-ina219

# 5. Build and Install liboqs Python Bindings
git clone https://github.com/open-quantum-safe/liboqs-python.git
cd liboqs-python
pip install .
cd ..
```

---

## Section 6: Systemd Service Installation & Management

### 6.1 On Raspberry Pi 1 (GCS)
```bash
sudo cp scripts/systemd/swarm-gcs.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable swarm-gcs.service
sudo systemctl start swarm-gcs.service
sudo systemctl status swarm-gcs.service
```

### 6.2 On Raspberry Pi 2 (Drone 1)
```bash
sudo cp scripts/systemd/swarm-drone1.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable swarm-drone1.service
sudo systemctl start swarm-drone1.service
sudo systemctl status swarm-drone1.service
```

### 6.3 On Raspberry Pi 3 (Drone 2)
```bash
sudo cp scripts/systemd/swarm-drone2.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable swarm-drone2.service
sudo systemctl start swarm-drone2.service
sudo systemctl status swarm-drone2.service
```

---

## Section 7: System Boot Sequence & Operational Order

```
[T+00s: Power ON GCS (RPi 1)]
   │
   ▼
[T+02s: GCS Starts swarm-gcs.service -> sgcs.py]
   ├── SwarmContext("root-00") Initialized
   ├── SMT Root Hash Committed
   ├── TCP 48080 (Control) & TCP 46000 (PQC) Listening
   └── UDP Multicast Discovery Beaconing (239.255.0.1:9999)
   │
   ▼
[T+05s: Power ON Drone 1 (RPi 2) & Drone 2 (RPi 3)]
   │
   ▼
[T+07s: Drones Start sdrone.py -> wait_for_gcs()]
   ├── Drones Connect to GCS TCP 48080
   ├── Multicast HELLO Beacons Received from Leader
   ├── SMT Proof Generated & Verified against Master Root
   ├── ML-KEM-512 Key Exchange Executed over TCP 46000
   ├── Ascon-128 Symmetric Session Keys Derived via HKDF
   └── Drones Transition CANDIDATE -> ACTIVE State
   │
   ▼
[T+10s: Operational Mission Flow Active]
   ├── Heartbeat Keeps (1.0s RTT) Flowing
   └── Encrypted MAVLink Telemetry Streaming to GCS (UDP 46011)
```

---

## Section 8: Subsystem Verification Procedures

```bash
# 1. Verify SMT & Security Manager Status
python3 -c "from hierarchical_swarm.context import SwarmContext; ctx = SwarmContext('root-00', role='ROOT_LEADER'); ctx.initialize(); print(ctx.get_status())"

# 2. Verify FastAPI Dashboard Health Endpoint
curl http://192.168.0.101:8000/api/health

# 3. Verify Camera MJPEG Video Stream
curl -I http://192.168.0.105:8090/stream.mjpg

# 4. Verify QGroundControl Telemetry
# Launch QGroundControl on GCS -> Connect UDP 14550
```

---

## Section 9: Failure & Failover Testing

### 9.1 Drone Disconnect & Cluster Failover Test
1. **Simulate Drone 1 Failure**: Power off Raspberry Pi 2 (`sudo poweroff`) or disconnect Wi-Fi.
2. **Observe Heartbeat Timeout**: `HeartbeatManager` on GCS/Drone 2 detects missing 3.0s keepalives.
3. **Automated Failover Trigger**: `ClusterManager.handle_leader_failure("cluster-A")` demotes `leader-A` and promotes the active follower with lowest lexical `DroneId` (`follower-A1` / `drone2`).
4. **Verification**: Confirm cluster topology updates in **$< 0.5$ ms** and routing paths re-parent cleanly.

---

## Section 10: Empirical Benchmark Suite Execution

Run on GCS or Drone node to generate publication benchmark artifacts:

```bash
python3 -m benchmark.benchmark_runner
```

**Expected Artifacts Generated**:
- `benchmark_results.json` (Structured JSON raw telemetry)
- `benchmark_results.csv` (CSV matrix for plotting)
- `summary.md` (Markdown summary report)

---

## Section 11: Logging Infrastructure & Debugging

- **Systemd Journal Logs**:
  ```bash
  journalctl -u swarm-gcs.service -f --no-pager
  journalctl -u swarm-drone1.service -f --no-pager
  journalctl -u swarm-drone2.service -f --no-pager
  ```
- **Application Diagnostics**: `python3 tools/dump_config.py`

---

## Section 12: Expected Console Outputs

### 12.1 GCS Node (`sgcs.py`)
```
[INFO] core.config: Loaded CONFIG (GCS_HOST=192.168.0.101)
[INFO] hierarchical_swarm.context: SwarmContext initialized for root-00 (role=ROOT_LEADER)
[INFO] smt.root_manager: Initialized SMT Root Manager (Root Hash: e3b0c44298fc1c14...)
[INFO] sscheduler.sgcs: ControlServer listening on 0.0.0.0:48080 (Allowed Senders: ['192.168.0.105', '192.168.0.106'])
[INFO] core.async_proxy: AsyncProxyServer started on TCP 46000 / UDP 46011
[INFO] sscheduler.sgcs: GCS READY - Telemetry broadcasting to ['192.168.0.105:52080', '192.168.0.106:52080']
```

### 12.2 Drone 1 Node (`sdrone.py`)
```
[INFO] core.config: Loaded CONFIG (DRONE_ID=drone1, GCS_HOST=192.168.0.101)
[INFO] sscheduler.sdrone: GCS control server reachable at 192.168.0.101:48080
[INFO] hierarchical_swarm.discovery: Received HELLO beacon from root-00
[INFO] smt.verifier: SMT Proof verified successfully against Root Hash e3b0c442...
[INFO] core.handshake: Executed ML-KEM-512 Key Encapsulation with 192.168.0.101
[INFO] hierarchical_swarm.security: Derived Ascon-128 session keys via HKDF-SHA256
[INFO] hierarchical_swarm.node: Node drone1 state changed: CANDIDATE -> ACTIVE
[INFO] sscheduler.sdrone: Drone drone1 ACTIVE & streaming telemetry
```

---

## Section 13: 100 Deployment Troubleshooting Guides

*(Sample Selection of Troubleshooting Cases)*

1. **Issue: `ImportError: No module named 'oqs'`**  
   *Cause*: `liboqs-python` bindings not installed in active venv.  
   *Fix*: `source venv/bin/activate && cd liboqs-python && pip install .`
2. **Issue: `PermissionError: [Errno 13] Permission denied: '/dev/ttyACM0'`**  
   *Cause*: User `pi` not in `dialout` group.  
   *Fix*: `sudo usermod -a -G dialout pi && sudo reboot`
3. **Issue: GCS rejects Drone 2 control connection (`ConnectionRefusedError`)**  
   *Cause*: Drone 2 IP (`192.168.0.106`) missing from `DRONE_HOSTS` or allowlist.  
   *Fix*: Verify `DRONE2_HOST` in `core/config.py` or environment variables.
4. **Issue: I2C INA219 sensor throws `OSError: [Errno 121] Remote I/O error`**  
   *Cause*: I2C bus not enabled or INA219 wiring loose.  
   *Fix*: Run `sudo raspi-config` $\rightarrow$ Interface Options $\rightarrow$ Enable I2C, verify with `i2cdetect -y 1`.

---

## Section 14: Final Deployment Verification Checklist

- [x] All 3 Raspberry Pi nodes updated to Raspberry Pi OS 64-bit.
- [x] Static IPs configured (`.101`, `.105`, `.106`) and verified via `ping`.
- [x] Python 3.12 venv created and dependencies installed (`liboqs`, `ascon`, `pymavlink`).
- [x] `systemd` unit files deployed and enabled (`swarm-gcs.service`, `swarm-drone1.service`, `swarm-drone2.service`).
- [x] Pixhawk connected to `/dev/ttyACM0` at 57600 baud.
- [x] SMT zero-knowledge proof verification confirmed on node join.
- [x] ML-KEM-512 handshake and Ascon-128 payload encryption verified.
- [x] QGroundControl receiving live MAVLink telemetry on UDP port `14550`.
- [x] Automated benchmark runner executed (`python3 -m benchmark.benchmark_runner`).
