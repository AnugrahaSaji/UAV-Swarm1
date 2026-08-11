#!/usr/bin/env python3
"""Environment check - Step 2, 3, 4 of benchmarking phase."""
import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

print("=== PYTHON ENV ===")
print(f"Python: {sys.version}")

print("\n=== OQS CHECK ===")
try:
    import oqs
    kems = oqs.get_enabled_KEM_mechanisms()
    sigs = oqs.get_enabled_sig_mechanisms()
    print(f"OQS KEMs available: {len(kems)}")
    print(f"OQS Sigs available: {len(sigs)}")
    print("OQS OK")
except Exception as e:
    print(f"OQS ERROR: {e}")

print("\n=== SUITES REGISTRY ===")
try:
    from core.suites import list_suites, list_scheduler_approved_suites
    suites = list_suites()
    approved = list_scheduler_approved_suites()
    print(f"Total suites: {len(suites)}")
    print(f"Scheduler-approved suites: {len(approved)}")
    for s in suites:
        marker = " [APPROVED]" if any(a.suite_id == s.suite_id for a in approved) else ""
        print(f"  {s.suite_id}: {s.kem_algorithm} x {s.sig_algorithm}{marker}")
except Exception as e:
    print(f"SUITES ERROR: {e}")

print("\n=== AEAD SUPPORT ===")
AEAD_CANDIDATES = [
    "chacha20poly1305",
    "ascon128",
    "aesgcm128",
    "aesgcm192",
    "aesgcm256",
    "aesccm128",
    "aesccm192",
    "aesccm256",
]

try:
    from core.aead import get_aead_cipher, required_key_length_for_aead
    for name in AEAD_CANDIDATES:
        try:
            key_len = required_key_length_for_aead(name)
            key = bytes(key_len)
            nonce = bytes(12)
            cipher = get_aead_cipher(name, key, nonce)
            ct, tag = cipher.encrypt(b"test" * 256)
            pt = cipher.decrypt(ct, tag)
            status = "SUPPORTED" if pt == b"test" * 256 else "DECRYPT-FAIL"
        except Exception as ex:
            status = f"UNSUPPORTED ({ex.__class__.__name__})"
        print(f"  {name}: {status}")
except Exception as e:
    print(f"AEAD MODULE ERROR: {e}")
    # Fallback: try raw import
    import importlib
    for name in AEAD_CANDIDATES:
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            status = "cryptography lib available"
        except Exception:
            status = "cryptography lib missing"
        print(f"  Fallback check: {status}")
        break
