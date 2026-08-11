#!/usr/bin/env python3
"""
Benchmark Data Transfer Script - scripts/transfer_benchmark_data.py

Transfers benchmark data from drone to GCS for consolidated analysis.

Usage (run on GCS):
    python -m scripts.transfer_benchmark_data [--drone-ip IP] [--remote-path PATH]

This script:
1. SSHs into the drone (via Tailscale IP or LAN)
2. Finds the latest benchmark run
3. Copies all JSONL + logs to GCS
4. Optionally merges data for analysis
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path
from datetime import datetime

# Default Drone SSH config
DRONE_TAILSCALE_IP = "100.101.93.23"
DRONE_SSH_USER = "dev"
DRONE_REMOTE_PATH = "~/secure-tunnel/logs/benchmarks"
LOCAL_BENCHMARK_DIR = Path(__file__).parent.parent / "logs" / "benchmarks"

def log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")

def run_ssh_cmd(ip: str, user: str, cmd: str) -> str:
    """Run SSH command and return output."""
    ssh_cmd = ["ssh", f"{user}@{ip}", cmd]
    result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise Exception(f"SSH command failed: {result.stderr}")
    return result.stdout.strip()

def list_remote_benchmarks(ip: str, user: str, remote_path: str) -> list:
    """List benchmark directories on drone."""
    cmd = f"ls -1 {remote_path} 2>/dev/null || echo ''"
    output = run_ssh_cmd(ip, user, cmd)
    if not output:
        return []
    return [d for d in output.split("\n") if d.startswith("bench_")]

def transfer_benchmark(ip: str, user: str, remote_path: str, run_id: str, local_dir: Path):
    """Transfer a benchmark run from drone to GCS using rsync or scp."""
    src = f"{user}@{ip}:{remote_path}/{run_id}/"
    dst = local_dir / run_id
    dst.mkdir(parents=True, exist_ok=True)
    
    # Try rsync first (more efficient)
    try:
        cmd = ["rsync", "-avz", "--progress", src, str(dst) + "/"]
        log(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, timeout=300)
        if result.returncode == 0:
            return True
    except FileNotFoundError:
        pass  # rsync not available
    
    # Fallback to scp
    cmd = ["scp", "-r", src, str(dst)]
    log(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, timeout=300)
    return result.returncode == 0

def main():
    parser = argparse.ArgumentParser(description="Transfer benchmark data from drone to GCS")
    parser.add_argument("--drone-ip", type=str, default=DRONE_TAILSCALE_IP,
                        help=f"Drone SSH IP (default: {DRONE_TAILSCALE_IP})")
    parser.add_argument("--drone-user", type=str, default=DRONE_SSH_USER,
                        help=f"Drone SSH user (default: {DRONE_SSH_USER})")
    parser.add_argument("--remote-path", type=str, default=DRONE_REMOTE_PATH,
                        help=f"Remote benchmark directory (default: {DRONE_REMOTE_PATH})")
    parser.add_argument("--local-dir", type=str, default=str(LOCAL_BENCHMARK_DIR),
                        help=f"Local destination directory")
    parser.add_argument("--run-id", type=str, default=None,
                        help="Specific run ID to transfer (default: latest)")
    parser.add_argument("--list", action="store_true",
                        help="List available benchmarks on drone")
    args = parser.parse_args()
    
    local_dir = Path(args.local_dir)
    local_dir.mkdir(parents=True, exist_ok=True)
    
    log("=" * 60)
    log("BENCHMARK DATA TRANSFER")
    log("=" * 60)
    log(f"Drone: {args.drone_user}@{args.drone_ip}")
    log(f"Remote path: {args.remote_path}")
    log(f"Local dir: {local_dir}")
    
    # List benchmarks
    log("\nFetching benchmark list from drone...")
    try:
        benchmarks = list_remote_benchmarks(args.drone_ip, args.drone_user, args.remote_path)
    except Exception as e:
        log(f"ERROR: Failed to connect to drone: {e}")
        sys.exit(1)
    
    if not benchmarks:
        log("No benchmarks found on drone.")
        sys.exit(0)
    
    log(f"Found {len(benchmarks)} benchmark(s):")
    for b in benchmarks:
        log(f"  - {b}")
    
    if args.list:
        sys.exit(0)
    
    # Select run to transfer
    if args.run_id:
        if args.run_id not in benchmarks:
            log(f"ERROR: Run '{args.run_id}' not found on drone")
            sys.exit(1)
        run_id = args.run_id
    else:
        # Get latest
        run_id = sorted(benchmarks)[-1]
    
    log(f"\nTransferring: {run_id}")
    
    # Transfer
    if transfer_benchmark(args.drone_ip, args.drone_user, args.remote_path, run_id, local_dir):
        log(f"✅ Transfer complete!")
        log(f"Data saved to: {local_dir / run_id}")
        
        # Check for JSONL file
        jsonl_files = list((local_dir / run_id).glob("*.jsonl"))
        if jsonl_files:
            log(f"\nBenchmark data files:")
            for f in jsonl_files:
                log(f"  - {f}")
    else:
        log("❌ Transfer failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()
