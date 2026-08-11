#!/usr/bin/env python3
"""Raw I2C test - try every communication mode to find what works."""
import smbus2
import time
import os
import struct

ADDR = 0x40
BUS = 1

def test_all():
    bus = smbus2.SMBus(BUS)
    print(f"Bus {BUS} opened, testing address 0x{ADDR:02x}")
    
    # Test 1: read_i2c_block_data (word read, 2 bytes)
    for attempt in range(5):
        try:
            data = bus.read_i2c_block_data(ADDR, 0x00, 2)
            print(f"[OK] block_read attempt={attempt}: config=0x{data[0]:02x}{data[1]:02x}")
            break
        except Exception as e:
            print(f"[FAIL] block_read attempt={attempt}: {e}")
            time.sleep(0.2)
    
    # Test 2: read_byte_data (single byte SMBus)
    for attempt in range(5):
        try:
            val = bus.read_byte_data(ADDR, 0x01)
            print(f"[OK] byte_data_read attempt={attempt}: reg1=0x{val:02x}")
            break
        except Exception as e:
            print(f"[FAIL] byte_data_read attempt={attempt}: {e}")
            time.sleep(0.2)
    
    # Test 3: write_byte (set register pointer) then read_byte 
    for attempt in range(5):
        try:
            bus.write_byte(ADDR, 0x01)
            print(f"[OK] write_byte attempt={attempt}")
            time.sleep(0.01)
            val = bus.read_byte(ADDR)
            print(f"[OK] read_after_write: val=0x{val:02x}")
            break
        except Exception as e:
            print(f"[FAIL] write+read attempt={attempt}: {e}")
            time.sleep(0.2)
    
    # Test 4: read_word_data (SMBus word protocol)
    for attempt in range(5):
        try:
            val = bus.read_word_data(ADDR, 0x00)
            print(f"[OK] word_read attempt={attempt}: config=0x{val:04x}")
            break
        except Exception as e:
            print(f"[FAIL] word_read attempt={attempt}: {e}")
            time.sleep(0.2)
    
    # Test 5: i2c_rdwr (raw I2C messages)
    for attempt in range(5):
        try:
            # Write register pointer
            write_msg = smbus2.i2c_msg.write(ADDR, [0x01])  # point to shunt voltage reg
            # Read 2 bytes
            read_msg = smbus2.i2c_msg.read(ADDR, 2)
            bus.i2c_rdwr(write_msg, read_msg)
            data = list(read_msg)
            print(f"[OK] i2c_rdwr attempt={attempt}: shunt=0x{data[0]:02x}{data[1]:02x}")
            break
        except Exception as e:
            print(f"[FAIL] i2c_rdwr attempt={attempt}: {e}")
            time.sleep(0.2)
    
    # Test 6: Quick command (just ACK test, like i2cdetect)
    for attempt in range(3):
        try:
            # smbus2 doesn't have quick command; do write_quick manually
            msg = smbus2.i2c_msg.write(ADDR, [])
            bus.i2c_rdwr(msg)
            print(f"[OK] quick_command attempt={attempt}: device ACKs")
            break
        except Exception as e:
            print(f"[FAIL] quick_command attempt={attempt}: {e}")
            time.sleep(0.2)
    
    # Test 7: Try with a fresh bus object each time
    bus.close()
    print("\n--- Fresh bus per attempt ---")
    for attempt in range(5):
        try:
            b = smbus2.SMBus(BUS)
            time.sleep(0.05)
            data = b.read_i2c_block_data(ADDR, 0x00, 2)
            print(f"[OK] fresh_bus attempt={attempt}: config=0x{data[0]:02x}{data[1]:02x}")
            b.close()
            break
        except Exception as e:
            print(f"[FAIL] fresh_bus attempt={attempt}: {e}")
            try:
                b.close()
            except:
                pass
            time.sleep(0.5)
    
    # Test 8: Try pi-ina219 with multiple retries
    print("\n--- pi-ina219 with retries ---")
    for attempt in range(5):
        try:
            from ina219 import INA219
            ina = INA219(shunt_ohms=0.1, max_expected_amps=3.0, address=ADDR, busnum=BUS)
            ina.configure()
            v = ina.voltage()
            c = ina.current()
            p = ina.power()
            print(f"[OK] pi-ina219 attempt={attempt}: V={v:.3f} I={c:.2f}mA P={p:.2f}mW")
            break
        except Exception as e:
            print(f"[FAIL] pi-ina219 attempt={attempt}: {e}")
            time.sleep(0.5)

if __name__ == "__main__":
    test_all()
