#!/bin/bash
# Check all voltage rails and power diagnostics on the Pi

echo "=== VCGENCMD VOLTAGES ==="
vcgencmd measure_volts core
vcgencmd measure_volts sdram_c
vcgencmd measure_volts sdram_i
vcgencmd measure_volts sdram_p

echo ""
echo "=== THROTTLE STATUS ==="
vcgencmd get_throttled

echo ""
echo "=== PMIC ADC ==="
vcgencmd pmic_read_adc 2>&1 || echo "  (pmic_read_adc not available on this Pi)"

echo ""
echo "=== CPU TEMP ==="
vcgencmd measure_temp

echo ""
echo "=== HWMON SENSORS ==="
for d in /sys/class/hwmon/hwmon*/; do
    name=$(cat "${d}name" 2>/dev/null)
    echo "--- $d ($name) ---"
    for pattern in in0_input in1_input in2_input in0_lcrit_alarm curr0_input curr1_input power0_input; do
        f="${d}${pattern}"
        if [ -f "$f" ]; then
            echo "  $pattern = $(cat $f)"
        fi
    done
done

echo ""
echo "=== KERNEL POWER SUPPLY ==="
for ps in /sys/class/power_supply/*/; do
    if [ -d "$ps" ]; then
        name=$(basename "$ps")
        echo "--- $name ---"
        for attr in type voltage_now current_now power_now online status; do
            f="${ps}${attr}"
            if [ -f "$f" ]; then
                echo "  $attr = $(cat $f)"
            fi
        done
    fi
done

echo ""
echo "=== DT OVERLAYS ==="
vcgencmd get_config str 2>&1 | grep -i "i2c\|dtoverlay\|dtparam"

echo ""
echo "=== INA219 CALIBRATION TEST ==="
sudo /home/dev/cenv/bin/python3 -c "
import time, sys

# Test 1: adafruit with different calibrations
try:
    import board, adafruit_ina219
    
    print('--- Adafruit INA219 calibration sweep ---')
    
    configs = [
        ('32V_2A',  'set_calibration_32V_2A'),
        ('32V_1A',  'set_calibration_32V_1A'),
        ('16V_400mA', 'set_calibration_16V_400mA'),
        ('16V_5A',  'set_calibration_16V_5A'),
    ]
    
    for label, method in configs:
        readings = []
        for attempt in range(8):
            try:
                i2c = board.I2C()
                sensor = adafruit_ina219.INA219(i2c)
                getattr(sensor, method)()
                v = sensor.bus_voltage
                sv = sensor.shunt_voltage
                c = sensor.current
                readings.append((v, sv, c))
                i2c.deinit()
            except Exception as e:
                pass
            time.sleep(0.15)
        
        if readings:
            avg_v = sum(r[0] for r in readings) / len(readings)
            avg_sv = sum(r[1] for r in readings) / len(readings)
            avg_c = sum(r[2] for r in readings) / len(readings)
            print(f'  {label:15s}: V_bus={avg_v:.3f}V  V_shunt={avg_sv*1000:.2f}mV  I={avg_c:.1f}mA  ({len(readings)}/8 OK)')
        else:
            print(f'  {label:15s}: ALL READS FAILED')
except Exception as e:
    print(f'  Adafruit test failed: {e}')

print()

# Test 2: pi-ina219 with different shunt values
try:
    from ina219 import INA219
    
    print('--- pi-ina219 shunt calibration sweep ---')
    for shunt in [0.01, 0.05, 0.1, 0.2, 1.0]:
        for attempt in range(5):
            try:
                ina = INA219(shunt_ohms=shunt, max_expected_amps=3.0, address=0x40, busnum=1)
                ina.configure()
                v = ina.voltage()
                c = ina.current()
                p = ina.power()
                sv = ina.shunt_voltage()
                print(f'  shunt={shunt:.2f}ohm: V={v:.3f}V  I={c:.1f}mA  P={p:.1f}mW  Vshunt={sv:.3f}mV')
                break
            except Exception as e:
                if attempt == 4:
                    print(f'  shunt={shunt:.2f}ohm: FAILED - {e}')
            time.sleep(0.3)
except ImportError:
    print('  pi-ina219 not available')
except Exception as e:
    print(f'  pi-ina219 test failed: {e}')
"

echo ""
echo "=== DONE ==="
