# Scheduler Policy Reconstruction — MDEAS

## Policy Classes

### TelemetryAwarePolicyV2 (Single-Axis)
**Purpose**: Legacy policy for simple NIST-level--based suite selection.
**Decision axis**: Suite tier (NIST level + KEM complexity + AEAD cost)

**Gate cascade** (evaluated in priority order):
1. Telemetry stale (age > 2000ms) → HOLD
2. Battery/temp CRITICAL → DOWNGRADE to lowest tier
3. Link failure + blackout → ROLLBACK + blacklist suite
4. Cooldown active → HOLD
5. Link degradation (hysteresis 5s) → DOWNGRADE
6. Thermal/battery stress (hysteresis 5s) → DOWNGRADE
7. Stable > min_stable_s → REKEY (same suite)
8. Disarmed + stable + no stress (hysteresis 30s) → UPGRADE

### EnergyAwarePolicy (3-Axis MDEAS)
**Purpose**: Measurement-Driven Energy-Aware Scheduling
**Three independent decision axes**:
- **Axis 1 (Data-plane)**: AEAD cipher selection via measured cost profiles
- **Axis 2 (Control-plane)**: NIST security level selection
- **Axis 3 (Compute-plane)**: DDoS detector lifecycle management

**12-Gate Decision Cascade**:
1. Telemetry stale → HOLD
2. DDoS detected → EMERGENCY (cheapest AEAD, L1)
3. Battery critical (<14000 mV) → EMERGENCY (L1 + cheapest AEAD, kill detector)
4. Temp critical (>80°C) → EMERGENCY (L1 + cheapest AEAD, kill detector)
5. Detector thermal overload → DOWNGRADE_DETECTOR
6. Predictive thermal crossing → SWITCH_AEAD (proactive with ΔT model)
7. Stress + hysteresis → SWITCH_AEAD with break-even check
8. AEAD recovery → upgrade toward preferred AEAD
9. Link degradation → DOWNGRADE_LEVEL
10. Cooldown active → HOLD
11. Stable → REKEY or UPGRADE_LEVEL
12. Can activate detector → UPGRADE_DETECTOR

## Suite Tier Computation
```python
def get_suite_tier(suite_name: str) -> int:
    # NIST level base: L1=0, L3=10, L5=20
    nist = get_nist_level(suite_name)
    base = {1: 0, 3: 10, 5: 20}[nist]
    
    # KEM complexity: mlkem=0, sntrup=2, hqc=3, frodokem=4, mceliece=5
    kem = extract_kem(suite_name)
    kem_cost = {"mlkem": 0, "sntrup": 2, "hqc": 3, "frodokem": 4, "mceliece": 5}[kem]
    
    # AEAD cost: aesgcm=0, chacha=1, ascon=2
    aead = extract_aead(suite_name)
    aead_cost = {"aesgcm": 0, "chacha": 1, "ascon": 2}[aead]
    
    return base + kem_cost + aead_cost
```

## AEAD Cost Profiles (AeadCostProfile)
```python
class AeadCostProfile:
    aead_name: str          # e.g., "aesgcm"
    encrypt_ns: float       # EWMA-smoothed encrypt latency
    decrypt_ns: float       # EWMA-smoothed decrypt latency  
    total_ns: float         # encrypt_ns + decrypt_ns
    power_mw: float         # Measured power during AEAD ops
    temp_delta_c: float     # Temperature increase per operation
    energy_per_bit_nj: float  # Derived energy efficiency metric
    sample_count: int       # Observation count
```

**Benchmark-Seeded Initialization (BSI)**: Pre-populated from INA219 power measurements.
**Runtime Updates**: EWMA with α=0.1 from live proxy counters.

## Break-Even Analysis
```python
break_even_s = rekey_cost_ns / (saving_per_pkt_ns × pkt_rate_hz × 2)
# saving_per_pkt_ns = |current.total_ns - target.total_ns|
# pkt_rate_hz = observed packet rate (bi-directional × 2)
# Under stress: accept break_even ≤ 120s
# Normal recovery: require break_even ≥ 30s
# Recovery: only if cost_ratio ≤ 2.0 and temp well below warn_c
```

## Threshold Constants (from settings.json)
| Parameter | Value | Source |
|-----------|-------|--------|
| battery.critical_mv | 14000 | settings.json |
| battery.low_mv | 14800 | settings.json |
| battery.warn_mv | 15200 | settings.json |
| battery.rate_warn_mv_per_min | 500 | settings.json |
| thermal.critical_c | 80.0 | settings.json |
| thermal.warn_c | 70.0 | settings.json |
| thermal.rate_warn_c_per_min | 5.0 | settings.json |
| rekey.min_stable_s | 60.0 | settings.json |
| rekey.max_per_window | 5 | settings.json |
| rekey.window_s | 300 | settings.json |
| rekey.blacklist_ttl_s | 1800 | settings.json |
| hysteresis.downgrade_s | 5.0 | settings.json |
| hysteresis.upgrade_s | 30.0 | settings.json |
| hysteresis.aead_recovery_s | 10.0 | settings.json |

## Cross-Axis Constraints
| Combination | Status | Reason |
|-------------|--------|--------|
| Ascon + TST | FORBIDDEN | Incompatible (CPU contention) |
| McEliece + SPHINCS+ | FORBIDDEN | Handshake timeout issues |
| McEliece + TST | DISCOURAGED | High combined CPU |

## Detector Overhead Budgets (MDEAS Axis 3)
| Detector | Max Power | Max Temp Impact | Max CPU | Max Baseline Temp | Warmup |
|----------|-----------|-----------------|---------|-------------------|--------|
| XGBOOST | +0.95 W | +4.8°C | +35% | 75°C | 10s |
| TST | +1.97 W | +10.7°C | +91% | 69°C | 5s |
| LGBM | implied | implied | implied | implied | 5s |
| RF | implied | implied | implied | implied | 15s |
