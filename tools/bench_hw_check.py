#!/usr/bin/env python3
"""Hardware validation script for benchmark preparation.
Run on the Pi to verify INA219, CPU freq, temperature, and PQC primitives."""

import sys
import os
import time
import json
from pathlib import Path

sys.path.insert(0, os.path.expanduser("~/secure-tunnel"))

def check_cpu():
    print("=" * 50)
    print("CPU FREQUENCY CHECK")
    print("=" * 50)
    with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor") as f:
        gov = f.read().strip()
    with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq") as f:
        cur = int(f.read().strip())
    with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_min_freq") as f:
        mn = int(f.read().strip())
    with open("/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq") as f:
        mx = int(f.read().strip())
    print(f"  Governor: {gov}")
    print(f"  Current:  {cur/1000:.0f} MHz")
    print(f"  Min:      {mn/1000:.0f} MHz")
    print(f"  Max:      {mx/1000:.0f} MHz")
    ok = (gov == "performance" and mn == mx == 1800000)
    print(f"  Status:   {'OK - locked at 1.8GHz' if ok else 'FAIL'}")
    return ok


def check_temperature():
    print("\n" + "=" * 50)
    print("TEMPERATURE CHECK")
    print("=" * 50)
    with open("/sys/class/thermal/thermal_zone0/temp") as f:
        temp = int(f.read().strip()) / 1000
    print(f"  CPU temp: {temp:.1f}°C")
    ok = temp < 65
    print(f"  Status:   {'OK' if ok else 'WARNING - too hot'}")
    return ok


def check_ina219():
    print("\n" + "=" * 50)
    print("INA219 POWER SENSOR CHECK")
    print("=" * 50)
    try:
        from core.metrics_collectors import PowerCollector
        pc = PowerCollector(backend="auto")
        print(f"  Detected backend: {pc.backend}")
        print(f"  INA library:      {pc._ina_backend}")
        if pc.backend == "none":
            print("  Status: FAIL - no power backend available")
            return False

        # Take a single reading
        reading = pc.collect()
        v = reading.get("voltage_v")
        c = reading.get("current_a")
        p = reading.get("power_w")
        err = reading.get("error")
        if err:
            print(f"  Read error: {err}")
            return False
        print(f"  Voltage: {v:.3f} V")
        print(f"  Current: {c:.3f} A  ({c*1000:.1f} mA)")
        print(f"  Power:   {p:.3f} W  ({p*1000:.1f} mW)")

        # Start sampling for 2 seconds at low rate (adafruit needs ~100ms per read)
        pc.start_sampling(rate_hz=10)
        time.sleep(2)
        samples = pc.stop_sampling()
        n = len(samples)
        print(f"  Samples (2s @ 10Hz): {n}")
        if n < 5:
            print("  Status: FAIL - too few samples")
            return False

        valid = [s for s in samples if isinstance(s.get("power_w"), (int, float)) and s["power_w"] > 0.01]
        if valid:
            powers = [s["power_w"] for s in valid]
            avg_p = sum(powers) / len(powers)
            print(f"  Valid power samples: {len(valid)}/{n}")
            print(f"  Power:   min={min(powers):.3f}  avg={avg_p:.3f}  max={max(powers):.3f} W")
            print(f"  Sample rate: ~{n/2:.0f} Hz")
            ok = len(valid) > 2 and max(powers) > 1.0 and max(powers) < 15.0
            if pc._ina_backend == "adafruit":
                print(f"  Note: adafruit backend may drop samples at high Hz (9-bit ADC quirk)")
            print(f"  Status:  {'OK' if ok else 'SUSPICIOUS'}")
            return ok
        else:
            print("  Status: FAIL - no valid power samples")
            return False
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def check_liboqs():
    print("\n" + "=" * 50)
    print("LIBOQS / PQC PRIMITIVES CHECK")
    print("=" * 50)
    try:
        from oqs.oqs import get_enabled_kem_mechanisms, get_enabled_sig_mechanisms
        from oqs.oqs import KeyEncapsulation, Signature as OqsSig
        print(f"  KEMs available: {len(get_enabled_kem_mechanisms())}")
        print(f"  SIGs available: {len(get_enabled_sig_mechanisms())}")
        
        # Quick smoke test: ML-KEM-768 keygen + encaps + decaps
        t0 = time.perf_counter_ns()
        kem = KeyEncapsulation("ML-KEM-768")
        pk = kem.generate_keypair()
        t1 = time.perf_counter_ns()
        ct, ss_enc = kem.encap_secret(pk)  
        t2 = time.perf_counter_ns()
        ss_dec = kem.decap_secret(ct)
        t3 = time.perf_counter_ns()
        
        kg_ms = (t1 - t0) / 1e6
        enc_ms = (t2 - t1) / 1e6
        dec_ms = (t3 - t2) / 1e6
        print(f"  ML-KEM-768: keygen={kg_ms:.3f}ms  encaps={enc_ms:.3f}ms  decaps={dec_ms:.3f}ms")
        assert ss_enc == ss_dec, "Shared secret mismatch!"
        print(f"  Shared secret match: OK ({len(ss_enc)} bytes)")
        
        # Quick SIG test: ML-DSA-65
        sig = OqsSig("ML-DSA-65")
        pk_sig = sig.generate_keypair()
        t0 = time.perf_counter_ns()
        signature = sig.sign(b"benchmark test message")
        t1 = time.perf_counter_ns()
        valid = sig.verify(b"benchmark test message", signature, pk_sig)
        t2 = time.perf_counter_ns()
        sign_ms = (t1 - t0) / 1e6
        ver_ms = (t2 - t1) / 1e6
        print(f"  ML-DSA-65:  sign={sign_ms:.3f}ms  verify={ver_ms:.3f}ms  valid={valid}")
        
        print(f"  Status: OK")
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def check_suites():
    print("\n" + "=" * 50)
    print("CIPHER SUITE REGISTRY CHECK")
    print("=" * 50)
    try:
        from core.suites import SUITES
        print(f"  Total suites: {len(SUITES)}")
        
        # SUITES is a mappingproxy (read-only dict-like)
        suite_list = list(SUITES.values())
        l1 = sum(1 for s in suite_list if getattr(s, 'nist_level', None) == 1)
        l3 = sum(1 for s in suite_list if getattr(s, 'nist_level', None) == 3)
        l5 = sum(1 for s in suite_list if getattr(s, 'nist_level', None) == 5)
        kems = set(getattr(s, 'kem_name', '') for s in suite_list)
        sigs = set(getattr(s, 'sig_name', '') for s in suite_list)
        aeads = set(getattr(s, 'aead_name', '') for s in suite_list)
        print(f"  L1: {l1}  L3: {l3}  L5: {l5}")
        print(f"  KEMs: {len(kems)}  SIGs: {len(sigs)}  AEADs: {len(aeads)}")
        
        ok = len(SUITES) == 72
        print(f"  Status: {'OK' if ok else 'FAIL'}")
        return ok
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def check_keys():
    print("\n" + "=" * 50)
    print("KEY MATERIAL CHECK")
    print("=" * 50)
    key_dir = os.path.expanduser("~/secure-tunnel/secrets/matrix")
    if not os.path.isdir(key_dir):
        print(f"  Key directory not found: {key_dir}")
        print(f"  Status: FAIL")
        return False
    dirs = [d for d in os.listdir(key_dir) if os.path.isdir(os.path.join(key_dir, d))]
    print(f"  Suite key directories: {len(dirs)}")
    # Check a sample
    sample = dirs[0] if dirs else None
    if sample:
        files = os.listdir(os.path.join(key_dir, sample))
        print(f"  Sample ({sample}): {files}")
    ok = len(dirs) >= 72
    print(f"  Status: {'OK' if ok else 'FAIL - need 72 key dirs'}")
    return ok


def check_mavproxy():
    print("\n" + "=" * 50)
    print("MAVPROXY / PIXHAWK CHECK")
    print("=" * 50)
    import subprocess
    # Check if MAVProxy is installed
    try:
        result = subprocess.run(["which", "mavproxy.py"], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"  MAVProxy: {result.stdout.strip()}")
        else:
            print(f"  MAVProxy: not found in PATH")
    except Exception:
        print(f"  MAVProxy: check failed")
    
    # Check /dev/ttyACM0 (Pixhawk)
    if os.path.exists("/dev/ttyACM0"):
        print(f"  Pixhawk: /dev/ttyACM0 present")
    elif os.path.exists("/dev/serial0"):
        print(f"  Pixhawk: /dev/serial0 present")
    else:
        print(f"  Pixhawk: no serial device found (might be /dev/ttyUSB0 or disconnected)")
    return True


if __name__ == "__main__":
    print("PQC BENCHMARK HARDWARE VALIDATION")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Host: {os.uname().nodename}")
    print()
    
    results = {}
    results["cpu"] = check_cpu()
    results["temp"] = check_temperature()
    results["ina219"] = check_ina219()
    results["liboqs"] = check_liboqs()
    results["suites"] = check_suites()
    results["keys"] = check_keys()
    results["mavproxy"] = check_mavproxy()
    
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    all_ok = True
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {name:12s}: {status}")
        if not ok:
            all_ok = False
    
    print(f"\n  Overall: {'ALL CHECKS PASSED' if all_ok else 'SOME CHECKS FAILED'}")
    sys.exit(0 if all_ok else 1)
