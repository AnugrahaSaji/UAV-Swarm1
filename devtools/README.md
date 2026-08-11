# Development Tools System

## Overview

This document describes the **DEVELOPMENT-ONLY** tooling system for the PQC Drone-GCS secure proxy. This system is designed for **LAB / LAPTOP TESTING ONLY** and does not affect production behavior when disabled.

## Architecture

```
devtools/
├── __init__.py          # Enable/disable logic, safe imports
├── config.py            # Configuration loader
├── data_bus.py          # Thread-safe observability bus
├── battery_sim.py       # Battery provider abstraction + simulation
├── battery_bridge.py    # Non-invasive injection bridge
├── dashboard.py         # Tkinter GUI dashboard
├── integration.py       # Scheduler integration layer
├── obs_schema.py        # Observability Plane schema
├── obs_emitter.py       # Fire-and-forget UDP emitter
├── obs_receiver.py      # UDP receiver + DataBus feeder
├── test_obs_plane.py    # OBS plane verification tests
└── launcher.py          # Entry point for dev mode
```

## Components

### 1. Battery Simulator

**Location:** `devtools/battery_sim.py`

Provides a `BatteryProvider` interface with two implementations:
- `RealBatteryProvider`: Pass-through to MAVLink (production path)
- `SimulatedBatteryProvider`: Configurable simulation for lab testing

**Simulation Modes:**
| Mode | Description | Rate |
|------|-------------|------|
| `stable` | Constant voltage | 0 mV/s |
| `slow_drain` | Slow linear drain | ~5 mV/s |
| `fast_drain` | Fast linear drain | ~20 mV/s |
| `throttle_drain` | Accelerated drain under load | Variable |
| `step_drop` | Sudden voltage drop | One-shot |
| `recovery` | Voltage rebound | ~10 mV/s |

Each mode exposes:
- `battery_mv`: Current voltage in millivolts
- `rate_mv_per_sec`: Rate of change
- `stress_level`: Qualitative level (low/medium/high/critical)

### 2. Data Bus

**Location:** `devtools/data_bus.py`

Thread-safe **SINGLE SOURCE OF TRUTH** for all dev tool consumers.

**Writers:**
- Scheduler (policy state)
- Telemetry receiver (link metrics)
- Battery provider (voltage, rate)
- Proxy (packet stats)
- OBS Receiver (remote snapshots)

**Readers:**
- GUI dashboard (read-only)
- Integration layer

**Key Features:**
- RLock-protected state
- History retention for timelines
- Event markers for visualization
- Subscription callbacks
- OBS snapshot ingestion

### 3. GUI Dashboard

**Location:** `devtools/dashboard.py`

Single-page Tkinter dashboard with 5 panels:

1. **SYSTEM STATUS**: Suite, action, cooldown, armed state
2. **BATTERY**: Voltage graph, rate, mode selector, sliders
3. **TELEMETRY**: rx_pps, gap_p95, blackout_count, age
4. **DATA PLANE**: Encrypted/plaintext PPS, replay drops, handshake
5. **TIMELINE**: Voltage vs time, suite switches, policy markers

**Properties:**
- Non-blocking (separate thread)
- Thread-safe (uses data bus locks)
- Configurable refresh rate (5-10 Hz)
- Completely disabled via config
- Can receive remote data via OBS plane

### 4. Battery Bridge

**Location:** `devtools/battery_bridge.py`

Non-invasive injection point for battery providers.

```python
# Usage in scheduler code:
from devtools.battery_bridge import LocalMonitorBridge

# Automatically uses simulation when enabled:
monitor = LocalMonitorBridge.create_with_devtools()
metrics = monitor.get_metrics()  # Battery comes from provider
```

When disabled, this is 100% pass-through to `LocalMonitor`.

### 5. Observability Plane (OBS_PLANE)

**Location:** `devtools/obs_schema.py`, `obs_emitter.py`, `obs_receiver.py`

A **FOURTH, TEMPORARY, DEV-ONLY** network plane that:
- Exists ONLY when explicitly enabled
- Runs alongside existing planes without interfering
- Works over SSH for laptop-based analysis
- Supports BOTH Drone (Raspberry Pi) and GCS (Laptop)
- Feeds a live Tkinter dashboard and offline analysis tools

**Critical Properties:**
- SNAPSHOT-ONLY (no commands, no RPCs, no state mutation)
- Fire-and-forget UDP (no acknowledgments)
- Zero backpressure (drops silently if buffer full)
- Localhost-only for SSH port forwarding

**Components:**

| Component | Purpose |
|-----------|---------|
| `ObsSnapshot` | Wire format for UDP snapshots |
| `ObsEmitter` | Fire-and-forget UDP transmitter |
| `ObsReceiver` | Background UDP listener |
| `MultiReceiver` | Listen on multiple ports |

## Observability Plane Architecture

```
                   SSH TUNNEL
┌─────────────────────────────────────────────────────────────────┐
│                                                                  │
│  ┌────────────┐                              ┌────────────────┐ │
│  │   DRONE    │                              │   LAPTOP/GCS   │ │
│  │  (RPi)     │                              │   (Analysis)   │ │
│  │            │                              │                │ │
│  │ ┌────────┐ │     UDP over SSH tunnel      │ ┌────────────┐ │ │
│  │ │Emitter │─┼──────────────────────────────┼▶│  Receiver  │ │ │
│  │ │:59001  │ │                              │ │  :59001    │ │ │
│  │ └────────┘ │                              │ └─────┬──────┘ │ │
│  │            │                              │       │        │ │
│  │ Scheduler  │                              │   DataBus     │ │
│  │            │                              │       │        │ │
│  └────────────┘                              │   Dashboard   │ │
│                                              │                │ │
│                                              └────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### SSH Port Forwarding Setup

**For monitoring a remote Drone:**
```bash
# On your laptop, forward local port to drone's OBS port:
ssh -L 59001:localhost:59001 user@drone-pi

# Now local receiver on :59001 gets drone's snapshots
```

**For monitoring a remote GCS:**
```bash
# Forward GCS port:
ssh -L 59002:localhost:59002 user@gcs-host
```

**Dual monitoring (both drone and GCS):**
```bash
# Open both tunnels:
ssh -L 59001:localhost:59001 user@drone-pi &
ssh -L 59002:localhost:59002 user@gcs-host &

# Dashboard receives from both
```

### OBS Snapshot Schema

```python
@dataclass
class ObsSnapshot:
    schema: str           # "uav.pqc.obs.snapshot.v1"
    schema_version: int   # 1
    node: str            # "drone" or "gcs"
    node_id: str         # Hostname or custom ID
    timestamp_mono_ms: float  # Monotonic clock (ms)
    timestamp_iso: str   # ISO 8601 UTC
    seq: int             # Sequence number for loss detection
    
    battery: BatterySnapshot
    telemetry: TelemetrySnapshot
    policy: PolicySnapshot
    proxy: ProxySnapshot
```

## Configuration

All features controlled via `settings.json`:

```json
{
    "dev_tools": {
        "enabled": false,
        "battery_simulation": {
            "enabled": false,
            "default_mode": "stable",
            "start_mv": 16000,
            "min_mv": 13000,
            "max_mv": 17000,
            "slow_drain_mv_per_sec": 5.0,
            "fast_drain_mv_per_sec": 20.0,
            "throttle_drain_factor": 2.0,
            "step_drop_mv": 2000,
            "recovery_mv_per_sec": 10.0
        },
        "gui": {
            "enabled": false,
            "refresh_hz": 5.0,
            "window_width": 1200,
            "window_height": 800,
            "timeline_points": 300,
            "graph_update_hz": 2.0
        },
        "observability_plane": {
            "enabled": false,
            "node_id": "",
            "drone_port": 59001,
            "gcs_port": 59002,
            "listen_host": "127.0.0.1",
            "emit_interval_ms": 200.0,
            "emit_on_change": true,
            "receive_drone": true,
            "receive_gcs": true
        },
        "bus_history_size": 1000,
        "bus_log_enabled": false,
        "bus_log_path": null
    }
}
```

**Rules:**
- When `dev_tools.enabled = false` → **NO DEV CODE ACTIVE**
- No branching scattered across files
- Centralized enablement logic only

## Usage

### Enable Dev Tools for Lab Testing

1. Edit `settings.json`:
```json
{
    "dev_tools": {
        "enabled": true,
        "battery_simulation": { "enabled": true },
        "gui": { "enabled": true },
        "observability_plane": { "enabled": true }
    }
}
```

2. Run launcher:
```bash
python -m devtools.launcher
```

### Standalone GUI Mode

Run GUI without scheduler (for testing):
```bash
python -m devtools.launcher --standalone
```

### Data Bus Only

Enable observability without GUI:
```bash
python -m devtools.launcher --data-bus-only
```

### OBS Plane Remote Monitoring

**On the drone (Raspberry Pi):**
1. Enable OBS plane in `settings.json`:
```json
{
    "dev_tools": {
        "enabled": true,
        "observability_plane": { "enabled": true }
    }
}
```

2. Run scheduler with dev tools integration:
```bash
python sscheduler/sdrone.py
```

**On your laptop:**
1. Set up SSH tunnel:
```bash
ssh -L 59001:localhost:59001 pi@drone-hostname
```

2. Run dashboard with OBS receiver:
```bash
python -m devtools.launcher --obs-receive
```

### Test OBS Plane

Run verification tests:
```bash
python -m devtools.test_obs_plane
```

## Safety Guarantees

### Production Path Unchanged

When `dev_tools.enabled = false`:
1. `devtools.is_enabled()` returns `False`
2. `get_integration()` returns `NullIntegration` (all methods are no-ops)
3. `LocalMonitorBridge.create_with_devtools()` returns pure pass-through
4. No GUI threads started
5. No battery simulation active
7. No OBS plane emitters/receivers started
8. Zero performance impact

### Isolation Guarantees

1. **GUI cannot affect policy decisions** - GUI is read-only from data bus
2. **Simulation cannot leak** - Battery provider only active when explicitly enabled
3. **No scheduler/policy modifications** - All dev code in separate `devtools/` module
4. **No hidden dev flags** - All configuration explicit in `settings.json`

### Verification

Run the verification script:
```bash
python -c "
import devtools
from devtools.integration import get_integration, NullIntegration

# When disabled:
assert devtools.is_enabled() == False
assert isinstance(get_integration(), NullIntegration)
print('Production behavior verified: dev tools inactive')
"
```

## Integration Points

### Scheduler Integration

```python
from devtools.integration import get_integration

# Creates NullIntegration if disabled
integration = get_integration()

# Safe to call unconditionally (no-op when disabled)
integration.update_policy(
    current_suite=suite_name,
    current_action=action,
    target_suite=target,
    confidence=0.95
)

integration.update_telemetry(
    rx_pps=10.0,
    gap_p95_ms=150.0,
    telemetry_age_ms=200.0
)
```

### Battery Provider Bridge

```python
from devtools.battery_bridge import get_local_monitor

# Returns LocalMonitorBridge with auto-configured provider
monitor = get_local_monitor()
monitor.start()

# get_metrics() returns LocalMetrics with battery from:
#   - MAVLink (when dev_tools disabled)
#   - SimulatedBatteryProvider (when battery_simulation enabled)
metrics = monitor.get_metrics()
```

### OBS Plane Integration

```python
from devtools.integration import DevToolsIntegration

# Create integration with OBS plane for drone
integration = DevToolsIntegration.create_if_enabled(node_type="drone")
integration.start()

# Updates are automatically emitted via OBS plane
integration.update_policy(
    current_suite=suite_name,
    current_action=action,
    confidence=0.95
)

# Force immediate snapshot emission
integration.emit_snapshot_now()
```

### Manual OBS Emitter

```python
import devtools
from devtools.obs_schema import BatterySnapshot, PolicySnapshot

# Create and start emitter
emitter = devtools.create_obs_emitter(node_type="drone")

# Emit snapshots
emitter.emit_snapshot(
    battery=BatterySnapshot(voltage_mv=15000),
    policy=PolicySnapshot(current_suite="KYBER768_ASCON128"),
)
```

### Manual OBS Receiver

```python
import devtools

# Create and start multi-receiver
receiver = devtools.create_multi_receiver()

# Connect to data bus
data_bus = devtools.get_data_bus()
receiver.add_callback(lambda snap: data_bus.update_from_obs_snapshot(snap))

receiver.start()
```

## File Structure

```
secure-tunnel/
├── devtools/                    # DEV-ONLY MODULE
│   ├── __init__.py              # Enable/disable gate
│   ├── config.py                # Configuration
│   ├── data_bus.py              # Observability bus
│   ├── battery_sim.py           # Battery simulation
│   ├── battery_bridge.py        # Injection bridge
│   ├── dashboard.py             # Tkinter GUI
│   ├── integration.py           # Scheduler hooks
│   ├── obs_schema.py            # OBS snapshot schema
│   ├── obs_emitter.py           # UDP emitter
│   ├── obs_receiver.py          # UDP receiver
│   ├── test_obs_plane.py        # OBS verification tests
│   └── launcher.py              # Entry point
│
├── settings.json                # Configuration (has dev_tools section)
│
├── sscheduler/                  # PRODUCTION (UNCHANGED)
│   ├── sdrone.py                # Drone scheduler
│   ├── sgcs.py                  # GCS scheduler
│   ├── policy.py                # Policy engine
│   └── local_mon.py             # Local monitor
│
└── core/                        # PRODUCTION (UNCHANGED)
    ├── async_proxy.py           # Proxy engine
    ├── handshake.py             # PQC handshake
    └── ...
```

## Testing

### Test All Imports
```bash
python -c "from devtools import is_enabled; print(f'enabled={is_enabled()}')"
```

### Test Battery Simulation
```bash
python -c "
from devtools.battery_sim import SimulatedBatteryProvider, SimulationMode
from devtools.config import BatterySimConfig

config = BatterySimConfig(enabled=True)
provider = SimulatedBatteryProvider(config)
provider.start()
provider.set_mode(SimulationMode.FAST_DRAIN)
import time; time.sleep(1)
print(f'Voltage after 1s drain: {provider.get_battery_mv()} mV')
provider.stop()
"
```

### Test GUI (Manual)
```bash
# Enable in settings.json first, then:
python -m devtools.launcher --standalone
```

## Troubleshooting

### GUI Not Starting
1. Check `dev_tools.enabled` is `true`
2. Check `dev_tools.gui.enabled` is `true`
3. Ensure Tkinter is installed: `python -c "import tkinter"`

### Battery Simulation Not Active
1. Check `dev_tools.enabled` is `true`
2. Check `dev_tools.battery_simulation.enabled` is `true`
3. Verify with: `python -c "import devtools; print(devtools.get_battery_provider().is_simulated())"`

### Scheduler Not Using Dev Tools
Ensure scheduler uses `LocalMonitorBridge.create_with_devtools()` or `get_local_monitor()`.

## Removal

To completely remove dev tools from the codebase:
1. Delete `devtools/` directory
2. Remove `dev_tools` section from `settings.json`
3. No other changes required (production code has no dependencies)
