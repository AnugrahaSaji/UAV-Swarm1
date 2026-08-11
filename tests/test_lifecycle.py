import sys
import time
import os
import subprocess
from pathlib import Path

# Add root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.process import ManagedProcess

def test_lifecycle():
    print("--- Testing ManagedProcess Lifecycle ---")
    
    # 1. Start a sleeper process
    cmd = [sys.executable, "-c", "import time; print('Child running'); time.sleep(30); print('Child done')"]
    
    print(f"Starting child: {cmd}")
    proc = ManagedProcess(cmd, name="test-sleeper", stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    
    if not proc.start():
        print("FAILED: Could not start process")
        return False
    
    print(f"Child started with PID: {proc.process.pid}")
    
    # 2. Verify running
    time.sleep(1.0)
    if not proc.is_running():
        print("FAILED: Process died immediately")
        stdout, stderr = proc.process.communicate()
        print(f"STDOUT: {stdout}")
        print(f"STDERR: {stderr}")
        return False
    
    print("Child is running...")
    
    # 3. Stop
    print("Stopping child...")
    start_stop = time.time()
    proc.stop()
    duration = time.time() - start_stop
    
    # 4. Verify stopped
    if proc.is_running():
        print("FAILED: Process still running after stop()")
        return False
    
    print(f"Child stopped successfully in {duration:.2f}s")
    return True

if __name__ == "__main__":
    if test_lifecycle():
        print("TEST PASSED")
        sys.exit(0)
    else:
        print("TEST FAILED")
        sys.exit(1)
