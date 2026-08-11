#!/bin/bash
echo "=== vcgencmd voltages ==="
vcgencmd measure_volts core
vcgencmd measure_volts sdram_c  
vcgencmd measure_volts sdram_i
vcgencmd measure_volts sdram_p

echo "=== throttled ==="
vcgencmd get_throttled

echo "=== hwmon sensors ==="
for d in /sys/class/hwmon/hwmon*/; do
    echo "--- $d ---"
    cat "$d/name" 2>/dev/null
    for f in "$d"in*_input "$d"in*_label "$d"curr*_input "$d"temp*_input; do
        [ -f "$f" ] && echo "  $f: $(cat "$f")"
    done
done

echo "=== power supply sysfs ==="
for d in /sys/class/power_supply/*/; do
    echo "--- $d ---"
    cat "$d/uevent" 2>/dev/null
done

echo "=== firmware hwmon ==="
ls /sys/devices/platform/soc/soc:firmware/hwmon/ 2>/dev/null
cat /sys/devices/platform/soc/soc:firmware/hwmon/*/in0_input 2>/dev/null && echo " (PMIC input mV)"

echo "=== USB max current (5=5A official PSU) ==="
cat /proc/device-tree/chosen/power/max_current 2>/dev/null | od -An -td4 2>/dev/null

echo "=== INA219 i2c device ==="
ls -la /sys/bus/i2c/devices/1-0040/ 2>/dev/null || echo "No kernel driver at 1-0040"
ls /sys/bus/i2c/devices/1-*/name 2>/dev/null
for f in /sys/bus/i2c/devices/1-*/name; do
    [ -f "$f" ] && echo "  $f: $(cat "$f")"
done

echo "=== I2C bus info ==="
cat /sys/bus/i2c/devices/i2c-1/name 2>/dev/null

echo "=== Config.txt I2C settings ==="
grep -i 'i2c\|dtoverlay\|dtparam' /boot/config.txt 2>/dev/null || grep -i 'i2c\|dtoverlay\|dtparam' /boot/firmware/config.txt 2>/dev/null

echo "=== Done ==="
