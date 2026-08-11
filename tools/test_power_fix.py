#!/usr/bin/env python3
"""Verify Ina219PowerMonitor and PowerCollector after BCM2835 warm-up fix."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pathlib import Path

print("=== Test 1: Ina219PowerMonitor ===")
try:
    from core.power_monitor import Ina219PowerMonitor
    pm = Ina219PowerMonitor(Path("/tmp/ina_test"), sample_hz=100)
    print(f"  Init OK, sign_factor={pm.sign_factor}")
    summary = pm.capture(label="quick_test", duration_s=2.0)
    print(f"  Capture OK: {summary.samples} samples")
    print(f"  Avg voltage: {summary.avg_voltage_v:.3f} V")
    print(f"  Avg current: {summary.avg_current_a:.4f} A")
    print(f"  Avg power:   {summary.avg_power_w:.3f} W")
    print(f"  Energy:      {summary.energy_j:.4f} J")
    print(f"  CSV: {summary.csv_path}")
except Exception as e:
    print(f"  FAIL: {e}")
    import traceback; traceback.print_exc()

print()

print("=== Test 2: PowerCollector ===")
try:
    from core.metrics_collectors import PowerCollector
    pc = PowerCollector()
    print(f"  Backend: {pc.backend}")
    print(f"  INA backend: {pc._ina_backend}")
    data = pc.collect()
    for k, v in sorted(data.items()):
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")
except Exception as e:
    print(f"  FAIL: {e}")
    import traceback; traceback.print_exc()

print()
print("=== Test 3: create_power_monitor (auto) ===")
try:
    from core.power_monitor import create_power_monitor
    pm2 = create_power_monitor(Path("/tmp/ina_test2"), sample_hz=100)
    print(f"  Type: {type(pm2).__name__}")
    summary2 = pm2.capture(label="auto_test", duration_s=1.0)
    print(f"  Avg voltage: {summary2.avg_voltage_v:.3f} V")
    print(f"  Avg current: {summary2.avg_current_a:.4f} A") 
    print(f"  Avg power:   {summary2.avg_power_w:.3f} W")
except Exception as e:
    print(f"  FAIL: {e}")
    import traceback; traceback.print_exc()

print("\nDone.")
