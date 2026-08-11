#!/usr/bin/env python3
"""Test both INA219 code paths to find which one works."""
import sys, os, time
sys.path.insert(0, os.path.expanduser("~/secure-tunnel"))

print("=" * 60)
print("TEST 1: pi-ina219 library (PowerCollector path)")
print("=" * 60)
try:
    from ina219 import INA219
    SHUNT = 0.1
    MAX_AMPS = 3.0
    for busnum in [1, 0]:
        for addr in [0x40]:
            for attempt in range(3):
                try:
                    ina = INA219(shunt_ohms=SHUNT, max_expected_amps=MAX_AMPS,
                                 address=addr, busnum=busnum)
                    ina.configure()
                    v = ina.voltage()
                    c = ina.current()  # mA
                    p = ina.power()    # mW
                    print(f"  pi-ina219: bus={busnum} addr=0x{addr:02x}")
                    print(f"  Voltage: {v:.3f} V")
                    print(f"  Current: {c:.1f} mA ({abs(c)/1000:.3f} A)")
                    print(f"  Power:   {p:.1f} mW ({p/1000:.3f} W)")
                    print(f"  STATUS: OK")
                    break
                except Exception as e:
                    print(f"  Attempt {attempt+1}/3 bus={busnum} addr=0x{addr:02x}: {e}")
                    time.sleep(0.3)
except ImportError:
    print("  pi-ina219 not installed")
except Exception as e:
    print(f"  FAILED: {e}")

print()
print("=" * 60)
print("TEST 2: adafruit_ina219 library")
print("=" * 60)
try:
    import adafruit_ina219
    import board
    for attempt in range(3):
        try:
            i2c = board.I2C()
            sensor = adafruit_ina219.INA219(i2c)
            v = sensor.bus_voltage
            c = sensor.current  # mA
            p = sensor.power    # mW
            print(f"  adafruit: Voltage={v:.3f}V Current={c:.1f}mA Power={p:.1f}mW")
            print(f"  STATUS: OK")
            break
        except Exception as e:
            print(f"  Attempt {attempt+1}/3: {e}")
            time.sleep(0.3)
except ImportError:
    print("  adafruit_ina219 not installed")
except Exception as e:
    print(f"  FAILED: {e}")

print()
print("=" * 60)
print("TEST 3: smbus2 direct register read (Ina219PowerMonitor path)")
print("=" * 60)
try:
    import smbus2
    for attempt in range(3):
        try:
            bus = smbus2.SMBus(1)
            # Reset: write 0x8000 to config register
            bus.write_i2c_block_data(0x40, 0x00, [0x80, 0x00])
            time.sleep(0.1)
            # Read config register
            hi, lo = bus.read_i2c_block_data(0x40, 0x00, 2)
            cfg = (hi << 8) | lo
            print(f"  Config register after reset: 0x{cfg:04x}")
            # Configure: 32V range, 320mV gain, highspeed ADC, continuous
            cfg_val = 0x2000 | 0x1800 | 0x0080 | 0x0000 | 0x0007
            bus.write_i2c_block_data(0x40, 0x00, [(cfg_val >> 8) & 0xFF, cfg_val & 0xFF])
            time.sleep(0.01)
            # Read shunt voltage (reg 0x01)
            hi, lo = bus.read_i2c_block_data(0x40, 0x01, 2)
            raw_shunt = (hi << 8) | lo
            if raw_shunt & 0x8000:
                raw_shunt -= 1 << 16
            v_shunt = raw_shunt * 10e-6  # V
            # Read bus voltage (reg 0x02)
            hi, lo = bus.read_i2c_block_data(0x40, 0x02, 2)
            raw_bus = (hi << 8) | lo
            v_bus = ((raw_bus >> 3) & 0x1FFF) * 0.004  # V
            current_a = v_shunt / 0.1  # shunt_ohm=0.1
            power_w = current_a * v_bus
            print(f"  Shunt voltage: {v_shunt*1000:.3f} mV")
            print(f"  Bus voltage:   {v_bus:.3f} V")
            print(f"  Current:       {current_a*1000:.1f} mA")
            print(f"  Power:         {power_w*1000:.1f} mW")
            print(f"  STATUS: OK")
            bus.close()
            break
        except Exception as e:
            print(f"  Attempt {attempt+1}/3: {e}")
            time.sleep(0.5)
except ImportError:
    print("  smbus2 not installed")
except Exception as e:
    print(f"  FAILED: {e}")

print()
print("=" * 60)
print("TEST 4: PowerCollector from metrics_collectors")
print("=" * 60)
try:
    from core.metrics_collectors import PowerCollector
    pc = PowerCollector(backend="auto")
    print(f"  Detected backend: {pc.backend}")
    print(f"  INA backend:      {pc._ina_backend}")
    print(f"  INA busnum:       {pc._ina_busnum}")
    if pc.backend != "none":
        reading = pc.collect()
        print(f"  Voltage: {reading.get('voltage_v')} V")
        print(f"  Current: {reading.get('current_a')} A")
        print(f"  Power:   {reading.get('power_w')} W")
        if reading.get('error'):
            print(f"  Error:   {reading['error']}")
        print(f"  STATUS: OK")
    else:
        print(f"  STATUS: NO BACKEND AVAILABLE")
except Exception as e:
    print(f"  FAILED: {e}")

print()
print("=" * 60)
print("TEST 5: create_power_monitor factory (new code)")
print("=" * 60)
try:
    from pathlib import Path
    import tempfile
    from core.power_monitor import create_power_monitor, PowerMonitorUnavailable
    try:
        pm = create_power_monitor(Path(tempfile.mkdtemp()), backend="auto")
        print(f"  Backend class: {type(pm).__name__}")
        if hasattr(pm, 'backend_name'):
            print(f"  Backend name:  {pm.backend_name}")
        print(f"  STATUS: OK (using {type(pm).__name__})")
    except PowerMonitorUnavailable as e:
        print(f"  PowerMonitorUnavailable: {e}")
        print(f"  STATUS: Correctly raised (no silent mock!)")
except Exception as e:
    print(f"  FAILED: {e}")
