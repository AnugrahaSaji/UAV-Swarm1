#!/usr/bin/env python3
"""
INA219 direct ioctl test — replicate EXACTLY what i2cdump does.
Uses ctypes to call I2C_SMBUS ioctl directly, bypassing smbus2.
"""
import os
import sys
import fcntl
import ctypes
import struct
import time

# Linux I2C ioctl constants
I2C_SLAVE       = 0x0703
I2C_SLAVE_FORCE = 0x0706
I2C_SMBUS       = 0x0720
I2C_RDWR        = 0x0707

# SMBus transaction types
I2C_SMBUS_READ  = 1
I2C_SMBUS_WRITE = 0

# SMBus size types
I2C_SMBUS_BYTE      = 1
I2C_SMBUS_BYTE_DATA = 2
I2C_SMBUS_WORD_DATA = 3
I2C_SMBUS_BLOCK_DATA = 5
I2C_SMBUS_I2C_BLOCK_DATA = 8

# i2c_smbus_data union (34 bytes max)
class i2c_smbus_data(ctypes.Union):
    _fields_ = [
        ("byte", ctypes.c_uint8),
        ("word", ctypes.c_uint16),
        ("block", ctypes.c_uint8 * 34),
    ]

# i2c_smbus_ioctl_data structure
class i2c_smbus_ioctl_data(ctypes.Structure):
    _fields_ = [
        ("read_write", ctypes.c_uint8),
        ("command", ctypes.c_uint8),
        ("size", ctypes.c_uint32),
        ("data", ctypes.POINTER(i2c_smbus_data)),
    ]

# i2c_msg for I2C_RDWR
class i2c_msg(ctypes.Structure):
    _fields_ = [
        ("addr", ctypes.c_uint16),
        ("flags", ctypes.c_uint16),
        ("len", ctypes.c_uint16),
        ("buf", ctypes.POINTER(ctypes.c_uint8)),
    ]

class i2c_rdwr_ioctl_data(ctypes.Structure):
    _fields_ = [
        ("msgs", ctypes.POINTER(i2c_msg)),
        ("nmsgs", ctypes.c_uint32),
    ]


def smbus_read_byte_data(fd, register):
    """Replicate i2cdump 'b' mode read — I2C_SMBUS with BYTE_DATA."""
    data = i2c_smbus_data()
    args = i2c_smbus_ioctl_data()
    args.read_write = I2C_SMBUS_READ
    args.command = register
    args.size = I2C_SMBUS_BYTE_DATA
    args.data = ctypes.pointer(data)
    
    fcntl.ioctl(fd, I2C_SMBUS, args)
    return data.byte


def smbus_read_word_data(fd, register):
    """I2C_SMBUS with WORD_DATA."""
    data = i2c_smbus_data()
    args = i2c_smbus_ioctl_data()
    args.read_write = I2C_SMBUS_READ
    args.command = register
    args.size = I2C_SMBUS_WORD_DATA
    args.data = ctypes.pointer(data)
    
    fcntl.ioctl(fd, I2C_SMBUS, args)
    return data.word


def smbus_read_i2c_block(fd, register, length):
    """I2C_SMBUS with I2C_BLOCK_DATA."""
    data = i2c_smbus_data()
    data.block[0] = length
    args = i2c_smbus_ioctl_data()
    args.read_write = I2C_SMBUS_READ
    args.command = register
    args.size = I2C_SMBUS_I2C_BLOCK_DATA
    args.data = ctypes.pointer(data)
    
    fcntl.ioctl(fd, I2C_SMBUS, args)
    return [data.block[i+1] for i in range(length)]


def i2c_rdwr_read(fd, addr, register, length):
    """I2C_RDWR: write register address, then read data."""
    # Write message (register address)
    wbuf = (ctypes.c_uint8 * 1)(register)
    wmsg = i2c_msg()
    wmsg.addr = addr
    wmsg.flags = 0  # write
    wmsg.len = 1
    wmsg.buf = wbuf
    
    # Read message
    rbuf = (ctypes.c_uint8 * length)()
    rmsg = i2c_msg()
    rmsg.addr = addr
    rmsg.flags = 1  # I2C_M_RD
    rmsg.len = length
    rmsg.buf = rbuf
    
    # Combined
    msgs = (i2c_msg * 2)(wmsg, rmsg)
    data = i2c_rdwr_ioctl_data()
    data.msgs = msgs
    data.nmsgs = 2
    
    fcntl.ioctl(fd, I2C_RDWR, data)
    return [rbuf[i] for i in range(length)]


INA_ADDR = 0x40

print("INA219 Direct ioctl Test")
print(f"PID: {os.getpid()}")
print()

# Open I2C bus
fd = os.open("/dev/i2c-1", os.O_RDWR)

# ============================================================
# TEST A: I2C_SLAVE (normal)
# ============================================================
print("=== TEST A: I2C_SLAVE + BYTE_DATA (like i2cdump b) ===")
fcntl.ioctl(fd, I2C_SLAVE, INA_ADDR)

for reg in range(8):
    try:
        val = smbus_read_byte_data(fd, reg)
        print(f"  reg 0x{reg:02X}: 0x{val:02X}")
    except Exception as e:
        print(f"  reg 0x{reg:02X}: FAIL {e}")
    time.sleep(0.01)

# ============================================================
# TEST B: I2C_SLAVE_FORCE
# ============================================================
print("\n=== TEST B: I2C_SLAVE_FORCE + BYTE_DATA ===")
fcntl.ioctl(fd, I2C_SLAVE_FORCE, INA_ADDR)

for reg in range(8):
    try:
        val = smbus_read_byte_data(fd, reg)
        print(f"  reg 0x{reg:02X}: 0x{val:02X}")
    except Exception as e:
        print(f"  reg 0x{reg:02X}: FAIL {e}")
    time.sleep(0.01)

# ============================================================
# TEST C: WORD_DATA
# ============================================================
print("\n=== TEST C: I2C_SLAVE_FORCE + WORD_DATA ===")
for reg in range(6):
    try:
        val = smbus_read_word_data(fd, reg)
        # SMBus returns LE, INA219 is BE
        be_val = ((val & 0xFF) << 8) | ((val >> 8) & 0xFF)
        print(f"  reg 0x{reg:02X}: raw=0x{val:04X} be=0x{be_val:04X}")
    except Exception as e:
        print(f"  reg 0x{reg:02X}: FAIL {e}")
    time.sleep(0.01)

# ============================================================
# TEST D: I2C_BLOCK_DATA
# ============================================================
print("\n=== TEST D: I2C_SLAVE_FORCE + I2C_BLOCK_DATA ===")
for reg in range(6):
    try:
        data = smbus_read_i2c_block(fd, reg, 2)
        val = (data[0] << 8) | data[1]
        print(f"  reg 0x{reg:02X}: [0x{data[0]:02X}, 0x{data[1]:02X}] = 0x{val:04X}")
    except Exception as e:
        print(f"  reg 0x{reg:02X}: FAIL {e}")
    time.sleep(0.01)

# ============================================================
# TEST E: I2C_RDWR (combined message)
# ============================================================
print("\n=== TEST E: I2C_RDWR (combined write+read message) ===")
for reg in range(6):
    try:
        data = i2c_rdwr_read(fd, INA_ADDR, reg, 2)
        val = (data[0] << 8) | data[1]
        print(f"  reg 0x{reg:02X}: [0x{data[0]:02X}, 0x{data[1]:02X}] = 0x{val:04X}")
    except Exception as e:
        print(f"  reg 0x{reg:02X}: FAIL {e}")
    time.sleep(0.01)

os.close(fd)

# ============================================================
# TEST F: smbus2 with force=True
# ============================================================
print("\n=== TEST F: smbus2 with force=True ===")
try:
    import smbus2
    bus = smbus2.SMBus(1, force=True)
    for reg in range(6):
        try:
            data = bus.read_i2c_block_data(INA_ADDR, reg, 2)
            val = (data[0] << 8) | data[1]
            print(f"  reg 0x{reg:02X}: 0x{val:04X}")
        except Exception as e:
            print(f"  reg 0x{reg:02X}: FAIL {e}")
        time.sleep(0.01)
    bus.close()
except Exception as e:
    print(f"  smbus2 force: {e}")

print("\nDone.")
