#!/bin/bash
echo "=== rpi_volt hwmon ==="
ls -la /sys/class/hwmon/hwmon1/
echo "---"
for f in /sys/class/hwmon/hwmon1/*; do
    fn=$(basename "$f")
    val=$(cat "$f" 2>/dev/null)
    echo "  $fn = $val"
done

echo ""
echo "=== Undervoltage bit check ==="
# Throttled register bits:
# Bit 0: Under-voltage detected
# Bit 1: Arm frequency capped
# Bit 2: Currently throttled
# Bit 3: Soft temperature limit active
# Bit 16: Under-voltage has occurred
# Bit 17: Arm frequency capping has occurred
# Bit 18: Throttling has occurred
# Bit 19: Soft temperature limit has occurred
t=$(vcgencmd get_throttled | cut -d= -f2)
echo "  Raw throttled: $t"
val=$((t))
echo "  Bit 0  (under-voltage now):      $(( (val >> 0) & 1 ))"
echo "  Bit 1  (freq capped now):        $(( (val >> 1) & 1 ))"
echo "  Bit 2  (throttled now):           $(( (val >> 2) & 1 ))"
echo "  Bit 3  (soft temp limit now):     $(( (val >> 3) & 1 ))"
echo "  Bit 16 (under-voltage occurred):  $(( (val >> 16) & 1 ))"
echo "  Bit 17 (freq capped occurred):    $(( (val >> 17) & 1 ))"
echo "  Bit 18 (throttled occurred):      $(( (val >> 18) & 1 ))"
echo "  Bit 19 (soft temp occurred):      $(( (val >> 19) & 1 ))"

echo ""
echo "=== CPU frequency (should be 1800 if no throttling) ==="
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq

echo ""
echo "=== Official PSU detection ==="
# Pi4 detects official PSU via USB-C CC pins
# max_current in device-tree: 5000 = 5A (official), 500/900 = non-official
if [ -f /proc/device-tree/chosen/power/max_current ]; then
    od -An -td4 /proc/device-tree/chosen/power/max_current
else
    echo "  not available"
fi

echo ""
echo "=== USB power info ==="
cat /sys/firmware/devicetree/base/chosen/power/max_current 2>/dev/null | od -An -td4 2>/dev/null || echo "  n/a"
dmesg | grep -i "power supply\|usb.*current\|max_current\|Under-voltage" | tail -10

echo ""
echo "=== INA219 wiring check ==="
# Read raw INA219 regs via python one-liner
source ~/cenv/bin/activate
python3 -c "
from smbus2 import SMBus
bus = SMBus(1)
try: bus.read_byte_data(0x40, 0)
except: pass
# Config
for reg, name in [(0,   'Config'),
                  (1, 'Shunt_V'),
                  (2,   'Bus_V'),
                  (3,   'Power'),
                  (4, 'Current'),
                  (5,   'Calib')]:
    for a in range(3):
        try:
            w = bus.read_word_data(0x40, reg)
            v = ((w&0xFF)<<8)|((w>>8)&0xFF)
            if v == 0 and a < 2 and reg in (0,2): continue
            break
        except OSError:
            v = None
    if v is not None:
        if reg == 0:
            brng = (v>>13)&1
            pga = (v>>11)&3
            badc = (v>>7)&0xf
            sadc = (v>>3)&0xf
            mode = v&7
            print(f'  {name:>8s}: 0x{v:04X}  BRNG={brng}({\\'32V\\' if brng else \\'16V\\'}) PGA=/{1<<pga} BADC={badc} SADC={sadc} Mode={mode}')
        elif reg == 1:
            s = v if v < 0x8000 else v - 65536
            print(f'  {name:>8s}: 0x{v:04X}  = {s*0.01:+.2f} mV  (sign={\\\"NEG\\\" if s<0 else \\\"POS\\\"})')
        elif reg == 2:
            vbus = ((v>>3)&0x1FFF)*0.004
            cnvr = (v>>1)&1
            ovf = v&1
            print(f'  {name:>8s}: 0x{v:04X}  = {vbus:.3f} V  CNVR={cnvr} OVF={ovf}')
        else:
            print(f'  {name:>8s}: 0x{v:04X}  ({v})')
    else:
        print(f'  {name:>8s}: READ ERROR')
bus.close()
"
