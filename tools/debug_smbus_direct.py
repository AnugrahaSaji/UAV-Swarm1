#!/usr/bin/env python3
"""Debug smbus2_direct detection path."""
import smbus2, os

busnum = 1
addr = 0x40

print("=== Fresh process: smbus2_direct detection ===")
bus = smbus2.SMBus(busnum)

print("Step 1: warm-up read_byte_data")
try:
    v = bus.read_byte_data(addr, 0x00)
    print(f"  OK val=0x{v:02X}")
except OSError as e:
    print(f"  EIO: {e}")

print("Step 2: 5x read_word_data retries")
for i in range(5):
    try:
        word_le = bus.read_word_data(addr, 0x00)
        raw = ((word_le & 0xFF) << 8) | ((word_le >> 8) & 0xFF)
        print(f"  [{i}] OK raw=0x{raw:04X}")
    except OSError as e:
        print(f"  [{i}] FAIL: {e}")

print()
print("Step 3: Now try continuous reads")
for i in range(10):
    try:
        w = bus.read_word_data(addr, 0x02)
        raw = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
        vbus = ((raw >> 3) & 0x1FFF) * 0.004
        
        w2 = bus.read_word_data(addr, 0x01)
        raw_sh = ((w2 & 0xFF) << 8) | ((w2 >> 8) & 0xFF)
        if raw_sh & 0x8000:
            raw_sh -= 1 << 16
        shunt_v = raw_sh * 10e-6
        current_a = abs(shunt_v / 0.1)
        print(f"  [{i}] V={vbus:.3f}V  I={current_a:.4f}A  P={vbus*current_a:.3f}W")
    except OSError as e:
        print(f"  [{i}] FAIL: {e}")

bus.close()
print("Done.")
