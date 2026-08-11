#!/usr/bin/env python3
"""INA219 calibration diagnostic — raw register analysis.

Reads all INA219 registers, decodes config, and computes
voltage/current with proper calibration for 3A / 0.1 ohm shunt.
Also checks if the bus voltage underread is due to:
  - wrong BRNG (16V vs 32V range)
  - wrong PGA gain
  - wrong ADC resolution
  - missing calibration register
  - shunt resistor value mismatch
"""
import time, struct

try:
    from smbus2 import SMBus
except ImportError:
    print("ERROR: smbus2 not installed")
    raise SystemExit(1)

I2C_BUS = 1
INA_ADDR = 0x40
SHUNT_OHM = 0.1  # physical shunt resistor

def read_u16(bus, reg):
    """Read 16-bit big-endian register via word read (BCM2835-safe)."""
    for attempt in range(3):
        try:
            w = bus.read_word_data(INA_ADDR, reg)
            val = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
            if val == 0 and attempt < 2:
                continue
            return val
        except OSError:
            pass
    return None

def write_u16(bus, reg, value):
    """Write 16-bit big-endian register via word write (BCM2835-safe).
    
    BCM2835 I2C is extremely fragile with consecutive writes.
    Strategy: close/reopen bus before each write attempt.
    """
    swapped = ((value & 0xFF) << 8) | ((value >> 8) & 0xFF)
    for _att in range(5):
        try:
            # Close and reopen to get a clean fd — BCM2835 workaround
            bus.close()
            time.sleep(0.02)
            bus.open(I2C_BUS)
            # Warm-up read after fresh open
            try: bus.read_byte_data(INA_ADDR, 0)
            except: pass
            time.sleep(0.005)
            bus.write_word_data(INA_ADDR, reg, swapped)
            time.sleep(0.005)
            # Warm-up read after write
            try: bus.read_byte_data(INA_ADDR, 0)
            except: pass
            return
        except OSError as e:
            if _att < 4:
                time.sleep(0.05)
    raise OSError("write_u16 failed after 5 retries")

def decode_config(cfg):
    """Decode INA219 config register fields."""
    rst   = (cfg >> 15) & 1
    brng  = (cfg >> 13) & 1
    pga   = (cfg >> 11) & 3
    badc  = (cfg >> 7) & 0xF
    sadc  = (cfg >> 3) & 0xF
    mode  = cfg & 7

    brng_str = "32V" if brng else "16V"
    pga_map = {0: "/1 (±40mV)", 1: "/2 (±80mV)", 2: "/4 (±160mV)", 3: "/8 (±320mV)"}
    adc_map = {
        0: "9-bit (84µs)", 1: "10-bit (148µs)", 2: "11-bit (276µs)", 3: "12-bit (532µs)",
        8: "12-bit (532µs)", 9: "2-sample avg (1.06ms)", 10: "4-sample avg (2.13ms)",
        11: "8-sample avg (4.26ms)", 12: "16-sample avg (8.51ms)",
        13: "32-sample avg (17ms)", 14: "64-sample avg (34ms)", 15: "128-sample avg (68ms)"
    }
    mode_map = {
        0: "Power-down", 1: "Shunt triggered", 2: "Bus triggered",
        3: "Shunt+Bus triggered", 4: "ADC off", 5: "Shunt continuous",
        6: "Bus continuous", 7: "Shunt+Bus continuous"
    }
    return {
        "RST": rst,
        "BRNG": f"{brng} ({brng_str})",
        "PGA": f"{pga} ({pga_map.get(pga, '?')})",
        "BADC": f"{badc} ({adc_map.get(badc, '?')})",
        "SADC": f"{sadc} ({adc_map.get(sadc, '?')})",
        "Mode": f"{mode} ({mode_map.get(mode, '?')})",
    }

def main():
    bus = SMBus(I2C_BUS)
    # BCM2835 warm-up
    try: bus.read_byte_data(INA_ADDR, 0)
    except: pass

    print("=" * 60)
    print("INA219 RAW REGISTER DUMP")
    print("=" * 60)

    reg_names = {
        0x00: "Configuration",
        0x01: "Shunt Voltage",
        0x02: "Bus Voltage",
        0x03: "Power",
        0x04: "Current",
        0x05: "Calibration",
    }
    regs = {}
    for r in range(6):
        val = read_u16(bus, r)
        regs[r] = val
        print(f"  Reg 0x{r:02X} ({reg_names[r]:>16s}): 0x{val:04X}  ({val:>5d})")

    print()
    print("=" * 60)
    print("CONFIG DECODE")
    print("=" * 60)
    cfg = regs[0x00]
    fields = decode_config(cfg)
    for k, v in fields.items():
        print(f"  {k:6s}: {v}")

    print()
    print("=" * 60)
    print("VOLTAGE ANALYSIS")
    print("=" * 60)

    # Bus voltage register: bits[15:3] = voltage, bit1=CNVR, bit0=OVF
    raw_bus = regs[0x02]
    cnvr = (raw_bus >> 1) & 1
    ovf = raw_bus & 1
    bus_v_field = (raw_bus >> 3) & 0x1FFF
    bus_voltage = bus_v_field * 0.004
    print(f"  Raw bus reg:   0x{raw_bus:04X}")
    print(f"  CNVR (ready):  {cnvr}")
    print(f"  OVF (overflow):{ovf}")
    print(f"  Voltage field: {bus_v_field} (13-bit)")
    print(f"  Bus voltage:   {bus_voltage:.4f} V  (field × 4mV)")
    print(f"  Expected 5V:   field should be ~1250 (5.0/0.004)")
    print(f"  Deficit:       {5.0 - bus_voltage:.3f} V")

    # Shunt voltage register: signed 16-bit, 10µV LSB
    raw_shunt = regs[0x01]
    if raw_shunt & 0x8000:
        shunt_signed = raw_shunt - (1 << 16)
    else:
        shunt_signed = raw_shunt
    shunt_voltage = shunt_signed * 10e-6  # 10µV per LSB
    current_from_shunt = shunt_voltage / SHUNT_OHM
    print()
    print(f"  Raw shunt reg: 0x{raw_shunt:04X} (signed: {shunt_signed})")
    print(f"  Shunt voltage: {shunt_voltage*1000:.3f} mV  ({shunt_signed} × 10µV)")
    print(f"  Current (V/R): {current_from_shunt*1000:.1f} mA  (shunt_v / {SHUNT_OHM}Ω)")
    print()

    # The INA219 bus voltage is measured at V- (load side of shunt).
    # V_supply = V_bus + V_shunt
    v_supply = bus_voltage + abs(shunt_voltage)
    print(f"  V_supply = V_bus + |V_shunt| = {bus_voltage:.4f} + {abs(shunt_voltage):.4f} = {v_supply:.4f} V")
    print(f"  (INA219 measures V- not V+ !)")

    # Now do multiple rapid reads to check consistency
    print()
    print("=" * 60)
    print("RAPID SAMPLING (20 reads, no delay)")
    print("=" * 60)
    voltages = []
    currents = []
    for i in range(20):
        v_raw = read_u16(bus, 0x02)
        s_raw = read_u16(bus, 0x01)
        v_field = (v_raw >> 3) & 0x1FFF
        v = v_field * 0.004
        s = s_raw if s_raw < 0x8000 else s_raw - 65536
        c = (s * 10e-6) / SHUNT_OHM
        voltages.append(v)
        currents.append(c)
    print(f"  Voltage: min={min(voltages):.4f}  max={max(voltages):.4f}  avg={sum(voltages)/len(voltages):.4f} V")
    print(f"  Current: min={min(currents)*1000:.1f}  max={max(currents)*1000:.1f}  avg={sum(currents)/len(currents)*1000:.1f} mA")

    # Now let's set calibration register for 3A max current
    # Cal = trunc(0.04096 / (Current_LSB × R_shunt))
    # For 3.2A max: Current_LSB = 3.2 / 32768 = 97.65625 µA
    # Let's use Current_LSB = 100 µA = 0.0001 A for clean math
    # Cal = trunc(0.04096 / (0.0001 × 0.1)) = trunc(0.04096 / 0.00001) = 4096
    print()
    print("=" * 60)
    print("CALIBRATION FOR 3A RANGE")
    print("=" * 60)
    CURRENT_LSB = 0.0001  # 100 µA per bit
    POWER_LSB = 20 * CURRENT_LSB  # per INA219 spec: Power_LSB = 20 × Current_LSB
    CAL_VALUE = int(0.04096 / (CURRENT_LSB * SHUNT_OHM))
    print(f"  Shunt:       {SHUNT_OHM} Ω")
    print(f"  Max current: {CURRENT_LSB * 32768:.1f} A  (Current_LSB × 2^15)")
    print(f"  Current_LSB: {CURRENT_LSB*1e6:.1f} µA/bit")
    print(f"  Power_LSB:   {POWER_LSB*1000:.2f} mW/bit")
    print(f"  Cal value:   {CAL_VALUE} (0x{CAL_VALUE:04X})")

    print(f"\n  Writing calibration register 0x05 = {CAL_VALUE} ...")
    write_u16(bus, 0x05, CAL_VALUE)
    time.sleep(0.01)

    # Also set optimal config:
    # BRNG=1 (32V), PGA=11 (/8, ±320mV for 3A×0.1Ω=300mV),
    # BADC=1100 (12-bit, 128-sample avg for accuracy),
    # SADC=1100 (12-bit, 128-sample avg),
    # Mode=111 (continuous shunt+bus)
    # But for initial diag, let's just use 12-bit single-sample for speed:
    # BRNG=1, PGA=11, BADC=0011 (12-bit), SADC=0011 (12-bit), Mode=111
    # That's: 0 0 1 11 0011 0011 111 = 0x399F (the default!)
    # Let's try 128-sample averaging for higher accuracy:
    # BRNG=1, PGA=11, BADC=1111 (128-avg), SADC=1111 (128-avg), Mode=111
    # = 0 0 1 11 1111 1111 111 = 0x3FFF
    NEW_CONFIG = 0x3FFF
    print(f"  Writing config 0x{NEW_CONFIG:04X} (32V, /8, 128-avg bus+shunt, continuous)...")
    write_u16(bus, 0x00, NEW_CONFIG)
    # 128-sample avg takes ~68ms per conversion
    time.sleep(0.2)

    # Read back
    cfg2 = read_u16(bus, 0x00)
    cal2 = read_u16(bus, 0x05)
    print(f"  Config readback: 0x{cfg2:04X}")
    print(f"  Cal readback:    0x{cal2:04X} ({cal2})")

    print()
    print("=" * 60)
    print("CALIBRATED READINGS (128-sample average)")
    print("=" * 60)
    for i in range(10):
        time.sleep(0.15)  # wait for new averaged conversion
        v_raw = read_u16(bus, 0x02)
        s_raw = read_u16(bus, 0x01)
        c_raw = read_u16(bus, 0x04)  # Current register (uses calibration)
        p_raw = read_u16(bus, 0x03)  # Power register (uses calibration)

        v_field = (v_raw >> 3) & 0x1FFF
        bus_v = v_field * 0.004

        s_signed = s_raw if s_raw < 0x8000 else s_raw - 65536
        shunt_mv = s_signed * 0.01  # 10µV = 0.01mV

        # Current register is signed
        c_signed = c_raw if c_raw < 0x8000 else c_raw - 65536
        current_a = c_signed * CURRENT_LSB

        # Power register is unsigned
        power_w = p_raw * POWER_LSB

        # Manual current from shunt
        manual_current = (s_signed * 10e-6) / SHUNT_OHM

        # Supply voltage = bus + shunt drop
        v_supply = bus_v + abs(s_signed * 10e-6)

        print(f"  [{i:2d}] Bus={bus_v:.4f}V  Shunt={shunt_mv:+.3f}mV  "
              f"I(cal)={current_a*1000:.1f}mA  I(man)={manual_current*1000:.1f}mA  "
              f"P(cal)={power_w*1000:.1f}mW  V_supply={v_supply:.4f}V")

    # Final summary with multiple reads
    print()
    print("=" * 60)
    print("AVERAGED FINAL READING (5 reads)")
    print("=" * 60)
    vsum = 0; isum = 0; psum = 0; vsup = 0
    for _ in range(5):
        time.sleep(0.15)
        v_raw = read_u16(bus, 0x02)
        s_raw = read_u16(bus, 0x01)
        c_raw = read_u16(bus, 0x04)
        p_raw = read_u16(bus, 0x03)
        v_field = (v_raw >> 3) & 0x1FFF
        bus_v = v_field * 0.004
        s_signed = s_raw if s_raw < 0x8000 else s_raw - 65536
        current_a = (c_raw if c_raw < 0x8000 else c_raw - 65536) * CURRENT_LSB
        power_w = p_raw * POWER_LSB
        vsum += bus_v; isum += current_a; psum += power_w
        vsup += bus_v + abs(s_signed * 10e-6)
    vavg = vsum/5; iavg = isum/5; pavg = psum/5; vsup_avg = vsup/5
    print(f"  Bus voltage:    {vavg:.4f} V")
    print(f"  Supply voltage: {vsup_avg:.4f} V  (bus + |shunt|)")
    print(f"  Current:        {iavg*1000:.1f} mA")
    print(f"  Power:          {pavg*1000:.1f} mW")
    print(f"  Power (V×I):    {vavg * abs(iavg) * 1000:.1f} mW")

    if vsup_avg < 4.7:
        print(f"\n  ⚠ WARNING: Supply voltage {vsup_avg:.3f}V is below 4.7V!")
        print(f"    Possible causes:")
        print(f"    - USB-C power supply cannot deliver enough current")
        print(f"    - Long/thin USB cable causing voltage drop")
        print(f"    - INA219 shunt wiring adding extra resistance")
        print(f"    - GPIO header 5V pin has higher drop than USB-C input")
    elif vsup_avg < 5.25:
        print(f"\n  ✓ Supply voltage {vsup_avg:.3f}V is within normal range (4.7-5.25V)")
    else:
        print(f"\n  ⚠ Supply voltage {vsup_avg:.3f}V is above 5.25V")

    # Restore default config for other tools
    print(f"\n  Restoring default config 0x399F...")
    write_u16(bus, 0x00, 0x399F)

    bus.close()
    print("\nDone.")

if __name__ == "__main__":
    main()
