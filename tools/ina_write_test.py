#!/usr/bin/env python3
"""Test if write_i2c_block_data breaks the warm-up state."""
import smbus2, time

ADDR = 0x40

print("=== Sequence 1: warm-up → read (no write) ===")
bus = smbus2.SMBus(1)
try:
    bus.read_byte_data(ADDR, 0)
except OSError as e:
    print(f"  warm-up: {e}")
try:
    hi, lo = bus.read_i2c_block_data(ADDR, 0x01, 2)
    print(f"  block read reg 1: OK  0x{(hi<<8)|lo:04X}")
except OSError as e:
    print(f"  block read reg 1: FAIL {e}")
bus.close()

print()
print("=== Sequence 2: warm-up → write → read ===")
bus = smbus2.SMBus(1)
try:
    bus.read_byte_data(ADDR, 0)
except OSError as e:
    print(f"  warm-up: {e}")
# write config (same as _configure does)
cfg = 0x399F  # default config
payload = [(cfg >> 8) & 0xFF, cfg & 0xFF]
try:
    bus.write_i2c_block_data(ADDR, 0x00, payload)
    print(f"  write config: OK")
except OSError as e:
    print(f"  write config: FAIL {e}")
time.sleep(0.002)
try:
    hi, lo = bus.read_i2c_block_data(ADDR, 0x01, 2)
    print(f"  block read reg 1: OK  0x{(hi<<8)|lo:04X}")
except OSError as e:
    print(f"  block read reg 1: FAIL {e}")
    # retry
    time.sleep(0.005)
    try:
        hi, lo = bus.read_i2c_block_data(ADDR, 0x01, 2)
        print(f"  block read reg 1 RETRY: OK  0x{(hi<<8)|lo:04X}")
    except OSError as e2:
        print(f"  block read reg 1 RETRY: FAIL {e2}")
bus.close()

print()
print("=== Sequence 3: warm-up → write_byte_data → read ===")
bus = smbus2.SMBus(1)
try:
    bus.read_byte_data(ADDR, 0)
except OSError as e:
    print(f"  warm-up: {e}")
try:
    bus.write_byte_data(ADDR, 0x00, 0x39)
    print(f"  write_byte_data: OK")
except OSError as e:
    print(f"  write_byte_data: FAIL {e}")
try:
    hi, lo = bus.read_i2c_block_data(ADDR, 0x01, 2)
    print(f"  block read reg 1: OK  0x{(hi<<8)|lo:04X}")
except OSError as e:
    print(f"  block read reg 1: FAIL {e}")
bus.close()

print()
print("=== Sequence 4: warm-up → write_word_data → read ===")
bus = smbus2.SMBus(1)
try:
    bus.read_byte_data(ADDR, 0)
except OSError as e:
    print(f"  warm-up: {e}")
try:
    bus.write_word_data(ADDR, 0x00, 0x9F39)  # swapped for SMBus byte order
    print(f"  write_word_data: OK")
except OSError as e:
    print(f"  write_word_data: FAIL {e}")
try:
    hi, lo = bus.read_i2c_block_data(ADDR, 0x01, 2)
    print(f"  block read reg 1: OK  0x{(hi<<8)|lo:04X}")
except OSError as e:
    print(f"  block read reg 1: FAIL {e}")
bus.close()

print()
print("=== Sequence 5: double warm-up → write_i2c_block → read ===")
bus = smbus2.SMBus(1)
for i in range(3):
    try:
        val = bus.read_byte_data(ADDR, 0)
        print(f"  warm-up {i}: OK val=0x{val:02X}")
    except OSError as e:
        print(f"  warm-up {i}: {e}")
try:
    bus.write_i2c_block_data(ADDR, 0x00, payload)
    print(f"  write_i2c_block: OK")
except OSError as e:
    print(f"  write_i2c_block: FAIL {e}")
time.sleep(0.002)
for i in range(3):
    try:
        hi, lo = bus.read_i2c_block_data(ADDR, 0x01, 2)
        print(f"  block read {i}: OK  0x{(hi<<8)|lo:04X}")
    except OSError as e:
        print(f"  block read {i}: FAIL {e}")
        time.sleep(0.001)
bus.close()

print("\nDone.")
