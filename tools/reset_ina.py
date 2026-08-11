#!/usr/bin/env python3
"""Reset INA219 and test read."""
import time
import os

# Method 1: raw file descriptor I/O (avoids smbus library issues)
print("=== INA219 Reset via raw fd ===")
try:
    import fcntl
    fd = os.open("/dev/i2c-1", os.O_RDWR)
    # Set slave address
    I2C_SLAVE = 0x0703
    fcntl.ioctl(fd, I2C_SLAVE, 0x40)
    # Write reset: reg 0x00, value 0x8000
    os.write(fd, bytes([0x00, 0x80, 0x00]))
    print("  Reset command sent")
    time.sleep(0.5)
    # Read config register
    os.write(fd, bytes([0x00]))
    data = os.read(fd, 2)
    print(f"  Config after reset: 0x{data[0]:02X}{data[1]:02X}")
    # Read bus voltage (reg 0x02)
    os.write(fd, bytes([0x02]))
    data = os.read(fd, 2)
    raw = (data[0] << 8) | data[1]
    voltage = ((raw >> 3) & 0x1FFF) * 0.004
    print(f"  Bus voltage: {voltage:.3f} V")
    # Read shunt voltage (reg 0x01)
    os.write(fd, bytes([0x01]))
    data = os.read(fd, 2)
    raw_s = (data[0] << 8) | data[1]
    if raw_s & 0x8000:
        raw_s -= 65536
    shunt_uv = raw_s * 10  # 10uV per LSB
    current_a = (shunt_uv / 1e6) / 0.1  # shunt = 0.1 ohm
    print(f"  Shunt voltage: {shunt_uv} uV")
    print(f"  Current: {current_a*1000:.1f} mA")
    print(f"  Power: {voltage * abs(current_a):.3f} W")
    os.close(fd)
    print("  RAW FD: OK")
except Exception as e:
    print(f"  RAW FD: FAIL - {e}")
    import traceback
    traceback.print_exc()

# Method 2: try smbus (old API, not smbus2)
print()
print("=== Test via smbus (old) ===")
try:
    import smbus
    bus = smbus.SMBus(1)
    val = bus.read_byte_data(0x40, 0x02)
    print(f"  smbus read_byte_data OK: {val}")
    bus.close()
    print("  SMBUS: OK")
except Exception as e:
    print(f"  SMBUS: FAIL - {e}")

# Method 3: smbus2
print()
print("=== Test via smbus2 ===")
try:
    import smbus2
    bus2 = smbus2.SMBus(1)
    data = bus2.read_i2c_block_data(0x40, 0x02, 2)
    print(f"  smbus2 read_i2c_block_data OK: {data}")
    bus2.close()
    print("  SMBUS2: OK")
except Exception as e:
    print(f"  SMBUS2: FAIL - {e}")

# Method 4: pi-ina219 library
print()
print("=== Test via pi-ina219 ===")
try:
    from ina219 import INA219
    ina = INA219(shunt_ohms=0.1, max_expected_amps=3.0, address=0x40, busnum=1)
    ina.configure()
    print(f"  voltage: {ina.voltage():.3f} V")
    print(f"  current: {ina.current():.3f} mA")
    print(f"  power:   {ina.power():.3f} mW")
    print("  PI-INA219: OK")
except Exception as e:
    print(f"  PI-INA219: FAIL - {e}")
