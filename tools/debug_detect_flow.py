#!/usr/bin/env python3
"""Simulate _detect_backend flow exactly."""
import smbus2, os

busnum = 1
addr = 0x40

print("=== Step 0: _warmup_i2c_bus (opens separate fd) ===")
try:
    wbus = smbus2.SMBus(busnum)
    try:
        wbus.read_byte_data(addr, 0x00)
        print("  Warm-up: OK (no EIO)")
    except OSError as e:
        print(f"  Warm-up: EIO (expected): {e}")
    wbus.close()
    print("  Closed warm-up fd")
except Exception as e:
    print(f"  Warm-up failed: {e}")

print()
print("=== Step 1: smbus2_direct detection (new fd) ===")
try:
    bus = smbus2.SMBus(busnum)
    # warm-up on this fd
    try:
        v = bus.read_byte_data(addr, 0x00)
        print(f"  Inner warm-up: OK val=0x{v:02X}")
    except OSError as e:
        print(f"  Inner warm-up: EIO: {e}")
    
    # 3 retry attempts for read_word_data
    for attempt in range(3):
        try:
            word_le = bus.read_word_data(addr, 0x00)
            raw = ((word_le & 0xFF) << 8) | ((word_le >> 8) & 0xFF)
            print(f"  Attempt {attempt}: OK raw=0x{raw:04X}")
            if raw != 0:
                print(f"  >>> smbus2_direct detection SUCCEEDED")
                break
        except OSError as e:
            print(f"  Attempt {attempt}: FAIL: {e}")
    else:
        print("  >>> smbus2_direct detection FAILED (all retries)")
    
    # Continue reading
    for i in range(3):
        try:
            w = bus.read_word_data(addr, 0x02)
            raw = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
            vbus = ((raw >> 3) & 0x1FFF) * 0.004
            w2 = bus.read_word_data(addr, 0x01)
            raw_sh = ((w2 & 0xFF) << 8) | ((w2 >> 8) & 0xFF)
            if raw_sh & 0x8000:
                raw_sh -= 1 << 16
            current_a = abs(raw_sh * 10e-6 / 0.1)
            print(f"  Read {i}: V={vbus:.3f}V I={current_a:.4f}A")
        except OSError as e:
            print(f"  Read {i}: FAIL {e}")
    bus.close()
except Exception as e:
    print(f"  FAILED: {e}")

print("\nDone.")
