#!/usr/bin/env python3
"""Debug smbus2_direct collect() voltage=0 issue."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.metrics_collectors import PowerCollector
import smbus2

pc = PowerCollector(backend="auto")
print(f"Backend: {pc.backend}, INA: {pc._ina_backend}")
print(f"_smbus: {pc._smbus}")
print(f"_ina219: {pc._ina219}")

bus = pc._smbus
addr = pc._ina_address

print(f"\n=== Direct reads on cached smbus (same fd as detect) ===")
for i in range(10):
    try:
        w = bus.read_word_data(addr, 0x02)
        raw = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
        vbus = ((raw >> 3) & 0x1FFF) * 0.004
        
        w2 = bus.read_word_data(addr, 0x01)
        raw_sh = ((w2 & 0xFF) << 8) | ((w2 >> 8) & 0xFF)
        if raw_sh & 0x8000:
            raw_sh -= 1 << 16
        current_a = abs(raw_sh * 10e-6 / 0.1)
        print(f"  [{i}] V={vbus:.3f}V  I={current_a:.4f}A  raw_v=0x{raw:04X} raw_sh=0x{((w2 & 0xFF) << 8) | ((w2 >> 8) & 0xFF):04X}")
    except OSError as e:
        print(f"  [{i}] FAIL: {e}")

print(f"\n=== Now call collect() 5x ===")
for i in range(5):
    d = pc.collect()
    print(f"  [{i}] V={d.get('voltage_v')}, I={d.get('current_a')}, err={d.get('error')}")
