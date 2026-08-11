from dashboard.backend.ingest import get_store
import json

def test():
    print("--- Testing Ingestion ---")
    store = get_store()
    runs = store.list_runs()
    print(f"Found {len(runs)} runs.")
    
    for r in runs:
        print(f"Run: {r.run_id} | TS: {r.run_start_time_wall} | Suites: {r.suite_count}")

        details = [s for s in store._suites.values() if s.run_context.run_id == r.run_id]
        print(f"  Loaded {len(details)} suites.")
        if details:
            s1 = details[0]
            print(f"  Suite 1 ID: {s1.run_context.suite_id}")
            print(f"  Handshake: {s1.handshake.handshake_total_duration_ms} ms")
            print(f"  KEM: {s1.crypto_identity.kem_algorithm}")
            print(f"  Power Avg: {s1.power_energy.power_avg_w} W") # Test comprehensive merge
            
if __name__ == "__main__":
    test()
