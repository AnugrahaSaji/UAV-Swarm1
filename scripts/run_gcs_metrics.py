#!/usr/bin/env python3
"""
Minimal runner for GCS Metrics Collector.
Usage: python scripts/run_gcs_metrics.py
"""

import sys
import time
import logging
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sscheduler.gcs_metrics import GcsMetricsCollector

def main():
    logging.basicConfig(level=logging.INFO)
    
    # Use the same port as configured in sgcs.py
    SNIFF_PORT = 14552
    
    print(f"Starting GCS Metrics Collector on port {SNIFF_PORT}...")
    print("Note: This script only collects metrics if MAVLink traffic is present on this port.")
    print("      (e.g. if sscheduler.sgcs is running and MAVProxy is forwarding to it)")
    
    collector = GcsMetricsCollector(
        mavlink_host="127.0.0.1",
        mavlink_port=SNIFF_PORT
    )
    
    try:
        collector.start()
        
        # Run for 30 seconds
        for i in range(30):
            time.sleep(1.0)
            if i % 5 == 0:
                print(f"Running... {30-i}s remaining")
                
    except KeyboardInterrupt:
        print("Interrupted")
    finally:
        print("Stopping collector...")
        collector.stop()
        print("Done.")

if __name__ == "__main__":
    main()
