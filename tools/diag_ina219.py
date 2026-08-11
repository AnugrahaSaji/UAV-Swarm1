#!/usr/bin/env python3
"""
INA219 Comprehensive Diagnostic — Based on Official Documentation
=================================================================

Tests EVERY I2C access method to identify why smbus2 fails but adafruit works.

INA219 Register Map (from TI datasheet SBOS448G):
  0x00 - Configuration (R/W, default 0x399F after reset)
  0x01 - Shunt Voltage (R, 10uV LSB, signed)
  0x02 - Bus Voltage   (R, 4mV LSB, bits [15:3])
  0x03 - Power          (R)
  0x04 - Current         (R, signed)
  0x05 - Calibration     (R/W)

Reset value: writing 0x8000 to reg 0x00 triggers full reset.

Hypothesis: smbus2 uses I2C_SMBUS ioctl → BCM2711 clock-stretching issue
            Blinka uses I2C_RDWR ioctl → works correctly
"""

import sys
import os
import time
import struct
import traceback

# INA219 constants from TI datasheet
INA219_ADDR     = 0x40
I2C_BUS         = 1
SHUNT_OHMS      = 0.1
MAX_AMPS        = 3.2  # 320mV / 0.1Ω
CONFIG_RESET    = 0x8000
CONFIG_DEFAULT  = 0x399F  # after reset: 32V, gain /8, 12-bit, continuous

REG_CONFIG      = 0x00
REG_SHUNT_V     = 0x01
REG_BUS_V       = 0x02
REG_POWER       = 0x03
REG_CURRENT     = 0x04
REG_CALIBRATION = 0x05

PASS = 0
FAIL = 0


def result(name, ok, detail=""):
    global PASS, FAIL
    tag = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{tag}] {name}" + (f"  — {detail}" if detail else ""))
    return ok


# ─────────────────────────────────────────────────────────
# TEST 1: i2cdetect — can the kernel see the device?
# ─────────────────────────────────────────────────────────
def test_1_i2cdetect():
    """Verify device is visible on the bus."""
    print("\n" + "=" * 60)
    print("TEST 1: Kernel I2C device detection")
    print("=" * 60)

    import subprocess
    try:
        out = subprocess.check_output(
            ["i2cdetect", "-y", "1"], text=True, timeout=5
        )
        found = "40" in out
        result("i2cdetect sees 0x40", found, f"output contains '40': {found}")
        if not found:
            print(out)
    except FileNotFoundError:
        result("i2cdetect binary", False, "not installed")
    except Exception as e:
        result("i2cdetect", False, str(e))


# ─────────────────────────────────────────────────────────
# TEST 2: smbus2 — I2C_SMBUS ioctl path
# ─────────────────────────────────────────────────────────
def test_2_smbus2_smbus_ioctl():
    """Test smbus2 using standard SMBus ioctl (read/write_word_data, read/write_i2c_block_data).
    This is what pi-ina219 & our Ina219PowerMonitor use internally."""
    print("\n" + "=" * 60)
    print("TEST 2: smbus2 — I2C_SMBUS ioctl (standard SMBus)")
    print("=" * 60)

    try:
        import smbus2
        print(f"  smbus2 version: {smbus2.__version__ if hasattr(smbus2, '__version__') else 'unknown'}")
    except ImportError:
        result("smbus2 import", False, "not installed")
        return

    bus = None
    try:
        bus = smbus2.SMBus(I2C_BUS)
        result("SMBus(1) open", True)
    except Exception as e:
        result("SMBus(1) open", False, str(e))
        return

    # 2a: read_word_data (used by Adafruit_GPIO / pi-ina219)
    try:
        val = bus.read_word_data(INA219_ADDR, REG_CONFIG)
        # Byte-swap (SMBus returns little-endian, INA219 is big-endian)
        val = ((val & 0xFF) << 8) | ((val >> 8) & 0xFF)
        result("read_word_data(0x00)", True, f"config = 0x{val:04X}")
    except Exception as e:
        result("read_word_data(0x00)", False, str(e))

    # 2b: read_i2c_block_data (used by our Ina219PowerMonitor)
    try:
        data = bus.read_i2c_block_data(INA219_ADDR, REG_CONFIG, 2)
        val = (data[0] << 8) | data[1]
        result("read_i2c_block_data(0x00, 2)", True, f"config = 0x{val:04X}")
    except Exception as e:
        result("read_i2c_block_data(0x00, 2)", False, str(e))

    # 2c: write_i2c_block_data — reset
    try:
        bus.write_i2c_block_data(INA219_ADDR, REG_CONFIG, [0x80, 0x00])
        time.sleep(0.01)
        result("write_i2c_block_data reset", True)
    except Exception as e:
        result("write_i2c_block_data reset", False, str(e))

    # 2d: read bus voltage register
    try:
        data = bus.read_i2c_block_data(INA219_ADDR, REG_BUS_V, 2)
        val = (data[0] << 8) | data[1]
        voltage = ((val >> 3) & 0x1FFF) * 0.004
        result("read bus voltage", True, f"0x{val:04X} = {voltage:.3f}V")
    except Exception as e:
        result("read bus voltage", False, str(e))

    if bus:
        bus.close()


# ─────────────────────────────────────────────────────────
# TEST 3: smbus2 i2c_msg — I2C_RDWR ioctl path
# ─────────────────────────────────────────────────────────
def test_3_smbus2_i2c_rdwr():
    """Test smbus2 using I2C_RDWR ioctl via i2c_msg.
    This is the SAME ioctl path that Blinka/busio uses!
    If this works but TEST 2 fails, it confirms BCM2711 SMBus ioctl issue."""
    print("\n" + "=" * 60)
    print("TEST 3: smbus2 — I2C_RDWR ioctl (raw I2C messages)")
    print("=" * 60)

    try:
        import smbus2
        from smbus2 import i2c_msg
    except ImportError:
        result("smbus2 i2c_msg import", False, "not available")
        return

    bus = None
    try:
        bus = smbus2.SMBus(I2C_BUS)
    except Exception as e:
        result("SMBus(1) open", False, str(e))
        return

    # 3a: Read config register using I2C_RDWR
    try:
        write = i2c_msg.write(INA219_ADDR, [REG_CONFIG])
        read = i2c_msg.read(INA219_ADDR, 2)
        bus.i2c_rdwr(write, read)
        data = list(read)
        val = (data[0] << 8) | data[1]
        result("i2c_rdwr read config", True, f"config = 0x{val:04X}")
    except Exception as e:
        result("i2c_rdwr read config", False, str(e))

    # 3b: Write reset via I2C_RDWR
    try:
        write = i2c_msg.write(INA219_ADDR, [REG_CONFIG, 0x80, 0x00])
        bus.i2c_rdwr(write)
        time.sleep(0.01)
        result("i2c_rdwr write reset", True)
    except Exception as e:
        result("i2c_rdwr write reset", False, str(e))

    # 3c: Read config after reset (should be 0x399F)
    try:
        write = i2c_msg.write(INA219_ADDR, [REG_CONFIG])
        read = i2c_msg.read(INA219_ADDR, 2)
        bus.i2c_rdwr(write, read)
        data = list(read)
        val = (data[0] << 8) | data[1]
        ok = val == CONFIG_DEFAULT
        result("config after reset", ok, f"0x{val:04X} (expect 0x{CONFIG_DEFAULT:04X})")
    except Exception as e:
        result("config after reset", False, str(e))

    # 3d: Read bus voltage
    try:
        write = i2c_msg.write(INA219_ADDR, [REG_BUS_V])
        read = i2c_msg.read(INA219_ADDR, 2)
        bus.i2c_rdwr(write, read)
        data = list(read)
        val = (data[0] << 8) | data[1]
        voltage = ((val >> 3) & 0x1FFF) * 0.004
        ok = 0.0 <= voltage <= 26.0
        result("bus voltage (i2c_rdwr)", ok, f"{voltage:.3f}V")
    except Exception as e:
        result("bus voltage (i2c_rdwr)", False, str(e))

    # 3e: Read shunt voltage
    try:
        write = i2c_msg.write(INA219_ADDR, [REG_SHUNT_V])
        read = i2c_msg.read(INA219_ADDR, 2)
        bus.i2c_rdwr(write, read)
        data = list(read)
        val = (data[0] << 8) | data[1]
        if val & 0x8000:
            val -= 1 << 16
        shunt_mv = val * 0.01  # 10uV LSB → mV
        result("shunt voltage (i2c_rdwr)", True, f"{shunt_mv:.3f} mV")
    except Exception as e:
        result("shunt voltage (i2c_rdwr)", False, str(e))

    # 3f: Write calibration + configuration, then read current & power
    try:
        # Configure: 16V range, gain /8 (320mV), 12-bit bus & shunt, continuous
        # Config = BRNG=0, PG=11, BADC=0011, SADC=0011, MODE=111
        # = 0b0_0_11_0011_0011_111 = 0x199F
        cfg = 0x199F
        write = i2c_msg.write(INA219_ADDR, [REG_CONFIG, (cfg >> 8) & 0xFF, cfg & 0xFF])
        bus.i2c_rdwr(write)
        time.sleep(0.005)

        # Calibration = trunc(0.04096 / (current_lsb * shunt_ohms))
        # For max_expected_amps=3.2A, current_lsb = 3.2 / 32800 ≈ 9.756e-5
        # Calibration = trunc(0.04096 / (9.756e-5 * 0.1)) = trunc(4198.4) = 4198
        current_lsb = MAX_AMPS / 32800
        cal = int(0.04096 / (current_lsb * SHUNT_OHMS))
        if cal > 0xFFFE:
            cal = 0xFFFE
        write = i2c_msg.write(INA219_ADDR, [REG_CALIBRATION, (cal >> 8) & 0xFF, cal & 0xFF])
        bus.i2c_rdwr(write)
        time.sleep(0.01)  # Wait for first conversion

        result("configure + calibrate (i2c_rdwr)", True, f"cfg=0x{cfg:04X} cal=0x{cal:04X}")

        # Read bus voltage
        write = i2c_msg.write(INA219_ADDR, [REG_BUS_V])
        read = i2c_msg.read(INA219_ADDR, 2)
        bus.i2c_rdwr(write, read)
        data = list(read)
        raw_bus = (data[0] << 8) | data[1]
        bus_v = ((raw_bus >> 3) & 0x1FFF) * 0.004

        # Read shunt voltage
        write = i2c_msg.write(INA219_ADDR, [REG_SHUNT_V])
        read = i2c_msg.read(INA219_ADDR, 2)
        bus.i2c_rdwr(write, read)
        data = list(read)
        raw_shunt = (data[0] << 8) | data[1]
        if raw_shunt & 0x8000:
            raw_shunt -= 1 << 16
        shunt_v = raw_shunt * 10e-6  # V

        # Read current register
        write = i2c_msg.write(INA219_ADDR, [REG_CURRENT])
        read = i2c_msg.read(INA219_ADDR, 2)
        bus.i2c_rdwr(write, read)
        data = list(read)
        raw_current = (data[0] << 8) | data[1]
        if raw_current & 0x8000:
            raw_current -= 1 << 16
        current_a = raw_current * current_lsb

        # Read power register
        write = i2c_msg.write(INA219_ADDR, [REG_POWER])
        read = i2c_msg.read(INA219_ADDR, 2)
        bus.i2c_rdwr(write, read)
        data = list(read)
        raw_power = (data[0] << 8) | data[1]
        power_w = raw_power * current_lsb * 20

        print(f"    Bus Voltage:   {bus_v:.3f} V")
        print(f"    Shunt Voltage: {shunt_v * 1000:.3f} mV")
        print(f"    Current (reg): {current_a * 1000:.1f} mA ({current_a:.4f} A)")
        print(f"    Current (ohm): {shunt_v / SHUNT_OHMS * 1000:.1f} mA")
        print(f"    Power (reg):   {power_w * 1000:.1f} mW ({power_w:.3f} W)")
        print(f"    Power (calc):  {bus_v * current_a * 1000:.1f} mW")

        ok = bus_v > 0 and abs(current_a) > 0.001
        result("full measurement (i2c_rdwr)", ok)
    except Exception as e:
        result("full measurement (i2c_rdwr)", False, str(e))
        traceback.print_exc()

    if bus:
        bus.close()


# ─────────────────────────────────────────────────────────
# TEST 4: Raw /dev/i2c-1 file descriptor (fcntl ioctl)
# ─────────────────────────────────────────────────────────
def test_4_raw_fd():
    """Test raw file descriptor I2C — same as kernel driver path."""
    print("\n" + "=" * 60)
    print("TEST 4: Raw /dev/i2c-1 file descriptor (ioctl)")
    print("=" * 60)

    import fcntl
    I2C_SLAVE = 0x0703

    fd = None
    try:
        fd = os.open("/dev/i2c-1", os.O_RDWR)
        fcntl.ioctl(fd, I2C_SLAVE, INA219_ADDR)
        result("/dev/i2c-1 open + ioctl", True)
    except Exception as e:
        result("/dev/i2c-1 open", False, str(e))
        return

    # Read config register
    try:
        os.write(fd, bytes([REG_CONFIG]))
        time.sleep(0.001)
        data = os.read(fd, 2)
        val = struct.unpack(">H", data)[0]
        result("raw fd read config", True, f"0x{val:04X}")
    except Exception as e:
        result("raw fd read config", False, str(e))

    # Read bus voltage
    try:
        os.write(fd, bytes([REG_BUS_V]))
        time.sleep(0.001)
        data = os.read(fd, 2)
        val = struct.unpack(">H", data)[0]
        voltage = ((val >> 3) & 0x1FFF) * 0.004
        result("raw fd bus voltage", True, f"{voltage:.3f}V")
    except Exception as e:
        result("raw fd bus voltage", False, str(e))

    if fd is not None:
        os.close(fd)


# ─────────────────────────────────────────────────────────
# TEST 5: adafruit_ina219 (official Adafruit example)
# ─────────────────────────────────────────────────────────
def test_5_adafruit():
    """Official Adafruit CircuitPython INA219 example.
    Uses board.I2C() → busio.I2C() → Blinka → I2C_RDWR ioctl."""
    print("\n" + "=" * 60)
    print("TEST 5: adafruit_ina219 (official Adafruit example)")
    print("=" * 60)

    try:
        import board
        from adafruit_ina219 import INA219, ADCResolution, BusVoltageRange
    except ImportError as e:
        result("adafruit import", False, str(e))
        return

    sensor = None
    try:
        i2c = board.I2C()
        sensor = INA219(i2c)
        result("INA219(board.I2C()) init", True)
    except Exception as e:
        result("INA219 init", False, str(e))
        return

    # Display config
    try:
        print(f"    bus_voltage_range:    0x{sensor.bus_voltage_range:X}")
        print(f"    gain:                 0x{sensor.gain:X}")
        print(f"    bus_adc_resolution:   0x{sensor.bus_adc_resolution:X}")
        print(f"    shunt_adc_resolution: 0x{sensor.shunt_adc_resolution:X}")
        print(f"    mode:                 0x{sensor.mode:X}")
        result("read config fields", True)
    except Exception as e:
        result("read config fields", False, str(e))

    # Configure optimal: 32-sample averaging, 16V range
    try:
        sensor.bus_adc_resolution = ADCResolution.ADCRES_12BIT_32S
        sensor.shunt_adc_resolution = ADCResolution.ADCRES_12BIT_32S
        sensor.bus_voltage_range = BusVoltageRange.RANGE_16V
        result("set 32-sample averaging + 16V", True)
    except Exception as e:
        result("set config", False, str(e))

    # Read measurements
    for attempt in range(5):
        try:
            time.sleep(0.1)  # Wait for conversion (~17ms * 2 = 34ms)
            bus_voltage = sensor.bus_voltage
            shunt_voltage = sensor.shunt_voltage
            current = sensor.current      # mA
            power = sensor.power          # watts

            vin_plus = bus_voltage + shunt_voltage
            calc_power = bus_voltage * (current / 1000)

            print(f"    [{attempt + 1}] V+={vin_plus:.3f}V  V-={bus_voltage:.3f}V  "
                  f"Shunt={shunt_voltage:.5f}V  I={current:.1f}mA  "
                  f"P(reg)={power:.3f}W  P(calc)={calc_power:.3f}W")

            if sensor.overflow:
                print(f"    [{attempt + 1}] WARNING: Math overflow detected!")

            if bus_voltage > 0:
                result(f"adafruit read #{attempt + 1}", True,
                       f"V={bus_voltage:.3f}V I={current:.1f}mA P={power:.3f}W")
            else:
                result(f"adafruit read #{attempt + 1}", False, "zero voltage")
        except Exception as e:
            result(f"adafruit read #{attempt + 1}", False, str(e))

    try:
        i2c.deinit()
    except:
        pass


# ─────────────────────────────────────────────────────────
# TEST 6: pi-ina219 (official pi-ina219 example)
# ─────────────────────────────────────────────────────────
def test_6_pi_ina219():
    """Official pi-ina219 library example with debug logging.
    Uses Adafruit_GPIO.I2C → smbus → I2C_SMBUS ioctl."""
    print("\n" + "=" * 60)
    print("TEST 6: pi-ina219 library (with debug logging)")
    print("=" * 60)

    try:
        from ina219 import INA219, DeviceRangeError
        import logging
    except ImportError as e:
        result("pi-ina219 import", False, str(e))
        return

    for attempt in range(3):
        try:
            # Use busnum=1 explicitly (required for RPi4 + Bullseye per README)
            ina = INA219(SHUNT_OHMS, busnum=I2C_BUS, log_level=logging.DEBUG)
            ina.configure()
            v = ina.voltage()
            try:
                c = ina.current()
                p = ina.power()
                sv = ina.shunt_voltage()
                print(f"    V={v:.3f}V  I={c:.2f}mA  P={p:.2f}mW  Shunt={sv:.3f}mV")
                result(f"pi-ina219 attempt #{attempt + 1}", True)
                return
            except DeviceRangeError as e:
                result(f"pi-ina219 attempt #{attempt + 1}", False, f"overflow: {e}")
        except Exception as e:
            result(f"pi-ina219 attempt #{attempt + 1}", False, str(e))
        time.sleep(0.5)


# ─────────────────────────────────────────────────────────
# TEST 7: Continuous sampling rate test
# ─────────────────────────────────────────────────────────
def test_7_sampling_rate():
    """Test sustainable read rate using the working method."""
    print("\n" + "=" * 60)
    print("TEST 7: Continuous sampling rate (i2c_rdwr)")
    print("=" * 60)

    try:
        import smbus2
        from smbus2 import i2c_msg
    except ImportError:
        result("smbus2 import", False)
        return

    bus = smbus2.SMBus(I2C_BUS)

    # Configure with 12-bit, continuous
    cfg = 0x199F  # 16V, gain /8, 12-bit bus+shunt, continuous
    current_lsb = MAX_AMPS / 32800
    cal = int(0.04096 / (current_lsb * SHUNT_OHMS))

    try:
        w = i2c_msg.write(INA219_ADDR, [REG_CONFIG, (cfg >> 8) & 0xFF, cfg & 0xFF])
        bus.i2c_rdwr(w)
        time.sleep(0.005)
        w = i2c_msg.write(INA219_ADDR, [REG_CALIBRATION, (cal >> 8) & 0xFF, cal & 0xFF])
        bus.i2c_rdwr(w)
        time.sleep(0.01)
    except Exception as e:
        result("configure for sampling", False, str(e))
        bus.close()
        return

    # Sample as fast as possible for 2 seconds
    duration = 2.0
    samples = []
    errors = 0
    t0 = time.time()
    while time.time() - t0 < duration:
        try:
            # Read bus voltage
            w = i2c_msg.write(INA219_ADDR, [REG_BUS_V])
            r = i2c_msg.read(INA219_ADDR, 2)
            bus.i2c_rdwr(w, r)
            d = list(r)
            raw_bus = (d[0] << 8) | d[1]
            bus_v = ((raw_bus >> 3) & 0x1FFF) * 0.004

            # Read current register
            w = i2c_msg.write(INA219_ADDR, [REG_CURRENT])
            r = i2c_msg.read(INA219_ADDR, 2)
            bus.i2c_rdwr(w, r)
            d = list(r)
            raw_cur = (d[0] << 8) | d[1]
            if raw_cur & 0x8000:
                raw_cur -= 1 << 16
            current_a = raw_cur * current_lsb

            samples.append((time.time() - t0, bus_v, current_a))
        except Exception:
            errors += 1

    elapsed = time.time() - t0
    rate = len(samples) / elapsed if elapsed > 0 else 0

    print(f"    Duration: {elapsed:.2f}s")
    print(f"    Samples:  {len(samples)} ({errors} errors)")
    print(f"    Rate:     {rate:.1f} Hz")

    if samples:
        voltages = [s[1] for s in samples]
        currents = [abs(s[2]) for s in samples]
        valid = [s for s in samples if s[1] > 0 and abs(s[2]) > 0.001]
        print(f"    Valid:    {len(valid)}/{len(samples)} ({100 * len(valid) / len(samples):.0f}%)")
        print(f"    V range:  {min(voltages):.3f} - {max(voltages):.3f} V")
        print(f"    I range:  {min(currents) * 1000:.1f} - {max(currents) * 1000:.1f} mA")
        if valid:
            avg_v = sum(s[1] for s in valid) / len(valid)
            avg_i = sum(abs(s[2]) for s in valid) / len(valid)
            avg_p = sum(s[1] * abs(s[2]) for s in valid) / len(valid)
            print(f"    Avg:      V={avg_v:.3f}V  I={avg_i * 1000:.1f}mA  P={avg_p:.3f}W")

        ok = len(valid) > len(samples) * 0.8 and rate > 100
        result(f"sampling rate", ok, f"{rate:.0f} Hz, {len(valid)} valid")
    else:
        result("sampling rate", False, "no samples")

    bus.close()


# ─────────────────────────────────────────────────────────
# TEST 8: Check which ioctl the Blinka I2C actually uses
# ─────────────────────────────────────────────────────────
def test_8_blinka_backend():
    """Inspect what I2C backend Blinka is actually using."""
    print("\n" + "=" * 60)
    print("TEST 8: Blinka I2C backend inspection")
    print("=" * 60)

    try:
        import board
        import busio
        i2c = busio.I2C(board.SCL, board.SDA)

        # Check the underlying implementation
        impl = type(i2c).__mro__
        print(f"    I2C class MRO: {[c.__name__ for c in impl]}")

        if hasattr(i2c, '_i2c'):
            inner = i2c._i2c
            print(f"    Inner I2C type: {type(inner).__name__}")
            if hasattr(inner, '_i2c_bus'):
                print(f"    Bus object: {type(inner._i2c_bus).__name__}")

        result("Blinka backend inspection", True)
        i2c.deinit()
    except Exception as e:
        result("Blinka backend", False, str(e))


# ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("INA219 Comprehensive Diagnostic")
    print(f"Python:   {sys.executable}")
    print(f"Platform: {sys.platform}")
    print(f"Time:     {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"PID:      {os.getpid()}")

    test_1_i2cdetect()
    test_2_smbus2_smbus_ioctl()
    test_3_smbus2_i2c_rdwr()
    test_4_raw_fd()
    test_5_adafruit()
    test_6_pi_ina219()
    test_7_sampling_rate()
    test_8_blinka_backend()

    print("\n" + "=" * 60)
    print(f"SUMMARY: {PASS} PASS, {FAIL} FAIL")
    print("=" * 60)

    if FAIL == 0:
        print("ALL TESTS PASSED")
    else:
        print("\nDiagnosis:")
        print("  If TEST 2 (SMBus ioctl) FAILS but TEST 3 (I2C_RDWR) PASSES:")
        print("    → BCM2711 I2C SMBus ioctl issue confirmed")
        print("    → Use I2C_RDWR path (adafruit/blinka or smbus2.i2c_msg)")
        print("    → core/power_monitor.py needs to use i2c_msg instead of")
        print("      write_i2c_block_data / read_i2c_block_data")
        print()
        print("  If BOTH TEST 2 and TEST 3 FAIL:")
        print("    → Hardware wiring issue or I2C bus problem")
        print("    → Check SDA/SCL connections and pull-up resistors")

    sys.exit(1 if FAIL > 0 else 0)
