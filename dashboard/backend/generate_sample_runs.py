import json
from pathlib import Path
from datetime import datetime

# Resolve repo root relative to backend
backend_dir = Path(__file__).resolve().parent
repo_root = backend_dir.parent.parent
runs_dir = repo_root / "logs" / "benchmarks" / "runs"

scenarios = ["no-ddos", "ddos-xgboost", "ddos-txt"]

suites_def = [
    {
        "suite_id": "ML-KEM-512_ML-DSA-44_ASCON-128",
        "kem": "ML-KEM-512",
        "kem_family": "ML-KEM",
        "kem_nist": "Level 1",
        "sig": "ML-DSA-44",
        "sig_family": "ML-DSA",
        "sig_nist": "Level 1",
        "aead": "ASCON-128",
        "sec_level": "Level 1",
        "base_latency": 12.5,
        "base_power": 3.15,
        "base_tp": 22.4,
    },
    {
        "suite_id": "ML-KEM-768_ML-DSA-65_AES-128-GCM",
        "kem": "ML-KEM-768",
        "kem_family": "ML-KEM",
        "kem_nist": "Level 3",
        "sig": "ML-DSA-65",
        "sig_family": "ML-DSA",
        "sig_nist": "Level 3",
        "aead": "AES-128-GCM",
        "sec_level": "Level 3",
        "base_latency": 18.2,
        "base_power": 3.65,
        "base_tp": 19.8,
    },
    {
        "suite_id": "ML-KEM-1024_ML-DSA-87_AES-256-GCM",
        "kem": "ML-KEM-1024",
        "kem_family": "ML-KEM",
        "kem_nist": "Level 5",
        "sig": "ML-DSA-87",
        "sig_family": "ML-DSA",
        "sig_nist": "Level 5",
        "aead": "AES-256-GCM",
        "sec_level": "Level 5",
        "base_latency": 25.7,
        "base_power": 4.10,
        "base_tp": 16.5,
    },
    {
        "suite_id": "Frodo640-AES_Falcon512_ChaCha20-Poly1305",
        "kem": "Frodo640-AES",
        "kem_family": "FrodoKEM",
        "kem_nist": "Level 1",
        "sig": "Falcon-512",
        "sig_family": "Falcon",
        "sig_nist": "Level 1",
        "aead": "ChaCha20-Poly1305",
        "sec_level": "Level 1",
        "base_latency": 45.1,
        "base_power": 5.20,
        "base_tp": 12.1,
    },
]

run_timestamp = "20260801_190000"

for scenario in scenarios:
    scen_dir = runs_dir / scenario
    scen_dir.mkdir(parents=True, exist_ok=True)
    
    # Latency and loss multiplier depending on DDoS scenario
    mult = 1.0
    if scenario == "ddos-xgboost":
        mult = 1.15
    elif scenario == "ddos-txt":
        mult = 1.45

    for idx, s in enumerate(suites_def):
        suite_id = s["suite_id"]
        
        latency = round(s["base_latency"] * mult, 2)
        power = round(s["base_power"], 2)
        tp = round(s["base_tp"] / mult, 2)
        loss = round(0.001 * mult, 4)


        drone_payload = {
            "run_context": {
                "run_id": run_timestamp,
                "suite_id": suite_id,
                "suite_index": idx + 1,
                "git_commit_hash": "a8f3b9c2",
                "drone_hostname": "raspberrypi-uav1",
                "gcs_hostname": "gcs-station-01",
                "drone_ip": "192.168.1.101",
                "gcs_ip": "192.168.1.100",
                "run_start_time_wall": "2026-08-01T19:00:00Z",
                "run_end_time_wall": "2026-08-01T19:05:00Z",
                "run_start_time_mono": 1000.0,
                "run_end_time_mono": 1300.0
            },
            "crypto_identity": {
                "kem_algorithm": s["kem"],
                "kem_family": s["kem_family"],
                "kem_nist_level": s["kem_nist"],
                "sig_algorithm": s["sig"],
                "sig_family": s["sig_family"],
                "sig_nist_level": s["sig_nist"],
                "aead_algorithm": s["aead"],
                "suite_security_level": s["sec_level"]
            },
            "lifecycle": {
                "suite_selected_time": 1000.5,
                "suite_activated_time": 1001.0,
                "suite_deactivated_time": 1299.0,
                "suite_total_duration_ms": 298500.0,
                "suite_active_duration_ms": 298000.0
            },
            "handshake": {
                "handshake_start_time_drone": 1001.1,
                "handshake_end_time_drone": 1001.1 + (latency / 1000.0),
                "handshake_total_duration_ms": latency,
                "protocol_handshake_duration_ms": round(latency * 0.8, 2),
                "end_to_end_handshake_duration_ms": latency,
                "handshake_success": True,
                "rekey_count": 2
            },
            "data_plane": {
                "achieved_throughput_mbps": tp,
                "goodput_mbps": round(tp * 0.95, 2),
                "packet_loss_ratio": loss,
                "total_packets_sent": 15000,
                "total_packets_received": int(15000 * (1 - loss))
            },
            "latency_jitter": {
                "one_way_latency_valid": True,
                "avg_one_way_latency_ms": round(latency * 0.4, 2),
                "rtt_valid": True,
                "avg_rtt_ms": latency
            },
            "power_energy": {
                "power_sensor_type": "INA219",
                "power_avg_w": power,
                "energy_total_j": round(power * 300.0, 2)
            },
            "system_drone": {
                "cpu_util_avg_pct": round(25.0 * mult, 1),
                "ram_util_avg_mb": 320.0,
                "cpu_temp_avg_c": 42.5
            },
            "validation": {
                "benchmark_pass_fail": "PASS",
                "metric_status": {
                    "ingest": {"status": "valid"},
                    "comprehensive": {"status": "valid"}
                }
            },
            "ingest_status": "valid"
        }

        gcs_payload = {
            "run_context": drone_payload["run_context"],
            "crypto_identity": drone_payload["crypto_identity"],
            "handshake": drone_payload["handshake"],
            "gcs_received_packets": int(15000 * (1 - loss))
        }

        drone_file = scen_dir / f"{run_timestamp}_{suite_id}_drone.json"
        gcs_file = scen_dir / f"{run_timestamp}_{suite_id}_gcs.json"

        with drone_file.open("w", encoding="utf-8") as f:
            json.dump(drone_payload, f, indent=2)

        with gcs_file.open("w", encoding="utf-8") as f:
            json.dump(gcs_payload, f, indent=2)

print("Successfully generated sample benchmark runs across all 3 scenario folders!")
