#!/usr/bin/env python3
"""Test: dummy read to wake I2C bus, then actual reads."""
import smbus2
import time

bus = smbus2.SMBus(1)

# Try several dummy operations to "warm up" the bus
print("=== Phase 1: Warm-up (dummy reads) ===")
for i in range(5):
    try:
        bus.read_byte(0x40)
        print(f"  dummy {i+1}: OK")
    except:
        print(f"  dummy {i+1}: fail (expected)")
    time.sleep(0.1)

print("\n=== Phase 2: Actual register reads ===")
for i in range(10):
    try:
        data = bus.read_i2c_block_data(0x40, 0x00, 2)
        val = (data[0] << 8) | data[1]
        print(f"  [{i+1:2d}] OK  config=0x{val:04X}")
    except Exception as e:
        print(f"  [{i+1:2d}] FAIL {e}")
    time.sleep(0.2)

print("\n=== Phase 3: i2c_rdwr after warm-up ===")
from smbus2 import i2c_msg
for i in range(10):
    try:
        write = i2c_msg.write(0x40, [0x00])
        read = i2c_msg.read(0x40, 2)
        bus.i2c_rdwr(write, read)
        data = list(read)
        val = (data[0] << 8) | data[1]
        print(f"  [{i+1:2d}] OK  config=0x{val:04X}")
    except Exception as e:
        print(f"  [{i+1:2d}] FAIL {e}")
    time.sleep(0.2)

print("\n=== Phase 4: Single byte reads (like i2cdump b) ===")
for reg in range(6):
    try:
        val = bus.read_byte_data(0x40, reg)
        print(f"  reg 0x{reg:02X}: 0x{val:02X}")
    except Exception as e:
        print(f"  reg 0x{reg:02X}: FAIL {e}")
    time.sleep(0.1)

print("\n=== Phase 5: Word reads ===")
for reg in range(6):
    try:
        val = bus.read_word_data(0x40, reg)
        # byte swap
        val = ((val & 0xFF) << 8) | ((val >> 8) & 0xFF)
        print(f"  reg 0x{reg:02X}: 0x{val:04X}")
    except Exception as e:
        print(f"  reg 0x{reg:02X}: FAIL {e}")
    time.sleep(0.1)

bus.close()
print("\nDone.")
