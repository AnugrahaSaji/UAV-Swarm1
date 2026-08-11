# Thesis Research Journal

Created: 2026-05-31

This journal records the current state of the thesis work, the historical context of the experiments, what has been implemented, what has been measured, what failed, and what the next execution plan should be.

The project is now best understood as a **measurement-driven adaptive resource-control layer for secure UAV communication**, not as a replacement for the Linux kernel scheduler.

---

## 1. Working Thesis Direction

The system under study is an end-to-end secure UAV communication stack:

- Windows laptop acts as the Ground Control Station, or GCS.
- Raspberry Pi 4 acts as the drone-side companion computer.
- Pixhawk is connected to the Raspberry Pi and provides MAVLink flight-controller communication.
- A secure tunnel/proxy layer protects MAVLink traffic between GCS and drone.
- Post-quantum cryptography is used for key establishment and authentication.
- AEAD ciphers protect data-plane packets.
- A CT-3 external power meter provides high-rate power measurement.
- The scheduler/controller layer should choose CPU/core/frequency/security/IDS behavior from measured evidence.

The correct contribution framing is:

```text
Benchmark -> Energy/Latency Model -> Runtime Scheduler -> Adaptive Resource Allocation
```

The scheduler is not replacing Linux scheduling. It is a user-level adaptive resource controller that uses Linux mechanisms:

- CPU frequency governor or frequency cap
- CPU affinity
- CPU hotplug when the kernel exposes it
- process placement
- crypto profile selection
- IDS mode selection
- rekey policy
- emergency battery policy

The scheduler must preserve secure MAVLink communication first. Any power saving must be secondary to flight-control reliability.

---

## 2. Correct Hardware Statement

The Raspberry Pi 4 Model B uses a Broadcom BCM2711 SoC with a quad-core ARM Cortex-A72 64-bit CPU.

In this setup:

- CPU frequency is controlled through Linux CPU frequency scaling.
- Task placement is controlled through CPU affinity.
- Core availability can only be controlled through CPU hotplug if the kernel exposes writable `online` files for secondary CPUs.

Important caveat:

Do not claim each core can independently run at a different frequency unless the Pi exposes independent CPUFreq policies. On Raspberry Pi 4, CPUFreq commonly treats the cores as one shared frequency policy, so setting frequency usually affects the policy group rather than one isolated core.

Correct scheduler wording:

```text
core-count, frequency-policy, and task-affinity aware scheduling
```

Avoid wording like:

```text
each core gets its own independent frequency
```

---

## 3. Current Hardware and Network Context

### Windows GCS

Role:

- Ground Control Station.
- Runs the GCS side of the secure tunnel.
- Runs Python in `oqs-dev`.
- Hosts the AVHzY CT-3 power meter API through the .NET bridge.
- Can publish real-time CT-3 measurements to the Pi over UDP.

Known environment:

```text
Python: C:\Users\ashis\Miniconda3\envs\oqs-dev\python.exe
Workspace: C:\Users\ashis\OneDrive\Desktop\thesis
```

GCS Tailscale IP:

```text
100.101.93.24
```

### Raspberry Pi / Drone Side

Role:

- Drone-side companion computer.
- Runs the drone side of secure tunnel/proxy.
- Runs MAVProxy connected to Pixhawk.
- Receives CT-3 power telemetry when Windows publishes it.

SSH target:

```text
dev@100.101.93.23
```

Pi Tailscale IP:

```text
100.101.93.23
```

Observed Pi state at latest check:

```text
CPU online set: 0-3
Throttling: throttled=0x0
```

This means all four cores were online and the Pi was not reporting throttling at the time of the check.

### Pixhawk

Pixhawk was observed through MAVProxy during a successful end-to-end run:

- ArduCopter V4.5.7
- Pixhawk1 hardware
- Mode: STABILIZE
- Pre-arm warnings included RC, compass, and low-battery messages.

This confirms the tunnel test was not only synthetic crypto; the drone-side MAVProxy did see a real flight-controller endpoint.

---

## 4. Existing Project Layout

Important paths:

```text
C:\Users\ashis\OneDrive\Desktop\thesis\deep-research-report.md
C:\Users\ashis\OneDrive\Desktop\thesis\secure-tunnel-main\secure-tunnel-main
C:\Users\ashis\OneDrive\Desktop\thesis\Thesis-main\Thesis-main
C:\Users\ashis\OneDrive\Desktop\thesis\measurement
C:\Users\ashis\OneDrive\Desktop\thesis\measurements
C:\Users\ashis\OneDrive\Desktop\thesis\pi_benchmark
C:\Users\ashis\OneDrive\Desktop\thesis\skills
```

Important secure tunnel code paths:

```text
secure-tunnel-main\secure-tunnel-main\core\suites.py
secure-tunnel-main\secure-tunnel-main\core\aead.py
secure-tunnel-main\secure-tunnel-main\core\handshake.py
secure-tunnel-main\secure-tunnel-main\core\async_proxy.py
secure-tunnel-main\secure-tunnel-main\core\config.py
secure-tunnel-main\secure-tunnel-main\sscheduler
```

Earlier instruction from the user:

- Do not read `.md` files inside `secure-tunnel-main\secure-tunnel-main`.
- Code files under `core/` and `sscheduler/` were allowed for inspection.

---

## 5. Literature and Research Context

The research direction was built around several paper/reference classes.

### OS-Level Energy-Aware Scheduling

Relevant idea:

- Linux can be made energy-aware at process or scheduling granularity.
- This motivates observing workload behavior and adapting resource allocation.

How it maps here:

- The thesis does not need to modify the Linux kernel.
- Instead, it can present an application-aware user-level controller that uses available Linux knobs.

### Raspberry Pi Energy Modeling

Relevant idea:

- Raspberry Pi energy can be estimated from software-observable features.
- External measurement can calibrate a lightweight model.

How it maps here:

- CT-3 power measurements are used as ground truth.
- Pi-side features such as CPU load, frequency, online cores, temperature, and network rate can be used later for a real-time power predictor.
- The predictor can support scheduling when the external meter is unavailable.

### UAV Propulsion and System Energy Models

Relevant idea:

- UAV energy is not only computing energy.
- Flight energy depends on velocity, acceleration, direction changes, subsystem efficiency, and battery voltage dynamics.

How it maps here:

- The current experiments measure companion-computer and attached-system power, not total propulsion energy.
- The thesis should clearly separate:
  - compute/security energy
  - avionics/peripheral baseline
  - propulsion energy
  - full drone battery endurance

### Reduced CPU Energy and DVFS

Relevant idea:

- Energy can be reduced by changing CPU speed if deadlines are still satisfied.
- DVFS trades execution time, instantaneous power, and energy.

How it maps here:

- The scheduler must not blindly lower frequency.
- It must test whether lower frequency saves total energy or only increases runtime.
- Metrics must include both power and energy per completed operation or per delivered packet.

### Patterson, Buchanan, Turino 2025 PQC Embedded Benchmarking

Relevant idea:

- PQC operations on Raspberry Pi-class devices can be measured systematically.
- Energy should be tied to operation count, runtime, and external power measurement.

How it maps here:

- Their framework is used as prior art for PQC workload characterization.
- Our difference is the measurement interface and system context:
  - Their external power measurement method is not copied directly.
  - We built a CT-3 API path using the vendor protocol bridge.
  - We integrate power telemetry with secure MAVLink/PQC tunnel experiments.
  - The end goal is an adaptive scheduler, not only a static PQC benchmark.

---

## 6. AVHzY CT-3 Power Meter Work

### What Was Built

The CT-3 is accessed from Windows through a .NET bridge around the vendor protocol DLL.

Important files:

```text
measurement\ct3_dotnet_bridge.cs
measurement\ct3_dotnet_bridge.exe
measurement\ct3_dotnet_api.py
measurement\ct3_linux_api.py
pi_benchmark\windows_ct3_udp_publisher.py
pi_benchmark\pi_power_udp_receiver.py
```

The current practical architecture:

```text
CT-3 meter -> Windows USB/libusb/.NET bridge -> Python API -> UDP telemetry -> Raspberry Pi scheduler
```

This avoids loading the Pi with CT-3 USB parsing during Pi workload tests.

### CT-3 Capabilities Observed

The CT-3 was successfully sampled from Windows at approximately 1 kHz.

Recent check:

```text
Output: measurements\ct3_live_checks\ct3_probe_after_baseline_20260531.csv
Samples: 2000
Duration: 1.985 s
Sample rate: 1007.56 Hz
Average power: 3.132 W
Energy: 6.218 J
```

Earlier check:

```text
Output: measurements\ct3_live_checks\ct3_probe_20260531.csv
Samples: 2010
Duration: 1.994 s
Sample rate: 1008.02 Hz
Average power: 3.054 W
Energy: 6.091 J
```

Interpretation:

- The CT-3 API path is working.
- The meter can provide approximately 1 kHz samples.
- Short captures are stable enough for benchmark windows.

### CT-3 Reliability Caveat

During the first core-count baseline attempt, two CT-3 recorder starts failed with:

```text
GeneralRequest[Ping]: Wait for reply timeout
```

This caused missing active power rows for core requests 1 and 3.

Action taken:

- `pi_benchmark\core_count_power_baseline.py` was patched to retry CT-3 stream startup and require the first sample before beginning a run.

Current status:

- The patch has been written.
- The patched full baseline has not yet been rerun after the user interrupted the work.

---

## 7. GCS Cryptography Availability

The GCS cryptography registry was tested directly, without starting the full tunnel.

Result file:

```text
measurements\e2e_preflight\gcs_crypto_registry_smoke_hqc_20260531.json
```

### KEM Status

After rebuilding liboqs with HQC enabled:

```text
KEMs OK: 9 / 9
```

Working KEMs:

```text
ML-KEM-512
ML-KEM-768
ML-KEM-1024
Classic-McEliece-348864
Classic-McEliece-460896
Classic-McEliece-8192128
HQC-128
HQC-192
HQC-256
```

### Signature Status

```text
Signatures OK: 8 / 8
```

Working signatures:

```text
ML-DSA-44
ML-DSA-65
ML-DSA-87
Falcon-512
Falcon-1024
SPHINCS+-SHA2-128s-simple
SPHINCS+-SHA2-192s-simple
SPHINCS+-SHA2-256s-simple
```

### AEAD Status

```text
AEADs OK: 7 / 9
```

Working AEADs:

```text
aesgcm128
aesgcm192
aesgcm256
aesccm128
aesccm192
aesccm256
chacha20poly1305
```

Not working:

```text
ascon128
aegis256
```

Reasons:

- `ascon128`: native `libasconaead128.dll` is missing.
- `aegis256`: appears in the registry, but `core\aead.py` does not currently accept it in `_SUPPORTED_AEAD_TOKENS`.

### HQC Rebuild Details

Rebuilt local liboqs source:

```text
C:\msys64\home\ashis\liboqs
```

Installed updated DLL:

```text
C:\msys64\home\ashis\oqs-install\bin\liboqs.dll
```

Old DLL backup:

```text
C:\msys64\home\ashis\oqs-install\bin\liboqs.dll.before_hqc_20260531_140104.bak
```

Enabled flags:

```text
OQS_ENABLE_KEM_HQC=ON
OQS_ENABLE_KEM_hqc_128=ON
OQS_ENABLE_KEM_hqc_192=ON
OQS_ENABLE_KEM_hqc_256=ON
```

Direct verification:

```text
HQC-128  public_key=2249  ciphertext=4433   shared_secret=64  OK
HQC-192  public_key=4522  ciphertext=8978   shared_secret=64  OK
HQC-256  public_key=7245  ciphertext=14421  shared_secret=64  OK
```

Remaining warning:

```text
liboqs 0.15.0-rc1 differs from liboqs-python 0.14.1
```

This is a reproducibility warning, not an immediate blocker for the algorithms that passed smoke tests.

---

## 8. Suite Registry and Security-Level Policy

The secure tunnel separates:

- KEM/SIG suite identity
- AEAD data-plane profile

Important file:

```text
secure-tunnel-main\secure-tunnel-main\core\suites.py
```

After HQC rebuild:

```text
Suites after runtime prune: 24
Runtime suites: 3
Benchmark suites: 24
```

Runtime/scheduler-allowed suites:

```text
cs-mlkem512-mldsa44
cs-mlkem768-mldsa65
cs-mlkem1024-mldsa87
```

Benchmark-only HQC suites now available:

```text
cs-hqc128-falcon512
cs-hqc128-mldsa44
cs-hqc128-sphincs128s
cs-hqc192-mldsa65
cs-hqc192-sphincs192s
cs-hqc256-falcon1024
cs-hqc256-mldsa87
cs-hqc256-sphincs256s
```

AEAD level policy:

```text
L1 -> aesgcm128, aesccm128, ascon128
L3 -> aesgcm192, aesccm192
L5 -> aesgcm256, aesccm256, chacha20poly1305
```

Practical current AEAD policy, because Ascon is not built:

```text
L1 -> aesgcm128, aesccm128
L3 -> aesgcm192, aesccm192
L5 -> aesgcm256, aesccm256, chacha20poly1305
```

Important example:

```text
cs-mlkem768-mldsa65 is L3
```

Therefore valid AEADs for it are:

```text
aesgcm192
aesccm192
```

Not:

```text
aesgcm256
```

unless the policy is explicitly changed.

---

## 9. Successful End-to-End Secure MAVLink Run

A live GCS-to-Pi secure tunnel test completed successfully.

Run directory:

```text
measurements\e2e_mavlink_grid_live\20260531_133009
```

Specific run:

```text
measurements\e2e_mavlink_grid_live\20260531_133009\cs-mlkem768-mldsa65__aesgcm192
```

Command used:

```powershell
& "C:\Users\ashis\Miniconda3\envs\oqs-dev\python.exe" .\pi_benchmark\e2e_mavlink_power_grid.py --execute --gcs-host 100.101.93.24 --suites cs-mlkem768-mldsa65 --aeads aesgcm192 --duration 20 --pre-s 5 --post-s 5 --output-dir .\measurements\e2e_mavlink_grid_live
```

Result:

```text
drone_returncode: 0
drone_timed_out: false
```

The drone side reported:

```text
Suite ACTIVE: cs-mlkem768-mldsa65 / aesgcm192
Deterministic benchmark run COMPLETE
```

Observed handshake metrics from Pi status:

```text
Handshake total: 47.246708 ms
KEM encaps: 0.285091 ms
SIG verify: 0.943589 ms
AEAD encrypt avg: 0.092553 ms
AEAD decrypt avg: 0.123729 ms
KEM public key: 1184 bytes
Ciphertext: 1088 bytes
Signature: 3309 bytes
Shared secret: 32 bytes
```

Packet counters from drone status snapshot:

```text
ptx_out: 43
ptx_in: 473
enc_out: 473
enc_in: 43
drops: 0
drop_auth: 0
drop_replay: 0
```

Power telemetry summary from the run:

```text
printed_records: 44
last_sent_packet_count: 2200
power_w_mean_printed: 3.658 W
power_w_min_printed: 3.268 W
power_w_max_printed: 4.146 W
ewma_1s_last_w: 3.283 W
sample_rate_hz_mean_printed: 963.79 Hz
sample_rate_hz_min_printed: 928.28 Hz
sample_rate_hz_max_printed: 1140.38 Hz
```

Interpretation:

- The GCS and Pi secure tunnel can activate a PQC suite and AEAD profile.
- The CT-3 telemetry path can run during the end-to-end experiment.
- MAVProxy saw the Pixhawk.
- The run was low traffic, likely heartbeat/telemetry dominated, not a high-rate MAVLink stress condition.

---

## 10. Firewall and Network State

Windows firewall rules were added and verified.

Rules:

```text
PQC Tunnel Benchmark TCP
PQC Tunnel Benchmark UDP
```

Allowed TCP ports:

```text
46000,48080
```

Allowed UDP ports:

```text
46011,46012,47001,47002,14550,14551,14552,14553,52080,50601
```

These are required for:

- tunnel TCP handshake
- scheduler/control traffic
- encrypted UDP data plane
- MAVLink/MAVProxy routing
- CT-3 power telemetry

---

## 11. Skill and Agent Knowledge Setup

A skills workspace was created.

Repo dump:

```text
skills\repo-dump
```

Custom skills:

```text
skills\custom-skills
```

Codex skill install path:

```text
C:\Users\ashis\.codex\skills
```

Installed project-focused skills:

```text
linux-infra
ssh-security
tunnel-engineering
network-debugging
linux-hardening
post-quantum
secure-coding
devops
crypto-engineering
agent-engineering
raspberry-pi-power-benchmarking
pqc-tunnel-benchmarking
```

Official OpenAI curated skills installed:

```text
security-best-practices
security-threat-model
pdf
jupyter-notebook
```

Manifest:

```text
skills\skill-install-manifest.md
```

Note:

Codex must be restarted to fully pick up newly installed skills in future turns.

---

## 12. Scheduler Concept as of Now

The scheduler should protect three priority levels.

### Level 1: Mission-Critical Tasks

These must not be stopped during flight:

- MAVLink proxy
- encryption/decryption path
- telemetry forwarding
- command forwarding
- Pixhawk communication

Scheduler rule:

```text
Never sacrifice secure MAVLink continuity for power saving.
```

### Level 2: Security-Enhancement Tasks

These improve security but can be degraded:

- XGBoost DDoS detector
- TST detector
- hybrid IDS mode
- frequent rekeying
- higher-cost PQC profiles

Scheduler rule:

```text
Adjust these according to battery, thermal state, threat level, and communication health.
```

### Level 3: Non-Critical Support Tasks

These can be delayed or disabled:

- verbose logging
- high-frequency telemetry recording
- debug printing
- nonessential background scripts

Scheduler rule:

```text
Disable these first when power, CPU, or thermal pressure rises.
```

---

## 13. Scheduler Inputs

The runtime controller should observe:

```text
battery level
CPU temperature
throttling flag
CPU utilization per process
power draw from CT-3 or calibrated model
packet loss
RTT / latency
MAVLink delivery health
IDS threat level
mission phase
IDS queue delay
```

These inputs make the scheduler scientific and measurable rather than trial-and-error.

---

## 14. Scheduler Actions

Candidate actions:

```text
change CPU governor
change frequency cap
change CPU affinity
change worker/core budget
change IDS mode
change AEAD profile
change PQC suite level
change rekey interval
enter emergency mode
reduce nonessential logging
```

Current limitation:

The current Pi kernel does not expose writable hotplug `online` files for CPU1-CPU3.

Observed:

```text
/sys/devices/system/cpu/cpu1/online: not present
/sys/devices/system/cpu/cpu2/online: not present
/sys/devices/system/cpu/cpu3/online: not present
```

Attempting to write CPU online state failed:

```text
tee: /sys/devices/system/cpu/cpu3/online: Permission denied
cat: /sys/devices/system/cpu/cpu3/online: No such file or directory
```

Therefore the immediate benchmark should be framed as:

```text
worker-count and CPU-affinity comparison with all hardware cores online
```

not:

```text
physical core hotplug comparison
```

unless the Pi kernel/boot configuration is changed to expose CPU hotplug.

---

## 15. Scheduler Operating Modes

Suggested operating modes:

### Performance Mode

Condition:

```text
high battery, high threat, no thermal issue
```

Behavior:

```text
more cores/workers
higher frequency policy
hybrid IDS
strong PQC/security profile
shorter rekey interval if needed
```

### Balanced Mode

Condition:

```text
normal flight
```

Behavior:

```text
moderate core budget
medium frequency policy
XGBoost active
TST conditional
runtime-approved PQC profile
```

### Energy-Saving Mode

Condition:

```text
battery reducing or temperature high
```

Behavior:

```text
lower frequency policy
reduced worker/core budget
XGBoost only
longer rekey interval
reduced logging
```

### Emergency Mode

Condition:

```text
battery below threshold, for example below 20%
```

Behavior:

```text
preserve encrypted MAVLink only
disable TST
possibly disable IDS
reduce logging
avoid expensive rekeys unless required
```

### Threat-Response Mode

Condition:

```text
DDoS or traffic anomaly suspected
```

Behavior:

```text
temporarily activate TST
increase compute budget
increase monitoring
preserve link reliability
```

### Thermal-Protection Mode

Condition:

```text
high temperature or throttling flag
```

Behavior:

```text
reduce frequency
reduce heavy IDS use
preserve proxy and MAVLink path
```

---

## 16. IDS Strategy

The strongest scheduler idea is conditional TST activation.

Instead of running the Time Series Transformer continuously:

```text
XGBoost runs as a lightweight first-stage screener.
TST runs only when traffic becomes suspicious or high-risk.
```

Trigger conditions for TST:

```text
XGBoost flags suspicious traffic
packet rate increases abnormally
packet loss or latency pattern indicates attack
threat level becomes high
mission phase requires stronger security
```

This gives the thesis a clear power-saving argument:

```text
Do not continuously run the expensive detector when a cheap detector can filter normal traffic.
```

---

## 17. Baseline Core/Worker Count Work

A new baseline orchestrator was added:

```text
pi_benchmark\core_count_power_baseline.py
```

Purpose:

- Runs on Windows.
- Uses CT-3 locally through the .NET bridge.
- Controls Pi over SSH.
- Attempts CPU hotplug if available.
- Runs Pi AEAD workload.
- Records CT-3 samples.
- Writes summary JSON/CSV.

Initial command run:

```powershell
& "C:\Users\ashis\Miniconda3\envs\oqs-dev\python.exe" .\pi_benchmark\core_count_power_baseline.py --pi dev@100.101.93.23 --algorithm aes256gcm --cycles 300000 --payload-size 1024 --repeat 1 --pre-s 5 --post-s 5 --settle-s 2 --output-dir .\measurements\core_count_baseline
```

Output directory:

```text
measurements\core_count_baseline\20260531_175550
```

### Initial Result Caveat

This run should be treated as a partial/diagnostic run, not the final baseline.

Reasons:

1. CPU hotplug did not actually change active hardware cores.
2. CT-3 stream startup failed for the 1-core and 3-core rows.
3. The script was patched after this run to retry CT-3 startup and label the mode correctly.
4. The patched script has not yet been rerun.

### Workload Results from Diagnostic Run

The workload itself completed for all requested worker counts.

AES-256-GCM, 300,000 total cycles, 1024-byte payload:

```text
requested workers/cores: 1
wall_s: 6.723
ops_per_s: 44,621
worker_cpu_percent_total: 99.39%
power: missing due CT-3 stream timeout
```

```text
requested workers/cores: 2
wall_s: 3.413
ops_per_s: 87,906
worker_cpu_percent_total: 197.19%
active_power_mean_w: 4.652 W
active_power_p95_w: 5.021 W
active_energy_j: 17.668 J
ops_per_j: 16,980
joules_per_10k_ops: 0.589
active samples: 3810
sample_rate_hz: 1002.90
```

```text
requested workers/cores: 3
wall_s: 2.320
ops_per_s: 129,301
worker_cpu_percent_total: 292.05%
power: missing due CT-3 stream timeout
```

```text
requested workers/cores: 4
wall_s: 1.807
ops_per_s: 165,991
worker_cpu_percent_total: 382.23%
active_power_mean_w: 5.814 W
active_power_p95_w: 6.741 W
active_energy_j: 12.954 J
ops_per_j: 23,158
joules_per_10k_ops: 0.432
active samples: 2240
sample_rate_hz: 1004.94
```

### Early Interpretation

Only the rows with power data can be compared energetically.

From those rows:

- 4 workers had higher instantaneous power than 2 workers.
- 4 workers finished much faster.
- Total active energy for 4 workers was lower than for 2 workers in this diagnostic run.

This suggests a possible race-to-idle behavior for AES-256-GCM at this workload size:

```text
higher parallelism -> higher power but shorter time -> lower total joules
```

But this is not final because:

- rows 1 and 3 are missing power
- hotplug was unavailable
- repeat count was 1
- frequency was governed by `ondemand`
- workload was synthetic AES only, not full tunnel/IDS/MAVLink

---

## 18. Benchmarking Plan Going Forward

The next work must proceed in layers.

### Phase A: Clean Baseline Re-Run

Goal:

```text
Produce reliable 1/2/3/4 worker-count AES-256-GCM baseline with CT-3 power for every row.
```

Method:

- Use patched `core_count_power_baseline.py`.
- Label mode as affinity-only if hotplug unavailable.
- Keep all hardware cores online.
- Run worker counts 1, 2, 3, 4.
- Use fixed total cycles.
- Use CT-3 retry startup.
- Use at least 3 repeats.
- Record Pi temperature and throttling before/after each row.

Suggested command:

```powershell
& "C:\Users\ashis\Miniconda3\envs\oqs-dev\python.exe" .\pi_benchmark\core_count_power_baseline.py --pi dev@100.101.93.23 --algorithm aes256gcm --cycles 300000 --payload-size 1024 --repeat 1 --pre-s 5 --post-s 5 --settle-s 2 --output-dir .\measurements\core_count_baseline
```

After the next successful run, update this journal with:

- all four power rows
- energy per 10k operations
- ops/s
- mean and p95 power
- temperature rise
- throttling status

### Phase B: AEAD Matrix

Goal:

Compare data-plane AEADs:

```text
aesgcm128
aesgcm192
aesgcm256
aesccm128
aesccm192
aesccm256
chacha20poly1305
```

For each:

```text
worker count: 1,2,3,4
payload sizes: 64,256,1024,4096
governor: ondemand first
repeat: at least 3
```

Metrics:

```text
ops/s
mean power
p95 power
energy
joules per 10k operations
temperature
throttling
```

### Phase C: DVFS/Frequency Policy

Goal:

Understand energy/runtime tradeoff under fixed frequency or governor modes.

Frequency points proposed earlier:

```text
600 MHz
900 MHz
1.2 GHz
1.5 GHz
1.8 GHz
```

Need first verify available Pi frequency controls:

```text
/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_frequencies
/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors
```

Metrics:

- runtime
- power
- energy
- throttling
- ops/joule

### Phase D: Full Secure Tunnel Benchmark

Goal:

Run end-to-end secure MAVLink workloads across valid suite/AEAD pairs.

Use runtime suites:

```text
cs-mlkem512-mldsa44
cs-mlkem768-mldsa65
cs-mlkem1024-mldsa87
```

Use valid AEADs by level:

```text
L1: aesgcm128, aesccm128
L3: aesgcm192, aesccm192
L5: aesgcm256, aesccm256, chacha20poly1305
```

Measure:

- handshake time
- rekey time
- AEAD encrypt/decrypt latency
- packet counters
- drop counters
- power
- energy
- MAVLink delivery rate
- latency

### Phase E: Benchmark-Only PQC Suite Exploration

Goal:

Benchmark all 24 registry suites, including HQC and Classic McEliece.

These should be clearly labeled:

```text
benchmark-only, not runtime scheduler default
```

This helps thesis comparison but should not be confused with flight-ready runtime policy.

### Phase F: IDS Integration

Goal:

Measure:

- no IDS
- XGBoost only
- TST only
- hybrid XGBoost -> conditional TST

Metrics:

- power
- inference latency
- CPU utilization
- detection accuracy
- effect on MAVLink delivery
- thermal behavior

### Phase G: Scheduler Policy Evaluation

Goal:

Compare:

```text
default Linux behavior
fixed high-performance configuration
static low-power configuration
adaptive scheduler
```

Success metric:

```text
energy saved without violating communication reliability
```

Reliability constraints should include:

- no authentication drops
- no replay drops
- MAVLink delivery remains acceptable
- command/telemetry latency stays within threshold
- no thermal throttling

---

## 19. Current Code Additions and Patch State

Added:

```text
pi_benchmark\core_count_power_baseline.py
```

Purpose:

- Windows-side orchestration of Pi AEAD workload and CT-3 capture.
- Produces:
  - `summary.json`
  - `summary.csv`
  - per-run CT-3 CSV files

Patched after diagnostic run:

- Added CT-3 startup retry.
- Added first-sample wait before beginning a row.
- Added hotplug capability detection.
- Added `core_control_mode` labeling.

Current status:

```text
patched but not rerun after patch
```

Important:

The diagnostic summary file was created before these patch improvements, so its rows do not yet include `core_control_mode`.

---

## 20. Current Known Issues

### Issue 1: CPU Hotplug Unavailable

The Pi currently does not expose secondary CPU `online` files.

Impact:

- Cannot claim true physical active-core-count control yet.
- Can still evaluate worker-count and CPU-affinity control.

Next:

- Investigate Pi kernel/boot configuration if true hotplug is required.
- Otherwise present this as affinity-aware scheduling.

### Issue 2: CT-3 Stream Startup Can Timeout

Observed during first core baseline:

```text
GeneralRequest[Ping]: Wait for reply timeout
```

Impact:

- Some benchmark rows may have missing power if stream startup fails.

Mitigation:

- Added retry and first-sample check in `core_count_power_baseline.py`.

Next:

- Rerun baseline and confirm no missing rows.

### Issue 3: Ascon Not Built

Impact:

- `ascon128` cannot be included in AEAD benchmarks yet.

Next:

```powershell
& "C:\Users\ashis\Miniconda3\envs\oqs-dev\python.exe" -m core.build_ascon_aead128
```

Then rerun AEAD smoke test.

### Issue 4: AEGIS Registry/Implementation Mismatch

Impact:

- `aegis256` appears in the registry but is not accepted by `core\aead.py`.

Next:

- Either add it to `_SUPPORTED_AEAD_TOKENS` and verify `pysodium`/libsodium support, or remove it from benchmark scope.

### Issue 5: liboqs/liboqs-python Version Mismatch

Impact:

- Warning remains during OQS import.
- Algorithms tested are working, but reproducibility should document this mismatch.

Next:

- Consider aligning `liboqs-python` with `liboqs 0.15.0-rc1` if available, or pin current build in methodology.

### Issue 6: Low-Rate End-to-End MAVLink Run

Impact:

- Successful E2E tunnel proves activation, but not high-load communication behavior.

Next:

- Add controlled MAVLink/high-rate traffic modes.
- Measure packet latency, loss, and energy under real traffic pressure.

---

## 21. Immediate Next Plan

The next practical sequence should be:

1. Rerun the patched core-count/worker-count baseline.
2. Confirm all four rows have CT-3 power samples.
3. Update this journal with clean results.
4. Expand to AEAD matrix.
5. Add fixed-frequency/DVFS grid.
6. Re-run valid end-to-end tunnel suites.
7. Add IDS workloads.
8. Build the adaptive scheduler policy from benchmark evidence.

Concrete next command:

```powershell
& "C:\Users\ashis\Miniconda3\envs\oqs-dev\python.exe" .\pi_benchmark\core_count_power_baseline.py --pi dev@100.101.93.23 --algorithm aes256gcm --cycles 300000 --payload-size 1024 --repeat 1 --pre-s 5 --post-s 5 --settle-s 2 --output-dir .\measurements\core_count_baseline
```

Before running:

```powershell
& "C:\Users\ashis\Miniconda3\envs\oqs-dev\python.exe" .\measurement\ct3_dotnet_api.py list
```

Expected:

```text
CT-3 visible
in_use: false
```

After running:

Check:

```text
summary.json
summary.csv
cores_1_ct3.csv
cores_2_ct3.csv
cores_3_ct3.csv
cores_4_ct3.csv
```

All four rows should have:

```text
active samples > 0
sample rate near 1000 Hz
returncode = 0
throttled = 0x0
```

---

## 22. Current Bottom Line

What is proven:

- CT-3 can be accessed from Windows with approximately 1 kHz sampling.
- Windows can send/measure power data without loading the Pi with CT-3 USB parsing.
- Pi is reachable over SSH at `dev@100.101.93.23`.
- GCS and Pi can run the secure tunnel end-to-end over Tailscale.
- PQC suite `cs-mlkem768-mldsa65` with `aesgcm192` completed successfully.
- HQC is now enabled and working on the GCS liboqs build.
- The GCS supports all 9 configured KEMs and all 8 configured signatures.
- A scheduler framing is now clear: measurement-driven user-level adaptive resource controller.

What is not yet proven:

- Clean 1/2/3/4 worker-count power baseline with complete power for all rows.
- True CPU hotplug control on this Pi.
- DVFS/frequency energy optimum.
- Full AEAD matrix.
- Full PQC suite matrix.
- IDS workload energy and latency.
- Adaptive scheduler superiority over static policies.

Most important next milestone:

```text
Produce a clean, complete AES-256-GCM worker-count baseline with CT-3 power for all 1/2/3/4 configurations.
```

---

## 23. Corrected Benchmarking Understanding: Handshake vs Always-On AEAD

Updated from user discussion on 2026-05-31:

The benchmark plan must distinguish **episodic handshake cost** from **continuous data-plane cost**.

KEM and digital signatures do not run continuously during normal flight. They run during:

- initial secure tunnel setup
- full PQC rekey
- suite switch that changes KEM/SIG identity

Therefore, KEM and signature costs should be measured as handshake/rekey overhead:

```text
handshake_time_ms
KEM_keygen_ms
KEM_encaps_ms
KEM_decaps_ms
signature_sign_ms
signature_verify_ms
handshake_energy_j
rekey_pause_ms
```

But during normal operation, the recurring cost is the AEAD data plane:

```text
MAVLink packet -> AEAD encrypt -> network -> AEAD decrypt -> MAVLink packet
```

So the scheduler's steady-state energy model must focus on:

- baseline Pi/peripheral power
- AEAD encryption/decryption cost
- packet rate
- payload size
- CPU frequency
- worker/core-affinity budget
- temperature/throttling

Correct interpretation:

```text
Handshake cost matters, but it is amortized over the session.
AEAD cost matters continuously because it runs for every protected packet.
```

This means the thesis should not overstate KEM/signature as always-running costs. The steady-state benchmark should mainly characterize AEAD and real MAVLink traffic.

---

## 24. Area-Under-Curve Energy Method

The CT-3 provides approximately 1000 Hz power samples. Energy should be computed as the area under the power curve, not only as average power.

For samples:

```text
(t0, P0), (t1, P1), ..., (tn, Pn)
```

Use trapezoidal integration:

```text
E = sum(((P_i + P_{i-1}) / 2) * (t_i - t_{i-1}))
```

Where:

```text
E = energy in joules
P = power in watts
t = timestamp in seconds
```

For active workload energy:

```text
E_active = AUC over active workload window
```

For baseline energy over the same duration:

```text
E_baseline_equivalent = P_baseline_mean * active_duration
```

For workload-only excess energy:

```text
E_excess = E_active - E_baseline_equivalent
```

This gives two useful views:

1. Total system energy during the operation.
2. Incremental energy attributable to the workload above baseline.

Both are important:

- Total energy matters for battery drain.
- Excess energy helps isolate encryption workload cost.

---

## 25. Real MAVLink Load vs Synthetic Constant Load

The real MAVLink workload may encrypt far fewer bytes/packets than a synthetic 10k or 100k encryption benchmark.

Therefore both workload classes are needed:

### Constant Synthetic Load

Purpose:

- stable repeatable stress
- clear comparison across frequency/core/AEAD settings
- enough operations to rise above meter noise
- useful for model fitting

Example:

```text
300000 AES-GCM encryptions over 1024-byte payload
```

### Real End-to-End MAVLink Load

Purpose:

- represents actual drone/GCS traffic
- lower packet rate
- smaller payloads
- includes real proxy overhead
- validates that synthetic conclusions do not break real communication

Example:

```text
Pixhawk -> MAVProxy -> secure proxy -> encrypted link -> GCS proxy -> GCS MAVProxy
```

Important thesis point:

```text
Synthetic crypto benchmarks find the envelope.
Real MAVLink benchmarks validate operational impact.
```

The scheduler should be trained/evaluated with both.

---

## 26. Full Frequency and Core/Grid Benchmark Requirement

The Pi exposes one CPUFreq policy shared by CPUs 0-3.

Observed policy:

```text
policy0 affected_cpus: 0 1 2 3
available frequencies:
600000 700000 800000 900000 1000000 1100000 1200000 1300000 1400000 1500000 1600000 1700000 1800000
available governors:
conservative ondemand userspace powersave performance schedutil
```

Therefore the correct grid is:

```text
frequencies: 600 MHz to 1800 MHz in 100 MHz steps
requested worker/core-affinity counts: 1, 2, 3, 4
```

Important limitation:

CPU hotplug files are not exposed on this Pi, so current experiments are:

```text
affinity/core-budget experiments with all hardware cores online
```

not:

```text
true physical core-offline experiments
```

The benchmark script must label this explicitly.

---

## 27. New Measurement-Driven Grid Script

Added:

```text
pi_benchmark\measurement_driven_power_grid.py
```

Purpose:

- run on Windows GCS
- control Raspberry Pi over SSH
- set Pi CPU frequency through `/sys/devices/system/cpu/cpufreq/policy0`
- attempt core hotplug if available
- otherwise use worker/core-affinity budget
- record CT-3 samples locally at approximately 1000 Hz
- measure no-load baseline for each configuration
- measure AEAD active workload for each configuration
- compute AUC energy and excess energy over baseline
- write JSON, CSV, and per-window CT-3 sample files

Default workload:

```text
/home/dev/pi_benchmark/pi_aead_workload.py
```

Default algorithm:

```text
aes256gcm
```

Main output:

```text
summary.json
summary.csv
*_baseline_ct3.csv
*_active_ct3.csv
```

Key metrics produced:

```text
baseline_power_mean_w
active_power_mean_w
active_power_p95_w
active_energy_j
excess_energy_j
joules_per_10k_ops
excess_joules_per_10k_ops
ops_per_j
excess_ops_per_j
active_sample_rate_hz
temperature before/after
```

---

## 28. Measurement Grid Smoke Test

Smoke test command:

```powershell
& "C:\Users\ashis\Miniconda3\envs\oqs-dev\python.exe" .\pi_benchmark\measurement_driven_power_grid.py --pi dev@100.101.93.23 --frequencies 600000 --core-counts 1 --cycles 1000 --payload-size 1024 --baseline-s 1 --pre-s 1 --post-s 1 --settle-s 1 --repeats 1 --output-dir .\measurements\measurement_driven_grid_smoke
```

Output:

```text
measurements\measurement_driven_grid_smoke\20260531_203639
```

Smoke result:

```text
frequency_hz: 600000
requested_cores: 1
core_control_mode: affinity_only_hotplug_unavailable
algorithm: aes256gcm
payload_size: 1024
cycles: 1000
returncode: 0
wall_s: 0.290861
ops_per_s: 3438.07
baseline_power_mean_w: 2.83685
active_power_mean_w: 3.00351
active_power_p95_w: 3.34658
active_energy_j: 2.85033
excess_energy_j: 0.158159
joules_per_10k_ops: 28.5033
excess_joules_per_10k_ops: 1.58159
active_samples: 970
active_sample_rate_hz: 1021.07
temp_before_mC: 39920
temp_after_mC: 39920
```

Interpretation:

- CT-3 capture worked.
- Pi frequency control worked at 600 MHz.
- AEAD workload executed successfully.
- AUC energy and excess energy calculations worked.
- Pi policy was restored afterward.

Post-smoke Pi state:

```text
governor: ondemand
min_freq: 600000
max_freq: 1800000
online CPUs: 0-3
throttled=0x0
```

---

## 29. Next Correct Full Grid Command

The next full synthetic AEAD grid should use all frequency steps and all worker/core-affinity counts.

Recommended first full grid:

```powershell
& "C:\Users\ashis\Miniconda3\envs\oqs-dev\python.exe" .\pi_benchmark\measurement_driven_power_grid.py --pi dev@100.101.93.23 --algorithm aes256gcm --cycles 300000 --payload-size 1024 --frequencies auto --core-counts 1,2,3,4 --baseline-s 5 --pre-s 3 --post-s 3 --settle-s 2 --repeats 1 --output-dir .\measurements\measurement_driven_grid
```

Expected grid size:

```text
13 frequencies * 4 worker counts * 1 repeat = 52 active workload rows
```

Each row includes a baseline window and active AEAD window.

Approximate runtime depends on workload duration, but this is a real experiment and should be allowed to run patiently.

After the first full grid:

1. Check for missing CT-3 samples.
2. Check `returncode = 0` for every row.
3. Check `active_sample_rate_hz` near 1000 Hz.
4. Check `throttled=0x0`.
5. Identify frequency/core setting with best:
   - lowest joules per 10k ops
   - lowest excess joules per 10k ops
   - acceptable latency/runtime

---

## 30. Correction: True Core-Off Benchmarking

The earlier grid used worker count plus process affinity when runtime CPU hotplug was unavailable. That is useful for measuring how many worker processes are used, but it is not the same as physically turning cores off.

The Raspberry Pi currently reports:

```text
/sys/devices/system/cpu/online = 0-3
/sys/devices/system/cpu/possible = 0-3
/sys/devices/system/cpu/cpu1/online = missing
```

Because the per-core `online` files are missing, this kernel does not expose runtime CPU hotplug. The corrected benchmark code now treats this as a hard stop for `--core-control hotplug`; it no longer silently falls back to affinity.

Follow-up inspection showed a more precise kernel-level picture:

```text
kernel: 6.12.47+rpt-rpi-v8
CONFIG_HOTPLUG_CPU=y
/sys/devices/system/cpu/cpuX/online = missing
/sys/devices/system/cpu/cpuX/hotplug/state = 237
/sys/devices/system/cpu/cpuX/hotplug/target = present
/sys/devices/system/cpu/hotplug/states includes "0: offline" and "237: online"
```

So CPU hotplug is compiled into the kernel, but this Raspberry Pi platform does not accept runtime CPU offlining through the exposed `hotplug/target` interface. A controlled CPU3 test failed with:

```text
tee: /sys/devices/system/cpu/cpu3/hotplug/target: Operation not supported
```

The Pi remained normal after the test:

```text
online CPUs: 0-3
cpu0..cpu3 hotplug state: 237
governor: ondemand
min/max: 600000/1800000
```

The benchmark code was updated again so it tries both runtime interfaces:

1. `/sys/devices/system/cpu/cpuX/online`
2. `/sys/devices/system/cpu/cpuX/hotplug/target`

If both are unavailable or the kernel returns `Operation not supported`, the correct conclusion is not that the scripts failed. The correct conclusion is that this Pi kernel/platform combination cannot runtime-offline cores. Boot-time `maxcpus=N` remains the valid true core-off method.

For this Pi, true core-count experiments must use boot-time CPU limiting:

```text
maxcpus=1
maxcpus=2
maxcpus=3
no maxcpus argument for 4 cores
```

The boot-time runner is:

```powershell
.\pi_benchmark\run_measurement_grid.ps1 -Mode boot-dry-run
.\pi_benchmark\run_measurement_grid.ps1 -Mode boot-smoke
.\pi_benchmark\run_measurement_grid.ps1 -Mode boot-full
```

`boot-dry-run` only prints the planned `/boot/firmware/cmdline.txt` values and does not reboot or edit the Pi. It verified the planned states on 2026-05-31:

```text
1 core: append maxcpus=1
2 cores: append maxcpus=2
3 cores: append maxcpus=3
4 cores: restore original cmdline with no maxcpus
```

`boot-smoke` and `boot-full` will edit `/boot/firmware/cmdline.txt`, reboot the Pi for each core count, verify the actual online CPU set, run the CT-3 measurement grid in `--core-control boot-current` mode, then restore the original boot cmdline and reboot at the end.

This is the scientifically correct path for the thesis core-off comparison. Runtime affinity still exists only as an explicit debug mode:

```text
--core-control affinity
```

That mode must not be described as core shutdown.

---

## 31. Mission-Critical Runtime Constraint: No Reboot-Based Core Switching

For the drone companion-computer use case, rebooting the Raspberry Pi during operation is not acceptable. The Pi is part of the active MAVLink/security path between GCS and flight controller. A reboot would interrupt:

- secure tunnel process
- MAVLink heartbeat forwarding
- Pixhawk companion link
- DDoS/traffic monitoring process
- telemetry and command path

Therefore, boot-time `maxcpus=N` must be treated as a **laboratory calibration method only**, not a runtime scheduler action.

### What the deeper inspection found

The Pi is running:

```text
Linux uavpi 6.12.47+rpt-rpi-v8
Debian 12 Bookworm
CPU online mask: 0-3
CPU possible mask: 0-3
CPUFreq policy0 affects CPUs: 0 1 2 3
available frequencies: 600000..1800000 Hz
available governors: conservative ondemand userspace powersave performance schedutil
```

Kernel CPU hotplug is compiled in:

```text
CONFIG_HOTPLUG_CPU=y
```

But the platform does not support runtime offlining:

```text
/sys/devices/system/cpu/cpuX/online: missing
/sys/devices/system/cpu/cpuX/hotplug/target: present
write target=0 result: Operation not supported
```

Device-tree CPU bring-up method:

```text
/proc/device-tree/cpus/cpu@*/enable-method = spin-table
no PSCI firmware node found
```

This matters because ARM runtime CPU offlining normally depends on the platform/firmware path being able to stop and restart secondary CPUs safely. Here the kernel has the hotplug framework, but the Raspberry Pi 4 BCM2711 platform does not provide usable individual-core runtime power-off.

Community confirmation from Raspberry Pi engineers: there is no way to turn off individual CPU cores on BCM2711/Pi 4; clock gating for idle cores is already good, and `maxcpus=1` mainly limits load spikes under load rather than acting as a live scheduler tool.

### Correct split for the thesis

We should separate two things:

1. **Offline calibration grid**
   - may reboot
   - may use `maxcpus=N`
   - purpose: measure energy/performance envelope
   - valid for lab characterization

2. **Mission runtime scheduler**
   - must not reboot
   - must not depend on runtime CPU offlining
   - must keep secure MAVLink path alive
   - should use only reversible runtime controls

### Runtime-safe controls for the scheduler

The scheduler should use:

- CPUFreq/DVFS:
  - set governor
  - set min/max frequency
  - choose fixed frequency or governor based on mission state
- process placement:
  - `taskset`
  - `os.sched_setaffinity`
  - systemd `CPUAffinity=`
  - cgroup v2 `cpuset`
- CPU budget:
  - cgroup v2 CPU controller
  - systemd `CPUQuota=`
  - lower CPU share for non-critical analytics
- priority:
  - `nice`
  - `chrt` only with care
  - keep MAVLink/security process above analytics
- workload shedding:
  - disable TST/high-cost DDoS model first
  - keep lightweight ExyBoost if budget allows
  - keep AEAD tunnel alive always
- crypto selection:
  - choose AEAD based on calibrated energy/latency table
  - avoid frequent KEM/SIG rekey unless needed
- power-aware policy:
  - use CT-3 during experiments
  - use calibrated CPU/power model during flight
  - fall back to conservative mode if measurement stream is missing

### Important reframing

The scheduler should not be described as "turning off cores during flight."

The correct claim is:

```text
The scheduler uses measurement-calibrated DVFS, CPU affinity/cgroups, process priority,
algorithm selection, and workload shedding to reduce energy while preserving the
continuous MAVLink security path.
```

The maxcpus grid remains useful because it tells us the theoretical lower envelope when fewer cores are available, but runtime control should imitate that behavior by keeping non-critical work away from selected cores and allowing idle clock gating, not by physically offlining cores.

---

## 32. Runtime Benchmark Direction: Software Scheduling + DVFS

Decision update: do not use core off/on for the active scheduler path.

The operational benchmark now focuses on controls that can be changed while the Pi keeps running:

```text
all CPU cores remain online: 0-3
frequency grid: 600000..1800000 Hz
software worker/affinity width: 1,2,3,4
core-control label: affinity_only_no_core_shutdown
power integration: CT-3 trapezoidal AUC
baseline: measured before each workload window
active workload: AEAD cycles
```

The normal wrapper modes were changed accordingly:

```powershell
.\pi_benchmark\run_measurement_grid.ps1 -Mode smoke
.\pi_benchmark\run_measurement_grid.ps1 -Mode full
```

These modes no longer attempt CPU hotplug. They use:

```text
--core-control affinity
```

Meaning:

- no reboot
- no runtime CPU offlining
- all four cores stay available to Linux
- workload process pool is restricted to the selected CPU set
- DVFS is still swept from 600 MHz to 1.8 GHz

Boot modes still exist only for lab/offline calibration:

```powershell
.\pi_benchmark\run_measurement_grid.ps1 -Mode boot-dry-run
.\pi_benchmark\run_measurement_grid.ps1 -Mode boot-smoke
.\pi_benchmark\run_measurement_grid.ps1 -Mode boot-full
```

But they should not be used as the mission runtime scheduler basis.

### New clean runtime-only implementation

Created a separate runtime-only benchmark path:

```text
pi_benchmark/runtime_dvfs_frequency_grid.py
pi_benchmark/run_runtime_dvfs_frequency_grid.ps1
```

This code intentionally has no CPU hotplug control and no boot/maxcpus control. It never disables cores and never reboots the Pi.

The only runtime controls are:

```text
CPUFreq policy0 frequency pinning
software worker width
software affinity inside pi_aead_workload.py
```

The terminology is changed from `requested_cores` to:

```text
worker_width
```

because this is not physical core shutdown.

Core-control label:

```text
software_affinity_only_all_cores_online
```

Before each run, the script verifies all expected CPUs are still online.

### Runtime-only frequency smoke result

Command:

```powershell
.\pi_benchmark\run_runtime_dvfs_frequency_grid.ps1 -Mode frequency-smoke
```

Output:

```text
measurements/runtime_dvfs_frequency_grid_smoke/20260531_224533
algorithm: AES-256-GCM
cycles per row: 5000
payload: 1024 bytes
worker width: 1
frequencies: 600, 900, 1200, 1500, 1800 MHz
online CPUs: 0-3 for every row
Pi restored: ondemand, min 600000, max 1800000, throttled=0x0
```

Smoke rows:

```text
freq      ops/s    active_W  active_J/10k  excess_J/10k
600 MHz   9876     3.110     6.8357        0.6341
900 MHz   14605    3.493     5.2668        0.7916
1200 MHz  18585    3.520     4.5965        0.6508
1500 MHz  23454    3.583     3.7622        0.4957
1800 MHz  27562    3.757     3.5019        0.4214
```

This smoke run is useful to validate code, CT-3 sampling, Pi restore, and frequency control. Because each row has only 5000 cycles, active windows are short; the full benchmark should use longer runs such as 300000 cycles per row.

Full runtime-only command:

```powershell
.\pi_benchmark\run_runtime_dvfs_frequency_grid.ps1 -Mode full
```

### Wrapper correction after CT-3 stream failure

The older wrapper command:

```powershell
.\pi_benchmark\run_measurement_grid.ps1 -Mode full
```

failed once at CT-3 stream start:

```text
RuntimeError: CT-3 stream did not produce samples after 3 attempts
```

The CT-3 was visible over USB, so the failure was not device enumeration. It happened during stream acquisition. After that, the clean runtime-only wrapper started correctly and held the CT-3 stream.

To prevent accidental use of the older mixed hotplug-era implementation, `run_measurement_grid.ps1` was changed so normal `smoke` and `full` modes now call:

```text
pi_benchmark/runtime_dvfs_frequency_grid.py
```

not:

```text
pi_benchmark/measurement_driven_power_grid.py
```

The legacy boot modes remain only for offline calibration:

```text
boot-dry-run
boot-smoke
boot-full
```

### Full clean runtime-only AES-256-GCM grid

Run completed:

```text
output: measurements/runtime_dvfs_frequency_grid/20260531_230656
rows: 52
failures: 0
algorithm: AES-256-GCM
cycles per row: 300000
payload: 1024 bytes
frequencies: 600000..1800000 Hz
worker_width: 1,2,3,4
core control: software_affinity_only_all_cores_online
CT-3 sample rate min/mean/max: 1000.57 / 1003.09 / 1008.51 Hz
Pi restored: online=0-3, governor=ondemand, min=600000, max=1800000, throttled=0x0
```

Best rows by **excess joules per 10k operations**:

```text
freq      workers  wall_s  ops/s   active_W  excess_J  excess_J/10k
1300 MHz  1        9.399   31917   3.639     4.538     0.1513
1000 MHz  2        6.219   48238   3.856     4.710     0.1570
1600 MHz  2        3.877   77386   4.403     5.031     0.1677
1400 MHz  2        4.416   67931   4.210     5.077     0.1692
800 MHz   3        5.187   57841   3.969     5.100     0.1700
```

Best rows by **total joules per 10k operations**:

```text
freq      workers  wall_s  ops/s    active_W  active_J/10k
1700 MHz  4        1.911   156985   5.684     0.4176
1800 MHz  4        1.803   166359   5.964     0.4176
1600 MHz  4        2.040   147084   5.461     0.4322
1500 MHz  4        2.147   139706   5.346     0.4398
1400 MHz  4        2.321   129275   5.174     0.4606
```

Interpretation:

- The most efficient **incremental CPU cost above baseline** is around 1300 MHz with 1 worker in this run.
- The most efficient **total batch completion energy** is 1700-1800 MHz with 4 workers.
- The scheduler should choose between these modes based on deadline:
  - background/energy-save: lower worker width, mid frequency
  - burst/latency-critical: 4 workers, 1600-1800 MHz
  - continuous MAVLink AEAD: must be benchmarked separately with realistic packet sizes and rates

### First runtime-safe AES-256-GCM grid run

Run completed on 2026-05-31:

```text
output: measurements/runtime_software_dvfs_grid/20260531_221653
rows: 52
failed rows: 0
frequency points: 600000..1800000 Hz
software affinity widths: 1,2,3,4
cycles per row: 300000
payload size: 1024 bytes
AEAD: AES-256-GCM
core control: affinity_only_no_core_shutdown
CT-3 sample rate min/mean/max: 1000.86 / 1003.10 / 1011.46 Hz
Pi restore state: all cores online, ondemand governor, min 600000, max 1800000, throttled=0x0
```

Best rows by **excess joules per 10k operations**:

```text
freq     workers  wall_s  ops/s   active_W  excess_J  excess_J/10k
600 MHz  1        20.454  14667   3.108     3.886     0.1295
700 MHz  1        17.399  17242   3.349     4.320     0.1440
1500 MHz 1        8.125   36921   3.733     4.508     0.1503
1000 MHz 1        12.373  24246   3.485     4.707     0.1569
1300 MHz 1        9.407   31892   3.646     4.735     0.1578
```

Best rows by **total joules per 10k operations**:

```text
freq      workers  wall_s  ops/s    active_W  active_J/10k
1800 MHz  4        1.798   166846   6.008     0.4195
1700 MHz  4        1.917   156495   5.645     0.4202
1600 MHz  4        2.027   147970   5.462     0.4262
1500 MHz  4        2.141   140115   5.317     0.4356
1400 MHz  4        2.315   129603   5.128     0.4552
```

Interpretation:

- If the metric is **incremental CPU energy above baseline**, low worker count at low/mid frequency is best.
- If the metric is **total energy to finish a fixed batch**, high frequency with 4 workers wins because it finishes very quickly.
- For mission operation, the scheduler should not blindly choose fastest or lowest frequency. It should choose based on latency budget:
  - latency-sensitive burst: 1600-1800 MHz, 4 workers
  - energy-conservative background crypto: 600-1000 MHz, 1 worker
  - balanced mode needs further comparison with real MAVLink packet sizes and traffic rate

### End-to-end runtime load probe at 600 MHz

Run completed on 2026-06-01:

```text
output: measurements/e2e_load_analysis_600mhz/20260601_001607
suite: cs-mlkem1024-mldsa87
KEM: ML-KEM-1024
signature: ML-DSA-87
data-plane AEAD: AES-GCM-256
Pi CPU policy during run: userspace, fixed 600000 Hz
Pi CPU policy after run: restored to ondemand, min 600000, max 1800000
throttle state: throttled=0x0
active data-plane window used for rates: 41.451 s, measured from fresh counter reset to final counter increase
```

Handshake and data-plane counters:

```text
ML-KEM/ML-DSA handshake total: 54.473 ms
ML-DSA verify on drone: 3.039 ms
ML-KEM encaps on drone: 0.805 ms
HKDF/key schedule on drone: 5.100 ms

AEAD encrypt count: 3581 total, 3556 inside measured active window
AEAD decrypt count: 96 total, 95 inside measured active window
drone->GCS encrypted packet rate: 85.79 pkt/s
GCS->drone encrypted packet rate: 2.29 pkt/s
encrypted output byte rate from drone: 6805.8 B/s
encrypted input byte rate to drone: 168.3 B/s
drops/replay/auth/header failures: 0
```

Per-packet AEAD timing on the drone:

```text
AES-GCM-256 encrypt avg: 0.1195 ms
AES-GCM-256 encrypt min/max: 0.0534 / 3.3958 ms
AES-GCM-256 decrypt avg: 0.1492 ms
AES-GCM-256 decrypt min/max: 0.0800 / 0.4607 ms
```

Pi process CPU load at fixed 600 MHz:

```text
process              mean CPU of one core   p95 CPU of one core   max CPU of one core   mean full-Pi share
MAVProxy             28.96%                 35.48%                38.93%                7.24%
drone async_proxy     9.45%                 12.39%                26.55%                2.36%
sdrone scheduler      0.47%                  1.78%                 3.56%                0.12%
```

System-level load during the active data-plane window:

```text
mean full-Pi CPU busy: 22.45%
median full-Pi CPU busy: 20.81%
p95 full-Pi CPU busy: 31.39%
max full-Pi CPU busy: 51.91%
mean temperature: 42.73 C
max temperature: 43.8 C
perf system-wide 30 s window: 10.256B instructions, 16.898B cycles, IPC 0.61, 150423 context switches
```

GCS-side MAVLink telemetry while proxy was steadily alive:

```text
steady rx_pps mean/median/p95/max: 85.86 / 85.6 / 89.4 / 90.2 pkt/s
steady rx_bps mean/median/p95/max: 3806 / 3794 / 3976 / 4002 B/s
steady jitter mean/p95/max: 21.58 / 21.9 / 21.9 ms
steady max inter-packet gap median/p95/max: 204 / 281 / 281 ms
heartbeat age median/p95/max: 203 / 515 / 516 ms
blackout count/total: 0 / 0 ms
```

Interpretation:

- After the PQ handshake, the actual continuous mission load is not KEM or signature work. It is mostly MAVProxy serial/MAVLink handling plus the AES-GCM packet bridge.
- At 600 MHz, MAVProxy is the largest drone-side CPU consumer, not AES-GCM. The async proxy is much smaller, averaging under 10% of one 600 MHz core for roughly 86 encrypted packets per second.
- The data-plane met the observed MAVLink workload without crypto drops or scheduler blackouts at 600 MHz. There were normal packet gaps up to roughly 281 ms in the GCS telemetry window, but the heartbeat stayed under roughly 516 ms in the steady window.
- For this workload, 600 MHz is feasible for the secure MAVLink path alone. The scheduler risk comes when heavier tasks such as DDoS detection or model inference run beside MAVProxy and the async proxy.

### Measurement code proof

The critical measurement code lines are recorded in:

```text
measurements/e2e_load_analysis_code_proof.md
```

This proof file points to the exact code paths used for:

- AES-GCM encrypt/decrypt timing from `time.perf_counter_ns()`
- async proxy packet counters: `ptx_in`, `ptx_out`, `enc_in`, `enc_out`
- 5-second sliding-window packet rate: `rx_pps = count / WINDOW_S`
- blackout calculation: inter-arrival gaps `>= 1000 ms`
- Pi process CPU calculation from `/proc/<pid>/stat`
- direct unencrypted UDP/MAVLink frame counting

### Direct unencrypted Pixhawk-to-GCS MAVLink baseline

Run completed on 2026-06-01:

```text
output: measurements/direct_mavlink_baseline/20260601_002706
path: Pixhawk serial -> Pi MAVProxy -> UDP/Tailscale -> Windows listener
encryption: none
Pi CPU policy during run: fixed 600000 Hz
Pi CPU policy after run: restored to ondemand, min 600000, max 1800000
listener port: UDP 14600
duration: 75.016 s
```

Firmware and vehicle context from MAVProxy:

```text
vehicle: 1:1
mode: STABILIZE
firmware: ArduCopter V4.5.7 (2a3dc4b7)
OS: ChibiOS 6a85082c
flight controller: Pixhawk1 0048003F 33355114 39383934
frame: QUAD/X
IMU fast sampling: 8.0 kHz / 1.0 kHz
```

Important Pixhawk parameters captured in `pixhawk_mav.parm`:

```text
SCHED_LOOP_RATE 400
SERIAL0_BAUD 115
SERIAL0_PROTOCOL 2
SYSID_THISMAV 1
SYSID_MYGCS 255

SR0_ADSB     4
SR0_EXTRA1   4
SR0_EXTRA2   4
SR0_EXTRA3   4
SR0_EXT_STAT 4
SR0_POSITION 4
SR0_RAW_CTRL 4
SR0_RAW_SENS 4
SR0_RC_CHAN  4

SR1_*, SR2_*, SR3_*, SR4_* are mostly 0 in this snapshot.
```

Direct baseline packet results:

```text
total UDP datagrams: 5934
total parsed MAVLink frames: 5934
parse-empty datagrams: 0
mean datagrams/s over whole run: 79.10
mean MAVLink frames/s over whole run: 79.10
steady datagrams/s mean/median/p95/max: 86.41 / 85.8 / 86.8 / 108.2
steady frames/s mean/median/p95/max: 86.41 / 85.8 / 86.8 / 108.2
steady blackout count/total: 0 / 0 ms
steady max gap median/p95/max: 219 / 234 / 234 ms
steady jitter mean/p95/max: 18.72 / 19.35 / 19.46 ms
heartbeat count: 69
heartbeat gap mean/median/p95/max: 996 / 1000 / 1000 / 1172 ms
```

Direct MAVProxy CPU at 600 MHz:

```text
MAVProxy CPU mean/median/p95/max: 29.71% / 26.0% / 41.0% / 121.15% of one core
MAVProxy RSS mean/max: 70.4 MB / 71.1 MB
```

Comparison with encrypted AES-GCM-256 end-to-end run at 600 MHz:

```text
direct unencrypted steady rate: 86.41 MAVLink frames/s
encrypted drone->GCS rate: 85.79 encrypted packets/s
GCS telemetry steady encrypted rx rate: 85.86 packets/s
```

Interpretation:

- The encrypted tunnel is not the reason the rate is around 86 packets/s. The direct unencrypted Pixhawk-to-GCS path is also around 86 packets/s.
- The expectation of 300+ packets/s does not match the current Pixhawk stream configuration. The captured `SR0_*` groups are set to 4 Hz. With many message groups enabled at 4 Hz plus heartbeats and occasional status/parameter messages, the resulting aggregate is around 80-90 MAVLink messages per second.
- To get 300+ packets/s, the Pixhawk/MAVLink stream rates must be intentionally increased using stream-rate parameters or MAVLink message interval commands, and the serial link/flight-controller load must be checked. The current `SERIAL0_BAUD 115` means this link is 115200 baud, so raising every stream aggressively can hit serial bandwidth and Pixhawk scheduling limits.
- For our scheduler, the correct current baseline is about 86 packets/s, not 300 packets/s. If the thesis wants a high-rate stress case, it should be a separate configured workload, not assumed as the default telemetry rate.

### Second Pixhawk / PX4 FMU v5.x configuration check

Run completed on 2026-06-01:

```text
config output: measurements/pixhawk_config/20260601_004129
direct packet-rate output: measurements/direct_mavlink_baseline_new_pixhawk/20260601_004229
device on Pi: /dev/ttyACM0
stable symlink: /dev/serial/by-id/usb-3D_Robotics_PX4_FMU_v5.x_0-if00
USB ID: 26ac:0032
USB product: 3D Robotics PX4 FMU v5.x
```

MAVLink identity:

```text
system/component: 1:1
vehicle type: 2 (quadrotor)
autopilot: 12 (PX4)
MAVLink version field: 3
mode observed through MAVProxy: LOITER
parameter count: 1101 / 1101 received
```

Autopilot version fields:

```text
vendor_id: 9900
product_id: 50
board_version: 50
uid: 3473208906308203572
flight_sw_version: 17761023
middleware_sw_version: 17761023
os_sw_version: 184549631
```

Important PX4 configuration values:

```text
MAV_SYS_ID       1
MAV_COMP_ID      1
MAV_TYPE         2
MAV_0_CONFIG     101
MAV_0_MODE       0
MAV_0_RATE       1200
MAV_0_FORWARD    1
MAV_1_CONFIG     0
MAV_2_CONFIG     0
SER_TEL1_BAUD    57600
SER_GPS1_BAUD    0
SYS_AUTOSTART    4001
SYS_USB_AUTO     2
CA_ROTOR_COUNT   4
COM_CPU_MAX      95
COM_RC_IN_MODE   3
COM_RC_LOSS_T    0.5
BAT1_N_CELLS     6
```

Direct unencrypted rate check for the second Pixhawk:

```text
path: PX4 FMU v5.x -> Pi MAVProxy -> UDP/Tailscale -> Windows listener
encryption: none
duration: 50.031 s
total UDP datagrams: 15243
total parsed MAVLink frames: 15243
mean whole-run rate: 304.67 frames/s
steady frames/s mean/median/p95/max: 337.61 / 334.2 / 500.8 / 518.4
steady blackout count/total: 0 / 0 ms
steady max gap median/p95/max: 31 / 78 / 78 ms
steady jitter mean/p95/max: 4.68 / 4.89 / 5.18 ms
heartbeat count: 44
heartbeat gap mean/median/p95/max: 988 / 1000 / 1015 / 1532 ms
MAVProxy CPU mean/median/p95/max: 72.45% / 70% / 103% / 123.08% of one core
```

Most common message IDs in the second Pixhawk baseline:

```text
30: 3976
105: 2115
31: 2115
32: 1274
331: 1250
22: 1102
111: 428
141: 427
83: 427
85: 427
36: 427
74: 427
```

Interpretation:

- This second board is the high-rate baseline. It produces about 300+ MAVLink frames/s with no encryption.
- The previous ArduPilot/Pixhawk1 board produced about 86 frames/s because of its stream-rate configuration.
- The difference is therefore not caused by the secure tunnel alone; it is strongly tied to flight-controller firmware and stream configuration.
- This PX4 board is a better stress source for the scheduler and encrypted tunnel because its raw MAVLink rate is close to the 300+ packets/s expectation.
- At this rate, MAVProxy alone is already heavy on a 600 MHz Pi, averaging about 72% of one core. Adding AES-GCM, PQC rekeying, and DDoS detection on top of this board will be the more realistic stress test for scheduler design.

### High-rate encrypted bidirectional benchmark preparation

Prepared on 2026-06-01:

```text
runner: pi_benchmark/run_highrate_e2e_bidir.ps1
injector: pi_benchmark/mavlink_bidir_injector.py
analyzer: pi_benchmark/analyze_e2e_mavlink_run.py
drone scheduler opt-in change: DRONE_MAVPROXY_BIDIR_IN=1
```

Important design correction:

- The existing drone scheduler started MAVProxy as `--master=/dev/ttyACM0 --out=udp:127.0.0.1:47003`.
- That is enough for Pixhawk -> Pi -> encrypted tunnel -> GCS telemetry.
- The proxy already has a decrypted GCS -> drone output port, `DRONE_PLAINTEXT_RX=47004`.
- But MAVProxy was not listening on `47004`, so true GCS -> Pixhawk command stress was not fully exercised.
- The scheduler now supports an opt-in mode using `DRONE_MAVPROXY_BIDIR_IN=1`, adding `--master=udpin:127.0.0.1:47004` to drone MAVProxy.

MAVLink documentation basis:

- `MAV_CMD_SET_MESSAGE_INTERVAL` sets the interval for a selected MAVLink message ID.
- `MAV_CMD_REQUEST_MESSAGE` requests one specific message instance.
- MAVLink `PING` is the standard round-trip latency/health probe: request has target system/component `0/0`; response returns the same timestamp/sequence to the sender.

Planned benchmark command when Pi SSH command execution is responsive:

```powershell
.\pi_benchmark\run_highrate_e2e_bidir.ps1 `
  -Suite cs-mlkem1024-mldsa87 `
  -Aead aesgcm256 `
  -Duration 45 `
  -PingHz 50
```

Expected outputs:

```text
measurements/e2e_highrate_bidir/<timestamp>/drone_status.json
measurements/e2e_highrate_bidir/<timestamp>/e2e_packet_size_summary.json
measurements/e2e_highrate_bidir/<timestamp>/bidir_injector_summary.json
```

The run is currently blocked by SSH command execution hanging even though Tailscale reachability and TCP/22 are healthy. Observed reachability:

```text
ping 100.101.93.23: 0% loss, about 7-9 ms
Test-NetConnection 100.101.93.23:22: TcpTestSucceeded=True
ssh dev@100.101.93.23 'echo ok': times out
tailscale ssh dev@100.101.93.23 'echo ok': times out
```

### High-rate encrypted bidirectional run: live status correction

After SSH authentication recovered, the first wrapper-driven attempts showed an important measurement bug:

- Windows-side GCS follower/MAVProxy and the CT-3 publisher could be left running.
- The Pi-side `sdrone`, drone MAVProxy, and drone proxy were not live.
- The existing `drone_status.json` could still say `running`, but that file was stale from an earlier run.
- Therefore liveness must be determined from process/port state, not from status JSON alone.

Live checks used:

```text
Windows:
Get-CimInstance Win32_Process ... sscheduler.sgcs / MAVProxy / windows_ct3 / injector
Get-NetUDPEndpoint / netstat for 14550,14552,14553,47001,47002,50601

Pi:
ps -eo pid,comm,%cpu,%mem,args
ss -tunlp
vcgencmd get_throttled
```

Fix applied for bidirectional observability:

- `secure-tunnel-main/secure-tunnel-main/sscheduler/sgcs.py`
- Added optional `GCS_EXTRA_SNIFF_PORT`.
- During the benchmark runner, `GCS_EXTRA_SNIFF_PORT=14553` makes GCS MAVProxy mirror decoded MAVLink to a second local listener.
- The normal metrics collector still owns `14552`; the injector observes traffic on `14553`.

The wrapper still orphaned helper processes, so the valid run below was performed manually in strict order:

```text
1. Clean old benchmark-owned Python, MAVProxy, CT-3 bridge, and Pi processes.
2. Start Windows CT-3 UDP publisher.
3. Start Pi CT-3 UDP receiver.
4. Start GCS follower with GCS_EXTRA_SNIFF_PORT=14553.
5. Start bidirectional MAVLink injector at 50 Hz into GCS plaintext port 47001.
6. Start Pi sdrone directly over SSH with DRONE_MAVPROXY_BIDIR_IN=1.
7. Collect drone_status.json and analyze GCS telemetry.
8. Cleanup all benchmark-owned processes.
```

Valid tunnel/load artifact:

```text
measurements/e2e_highrate_bidir/manual_20260601_041123
```

Run configuration:

```text
suite: cs-mlkem1024-mldsa87
KEM: ML-KEM-1024
signature: ML-DSA-87
AEAD: AES-GCM-256
sdrone duration: 45 s
bidirectional injector: 50 PING/s for 75 s
Pi Pixhawk: PX4 FMU v5.x on /dev/ttyACM0
GCS extra sniff: 127.0.0.1:14553
```

Tunnel and MAVLink results:

```text
drone -> GCS encrypted packets: 16999
GCS -> drone encrypted packets: 2570
drops/auth/replay/header/session drops: 0

GCS steady received MAVLink rate:
mean: 386.58 packets/s
median: 393.6 packets/s
p95: 459.4 packets/s
max: 499.0 packets/s

GCS steady received byte rate:
mean: 26344.41 bytes/s

blackout count: 0
blackout total: 0 ms
max observed steady gap: 110 ms
steady jitter mean: 4.77 ms
```

Packet sizes:

```text
drone plaintext input avg: 56.30 bytes
drone ciphertext output avg: 103.30 bytes
GCS ciphertext input avg: 68.30 bytes
drone plaintext output avg: 21.30 bytes
AEAD/framing expansion: about 47 bytes per packet in both directions
```

Crypto timing:

```text
handshake total: 43.996 ms
ML-KEM encapsulation: 1.023 ms
ML-DSA verification: 4.986 ms
AES-GCM encrypt avg: 0.0805 ms
AES-GCM decrypt avg: 0.0940 ms
AES-GCM encrypt max: 2.593 ms
AES-GCM decrypt max: 1.074 ms
```

Bidirectional injector observation:

```text
PINGs injected into GCS plaintext port: 3750
messages observed on extra GCS sniff port: 34062
bytes observed on extra GCS sniff port: 1917402
PING responses matched by seq/target: 0
```

Interpretation:

- The extra sniff port confirms the GCS-side decoded MAVLink stream was visible to the injector.
- The injected PINGs increased GCS-to-drone encrypted traffic to 2570 packets.
- No PING RTT can be reported because no response matched the injector's expected source/target/sequence tuple. Message ID 4 appeared frequently, so this needs a follow-up parser check to distinguish looped/broadcast PINGs from true autopilot replies.
- For scheduler planning, the important result is that the encrypted high-rate PX4 stream reached about 386 packets/s steady with zero blackouts while AES-GCM averaged under 0.1 ms per packet on the Pi.

Power result for this run:

```text
INVALID: CT-3 CSV only contains the header row.
reason: Windows CT-3 bridge stopped producing samples.
```

Power debugging performed:

```text
ct3_dotnet_bridge.exe from the failed wrapper run had orphaned and claimed the device.
After killing it, ct3_dotnet_api.py list showed in_use=false.
However, local capture then hung at ShizukuProtocol protocol.Ping().
pnputil /restart-device failed because admin rights are required.
LibUsbDotNet ResetDevice() succeeded, but protocol.Ping() still hung.
```

Bridge maintenance added:

- `measurement/ct3_dotnet_bridge.cs`
- Added `--mode reset`, which calls LibUsbDotNet `ResetDevice()`.
- Added `--prefer-serial`, although the vendor scanner still only reports the libusb interface for this meter.

Current CT-3 conclusion:

- The end-to-end encrypted communication benchmark is valid.
- The power measurement for `manual_20260601_041123` is not valid.
- The next power-valid run requires physically unplugging/replugging the CT-3 or resetting it through the Shizuku app/device mode so that vendor `Ping()` returns again.

### Packet-size and latency correction

Detailed packet-size analysis was added here:

```text
measurements/e2e_highrate_bidir/manual_20260601_041123/packet_overhead_analysis.md
```

Important correction:

- The previous summary gave average packet sizes only.
- It did not give mode packet size or the MAVLink message mix.
- That was incomplete because MAVLink traffic is a mixture of different message IDs and payload sizes.

Our encrypted tunnel adds a fixed 47 bytes per MAVLink UDP datagram in this run:

```text
AEAD header: 30 bytes
AES-GCM tag: 16 bytes
internal packet type byte: 1 byte
transmitted nonce: 0 bytes
total expansion: 47 bytes
```

Formula:

```text
encrypted_size = mavlink_frame_size + 47 bytes
```

Measured averages from the valid encrypted run:

```text
drone -> GCS plaintext avg: 56.30 bytes
drone -> GCS ciphertext avg: 103.30 bytes
GCS -> drone ciphertext avg: 68.30 bytes
GCS -> drone plaintext avg: 21.30 bytes
```

Most likely mode packet sizes:

```text
drone telemetry mode:
ATTITUDE, MAVLink v2 plaintext about 40 bytes, encrypted about 87 bytes

command/injected side mode:
PING, MAVLink v1 plaintext about 22 bytes, encrypted about 69 bytes
```

Top observed decoded message IDs:

```text
30  ATTITUDE              7768
4   PING                  4306
105 HIGHRES_IMU           4158
31  ATTITUDE_QUATERNION   4158
32  LOCAL_POSITION_NED    2500
22  PARAM_VALUE           1634
```

Latency correction:

```text
handshake total: 43.996 ms
AES-GCM encrypt avg on Pi: 0.0805 ms
AES-GCM decrypt avg on Pi: 0.0940 ms
GCS steady max packet gap: 110 ms
GCS steady jitter mean: 4.77 ms
blackouts: 0
```

We cannot report true command RTT from this run:

```text
PINGs injected: 3750
PING responses matched by sequence/target: 0
```

The correct statement is that Pi-side crypto processing latency is under 0.1 ms per packet on average, while full end-to-end command RTT still needs a corrected PING/COMMAND_ACK measurement.

Tooling correction:

- `pi_benchmark/mavlink_bidir_injector.py` now records datagram size, frame size, and `(message_id, frame_size)` histograms for future runs.

## MAVLink Encryption and Network Analysis Documentation

Created a separate expert-level analysis document for MAVLink packet rates, packet sizes, encrypted tunnel overhead, command injection behavior, latency interpretation, and scheduler implications:

```text
measurements/mavlink_encryption_network_analysis.md
```

Key documented conclusion:

- The 499 pps result is not heartbeat-only traffic.
- Direct unencrypted PX4 telemetry was already about 304.67 pps.
- The encrypted PING-injection run reached about 386.58 pps mean and 499 pps max.
- The current AES-GCM tunnel adds 47 bytes per MAVLink datagram.
- Power from that encrypted run is invalid because CT-3 produced no samples.

## Max-Load MAVLink Encrypted Power Run

Fresh post-reboot run completed with CT-3 working:

```text
measurements/e2e_max_mavlink_power/20260601_052911/
```

Configuration:

```text
Suite: ML-KEM-1024 + ML-DSA-87
AEAD: AES-GCM-256
PING injection: 100 Hz
SET_MESSAGE_INTERVAL requested: ATTITUDE 200 Hz, ATTITUDE_QUATERNION 200 Hz, LOCAL_POSITION_NED 100 Hz, HIGHRES_IMU 100 Hz, TIMESYNC 100 Hz, plus status/control telemetry streams at 20-50 Hz.
```

Results:

```text
secure proxy encrypt count: 25791
secure proxy decrypt count: 6758
total AEAD ops over 60 s: about 542.48 ops/s
GCS rx_pps mean/median/p95/max: 436.42 / 448.50 / 463.00 / 475.00
GCS sniff decoded messages: 51586 over 80 s, about 644.83 messages/s
drops/auth/replay/header/session drops: 0
handshake: 27.888 ms
AES-GCM encrypt/decrypt avg: 0.06854 ms / 0.07854 ms
```

Power:

```text
CT-3 receiver rows: 4216
estimated CT-3 samples: 84801
estimated CT-3 rate: 1000.06 Hz
capture duration: 84.796 s
energy: 373.369 J
average power: 4.403 W
median/p95/max power: 4.444 / 5.361 / 6.152 W
UDP power sequence drops: 0
post-run Pi: throttled=0x0, temp=47.7 C
```

Report updated:

```text
measurements/mavlink_encryption_network_analysis.md
```

## Max-Load MAVLink ChaCha20-Poly1305 Power Run

Fresh comparable run completed:

```text
measurements/e2e_max_mavlink_power/20260601_054344/
```

Configuration:

```text
Suite: ML-KEM-1024 + ML-DSA-87
AEAD: ChaCha20-Poly1305
PING injection: 100 Hz
Same max-load SET_MESSAGE_INTERVAL profile as AES run
```

Results:

```text
secure proxy encrypt count: 25513
secure proxy decrypt count: 6745
total AEAD ops over 60 s: about 537.63 ops/s
GCS rx_pps mean/median/p95/max: 432.39 / 446.60 / 460.40 / 462.00
GCS sniff decoded messages: 51108 over 80 s, about 638.85 messages/s
drops/auth/replay/header/session drops: 0
handshake: 35.837 ms
ChaCha encrypt/decrypt avg: 0.06722 ms / 0.07659 ms
```

Power:

```text
CT-3 receiver rows: 4229
estimated CT-3 samples: 84811
estimated CT-3 rate: 999.98 Hz
capture duration: 84.813 s
energy: 372.099 J
average power: 4.387 W
median/p95/max power: 4.360 / 5.369 / 5.902 W
UDP power sequence drops: 0
post-run Pi: throttled=0x0, temp=46.2 C
```

Initial AES-vs-ChaCha conclusion:

```text
AES-GCM avg power: 4.403 W
ChaCha avg power: 4.387 W
ChaCha difference: about -0.016 W, roughly -0.36%

AES-GCM encrypt/decrypt avg: 0.06854 ms / 0.07854 ms
ChaCha encrypt/decrypt avg: 0.06722 ms / 0.07659 ms
ChaCha is about 1.9% faster on encrypt and 2.5% faster on decrypt in this run.
```

Interpretation:

- Both AEADs handled the max-load MAVLink profile with zero tunnel drops.
- ChaCha was slightly faster and slightly lower power in this single run.
- The power gap is too small for a strong claim without repeated runs, but it is useful input for scheduler policy.

## XGBoost Workload Added to AEAD DVFS Grid

Prepared the end-to-end benchmark path so XGBoost can run as a concurrent drone-side workload during the encrypted MAVLink tests.

Code changes:

```text
secure-tunnel-main/secure-tunnel-main/sscheduler/sdrone.py
- Added --detector-level for deterministic benchmark runs.
- Deterministic runs can now force XGBOOST instead of relying on energy-aware policy decisions.
- The run logs "Detector ACTIVE: XGBOOST" only after the detector process starts and survives the startup check.

secure-tunnel-main/secure-tunnel-main/sscheduler/detector_manager.py
- Added DETECTOR_IFACE, DETECTOR_WINDOW, DETECTOR_THRESHOLD, DETECTOR_USE_SUDO, and DETECTOR_XGBOOST_SCRIPT environment controls.
- XGBoost can now be launched through sudo for raw packet capture.

secure-tunnel-main/secure-tunnel-main/ddos/xgb_old.py
- Added compatibility arguments for the detector manager.
- Added /tmp/ddos_severity.json reporting so benchmark output records detector activity.

pi_benchmark/run_max_mavlink_e2e_power_stress.ps1
- Added DetectorLevel, DetectorIface, DetectorWindow, and DetectorXgbScript parameters.
- Removes stale drone_status.json and detector severity files before each run.
- Collects ddos_severity.json and detector_xgboost.err.txt into each output folder.

pi_benchmark/run_mavlink_aead_dvfs_grid.ps1
- Added detector parameters to the full AEAD/frequency grid.
- XGBoost grid output goes under measurements/mavlink_aead_dvfs_grid_xgboost/.
```

Important implementation choice:

```text
The local ddos/models/xgb_model.pkl file is a Git LFS pointer, not the real model.
To avoid overwriting a valid Pi model with a pointer file, the benchmark path uses xgb_old.py with ddos/xgboost_model.bin.
Default detector interface is lo, because the drone-side plaintext MAVLink/proxy traffic is visible on loopback during the end-to-end run.
```

Run command planned after SSH auth:

```powershell
.\pi_benchmark\run_mavlink_aead_dvfs_grid.ps1 -DetectorLevel XGBOOST -DetectorIface lo -DetectorXgbScript xgb_old.py -FrequenciesKHz 600000,900000,1200000,1500000,1800000
```

Current blocker:

```text
Pi is reachable on TCP/22, but Tailscale SSH is requesting an interactive check.
Latest URL shown by the client: https://login.tailscale.com/a/l13708fc03a9cbd
The grid should be started only after that check is accepted, otherwise ssh/scp will hang before the measurement begins.
```

## XGBoost AEAD DVFS Grid Completed

Completed the full end-to-end MAVLink AEAD/frequency grid with XGBoost running as the concurrent drone-side DDoS workload.

Output root:

```text
measurements/mavlink_aead_dvfs_grid_xgboost/20260602_012519
```

Generated summaries:

```text
measurements/mavlink_aead_dvfs_grid_xgboost/20260602_012519/summary.md
measurements/mavlink_aead_dvfs_grid_xgboost/20260602_012519/summary.csv
measurements/mavlink_aead_dvfs_grid_xgboost/20260602_012519/summary.json
```

Configuration:

```text
Frequencies: 600, 900, 1200, 1500, 1800 MHz
AEADs: aesgcm128, aesgcm192, aesgcm256, aesccm128, aesccm192, aesccm256, chacha20poly1305, ascon128
Detector: XGBoost via /home/dev/nenv/bin/python
Detector script: ddos/xgb_old.py
Detector interface: lo
Run duration: 60 s per AEAD
Baseline duration: 30 s per frequency
CT-3 target period: 1 ms
```

Validation:

```text
Workload power summaries: 40/40 valid
Baseline power summaries: 5/5 valid
Pi restored after run: governor=ondemand, min=600000, max=1800000, throttled=0x0
```

Frequency averages:

```text
600 MHz  baseline 3.317 W  workload 3.916 W  excess 0.600 W  rx_pps 333.3  AEAD ops/s 438.0
900 MHz  baseline 3.580 W  workload 4.283 W  excess 0.704 W  rx_pps 402.0  AEAD ops/s 506.1
1200 MHz baseline 3.627 W  workload 4.464 W  excess 0.837 W  rx_pps 439.9  AEAD ops/s 546.3
1500 MHz baseline 3.613 W  workload 4.596 W  excess 0.982 W  rx_pps 431.3  AEAD ops/s 537.4
1800 MHz baseline 3.759 W  workload 4.819 W  excess 1.060 W  rx_pps 428.8  AEAD ops/s 540.1
```

Important measurement note:

```text
The first complete grid pass produced some empty CT-3 CSVs because the Shizuku/CT-3 bridge occasionally timed out or buffer-overflowed on startup.
The benchmark scripts were patched to reject zero-row power captures, and the missing baselines/workload rows were rerun into the same root.
The final summary uses only non-empty CT-3 power captures.
```
