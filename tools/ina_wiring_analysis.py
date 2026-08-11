#!/usr/bin/env python3
"""INA219 wiring analysis — considering power flows THROUGH the INA219.

Physical setup (high-side measurement):
  PSU 5V → INA219 V_IN+ → [0.1Ω shunt] → V_IN- → Pi 5V rail → Pi load → GND
  
  INA219 GND → Pi GND (same ground reference)

  V_bus register = voltage at V_IN- pin relative to GND
  V_shunt register = V_IN+ - V_IN- (positive when current flows V+ → V-)

If V_shunt is NEGATIVE, it means either:
  a) V+/V- silkscreen labels are swapped on the breakout board, OR
  b) The wiring is: PSU → V_IN- → shunt → V_IN+ → Pi (reversed)

In case (b):
  V_bus = voltage at V_IN- = PSU output voltage
  V_shunt = V_IN+ - V_IN- = V_pi - V_psu = negative (because V_pi < V_psu)
  V_pi = V_bus + V_shunt = V_psu - |V_shunt|
  
  So V_bus should be ~5.1V and V_pi should be ~5.04V
  
  BUT we read V_bus = 4.2V. That's wrong for a 5.1V supply.

In case (a) - labels swapped but wiring physically correct:
  Physical: PSU → physical_V- → shunt → physical_V+ → Pi
  But chip pins are: physical_V- is actually chip V_IN+, physical_V+ is chip V_IN-
  So: V_bus = voltage at chip V_IN- = voltage at physical V+ = Pi voltage
  V_shunt = chip V_IN+ - chip V_IN- = physical V- - physical V+ = negative
  
This would mean: V_bus = Pi voltage = 4.2V ... but Pi says no undervoltage!

Let me check if the default config has reduced BRNG or if the ADC is wrong.
"""
import time, statistics
from smbus2 import SMBus

BUS = 1
ADDR = 0x40
SHUNT_OHM = 0.1

bus = SMBus(BUS)
try: bus.read_byte_data(ADDR, 0)
except: pass

def r16(reg):
    for _ in range(3):
        try:
            w = bus.read_word_data(ADDR, reg)
            v = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
            if v == 0 and _ < 2 and reg in (0x00, 0x02):
                continue
            return v
        except OSError:
            pass
    return None

print("=" * 60)
print("INA219 REGISTER STATE")
print("=" * 60)

cfg = r16(0x00)
print(f"  Config: 0x{cfg:04X}")
brng = (cfg >> 13) & 1
pga = (cfg >> 11) & 3
badc = (cfg >> 7) & 0xF
sadc = (cfg >> 3) & 0xF
mode = cfg & 7
vrange = "32V" if brng else "16V"
pga_gain = 1 << pga
pga_mv = [40, 80, 160, 320][pga]
print(f"  BRNG: {brng} ({vrange} range)")
print(f"  PGA:  /{pga_gain} (±{pga_mv}mV shunt range)")
print(f"  BADC: {badc} (bus ADC config)")
print(f"  SADC: {sadc} (shunt ADC config)")
print(f"  Mode: {mode} (7=continuous shunt+bus)")

print()
print("=" * 60)
print("RAW REGISTER ANALYSIS")
print("=" * 60)

# Read bus voltage register raw
vr = r16(0x02)
print(f"  Bus voltage raw: 0x{vr:04X} = {vr:016b}b")
print(f"  Bits [15:3] (voltage):  {(vr >> 3) & 0x1FFF} × 4mV = {((vr >> 3) & 0x1FFF) * 0.004:.3f} V")
print(f"  Bit 1 (CNVR):           {(vr >> 1) & 1}")
print(f"  Bit 0 (OVF):            {vr & 1}")

# Read shunt voltage register raw
sr = r16(0x01)
s_signed = sr if sr < 0x8000 else sr - 65536
print(f"\n  Shunt voltage raw: 0x{sr:04X} = signed {s_signed}")
print(f"  Value:  {s_signed} × 10µV = {s_signed * 0.01:.2f} mV = {s_signed * 10e-6:.6f} V")

print()
print("=" * 60)
print("CRITICAL ANALYSIS: WHERE IS 5V?")
print("=" * 60)

# 100 samples for good statistics
vbus_list = []
shunt_list = []
for i in range(100):
    vr = r16(0x02)
    sr = r16(0x01)
    if vr and sr is not None:
        vf = (vr >> 3) & 0x1FFF
        vb = vf * 0.004
        ss = sr if sr < 0x8000 else sr - 65536
        sv = ss * 10e-6
        vbus_list.append(vb)
        shunt_list.append(sv)

vbus_avg = statistics.mean(vbus_list)
vbus_std = statistics.stdev(vbus_list)
shunt_avg = statistics.mean(shunt_list)
shunt_std = statistics.stdev(shunt_list)
current_avg = abs(shunt_avg) / SHUNT_OHM

print(f"  100 samples:")
print(f"  V_bus:   {vbus_avg:.4f} ± {vbus_std:.4f} V")
print(f"  V_shunt: {shunt_avg*1000:.3f} ± {shunt_std*1000:.3f} mV")
print(f"  Current: {current_avg*1000:.1f} mA")
print(f"  V_shunt direction: {'NEGATIVE (reversed polarity)' if shunt_avg < 0 else 'POSITIVE (normal)'}")

# Key question: is V_bus the supply side or load side?
# INA219 spec: V_bus = voltage at V_IN- relative to GND

# If INA219 is wired correctly (PSU→V+→shunt→V-→Pi):
#   V_bus = Pi rail voltage, V_shunt > 0
#   V_supply = V_bus + V_shunt

# If INA219 is wired reversed (PSU→V-→shunt→V+→Pi):
#   V_bus = PSU output, V_shunt < 0  (V_IN+ is Pi side, V_IN- is PSU side)
#   V_supply = V_bus (PSU side)
#   V_pi = V_bus + V_shunt (= V_bus - drop)

# Our data: V_bus=4.2V, V_shunt=-57mV
# If reversed: V_supply=4.2V (PSU side), V_pi=4.14V → Pi would undervolt!
# If correct: V_pi=4.2V → Pi would undervolt!

# BUT Pi reports NO undervoltage (threshold ~4.63V). So either:
# 1. INA219 ADC has systematic error/offset
# 2. The INA219 is NOT inline with the Pi power (Pi gets power elsewhere)
# 3. Something wrong with our understanding of the circuit

print()
print("  Scenario A: Normal wiring (PSU→V+→shunt→V-→Pi)")
va_supply = vbus_avg + shunt_avg  # V+ side
va_pi = vbus_avg  # V- side = Pi
print(f"    V_supply (V+): {vbus_avg + shunt_avg:.3f} V")
print(f"    V_pi (V-):     {vbus_avg:.3f} V")

print(f"\n  Scenario B: Reversed wiring (PSU→V-→shunt→V+→Pi)")
vb_supply = vbus_avg  # V- side = PSU
vb_pi = vbus_avg + shunt_avg  # V+ side = Pi
print(f"    V_PSU (V-):    {vbus_avg:.3f} V")
print(f"    V_pi (V+):     {vbus_avg + shunt_avg:.3f} V")

print(f"\n  ⚠ BOTH scenarios show ~4.2V at the Pi!")
print(f"  But Pi reports throttled=0x0 (no undervoltage, threshold ~4.63V)")
print(f"  This is CONTRADICTORY unless INA219 reading is inaccurate.")

# Check for breakout board voltage divider
# Some INA219 breakout boards have voltage dividers or level shifters
# that can affect the bus voltage sense path
print()
print("=" * 60)
print("BREAKOUT BOARD / ADC ERROR ANALYSIS") 
print("=" * 60)

# If there's a systematic gain error:
# True_V = measured_V × gain_factor
# If Pi is actually at 5.0V but INA reads 4.2V:
gain_factor = 5.0 / vbus_avg
print(f"  If true voltage = 5.0V:")
print(f"    Gain correction factor: {gain_factor:.4f}")
print(f"    ADC error: {(1 - 1/gain_factor) * 100:.1f}%")

# Or if there's a fixed offset:
offset = 5.0 - vbus_avg
print(f"    Offset correction: +{offset:.3f} V")

# Check if the issue could be BRNG bit interpretation
# BRNG=1: FSR=32V, LSB=4mV (we read this)
# BRNG=0: FSR=16V, LSB=4mV (would give same value)
# The LSB is always 4mV regardless of BRNG
print(f"\n  Bus voltage LSB is always 4mV regardless of BRNG.")
print(f"  BRNG only sets the full-scale range, not the step size.")
print(f"  Our reading of {vbus_avg:.3f}V with field ~{int(vbus_avg/0.004)} is correct math.")

# Check if INA219 could have a different resolution
# Some clones have 10-bit ADC instead of 12-bit
raw_fields = [(r16(0x02) >> 3) & 0x1FFF for _ in range(20)]
unique_lsbs = set(f & 0x07 for f in raw_fields)
print(f"\n  Last 3 bits of voltage field across 20 reads: {unique_lsbs}")
if len(unique_lsbs) <= 2:
    print(f"  ⚠ Very few LSB values — ADC may have reduced resolution")
else:
    print(f"  ADC appears to have full 12-bit resolution")

# Power calculation with our data (as-is)
power = vbus_avg * current_avg
print(f"\n  Power (as measured): {vbus_avg:.3f}V × {current_avg:.3f}A = {power:.3f}W")

# If we apply gain correction to 5V:
corrected_v = vbus_avg * gain_factor
corrected_p = corrected_v * current_avg
print(f"  Power (corrected to 5V): {corrected_v:.3f}V × {current_avg:.3f}A = {corrected_p:.3f}W")
print(f"  Difference: {(corrected_p - power) * 1000:.1f} mW ({(corrected_p/power - 1)*100:.1f}%)")

bus.close()
print("\nDone.")
