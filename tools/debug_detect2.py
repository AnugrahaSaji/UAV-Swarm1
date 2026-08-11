#!/usr/bin/env python3
"""Debug PowerCollector detection with verbose output."""
import sys, os
os.environ["INA219_DETECT_DEBUG"] = "1"  # we'll add this debug flag
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import core.metrics_collectors as mc
print(f"HAS_SMBUS2: {mc.HAS_SMBUS2}")
print(f"HAS_INA219: {mc.HAS_INA219}")
print(f"_INA219_BACKEND: {mc._INA219_BACKEND}")

# Manually instantiate with debug
pc = mc.PowerCollector(backend="auto")
print(f"\nResult: backend={pc.backend}, ina_backend={pc._ina_backend}")
print(f"_smbus={pc._smbus}")

# Test collect
d = pc.collect()
print(f"collect(): {d}")
