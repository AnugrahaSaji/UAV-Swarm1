#!/usr/bin/env python3
"""Validate INA219 bus-voltage gain correction on Pi 4.

Reads 50 samples from INA219 and shows raw vs corrected voltage.
Expected: corrected voltage ≈ 5.0V (official PSU 5.1V, Pi idle).
"""
import os
import sys
import time
import statistics

GAIN = float(os.environ.get("INA219_VBUS_GAIN", "1.18"))

try:
    import smbus2
except ImportError:
    sys.exit("smbus2 not available")

ADDR = 0x40

bus = smbus2.SMBus(1)
# BCM2835 first-transaction warm-up
try:
    bus.read_byte_data(ADDR, 0x00)
except OSError:
    pass

raw_voltages = []
shunt_voltages = []
corrected_voltages = []

print(f"INA219_VBUS_GAIN = {GAIN}")
print(f"Sampling 50 readings...\n")

for i in range(50):
    for _att in range(3):
        try:
            # Bus voltage register 0x02
            w = bus.read_word_data(ADDR, 0x02)
            raw_v = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
            v_raw = ((raw_v >> 3) & 0x1FFF) * 0.004
            if v_raw < 0.1 and _att < 2:
                continue

            # Shunt voltage register 0x01
            w = bus.read_word_data(ADDR, 0x01)
            raw_sh = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
            if raw_sh & 0x8000:
                raw_sh -= 1 << 16
            v_sh = raw_sh * 10e-6

            v_corrected = v_raw * GAIN
            current_a = abs(v_sh) / 0.1

            raw_voltages.append(v_raw)
            shunt_voltages.append(v_sh)
            corrected_voltages.append(v_corrected)
            break
        except OSError:
            pass
    time.sleep(0.02)

bus.close()

print(f"{'':4s} {'RAW V_bus':>10s}  {'CORRECTED':>10s}  {'V_shunt':>10s}  {'Current':>10s}  {'Power':>10s}")
print("-" * 68)
for i in range(len(raw_voltages)):
    cur = abs(shunt_voltages[i]) / 0.1
    pwr = corrected_voltages[i] * cur
    print(f"{i+1:3d}. {raw_voltages[i]:10.4f}V  {corrected_voltages[i]:10.4f}V  "
          f"{shunt_voltages[i]*1000:8.2f}mV  {cur:8.4f}A  {pwr:8.4f}W")

print()
print("=" * 68)
print("SUMMARY")
print("=" * 68)
mean_raw = statistics.mean(raw_voltages)
mean_cor = statistics.mean(corrected_voltages)
std_raw = statistics.stdev(raw_voltages) if len(raw_voltages) > 1 else 0
std_cor = statistics.stdev(corrected_voltages) if len(corrected_voltages) > 1 else 0
mean_sh = statistics.mean(shunt_voltages)
mean_cur = abs(mean_sh) / 0.1

print(f"  Raw V_bus:       {mean_raw:.4f} ± {std_raw:.4f} V")
print(f"  Corrected V_bus: {mean_cor:.4f} ± {std_cor:.4f} V")
print(f"  V_shunt:         {mean_sh*1000:.2f} ± {statistics.stdev(shunt_voltages)*1000:.2f} mV")
print(f"  Current:         {mean_cur:.4f} A")
print(f"  Power (corr):    {mean_cor * mean_cur:.4f} W")
print()

# Sanity checks
if 4.5 <= mean_cor <= 5.5:
    print("✓ PASS: Corrected voltage in expected range [4.5V, 5.5V]")
else:
    print(f"✗ FAIL: Corrected voltage {mean_cor:.3f}V outside [4.5V, 5.5V]")

if 0.2 <= mean_cur <= 2.0:
    print(f"✓ PASS: Current {mean_cur:.3f}A in expected idle range [0.2A, 2.0A]")
else:
    print(f"✗ FAIL: Current {mean_cur:.3f}A outside expected range")

if mean_cor * mean_cur < 10:
    print(f"✓ PASS: Power {mean_cor * mean_cur:.2f}W reasonable for Pi4")
else:
    print(f"✗ FAIL: Power {mean_cor * mean_cur:.2f}W seems too high")
