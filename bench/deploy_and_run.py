#!/usr/bin/env python3
"""
Benchmark Deployment & Execution Script

This script:
1. Commits and pushes changes to Git
2. SSHs to drone via Tailscale to pull changes
3. Starts benchmark on both sides

Usage:
    python -m bench.deploy_and_run --test    # Test with 2 suites
    python -m bench.deploy_and_run           # Full benchmark (all suites)

Network Configuration:
    SSH to drone: dev@100.101.93.23 (Tailscale)
    Benchmark traffic: 192.168.0.101 <-> 192.168.0.105 (LAN)
"""

import os
import sys
import time
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]

# =============================================================================
# Network Configuration — read from environment (.denv/.genv)
# =============================================================================

# Tailscale - SSH/Git management ONLY
DRONE_TAILSCALE_IP = os.environ.get("DRONE_HOST_TAILSCALE", "100.101.93.23")
DRONE_SSH_USER = os.environ.get("DRONE_SSH_USER", "dev")

# LAN - Benchmark traffic ONLY
GCS_LAN_IP = os.environ.get("GCS_HOST_LAN", "192.168.0.101")
DRONE_LAN_IP = os.environ.get("DRONE_HOST_LAN", "192.168.0.105")

# Paths
DRONE_PROJECT_PATH = os.environ.get("DRONE_PROJECT_PATH", "~/secure-tunnel")
DRONE_VENV = os.environ.get("DRONE_VENV_PATH", "cenv").rstrip("/").split("/")[-1]

# =============================================================================
# Helpers
# =============================================================================

def log(msg: str, level: str = "INFO"):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    print(f"[{ts}] [{level}] {msg}", flush=True)

def run_local(cmd: str, capture: bool = False) -> tuple:
    """Run command locally."""
    log(f"LOCAL: {cmd}")
    result = subprocess.run(cmd, shell=True, capture_output=capture, text=True)
    if capture:
        return result.returncode, result.stdout, result.stderr
    return result.returncode, "", ""

def run_ssh(cmd: str, capture: bool = False) -> tuple:
    """Run command on drone via Tailscale SSH."""
    ssh_cmd = f'ssh {DRONE_SSH_USER}@{DRONE_TAILSCALE_IP} "{cmd}"'
    log(f"SSH: {cmd}")
    result = subprocess.run(ssh_cmd, shell=True, capture_output=capture, text=True)
    if capture:
        return result.returncode, result.stdout, result.stderr
    return result.returncode, "", ""

# =============================================================================
# Deployment Steps
# =============================================================================

def check_drone_connectivity() -> bool:
    """Check if drone is reachable via Tailscale."""
    log("Checking drone connectivity via Tailscale...")
    code, stdout, _ = run_ssh("echo 'SSH OK' && hostname", capture=True)
    if code == 0:
        log(f"Drone reachable: {stdout.strip()}")
        return True
    log("Drone not reachable via Tailscale SSH", "ERROR")
    return False

def check_lan_connectivity() -> bool:
    """Check if GCS can reach drone on LAN."""
    log(f"Checking LAN connectivity ({GCS_LAN_IP} -> {DRONE_LAN_IP})...")
    # Use PowerShell Test-Connection
    code, stdout, _ = run_local(
        f'Test-Connection -ComputerName {DRONE_LAN_IP} -Count 2 -Quiet',
        capture=True
    )
    if "True" in stdout or code == 0:
        log("LAN connectivity OK")
        return True
    log("LAN connectivity FAILED - check network", "ERROR")
    return False

def git_commit_push() -> bool:
    """Commit changes and push to remote."""
    log("Checking for Git changes...")
    
    # Check status
    code, stdout, _ = run_local("git status --porcelain", capture=True)
    if stdout.strip():
        log(f"Changes detected:\n{stdout}")
        
        # Add all changes
        run_local("git add -A")
        
        # Commit
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        msg = f"benchmark: add LAN benchmark scripts {timestamp}"
        code, _, _ = run_local(f'git commit -m "{msg}"')
        if code != 0:
            log("Commit failed", "ERROR")
            return False
    else:
        log("No changes to commit")
    
    # Push
    log("Pushing to remote...")
    code, _, stderr = run_local("git push", capture=True)
    if code != 0:
        log(f"Push failed: {stderr}", "ERROR")
        return False
    
    log("Push successful")
    return True

def sync_drone() -> bool:
    """Sync drone with Git remote."""
    log("Syncing drone with Git...")
    
    # Pull on drone
    cmd = f"cd {DRONE_PROJECT_PATH} && git pull"
    code, stdout, stderr = run_ssh(cmd, capture=True)
    if code != 0:
        log(f"Git pull failed: {stderr}", "ERROR")
        return False
    
    log(f"Drone sync: {stdout.strip()}")
    return True

def start_gcs_server(run_id: str) -> subprocess.Popen:
    """Start GCS benchmark server locally."""
    log("Starting GCS benchmark server...")
    
    cmd = [
        sys.executable, "-m", "bench.lan_benchmark_gcs",
        "--run-id", run_id,
        "--bind", "0.0.0.0"
    ]
    
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    
    # Wait for server to start
    time.sleep(3)
    
    if proc.poll() is None:
        log("GCS server started")
        return proc
    else:
        log("GCS server failed to start", "ERROR")
        return None

def start_drone_benchmark(run_id: str, max_suites: int = None) -> bool:
    """Start drone benchmark controller via SSH."""
    log("Starting drone benchmark controller...")
    
    # Build command
    drone_cmd = (
        f"cd {DRONE_PROJECT_PATH} && "
        f"source {DRONE_VENV}/bin/activate && "
        f"python -m bench.lan_benchmark_drone "
        f"--run-id {run_id} "
        f"--gcs-host {GCS_LAN_IP}"
    )
    
    if max_suites:
        drone_cmd += f" --max-suites {max_suites}"
    
    # Run via SSH (this blocks until benchmark completes)
    code, stdout, stderr = run_ssh(drone_cmd, capture=True)
    
    print(stdout)
    if stderr:
        print(stderr, file=sys.stderr)
    
    return code == 0

def fetch_results(run_id: str) -> bool:
    """Fetch benchmark results from drone via SCP."""
    log("Fetching results from drone...")
    
    remote_path = f"{DRONE_PROJECT_PATH}/logs/lan_benchmark/{run_id}/"
    local_path = ROOT / "logs" / "lan_benchmark" / run_id
    local_path.mkdir(parents=True, exist_ok=True)
    
    # Use SCP to fetch
    scp_cmd = f'scp -r {DRONE_SSH_USER}@{DRONE_TAILSCALE_IP}:{remote_path}* "{local_path}/"'
    code, _, _ = run_local(scp_cmd, capture=True)
    
    if code == 0:
        log(f"Results fetched to: {local_path}")
        return True
    else:
        log("SCP failed - results remain on drone", "WARN")
        return False

# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Deploy and Run LAN Benchmark")
    parser.add_argument("--test", action="store_true",
                        help="Test mode - run only 2 suites")
    parser.add_argument("--max-suites", type=int, default=None,
                        help="Maximum suites to benchmark")
    parser.add_argument("--skip-sync", action="store_true",
                        help="Skip Git sync (use existing code)")
    parser.add_argument("--run-id", default=None,
                        help="Run ID (default: timestamp)")
    args = parser.parse_args()
    
    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    max_suites = args.max_suites or (2 if args.test else None)
    
    print("=" * 70)
    print("PQC BENCHMARK DEPLOYMENT & EXECUTION")
    print("=" * 70)
    print(f"Run ID: {run_id}")
    print(f"Test mode: {args.test}")
    print(f"Max suites: {max_suites or 'ALL'}")
    print()
    print("NETWORK CONFIGURATION:")
    print(f"  SSH (Tailscale): {DRONE_SSH_USER}@{DRONE_TAILSCALE_IP}")
    print(f"  Benchmark (LAN): {GCS_LAN_IP} <-> {DRONE_LAN_IP}")
    print()
    
    # Step 1: Check connectivity
    log("=" * 50)
    log("STEP 1: Checking connectivity")
    log("=" * 50)
    
    if not check_drone_connectivity():
        return 1
    
    if not check_lan_connectivity():
        log("WARNING: LAN check failed - benchmark may not work", "WARN")
        # Continue anyway - might be firewall on ping
    
    # Step 2: Sync code
    if not args.skip_sync:
        log("=" * 50)
        log("STEP 2: Syncing code")
        log("=" * 50)
        
        if not git_commit_push():
            return 1
        
        if not sync_drone():
            return 1
    else:
        log("Skipping Git sync (--skip-sync)")
    
    # Step 3: Start GCS server
    log("=" * 50)
    log("STEP 3: Starting GCS benchmark server")
    log("=" * 50)
    
    gcs_proc = start_gcs_server(run_id)
    if not gcs_proc:
        return 1
    
    try:
        # Step 4: Run benchmark
        log("=" * 50)
        log("STEP 4: Running benchmark on drone")
        log("=" * 50)
        
        success = start_drone_benchmark(run_id, max_suites)
        
        # Step 5: Fetch results
        log("=" * 50)
        log("STEP 5: Fetching results")
        log("=" * 50)
        
        fetch_results(run_id)
        
        print()
        print("=" * 70)
        print("BENCHMARK COMPLETE" if success else "BENCHMARK FAILED")
        print("=" * 70)
        print(f"Run ID: {run_id}")
        print(f"Results: logs/lan_benchmark/{run_id}/")
        
        return 0 if success else 1
        
    finally:
        # Cleanup - stop GCS server
        if gcs_proc and gcs_proc.poll() is None:
            log("Stopping GCS server...")
            gcs_proc.terminate()
            gcs_proc.wait(timeout=5)

if __name__ == "__main__":
    sys.exit(main())
