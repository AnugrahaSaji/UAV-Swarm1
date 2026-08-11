#!/usr/bin/env python3
"""Minimal INA219 write test — isolate BCM2835 write failures."""
import time
from smbus2 import SMBus

I2C_BUS = 1
INA_ADDR = 0x40

def try_write(desc, bus, reg, value):
    swapped = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)
    try:
        bus.write_word_data(INA_ADDR, reg, swapped)
        # Read back to verify
        time.sleep(0.005)
        try:
            rb = bus.read_word_data(INA_ADDR, reg)
            rb_be = ((rb & 0xFF) << 8) | ((rb >> 8) & 0xFF)
        except OSError:
            # First read after write can fail
            rb = bus.read_word_data(INA_ADDR, reg)
            rb_be = ((rb & 0xFF) << 8) | ((rb >> 8) & 0xFF)
        print(f"  {desc}: WRITE OK, readback=0x{rb_be:04X} (expected 0x{value:04X}) {'✓' if rb_be == value else '✗'}")
        return True
    except OSError as e:
        print(f"  {desc}: WRITE FAILED — {e}")
        return False

print("=== Test 1: Fresh bus, immediate write to config (0x00) ===")
bus = SMBus(I2C_BUS)
try: bus.read_byte_data(INA_ADDR, 0)
except: pass
try_write("Config 0x399F", bus, 0x00, 0x399F)
bus.close()

print("\n=== Test 2: Fresh bus, write to calibration (0x05) ===")
bus = SMBus(I2C_BUS)
try: bus.read_byte_data(INA_ADDR, 0)
except: pass
try_write("Cal 0x1000", bus, 0x05, 0x1000)
bus.close()

print("\n=== Test 3: Same bus, two writes (config then cal) ===")
bus = SMBus(I2C_BUS)
try: bus.read_byte_data(INA_ADDR, 0)
except: pass
ok1 = try_write("Config 0x399F", bus, 0x00, 0x399F)
time.sleep(0.05)
# Warm-up between writes
try: bus.read_byte_data(INA_ADDR, 0)
except: pass
ok2 = try_write("Cal 0x1000", bus, 0x05, 0x1000)
bus.close()

print("\n=== Test 4: Same bus, two writes with bus reopen between ===")
bus = SMBus(I2C_BUS)
try: bus.read_byte_data(INA_ADDR, 0)
except: pass
ok1 = try_write("Config 0x399F", bus, 0x00, 0x399F)
bus.close()
time.sleep(0.05)
bus = SMBus(I2C_BUS)
try: bus.read_byte_data(INA_ADDR, 0)
except: pass
ok2 = try_write("Cal 0x1000", bus, 0x05, 0x1000)
bus.close()

print("\n=== Test 5: write_byte_data instead (two bytes separately) ===")
bus = SMBus(I2C_BUS)
try: bus.read_byte_data(INA_ADDR, 0)
except: pass
# Write calibration 0x1000 as two byte writes
# INA219 registers are 16-bit big-endian
# Method: write high byte, then low byte? No — INA219 expects a 16-bit
# write in one I2C transaction. Let's try write_block_data with 2 bytes.
try:
    # write_byte_data writes reg, then ONE byte. INA219 needs 2 bytes.
    # So write_byte_data won't work for 16-bit registers.
    # Let's try i2c_rdwr for raw I2C:
    from smbus2 import i2c_msg
    msg = i2c_msg.write(INA_ADDR, [0x05, 0x10, 0x00])  # reg, MSB, LSB
    bus.i2c_rdwr(msg)
    time.sleep(0.005)
    try:
        rb = bus.read_word_data(INA_ADDR, 0x05)
        rb_be = ((rb & 0xFF) << 8) | ((rb >> 8) & 0xFF)
    except OSError:
        rb = bus.read_word_data(INA_ADDR, 0x05)
        rb_be = ((rb & 0xFF) << 8) | ((rb >> 8) & 0xFF)
    print(f"  i2c_rdwr write: OK, readback=0x{rb_be:04X} (expected 0x1000) {'✓' if rb_be == 0x1000 else '✗'}")
except Exception as e:
    print(f"  i2c_rdwr write: FAILED — {e}")
bus.close()

print("\n=== Test 6: Full config via i2c_rdwr raw I2C ===")
bus = SMBus(I2C_BUS)
try: bus.read_byte_data(INA_ADDR, 0)
except: pass
from smbus2 import i2c_msg
# Write config 0x3FFF
try:
    msg = i2c_msg.write(INA_ADDR, [0x00, 0x3F, 0xFF])
    bus.i2c_rdwr(msg)
    time.sleep(0.005)
    try:
        rb = bus.read_word_data(INA_ADDR, 0x00)
        rb_be = ((rb & 0xFF) << 8) | ((rb >> 8) & 0xFF)
    except OSError:
        rb = bus.read_word_data(INA_ADDR, 0x00)
        rb_be = ((rb & 0xFF) << 8) | ((rb >> 8) & 0xFF)
    print(f"  Config 0x3FFF via i2c_rdwr: readback=0x{rb_be:04X} {'✓' if rb_be == 0x3FFF else '✗'}")
except Exception as e:
    print(f"  Config 0x3FFF via i2c_rdwr: FAILED — {e}")
# Write cal 0x1000
try:
    msg = i2c_msg.write(INA_ADDR, [0x05, 0x10, 0x00])
    bus.i2c_rdwr(msg)
    time.sleep(0.005)
    try:
        rb = bus.read_word_data(INA_ADDR, 0x05)
        rb_be = ((rb & 0xFF) << 8) | ((rb >> 8) & 0xFF)
    except OSError:
        rb = bus.read_word_data(INA_ADDR, 0x05)
        rb_be = ((rb & 0xFF) << 8) | ((rb >> 8) & 0xFF)
    print(f"  Cal 0x1000 via i2c_rdwr: readback=0x{rb_be:04X} {'✓' if rb_be == 0x1000 else '✗'}")
except Exception as e:
    print(f"  Cal 0x1000 via i2c_rdwr: FAILED — {e}")

# Restore config default
try:
    msg = i2c_msg.write(INA_ADDR, [0x00, 0x39, 0x9F])
    bus.i2c_rdwr(msg)
    print("  Restored default config 0x399F")
except Exception as e:
    print(f"  Restore failed: {e}")
bus.close()

print("\nDone.")
