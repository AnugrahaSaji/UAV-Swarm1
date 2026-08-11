# Table Reasoning: Scheduler Safety Thresholds and Detector Constraints

## Target table
- Manuscript table: `tab:scheduler-thresholds-constraints`
- File: `vtc/results.tex`

## Source of truth
- Code file: `sscheduler/policy.py`

## Extracted constants (code-backed)
1. Global settings defaults from `load_settings()`:
   - `battery`: `critical_mv=14000`, `low_mv=14800`, `warn_mv=15200`, `rate_warn_mv_per_min=500`
   - `thermal`: `critical_c=80.0`, `warn_c=70.0`, `rate_warn_c_per_min=5.0`

2. Detector empirical overhead (`_DETECTOR_OVERHEAD`):
   - `NONE`: `ΔP=0.00 W`, `ΔT=0.0°C`, `ΔCPU=0 pp`
   - `XGBOOST`: `ΔP=0.95 W`, `ΔT=4.8°C`, `ΔCPU=35 pp`
   - `TST`: `ΔP=1.97 W`, `ΔT=10.7°C`, `ΔCPU=91 pp`

3. Detector gating thresholds:
   - `_DETECTOR_MAX_BASELINE_TEMP`:
     - `NONE=80.0°C`, `XGBOOST=75.0°C`, `TST=69.0°C`
   - `_DETECTOR_WARMUP_S`:
     - `NONE=0.0 s`, `XGBOOST=10.0 s`, `TST=5.0 s`

4. Cross-axis constraints:
   - `_FORBIDDEN_AEAD_WITH_TST = {"ascon128a"}`
   - `_DISCOURAGED_KEM_WITH_TST = {"classicmceliece348864", "classicmceliece460896", "classicmceliece8192128"}`
   - `_FORBIDDEN_KEM_SIG_PAIRS` includes:
     - (`classicmceliece348864`, `sphincs128s`)
     - (`classicmceliece460896`, `sphincs192s`)
     - (`classicmceliece8192128`, `sphincs256s`)
     - plus listed cross-level variants in the same set.

## Reproducibility
- Values are copied directly from constant definitions in `sscheduler/policy.py`.
- No post-processing computation is applied for this table.

## Notes
- This table is intentionally code-traceable: every value maps to a named constant.
- It represents policy constraints and gates (not inferred runtime averages).
