import sys
import os
from pathlib import Path
import subprocess

# Add project root to path
sys.path.insert(0, os.getcwd())

from core.suites import SUITES

def main():
    matrix_dir = Path("secrets/matrix")
    matrix_dir.mkdir(parents=True, exist_ok=True)

    print(f"Regenerating keys for {len(SUITES)} suites...")

    for suite_id, suite in SUITES.items():
        print(f"Processing {suite_id}...")
        suite_dir = matrix_dir / suite_id
        suite_dir.mkdir(exist_ok=True)
        
        # Run init-identity
        cmd = [
            sys.executable, "-m", "core.run_proxy", "init-identity",
            "--suite", suite_id,
            "--output-dir", str(suite_dir)
        ]
        
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            print(f"  [OK] {suite_id}")
        except subprocess.CalledProcessError as e:
            print(f"  [FAIL] {suite_id}")
            print(e.stderr.decode())

if __name__ == "__main__":
    main()
