#!/usr/bin/env python3
"""Quick INA219 sensor verification script."""
import os, time, json

os.environ.setdefault("DRONE_POWER_BACKEND", "ina219")
os.environ.setdefault("INA219_I2C_BUS", "1")
os.environ.setdefault("INA219_ADDR", "0x40")
os.environ.setdefault("INA219_SHUNT_OHM", "0.1")

from core.metrics_collectors import PowerCollector

pc = PowerCollector(backend="auto")
print("BACKEND:", pc.backend)
print("INA219_OBJ:", type(pc._ina219).__name__ if pc._ina219 else "None")

if pc.backend == "ina219":
    samples = []
    for i in range(5):
        r = pc.collect()
        v = r.get("bus_voltage_v") or r.get("voltage_v")
        a = r.get("current_a") or r.get("current_ma")
        w = r.get("power_w") or r.get("power_mw")
        print(f"Sample {i}: V={v}  A={a}  W={w}")
        samples.append({"v": v, "a": a, "w": w})
        time.sleep(0.4)
    valid = sum(1 for s in samples if s["v"] and s["v"] > 0)
    print(f"\nValid readings: {valid}/5")
    print("SENSOR_OK" if valid >= 3 else "SENSOR_FAIL")
else:
    print("SENSOR_FAIL: backend =", pc.backend)
