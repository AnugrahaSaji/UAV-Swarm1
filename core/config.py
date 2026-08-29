"""
Core configuration constants for PQC drone-GCS secure proxy.

Single source of truth for all network ports, hosts, and runtime parameters.
"""

import os
import sys
from ipaddress import ip_address
from typing import Dict, Any
from core.exceptions import ConfigError

# Load .denv / .genv files (if present) before reading env vars.
# Import is guarded so config.py still works if env_loader isn't available.
try:
    from core.env_loader import load_env_files
    load_env_files()
except ImportError:
    pass

# Baseline host defaults — read from environment (populated by .denv/.genv)
# with hardcoded fallbacks for backward compatibility.
_DRONE_HOST_LAN = os.getenv("DRONE_HOST_LAN", "10.2.142.211")
_DRONE_HOST_TAILSCALE = os.getenv("DRONE_HOST_TAILSCALE", "100.101.93.23")
_GCS_HOST_LAN = os.getenv("GCS_HOST_LAN", "10.2.129.165")
_GCS_HOST_TAILSCALE = os.getenv("GCS_HOST_TAILSCALE", "100.101.93.24")
 
def _resolve_host_defaults() -> tuple[str, str, str]:
    """Resolve default DRONE/GCS hosts from an explicit runtime profile.

    Supported profiles via TUNNEL_HOST_PROFILE:
    - lan (default)
    - tailscale
    - localhost
    """

    raw_profile = os.getenv("TUNNEL_HOST_PROFILE", "lan").strip().lower()
    profile = raw_profile if raw_profile in {"lan", "tailscale", "localhost"} else "lan"

    if profile == "tailscale":
        return _DRONE_HOST_TAILSCALE, _GCS_HOST_TAILSCALE, profile
    if profile == "localhost":
        return "127.0.0.1", "127.0.0.1", profile
    return _DRONE_HOST_LAN, _GCS_HOST_LAN, profile


_DEFAULT_DRONE_HOST, _DEFAULT_GCS_HOST, _HOST_PROFILE = _resolve_host_defaults()

# Environment-sourced default credential — no fallback in source control.
# Set PQC_LAB_PASSWORD in .genv or the environment before running.
_LAB_PASSWORD_DEFAULT = os.getenv("PQC_LAB_PASSWORD", "")


_DRONE1_HOST = os.getenv("DRONE1_HOST", os.getenv("DRONE_HOST_LAN", "10.2.142.211"))
_DRONE2_HOST = os.getenv("DRONE2_HOST", "10.2.142.211")

_DEFAULT_DRONE_HOSTS: Dict[str, str] = {
    "drone1": _DRONE1_HOST,
    "drone2": _DRONE2_HOST,
}

_DEFAULT_DRONE_HOST_ALLOWLIST = list(dict.fromkeys([
    _DEFAULT_DRONE_HOST,
    _DRONE1_HOST,
    _DRONE2_HOST,
    _DRONE_HOST_LAN,
    _DRONE_HOST_TAILSCALE,
]))

def resolve_drone_host(drone_id: str = "drone1") -> str:
    """Resolves the IP address for a specified drone identifier or falls back to DRONE_HOST."""
    hosts = CONFIG.get("DRONE_HOSTS", {})
    if isinstance(hosts, dict) and drone_id in hosts:
        return str(hosts[drone_id])
    return str(CONFIG.get("DRONE_HOST", _DEFAULT_DRONE_HOST))


# Default configuration - all required keys with correct types
CONFIG = {
    # Handshake (TCP)
    "TCP_HANDSHAKE_PORT": 46000,

    # Encrypted UDP data-plane (network)
    "UDP_DRONE_RX": 46012,   # drone binds here; GCS sends here
    "UDP_GCS_RX": 46011,     # gcs binds here; Drone sends here

    # Plaintext UDP (local loopback to apps/FC)
    "DRONE_PLAINTEXT_TX": 47003,  # app→drone-proxy (to encrypt out)
    "DRONE_PLAINTEXT_RX": 47004,  # drone-proxy→app (after decrypt)
    "GCS_PLAINTEXT_TX": 47001,    # app→gcs-proxy
    "GCS_PLAINTEXT_RX": 47002,    # gcs-proxy→app
    # MAVLink sniff ports (MAVProxy secondary output for metrics collection)
    "MAVLINK_SNIFF_DRONE": 47005,  # drone-side MAVProxy → MavLinkMetricsCollector
    "MAVLINK_SNIFF_GCS": 14552,    # gcs-side MAVProxy → MavLinkMetricsCollector
    # Max MAVLink packets consumed per collector loop to bound CPU while
    # allowing higher sustained burst handling.
    "GCS_METRICS_PACKETS_PER_LOOP": 100,
    # Direct proxy→collector sniff bypass (0 = disabled, use MAVProxy path).
    # When enabled, the decrypting proxy sends a second copy of each plaintext
    # packet directly to this port, bypassing MAVProxy's processing bottleneck.
    "GCS_PLAINTEXT_SNIFF_PORT": 14553,
    # Swarm discovery & multicast ports (hierarchical_swarm)
    "SWARM_MCAST_GROUP": "239.255.0.1",
    "SWARM_MCAST_PORT": 9999,
    "SWARM_HANDSHAKE_PORT": 10000,

    # Dashboard & Camera ports
    "DASHBOARD_PORT": 8000,
    "CAMERA_STREAM_PORT": 8090,

    # UDP socket buffer size (bytes).  Overrides the OS default (~8 KB on Win).
    "UDP_SOCK_BUF_BYTES": 2 * 1024 * 1024,
    # Use localhost for plaintext bindings to ensure compatibility with local MAVProxy
    "DRONE_PLAINTEXT_HOST": "127.0.0.1",
    "GCS_PLAINTEXT_HOST": "127.0.0.1",

    # Hosts
    "DRONE_HOST": _DEFAULT_DRONE_HOST,
    "DRONE_HOSTS": _DEFAULT_DRONE_HOSTS,
    "DRONE_HOST_ALLOWLIST": _DEFAULT_DRONE_HOST_ALLOWLIST,
    "GCS_HOST": _DEFAULT_GCS_HOST,
    "TUNNEL_HOST_PROFILE": _HOST_PROFILE,
    "DRONE_HOST_LAN": _DRONE_HOST_LAN,
    "DRONE_HOST_TAILSCALE": _DRONE_HOST_TAILSCALE,
    "GCS_HOST_LAN": _GCS_HOST_LAN,
    "GCS_HOST_TAILSCALE": _GCS_HOST_TAILSCALE,

    # Pre-shared key (hex) for drone authentication during handshake.
    # Default is a placeholder; override in production via environment variable.
    # Intentionally default to empty; require injection via environment in non-dev.
    "DRONE_PSK": "",

    # Crypto/runtime
    "REPLAY_WINDOW": 1024,
    "WIRE_VERSION": 2,      # protocol/header version byte
    "WIRE_SESSION_ID_LEN": 16,
    # Allow slower suites to finish the rekey handshake without timing out
    "REKEY_HANDSHAKE_TIMEOUT": 45.0,

    # --- Bare scheduler defaults (scheduler/bare/*) ---
    # Dwell time per suite before automatic rotation (seconds).
    # Both drone_follower and gcs_scheduler read this for consistency.
    "BARE_SUITE_DWELL_S": 10.0,
    # Confirmation timeout for local proxy state change after rekey request.
    "BARE_CONFIRM_TIMEOUT_S": 10.0,
    # Poll interval for status checks during dwell period.
    "BARE_POLL_INTERVAL_S": 2.0,

    # --- Optional hardening / QoS knobs (NOT required; safe defaults) ---
    # Limit TCP handshake attempts accepted per IP at the GCS (server) side.
    # Model: token bucket; BURST tokens max, refilling at REFILL_PER_SEC tokens/sec.
    "HANDSHAKE_RL_BURST": 5,
    "HANDSHAKE_RL_REFILL_PER_SEC": 1,

    # Rekey circuit-breaker: suppress new rekey attempts after N consecutive
    # failures within a sliding window.  Cooldown is seconds to wait before
    # accepting rekeys again.  Set REKEY_CB_ENABLED=False (default) to keep
    # legacy behaviour unchanged.
    "REKEY_CB_ENABLED": False,
    "REKEY_CB_FAIL_THRESHOLD": 3,
    "REKEY_CB_WINDOW_S": 60.0,
    "REKEY_CB_COOLDOWN_S": 30.0,

    # Strict semaphore-style rekey gate. When enabled, only one rekey worker
    # may run at a time to avoid overlap windows between back-to-back requests.
    "REKEY_STRICT_SINGLE_FLIGHT": True,
    # Used only when REKEY_STRICT_SINGLE_FLIGHT is disabled.
    "REKEY_MAX_CONCURRENT": 3,

    # Pre-rekey liveness check: skip rekey if no data/heartbeat received
    # from peer within this many seconds.  Uses data-plane keepalive
    # (0x00 packet every 15 s) as liveness signal.  Default 45 s = 3×keepalive.
    "REKEY_LIVENESS_THRESHOLD_S": 45.0,

    # Clock-sync smoothing: use median-of-N samples instead of raw
    # single-sample replacement.  Set CLOCK_SYNC_SMOOTHING=False (default)
    # to keep legacy deterministic single-sample behaviour.
    "CLOCK_SYNC_SMOOTHING": False,
    "CLOCK_SYNC_WINDOW": 3,

    # Mark encrypted UDP with DSCP EF (46) to prioritize on WMM-enabled APs.
    # Set to None to disable. Implementation multiplies by 4 to form TOS.
    "ENCRYPTED_DSCP": 46,

    # Feature flag: if True, proxy prefixes app->proxy plaintext with 1 byte packet type.
    # 0x01 = MAVLink/data (forward to local app); 0x02 = control (route to policy engine).
    # When False (default), proxy passes bytes unchanged (backward compatible).
    "ENABLE_PACKET_TYPE": True,

    # Enable standardized Ascon-AEAD128 exposure in runtime probing.
    # This path is backed by the vendored SP 800-232 implementation.
    "ENABLE_ASCON": True,

    # Enforce 16-byte key usage for the standardized Ascon backend.
    "ASCON_STRICT_KEY_SIZE": False,

    # HMAC auth shared secret for MAV schedulers (string, UTF-8). Override via env MAV_AUTH_KEY.
    "MAV_AUTH_KEY": os.getenv("MAV_AUTH_KEY", "pqc_uav_scheduler_default_auth_key"),
    # Optional allow list for MAV scheduler control channels. Accepts list/tuple or comma string.
    "MAV_ALLOWED_SENDERS": [],

    # Direct MAVProxy wiring defaults for lab setups. These are used by
    # auto/mav helpers to build a plain Pixhawk↔GCS MAVLink path that is
    # independent of the PQC proxy. Adjust these if wiring or tools move.
    "MAV_FC_DEVICE": "udp:127.0.0.1:14550" if sys.platform == "win32" else "/dev/ttyACM0",  # SITL UDP on Windows, Pixhawk USB serial on Linux Pi
    "MAV_FC_BAUD": 57600,              # Pixhawk serial baud rate
    # GCS-side UDP ports where the drone sends MAVLink (LAN-facing).
    "MAV_GCS_IN_PORT_1": 14550,
    "MAV_GCS_IN_PORT_2": 14551,
    # GCS MAVProxy bind host for incoming MAVLink from the drone.
    "MAV_GCS_LISTEN_HOST": "0.0.0.0",
    # Local loopback host/ports on the GCS for ground tools (e.g., QGC).
    "MAV_LOCAL_HOST": "127.0.0.1",
    "MAV_LOCAL_OUT_PORT_1": 14550,
    "MAV_LOCAL_OUT_PORT_2": 14551,
    # Local QGroundControl (QGC) listen port for mirrored MAVLink output
    "QGC_PORT": 14550,
    # Explicit drone host/port for client-style GCS master (two-way heartbeat).
    # Using explicit remote prevents passive listener stalls on some platforms.
    "MAV_DRONE_HOST": _DEFAULT_DRONE_HOST,
    "MAV_DRONE_UDP_PORT": 14550,

    # Enforce strict matching of encrypted UDP peer IP/port with the authenticated handshake peer.
    # Disable (set to False) only when operating behind NAT where source ports may differ.
    "STRICT_UDP_PEER_MATCH": True,
    "STRICT_HANDSHAKE_IP": True,

    # Log real session IDs only when explicitly enabled (default False masks them to hashes).
    "LOG_SESSION_ID": False,

    # --- Simple automation defaults (tools/auto/*_simple.py) ---
    # Optional: enable TCP JSON control listener inside the core proxy.
    # When enabled, each side may expose a listener (DRONE_CONTROL_* / GCS_CONTROL_*).
    # Only the configured CONTROL_COORDINATOR_ROLE will accept "cmd":"rekey";
    # non-coordinator nodes respond with coordinator_only.
    "ENABLE_TCP_CONTROL": False,
    # Rekey coordinator/dominator role for the in-band two-phase commit.
    # This does NOT change the TCP handshake roles (GCS still serves, drone still connects);
    # it only defines which side initiates prepare/commit and triggers the rekey handshake.
    # Allowed: "gcs" (default, legacy) or "drone".
    "CONTROL_COORDINATOR_ROLE": "gcs",
    # Control-plane stale state recovery timeouts.
    "CONTROL_NEGOTIATING_TIMEOUT_S": 15.0,
    "CONTROL_SWAPPING_TIMEOUT_S": 30.0,
    # Control server bind host for the drone follower. Default to the
    # configured drone host (LAN) so remote GCS schedulers can reach
    # the control RPCs by default. Use env override `DRONE_CONTROL_HOST`
    # for special cases (loopback-only testing).
    "DRONE_CONTROL_HOST": _DEFAULT_DRONE_HOST,
    "DRONE_CONTROL_PORT": 48080,
    # Optional control listener settings for the GCS host.
    # Used by core's TCP control server (when enabled) and by tooling.
    # Bind to 0.0.0.0 by default to accept local + remote commands.
    "GCS_CONTROL_HOST": "0.0.0.0",
    "GCS_CONTROL_PORT": 48080,
    # Telemetry port for GCS -> Drone feedback channel (UDP)
    "GCS_TELEMETRY_PORT": 52080,
    # Encrypted-plane control channel used by certain schedulers to route
    # drone-originated control/status back to the GCS when ENABLE_PACKET_TYPE is set.
    # Keep distinct from the plaintext follower RPC port to avoid conflicts.
    "DRONE_TO_GCS_CTL_PORT": 48181,
    "SIMPLE_VERIFY_TIMEOUT_S": 5.0,
    "SIMPLE_PACKETS_PER_SUITE": 1,
    "SIMPLE_PACKET_DELAY_S": 0.0,
    "SIMPLE_SUITE_DWELL_S": 0.0,
    # Default initial suite used by simple automation drivers and schedulers.
    # Keep suite IDs centralized in core.suites; tooling should fall back to it.
    "SIMPLE_INITIAL_SUITE": None,

    # Benchmark suite-switch mode:
    #   "cold_restart"   — stop proxy process, start new process (default, backward compatible)
    #   "in_band_rekey"  — use in-band _do_rekey() with atomic cipher swap (no process restart)
    "BENCHMARK_MODE": "cold_restart",

    # Primitive benchmark coverage lists used by metrics tools and tests.
    # Keep these aligned with supported algorithms on target hardware.
    "PRIMITIVE_TEST_KEMS": [
        "ML-KEM-768",
        "Kyber512",
        "HQC-192",
    ],
    "PRIMITIVE_TEST_SIGS": [
        "ML-DSA-65",
        "Falcon-512",
        "SPHINCS+-SHA2-128s-simple",
    ],
    "PRIMITIVE_TEST_AEADS": [
        "aesgcm",
        "chacha20poly1305",
    ],
    # Automation defaults for tools/auto orchestration scripts
    "AUTO_DRONE": {
        # Session IDs default to "<prefix>_<unix>" unless DRONE_SESSION_ID env overrides
        "session_prefix": "run",
        # Optional explicit initial suite override (None -> defer to tooling defaults).
        "initial_suite": None,
        # Enable follower monitors (perf/pidstat/psutil) by default
        "monitors_enabled": True,
        # Apply CPU governor tweaks unless disabled
        "cpu_optimize": True,
        # Enable telemetry publisher back to the scheduler
        "telemetry_enabled": True,
        # Optional explicit telemetry host/port (None -> derive from CONTROL_HOST defaults)
        "telemetry_host": None,
        "telemetry_port": 52080,
        # Override monitoring output base directory (None -> DEFAULT_MONITOR_BASE)
        "monitor_output_base": None,
        # Optional environment exports applied before creating the power monitor
        "power_env": {
            # Maintain 1 kHz sampling by default; backend remains auto unless overridden
            "DRONE_POWER_BACKEND": "ina219",
            "DRONE_POWER_SAMPLE_HZ": "1000",
            "INA219_I2C_BUS": "1",
            "INA219_ADDR": "0x40",
            "INA219_SHUNT_OHM": "0.1",
        },
        # Synthetic flight model defaults used when power telemetry
        # translates PQC utilization into flight endurance estimates.
        "mock_mass_kg": 6.5,
        "kinematics_horizontal_mps": 13.0,
        "kinematics_vertical_mps": 3.5,
        "kinematics_cycle_s": 18.0,
        "kinematics_yaw_rate_dps": 45.0,
        # Toggle MAVProxy launch vs. legacy UDP echo helper.
        # MAVProxy stays enabled by default to keep parity with lab setups.
        "mavproxy_enabled": True,
        "udp_echo_enabled": False,
    },

    "AUTO_GCS": {
        # Session IDs default to "<prefix>_<unix>" unless GCS_SESSION_ID env overrides
        "session_prefix": "run",  # string prefix for run IDs
        # Traffic profile: "blast", "constant", "mavproxy", or "saturation"
        "traffic": "constant",  # modes: constant|blast|mavproxy|saturation
        # Traffic engine: "native" (built-in blaster) or "iperf3" (external client)
        "traffic_engine": "native",  # generator: native|iperf3
        # Duration for active traffic window per suite (seconds)
        # For cores+DVFS sweeps we default to short, aggressive 10s windows.
        "duration_s": 10.0,  # positive float seconds
        # Delay after rekey before starting traffic (seconds)
        "pre_gap_s": 1.0,  # non-negative float seconds (keep a short warmup)
        # Delay between suites (seconds). Shorten for faster cores+DVFS sweeps.
        "inter_gap_s": 5.0,  # non-negative float seconds
        # UDP payload size (bytes) for blaster calculations
        # Use a near-MTU payload to stress the data plane.
        "payload_bytes": 1200,  # payload bytes (>0)
        # Sample every Nth send/receive event (0 disables)
        "event_sample": 100,  # packets between samples (>=0)
        # Number of full passes across suite list. For DVFS sweeps, set this
        # to match the number of DVFS combos (e.g. 13 for 600-1800 MHz in
        # 100 MHz steps) so each pass runs the full suite set at a fixed
        # CPU frequency.
        "passes": 13,  # positive integer
        # Explicit packets-per-second override; 0 means best-effort
        "rate_pps": 0,  # packets/sec (>=0)
        # Optional bandwidth target in Mbps (converted to PPS if > 0)
        # Default to ~10 Mbps to exercise realistic airlink load.
        "bandwidth_mbps": 10.0,  # Mbps target (>=0)
        # Max rate explored during saturation sweeps (Mbps)
        "max_rate_mbps": 200.0,  # saturation upper bound Mbps (>0)
        # Optional ordered suite subset (None -> all suites from core.suites, including ChaCha20-Poly1305 and ASCON variants)
        # Set to None to run the full suite matrix
        "suites": None,
        # Launch local GCS proxy under scheduler control
        "launch_proxy": True,  # bool controls local proxy launch
        # Enable local proxy monitors (perf/pidstat/psutil)
        "monitors_enabled": True,  # bool controlling monitor sidecars
        # Start telemetry collector on the scheduler side
        "telemetry_enabled": True,  # bool gating telemetry collector
        # Bind/port for telemetry collector (defaults to CONFIG values)
        "telemetry_bind_host": "0.0.0.0",  # bind address string
        "telemetry_port": 52080,  # telemetry listen port (1-65535)
        # Emit combined Excel workbook when run completes
        "export_combined_excel": True,  # bool to generate combined workbook
        # Optional iperf3 configuration used when traffic_engine == "iperf3"
        "iperf3": {
            "server_host": None,  # override iperf3 server host or None for default
            "server_port": 5201,  # iperf3 UDP port (1-65535)
            "binary": "iperf3",  # iperf3 executable path/name
            "extra_args": [],  # additional CLI args list
            "force_cli": False,  # bool to force CLI output mode
        },
        # Blocklist of AEAD tokens to exclude from automation runs (case-insensitive)
        "aead_exclude_tokens": [],
        # Optional post-run fetch of drone artifacts (logs, power captures)
        "post_fetch": {
            # Legacy remote-fetch pipeline is disabled; artifacts must be synced via Git.
            "enabled": False,
            "host": _DEFAULT_DRONE_HOST,
            "username": "dev",
            "password": os.getenv("AUTO_GCS_POST_FETCH_PASSWORD", _LAB_PASSWORD_DEFAULT),
            "key": None,
            "strategy": "disabled",
            "port": 22,
            "logs_remote": "~/research/logs/auto/drone",
            "logs_local": "logs/auto",
            "output_remote": "~/research/output/drone",
            "output_local": "output/drone",
        },
        # Power fetch now relies on locally synced artifacts instead of remote copy.
        "power_fetch_enabled": False,
        "power_fetch_target": f"dev@{_DEFAULT_DRONE_HOST}",
        "artifact_fetch_strategy": "auto",  # Default fetch strategy for artifacts (auto selects best available)
        "post_report": {
            "enabled": True,  # bool toggling post-run report generation
            "script": "tools/report_constant_run.py",  # reporting script path
            "output_dir": "output/gcs",  # base output directory
            "table_name": "run_summary_table.md",  # Markdown table filename
            "text_name": "run_suite_summaries.txt",  # narrative summary filename
        },
        # Non-interactive SFTP password for POWER fetch (used by gcs_scheduler._sftp_fetch)
        # Set to None to prefer key/agent-based auth. For development convenience we
        # populate it here; in production prefer using an SSH agent or per-run env var.
        "power_fetch_password": os.getenv("AUTO_GCS_POWER_FETCH_PASSWORD", _LAB_PASSWORD_DEFAULT),
        # Optional explicit private key for power fetch operations (overrides agent lookup)
        "power_fetch_key": None,
    },

    # Allow plaintext host bindings to be non-loopback by default so LAN runners work
    # without env overrides. Set to False to force loopback-only bindings.
    "ALLOW_NON_LOOPBACK_PLAINTEXT": True,

    # ==========================================================================
    # BENCHMARK PIPELINE CONFIGURATION
    # ==========================================================================
    # Unified settings for bench/benchmark_power_perf.py and analysis tools.
    # These settings configure INA219 power monitoring, perf integration, and
    # the benchmark execution parameters.
    "BENCHMARK": {
        # Default iterations per operation (override with -n/--iterations)
        "default_iterations": 200,
        # Quick test iterations for development/validation runs
        "quick_iterations": 5,
        
        # INA219 Power Monitoring
        "power": {
            "enabled": True,
            "sample_hz": 1000,           # 1kHz sampling rate (verified)
            "warmup_ms": 50,             # Warmup period before operation
            "cooldown_ms": 50,           # Cooldown period after operation
            "i2c_bus": 1,                # I2C bus number
            "i2c_address": 0x40,         # INA219 address
            "shunt_ohm": 0.1,            # Shunt resistor value
        },
        
        # Linux perf counters
        "perf": {
            "enabled": True,
            "counters": [
                "cycles",
                "instructions",
                "cache-misses",
                "branch-misses",
            ],
        },
        
        # Output configuration
        "output": {
            "base_dir": "benchmarks/bench_results_power",   # Default output directory
            "analysis_dir": "benchmarks/power_analysis",    # Analysis output directory
            "save_raw_samples": False,           # Save individual power samples (large)
            "json_indent": 2,                    # JSON formatting
        },
        
        # Analysis and reporting
        "analysis": {
            "plot_dpi": 300,
            "plot_format": "png",
            "report_format": "markdown",         # markdown, pdf, or both
        },
        
        # Algorithms to include (None = all available)
        "include_kems": None,
        "include_sigs": None,
        "include_aeads": None,
        
        # AEAD payload sizes for throughput analysis
        "aead_payload_sizes": [64, 256, 1024, 4096],
    },
}


# Required keys with their expected types
_REQUIRED_KEYS = {
    "TCP_HANDSHAKE_PORT": int,
    "UDP_DRONE_RX": int,
    "UDP_GCS_RX": int,
    "DRONE_PLAINTEXT_TX": int,
    "DRONE_PLAINTEXT_RX": int,
    "GCS_PLAINTEXT_TX": int,
    "GCS_PLAINTEXT_RX": int,
    "DRONE_HOST": str,
    "GCS_HOST": str,
    "DRONE_PLAINTEXT_HOST": str,
    "GCS_PLAINTEXT_HOST": str,
    "REPLAY_WINDOW": int,
    "WIRE_VERSION": int,
    "WIRE_SESSION_ID_LEN": int,
    "ENABLE_PACKET_TYPE": bool,
    "ENABLE_ASCON": bool,
    "STRICT_UDP_PEER_MATCH": bool,
    "STRICT_HANDSHAKE_IP": bool,
    "LOG_SESSION_ID": bool,
    "DRONE_PSK": str,
    "REKEY_HANDSHAKE_TIMEOUT": float,
    "REKEY_STRICT_SINGLE_FLIGHT": bool,
    "REKEY_MAX_CONCURRENT": int,
    "ASCON_STRICT_KEY_SIZE": bool,
    "DRONE_TO_GCS_CTL_PORT": int,
    "DRONE_CONTROL_HOST": str,
    "DRONE_CONTROL_PORT": int,
    "GCS_CONTROL_HOST": str,
    "GCS_CONTROL_PORT": int,
    "GCS_TELEMETRY_PORT": int,
    "QGC_PORT": int,
}

# Env-overridable keys that are not part of _REQUIRED_KEYS but still need type parsing.
_ENV_OPTIONAL_TYPES = {
    "ENABLE_TCP_CONTROL": bool,
    "CONTROL_COORDINATOR_ROLE": str,
    "CONTROL_NEGOTIATING_TIMEOUT_S": float,
    "CONTROL_SWAPPING_TIMEOUT_S": float,
    "MAV_AUTH_KEY": str,
    "MAV_ALLOWED_SENDERS": str,
}

# Keys that can be overridden by environment variables
_ENV_OVERRIDABLE = {
        "ENABLE_TCP_CONTROL",
    "CONTROL_COORDINATOR_ROLE",
    "CONTROL_NEGOTIATING_TIMEOUT_S",
    "CONTROL_SWAPPING_TIMEOUT_S",
    "DRONE_HOST",
    "GCS_HOST",
    "TCP_HANDSHAKE_PORT",
    "UDP_DRONE_RX", 
    "UDP_GCS_RX",
    "DRONE_PLAINTEXT_TX",  # Added for testing/benchmarking flexibility
    "DRONE_PLAINTEXT_RX",  # Added for testing/benchmarking flexibility  
    "GCS_PLAINTEXT_TX",    # Added for testing/benchmarking flexibility
    "GCS_PLAINTEXT_RX",    # Added for testing/benchmarking flexibility
    "DRONE_CONTROL_PORT",
    "DRONE_CONTROL_HOST",
    "GCS_CONTROL_PORT",
    "GCS_CONTROL_HOST",
    "GCS_TELEMETRY_PORT",
    "DRONE_TO_GCS_CTL_PORT",
    "ENABLE_PACKET_TYPE",
    "ENABLE_ASCON",
    "STRICT_UDP_PEER_MATCH",
    "STRICT_HANDSHAKE_IP",
    "LOG_SESSION_ID",
    "DRONE_PSK",
    "REKEY_STRICT_SINGLE_FLIGHT",
    "REKEY_MAX_CONCURRENT",
    "ASCON_STRICT_KEY_SIZE",
    "MAV_AUTH_KEY",
    "MAV_ALLOWED_SENDERS",
}


def validate_config(cfg: Dict[str, Any]) -> None:
    """
    Ensure all required keys exist with correct types/ranges.
    Raise NotImplementedError("<reason>") on any violation.
    No return value on success.
    """
    # Check all required keys exist
    missing_keys = set(_REQUIRED_KEYS.keys()) - set(cfg.keys())
    if missing_keys:
        raise ConfigError(f"CONFIG missing required keys: {', '.join(sorted(missing_keys))}")
    
    # Check types for all keys
    for key, expected_type in _REQUIRED_KEYS.items():
        value = cfg[key]
        if key == "REKEY_HANDSHAKE_TIMEOUT":
            if not isinstance(value, (int, float)):
                raise ConfigError(
                    f"CONFIG[{key}] must be float seconds, got {type(value).__name__}"
                )
            continue
        if not isinstance(value, expected_type):
            raise ConfigError(f"CONFIG[{key}] must be {expected_type.__name__}, got {type(value).__name__}")
    
    # Validate port ranges
    for key in _REQUIRED_KEYS:
        if key.endswith("_PORT") or key.endswith("_RX") or key.endswith("_TX"):
            port = cfg[key]
            if not (1 <= port <= 65535):
                raise ConfigError(f"CONFIG[{key}] must be valid port (1-65535), got {port}")
    
    # Validate specific constraints
    if cfg["WIRE_VERSION"] != 2:
        raise ConfigError(f"CONFIG[WIRE_VERSION] must be 2 for the upgraded protocol, got {cfg['WIRE_VERSION']}")
    if cfg["WIRE_SESSION_ID_LEN"] != 16:
        raise ConfigError(
            f"CONFIG[WIRE_SESSION_ID_LEN] must be 16 for protocol v2, got {cfg['WIRE_SESSION_ID_LEN']}"
        )
    
    if cfg["REPLAY_WINDOW"] < 64:
        raise ConfigError(f"CONFIG[REPLAY_WINDOW] must be >= 64, got {cfg['REPLAY_WINDOW']}")
    if cfg["REPLAY_WINDOW"] > 8192:
        raise ConfigError(f"CONFIG[REPLAY_WINDOW] must be <= 8192, got {cfg['REPLAY_WINDOW']}")
    if cfg["REKEY_MAX_CONCURRENT"] < 1:
        raise ConfigError(
            f"CONFIG[REKEY_MAX_CONCURRENT] must be >= 1, got {cfg['REKEY_MAX_CONCURRENT']}"
        )
    
    # Validate hosts are valid strings (basic check)
    for host_key in ["DRONE_HOST", "GCS_HOST"]:
        host = cfg[host_key]
        if not host or not isinstance(host, str):
            raise ConfigError(f"CONFIG[{host_key}] must be non-empty string, got {repr(host)}")
        try:
            ip_address(host)
        except ValueError as exc:
            raise ConfigError(f"CONFIG[{host_key}] must be a valid IP address: {exc}")

    # Loopback hosts for plaintext path may remain hostnames (e.g., 127.0.0.1).
    # Allow override via CONFIG key or environment variable for backward compatibility
    allow_non_loopback_plaintext_env = str(os.environ.get("ALLOW_NON_LOOPBACK_PLAINTEXT", "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    allow_non_loopback_plaintext_cfg = bool(cfg.get("ALLOW_NON_LOOPBACK_PLAINTEXT", False))
    allow_non_loopback_plaintext = allow_non_loopback_plaintext_cfg or allow_non_loopback_plaintext_env
    for host_key in ["DRONE_PLAINTEXT_HOST", "GCS_PLAINTEXT_HOST"]:
        host = cfg[host_key]
        if not host or not isinstance(host, str):
            raise ConfigError(f"CONFIG[{host_key}] must be non-empty string, got {repr(host)}")
        if allow_non_loopback_plaintext:
            continue
        try:
            parsed = ip_address(host)
            if not parsed.is_loopback:
                raise ConfigError(
                    f"CONFIG[{host_key}] must be a loopback address unless ALLOW_NON_LOOPBACK_PLAINTEXT is set"
                )
        except ValueError:
            if host.lower() != "localhost":
                raise ConfigError(
                    f"CONFIG[{host_key}] must be a loopback address (localhost) unless ALLOW_NON_LOOPBACK_PLAINTEXT is set"
                )
    
    # Optional keys are intentionally not required; do light validation if present
    if "ENCRYPTED_DSCP" in cfg and cfg["ENCRYPTED_DSCP"] is not None:
        if not (0 <= int(cfg["ENCRYPTED_DSCP"]) <= 63):
            raise ConfigError("CONFIG[ENCRYPTED_DSCP] must be 0..63 or None")

    if "ENABLE_TCP_CONTROL" in cfg:
        if not isinstance(cfg["ENABLE_TCP_CONTROL"], bool):
            raise ConfigError("CONFIG[ENABLE_TCP_CONTROL] must be bool")

    coord = cfg.get("CONTROL_COORDINATOR_ROLE", "gcs")
    if coord is not None:
        if not isinstance(coord, str):
            raise ConfigError("CONFIG[CONTROL_COORDINATOR_ROLE] must be str")
        coord_norm = coord.strip().lower()
        if coord_norm not in {"gcs", "drone"}:
            raise ConfigError("CONFIG[CONTROL_COORDINATOR_ROLE] must be 'gcs' or 'drone'")

    for timeout_key in ("CONTROL_NEGOTIATING_TIMEOUT_S", "CONTROL_SWAPPING_TIMEOUT_S"):
        if timeout_key in cfg:
            value = cfg[timeout_key]
            if not isinstance(value, (int, float)):
                raise ConfigError(f"CONFIG[{timeout_key}] must be float seconds")
            if float(value) <= 0.0:
                raise ConfigError(f"CONFIG[{timeout_key}] must be > 0")

    # Validate DRONE_PSK: require in non-dev environments; allow empty in dev.
    psk = cfg.get("DRONE_PSK", "")
    if os.getenv("ENV", "dev") != "dev" and not psk:
        raise ConfigError("CONFIG[DRONE_PSK] must be provided in non-dev environment")
    if psk:
        try:
            psk_bytes = bytes.fromhex(psk)
        except ValueError:
            raise ConfigError("CONFIG[DRONE_PSK] must be a hex string")
        if len(psk_bytes) != 32:
            raise ConfigError("CONFIG[DRONE_PSK] must decode to 32 bytes")


def _apply_env_overrides(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Apply environment variable overrides to config."""
    result = cfg.copy()
    
    for key in _ENV_OVERRIDABLE:
        env_var = key
        if env_var in os.environ:
            env_value = os.environ[env_var]
            expected_type = _REQUIRED_KEYS.get(key) or _ENV_OPTIONAL_TYPES.get(key)
            if expected_type is None:
                raise ConfigError(f"Unsupported env override key: {env_var}")
            
            try:
                if expected_type == int:
                    result[key] = int(env_value)
                elif expected_type == str:
                    result[key] = str(env_value)
                elif expected_type == bool:
                    lowered = str(env_value).strip().lower()
                    if lowered in {"1", "true", "yes", "on"}:
                        result[key] = True
                    elif lowered in {"0", "false", "no", "off"}:
                        result[key] = False
                    else:
                        raise ValueError(f"invalid boolean literal: {env_value}")
                elif expected_type == float:
                    result[key] = float(env_value)
                else:
                    raise ConfigError(f"Unsupported type for env override: {expected_type}")
            except ValueError:
                raise ConfigError(f"Invalid {expected_type.__name__} value for {env_var}: {env_value}")
    
    if not result.get("DRONE_PSK"):
        psk_file = Path(__file__).resolve().parent.parent / "drone_psk.txt"
        if psk_file.is_file():
            content = psk_file.read_text(encoding="utf-8").strip()
            if content and not content.startswith("%"):
                result["DRONE_PSK"] = content
                os.environ["DRONE_PSK"] = content

    return result


# Apply environment overrides and validate
CONFIG = _apply_env_overrides(CONFIG)
validate_config(CONFIG)
