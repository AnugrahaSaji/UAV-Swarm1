#!/usr/bin/env python3
"""Definitive INA219 voltage analysis.
Question: Is the 4.2V reading correct, or is there an ADC/decode error?

INA219 Bus Voltage Register (0x02):
  - Bits [15:3] = Bus voltage data (13 bits)
  - Bit 1 = CNVR (conversion ready)
  - Bit 0 = OVF (math overflow)
  - LSB = 4 mV
  - Full scale: BRNG=1 → 32V, BRNG=0 → 16V
  - Bus voltage is measured at V_IN- pin

INA219 Shunt Voltage Register (0x01):
  - Signed 16-bit (or less depending on PGA)
  - LSB = 10 µV
  - V_shunt = V_IN+ - V_IN-
  - Negative means V_IN+ < V_IN- (reversed current or swapped wiring)

Supply voltage: V_supply = V_IN+ = V_bus + V_shunt
  (where V_bus = voltage at V_IN-)
"""
import time
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

# Take 50 rapid samples
print("=" * 60)
print("50 RAPID SAMPLES (bus voltage + shunt)")
print("=" * 60)
samples = []
for i in range(50):
    vr = r16(0x02)
    sr = r16(0x01)
    if vr is not None and sr is not None:
        v_field = (vr >> 3) & 0x1FFF
        cnvr = (vr >> 1) & 1
        ovf = vr & 1
        vbus = v_field * 0.004
        s_signed = sr if sr < 0x8000 else sr - 65536
        shunt_mv = s_signed * 0.01
        shunt_v = s_signed * 10e-6
        # V_supply = V_IN+ = V_bus (at V_IN-) + V_shunt (V+ - V-)
        v_supply = vbus + shunt_v
        i_amps = abs(shunt_v) / SHUNT_OHM
        samples.append({
            'raw_bus': vr, 'raw_sh': sr, 'v_field': v_field,
            'cnvr': cnvr, 'ovf': ovf,
            'vbus': vbus, 'shunt_mv': shunt_mv,
            'v_supply': v_supply, 'i_amps': i_amps
        })

if not samples:
    print("  NO VALID SAMPLES!")
    bus.close()
    raise SystemExit(1)

# Print first 10
for i, s in enumerate(samples[:10]):
    print(f"  [{i:2d}] raw=0x{s['raw_bus']:04X}  field={s['v_field']:4d}  "
          f"Vbus={s['vbus']:.3f}V  Vshunt={s['shunt_mv']:+.2f}mV  "
          f"Vsupply={s['v_supply']:.3f}V  I={s['i_amps']*1000:.1f}mA  "
          f"CNVR={s['cnvr']} OVF={s['ovf']}")
print(f"  ... ({len(samples)} total samples)")

# Statistics
vbus_vals = [s['vbus'] for s in samples]
vsh_vals = [s['shunt_mv'] for s in samples]
vsup_vals = [s['v_supply'] for s in samples]
i_vals = [s['i_amps'] for s in samples]

print(f"\n  Vbus:    min={min(vbus_vals):.3f}  avg={sum(vbus_vals)/len(vbus_vals):.3f}  max={max(vbus_vals):.3f} V")
print(f"  Vshunt:  min={min(vsh_vals):.2f}  avg={sum(vsh_vals)/len(vsh_vals):.2f}  max={max(vsh_vals):.2f} mV")
print(f"  Vsupply: min={min(vsup_vals):.3f}  avg={sum(vsup_vals)/len(vsup_vals):.3f}  max={max(vsup_vals):.3f} V")
print(f"  Current: min={min(i_vals)*1000:.1f}  avg={sum(i_vals)/len(i_vals)*1000:.1f}  max={max(i_vals)*1000:.1f} mA")

# Analysis
avg_vbus = sum(vbus_vals) / len(vbus_vals)
avg_vsh = sum(vsh_vals) / len(vsh_vals)
avg_vsup = sum(vsup_vals) / len(vsup_vals)
avg_i = sum(i_vals) / len(i_vals)

print("\n" + "=" * 60)
print("ANALYSIS")
print("=" * 60)
print(f"  INA219 V_bus (at V_IN-):  {avg_vbus:.3f} V")
print(f"  INA219 V_shunt (V+ - V-): {avg_vsh:.2f} mV")
print(f"  V_supply (V+ = V_bus + V_shunt): {avg_vsup:.3f} V")
print(f"  Current: {avg_i*1000:.1f} mA  ({avg_i:.3f} A)")
print(f"  Power:   {avg_vbus * avg_i:.3f} W")

if avg_vsh < 0:
    print(f"\n  ⚠ SHUNT VOLTAGE IS NEGATIVE ({avg_vsh:.2f} mV)")
    print(f"    This means V_IN+ < V_IN- (V+ is lower than V-).")
    print(f"    Likely cause: V+ and V- wires are SWAPPED on the shunt.")
    print(f"    Current direction: from V- toward V+ (reversed high-side)")
    print(f"    The current magnitude is still correct: {avg_i*1000:.1f} mA")
    print(f"    For correct supply voltage with swapped V+/V-:")
    # If V+/V- are swapped on the INA219 breakout:
    # Physical V+ (actual supply) → connected to INA219 V_IN-
    # Physical V- (actual load)   → connected to INA219 V_IN+
    # V_bus measures V_IN- = actual supply voltage
    # V_shunt = V_IN+ - V_IN- = V_load - V_supply < 0
    # So actual V_supply = V_bus (what we read)
    # And actual V_load = V_bus + V_shunt = V_bus - |V_shunt|
    print(f"    V_supply (actual) = V_bus = {avg_vbus:.3f} V")
    print(f"    V_load (actual)   = V_bus + V_shunt = {avg_vbus + avg_vsh/1000:.3f} V")
    print(f"    Shunt drop = {abs(avg_vsh):.2f} mV across {SHUNT_OHM} Ω")

print(f"\n  ⓘ  The INA219 reads ~{avg_vbus:.1f}V. If this should be 5V:")
print(f"     Deficit: {5.0 - avg_vbus:.2f}V")
print(f"     Possible causes:")
print(f"       1. Power supply is weak/undervolting")
print(f"       2. USB-C cable has high resistance")
print(f"       3. INA219 is not on the 5V rail (wrong wiring point)")
print(f"       4. Additional inline resistance (connectors, breadboard)")
print(f"     Check with multimeter: measure between GPIO pin 2 (5V) and pin 6 (GND)")

# Check if we're seeing 3.3V rail instead of 5V
if 3.0 < avg_vbus < 3.6:
    print(f"\n  ⚠ This looks like the 3.3V rail, NOT the 5V rail!")
    print(f"    The INA219 might be connected to GPIO 3.3V (pin 1) instead of 5V (pin 2)")
elif 4.5 < avg_vbus < 5.5:
    print(f"\n  ✓ Voltage is in normal 5V range")
elif 3.6 < avg_vbus < 4.5:
    print(f"\n  ⚠ Voltage {avg_vbus:.2f}V is between 3.3V and 5V rails.")
    print(f"    This is abnormally low for a 5V rail.")
    print(f"    Strongly suggests: insufficient power supply, high-resistance cable,")
    print(f"    or extra resistance in the measurement path (breadboard / jumper wires)")

bus.close()
print("\nDone.")
