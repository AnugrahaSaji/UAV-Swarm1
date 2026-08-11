#!/usr/bin/env python3
"""Compare ADC resolution effects on INA219 voltage readings."""
import time

print("=== ADC Resolution Comparison ===")
print()

try:
    import board
    import adafruit_ina219
except ImportError as e:
    print(f"Import failed: {e}")
    exit(1)

# Test 1: Default 12-bit ADC
print("--- 12-bit ADC (default) ---")
vals_12 = []
for i in range(8):
    try:
        i2c = board.I2C()
        s = adafruit_ina219.INA219(i2c)
        s.set_calibration_32V_2A()
        v = s.bus_voltage
        c = s.current
        sv = s.shunt_voltage
        vals_12.append((v, c, sv))
        print(f"  [{i+1}] V={v:.3f}V  I={c:.1f}mA  Vshunt={sv*1000:.2f}mV")
        i2c.deinit()
    except Exception as e:
        print(f"  [{i+1}] FAIL: {e}")
        try:
            i2c.deinit()
        except:
            pass
    time.sleep(0.15)

if vals_12:
    avg_v = sum(r[0] for r in vals_12) / len(vals_12)
    avg_c = sum(r[1] for r in vals_12) / len(vals_12)
    print(f"  AVG: V={avg_v:.3f}V  I={avg_c:.1f}mA  ({len(vals_12)}/8 OK)")

print()

# Test 2: 9-bit ADC (fast, for 1kHz sampling)
print("--- 9-bit ADC (fast mode) ---")
vals_9 = []
for i in range(8):
    try:
        i2c = board.I2C()
        s = adafruit_ina219.INA219(i2c)
        s.set_calibration_32V_2A()
        s.bus_adc_resolution = adafruit_ina219.ADCResolution.ADCRES_9BIT_1S
        s.shunt_adc_resolution = adafruit_ina219.ADCResolution.ADCRES_9BIT_1S
        v = s.bus_voltage
        c = s.current
        sv = s.shunt_voltage
        vals_9.append((v, c, sv))
        print(f"  [{i+1}] V={v:.3f}V  I={c:.1f}mA  Vshunt={sv*1000:.2f}mV")
        i2c.deinit()
    except Exception as e:
        print(f"  [{i+1}] FAIL: {e}")
        try:
            i2c.deinit()
        except:
            pass
    time.sleep(0.15)

if vals_9:
    avg_v = sum(r[0] for r in vals_9) / len(vals_9)
    avg_c = sum(r[1] for r in vals_9) / len(vals_9)
    print(f"  AVG: V={avg_v:.3f}V  I={avg_c:.1f}mA  ({len(vals_9)}/8 OK)")

print()

# Test 3: smbus2 direct register read
print("--- smbus2 direct register read ---")
try:
    import smbus2
    for i in range(5):
        try:
            bus = smbus2.SMBus(1)
            # Config register
            cfg = bus.read_i2c_block_data(0x40, 0x00, 2)
            cfg_val = (cfg[0] << 8) | cfg[1]
            # Bus voltage register
            bv = bus.read_i2c_block_data(0x40, 0x02, 2)
            bv_val = (bv[0] << 8) | bv[1]
            voltage = ((bv_val >> 3) & 0x1FFF) * 0.004
            # Shunt voltage register
            sv = bus.read_i2c_block_data(0x40, 0x01, 2)
            sv_raw = (sv[0] << 8) | sv[1]
            if sv_raw > 32767:
                sv_raw -= 65536
            shunt_mv = sv_raw * 0.01  # 10uV per LSB
            bus.close()
            print(f"  [{i+1}] Config=0x{cfg_val:04X}  BusV=0x{bv_val:04X}={voltage:.3f}V  ShuntV={shunt_mv:.2f}mV")
        except Exception as e:
            print(f"  [{i+1}] FAIL: {e}")
        time.sleep(0.2)
except ImportError:
    print("  smbus2 not available")

print()

# Test 4: PowerCollector from core
print("--- PowerCollector (production code path) ---")
import sys, os
sys.path.insert(0, "/home/dev/secure-tunnel")
os.environ["INA219_I2C_BUS"] = "1"
os.environ["INA219_ADDR"] = "0x40"
os.environ["INA219_DETECT_RETRIES"] = "8"
os.environ["INA219_DETECT_DELAY"] = "0.3"

from core.metrics_collectors import PowerCollector
pc = PowerCollector(backend="auto")
print(f"  Backend: {pc.backend}")
print(f"  INA backend: {pc._ina_backend}")
print(f"  INA219 obj: {type(pc._ina219).__name__ if pc._ina219 else 'None'}")

if pc.backend != "none":
    ok = 0
    for i in range(10):
        s = pc.collect()
        v = s.get("voltage_v")
        c = s.get("current_a")
        p = s.get("power_w")
        e = s.get("error")
        if e:
            print(f"  [{i+1:2d}] ERROR: {e}")
        elif v is not None:
            ok += 1
            print(f"  [{i+1:2d}] V={v:.3f}V  I={c:.4f}A  P={p:.3f}W")
        else:
            print(f"  [{i+1:2d}] null readings")
        time.sleep(0.15)
    print(f"  Success: {ok}/10")

print()
print("=== DONE ===")
