#!/usr/bin/env python3
"""Diagnose which INA219 backend actually works on this Pi."""
import sys
import traceback

# Run ONLY one test at a time based on argument
test = sys.argv[1] if len(sys.argv) > 1 else "pi"

if test == "pi":
    print("=== pi-ina219 (direct) ===")
    try:
        from ina219 import INA219
        ina = INA219(shunt_ohms=0.1, max_expected_amps=3.0, address=0x40, busnum=1)
        ina.configure()
        print(f"  voltage: {ina.voltage():.3f} V")
        print(f"  current: {ina.current():.3f} mA")
        print(f"  power:   {ina.power():.3f} mW")
        bus_obj = getattr(ina, '_i2c', None)
        print(f"  internal I2C type: {type(bus_obj).__name__}")
        print(f"  internal I2C module: {type(bus_obj).__module__}")
        print("  RESULT: OK")
    except Exception as e:
        print(f"  RESULT: FAIL - {e}")
        traceback.print_exc()

elif test == "adafruit":
    print("=== adafruit_ina219 ===")
    try:
        import board
        import adafruit_ina219
        i2c = board.I2C()
        sensor = adafruit_ina219.INA219(i2c)
        print(f"  bus_voltage: {sensor.bus_voltage:.3f} V")
        print(f"  current:     {sensor.current:.3f} mA")
        print(f"  power:       {sensor.power:.3f} mW")
        print("  RESULT: OK")
    except Exception as e:
        print(f"  RESULT: FAIL - {e}")
        traceback.print_exc()

elif test == "smbus2":
    print("=== smbus2 direct register read ===")
    try:
        import smbus2
        bus = smbus2.SMBus(1)
        hi, lo = bus.read_i2c_block_data(0x40, 0x02, 2)
        raw = (hi << 8) | lo
        voltage = ((raw >> 3) & 0x1FFF) * 0.004
        print(f"  raw reg 0x02: 0x{raw:04X}")
        print(f"  bus_voltage:  {voltage:.3f} V")
        try:
            bus.write_i2c_block_data(0x40, 0x00, [0x39, 0x9F])
            print("  write_config: OK")
        except Exception as we:
            print(f"  write_config: FAIL - {we}")
        bus.close()
        print("  RESULT: OK (read)")
    except Exception as e:
        print(f"  RESULT: FAIL - {e}")
        traceback.print_exc()

elif test == "collector":
    print("=== PowerCollector auto-detect ===")
    try:
        import os
        os.environ["DRONE_POWER_BACKEND"] = "ina219"
        os.environ["INA219_I2C_BUS"] = "1"
        os.environ["INA219_ADDR"] = "0x40"
        from core.metrics_collectors import PowerCollector, _INA219_BACKEND, HAS_INA219
        print(f"  HAS_INA219:     {HAS_INA219}")
        print(f"  _INA219_BACKEND: {_INA219_BACKEND}")
        pc = PowerCollector(backend="auto")
        print(f"  resolved: {pc.backend}")
        print(f"  obj:      {type(pc._ina219).__name__ if pc._ina219 else None}")
        if pc.backend == "ina219":
            r = pc.collect()
            print(f"  V={r.get('voltage_v')}  A={r.get('current_a')}  W={r.get('power_w')}")
            print("  RESULT: OK")
        else:
            print("  RESULT: FAIL (backend=none)")
    except Exception as e:
        print(f"  RESULT: FAIL - {e}")
        traceback.print_exc()
