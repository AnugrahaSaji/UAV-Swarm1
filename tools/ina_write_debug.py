#!/usr/bin/env python3
"""Test if BCM2835 first write silently fails (data not sent on bus).
Theory: like first-read-returns-EIO, first-write-may-succeed-but-not-transmit."""
import time
from smbus2 import SMBus

BUS = 1
ADDR = 0x40

def r16(bus, reg):
    for _ in range(3):
        try:
            w = bus.read_word_data(ADDR, reg)
            v = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
            if v == 0 and reg in (0x00, 0x02, 0x05) and _ < 2:
                continue
            return v
        except OSError:
            pass
    return None

def w16_raw(bus, reg, val):
    """Single write attempt, no retry."""
    msb = (val >> 8) & 0xFF
    lsb = val & 0xFF
    swapped = (lsb << 8) | msb
    bus.write_word_data(ADDR, reg, swapped)

bus = SMBus(BUS)

# Warm-up read
try: bus.read_byte_data(ADDR, 0)
except: pass

print("=== Baseline: Cal register ===")
print(f"  Cal = 0x{r16(bus, 0x05):04X}")

# Test 1: Write cal once (might be silently dropped)
print("\n=== Test 1: Single write to cal ===")
w16_raw(bus, 0x05, 0x1000)
time.sleep(0.01)
rb = r16(bus, 0x05)
print(f"  After 1 write: Cal = 0x{rb:04X}  {'OK' if rb == 0x1000 else 'FAILED (silent drop)'}")

# Test 2: Write cal twice (second should stick if first was dropped)
print("\n=== Test 2: Write cal twice ===")
bus.close(); time.sleep(0.02)
bus = SMBus(BUS)
try: bus.read_byte_data(ADDR, 0)
except: pass
w16_raw(bus, 0x05, 0x1000)  # first write — might be dropped
time.sleep(0.005)
w16_raw(bus, 0x05, 0x1000)  # second write — should stick
time.sleep(0.01)
rb = r16(bus, 0x05)
print(f"  After 2 writes: Cal = 0x{rb:04X}  {'OK' if rb == 0x1000 else 'FAILED'}")

# Test 3: Dummy write (safe value) then real write
print("\n=== Test 3: Dummy write (config default) + real write (cal) ===")
bus.close(); time.sleep(0.02)
bus = SMBus(BUS)
try: bus.read_byte_data(ADDR, 0)
except: pass
w16_raw(bus, 0x00, 0x399F)  # dummy: write default config (harmless)
time.sleep(0.005)
w16_raw(bus, 0x05, 0x1000)  # real write: cal
time.sleep(0.01)
rb = r16(bus, 0x05)
print(f"  After dummy+real: Cal = 0x{rb:04X}  {'OK' if rb == 0x1000 else 'FAILED'}")

# Test 4: Multiple warm-up writes then real write
print("\n=== Test 4: 3 dummy writes + real write ===")
bus.close(); time.sleep(0.02)
bus = SMBus(BUS)
try: bus.read_byte_data(ADDR, 0)
except: pass
for i in range(3):
    try: w16_raw(bus, 0x00, 0x399F)
    except: pass
    time.sleep(0.005)
w16_raw(bus, 0x05, 0x1000)
time.sleep(0.01)
rb = r16(bus, 0x05)
print(f"  After 3 dummies+real: Cal = 0x{rb:04X}  {'OK' if rb == 0x1000 else 'FAILED'}")

# Test 5: Read between writes
print("\n=== Test 5: Read-write-read-write pattern ===")
bus.close(); time.sleep(0.02)
bus = SMBus(BUS)
try: bus.read_byte_data(ADDR, 0)
except: pass
_ = r16(bus, 0x00)  # read config
w16_raw(bus, 0x05, 0x1000)  # write cal
time.sleep(0.005)
_ = r16(bus, 0x05)  # read cal
w16_raw(bus, 0x05, 0x1000)  # write cal again
time.sleep(0.01)
rb = r16(bus, 0x05)
print(f"  After R-W-R-W: Cal = 0x{rb:04X}  {'OK' if rb == 0x1000 else 'FAILED'}")

# Test 6: write_byte_data (different SMBus command type)
print("\n=== Test 6: write_byte_data (MSB then LSB separately) ===")
bus.close(); time.sleep(0.02)
bus = SMBus(BUS)
try: bus.read_byte_data(ADDR, 0)
except: pass
# INA219 needs 16-bit write. write_byte_data only writes 1 byte.
# This won't work for INA219 but let's see if the write path is functional.
try:
    bus.write_byte_data(ADDR, 0x05, 0x10)  # writes reg 0x05, data=0x10
    print(f"  write_byte_data: OK (no exception)")
except OSError as e:
    print(f"  write_byte_data: FAILED — {e}")

# Test 7: Write a clearly different config, not default
print("\n=== Test 7: Write non-default config 0x299F (PGA=/2) ===")
bus.close(); time.sleep(0.02)
bus = SMBus(BUS)
try: bus.read_byte_data(ADDR, 0)
except: pass
# Warm up with dummy writes
try: w16_raw(bus, 0x00, 0x399F)
except: pass
time.sleep(0.005)
try: w16_raw(bus, 0x00, 0x399F)
except: pass
time.sleep(0.005)
# Now write non-default
w16_raw(bus, 0x00, 0x299F)
time.sleep(0.01)
rb = r16(bus, 0x00)
print(f"  Config = 0x{rb:04X}  {'WRITE WORKS!' if rb == 0x299F else 'STILL DEFAULT' if rb == 0x399F else f'UNEXPECTED'}")

# Restore
try: w16_raw(bus, 0x00, 0x399F)
except: pass

bus.close()
print("\nDone.")
