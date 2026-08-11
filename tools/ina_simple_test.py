#!/usr/bin/env python3
"""Simple INA219 reliability test — reads config register 30 times."""
import smbus2
import time

bus = smbus2.SMBus(1)
ok = 0
fail = 0

print("=== INA219 I2C Reliability Test ===")
print("Reading config register (0x00) 30 times, 300ms apart")
print()

for i in range(30):
    try:
        data = bus.read_i2c_block_data(0x40, 0x00, 2)
        val = (data[0] << 8) | data[1]
        ok += 1
        print(f"  [{i+1:2d}] OK  config=0x{val:04X}")
    except Exception as e:
        fail += 1
        print(f"  [{i+1:2d}] FAIL {e}")
    time.sleep(0.3)

print(f"\nResult: {ok}/30 OK, {fail}/30 FAIL ({ok*100//30}%)")

# Now try different read methods on the same register
print("\n=== Method comparison (5 attempts each) ===")
methods = [
    ("read_i2c_block_data", lambda: bus.read_i2c_block_data(0x40, 0x00, 2)),
    ("read_word_data",      lambda: bus.read_word_data(0x40, 0x00)),
    ("read_byte_data",      lambda: bus.read_byte_data(0x40, 0x00)),
]

for name, fn in methods:
    m_ok = 0
    for j in range(5):
        try:
            val = fn()
            m_ok += 1
            print(f"  {name} #{j+1}: OK  raw={val}")
        except Exception as e:
            print(f"  {name} #{j+1}: FAIL {e}")
        time.sleep(0.3)
    print(f"  -> {name}: {m_ok}/5\n")

# Try i2c_rdwr (different ioctl)
from smbus2 import i2c_msg
print("=== i2c_rdwr method (5 attempts) ===")
rdwr_ok = 0
for j in range(5):
    try:
        write = i2c_msg.write(0x40, [0x00])
        read = i2c_msg.read(0x40, 2)
        bus.i2c_rdwr(write, read)
        data = list(read)
        val = (data[0] << 8) | data[1]
        rdwr_ok += 1
        print(f"  i2c_rdwr #{j+1}: OK  config=0x{val:04X}")
    except Exception as e:
        print(f"  i2c_rdwr #{j+1}: FAIL {e}")
    time.sleep(0.3)
print(f"  -> i2c_rdwr: {rdwr_ok}/5")

bus.close()
