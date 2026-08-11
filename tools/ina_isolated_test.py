#!/usr/bin/env python3
"""Isolated test: exact power_monitor init sequence in a fresh process."""
import smbus2, time, struct

ADDR = 0x40

bus = smbus2.SMBus(1)

# Step 1: warm-up
print("Step 1: read_byte_data warm-up")
try:
    v = bus.read_byte_data(ADDR, 0x00)
    print(f"  OK val=0x{v:02X}")
except OSError as e:
    print(f"  EIO (expected): {e}")

# Step 2: second warm-up read (to confirm bus is warm)
print("Step 2: confirm warm-up")
try:
    v = bus.read_byte_data(ADDR, 0x00)
    print(f"  OK val=0x{v:02X}")
except OSError as e:
    print(f"  FAIL: {e}")

# Step 3a: write_word_data (what _configure should use)
cfg = 0x399F
word_le = ((cfg & 0xFF) << 8) | ((cfg >> 8) & 0xFF)
print(f"Step 3a: write_word_data(0x00, 0x{word_le:04X})")
try:
    bus.write_word_data(ADDR, 0x00, word_le)
    print(f"  OK")
except OSError as e:
    print(f"  FAIL: {e}")

time.sleep(0.005)

# Step 4a: read_word_data
print("Step 4a: read_word_data(0x01)")
try:
    w = bus.read_word_data(ADDR, 0x01)
    swapped = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
    print(f"  OK raw=0x{w:04X} swapped=0x{swapped:04X}")
except OSError as e:
    print(f"  FAIL: {e}")

# Step 4b: read_byte_data
print("Step 4b: read_byte_data(0x01)")
try:
    v = bus.read_byte_data(ADDR, 0x01)
    print(f"  OK val=0x{v:02X}")
except OSError as e:
    print(f"  FAIL: {e}")

bus.close()

print()
print("=== Alternative: use write_byte_data x2 instead of write_word_data ===")
bus = smbus2.SMBus(1)

print("Step 1: warm-up")
try:
    v = bus.read_byte_data(ADDR, 0x00)
    print(f"  OK val=0x{v:02X}")
except OSError as e:
    print(f"  EIO: {e}")

print("Step 2: write config as 2 x write_byte_data")
try:
    bus.write_byte_data(ADDR, 0x00, (cfg >> 8) & 0xFF)
    print(f"  write hi byte: OK")
except OSError as e:
    print(f"  write hi byte: FAIL {e}")
    
# INA219 auto-increments register pointer? No, need to write both bytes 
# to register 0x00 at once. Let me try write_word_data on fresh bus.
# Actually for INA219 the 16-bit register write needs both bytes in one transaction.

time.sleep(0.005)
print("Step 3: read_word_data(0x00) to check config")
try:
    w = bus.read_word_data(ADDR, 0x00)
    swapped = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
    print(f"  OK raw=0x{w:04X} config=0x{swapped:04X}")
except OSError as e:
    print(f"  FAIL: {e}")

print("Step 4: read_word_data(0x01) shunt voltage")
try:
    w = bus.read_word_data(ADDR, 0x01)
    swapped = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
    print(f"  OK raw=0x{w:04X} shunt_v=0x{swapped:04X}")
except OSError as e:
    print(f"  FAIL: {e}")

print("Step 5: read_word_data(0x02) bus voltage")
try:
    w = bus.read_word_data(ADDR, 0x02)
    swapped = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
    vbus = ((swapped >> 3) & 0x1FFF) * 0.004
    print(f"  OK raw=0x{w:04X} bus_v={vbus:.3f}V")
except OSError as e:
    print(f"  FAIL: {e}")

bus.close()

print()
print("=== Skip configure: just warm-up and read ===")
bus = smbus2.SMBus(1)
print("Step 1: warm-up")
try:
    bus.read_byte_data(ADDR, 0x00)
except OSError:
    print("  EIO (expected)")

print("Step 2: 5x read_word_data")
for reg in range(5):
    try:
        w = bus.read_word_data(ADDR, reg)
        swapped = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
        print(f"  reg {reg}: 0x{swapped:04X}")
    except OSError as e:
        print(f"  reg {reg}: FAIL {e}")

bus.close()
print("Done.")
