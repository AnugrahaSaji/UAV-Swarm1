#!/usr/bin/env python3
"""
Convert DDoS detector overhead benchmark results into dashboard-compatible
ComprehensiveSuiteMetrics JSON files.

Maps the 3 phases to the 3 dashboard scenario folders:
    baseline.json  →  logs/benchmarks/runs/no-ddos/
    xgb.json       →  logs/benchmarks/runs/ddos-xgboost/
    tst.json       →  logs/benchmarks/runs/ddos-txt/

Each suite gets its own {date}_{time}_{suite_id}_drone.json file.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SRC = None  # Will find latest directory automatically
DEST_ROOT = REPO_ROOT / "logs" / "benchmarks" / "runs"

PHASE_MAP = {
    "baseline.json": "no-ddos",
    "xgb.json":      "ddos-xgboost",
    "tst.json":      "ddos-txt",
}

# ── AEAD lookup from suite_id ────────────────────────────────────────────────

AEAD_MAP = {
    "aesgcm":           "AES-256-GCM",
    "ascon128":         "Ascon-AEAD128",
    "ascon128a":        "ASCON-128a",
    "chacha20poly1305": "ChaCha20-Poly1305",
}

KEM_FAMILY = {
    "classicmceliece": "Classic-McEliece",
    "hqc":             "HQC",
    "mlkem":           "ML-KEM",
}

SIG_FAMILY = {
    "falcon":    "Falcon",
    "mldsa":     "ML-DSA",
    "sphincs":   "SPHINCS+",
}

NIST_LEVEL = {
    "348864":  "L1", "460896": "L3", "8192128": "L5",
    "128":     "L1", "192":    "L3", "256":     "L5",
    "512":     "L1", "768":    "L3", "1024":    "L5",
    "44":      "L2", "65":     "L3", "87":      "L5",
    "128s":    "L1", "192s":   "L3", "256s":    "L5",
}


# ── Unit conversion helpers ──────────────────────────────────────────────────

def _safe_div(val, divisor):
    """Safely divide a value, returning None if val is None."""
    if val is None:
        return None
    return val / divisor


def _us_to_ms(val):
    """Convert microseconds to milliseconds, or None."""
    if val is None:
        return None
    return val / 1000.0


def _us_to_ns(val):
    """Convert microseconds to nanoseconds (int), or None."""
    if val is None:
        return None
    return int(val * 1000)


def _calc_sample_rate(suite_result):
    """Compute effective INA219 sampling rate (Hz) from count/duration."""
    count = suite_result.get("power_samples_count", 0)
    dur = suite_result.get("duration_s", 0)
    if count and dur and dur > 0:
        return round(count / dur, 1)
    return None


def parse_suite_id(suite_id: str):
    """Parse 'cs-mlkem512-aesgcm-falcon512' into components."""
    s = suite_id.removeprefix("cs-")

    # Find AEAD
    aead_key = aead_name = None
    for k, v in AEAD_MAP.items():
        if f"-{k}-" in s:
            aead_key = k
            aead_name = v
            break

    if not aead_key:
        return None

    parts = s.split(f"-{aead_key}-")
    kem_raw = parts[0]    # e.g. "mlkem512" or "classicmceliece348864"
    sig_raw = parts[1]    # e.g. "falcon512" or "sphincs128s"

    # KEM
    kem_family_key = kem_family_name = kem_alg = None
    for k, v in KEM_FAMILY.items():
        if kem_raw.startswith(k):
            kem_family_key = k
            kem_family_name = v
            param = kem_raw[len(k):]
            kem_alg = f"{v}-{param}" if param else v
            break

    # SIG
    sig_family_key = sig_family_name = sig_alg = None
    for k, v in SIG_FAMILY.items():
        if sig_raw.startswith(k):
            sig_family_key = k
            sig_family_name = v
            param = sig_raw[len(k):]
            sig_alg = f"{v}-{param}" if param else v
            break

    # NIST level — use KEM param
    nist = "L1"
    if kem_family_key and kem_raw[len(kem_family_key):]:
        param = kem_raw[len(kem_family_key):]
        nist = NIST_LEVEL.get(param, "L1")

    return {
        "kem_algorithm": kem_alg,
        "kem_family": kem_family_name,
        "kem_nist_level": nist,
        "sig_algorithm": sig_alg,
        "sig_family": sig_family_name,
        "aead_algorithm": aead_name,
        "suite_security_level": nist,
    }


def build_comprehensive(suite_result: dict, run_id: str, suite_index: int,
                         phase_timestamp: str) -> dict:
    """Build a ComprehensiveSuiteMetrics dict from a bench result entry."""

    sid = suite_result["suite_id"]
    crypto = parse_suite_id(sid)
    if crypto is None:
        crypto = {
            "kem_algorithm": suite_result.get("kem"),
            "kem_family": None,
            "kem_nist_level": suite_result.get("nist_level", "L1"),
            "sig_algorithm": suite_result.get("sig"),
            "sig_family": None,
            "aead_algorithm": "",
            "suite_security_level": suite_result.get("nist_level", "L1"),
        }

    mean_ms = suite_result["mean_us"] / 1000.0
    median_ms = suite_result["median_us"] / 1000.0
    p95_ms = suite_result["p95_us"] / 1000.0
    p99_ms = suite_result["p99_us"] / 1000.0
    stdev_ms = suite_result["stdev_us"] / 1000.0

    return {
        "run_context": {
            "run_id": run_id,
            "suite_id": sid,
            "suite_index": suite_index,
            "git_commit_hash": None,
            "git_dirty_flag": None,
            "gcs_hostname": "",
            "drone_hostname": "uavpi",
            "gcs_ip": "",
            "drone_ip": "100.101.93.23",
            "python_env_gcs": "",
            "python_env_drone": "/usr/bin/python3",
            "liboqs_version": "0.14.1-dev",
            "kernel_version_gcs": "",
            "kernel_version_drone": "6.12.47+rpt-rpi-v8",
            "clock_offset_ms": 0.0,
            "clock_offset_method": "none",
            "run_start_time_wall": phase_timestamp,
            "run_end_time_wall": phase_timestamp,
            "run_start_time_mono": 0.0,
            "run_end_time_mono": suite_result.get("duration_s", 10.0),
        },
        "crypto_identity": {
            "kem_algorithm": crypto.get("kem_algorithm") or suite_result.get("kem"),
            "kem_family": crypto.get("kem_family"),
            "kem_nist_level": crypto.get("kem_nist_level", "L1"),
            "sig_algorithm": crypto.get("sig_algorithm") or suite_result.get("sig"),
            "sig_family": crypto.get("sig_family"),
            "aead_algorithm": crypto.get("aead_algorithm", ""),
            "suite_security_level": crypto.get("suite_security_level", "L1"),
        },
        "lifecycle": {
            "suite_selected_time": 0.0,
            "suite_activated_time": 0.0,
            "suite_deactivated_time": 0.0,
            "suite_total_duration_ms": suite_result.get("duration_s", 10.0) * 1000,
            "suite_active_duration_ms": suite_result.get("duration_s", 10.0) * 1000,
        },
        "handshake": {
            "handshake_start_time_drone": 0.0,
            "handshake_end_time_drone": mean_ms / 1000.0,
            "handshake_total_duration_ms": mean_ms,
            "protocol_handshake_duration_ms": mean_ms,
            "end_to_end_handshake_duration_ms": mean_ms,
            "handshake_success": suite_result.get("error") is None,
            "handshake_failure_reason": suite_result.get("error", ""),
            "handshake_median_ms": median_ms,
            "handshake_p95_ms": p95_ms,
            "handshake_p99_ms": p99_ms,
            "handshake_stdev_ms": stdev_ms,
            "handshake_iterations": suite_result.get("iterations", 0),
            "handshake_throughput_hz": suite_result.get("throughput_hz", 0.0),
        },
        "crypto_primitives": {
            # Model fields (ms)
            "kem_keygen_time_ms": _us_to_ms(suite_result.get("build_hello_avg_us")),
            "kem_encapsulation_time_ms": _us_to_ms(suite_result.get("encap_avg_us")),
            "kem_decapsulation_time_ms": _us_to_ms(suite_result.get("decap_avg_us")),
            "signature_sign_time_ms": _us_to_ms(suite_result.get("build_hello_avg_us")),
            "signature_verify_time_ms": _us_to_ms(suite_result.get("parse_verify_avg_us")),
            "total_crypto_time_ms": mean_ms,
            # ns fields
            "kem_encaps_ns": _us_to_ns(suite_result.get("encap_avg_us")),
            "kem_decaps_ns": _us_to_ns(suite_result.get("decap_avg_us")),
            "sig_sign_ns": _us_to_ns(suite_result.get("build_hello_avg_us")),
            "sig_verify_ns": _us_to_ns(suite_result.get("parse_verify_avg_us")),
            # sizes
            "pub_key_size_bytes": suite_result.get("public_key_bytes"),
            "ciphertext_size_bytes": suite_result.get("ciphertext_bytes"),
            "sig_size_bytes": suite_result.get("signature_bytes"),
            "shared_secret_size_bytes": suite_result.get("shared_secret_bytes"),
            # extras (raw per-step timings, µs)
            "build_hello_avg_us": suite_result.get("build_hello_avg_us", 0.0),
            "parse_verify_avg_us": suite_result.get("parse_verify_avg_us", 0.0),
            "encap_avg_us": suite_result.get("encap_avg_us", 0.0),
            "decap_avg_us": suite_result.get("decap_avg_us", 0.0),
            "derive_keys_client_avg_us": suite_result.get("derive_keys_client_avg_us", 0.0),
            "derive_keys_server_avg_us": suite_result.get("derive_keys_server_avg_us", 0.0),
        },
        "rekey": {},
        "data_plane": {
            "achieved_throughput_mbps": None,
            "goodput_mbps": None,
        },
        "latency_jitter": {
            "one_way_latency_avg_ms": None,
            "rtt_avg_ms": mean_ms,
            "rtt_p95_ms": p95_ms,
            "rtt_sample_count": suite_result.get("iterations", 0),
            "rtt_valid": True,
        },
        "mavproxy_drone": {},
        "mavproxy_gcs": {},
        "mavlink_integrity": {},
        "fc_telemetry": {},
        "control_plane": {},
        "system_drone": {
            "cpu_usage_avg_percent": suite_result.get("cpu_avg", 0.0),
            "cpu_usage_peak_percent": suite_result.get("cpu_peak", 0.0),
            "temperature_c": suite_result.get("temp_c", 0.0),
            "load_avg_1m": suite_result.get("load_avg", 0.0),
            "memory_rss_mb": suite_result.get("mem_rss_mb", 0.0),
            "cpu_freq_mhz": suite_result.get("cpu_freq_mhz", 0.0),
        },
        "system_gcs": {},
        "power_energy": {
            "power_sensor_type": "INA219" if suite_result.get("avg_power_mw") else "none",
            "voltage_avg_v": suite_result.get("avg_voltage_v"),
            "current_avg_a": _safe_div(suite_result.get("avg_current_ma"), 1000),
            "power_avg_w": _safe_div(suite_result.get("avg_power_mw"), 1000),
            "power_peak_w": None,
            "energy_total_j": _safe_div(suite_result.get("total_energy_mj"), 1000),
            "energy_per_handshake_j": _safe_div(suite_result.get("avg_energy_mj_per_hs"), 1000),
            "power_sampling_rate_hz": _calc_sample_rate(suite_result),
            # extras (original units for reference)
            "avg_power_mw": suite_result.get("avg_power_mw"),
            "avg_current_ma": suite_result.get("avg_current_ma"),
            "total_energy_mj": suite_result.get("total_energy_mj"),
            "power_samples_count": suite_result.get("power_samples_count", 0),
        },
        "observability": {},
        "validation": {
            "benchmark_pass_fail": "PASS" if suite_result.get("error") is None else "FAIL",
            "metric_status": {},
        },
    }


def main():
    if len(sys.argv) > 1:
        src_dir = Path(sys.argv[1])
    elif DEFAULT_SRC:
        src_dir = DEFAULT_SRC
    else:
        # Auto-find latest bench_ddos_results directory
        results_root = REPO_ROOT / "bench_ddos_results"
        if results_root.exists():
            dirs = sorted([d for d in results_root.iterdir() if d.is_dir()])
            if dirs:
                src_dir = dirs[-1]  # latest by timestamp name
                print(f"  Auto-detected latest: {src_dir.name}")
            else:
                print("ERROR: No result directories in bench_ddos_results/")
                sys.exit(1)
        else:
            print("ERROR: bench_ddos_results/ not found")
            sys.exit(1)

    if not src_dir.exists():
        print(f"ERROR: Source directory not found: {src_dir}")
        sys.exit(1)

    total_files = 0

    for phase_file, folder_name in PHASE_MAP.items():
        phase_path = src_dir / phase_file
        if not phase_path.exists():
            print(f"  SKIP {phase_file} (not found)")
            continue

        phase_data = json.loads(phase_path.read_text(encoding="utf-8"))
        dest = DEST_ROOT / folder_name
        dest.mkdir(parents=True, exist_ok=True)

        # Clear existing files in dest
        for old in dest.glob("*.json"):
            old.unlink()

        timestamp = phase_data.get("timestamp", datetime.now(timezone.utc).isoformat())
        # Build run_id from timestamp: "20260209_090851"
        try:
            dt = datetime.fromisoformat(timestamp)
            run_id = dt.strftime("%Y%m%d_%H%M%S")
        except Exception:
            run_id = "20260209_090851"

        results = phase_data.get("results", [])
        print(f"  {phase_file:20s} → {folder_name:20s}  ({len(results)} suites, run_id={run_id})")

        for idx, suite_result in enumerate(results):
            comp = build_comprehensive(suite_result, run_id, idx, timestamp)
            sid = suite_result["suite_id"]
            filename = f"{run_id}_{sid}_drone.json"
            out_path = dest / filename
            out_path.write_text(
                json.dumps(comp, indent=2, default=str),
                encoding="utf-8"
            )
            total_files += 1

    print(f"\n  Total: {total_files} files written to {DEST_ROOT}")
    print(f"  Scenarios: {', '.join(PHASE_MAP.values())}")


if __name__ == "__main__":
    print("=" * 60)
    print("  DDoS Benchmark → Dashboard Ingest Converter")
    print("=" * 60)
    main()
    print("\n  Done! Start the dashboard to view results.")
