#!/usr/bin/env python3
"""Debug PowerCollector detection."""
import sys, os, platform
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

print(f"Platform: {platform.system()} {platform.machine()}")

# Test imports
try:
    from ina219 import INA219
    print("pi-ina219: available")
except ImportError:
    print("pi-ina219: NOT available")

try:
    import adafruit_ina219
    import board
    print("adafruit_ina219: available")
except ImportError as e:
    print(f"adafruit_ina219: NOT available ({e})")

try:
    import smbus2
    print(f"smbus2: available v{smbus2.__version__}")
except ImportError:
    print("smbus2: NOT available")

print()

# Test warm-up function
from core.metrics_collectors import _warmup_i2c_bus, HAS_SMBUS2
print(f"HAS_SMBUS2: {HAS_SMBUS2}")
print("Running _warmup_i2c_bus...")
_warmup_i2c_bus(busnum=1, address=0x40)
print("  done")

print()
# Test pi-ina219 directly
print("=== pi-ina219 direct test ===")
try:
    from ina219 import INA219
    ina = INA219(shunt_ohms=0.1, max_expected_amps=3.0, address=0x40, busnum=1)
    ina.configure()
    v = ina.voltage()
    c = ina.current()
    print(f"  OK: {v:.3f}V, {c:.1f}mA")
except Exception as e:
    print(f"  FAIL: {e}")

print()
# Test adafruit directly
print("=== adafruit_ina219 direct test ===")
try:
    import board
    import adafruit_ina219
    i2c = board.I2C()
    sensor = adafruit_ina219.INA219(i2c)
    v = sensor.bus_voltage
    c = sensor.current
    print(f"  OK: {v:.3f}V, {c:.1f}mA")
except Exception as e:
    print(f"  FAIL: {e}")

print()
# Test PowerCollector
print("=== PowerCollector test ===")
from core.metrics_collectors import PowerCollector
pc = PowerCollector()
print(f"  Backend: {pc.backend}")
print(f"  INA backend: {pc._ina_backend}")
data = pc.collect()
for k, v in sorted(data.items()):
    print(f"  {k}: {v}")
