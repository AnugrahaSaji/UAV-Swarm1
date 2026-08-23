import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.handshake import Signature

def main():
    secrets_dir = Path("secrets")
    secrets_dir.mkdir(exist_ok=True)

    sig = Signature("ML-DSA-65")
    pub_key = sig.generate_keypair()
    priv_key = sig.export_secret_key()

    key_file = secrets_dir / "gcs_signing.key"
    pub_file = secrets_dir / "gcs_signing.pub"

    key_file.write_bytes(priv_key)
    pub_file.write_bytes(pub_key)

    print("Generated persistent ML-DSA-65 keypair:")
    print(f"  Private key: {key_file} ({len(priv_key)} bytes)")
    print(f"  Public key:  {pub_file} ({len(pub_key)} bytes)")

if __name__ == "__main__":
    main()
