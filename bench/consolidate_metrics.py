#!/usr/bin/env python3
"""
Metrics Consolidator - bench/consolidate_metrics.py

Consolidates benchmark metrics from GCS and Drone into unified results.
Call this after running benchmarks on both sides to merge the data.

Usage:
    python -m bench.consolidate_metrics <run_id> [--drone-host <ip>]

This will:
1. Copy drone metrics from remote drone to local GCS
2. Merge GCS and Drone metrics per suite
3. Generate consolidated results JSON
4. Optionally generate the IEEE report
"""

import os
import sys
import json
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config import CONFIG

# =============================================================================
# Configuration
# =============================================================================

ROOT = Path(__file__).resolve().parents[1]
LOGS_DIR = ROOT / "logs" / "full_benchmark"

DRONE_HOST = str(CONFIG.get("DRONE_HOST", "192.168.0.100"))
DRONE_USER = os.environ.get("DRONE_SSH_USER", "dev")
DRONE_PROJECT_PATH = "~/secure-tunnel"

# =============================================================================
# Utilities
# =============================================================================

def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)

def run_ssh_command(host: str, cmd: str, timeout: int = 30) -> tuple:
    """Run command on remote host via SSH."""
    full_cmd = ["ssh", f"{DRONE_USER}@{host}", cmd]
    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout"
    except Exception as e:
        return -1, "", str(e)

def scp_from_drone(host: str, remote_path: str, local_path: str) -> bool:
    """Copy file from drone to local."""
    full_cmd = ["scp", "-r", f"{DRONE_USER}@{host}:{remote_path}", str(local_path)]
    try:
        result = subprocess.run(full_cmd, capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except Exception as e:
        log(f"SCP error: {e}")
        return False

# =============================================================================
# Metrics Consolidator
# =============================================================================

class MetricsConsolidator:
    """Consolidates metrics from GCS and Drone."""
    
    def __init__(self, run_id: str, drone_host: str = None):
        self.run_id = run_id
        self.drone_host = drone_host or DRONE_HOST
        
        self.local_run_dir = LOGS_DIR / run_id
        self.local_metrics_dir = self.local_run_dir / "metrics"
        self.drone_metrics_dir = self.local_run_dir / "drone_metrics"
        
        if not self.local_run_dir.exists():
            raise FileNotFoundError(f"Run directory not found: {self.local_run_dir}")
    
    def fetch_drone_metrics(self) -> bool:
        """Fetch metrics files from drone."""
        log(f"Fetching metrics from drone ({self.drone_host})...")
        
        remote_path = f"{DRONE_PROJECT_PATH}/logs/full_benchmark/{self.run_id}/metrics/*"
        self.drone_metrics_dir.mkdir(parents=True, exist_ok=True)
        
        if scp_from_drone(self.drone_host, remote_path, str(self.drone_metrics_dir)):
            log(f"Drone metrics copied to: {self.drone_metrics_dir}")
            return True
        else:
            log("Failed to fetch drone metrics")
            return False
    
    def load_metrics_file(self, filepath: Path) -> Optional[Dict[str, Any]]:
        """Load a metrics JSON file."""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except Exception as e:
            log(f"Error loading {filepath}: {e}")
            return None
    
    def consolidate(self) -> Path:
        """Consolidate all metrics into unified results."""
        log("Consolidating metrics...")
        
        # Load existing results (if any)
        results_file = self.local_run_dir / f"benchmark_results_{self.run_id}.json"
        if results_file.exists():
            with open(results_file, 'r') as f:
                base_results = json.load(f)
        else:
            base_results = {
                "run_id": self.run_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "results": []
            }
        
        # Index existing results by suite_id
        results_by_suite = {r["suite_id"]: r for r in base_results.get("results", [])}
        
        # Process GCS metrics
        gcs_metrics = self._load_role_metrics(self.local_metrics_dir, "gcs")
        log(f"Loaded {len(gcs_metrics)} GCS metrics files")
        
        # Process Drone metrics
        drone_metrics = self._load_role_metrics(self.drone_metrics_dir, "drone")
        log(f"Loaded {len(drone_metrics)} Drone metrics files")
        
        # Merge metrics
        all_suite_ids = set(gcs_metrics.keys()) | set(drone_metrics.keys()) | set(results_by_suite.keys())
        
        consolidated_results = []
        for suite_id in sorted(all_suite_ids):
            result = results_by_suite.get(suite_id, {"suite_id": suite_id, "success": True})
            
            # Merge GCS metrics
            if suite_id in gcs_metrics:
                gcs_data = gcs_metrics[suite_id]
                self._merge_gcs_metrics(result, gcs_data)
            
            # Merge Drone metrics
            if suite_id in drone_metrics:
                drone_data = drone_metrics[suite_id]
                self._merge_drone_metrics(result, drone_data)
            
            consolidated_results.append(result)
        
        # Update results
        base_results["results"] = consolidated_results
        base_results["consolidated_at"] = datetime.now(timezone.utc).isoformat()
        base_results["total_suites"] = len(consolidated_results)
        base_results["successful_suites"] = sum(1 for r in consolidated_results if r.get("success"))
        
        # Save consolidated results
        output_file = self.local_run_dir / f"consolidated_results_{self.run_id}.json"
        with open(output_file, 'w') as f:
            json.dump(base_results, f, indent=2)
        
        log(f"Consolidated results saved to: {output_file}")
        return output_file
    
    def _load_role_metrics(self, metrics_dir: Path, role: str) -> Dict[str, Dict[str, Any]]:
        """Load all metrics files for a given role."""
        if not metrics_dir.exists():
            return {}
        
        metrics = {}
        pattern = f"*_{role}.json"
        
        for filepath in metrics_dir.glob(pattern):
            data = self.load_metrics_file(filepath)
            if data:
                # Extract suite_id from filename or data
                suite_id = data.get("run_context", {}).get("suite_id")
                if not suite_id:
                    # Try to extract from filename
                    parts = filepath.stem.split("_")
                    if len(parts) >= 2:
                        suite_id = parts[1]
                
                if suite_id:
                    metrics[suite_id] = data
        
        return metrics
    
    def _merge_gcs_metrics(self, result: Dict[str, Any], gcs_data: Dict[str, Any]):
        """Merge GCS-specific metrics into result."""
        # Handshake timing (GCS side)
        handshake = gcs_data.get("handshake", {})
        if handshake:
            gcs_hs_duration = handshake.get("handshake_total_duration_ms", 0)
            # Use GCS timing if we don't have drone timing
            if gcs_hs_duration > 0 and result.get("handshake_duration_ms", 0) == 0:
                result["handshake_duration_ms"] = gcs_hs_duration
    
    def _merge_drone_metrics(self, result: Dict[str, Any], drone_data: Dict[str, Any]):
        """Merge Drone-specific metrics into result (including power)."""
        # System metrics
        sys_drone = drone_data.get("system_drone", {})
        if sys_drone:
            result["drone_cpu_avg_percent"] = sys_drone.get("cpu_usage_avg_percent", 0)
            result["drone_cpu_peak_percent"] = sys_drone.get("cpu_usage_peak_percent", 0)
            result["drone_memory_rss_mb"] = sys_drone.get("memory_rss_mb", 0)
            result["drone_temperature_c"] = sys_drone.get("temperature_c", 0)
            result["drone_load_avg_1m"] = sys_drone.get("load_avg_1m", 0)
        
        # Power metrics (DRONE ONLY - this is the key difference!)
        power = drone_data.get("power_energy", {})
        if power:
            result["drone_power_avg_w"] = power.get("power_avg_w", 0)
            result["drone_power_peak_w"] = power.get("power_peak_w", 0)
            result["drone_energy_total_j"] = power.get("energy_total_j", 0)
            result["drone_energy_per_handshake_j"] = power.get("energy_per_handshake_j", 0)
        
        # Handshake timing (Drone side - preferred)
        handshake = drone_data.get("handshake", {})
        if handshake:
            drone_hs_duration = handshake.get("handshake_total_duration_ms", 0)
            if drone_hs_duration > 0:
                result["handshake_duration_ms"] = drone_hs_duration
        
        # Crypto identity
        crypto = drone_data.get("crypto_identity", {})
        if crypto:
            result["kem_algorithm"] = crypto.get("kem_algorithm", "")
            result["sig_algorithm"] = crypto.get("sig_algorithm", "")
            result["aead_algorithm"] = crypto.get("aead_algorithm", "")
            result["nist_level"] = crypto.get("suite_security_level", "")
        

# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Consolidate benchmark metrics from GCS and Drone")
    parser.add_argument("run_id", help="Benchmark run ID")
    parser.add_argument("--drone-host", default=None, help=f"Drone IP (default: {DRONE_HOST})")
    parser.add_argument("--skip-fetch", action="store_true", help="Skip fetching from drone")
    parser.add_argument("--generate-report", action="store_true", help="Generate IEEE report after consolidation")
    args = parser.parse_args()
    
    print("=" * 60)
    print("Metrics Consolidator")
    print("=" * 60)
    print(f"Run ID: {args.run_id}")
    print()
    
    try:
        consolidator = MetricsConsolidator(args.run_id, args.drone_host)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1
    
    # Fetch drone metrics
    if not args.skip_fetch:
        if not consolidator.fetch_drone_metrics():
            print("Warning: Could not fetch drone metrics. Proceeding with local data only.")
    
    # Consolidate
    output_file = consolidator.consolidate()
    
    # Generate report
    if args.generate_report:
        from bench.generate_ieee_report import IEEEReportGenerator
        log("Generating IEEE report...")
        generator = IEEEReportGenerator(str(output_file))
        report_file = generator.generate()
        log(f"Report generated: {report_file}")
    
    print("\nConsolidation complete!")
    print(f"Results: {output_file}")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
