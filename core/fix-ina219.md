# INA219 Configuration & Code Guide — Plug-and-Play Sensor Reuse

How the INA219 power sensor works in this project, what went wrong, how we
fixed it, and how to reuse it in any future project without repeating the
debugging.

---

## 1. Hardware Setup

```
Raspberry Pi 4 Model B
│
├── GPIO Pin 3 (SDA1) ──┐
├── GPIO Pin 5 (SCL1) ──┤
├── GPIO Pin 1 (3.3V) ──┤── INA219 Breakout
└── GPIO Pin 6 (GND) ───┘
                              │
                         0.1Ω shunt resistor (onboard)
                              │
                    VIN+ ─────┤───── 5V supply rail
                    VIN- ─────┘
```

- **I2C bus**: 1 (default RPi)
- **I2C address**: 0x40 (A0=A1=GND, default)
- **Shunt resistor**: 0.1 Ω (onboard the breakout)
- **Measurement**: board-level power (CPU + DRAM + GPU + I/O)

### Quick Check

```bash
sudo apt install i2c-tools
i2cdetect -y 1
# Should show "40" at row 0x40
```

---

## 2. The Clone Chip Problem

Our INA219 is a **counterfeit/clone chip**. It reads registers correctly but
**silently ignores configuration writes**. This means:

| Operation | Real INA219 | Our Clone |
|-----------|------------|-----------|
| Read register | ✓ Works | ✓ Works |
| Write config (reg 0x00) | ✓ Applied | ✗ Silently ignored |
| Write calibration (reg 0x05) | ✓ Applied | ✗ Silently ignored |
| Read-back config after write | Returns new value | Returns old value |

This breaks every standard INA219 library (Adafruit, pi-ina219) because they
all configure bus voltage range, PGA gain, and ADC resolution via register
writes. Our chip ignores all of that and runs in its **power-on defaults**.

### How We Know

```python
import smbus2
bus = smbus2.SMBus(1)

# Read current config
old = bus.read_word_data(0x40, 0x00)
print(f"Before: 0x{old:04X}")       # e.g. 0x9F39

# Write new config
bus.write_word_data(0x40, 0x00, 0x1234)

# Read back
new = bus.read_word_data(0x40, 0x00)
print(f"After:  0x{new:04X}")       # Still 0x9F39 ← unchanged!
```

---

## 3. BCM2835/BCM2711 I2C Quirks

The RPi 4's I2C controller (BCM2711, same design as BCM2835) has two known
issues that affect INA219 reads:

### Quirk 1: First Transaction After Open Fails

```python
bus = smbus2.SMBus(1)
val = bus.read_byte_data(0x40, 0x00)   # ← EIO or garbage
val = bus.read_byte_data(0x40, 0x00)   # ← works fine
```

**Fix**: Always do a throwaway read immediately after `SMBus(bus_num)`:

```python
self._bus = smbus2.SMBus(bus_num)
try:
    self._bus.read_byte_data(self._addr, 0x00)  # throwaway
except OSError:
    pass  # expected on BCM2835
```

### Quirk 2: Idle Bus Returns Zeros

After the I2C bus has been idle for ~50 ms, the next `read_word_data` often
returns `0x0000` for register 0x00 (config) or register 0x02 (bus voltage).
These are registers that should never legitimately be zero.

**Fix**: Zero-value retry for critical registers:

```python
def _read_u16(self, reg: int) -> int:
    for attempt in range(3):
        try:
            raw = self._bus.read_word_data(self._addr, reg)
            val = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)  # LE→BE swap
            # Retry if zero on a register that shouldn't be zero
            if val == 0 and reg in (0x00, 0x02) and attempt < 2:
                time.sleep(0.001)    # 1 ms settle
                continue
            return val
        except OSError:
            if attempt == 2:
                raise
            time.sleep(0.0005)       # 0.5 ms backoff
    return 0
```

**Important**: The byte-swap `((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)` is
required because `read_word_data()` returns data in LE format but the INA219
sends it in BE format.

---

## 4. VBUS Gain Calibration

The clone chip reads bus voltage ~18% low compared to the actual rail. We
measured the real voltage with a multimeter and derived a correction factor:

| Register Value | Raw Decoded | Actual (multimeter) | Factor |
|---------------|-------------|---------------------|--------|
| 0x2900 → 0x0029 | ~4.22 V | 5.13 V | 1.22 |

The bus voltage formula with correction:

```python
_VBUS_GAIN = float(os.environ.get("INA219_VBUS_GAIN", "1.22"))

def _read_bus_voltage(self) -> float:
    raw = self._read_u16(0x02)
    # INA219: bits [15:3] are the voltage, LSB = 4 mV
    voltage = ((raw >> 3) & 0x1FFF) * 0.004 * self._vbus_gain
    return voltage
```

Without `_VBUS_GAIN`, power calculations would be 18% too low.

---

## 5. Shunt Polarity Auto-Detection

Some boards wire VIN+ and VIN- backwards, yielding negative shunt voltage.
Our code auto-detects this during init:

```python
def _resolve_sign(self) -> int:
    """2-second probe → returns -1 if median shunt voltage < -20 μV."""
    samples = []
    deadline = time.time() + 2.0
    while time.time() < deadline:
        raw = self._read_s16(0x01)       # shunt voltage register
        uv = raw * 10.0                   # LSB = 10 μV
        samples.append(uv)
        time.sleep(0.005)
    median_uv = sorted(samples)[len(samples) // 2]
    return -1 if median_uv < -20.0 else 1
```

All subsequent current reads are multiplied by this sign factor:

```python
def _read_current_voltage(self) -> tuple[float, float]:
    shunt_v = self._read_s16(0x01) * 10e-6 * self._sign
    current_a = shunt_v / self._shunt_ohm
    voltage_v = self._read_bus_voltage()
    return (current_a, voltage_v)
```

---

## 6. Environment Variables

All INA219 parameters are configurable via environment variables. This is the
plug-and-play interface — change these without touching code:

| Variable | Default | Description |
|----------|---------|-------------|
| `INA219_SAMPLE_HZ` | `1000` | Target sample rate (actual: ~100–1100 Hz depending on ADC) |
| `INA219_SHUNT_OHM` | `0.1` | Shunt resistance in ohms (printed on breakout board) |
| `INA219_I2C_BUS` | `1` | I2C bus number (`ls /dev/i2c-*`) |
| `INA219_ADDR` | `0x40` | I2C address (depends on A0/A1 pins) |
| `INA219_SIGN_MODE` | `auto` | `auto`, `positive`, or `negative` |
| `INA219_VBUS_GAIN` | `1.22` | Bus voltage correction factor |

### Example: Different shunt + address

```bash
export INA219_SHUNT_OHM=0.01
export INA219_ADDR=0x41
export INA219_VBUS_GAIN=1.0     # genuine chip, no correction needed
python bench_power_aead.py --quick
```

---

## 7. Quick-Start Usage (Plug-and-Play)

### Minimal Power Read

```python
from core.power_monitor import Ina219PowerMonitor
from pathlib import Path

pm = Ina219PowerMonitor(Path("/tmp/readings"), sample_hz=100)

# Single-shot read
current_a, voltage_v = pm._read_current_voltage()
power_w = current_a * voltage_v
print(f"V={voltage_v:.2f}V  I={current_a:.3f}A  P={power_w:.2f}W")
# → V=5.15V  I=0.574A  P=2.96W
```

### Streaming Samples

```python
from core.power_monitor import Ina219PowerMonitor
from pathlib import Path

pm = Ina219PowerMonitor(Path("/tmp/readings"), sample_hz=100)

for sample in pm.iter_samples():
    print(f"t={sample.ts_ns}  V={sample.voltage_v:.2f}  "
          f"I={sample.current_a:.3f}  P={sample.power_w:.2f}")
    # iter_samples() is an infinite generator with tick-scheduled sleep
    # Break when done
```

### Timed Capture with CSV

```python
from core.power_monitor import Ina219PowerMonitor
from pathlib import Path

pm = Ina219PowerMonitor(Path("/tmp/readings"), sample_hz=100)

summary = pm.capture(duration_s=10)
print(f"Avg: {summary.power_avg_w:.3f}W")
print(f"Peak: {summary.power_max_w:.3f}W")
print(f"Energy: {summary.energy_j:.3f}J")
# CSV file written to /tmp/readings/capture_<timestamp>.csv
```

### Background Thread (for concurrent workloads)

This is what `bench_power_aead.py` does internally:

```python
import time, threading
from core.power_monitor import Ina219PowerMonitor
from pathlib import Path

pm = Ina219PowerMonitor(Path("/tmp/readings"), sample_hz=100)
samples = []
running = True

def sampler():
    dt = 1.0 / pm.sample_hz
    next_tick = time.perf_counter()
    while running:
        try:
            current_a, voltage_v = pm._read_current_voltage()
            samples.append((voltage_v, current_a, current_a * voltage_v))
        except OSError:
            pass  # skip failed reads, don't crash
        next_tick += dt
        sl = next_tick - time.perf_counter()
        if sl > 0:
            time.sleep(sl)

t = threading.Thread(target=sampler, daemon=True)
t.start()
time.sleep(0.1)  # settle
# ... your workload here ...
time.sleep(0.1)  # settle
running = False
t.join()

avg_power = sum(s[2] for s in samples) / len(samples)
print(f"Average power during workload: {avg_power:.3f}W")
```

---

## 8. Diagnostic Checklist

When the INA219 isn't working, follow this sequence:

### Step 1: Physical check

```bash
i2cdetect -y 1
# ✓  0x40 appears  →  wiring OK
# ✗  nothing       →  check SDA/SCL/VCC/GND wiring
```

### Step 2: Raw register read

```python
import smbus2
bus = smbus2.SMBus(1)
_ = bus.read_byte_data(0x40, 0x00)   # throwaway (BCM2835 quirk)

config = bus.read_word_data(0x40, 0x00)
shunt  = bus.read_word_data(0x40, 0x01)
bus_v  = bus.read_word_data(0x40, 0x02)
print(f"Config: 0x{config:04X}  Shunt: 0x{shunt:04X}  Bus: 0x{bus_v:04X}")
# Config should be non-zero (e.g. 0x399F)
# Shunt should fluctuate (current flowing)
# Bus should be non-zero (voltage present)
```

### Step 3: Burst read test

Real data read at max speed to verify I2C stability:

```python
import smbus2, time

bus = smbus2.SMBus(1)
_ = bus.read_byte_data(0x40, 0x00)  # throwaway

ok, fail = 0, 0
for _ in range(50):
    try:
        raw = bus.read_word_data(0x40, 0x02)
        val = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)
        v = ((val >> 3) & 0x1FFF) * 0.004
        if 3.0 < v < 6.0:
            ok += 1
        else:
            fail += 1
    except OSError:
        fail += 1

print(f"{ok}/50 valid reads")
# ✓ 45+/50  →  sensor working
# ✗ <30/50  →  wiring issue or dead sensor
```

### Step 4: Verify VBUS gain

```bash
# Measure actual voltage with a multimeter at VIN+ / GND
# Compare with the INA219 decoded value
# Gain = actual_voltage / ina219_decoded_voltage
# Default clone gain ≈ 1.22
```

---

## 9. Common Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `OSError: [Errno 121] Remote I/O error` | First read after open | Throwaway read (see §3) |
| All reads return 0x0000 | Idle bus stale | Retry with 1 ms delay (see §3) |
| Voltage reads ~4.2V instead of ~5.1V | Clone chip gain error | Set `INA219_VBUS_GAIN=1.22` |
| Negative current values | Reversed VIN+/VIN- | Set `INA219_SIGN_MODE=negative` or swap wires |
| Config writes have no effect | Clone chip | Normal — registers are read-only on clones |
| `EIO` during concurrent workload | GIL starvation | Use two-pass methodology (see `process-aead-benchmark.md`) |
| Inconsistent sample rate | ADC profile mismatch | Let auto-selection handle it (based on `sample_hz`) |

---

## 10. Porting to a New Board

To use the same INA219 code on a different SBC (e.g., Jetson, BeagleBone):

1. **Check I2C bus number**: `ls /dev/i2c-*` → set `INA219_I2C_BUS`
2. **Check for BCM quirks**: If NOT RPi, the throwaway read and zero-retry
   may be unnecessary. The code handles this gracefully (retry simply succeeds
   on the first attempt on non-BCM I2C controllers).
3. **Measure VBUS gain**: Use a multimeter, compare with raw decoded value.
   If they match, set `INA219_VBUS_GAIN=1.0`. If not, compute the ratio.
4. **Check shunt value**: Read the resistor markings on your breakout board.
   Common values: 0.1 Ω (most boards), 0.01 Ω (high-current boards).

```bash
# Example: Jetson Nano, bus 0, genuine INA219, 0.01 Ω shunt
export INA219_I2C_BUS=0
export INA219_VBUS_GAIN=1.0
export INA219_SHUNT_OHM=0.01
python -c "from core.power_monitor import Ina219PowerMonitor; \
           from pathlib import Path; \
           pm = Ina219PowerMonitor(Path('/tmp/test'), sample_hz=100); \
           s = next(pm.iter_samples()); \
           print(f'V={s.voltage_v:.2f} I={s.current_a:.3f} P={s.power_w:.2f}')"
```

---

## Files

| File | What |
|------|------|
| `core/power_monitor.py` | `Ina219PowerMonitor` — full implementation |
| `core/_burst_test.py` | I2C burst validation script (47/50 valid) |
| `bench_power_aead.py` | Concurrent power+AEAD benchmark |
| `process-aead-benchmark.md` | How the benchmark was built and run |
| Commit `2244d51` | INA219 fix + BCM2835 hardening |
