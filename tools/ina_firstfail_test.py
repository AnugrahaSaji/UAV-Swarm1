#!/usr/bin/env python3
"""
INA219 first-fail workaround test.
Strace shows: first I2C_SMBUS ioctl always returns EIO,
but i2cdump succeeds on subsequent calls.
Test: ignore first error and continue reading.
"""
import smbus2
import time
import sys

ADDR = 0x40

print("=== INA219 first-fail workaround test ===")
print()

bus = smbus2.SMBus(1)

# Phase 1: Many read_byte_data attempts (same as i2cdump b mode)
print("Phase 1: read_byte_data — 10 sequential reads from reg 0x00")
for i in range(10):
    try:
        val = bus.read_byte_data(ADDR, 0x00)
        print(f"  [{i+1:2d}] OK  val=0x{val:02X}")
    except OSError as e:
        print(f"  [{i+1:2d}] EIO  (errno={e.errno})")

# Phase 2: read_byte (simpler - no register select)
print("\nPhase 2: read_byte — 10 sequential reads (no register)")
for i in range(10):
    try:
        val = bus.read_byte(ADDR)
        print(f"  [{i+1:2d}] OK  val=0x{val:02X}")
    except OSError as e:
        print(f"  [{i+1:2d}] EIO  (errno={e.errno})")

# Phase 3: Alternate between different registers (like i2cdump does)
print("\nPhase 3: read_byte_data — regs 0,1,2,3,4,5 sequentially")
for reg in range(6):
    try:
        val = bus.read_byte_data(ADDR, reg)
        print(f"  reg 0x{reg:02X}: OK  val=0x{val:02X}")
    except OSError as e:
        print(f"  reg 0x{reg:02X}: EIO")

# Phase 4: Close and reopen, then try
print("\nPhase 4: close/reopen bus then read_byte_data")
bus.close()
bus = smbus2.SMBus(1)
results = []
for i in range(10):
    try:
        val = bus.read_byte_data(ADDR, i % 6)
        results.append(('OK', val))
        print(f"  [{i+1:2d}] OK  reg=0x{i%6:02X} val=0x{val:02X}")
    except OSError as e:
        results.append(('FAIL', e.errno))
        print(f"  [{i+1:2d}] EIO  reg=0x{i%6:02X}")

# Phase 5: Try 100 rapid reads with no delay
print("\nPhase 5: 100 rapid read_byte_data(0x00) — no delay")
ok = 0
fail = 0
for i in range(100):
    try:
        bus.read_byte_data(ADDR, 0x00)
        ok += 1
    except:
        fail += 1
print(f"  {ok}/100 OK, {fail}/100 FAIL")

# Phase 6: Use force=True 
print("\nPhase 6: force=True, 10 reads")
bus.close()
bus = smbus2.SMBus(1, force=True)
for i in range(10):
    try:
        val = bus.read_byte_data(ADDR, 0x00)
        print(f"  [{i+1:2d}] OK  val=0x{val:02X}")
    except OSError as e:
        print(f"  [{i+1:2d}] EIO")

# Phase 7: Different address objects
print("\nPhase 7: read with address 0x40 then try parsing i2cdump output")
bus.close()

import subprocess
try:
    out = subprocess.check_output(
        ["sudo", "i2cdump", "-y", "1", "0x40", "w"],
        text=True, timeout=10
    )
    print("  i2cdump w output:")
    for line in out.strip().split("\n"):
        print(f"    {line}")
    
    # Parse register values from word dump
    lines = out.strip().split("\n")
    if len(lines) > 1:
        # First data line has the first 8 word values
        parts = lines[1].split()
        if len(parts) > 1:
            print("\n  Parsed register values:")
            for idx, part in enumerate(parts[1:], 0):
                if part == "XXXX":
                    print(f"    reg {idx}: XXXX (first-fail)")
                else:
                    try:
                        raw = int(part, 16)
                        # SMBus word is LE on wire, need to swap for INA219 (BE)
                        be = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)
                        print(f"    reg {idx}: raw=0x{raw:04X} be=0x{be:04X}")
                    except ValueError:
                        print(f"    reg {idx}: {part}")
except subprocess.CalledProcessError as e:
    print(f"  i2cdump failed: {e}")
except FileNotFoundError:
    print("  i2cdump not found")

print("\nDone.")
