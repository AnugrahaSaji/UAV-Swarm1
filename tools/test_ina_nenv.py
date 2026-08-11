#!/usr/bin/env python3
"""Quick test: can bench_ddos_v2.PowerMonitor detect INA219?"""
import sys, os
sys.path.insert(0, "/home/dev/secure-tunnel")
os.environ.setdefault("LIBOQS_PYTHON_DIR", "/home/dev/quantum-safe/liboqs-python")

from bench_ddos_v2 import PowerMonitor

pm = PowerMonitor()
print(f"available: {pm.available}")
print(f"backend:   {pm._backend}")
if pm.available:
    r = pm.read_once()
    print(f"voltage:   {r.get('voltage_v', 'N/A')} V")
    print(f"current:   {r.get('current_ma', 'N/A')} mA")
    print(f"power:     {r.get('power_mw', 'N/A')} mW")
else:
    # Try manual debug
    print("\n--- Debug ---")
    try:
        import smbus2
        bus = smbus2.SMBus(1)
        try:
            bus.read_byte_data(0x40, 0x00)
        except OSError as e:
            print(f"warmup EIO (expected): {e}")
        # Read config
        w = bus.read_word_data(0x40, 0x00)
        raw = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
        print(f"config reg: 0x{raw:04X}")
        # Read bus voltage
        w = bus.read_word_data(0x40, 0x02)
        raw = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
        v = ((raw >> 3) & 0x1FFF) * 0.004
        print(f"bus voltage raw: {v:.3f} V")
        bus.close()
        print("smbus2 direct: OK")
    except Exception as e:
        print(f"smbus2 direct failed: {e}")

    try:
        from ina219 import INA219
        ina = INA219(shunt_ohms=0.1, max_expected_amps=3.0)
        ina.configure()
        print(f"pi-ina219: voltage={ina.voltage():.3f} V, current={ina.current():.1f} mA")
    except Exception as e:
        print(f"pi-ina219 failed: {e}")

    try:
        import board, adafruit_ina219
        i2c = board.I2C()
        sensor = adafruit_ina219.INA219(i2c)
        print(f"adafruit: bus_voltage={sensor.bus_voltage:.3f} V, current={sensor.current:.1f} mA")
    except Exception as e:
        print(f"adafruit failed: {e}")
