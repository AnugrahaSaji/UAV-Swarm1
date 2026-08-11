#!/usr/bin/env python3
"""Minimal reproduction of voltage=0 bug."""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.metrics_collectors import PowerCollector

pc = PowerCollector(backend="auto")
print(f"Backend: {pc.backend}, INA: {pc._ina_backend}")
print(f"_smbus fd: {pc._smbus.fd if pc._smbus else None}")
print(f"_ina219: {pc._ina219}")

# Test A: tight loop collects
print("\n=== Test A: tight loop (no sleep) ===")
for i in range(5):
    d = pc.collect()
    print(f"  [{i}] V={d.get('voltage_v')}, I={d.get('current_a')}")

# Test B: with sleep
print("\n=== Test B: with 0.1s sleep ===")
for i in range(5):
    d = pc.collect()
    print(f"  [{i}] V={d.get('voltage_v')}, I={d.get('current_a')}")
    time.sleep(0.1)

# Test C: raw read between collects
print("\n=== Test C: raw read between collects ===")
bus = pc._smbus
addr = pc._ina_address
for i in range(5):
    # raw read
    try:
        w = bus.read_word_data(addr, 0x02)
        raw = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
        vbus = ((raw >> 3) & 0x1FFF) * 0.004
        print(f"  raw[{i}] V={vbus:.3f}")
    except OSError as e:
        print(f"  raw[{i}] FAIL: {e}")
    # collect
    d = pc.collect()
    print(f"  col[{i}] V={d.get('voltage_v')}, I={d.get('current_a')}")
