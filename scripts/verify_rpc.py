import time
import sys
import os
# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sscheduler.sdrone import send_gcs_command

print("Testing Chronos Sync RPC...")
try:
    resp = send_gcs_command('chronos_sync', t1=time.time())
    print(f"Response: {resp}")
    if resp.get('status') == 'ok' and 't2' in resp:
        print("SUCCESS: Chronos Sync handshake verified.")
    else:
        print("FAILURE: Invalid response.")
except Exception as e:
    print(f"FAILURE: Exception {e}")
