
import sys
import time
import subprocess
import threading
import signal
import os
from pathlib import Path

# Configuration
DRONE_USER = "dev"
DRONE_IP = "100.101.93.23"
DRONE_CMD = "cd ~/secure-tunnel && source ~/cenv/bin/activate && python -m sscheduler.sdrone_bench --interval 10"
GCS_CMD = [sys.executable, "-m", "sscheduler.sgcs_bench"]

def stream_reader(pipe, prefix):
    for line in iter(pipe.readline, ''):
        print(f"[{prefix}] {line.strip()}")
    pipe.close()

def main():
    print(">>> PHASE 4: BENCHMARK EXECUTION LOOP INITIATED <<<")
    
    # 1. Start GCS Server
    print(">>> Starting GCS Benchmark Server...")
    gcs_proc = subprocess.Popen(
        GCS_CMD,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, # Merge stderr
        text=True,
        bufsize=1,
        cwd=str(Path(__file__).parent.parent)
    )
    
    # Start GCS log streamer
    t_gcs = threading.Thread(target=stream_reader, args=(gcs_proc.stdout, "GCS"))
    t_gcs.daemon = True
    t_gcs.start()
    
    # 2. Start Drone Client (SSH)
    print(">>> Waiting 5s for GCS to settle...")
    time.sleep(5)
    
    print(f">>> Starting Drone Benchmark Loop ({DRONE_CMD})...")
    ssh_cmd = ["ssh", f"{DRONE_USER}@{DRONE_IP}", DRONE_CMD]
    drone_proc = subprocess.Popen(
        ssh_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    # Start Drone log streamer
    t_drone = threading.Thread(target=stream_reader, args=(drone_proc.stdout, "DRONE"))
    t_drone.daemon = True
    t_drone.start()
    
    # 3. Wait for Drone to finish
    print(">>> Monitoring execution... (Expect ~12 minutes)")
    try:
        drone_proc.wait()
    except KeyboardInterrupt:
        print(">>> INTERRUPTED! Stopping...")
        drone_proc.terminate()
        gcs_proc.terminate()
        sys.exit(1)
        
    print(f">>> Drone finished with code {drone_proc.returncode}")
    
    # 4. Stop GCS
    print(">>> Stopping GCS Server...")
    gcs_proc.terminate()
    try:
        gcs_proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        gcs_proc.kill()
        
    if drone_proc.returncode == 0:
        print(">>> BENCHMARK EXECUTION SUCCESS <<<")
    else:
        print(">>> BENCHMARK EXECUTION FAILED <<<")
        sys.exit(drone_proc.returncode)

if __name__ == "__main__":
    main()
