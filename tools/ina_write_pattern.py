#!/usr/bin/env python3
"""BCM2835 write pattern: 1st write = silent drop, 2nd = EIO, 3rd = ???"""
import time
from smbus2 import SMBus

BUS = 1
ADDR = 0x40

def r16(bus, reg):
    for _ in range(3):
        try:
            w = bus.read_word_data(ADDR, reg)
            v = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
            if v == 0 and _ < 2 and reg in (0x00, 0x02, 0x05):
                continue
            return v
        except OSError:
            pass
    return None

def w16_attempt(bus, reg, val):
    msb = (val >> 8) & 0xFF
    lsb = val & 0xFF
    swapped = (lsb << 8) | msb
    try:
        bus.write_word_data(ADDR, reg, swapped)
        return "ok"
    except OSError as e:
        return f"EIO"

# Strategy: open bus, warmup read, then try N writes in sequence
bus = SMBus(BUS)
try: bus.read_byte_data(ADDR, 0)
except: pass

print("=== Sequential writes to cal (0x05 = 0x1000), checking each ===")
for i in range(6):
    result = w16_attempt(bus, 0x05, 0x1000)
    time.sleep(0.005)
    rb = r16(bus, 0x05)
    print(f"  Write #{i+1}: {result:3s}  readback=0x{rb:04X}  {'✓' if rb == 0x1000 else '✗'}")

bus.close()

# Test: interleave reads between writes
print("\n=== Interleaved: read config, write cal, repeat ===")
bus = SMBus(BUS)
try: bus.read_byte_data(ADDR, 0)
except: pass
for i in range(6):
    cfg = r16(bus, 0x00)
    result = w16_attempt(bus, 0x05, 0x1000)
    time.sleep(0.005)
    rb = r16(bus, 0x05)
    print(f"  [{i}] cfg=0x{cfg:04X}  write={result:3s}  cal=0x{rb:04X}  {'✓' if rb == 0x1000 else '✗'}")

bus.close()

# Test: write config (non-default) with retries
print("\n=== Write non-default config 0x299F with retries ===")
bus = SMBus(BUS)
try: bus.read_byte_data(ADDR, 0)
except: pass
for i in range(6):
    result = w16_attempt(bus, 0x00, 0x299F)
    time.sleep(0.005)
    rb = r16(bus, 0x00)
    print(f"  Write #{i+1}: {result:3s}  readback=0x{rb:04X}  {'✓ CHANGED' if rb == 0x299F else '✗ default' if rb == 0x399F else f'? {rb:#06x}'}")

# Restore if changed
w16_attempt(bus, 0x00, 0x399F)
bus.close()

# Test: close/reopen between every write attempt
print("\n=== Fresh bus per write (close/reopen) ===")
for i in range(6):
    bus = SMBus(BUS)
    try: bus.read_byte_data(ADDR, 0)
    except: pass
    # Do a read to "warm up"
    _ = r16(bus, 0x00)
    result = w16_attempt(bus, 0x05, 0x1000)
    time.sleep(0.005)
    rb = r16(bus, 0x05)
    print(f"  [{i}] write={result:3s}  cal=0x{rb:04X}  {'✓' if rb == 0x1000 else '✗'}")
    bus.close()
    time.sleep(0.05)

# Test: use write_byte_data for warm-up, then write_word_data
print("\n=== warm-up with write_byte_data then write_word_data ===")
bus = SMBus(BUS)
try: bus.read_byte_data(ADDR, 0)
except: pass
# Dummy byte write
try: bus.write_byte_data(ADDR, 0x00, 0x39)
except: pass
time.sleep(0.005)
for i in range(4):
    result = w16_attempt(bus, 0x05, 0x1000)
    time.sleep(0.005)
    rb = r16(bus, 0x05)
    print(f"  [{i}] write={result:3s}  cal=0x{rb:04X}  {'✓' if rb == 0x1000 else '✗'}")
bus.close()

print("\nDone.")
