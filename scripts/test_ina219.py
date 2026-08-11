#!/usr/bin/env python3
"""Quick INA219 power monitor test."""
import sys
sys.path.insert(0, '/home/dev/secure-tunnel')

from pathlib import Path
from core.power_monitor import Ina219PowerMonitor

print("=== INA219 Power Monitor Test ===")
try:
    pm = Ina219PowerMonitor(output_dir=Path('/tmp'))
    print(f"Sample Rate: {pm.sample_hz} Hz")
    print(f"Sign Factor: {pm.sign_factor}")
    
    # Get a few samples
    samples = list(pm.iter_samples(0.5))  # 0.5 second
    print(f"Collected {len(samples)} samples in 0.5s")
    
    if samples:
        s = samples[-1]
        print(f"Latest: V={s.voltage_v:.3f}V, I={s.current_a:.4f}A, P={s.power_w:.3f}W")
        
        # Calculate average power
        avg_power = sum(s.power_w for s in samples) / len(samples)
        print(f"Avg Power: {avg_power:.3f}W")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
