# Lab Ops — GCS + Drone Pi (IP Consistency, SSH, Sync)

This document is a **technical common reference** for running/validating secure-tunnel experiments.

## 1) Hardware Inventory (Fill With Measured Truth)

Do not guess specs; record them from commands.

### GCS (Windows)

- Record:
  - CPU/RAM/GPU
  - Windows version
  - Active network adapter and IPv4

Commands:
- `systeminfo`
- `ipconfig /all`

### Drone (Raspberry Pi)

- Record:
  - Model (`cat /proc/cpuinfo | grep Model`)
  - CPU governor (`cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`)
  - Temp (`vcgencmd measure_temp`)
  - NIC + IPv4 (`ip -4 addr`)

SSH baseline:
- `ssh dev@100.101.93.23`
- On Pi: `cd secure-tunnel; source ~/cenv/bin/activate`

## 2) IP Types Used (Know Which One You’re Using)

secure-tunnel uses multiple IP “types” depending on purpose:

- **LAN IPv4** (runtime traffic): `192.168.0.x`
  - Used for TCP handshake + encrypted UDP data plane.
- **Tailscale IPv4** (management only): `100.x.y.z`
  - Used for SSH, Git maintenance, fetching logs.
- **Localhost**: `127.0.0.1`
  - Used for plaintext MAVLink sockets on each machine; traffic must not leave the host.
- **Bind-all**: `0.0.0.0`
  - Used to listen on all interfaces for certain services.

The active profile is selected by `TUNNEL_HOST_PROFILE` in `core/config.py`:
- `lan` (default), `tailscale`, or `localhost`.

## 3) Configuration Sources (What Overrides What)

1. `.denv` + `.denv.local` (drone-side)
2. `.genv` + `.genv.local` (GCS-side)
3. Environment variables (explicit env wins; loader never overwrites)
4. `core/config.py` defaults (fallbacks only)

Key files:
- `core/config.py`
- `core/env_loader.py`
- `.denv`, `.denv.local` (git-ignored overrides)
- `.genv`, `.genv.local` (git-ignored overrides)

## 4) IP Consistency Preflight (Mandatory Gate)

Before benchmarks, paper claim verification, or any run that touches networking:

A) Confirm **expected config** (repo truth)
- Read `.genv/.genv.local` and `.denv/.denv.local`
- Confirm `core/config.py` resolves the same hosts

B) Confirm **observed reality** (machine truth)
- On GCS: `ipconfig` → confirm the IPv4 on the active adapter
- On Pi: `ip -4 addr show wlan0` (or active iface) → confirm IPv4

C) Confirm **reachability**
- From GCS → Pi LAN: `ping <DRONE_HOST_LAN>`
- From Pi → GCS LAN: `ping -c 3 <GCS_HOST_LAN>`

D) Confirm **management isolation**
- SSH uses Tailscale (`100.x`) only.
- Runtime traffic uses LAN (`192.168.0.x`) only.

If any mismatch exists: stop and fix config first. Do not “try anyway”.

## 5) Keeping Pi Code Up To Date (Git vs SCP)

### Option A — Git pull on the Pi (preferred if repo is a real git checkout on Pi)

- On GCS: commit + push.
- On Pi:
  - `cd ~/secure-tunnel`
  - `git status`
  - `git pull`

### Option B — SCP sync (useful if the Pi directory is not a git checkout)

- Copy specific files/directories only (avoid secrets):
  - From GCS: `scp -r core sscheduler bench scripts zfinal dev@100.101.93.23:~/secure-tunnel/`

Always verify after sync:
- Run a minimal import check on Pi: `python3 -c "from core.config import CONFIG; print(CONFIG['TUNNEL_HOST_PROFILE'])"`

## 6) Evidence Capture (Quality Gate)

For every terminal procedure:
- Capture output (copy/paste or write to `zfinal/raw/` report).
- Evaluate quality: latencies, loss, CPU temp, power stability.
- If results are anomalous: reproduce, isolate variables, and document.
