#!/usr/bin/env python3
"""Deep INA219 hardware diagnostic - tests every access method."""
import sys
import time
import os

def test_smbus2():
    """Test raw smbus2 register access."""
    print("=== TEST 1: smbus2 raw register access ===")
    try:
        import smbus2
        bus = smbus2.SMBus(1)
        
        # Try reset first
        print("  Sending reset (0x8000 to reg 0x00)...")
        try:
            bus.write_word_data(0x40, 0x00, 0x0080)  # byte-swapped 0x8000
            time.sleep(0.05)
            print("  Reset sent OK")
        except Exception as e:
            print(f"  Reset WRITE failed: {e}")
        
        # Read config register
        for i in range(3):
            try:
                data = bus.read_i2c_block_data(0x40, 0x00, 2)
                val = (data[0] << 8) | data[1]
                print(f"  Read #{i+1}: Config reg = 0x{val:04X}")
            except Exception as e:
                print(f"  Read #{i+1}: FAILED - {e}")
            time.sleep(0.2)
        
        # Read bus voltage register
        for i in range(3):
            try:
                data = bus.read_i2c_block_data(0x40, 0x02, 2)
                val = (data[0] << 8) | data[1]
                voltage = ((val >> 3) & 0x1FFF) * 0.004
                print(f"  Read #{i+1}: Bus voltage reg = 0x{val:04X} = {voltage:.3f}V")
            except Exception as e:
                print(f"  Read #{i+1}: FAILED - {e}")
            time.sleep(0.2)
        
        bus.close()
    except ImportError:
        print("  smbus2 not installed")
    except Exception as e:
        print(f"  FATAL: {e}")

def test_pi_ina219():
    """Test pi-ina219 library."""
    print("\n=== TEST 2: pi-ina219 library ===")
    try:
        from ina219 import INA219
        
        for attempt in range(3):
            try:
                ina = INA219(shunt_ohms=0.1, max_expected_amps=3.0, address=0x40, busnum=1)
                ina.configure()
                v = ina.voltage()
                c = ina.current()
                p = ina.power()
                print(f"  Attempt {attempt+1}: V={v:.3f}V, I={c:.2f}mA, P={p:.2f}mW")
                return True
            except Exception as e:
                print(f"  Attempt {attempt+1}: FAILED - {e}")
                time.sleep(0.5)
    except ImportError:
        print("  pi-ina219 not installed")
    return False

def test_adafruit():
    """Test adafruit_ina219 library."""
    print("\n=== TEST 3: adafruit_ina219 library ===")
    try:
        import board
        import adafruit_ina219
        
        for attempt in range(3):
            try:
                i2c = board.I2C()
                sensor = adafruit_ina219.INA219(i2c)
                v = sensor.bus_voltage
                c = sensor.current
                p = sensor.power
                print(f"  Attempt {attempt+1}: V={v:.3f}V, I={c:.2f}mA, P={p:.2f}mW")
                return True
            except Exception as e:
                print(f"  Attempt {attempt+1}: FAILED - {e}")
                time.sleep(0.5)
    except ImportError as ie:
        print(f"  Import failed: {ie}")
    return False

def test_raw_fd():
    """Test raw file descriptor I2C access."""
    print("\n=== TEST 4: Raw /dev/i2c-1 access ===")
    import struct
    import fcntl
    
    I2C_SLAVE = 0x0703
    
    try:
        fd = os.open("/dev/i2c-1", os.O_RDWR)
        fcntl.ioctl(fd, I2C_SLAVE, 0x40)
        
        # Write register pointer to 0x00 (config)
        os.write(fd, bytes([0x00]))
        time.sleep(0.01)
        
        # Read 2 bytes
        data = os.read(fd, 2)
        val = struct.unpack(">H", data)[0]
        print(f"  Config register: 0x{val:04X}")
        
        # Write register pointer to 0x02 (bus voltage)
        os.write(fd, bytes([0x02]))
        time.sleep(0.01)
        data = os.read(fd, 2)
        val = struct.unpack(">H", data)[0]
        voltage = ((val >> 3) & 0x1FFF) * 0.004
        print(f"  Bus voltage: 0x{val:04X} = {voltage:.3f}V")
        
        os.close(fd)
        return True
    except Exception as e:
        print(f"  FAILED: {e}")
        try:
            os.close(fd)
        except:
            pass
    return False

def test_power_collector():
    """Test the actual PowerCollector from core/metrics_collectors.py."""
    print("\n=== TEST 5: core.metrics_collectors.PowerCollector ===")
    try:
        sys.path.insert(0, "/home/dev/secure-tunnel")
        os.environ["INA219_I2C_BUS"] = "1"
        os.environ["INA219_ADDR"] = "0x40"
        
        from core.metrics_collectors import PowerCollector
        
        pc = PowerCollector(backend="auto")
        print(f"  Backend detected: {pc.backend}")
        print(f"  INA219 object: {pc._ina219}")
        print(f"  Bus number: {pc._ina_busnum}")
        print(f"  Address: 0x{pc._ina_address:02X}")
        
        if pc.backend != "none":
            sample = pc.collect()
            print(f"  Sample: V={sample.get('voltage_v')}, I={sample.get('current_a')}, P={sample.get('power_w')}")
            if sample.get("error"):
                print(f"  Error: {sample['error']}")
        else:
            print("  Backend is 'none' - no INA219 available")
    except Exception as e:
        print(f"  FAILED: {e}")
        import traceback
        traceback.print_exc()

def test_power_monitor():
    """Test core/power_monitor.py Ina219PowerMonitor."""
    print("\n=== TEST 6: core.power_monitor.Ina219PowerMonitor ===")
    try:
        sys.path.insert(0, "/home/dev/secure-tunnel")
        from core.power_monitor import Ina219PowerMonitor, PowerMonitorUnavailable
        from pathlib import Path
        
        out = Path("/tmp/ina_test_output")
        out.mkdir(exist_ok=True)
        
        try:
            pm = Ina219PowerMonitor(output_dir=out, i2c_bus=1, address=0x40, shunt_ohm=0.1, sample_hz=10)
            print(f"  Monitor created OK")
            
            # Try a single read
            c, v = pm._read_current_voltage()
            print(f"  Single read: V={v:.3f}V, I={c:.4f}A")
        except PowerMonitorUnavailable as e:
            print(f"  PowerMonitorUnavailable: {e}")
        except Exception as e:
            print(f"  FAILED: {e}")
            import traceback
            traceback.print_exc()
    except ImportError as ie:
        print(f"  Import failed: {ie}")

if __name__ == "__main__":
    print(f"Python: {sys.executable}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"PID: {os.getpid()}")
    print()
    
    test_smbus2()
    test_pi_ina219()
    test_adafruit()
    test_raw_fd()
    test_power_collector()
    test_power_monitor()
    
    print("\n=== DONE ===")
