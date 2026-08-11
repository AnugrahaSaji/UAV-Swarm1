# Simulation Removal & Isolation Plan

To transition the `secure-tunnel` from a test/benchmarking harness to a pure production system, follow these steps to remove or isolate simulation artifacts.

## 1. Artifacts to Remove

The following files and classes are used solely for generating synthetic data or traffic.

| Component | Location | Action | Reason |
| :--- | :--- | :--- | :--- |
| `SyntheticKinematicsModel` | `auto/drone_follower.py` | **DELETE** | Generates fake flight data. Dangerous in production. |
| `Blaster` | `auto/gcs_scheduler.py` | **DELETE** | UDP traffic generator. Not needed for real ops. |
| `TrafficGenerator` | `sscheduler/sgcs.py` | **DISABLE** | Used for link testing. Ensure it's not triggered in flight. |
| `UdpEchoServer` | `sscheduler/sdrone.py` | **DISABLE** | Used for loopback testing. |

## 2. Configuration Cleanup

Edit `core/config.py` to remove simulation defaults.

**Remove these keys from `AUTO_DRONE_CONFIG`:**
```python
"mock_mass_kg": 6.5,
"kinematics_update_rate_hz": 50,
```

## 3. Operational Transition

**Do NOT use:**
*   `auto/drone_follower.py`
*   `auto/gcs_scheduler.py`

**USE instead:**
*   `sscheduler/sdrone.py` (Drone Controller)
*   `sscheduler/sgcs.py` (GCS Follower)

## 4. Verification

After cleanup, verify that `sscheduler/sdrone.py` is configured to read from the real MAVLink master:

```bash
# On Drone
python -m sscheduler.sdrone --mav-master=/dev/ttyACM0
```

Ensure `sscheduler/gcs_metrics.py` is receiving real MAVLink packets from the GCS MAVProxy instance, not a simulator.
