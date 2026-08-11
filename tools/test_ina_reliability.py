#!/usr/bin/env python3
"""INA219 reliability test - measures success rate across many attempts."""
import sys
import time
import os

sys.path.insert(0, "/home/dev/secure-tunnel")

def test_pi_ina219_reliability(n=30):
    print(f"=== pi-ina219 reliability test ({n} attempts) ===")
    try:
        from ina219 import INA219
    except ImportError:
        print("  pi-ina219 not installed")
        return

    ok = 0
    fail = 0
    for i in range(n):
        try:
            ina = INA219(shunt_ohms=0.1, max_expected_amps=3.0, address=0x40, busnum=1)
            ina.configure()
            v = ina.voltage()
            c = ina.current()
            p = ina.power()
            ok += 1
            print(f"  [{i+1:2d}] OK  V={v:.3f}V  I={c:.1f}mA  P={p:.1f}mW")
        except Exception as e:
            fail += 1
            print(f"  [{i+1:2d}] FAIL {e}")
        time.sleep(0.3)
    print(f"  Result: {ok}/{n} OK, {fail}/{n} FAIL ({ok*100//n}%)")

def test_adafruit_reliability(n=30):
    print(f"\n=== adafruit_ina219 reliability test ({n} attempts) ===")
    try:
        import board
        import adafruit_ina219
    except ImportError as e:
        print(f"  adafruit not installed: {e}")
        return

    ok = 0
    fail = 0
    for i in range(n):
        try:
            i2c = board.I2C()
            sensor = adafruit_ina219.INA219(i2c)
            v = sensor.bus_voltage
            c = sensor.current
            ok += 1
            print(f"  [{i+1:2d}] OK  V={v:.3f}V  I={c:.1f}mA")
            i2c.deinit()
        except Exception as e:
            fail += 1
            print(f"  [{i+1:2d}] FAIL {e}")
            try:
                i2c.deinit()
            except:
                pass
        time.sleep(0.3)
    print(f"  Result: {ok}/{n} OK, {fail}/{n} FAIL ({ok*100//n}%)")

def test_smbus2_reliability(n=30):
    print(f"\n=== smbus2 raw register reliability test ({n} attempts) ===")
    try:
        import smbus2
    except ImportError:
        print("  smbus2 not installed")
        return

    ok = 0
    fail = 0
    for i in range(n):
        try:
            bus = smbus2.SMBus(1)
            data = bus.read_i2c_block_data(0x40, 0x02, 2)
            val = (data[0] << 8) | data[1]
            voltage = ((val >> 3) & 0x1FFF) * 0.004
            bus.close()
            ok += 1
            print(f"  [{i+1:2d}] OK  raw=0x{val:04X}  V={voltage:.3f}V")
        except Exception as e:
            fail += 1
            print(f"  [{i+1:2d}] FAIL {e}")
            try:
                bus.close()
            except:
                pass
        time.sleep(0.3)
    print(f"  Result: {ok}/{n} OK, {fail}/{n} FAIL ({ok*100//n}%)")

def test_power_collector_with_retries():
    print(f"\n=== PowerCollector backend detection (with env) ===")
    os.environ["INA219_I2C_BUS"] = "1"
    os.environ["INA219_ADDR"] = "0x40"
    os.environ["INA219_DETECT_RETRIES"] = "10"
    os.environ["INA219_DETECT_DELAY"] = "0.5"

    from core.metrics_collectors import PowerCollector
    pc = PowerCollector(backend="auto")
    print(f"  Backend: {pc.backend}")
    print(f"  INA219 obj: {pc._ina219}")
    print(f"  Is adafruit: {pc._is_adafruit_sensor() if pc._ina219 else 'N/A'}")

    if pc.backend != "none":
        print("\n  Collecting 10 samples...")
        for i in range(10):
            s = pc.collect()
            v = s.get("voltage_v")
            c = s.get("current_a")
            p = s.get("power_w")
            e = s.get("error")
            if e:
                print(f"  [{i+1:2d}] ERROR: {e}")
            else:
                print(f"  [{i+1:2d}] V={v}  I={c}  P={p}")
            time.sleep(0.2)

if __name__ == "__main__":
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    test_smbus2_reliability(20)
    test_pi_ina219_reliability(20)
    test_adafruit_reliability(20)
    test_power_collector_with_retries()
    print("\n=== ALL DONE ===")
