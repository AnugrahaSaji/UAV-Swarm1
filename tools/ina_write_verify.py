#!/usr/bin/env python3
"""Verify if INA219 register writes ACTUALLY take effect on BCM2835.
Test by writing non-default values and reading back."""
import time
from smbus2 import SMBus

I2C_BUS = 1
INA_ADDR = 0x40

def read_u16(bus, reg):
    for att in range(3):
        try:
            w = bus.read_word_data(INA_ADDR, reg)
            val = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
            if val == 0 and att < 2 and reg in (0x00, 0x02):
                continue
            return val
        except OSError:
            pass
    return None

bus = SMBus(I2C_BUS)
try: bus.read_byte_data(INA_ADDR, 0)
except: pass

print("=== Current register state ===")
for r in range(6):
    v = read_u16(bus, r)
    print(f"  Reg 0x{r:02X}: 0x{v:04X}" if v is not None else f"  Reg 0x{r:02X}: None")

# The default config is 0x399F. Let's try writing a DIFFERENT value.
# Try: BRNG=1, PGA=/4 (10), BADC=12-bit (0011), SADC=12-bit (0011), Mode=111
# = 0 0 1 10 0011 0011 111 = 0x319F
TEST_CONFIG = 0x319F
print(f"\n=== Test A: write_word_data config 0x{TEST_CONFIG:04X} (PGA=/4) ===")
swapped = ((TEST_CONFIG & 0xFF) << 8) | ((TEST_CONFIG >> 8) & 0xFF)
try:
    bus.write_word_data(INA_ADDR, 0x00, swapped)
    time.sleep(0.01)
    rb = read_u16(bus, 0x00)
    print(f"  Readback: 0x{rb:04X} (expected 0x{TEST_CONFIG:04X}) {'✓ WRITE WORKS' if rb == TEST_CONFIG else '✗ WRITE FAILED — GOT DEFAULT'}")
except OSError as e:
    print(f"  Write error: {e}")

# Restore default
time.sleep(0.01)
swapped = ((0x399F & 0xFF) << 8) | ((0x399F >> 8) & 0xFF)
try:
    bus.write_word_data(INA_ADDR, 0x00, swapped)
except: pass

# Try writing cal register with write_word_data
print(f"\n=== Test B: write_word_data cal reg 0x05 = 0x1000 ===")
time.sleep(0.01)
try: bus.read_byte_data(INA_ADDR, 0)
except: pass
swapped = ((0x1000 & 0xFF) << 8) | ((0x1000 >> 8) & 0xFF)
try:
    bus.write_word_data(INA_ADDR, 0x05, swapped)
    time.sleep(0.01)
    rb = read_u16(bus, 0x05)
    print(f"  Readback: 0x{rb:04X} (expected 0x1000) {'✓' if rb == 0x1000 else '✗'}")
except OSError as e:
    print(f"  Write error: {e}")

# Try using i2cset command via subprocess (Linux kernel i2c-tools)
print(f"\n=== Test C: i2cset (i2c-tools) cal reg 0x05 = 0x1000 ===")
import subprocess
# i2cset -y 1 0x40 0x05 0x10 0x00 i  (i for block/I2C mode)
# Or: i2cset -y 1 0x40 0x05 0x1000 w  (w for 16-bit word, little-endian!)
# For SMBus word (little-endian): 0x1000 → send low=0x00, high=0x10
# INA219 expects big-endian, so we need to swap: send 0x0010 in word mode
# Actually i2cset -y 1 0x40 0x05 0x0010 w → sends [0x05, 0x10, 0x00] on wire
# That's [reg, low_byte=0x10, high_byte=0x00] → INA219 MSB=0x10, LSB=0x00 = 0x1000
result = subprocess.run(
    ["i2cset", "-y", "1", "0x40", "0x05", "0x0010", "w"],
    capture_output=True, text=True
)
print(f"  i2cset stdout: {result.stdout.strip()}")
print(f"  i2cset stderr: {result.stderr.strip()}")
print(f"  i2cset rc: {result.returncode}")
time.sleep(0.01)
rb = read_u16(bus, 0x05)
print(f"  Readback: 0x{rb:04X} (expected 0x1000) {'✓' if rb == 0x1000 else '✗'}")

# Try i2cset for config too
print(f"\n=== Test D: i2cset config 0x00 = 0x319F (non-default) ===")
# 0x319F big-endian → SMBus word: swap → 0x9F31
result = subprocess.run(
    ["i2cset", "-y", "1", "0x40", "0x00", "0x9f31", "w"],
    capture_output=True, text=True
)
print(f"  i2cset rc: {result.returncode}, stderr: {result.stderr.strip()}")
time.sleep(0.01)
rb = read_u16(bus, 0x00)
print(f"  Readback: 0x{rb:04X} (expected 0x319F) {'✓ REAL WRITE' if rb == 0x319F else '✗'}")

# Restore
subprocess.run(["i2cset", "-y", "1", "0x40", "0x00", "0x9f39", "w"],
               capture_output=True, text=True)
time.sleep(0.01)
rb = read_u16(bus, 0x00)
print(f"  Restore: 0x{rb:04X} (expected 0x399F) {'✓' if rb == 0x399F else '✗'}")

# Also test with i2c block write mode
print(f"\n=== Test E: i2cset block mode (i) cal 0x05 = 0x1000 ===")
result = subprocess.run(
    ["i2cset", "-y", "1", "0x40", "0x05", "0x10", "0x00", "i"],
    capture_output=True, text=True
)
print(f"  i2cset rc: {result.returncode}, stderr: {result.stderr.strip()}")
time.sleep(0.01)
rb = read_u16(bus, 0x05)
print(f"  Readback: 0x{rb:04X} (expected 0x1000) {'✓' if rb == 0x1000 else '✗'}")

# Read all registers final state
print(f"\n=== Final register state ===")
for r in range(6):
    v = read_u16(bus, r)
    print(f"  Reg 0x{r:02X}: 0x{v:04X}" if v is not None else f"  Reg 0x{r:02X}: None")

bus.close()
print("\nDone.")
