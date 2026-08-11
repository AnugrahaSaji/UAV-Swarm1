#!/bin/bash
echo "=== HWMON DEVICES ==="
for h in /sys/class/hwmon/hwmon*; do
  n=$(cat "$h/name" 2>/dev/null)
  echo "HWMON|${h}|${n}"
  ls "$h/" | grep -E "in[0-9]|curr|power|temp|volt" | tr '\n' ',' ; echo
done
echo "=== VCGENCMD PMIC ==="
vcgencmd pmic_read_adc 2>&1 | head -30
echo "=== VCGENCMD VOLTS ==="
vcgencmd measure_volts core 2>&1
vcgencmd measure_volts sdram_c 2>&1
vcgencmd measure_temp 2>&1
echo "=== DONE ==="
