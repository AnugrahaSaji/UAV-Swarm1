import json
from ingest import get_store

store = get_store()

print("=" * 75)
print(" 1. BACKEND HEALTH & METRICS STORE SUMMARY")
print("=" * 75)
print(f"• Total Loaded Suites : {store.suite_count}")
print(f"• Total Benchmark Runs: {store.run_count}")

runs = store.list_runs()
print("\nBenchmark Runs Discovered:")
for r in runs:
    print(f"  - Run ID: {r.run_id} | Scenario: {r.scenario_folder} | Type: {r.run_type}")

print("\n" + "=" * 75)
print(" 2. SAMPLE BENCHMARK TEST DATA ENTRY (Ingested by Dashboard)")
print("=" * 75)

suites = store.list_suites()
if suites:
    sample_summary = suites[0]
    print("Suite Summary (Used for Dashboard Table View):")
    print(json.dumps(sample_summary.model_dump(), indent=2))

    full_suite = store.get_suite(sample_summary.suite_id)
    if full_suite:
        print("\nFull Comprehensive Metrics Breakdown (Used for Detail View):")
        detail = {
            "Run Context": {
                "run_id": full_suite.run_context.run_id,
                "suite_id": full_suite.run_context.suite_id,
                "drone_host": full_suite.run_context.drone_hostname,
                "gcs_host": full_suite.run_context.gcs_hostname
            },
            "Cryptographic Suite": {
                "KEM": full_suite.crypto_identity.kem_algorithm,
                "Signature": full_suite.crypto_identity.sig_algorithm,
                "AEAD Encryption": full_suite.crypto_identity.aead_algorithm,
                "NIST Security Level": full_suite.crypto_identity.suite_security_level
            },
            "Handshake Performance": {
                "Success": full_suite.handshake.handshake_success,
                "Handshake Duration (ms)": full_suite.handshake.handshake_total_duration_ms,
                "Rekey Count": full_suite.handshake.rekey_count
            },
            "Network Data Plane": {
                "Throughput (Mbps)": full_suite.data_plane.achieved_throughput_mbps,
                "Goodput (Mbps)": full_suite.data_plane.goodput_mbps,
                "Packet Loss Ratio": full_suite.data_plane.packet_loss_ratio
            },
            "Power & Energy (Drone Sensor)": {
                "Sensor Type": full_suite.power_energy.power_sensor_type,
                "Average Power (W)": full_suite.power_energy.power_avg_w,
                "Total Energy (Joules)": full_suite.power_energy.energy_total_j
            },
            "Drone System Resources": {
                "CPU Utilization (%)": full_suite.system_drone.cpu_util_avg_pct,
                "RAM Used (MB)": full_suite.system_drone.ram_util_avg_mb,
                "CPU Temp (°C)": full_suite.system_drone.cpu_temp_avg_c
            }
        }
        print(json.dumps(detail, indent=2))

print("\n" + "=" * 75)
print(" 3. COMPARISON TEST DATA (Suite A vs Suite B)")
print("=" * 75)
if len(suites) >= 2:
    suite_a = store.get_suite(suites[0].suite_id)
    suite_b = store.get_suite(suites[1].suite_id)
    
    diff_hs = suite_a.handshake.handshake_total_duration_ms - suite_b.handshake.handshake_total_duration_ms
    diff_pwr = suite_a.power_energy.power_avg_w - suite_b.power_energy.power_avg_w
    
    comparison = {
        "Suite A": f"{suite_a.crypto_identity.kem_algorithm} + {suite_a.crypto_identity.sig_algorithm}",
        "Suite B": f"{suite_b.crypto_identity.kem_algorithm} + {suite_b.crypto_identity.sig_algorithm}",
        "Handshake Latency Comparison": {
            "Suite A Latency": f"{suite_a.handshake.handshake_total_duration_ms} ms",
            "Suite B Latency": f"{suite_b.handshake.handshake_total_duration_ms} ms",
            "Latency Difference": f"{round(diff_hs, 2)} ms"
        },
        "Power Draw Comparison": {
            "Suite A Power": f"{suite_a.power_energy.power_avg_w} W",
            "Suite B Power": f"{suite_b.power_energy.power_avg_w} W",
            "Power Difference": f"{round(diff_pwr, 2)} W"
        }
    }
    print(json.dumps(comparison, indent=2))
