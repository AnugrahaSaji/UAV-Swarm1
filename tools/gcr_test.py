#!/usr/bin/env python3
"""I2C general call reset + INA219 test."""
import smbus2
import time

BUS = 1
ADDR = 0x40

# Step 1: General call reset (I2C standard)
b = smbus2.SMBus(BUS)
try:
    b.write_byte(0x00, 0x06)  # General call reset
    print("GENERAL_CALL_RESET: OK")
except Exception as e:
    print(f"GENERAL_CALL_RESET: {e}")
b.close()

time.sleep(1)

# Step 2: Try to read config register after reset
b = smbus2.SMBus(BUS)
for attempt in range(10):
    try:
        data = b.read_i2c_block_data(ADDR, 0x00, 2)
        config = (data[0] << 8) | data[1]
        print(f"CONFIG_REG: 0x{config:04x} (attempt {attempt}) - DEFAULT=0x399F")
        # If we can read, try shunt voltage
        data = b.read_i2c_block_data(ADDR, 0x01, 2)
        shunt = (data[0] << 8) | data[1]
        if shunt & 0x8000:
            shunt -= 0x10000
        shunt_mv = shunt * 0.01
        print(f"SHUNT_VOLTAGE: {shunt_mv:.2f} mV")
        
        data = b.read_i2c_block_data(ADDR, 0x02, 2)
        bus_raw = (data[0] << 8) | data[1]
        bus_v = ((bus_raw >> 3) & 0x1FFF) * 0.004
        print(f"BUS_VOLTAGE: {bus_v:.3f} V")
        break
    except Exception as e:
        print(f"READ attempt {attempt}: {e}")
        time.sleep(0.3)
b.close()

# Step 3: Try pi-ina219 
print("\n--- pi-ina219 ---")
time.sleep(0.5)
for attempt in range(5):
    try:
        from ina219 import INA219
        ina = INA219(shunt_ohms=0.1, max_expected_amps=3.0, address=ADDR, busnum=BUS)
        ina.configure()
        v = ina.voltage()
        c = ina.current()
        p = ina.power()
        print(f"PI-INA219 OK: V={v:.3f}V I={c:.2f}mA P={p:.2f}mW")
        break
    except Exception as e:
        print(f"PI-INA219 attempt {attempt}: {e}")
        time.sleep(0.5)
