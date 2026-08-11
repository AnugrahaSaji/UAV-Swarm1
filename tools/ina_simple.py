#!/usr/bin/env python3
"""Simple INA219 init → read → calibrate → read."""
import time
from smbus2 import SMBus, i2c_msg

BUS = 1
ADDR = 0x40
SHUNT = 0.1  # ohm

def r16(bus, reg):
    """Read 16-bit big-endian register."""
    for _ in range(3):
        try:
            w = bus.read_word_data(ADDR, reg)
            v = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
            if v == 0 and reg in (0x00, 0x02) and _ < 2:
                continue
            return v
        except OSError:
            pass
    return None

def w16(bus, reg, val):
    """Write 16-bit big-endian register. Try i2c_rdwr first, fallback to write_word_data."""
    # Method 1: raw I2C write (3 bytes: reg, MSB, LSB)
    msb = (val >> 8) & 0xFF
    lsb = val & 0xFF
    try:
        msg = i2c_msg.write(ADDR, [reg, msb, lsb])
        bus.i2c_rdwr(msg)
        return "i2c_rdwr"
    except OSError:
        pass
    # Method 2: SMBus write_word_data (little-endian swap)
    try:
        swapped = (lsb << 8) | msb
        bus.write_word_data(ADDR, reg, swapped)
        return "write_word"
    except OSError:
        pass
    return None

bus = SMBus(BUS)

# --- Warm-up ---
try: bus.read_byte_data(ADDR, 0)
except: pass

print("==== STEP 1: READ (before calibration) ====")
cfg = r16(bus, 0x00)
cal = r16(bus, 0x05)
print(f"  Config:      0x{cfg:04X}")
print(f"  Calibration: 0x{cal:04X}")

for i in range(5):
    vr = r16(bus, 0x02)
    sr = r16(bus, 0x01)
    cr = r16(bus, 0x04)
    pr = r16(bus, 0x03)
    vbus = ((vr >> 3) & 0x1FFF) * 0.004
    ssh = sr if sr < 0x8000 else sr - 65536
    shunt_mv = ssh * 0.01
    curr_manual = (ssh * 10e-6) / SHUNT
    vsupply = vbus + abs(ssh * 10e-6)
    print(f"  [{i}] Vbus={vbus:.3f}V  Vshunt={shunt_mv:+.2f}mV  "
          f"I(manual)={curr_manual*1000:.1f}mA  Vsupply={vsupply:.3f}V  "
          f"Cur_reg=0x{cr:04X}  Pwr_reg=0x{pr:04X}")

print("\n==== STEP 2: CALIBRATE ====")
# Current_LSB = 100µA, Cal = 0.04096 / (0.0001 * 0.1) = 4096
CAL = 4096
CLSB = 0.0001
PLSB = 20 * CLSB
print(f"  Writing Cal=0x{CAL:04X} ({CAL}) ...")
bus.close()
time.sleep(0.05)
bus = SMBus(BUS)
try: bus.read_byte_data(ADDR, 0)
except: pass
method = w16(bus, 0x05, CAL)
print(f"  Write method: {method}")
time.sleep(0.01)
rb = r16(bus, 0x05)
print(f"  Readback:     0x{rb:04X}  {'OK' if rb == CAL else 'MISMATCH'}")

print("\n==== STEP 3: READ (after calibration) ====")
time.sleep(0.1)
for i in range(5):
    time.sleep(0.05)
    vr = r16(bus, 0x02)
    sr = r16(bus, 0x01)
    cr = r16(bus, 0x04)
    pr = r16(bus, 0x03)
    vbus = ((vr >> 3) & 0x1FFF) * 0.004
    ssh = sr if sr < 0x8000 else sr - 65536
    shunt_mv = ssh * 0.01
    curr_manual = (ssh * 10e-6) / SHUNT
    # If cal took effect, current/power regs should be non-zero
    c_signed = cr if cr < 0x8000 else cr - 65536
    curr_cal = c_signed * CLSB
    pwr_cal = pr * PLSB
    vsupply = vbus + abs(ssh * 10e-6)
    print(f"  [{i}] Vbus={vbus:.3f}V  Vshunt={shunt_mv:+.2f}mV  Vsupply={vsupply:.3f}V")
    print(f"       I(manual)={curr_manual*1000:.1f}mA  I(cal)={curr_cal*1000:.1f}mA  P(cal)={pwr_cal*1000:.1f}mW")

bus.close()
