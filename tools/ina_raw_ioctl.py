#!/usr/bin/env python3
"""Direct ioctl I2C write — bypass smbus2 entirely."""
import os, struct, fcntl, time, array

I2C_DEV = "/dev/i2c-1"
INA_ADDR = 0x40

I2C_SLAVE = 0x0703
I2C_RDWR  = 0x0707

class i2c_msg(struct.Struct):
    """struct i2c_msg { __u16 addr; __u16 flags; __u16 len; __u8 *buf; }"""
    pass

def raw_write(fd, reg, msb, lsb):
    """Direct I2C write: [reg, msb, lsb] using standard write() syscall."""
    data = bytes([reg, msb, lsb])
    n = os.write(fd, data)
    return n

def raw_read(fd, reg, length=2):
    """Direct I2C read: write reg addr, then read N bytes."""
    os.write(fd, bytes([reg]))
    data = os.read(fd, length)
    return data

fd = os.open(I2C_DEV, os.O_RDWR)
# Set slave address
fcntl.ioctl(fd, I2C_SLAVE, INA_ADDR)

# Warm-up
try: os.read(fd, 1)
except: pass

print("=== Raw I2C via os.write/os.read ===")

# Read current config
try:
    data = raw_read(fd, 0x00, 2)
    cfg = (data[0] << 8) | data[1]
    print(f"  Config: 0x{cfg:04X}")
except Exception as e:
    print(f"  Config read: {e}")
    # Retry
    try:
        data = raw_read(fd, 0x00, 2)
        cfg = (data[0] << 8) | data[1]
        print(f"  Config (retry): 0x{cfg:04X}")
    except Exception as e2:
        print(f"  Config read retry: {e2}")

# Read bus voltage
try:
    data = raw_read(fd, 0x02, 2)
    raw = (data[0] << 8) | data[1]
    vbus = ((raw >> 3) & 0x1FFF) * 0.004
    print(f"  Bus voltage: {vbus:.3f} V (raw 0x{raw:04X})")
except Exception as e:
    print(f"  Bus voltage read: {e}")

# Read shunt
try:
    data = raw_read(fd, 0x01, 2)
    raw = (data[0] << 8) | data[1]
    if raw & 0x8000: raw -= 65536
    print(f"  Shunt: {raw * 0.01:+.2f} mV")
except Exception as e:
    print(f"  Shunt read: {e}")

# Read cal
try:
    data = raw_read(fd, 0x05, 2)
    cal = (data[0] << 8) | data[1]
    print(f"  Cal: 0x{cal:04X}")
except Exception as e:
    print(f"  Cal read: {e}")

# Write cal = 0x1000 via raw write
print("\n--- Writing cal=0x1000 via raw os.write ---")
try:
    n = raw_write(fd, 0x05, 0x10, 0x00)
    print(f"  Written {n} bytes")
    time.sleep(0.01)
    data = raw_read(fd, 0x05, 2)
    cal = (data[0] << 8) | data[1]
    print(f"  Cal readback: 0x{cal:04X}  {'✓' if cal == 0x1000 else '✗'}")
except Exception as e:
    print(f"  Write/read error: {e}")

# Write non-default config 0x299F via raw write  
print("\n--- Writing config=0x299F via raw os.write ---")
try:
    n = raw_write(fd, 0x00, 0x29, 0x9F)
    print(f"  Written {n} bytes")
    time.sleep(0.01)
    data = raw_read(fd, 0x00, 2)
    cfg = (data[0] << 8) | data[1]
    print(f"  Config readback: 0x{cfg:04X}  {'✓' if cfg == 0x299F else '✗'}")
except Exception as e:
    print(f"  Write/read error: {e}")

# Try reset: write config bit 15 = 1
print("\n--- Soft reset (config = 0x8000) ---")
try:
    raw_write(fd, 0x00, 0x80, 0x00)
    time.sleep(0.1)
    data = raw_read(fd, 0x00, 2)
    cfg = (data[0] << 8) | data[1]
    print(f"  Config after reset: 0x{cfg:04X}  (default=0x399F)")
except Exception as e:
    print(f"  Reset error: {e}")

# All registers after
print("\n--- Final register state ---")
for reg in range(6):
    try:
        data = raw_read(fd, reg, 2)
        val = (data[0] << 8) | data[1]
        print(f"  Reg 0x{reg:02X}: 0x{val:04X}")
    except Exception as e:
        print(f"  Reg 0x{reg:02X}: {e}")

os.close(fd)
print("\nDone.")
