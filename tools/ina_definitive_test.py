#!/usr/bin/env python3
"""Definitive test: which warm-up method works?"""
import smbus2
import time

ADDR = 0x40

# ============================================================
# Test A: read_byte_data warm-up (the one that worked!)
# ============================================================
print("=== Test A: read_byte_data warm-up ===")
bus = smbus2.SMBus(1)
for i in range(5):
    try:
        v = bus.read_byte_data(ADDR, 0)
        print(f"  [{i+1}] OK  val=0x{v:02X}")
    except Exception:
        print(f"  [{i+1}] EIO")

print("\n  After warm-up — word reads:")
for reg in range(6):
    try:
        v = bus.read_word_data(ADDR, reg)
        be = ((v & 0xFF) << 8) | ((v >> 8) & 0xFF)
        print(f"  reg {reg}: 0x{be:04X}")
    except Exception:
        print(f"  reg {reg}: FAIL")

print("\n  After warm-up — block reads:")
for reg in range(6):
    try:
        d = bus.read_i2c_block_data(ADDR, reg, 2)
        v = (d[0] << 8) | d[1]
        print(f"  reg {reg}: 0x{v:04X}")
    except Exception:
        print(f"  reg {reg}: FAIL")
bus.close()

# ============================================================
# Test B: read_byte warm-up (the one that corrupted bus!)
# ============================================================
print("\n=== Test B: read_byte warm-up (BAD?) ===")
bus = smbus2.SMBus(1)
for i in range(5):
    try:
        v = bus.read_byte(ADDR)
        print(f"  [{i+1}] OK  val=0x{v:02X}")
    except Exception:
        print(f"  [{i+1}] EIO")

print("\n  After warm-up — byte_data reads:")
for reg in range(6):
    try:
        v = bus.read_byte_data(ADDR, reg)
        print(f"  reg {reg}: 0x{v:02X}")
    except Exception:
        print(f"  reg {reg}: FAIL")
bus.close()

# ============================================================
# Test C: write_byte_data warm-up (write then read)
# ============================================================
print("\n=== Test C: write_byte_data warm-up ===")
bus = smbus2.SMBus(1)
try:
    # Just write the register pointer (writing reg 0x00 pointer)
    bus.write_byte(ADDR, 0x00)
    print("  write_byte(0x00): OK")
except Exception:
    print("  write_byte(0x00): EIO")

print("\n  After write warm-up — byte_data reads:")
for reg in range(6):
    try:
        v = bus.read_byte_data(ADDR, reg)
        print(f"  reg {reg}: 0x{v:02X}")
    except Exception:
        print(f"  reg {reg}: FAIL")
bus.close()

# ============================================================
# Test D: Full INA219 read with proper warm-up
# ============================================================
print("\n=== Test D: Full INA219 register dump ===")
bus = smbus2.SMBus(1)

# Warm up with a throwaway read_byte_data
try:
    bus.read_byte_data(ADDR, 0)
except:
    pass  # first fail expected

# Now read all 6 registers (16-bit each)
reg_names = ["Config", "Shunt V", "Bus V", "Power", "Current", "Calibration"]
for reg in range(6):
    try:
        d = bus.read_i2c_block_data(ADDR, reg, 2)
        val = (d[0] << 8) | d[1]
        
        # Decode
        if reg == 0:  # Config
            desc = f"range={'16V' if val & 0x2000 else '32V'}, gain={((val>>11)&3)}"
        elif reg == 1:  # Shunt voltage
            sv = val if val < 0x8000 else val - 0x10000
            desc = f"{sv * 0.01:.2f} mV → {sv * 0.01 / 100:.4f} A (0.1Ω)"
        elif reg == 2:  # Bus voltage
            bv = ((val >> 3) & 0x1FFF) * 4 / 1000
            cnvr = (val >> 1) & 1
            ovf = val & 1
            desc = f"{bv:.3f} V  cnvr={cnvr} ovf={ovf}"
        else:
            desc = ""
        
        print(f"  [{reg_names[reg]:12s}] 0x{val:04X}  {desc}")
    except Exception as e:
        print(f"  [{reg_names[reg]:12s}] FAIL: {e}")

bus.close()
print("\nDone.")
