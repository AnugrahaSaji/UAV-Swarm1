#!/usr/bin/env python3
"""Debug PowerCollector sampling - find why power_w is None."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.metrics_collectors import PowerCollector

pc = PowerCollector(backend="auto")
print(f"Backend: {pc.backend}, INA: {pc._ina_backend}")

# Manual collect x5
print("\n=== Manual collect() x5 ===")
for i in range(5):
    d = pc.collect()
    print(f"  [{i}] V={d.get('voltage_v')}, A={d.get('current_a')}, W={d.get('power_w')}, err={d.get('error')}")
    time.sleep(0.1)

# Sampling
print("\n=== Sampling 2s @ 10Hz ===")
pc.start_sampling(rate_hz=10)
time.sleep(2)
samples = pc.stop_sampling()
print(f"  Total samples: {len(samples)}")
valid = [s for s in samples if isinstance(s.get("power_w"), (int, float)) and s["power_w"] > 0.01]
print(f"  Valid samples: {len(valid)}")
if not valid and samples:
    # Show first few
    for i, s in enumerate(samples[:3]):
        print(f"  Sample {i}: V={s.get('voltage_v')}, A={s.get('current_a')}, W={s.get('power_w')}, err={s.get('error')}")
elif valid:
    powers = [s["power_w"] for s in valid]
    print(f"  Power range: {min(powers):.3f} - {max(powers):.3f} W")
