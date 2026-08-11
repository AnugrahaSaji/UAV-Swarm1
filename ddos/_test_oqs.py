import sys
sys.path.insert(0, "/home/dev/quantum-safe/liboqs-python")
import oqs
print("oqs version:", oqs.oqs_version())
from oqs.oqs import KeyEncapsulation, Signature
print("KeyEncapsulation:", KeyEncapsulation)
print("Signature:", Signature)
print("OK!")
