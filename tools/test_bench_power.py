#!/usr/bin/env python3
"""Test bench_ddos_v2 PowerMonitor and bench_hw_check."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

print("=== bench_ddos_v2 PowerMonitor ===")
try:
    from bench_ddos_v2 import PowerMonitor
    pm = PowerMonitor()
    print(f"  Available: {pm.available}")
    print(f"  Backend: {pm._backend}")
    r = pm.read_once()
    print(f"  Reading: {r}")
except Exception as e:
    print(f"  FAIL: {e}")
    import traceback; traceback.print_exc()
