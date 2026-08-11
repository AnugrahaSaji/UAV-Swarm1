# SSH Lab Setup Guide

Quick reference for running PQC Drone-GCS system in a lab environment with SSH-based remote observability.

## Network Configuration

| Component | Network | IP |
|-----------|---------|-----|
| SSH (Dev Tools) | Tailscale | `100.101.93.23` |
| Runtime Planes | LAN | (use LAN IPs) |

> **CRITICAL**: Use Tailscale IP **ONLY** for SSH. Runtime traffic (telemetry, proxy) uses LAN IPs.

## Quick Start

### 1. SSH into Drone (Raspberry Pi)

```bash
ssh -X -L 59001:localhost:59001 dev@100.101.93.23
```

Options:
- `-X` : Enable X11 forwarding (for GUI)
- `-L 59001:localhost:59001` : Forward OBS plane (drone port)

### 2. Run Drone Scheduler (on Pi via SSH)

```bash
cd ~/secure-tunnel
python -m devtools.launcher --role drone
```

### 3. Run GCS Scheduler (on Laptop)

```bash
cd ~/secure-tunnel
python -m devtools.launcher --role gcs
```

### 4. (Optional) GUI-Only Mode (separate laptop terminal)

```bash
python -m devtools.launcher --gui-only
```

This receives OBS snapshots and displays the dashboard without running a scheduler.

### 5. (Optional) OBS Receiver Only (for debugging)

```bash
python -m devtools.launcher --obs-receive
```

Prints OBS snapshots to console without GUI.

## Full SSH Command with Both Ports

If you need to forward both drone and GCS OBS ports:

```bash
ssh -X \
    -L 59001:localhost:59001 \
    -L 59002:localhost:59002 \
    dev@100.101.93.23
```

## Enable Dev Tools

Edit `settings.json`:

```json
{
    "dev_tools": {
        "enabled": true,
        "battery_simulation": {
            "enabled": true,
            "default_mode": "stable"
        },
        "gui": {
            "enabled": true,
            "refresh_hz": 5.0
        },
        "observability_plane": {
            "enabled": true,
            "drone_port": 59001,
            "gcs_port": 59002
        }
    }
}
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        LAPTOP                                   │
│                                                                 │
│  ┌─────────────────┐       ┌─────────────────────────────────┐ │
│  │ GCS Scheduler   │       │ GUI Dashboard                   │ │
│  │ --role gcs      │       │ --gui-only                      │ │
│  │                 │       │                                 │ │
│  │ OBS Emitter     │       │ OBS Receivers                   │ │
│  │ UDP→localhost   │       │ drone:59001 ←─┐                │ │
│  │ :59002          │       │ gcs:59002 ←───│───────────────┐ │ │
│  └─────────────────┘       └───────────────│───────────────│─┘ │
│                                            │               │   │
│  ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ │ ─ ─ ─ ─ ─ ─ │ ─ │
│                           SSH Tunnel      │               │   │
│                           -L 59001:...    │               │   │
└───────────────────────────────────────────│───────────────│───┘
                                            │               │
                                            ▼               │
┌───────────────────────────────────────────────────────────│───┐
│                   RASPBERRY PI (Drone)                    │   │
│                                                           │   │
│  ┌─────────────────┐                                      │   │
│  │ Drone Scheduler │                                      │   │
│  │ --role drone    │                                      │   │
│  │                 │                                      │   │
│  │ OBS Emitter     │                                      │   │
│  │ UDP→localhost   │──────────────────────────────────────┘   │
│  │ :59001          │                                          │
│  └─────────────────┘                                          │
└───────────────────────────────────────────────────────────────┘
```

## OBS Ports

| Node | Port | Direction |
|------|------|-----------|
| Drone | 59001 | Emit → Forward → Receive |
| GCS | 59002 | Emit → Receive (local) |

## Launcher Commands

| Command | Description |
|---------|-------------|
| `--role drone` | Run as drone with dev tools |
| `--role gcs` | Run as GCS with dev tools |
| `--gui-only` | GUI dashboard only (no scheduler) |
| `--obs-receive` | Console OBS output only |
| `--standalone` | Demo mode with fake data |
| `--no-gui` | Disable GUI |
| `--no-battery-sim` | Disable battery simulation |
| `--no-obs` | Disable OBS plane |

## Troubleshooting

### GUI Not Appearing via SSH
- Ensure X11 forwarding is enabled: `ssh -X ...`
- On macOS: Install XQuartz
- On Windows: Install VcXsrv or use WSL2 with X server

### OBS Snapshots Not Received
1. Check SSH tunnel is active: `ss -tlnp | grep 59001`
2. Verify dev_tools.enabled = true in settings.json
3. Verify observability_plane.enabled = true
4. Check firewall allows localhost UDP

### Scheduler Not Starting
- Verify sscheduler module is available
- Check for Python import errors
- Run with `--standalone` to test dev tools only
