#!/usr/bin/env python3
"""Check oqs imports."""
import sys
try:
    from oqs.oqs import KeyEncapsulation, Signature
    print("Style 1 OK: oqs.oqs")
    sys.exit(0)
except ImportError as e:
    print(f"Style 1 failed: {e}")

try:
    from oqs import KeyEncapsulation, Signature
    print("Style 2 OK: oqs")
    sys.exit(0)
except ImportError as e:
    print(f"Style 2 failed: {e}")

try:
    import oqs
    print(f"Style 3: oqs module has: {[a for a in dir(oqs) if not a.startswith('_')]}")
    KE = getattr(oqs, 'KeyEncapsulation', None)
    print(f"  KeyEncapsulation: {KE}")
    sys.exit(0)
except ImportError as e:
    print(f"Style 3 failed: {e}")

# Check if liboqs-python is in a different location
import subprocess
result = subprocess.run([sys.executable, '-m', 'pip', 'list'], capture_output=True, text=True)
for line in result.stdout.split('\n'):
    if 'oqs' in line.lower():
        print(f"  pip: {line}")
