#!/usr/bin/env python3
"""
Comprehensive Metrics Aggregator
core/metrics_aggregator.py

Aggregates metrics from all collectors into the ComprehensiveSuiteMetrics schema.
Provides APIs for both GCS and Drone sides.

Usage:
    from core.metrics_aggregator import MetricsAggregator
    
    agg = MetricsAggregator(role="drone")
    agg.start_suite("cs-mlkem512-falcon512")
    # ... run benchmark ...
    metrics = agg.finalize_suite()
"""

import os
import sys
import time
import json
import socket
import platform
import threading
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Callable

from core.metrics_schema import (
    ComprehensiveSuiteMetrics,
    RunContextMetrics,
    SuiteCryptoIdentity,
    SuiteLifecycleTimeline,
    HandshakeMetrics,
    CryptoPrimitiveBreakdown,
    RekeyMetrics,
    DataPlaneMetrics,
    LatencyJitterMetrics,
    MavProxyDroneMetrics,
    MavProxyGcsMetrics,
    MavLinkIntegrityMetrics,
    FlightControllerTelemetry,
    ControlPlaneMetrics,
    SystemResourcesDrone,
    SystemResourcesGcs,
    PowerEnergyMetrics,
    ObservabilityMetrics,
    ValidationMetrics,
)

from core.config import CONFIG

from core.metrics_collectors import (
    EnvironmentCollector,
    SystemCollector,
    PowerCollector,
    NetworkCollector,
)

# Import MAVLink collector (optional)
try:
    from core.mavlink_collector import MavLinkMetricsCollector
    HAS_MAVLINK_COLLECTOR = True
except ImportError:
    HAS_MAVLINK_COLLECTOR = False
    MavLinkMetricsCollector = None


class MetricsAggregator:
    """
    Aggregates metrics from multiple collectors into ComprehensiveSuiteMetrics.
    
    Designed to be instantiated on both GCS and Drone sides, with role-specific
    collection logic.
    """
    
    def __init__(self, role: str = "auto", output_dir: str = None):
        """
        Initialize the aggregator.
        
        Args:
            role: "gcs", "drone", or "auto" (detect from platform)
            output_dir: Directory for output files
        """
        self.role = role if role != "auto" else self._detect_role()
        
        # Output directory
        if output_dir:
            self.output_dir = Path(output_dir)
        else:
            self.output_dir = Path(__file__).parent.parent / "logs" / "comprehensive_metrics"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize collectors
        self.env_collector = EnvironmentCollector()
        self.system_collector = SystemCollector()
        self.network_collector = NetworkCollector()
        self.latency_tracker = None
        
        # Power collector (drone only)
        # Honour DRONE_POWER_BACKEND from .denv / env if set, otherwise auto-detect.
        if self.role == "drone":
            _pw_backend = os.environ.get("DRONE_POWER_BACKEND", "auto")
            self.power_collector = PowerCollector(backend=_pw_backend)
        else:
            self.power_collector = None
        
        # MAVLink collector (both sides)
        if HAS_MAVLINK_COLLECTOR:
            self.mavlink_collector = MavLinkMetricsCollector(role=self.role)
        else:
            self.mavlink_collector = None
        
        # Current metrics object
        self._current_metrics: Optional[ComprehensiveSuiteMetrics] = None
        self._run_id: str = ""
        self._suite_index: int = 0
        
        # Background collection
        self._collecting = False
        self._collect_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._system_samples: List[Dict[str, Any]] = []

        # Proxy counters snapshot (for throughput calculations)
        self._last_proxy_counters: Optional[Dict[str, Any]] = None

        # Clock sync offset (run context)
        self._clock_offset_ms: Optional[float] = None
        self._clock_offset_method: str = "ntp"
        
        # Callbacks for external data
        self._proxy_metrics_callback: Optional[Callable[[], Dict[str, Any]]] = None
        self._mavlink_metrics_callback: Optional[Callable[[], Dict[str, Any]]] = None
        self._metric_status: Dict[str, Dict[str, str]] = {}

    def _mark_metric_status(self, field_path: str, status: str, reason: str) -> None:
        """Record metric status and reason for transparency."""
        if not field_path:
            return
        self._metric_status[field_path] = {
            "status": str(status),
            "reason": str(reason),
        }
    
    def _detect_role(self) -> str:
        """Detect role from platform."""
        machine = platform.machine().lower()
        if "arm" in machine or "aarch" in machine:
            return "drone"
        return "gcs"
    
    def set_run_id(self, run_id: str):
        """Set the run ID for this benchmark session."""
        self._run_id = run_id
    
    def register_proxy_callback(self, callback: Callable[[], Dict[str, Any]]):
        """Register callback to get proxy metrics."""
        self._proxy_metrics_callback = callback
    
    def register_mavlink_callback(self, callback: Callable[[], Dict[str, Any]]):
        """Register callback to get MAVLink metrics."""
        self._mavlink_metrics_callback = callback

    def inject_rtt_sample(self, rtt_ms: float) -> None:
        """Forward an externally-measured RTT sample to the mavlink collector."""
        if self.mavlink_collector is not None:
            try:
                self.mavlink_collector.inject_rtt_sample(rtt_ms)
            except Exception:
                pass
        # FIX-S4b: Tag the latency schema so downstream consumers know this
        # RTT was measured over the TCP control channel, not the UDP tunnel.
        if self._current_metrics is not None:
            self._current_metrics.latency_jitter.rtt_source = "control_tcp"

    def set_clock_offset(self, offset_seconds: float, method: str = "ntp"):
        """Record clock offset for run context and forward to mavlink collector."""
        try:
            self._clock_offset_ms = float(offset_seconds) * 1000.0
            self._clock_offset_method = method or "ntp"
        except (TypeError, ValueError):
            return

        if self._current_metrics:
            self._current_metrics.run_context.clock_offset_ms = self._clock_offset_ms
            self._current_metrics.run_context.clock_offset_method = self._clock_offset_method

        # Forward to mavlink collector so OWL can use Chronos offset as
        # fallback when SYSTEM_TIME is unavailable (no GPS).
        if self.mavlink_collector is not None:
            try:
                self.mavlink_collector.set_clock_offset(offset_seconds)
            except Exception:
                pass
    
    def start_suite(self, suite_id: str, suite_config: Dict[str, Any] = None) -> ComprehensiveSuiteMetrics:
        """
        Start collecting metrics for a new suite.
        
        Args:
            suite_id: The cipher suite identifier
            suite_config: Optional suite configuration from core.suites
        
        Returns:
            The metrics object being populated
        """
        # Create new metrics object
        self._current_metrics = ComprehensiveSuiteMetrics()
        m = self._current_metrics
        
        # A. Run & Context
        env = self.env_collector.collect()
        m.run_context.run_id = self._run_id
        m.run_context.suite_id = suite_id
        m.run_context.suite_index = self._suite_index
        m.run_context.git_commit_hash = env.get("git_commit", "")
        m.run_context.git_dirty_flag = env.get("git_dirty", False)
        
        if self.role == "gcs":
            m.run_context.gcs_hostname = env.get("hostname", "")
            m.run_context.gcs_ip = self.env_collector.get_ip_address()
            m.run_context.python_env_gcs = env.get("conda_env", "") or env.get("virtual_env", "")
            m.run_context.kernel_version_gcs = env.get("kernel_version", "")
        else:
            m.run_context.drone_hostname = env.get("hostname", "")
            m.run_context.drone_ip = self.env_collector.get_ip_address()
            m.run_context.python_env_drone = env.get("conda_env", "") or env.get("virtual_env", "")
            m.run_context.kernel_version_drone = env.get("kernel_version", "")
        
        m.run_context.liboqs_version = env.get("liboqs_version", "")
        m.run_context.run_start_time_wall = datetime.now(timezone.utc).isoformat()
        m.run_context.run_start_time_mono = time.monotonic()
        if self._clock_offset_ms is not None:
            m.run_context.clock_offset_ms = self._clock_offset_ms
            m.run_context.clock_offset_method = self._clock_offset_method
        else:
            m.run_context.clock_offset_ms = None
            m.run_context.clock_offset_method = None
            self._mark_metric_status(
                "run_context.clock_offset_ms",
                "not_collected",
                "clock_sync_not_performed"
            )

        # Normalize empty strings to None for run context fields
        for field_name in (
            "git_commit_hash",
            "gcs_hostname",
            "drone_hostname",
            "gcs_ip",
            "drone_ip",
            "python_env_gcs",
            "python_env_drone",
            "liboqs_version",
            "kernel_version_gcs",
            "kernel_version_drone",
        ):
            value = getattr(m.run_context, field_name, None)
            if isinstance(value, str) and not value.strip():
                setattr(m.run_context, field_name, None)
                self._mark_metric_status(
                    f"run_context.{field_name}",
                    "not_collected",
                    "missing_environment_value"
                )
        
        # B. Suite Crypto Identity (from config)
        if suite_config:
            m.crypto_identity.kem_algorithm = suite_config.get("kem_name", "")
            m.crypto_identity.kem_nist_level = suite_config.get("nist_level", "")
            m.crypto_identity.sig_algorithm = suite_config.get("sig_name", "")
            m.crypto_identity.sig_nist_level = suite_config.get("nist_level", "")
            m.crypto_identity.aead_algorithm = suite_config.get("aead", "")
            m.crypto_identity.suite_security_level = suite_config.get("nist_level", "")
            
            # Parse family from algorithm name
            kem_name = suite_config.get("kem_name", "")
            if "ML-KEM" in kem_name:
                m.crypto_identity.kem_family = "ML-KEM"
            elif "HQC" in kem_name:
                m.crypto_identity.kem_family = "HQC"
            elif "McEliece" in kem_name:
                m.crypto_identity.kem_family = "Classic-McEliece"
            
            sig_name = suite_config.get("sig_name", "")
            if "Falcon" in sig_name:
                m.crypto_identity.sig_family = "Falcon"
            elif "ML-DSA" in sig_name or "Dilithium" in sig_name:
                m.crypto_identity.sig_family = "ML-DSA"
            elif "SPHINCS" in sig_name:
                m.crypto_identity.sig_family = "SPHINCS+"

        # Normalize empty crypto identity fields
        for field_name in (
            "kem_algorithm",
            "kem_family",
            "kem_nist_level",
            "sig_algorithm",
            "sig_family",
            "sig_nist_level",
            "aead_algorithm",
            "suite_security_level",
        ):
            value = getattr(m.crypto_identity, field_name, None)
            if isinstance(value, str) and not value.strip():
                setattr(m.crypto_identity, field_name, None)
                self._mark_metric_status(
                    f"crypto_identity.{field_name}",
                    "not_collected",
                    "missing_suite_config"
                )
        
        # C. Lifecycle - mark selection time
        m.lifecycle.suite_selected_time = time.monotonic()
        
        # Start background collection
        self._start_background_collection()
        
        # Start power sampling (drone only)
        _power_hz = float(os.environ.get(
            "DRONE_POWER_SAMPLE_HZ",
            str(CONFIG.get("BENCHMARK", {}).get("power", {}).get("sample_hz", 1000)),
        ))
        if self.role == "drone" and self.power_collector and self.power_collector.backend != "none":
            self.power_collector.start_sampling(rate_hz=_power_hz)
        
        # Start MAVLink sniffing
        if self.mavlink_collector:
            # When a direct sniff port is configured (GCS_PLAINTEXT_SNIFF_PORT),
            # the proxy sends a second plaintext copy directly to that port —
            # bypassing MAVProxy.  Use it for lossless measurement.
            # Drone always sniffs via MAVProxy on MAVLINK_SNIFF_DRONE (47005).
            if self.role == "gcs":
                direct_sniff = int(CONFIG.get("GCS_PLAINTEXT_SNIFF_PORT", 0))
                sniff_port = direct_sniff if direct_sniff else int(CONFIG.get("MAVLINK_SNIFF_GCS", 14552))
            else:
                sniff_port = int(CONFIG.get("MAVLINK_SNIFF_DRONE", 47005))
            try:
                self.mavlink_collector.start_sniffing(port=sniff_port)
            except Exception:
                pass  # Port may already be in use

            # Start active RTT probe: send MAVLink PING via plaintext TX path
            # so RTT remains available even when no COMMAND_LONG traffic exists.
            # Drone sends to DRONE_PLAINTEXT_TX (47003), GCS to GCS_PLAINTEXT_TX (47001).
            rtt_probe_port = 47003 if self.role == "drone" else 47001
            try:
                self.mavlink_collector.start_rtt_probe(
                    host="127.0.0.1",
                    port=rtt_probe_port,
                    rate_hz=1.0,
                )
            except Exception:
                pass
        
        self._suite_index += 1
        return m
    
    def record_handshake_start(self):
        """Mark handshake start time."""
        if self._current_metrics:
            now = time.monotonic()
            if self.role == "gcs":
                self._current_metrics.handshake.handshake_start_time_gcs = now
            else:
                self._current_metrics.handshake.handshake_start_time_drone = now

    def reset_mavlink_count_window(self) -> None:
        """Reset MAVLink collector counters so the counting window starts
        now — aligning with the moment the proxy begins forwarding.

        Call this immediately after the handshake is confirmed and the
        proxy forwarding loop is live.  Without this reset the collector
        accumulates messages during the multi-second start-up window
        (GCS command, subprocess launch, TCP handshake) that the proxy
        never sees, producing a phantom 13-20 % 'loss'.
        """
        if self.mavlink_collector is not None:
            self.mavlink_collector.reset_count_window()
        # Also update the lifecycle activation timestamp so duration
        # calculations use the proxy-aligned start time.
        if self._current_metrics:
            self._current_metrics.lifecycle.suite_activated_time = time.monotonic()

    def record_handshake_end(self, success: bool = True, failure_reason: str = ""):
        """Mark handshake end and record status.
        
        IDEMPOTENT: If handshake timing is already recorded, this call is ignored
        to prevent overwriting with incorrect values (e.g., suite duration).
        """
        if self._current_metrics:
            h = self._current_metrics.handshake
            
            # GUARD: Prevent double-call from overwriting correct timing
            if isinstance(h.handshake_total_duration_ms, (int, float)) and h.handshake_total_duration_ms > 0:
                import logging
                logging.getLogger(__name__).warning(
                    "record_handshake_end() called twice - ignoring to preserve "
                    f"original duration of {h.handshake_total_duration_ms:.2f}ms"
                )
                return
            
            now = time.monotonic()
            
            if self.role == "gcs":
                h.handshake_end_time_gcs = now
                if h.handshake_start_time_gcs and h.handshake_start_time_gcs > 0:
                    h.handshake_total_duration_ms = (now - h.handshake_start_time_gcs) * 1000
            else:
                h.handshake_end_time_drone = now
                if h.handshake_start_time_drone and h.handshake_start_time_drone > 0:
                    h.handshake_total_duration_ms = (now - h.handshake_start_time_drone) * 1000

            h.end_to_end_handshake_duration_ms = h.handshake_total_duration_ms
            
            h.handshake_success = success
            h.handshake_failure_reason = failure_reason
            
            # Mark lifecycle activation
            self._current_metrics.lifecycle.suite_activated_time = now
    
    def record_crypto_primitives(self, primitives: Dict[str, Any]):
        """
        Record cryptographic primitive timing.
        
        Expected keys:
            - kem_keygen_ns, kem_encaps_ns, kem_decaps_ns
            - sig_sign_ns, sig_verify_ns
            - pub_key_size_bytes, ciphertext_size_bytes, sig_size_bytes
        """
        if not self._current_metrics:
            return
        
        cp = self._current_metrics.crypto_primitives
        
        # Timing in milliseconds
        if "kem_keygen_ns" in primitives:
            cp.kem_keygen_ns = primitives["kem_keygen_ns"]
            cp.kem_keygen_time_ms = primitives["kem_keygen_ns"] / 1_000_000
        if "kem_encaps_ns" in primitives:
            cp.kem_encaps_ns = primitives["kem_encaps_ns"]
            cp.kem_encapsulation_time_ms = primitives["kem_encaps_ns"] / 1_000_000
        if "kem_decaps_ns" in primitives:
            cp.kem_decaps_ns = primitives["kem_decaps_ns"]
            cp.kem_decapsulation_time_ms = primitives["kem_decaps_ns"] / 1_000_000
        if "sig_sign_ns" in primitives:
            cp.sig_sign_ns = primitives["sig_sign_ns"]
            cp.signature_sign_time_ms = primitives["sig_sign_ns"] / 1_000_000
        if "sig_verify_ns" in primitives:
            cp.sig_verify_ns = primitives["sig_verify_ns"]
            cp.signature_verify_time_ms = primitives["sig_verify_ns"] / 1_000_000
        
        # Also accept ms values directly (map to correct schema field names)
        ms_field_map = {
            "kem_keygen_ms": "kem_keygen_time_ms",
            "kem_encaps_ms": "kem_encapsulation_time_ms",
            "kem_decaps_ms": "kem_decapsulation_time_ms",
            "kem_decap_ms": "kem_decapsulation_time_ms",  # alternate name
            "sig_sign_ms": "signature_sign_time_ms",
            "sig_verify_ms": "signature_verify_time_ms",
        }
        for src_key, dst_field in ms_field_map.items():
            if src_key in primitives and primitives[src_key]:
                setattr(cp, dst_field, float(primitives[src_key]))

        # Protocol-level handshake duration (proxy-internal)
        hs = self._current_metrics.handshake
        protocol_ms = primitives.get("rekey_ms")
        if protocol_ms is None:
            total_ns = primitives.get("handshake_total_ns")
            if isinstance(total_ns, (int, float)) and total_ns > 0:
                protocol_ms = total_ns / 1_000_000.0
        if isinstance(protocol_ms, (int, float)) and protocol_ms > 0:
            hs.protocol_handshake_duration_ms = float(protocol_ms)

            # FIX: Override the scheduler-level handshake duration with the
            # proxy's own perf_counter_ns measurement.  The scheduler's
            # record_handshake_start/end span includes subprocess spawning,
            # sleep(2.0)+sleep(1.0) warm-up delays, RPC round-trip and file-
            # polling jitter — none of which is part of the actual PQC
            # handshake protocol.  The proxy measures handshake_total_ns with
            # time.perf_counter_ns() purely around the protocol exchange
            # (KEM keygen → encaps/decaps → sig sign/verify → key derive),
            # so it is the ground-truth value for research reporting.
            hs.handshake_total_duration_ms = float(protocol_ms)
            hs.end_to_end_handshake_duration_ms = float(protocol_ms)

        # Artifact sizes
        pub_key_size = primitives.get("pub_key_size_bytes")
        ciphertext_size = primitives.get("ciphertext_size_bytes")
        sig_size = primitives.get("sig_size_bytes")
        shared_secret_size = primitives.get("shared_secret_size_bytes")
        cp.pub_key_size_bytes = int(pub_key_size) if pub_key_size is not None else None
        cp.ciphertext_size_bytes = int(ciphertext_size) if ciphertext_size is not None else None
        cp.sig_size_bytes = int(sig_size) if sig_size is not None else None
        cp.shared_secret_size_bytes = int(shared_secret_size) if shared_secret_size is not None else None

        # Calculate total
        total_parts = [
            cp.kem_keygen_time_ms,
            cp.kem_encapsulation_time_ms,
            cp.kem_decapsulation_time_ms,
            cp.signature_sign_time_ms,
            cp.signature_verify_time_ms,
        ]
        if all(part is not None for part in total_parts):
            cp.total_crypto_time_ms = sum(total_parts)
        else:
            cp.total_crypto_time_ms = None
    
    def record_data_plane_metrics(self, counters: Dict[str, Any]):
        """
        Record data plane (proxy) metrics.
        
        Expected keys from proxy counters:
            - ptx_in, ptx_out, enc_in, enc_out
            - drop_replay, drop_auth, drop_header
            - bytes_in, bytes_out
            - primitive_metrics (nested AEAD timing)
        """
        if not self._current_metrics:
            return
        
        dp = self._current_metrics.data_plane
        self._last_proxy_counters = counters
        
        dp.ptx_in = counters.get("ptx_in")
        dp.ptx_out = counters.get("ptx_out")
        dp.enc_in = counters.get("enc_in")
        dp.enc_out = counters.get("enc_out")
        dp.drop_replay = counters.get("drop_replay")
        dp.drop_auth = counters.get("drop_auth")
        dp.drop_header = counters.get("drop_header")
        # FIX-AGG: Ingest previously-invisible drop counters for dashboard visibility
        dp.drop_session_epoch = counters.get("drop_session_epoch")
        dp.drop_other = counters.get("drop_other")
        dp.drop_src_addr = counters.get("drop_src_addr")
        dp.sniff_drop = counters.get("sniff_drop")

        dp.replay_drop_count = dp.drop_replay if dp.drop_replay is not None else None
        drop_session_epoch = counters.get("drop_session_epoch")
        if dp.drop_auth is not None and dp.drop_header is not None and drop_session_epoch is not None:
            dp.decode_failure_count = dp.drop_auth + dp.drop_header + drop_session_epoch
        else:
            dp.decode_failure_count = None

        dp.packets_sent = dp.enc_out
        dp.packets_received = dp.enc_in
        if dp.drop_replay is not None and dp.drop_auth is not None and dp.drop_header is not None:
            dp.packets_dropped = dp.drop_replay + dp.drop_auth + dp.drop_header
        else:
            dp.packets_dropped = None

        # Calculate ratios
        if dp.packets_sent is not None and dp.packets_dropped is not None and dp.packets_sent > 0:
            dp.packet_loss_ratio = dp.packets_dropped / dp.packets_sent
            dp.packet_delivery_ratio = 1.0 - dp.packet_loss_ratio
        else:
            dp.packet_loss_ratio = None
            dp.packet_delivery_ratio = None

        # Byte counters
        dp.bytes_sent = counters.get("ptx_bytes_out") if "ptx_bytes_out" in counters else counters.get("bytes_out")
        dp.bytes_received = counters.get("ptx_bytes_in") if "ptx_bytes_in" in counters else counters.get("bytes_in")

        # Rekey metrics (proxy counters)
        rk = self._current_metrics.rekey
        rk.rekey_success = counters.get("rekeys_ok")
        rk.rekey_failure = counters.get("rekeys_fail")
        if rk.rekey_success is not None or rk.rekey_failure is not None:
            rk.rekey_attempts = (rk.rekey_success or 0) + (rk.rekey_failure or 0)
        else:
            rk.rekey_attempts = None
        rk.rekey_interval_ms = counters.get("rekey_interval_ms")
        rk.rekey_duration_ms = counters.get("rekey_duration_ms")
        if rk.rekey_duration_ms is None:
            rk.rekey_duration_ms = counters.get("last_rekey_ms")
        rk.rekey_blackout_duration_ms = counters.get("rekey_blackout_duration_ms")
        rk.rekey_trigger_reason = counters.get("rekey_trigger_reason")
        
        # AEAD timing from primitive_metrics (nested structure)
        prim = counters.get("primitive_metrics", {})
        enc_stats = prim.get("aead_encrypt", {})
        dec_stats = prim.get("aead_decrypt_ok", {})
        
        if enc_stats.get("count", 0) > 0:
            dp.aead_encrypt_count = enc_stats["count"]
            dp.aead_encrypt_avg_ns = enc_stats.get("total_ns", 0) // enc_stats["count"]
        if dec_stats.get("count", 0) > 0:
            dp.aead_decrypt_count = dec_stats["count"]
            dp.aead_decrypt_avg_ns = dec_stats.get("total_ns", 0) // dec_stats["count"]
    
    def record_latency_sample(self, latency_ms: float):
        """Record a latency sample."""
        if self.latency_tracker:
            self.latency_tracker.record(latency_ms)

    def record_control_plane_metrics(
        self,
        scheduler_tick_interval_ms: Optional[float] = None,
        scheduler_action_type: Optional[str] = None,
        scheduler_action_reason: Optional[str] = None,
        policy_name: Optional[str] = None,
        policy_state: Optional[str] = None,
        policy_suite_index: Optional[int] = None,
        policy_total_suites: Optional[int] = None,
    ) -> None:
        """Record control plane metrics for the current suite."""
        if not self._current_metrics:
            return
        cp = self._current_metrics.control_plane
        if scheduler_tick_interval_ms is not None:
            cp.scheduler_tick_interval_ms = float(scheduler_tick_interval_ms)
        if scheduler_action_type is not None:
            cp.scheduler_action_type = str(scheduler_action_type)
        if scheduler_action_reason is not None:
            cp.scheduler_action_reason = str(scheduler_action_reason)
        if policy_name is not None:
            cp.policy_name = str(policy_name)
        if policy_state is not None:
            cp.policy_state = str(policy_state)
        if policy_suite_index is not None:
            cp.policy_suite_index = int(policy_suite_index)
        if policy_total_suites is not None:
            cp.policy_total_suites = int(policy_total_suites)
    
    def record_traffic_start(self):
        """Mark start of data plane traffic."""
        if self._current_metrics:
            if hasattr(self._current_metrics.lifecycle, "suite_traffic_start_time"):
                self._current_metrics.lifecycle.suite_traffic_start_time = time.monotonic()
    
    def record_traffic_end(self):
        """Mark end of data plane traffic."""
        if self._current_metrics:
            if hasattr(self._current_metrics.lifecycle, "suite_traffic_end_time"):
                self._current_metrics.lifecycle.suite_traffic_end_time = time.monotonic()
    
    def _start_background_collection(self):
        """Start background system metrics collection."""
        if self._collecting:
            return
        
        self._collecting = True
        self._system_samples = []
        self._stop_event.clear()
        
        def collect_loop():
            while not self._stop_event.is_set():
                sample = self.system_collector.collect()
                sample["mono_time"] = time.monotonic()
                self._system_samples.append(sample)
                time.sleep(0.5)  # 2 Hz sampling
        
        self._collect_thread = threading.Thread(target=collect_loop, daemon=True)
        self._collect_thread.start()
    
    def _stop_background_collection(self):
        """Stop background collection."""
        if not self._collecting:
            return
        
        self._stop_event.set()
        if self._collect_thread:
            self._collect_thread.join(timeout=1.0)
        self._collecting = False
    
    def stop_mavlink_collector_early(self) -> None:
        """Stop the MAVLink collector NOW, before finalize_suite() processing.

        Call this immediately after reading drone_status.json so that the
        collector's mav_d count is snapshotted at the same instant as the
        proxy's ptx_in.  finalize_suite() will see the collector already
        stopped and re-use its cached metrics.
        """
        if self.mavlink_collector:
            self.mavlink_collector.stop()
    
    def finalize_suite(self, merge_from: Dict[str, Any] = None) -> ComprehensiveSuiteMetrics:
        """
        Finalize metrics collection for current suite.
        
        Args:
            merge_from: Optional dict with additional metrics to merge
                        (e.g., from peer side via control channel)
        
        Returns:
            Completed metrics object
        """
        if not self._current_metrics:
            return ComprehensiveSuiteMetrics()
        
        m = self._current_metrics
        
        # Stop background collection
        self._stop_background_collection()
        
        # MEASUREMENT-SYNC: Stop MAVLink collector IMMEDIATELY so its final
        # count (mav_d) is captured as close as possible to the last
        # drone_status.json snapshot (ptx_in).  Previously the collector was
        # stopped ~300 lines later, after power/system/crypto processing,
        # causing a 1-2 s skew at ~330 msg/s → 250-520 phantom "gap" msgs.
        _mavlink_stopped_metrics: Dict[str, Any] = {}
        if self.mavlink_collector:
            _mavlink_stopped_metrics = self.mavlink_collector.stop()
        
        # Stop power sampling
        power_samples = []
        if self.power_collector:
            power_samples = self.power_collector.stop_sampling()
        
        # Finalize timing
        now = time.monotonic()
        m.run_context.run_end_time_wall = datetime.now(timezone.utc).isoformat()
        m.run_context.run_end_time_mono = now
        
        # C. Lifecycle finalization
        m.lifecycle.suite_deactivated_time = now
        m.lifecycle.suite_total_duration_ms = (now - m.lifecycle.suite_selected_time) * 1000
        if m.lifecycle.suite_activated_time > 0:
            m.lifecycle.suite_active_duration_ms = (now - m.lifecycle.suite_activated_time) * 1000

        # G. Data plane throughput (requires counters snapshot)
        duration_s = 0.0
        if m.lifecycle.suite_active_duration_ms > 0:
            duration_s = m.lifecycle.suite_active_duration_ms / 1000.0
        elif m.lifecycle.suite_total_duration_ms > 0:
            duration_s = m.lifecycle.suite_total_duration_ms / 1000.0
        if duration_s > 0 and self._last_proxy_counters is not None:
            def _get_counter_int(name: str) -> Optional[int]:
                value = self._last_proxy_counters.get(name)
                if value is None:
                    return None
                try:
                    return int(value)
                except (TypeError, ValueError):
                    return None

            ptx_out = _get_counter_int("ptx_bytes_out")
            ptx_in = _get_counter_int("ptx_bytes_in")
            enc_out = _get_counter_int("enc_bytes_out")
            if enc_out is None:
                enc_out = _get_counter_int("bytes_out")
            enc_in = _get_counter_int("enc_bytes_in")
            if enc_in is None:
                enc_in = _get_counter_int("bytes_in")

            if ptx_out is not None and ptx_in is not None:
                total_payload_bytes = max(0, ptx_out + ptx_in)
                m.data_plane.goodput_mbps = (total_payload_bytes * 8.0) / (duration_s * 1_000_000.0)
                m.data_plane.achieved_throughput_mbps = m.data_plane.goodput_mbps
            else:
                m.data_plane.goodput_mbps = None
                m.data_plane.achieved_throughput_mbps = None

            if enc_out is not None and enc_in is not None:
                total_wire_bytes = max(0, enc_out + enc_in)
                m.data_plane.wire_rate_mbps = (total_wire_bytes * 8.0) / (duration_s * 1_000_000.0)
            else:
                m.data_plane.wire_rate_mbps = None
        elif self._last_proxy_counters is None:
            self._mark_metric_status(
                "data_plane",
                "not_collected",
                "proxy_counters_missing"
            )
            m.data_plane.achieved_throughput_mbps = None
            m.data_plane.goodput_mbps = None
            m.data_plane.wire_rate_mbps = None
            m.data_plane.packets_sent = None
            m.data_plane.packets_received = None
            m.data_plane.packets_dropped = None
            m.data_plane.packet_loss_ratio = None
            m.data_plane.packet_delivery_ratio = None
            m.data_plane.replay_drop_count = None
            m.data_plane.decode_failure_count = None
            m.data_plane.ptx_in = None
            m.data_plane.ptx_out = None
            m.data_plane.enc_in = None
            m.data_plane.enc_out = None
            m.data_plane.drop_replay = None
            m.data_plane.drop_auth = None
            m.data_plane.drop_header = None
            m.data_plane.bytes_sent = None
            m.data_plane.bytes_received = None
            m.data_plane.aead_encrypt_avg_ns = None
            m.data_plane.aead_decrypt_avg_ns = None
            m.data_plane.aead_encrypt_count = None
            m.data_plane.aead_decrypt_count = None

            m.rekey.rekey_attempts = None
            m.rekey.rekey_success = None
            m.rekey.rekey_failure = None
            m.rekey.rekey_interval_ms = None
            m.rekey.rekey_duration_ms = None
            m.rekey.rekey_blackout_duration_ms = None
            m.rekey.rekey_trigger_reason = None
            self._mark_metric_status(
                "rekey",
                "not_collected",
                "proxy_counters_missing"
            )

        if all(
            getattr(m.rekey, field) is None
            for field in (
                "rekey_attempts",
                "rekey_success",
                "rekey_failure",
                "rekey_interval_ms",
                "rekey_duration_ms",
                "rekey_blackout_duration_ms",
                "rekey_trigger_reason",
            )
        ):
            self._mark_metric_status(
                "rekey",
                "not_collected",
                "proxy_rekey_counters_missing"
            )
        
        # N. System resources
        if self._system_samples:
            cpu_samples = [
                s["cpu_percent"]
                for s in self._system_samples
                if isinstance(s.get("cpu_percent"), (int, float))
            ]
            
            sys_m = m.system_drone
            
            if cpu_samples:
                sys_m.cpu_usage_avg_percent = sum(cpu_samples) / len(cpu_samples)
                sys_m.cpu_usage_peak_percent = max(cpu_samples)
            
            # Use last sample for other metrics
            last = self._system_samples[-1]
            sys_m.cpu_freq_mhz = last.get("cpu_freq_mhz")
            sys_m.memory_rss_mb = last.get("memory_rss_mb")
            sys_m.memory_vms_mb = last.get("memory_vms_mb")
            sys_m.thread_count = last.get("thread_count")
            sys_m.uptime_s = last.get("uptime_s")

            sys_m.temperature_c = last.get("temperature_c")
            sys_m.load_avg_1m = last.get("load_avg_1m")
            sys_m.load_avg_5m = last.get("load_avg_5m")
            sys_m.load_avg_15m = last.get("load_avg_15m")
        else:
            self._mark_metric_status(
                "system_drone",
                "not_collected",
                "no_system_samples"
            )
            m.system_drone.cpu_usage_avg_percent = None
            m.system_drone.cpu_usage_peak_percent = None
            m.system_drone.cpu_freq_mhz = None
            m.system_drone.memory_rss_mb = None
            m.system_drone.memory_vms_mb = None
            m.system_drone.thread_count = None
            m.system_drone.uptime_s = None
            m.system_drone.temperature_c = None
            m.system_drone.load_avg_1m = None
            m.system_drone.load_avg_5m = None
            m.system_drone.load_avg_15m = None
        
        # P. Power & Energy
        if power_samples:
            energy_stats = self.power_collector.get_energy_stats(power_samples)
            m.power_energy.power_sensor_type = self.power_collector.backend
            m.power_energy.power_sampling_rate_hz = 1000.0
            m.power_energy.power_avg_w = energy_stats.get("power_avg_w")
            m.power_energy.power_peak_w = energy_stats.get("power_peak_w")
            m.power_energy.energy_total_j = energy_stats.get("energy_total_j")
            m.power_energy.voltage_avg_v = energy_stats.get("voltage_avg_v")
            m.power_energy.current_avg_a = energy_stats.get("current_avg_a")
            
            # Calculate per-handshake energy
            if isinstance(m.handshake.handshake_total_duration_ms, (int, float)) and m.handshake.handshake_total_duration_ms > 0:
                hs_duration_s = m.handshake.handshake_total_duration_ms / 1000.0
                if isinstance(m.power_energy.power_avg_w, (int, float)):
                    m.power_energy.energy_per_handshake_j = m.power_energy.power_avg_w * hs_duration_s
                else:
                    m.power_energy.energy_per_handshake_j = None
            else:
                m.power_energy.energy_per_handshake_j = None
            
            # P-seg. Power segmentation: handshake vs steady-state
            hs_start = m.handshake.handshake_start_time_drone
            hs_end = m.handshake.handshake_end_time_drone
            if (isinstance(hs_start, (int, float)) and hs_start > 0
                    and isinstance(hs_end, (int, float)) and hs_end > hs_start):
                hs_samples = [
                    s for s in power_samples
                    if isinstance(s.get("mono_time"), (int, float))
                    and hs_start <= s["mono_time"] <= hs_end
                ]
                ss_samples = [
                    s for s in power_samples
                    if isinstance(s.get("mono_time"), (int, float))
                    and s["mono_time"] > hs_end
                ]
                if len(hs_samples) >= 2:
                    hs_stats = self.power_collector.get_energy_stats(hs_samples)
                    hs_energy_j = hs_stats.get("energy_total_j")
                    hs_peak_w = hs_stats.get("power_peak_w")
                    m.power_energy.handshake_energy_mj = (
                        hs_energy_j * 1000.0 if isinstance(hs_energy_j, (int, float)) else None
                    )
                    m.power_energy.handshake_peak_power_mw = (
                        hs_peak_w * 1000.0 if isinstance(hs_peak_w, (int, float)) else None
                    )
                else:
                    m.power_energy.handshake_energy_mj = None
                    m.power_energy.handshake_peak_power_mw = None
                if len(ss_samples) >= 2:
                    ss_stats = self.power_collector.get_energy_stats(ss_samples)
                    ss_energy_j = ss_stats.get("energy_total_j")
                    ss_avg_w = ss_stats.get("power_avg_w")
                    m.power_energy.steady_energy_mj = (
                        ss_energy_j * 1000.0 if isinstance(ss_energy_j, (int, float)) else None
                    )
                    m.power_energy.steady_avg_power_mw = (
                        ss_avg_w * 1000.0 if isinstance(ss_avg_w, (int, float)) else None
                    )
                else:
                    m.power_energy.steady_energy_mj = None
                    m.power_energy.steady_avg_power_mw = None
            else:
                m.power_energy.handshake_energy_mj = None
                m.power_energy.handshake_peak_power_mw = None
                m.power_energy.steady_energy_mj = None
                m.power_energy.steady_avg_power_mw = None
        else:
            m.power_energy.power_sensor_type = None
            m.power_energy.power_sampling_rate_hz = None
            m.power_energy.power_avg_w = None
            m.power_energy.power_peak_w = None
            m.power_energy.energy_total_j = None
            m.power_energy.energy_per_handshake_j = None
            m.power_energy.voltage_avg_v = None
            m.power_energy.current_avg_a = None
            m.power_energy.handshake_energy_mj = None
            m.power_energy.handshake_peak_power_mw = None
            m.power_energy.steady_energy_mj = None
            m.power_energy.steady_avg_power_mw = None
            self._mark_metric_status(
                "power_energy",
                "not_collected",
                f"no_power_samples (backend={self.power_collector.backend if self.power_collector else 'none'})"
            )

        # E. Crypto primitive breakdown (null when not collected)
        cp = m.crypto_primitives
        if (
            (cp.kem_keygen_time_ms or 0) == 0 and
            (cp.kem_encapsulation_time_ms or 0) == 0 and
            (cp.kem_decapsulation_time_ms or 0) == 0 and
            (cp.signature_sign_time_ms or 0) == 0 and
            (cp.signature_verify_time_ms or 0) == 0 and
            (cp.pub_key_size_bytes or 0) == 0 and
            (cp.ciphertext_size_bytes or 0) == 0 and
            (cp.sig_size_bytes or 0) == 0
        ):
            cp.kem_keygen_time_ms = None
            cp.kem_encapsulation_time_ms = None
            cp.kem_decapsulation_time_ms = None
            cp.signature_sign_time_ms = None
            cp.signature_verify_time_ms = None
            cp.total_crypto_time_ms = None
            cp.kem_keygen_ns = None
            cp.kem_encaps_ns = None
            cp.kem_decaps_ns = None
            cp.sig_sign_ns = None
            cp.sig_verify_ns = None
            cp.pub_key_size_bytes = None
            cp.ciphertext_size_bytes = None
            cp.sig_size_bytes = None
            cp.shared_secret_size_bytes = None
            self._mark_metric_status(
                "crypto_primitives",
                "not_collected",
                "handshake_primitives_missing"
            )
        
        # I/J. MAVLink metrics
        if self.mavlink_collector:
            try:
                # Collector was already stopped at the top of finalize_suite()
                # (MEASUREMENT-SYNC).  Re-use cached metrics dict.
                mavlink_metrics = _mavlink_stopped_metrics
                
                if self.role == "gcs":
                    self.mavlink_collector.populate_schema_metrics(m.mavproxy_gcs, "gcs")
                else:
                    self.mavlink_collector.populate_schema_metrics(m.mavproxy_drone, "drone")

                    if (m.mavproxy_drone.mavproxy_drone_cmd_sent_count or 0) <= 0:
                        self._mark_metric_status(
                            "mavproxy_drone.mavproxy_drone_cmd_ack_latency_avg_ms",
                            "invalid",
                            "no_command_sent"
                        )
                
                # K. MAVLink integrity
                self.mavlink_collector.populate_mavlink_integrity(m.mavlink_integrity)

                # H. Latency & Jitter (from MAVLink metrics)
                m.latency_jitter.one_way_latency_avg_ms = mavlink_metrics.get("one_way_latency_avg_ms")
                m.latency_jitter.one_way_latency_p95_ms = mavlink_metrics.get("one_way_latency_p95_ms")
                m.latency_jitter.jitter_avg_ms = mavlink_metrics.get("jitter_avg_ms")
                m.latency_jitter.jitter_p95_ms = mavlink_metrics.get("jitter_p95_ms")
                m.latency_jitter.latency_sample_count = mavlink_metrics.get("latency_sample_count")
                m.latency_jitter.latency_invalid_reason = mavlink_metrics.get("latency_invalid_reason", "")
                m.latency_jitter.one_way_latency_valid = mavlink_metrics.get("one_way_latency_valid")

                m.latency_jitter.rtt_avg_ms = mavlink_metrics.get("rtt_avg_ms")
                m.latency_jitter.rtt_p95_ms = mavlink_metrics.get("rtt_p95_ms")
                m.latency_jitter.rtt_sample_count = mavlink_metrics.get("rtt_sample_count")
                m.latency_jitter.rtt_invalid_reason = mavlink_metrics.get("rtt_invalid_reason", "")
                m.latency_jitter.rtt_valid = mavlink_metrics.get("rtt_valid")

                if m.latency_jitter.latency_invalid_reason:
                    self._mark_metric_status(
                        "latency_jitter.one_way_latency_avg_ms",
                        "invalid",
                        m.latency_jitter.latency_invalid_reason,
                    )
                    if m.mavlink_integrity.mavlink_message_latency_avg_ms is None:
                        self._mark_metric_status(
                            "mavlink_integrity.mavlink_message_latency_avg_ms",
                            "invalid",
                            m.latency_jitter.latency_invalid_reason,
                        )
                if m.latency_jitter.rtt_invalid_reason:
                    self._mark_metric_status(
                        "latency_jitter.rtt_avg_ms",
                        "invalid",
                        m.latency_jitter.rtt_invalid_reason,
                    )

                # L. Flight controller telemetry (drone only)
                if self.role == "drone":
                    fc = self.mavlink_collector.get_flight_controller_metrics()
                    m.fc_telemetry.fc_mode = fc.get("fc_mode", "")
                    m.fc_telemetry.fc_armed_state = bool(fc.get("fc_armed_state", False))
                    m.fc_telemetry.fc_heartbeat_age_ms = fc.get("fc_heartbeat_age_ms", 0.0) or 0.0
                    m.fc_telemetry.fc_attitude_update_rate_hz = fc.get("fc_attitude_update_rate_hz", 0.0) or 0.0
                    m.fc_telemetry.fc_position_update_rate_hz = fc.get("fc_position_update_rate_hz", 0.0) or 0.0
                    m.fc_telemetry.fc_battery_voltage_v = fc.get("fc_battery_voltage_v", 0.0) or 0.0
                    m.fc_telemetry.fc_battery_current_a = fc.get("fc_battery_current_a", 0.0) or 0.0
                    m.fc_telemetry.fc_battery_remaining_percent = fc.get("fc_battery_remaining_percent", 0.0) or 0.0
                    m.fc_telemetry.fc_cpu_load_percent = fc.get("fc_cpu_load_percent", 0.0) or 0.0
                    m.fc_telemetry.fc_sensor_health_flags = int(fc.get("fc_sensor_health_flags", 0) or 0)
            except Exception:
                pass
        else:
            self._mark_metric_status(
                "latency_jitter",
                "not_collected",
                "mavlink_collector_unavailable"
            )
            # Null out MAVLink-dependent metrics
            m.mavproxy_drone.mavproxy_drone_start_time = None
            m.mavproxy_drone.mavproxy_drone_end_time = None
            m.mavproxy_drone.mavproxy_drone_tx_pps = None
            m.mavproxy_drone.mavproxy_drone_rx_pps = None
            m.mavproxy_drone.mavproxy_drone_total_msgs_sent = None
            m.mavproxy_drone.mavproxy_drone_total_msgs_received = None
            m.mavproxy_drone.mavproxy_drone_msg_type_counts = None
            m.mavproxy_drone.mavproxy_drone_heartbeat_interval_ms = None
            m.mavproxy_drone.mavproxy_drone_heartbeat_loss_count = None
            m.mavproxy_drone.mavproxy_drone_seq_gap_count = None
            m.mavproxy_drone.mavproxy_drone_cmd_sent_count = None
            m.mavproxy_drone.mavproxy_drone_cmd_ack_received_count = None
            m.mavproxy_drone.mavproxy_drone_cmd_ack_latency_avg_ms = None
            m.mavproxy_drone.mavproxy_drone_cmd_ack_latency_p95_ms = None
            m.mavproxy_drone.mavproxy_drone_stream_rate_hz = None

            m.mavlink_integrity.mavlink_sysid = None
            m.mavlink_integrity.mavlink_compid = None
            m.mavlink_integrity.mavlink_protocol_version = None
            m.mavlink_integrity.mavlink_packet_crc_error_count = None
            m.mavlink_integrity.mavlink_decode_error_count = None
            m.mavlink_integrity.mavlink_msg_drop_count = None
            m.mavlink_integrity.mavlink_out_of_order_count = None
            m.mavlink_integrity.mavlink_duplicate_count = None
            m.mavlink_integrity.mavlink_message_latency_avg_ms = None

            m.latency_jitter.one_way_latency_valid = None
            m.latency_jitter.rtt_valid = None

            self._mark_metric_status(
                "mavlink_integrity",
                "not_collected",
                "mavlink_collector_unavailable"
            )

            m.fc_telemetry.fc_mode = None
            m.fc_telemetry.fc_armed_state = None
            m.fc_telemetry.fc_heartbeat_age_ms = None
            m.fc_telemetry.fc_attitude_update_rate_hz = None
            m.fc_telemetry.fc_position_update_rate_hz = None
            m.fc_telemetry.fc_battery_voltage_v = None
            m.fc_telemetry.fc_battery_current_a = None
            m.fc_telemetry.fc_battery_remaining_percent = None
            m.fc_telemetry.fc_cpu_load_percent = None
            m.fc_telemetry.fc_sensor_health_flags = None

            self._mark_metric_status(
                "fc_telemetry",
                "not_collected",
                "mavlink_collector_unavailable"
            )
        
        # Q. Observability
        if self._system_samples:
            m.observability.log_sample_count = len(self._system_samples)
            m.observability.metrics_sampling_rate_hz = 2.0
            m.observability.collection_start_time = m.run_context.run_start_time_mono
            m.observability.collection_end_time = now
            m.observability.collection_duration_ms = (now - m.run_context.run_start_time_mono) * 1000
        else:
            m.observability.log_sample_count = None
            m.observability.metrics_sampling_rate_hz = None
            m.observability.collection_start_time = None
            m.observability.collection_end_time = None
            m.observability.collection_duration_ms = None
            self._mark_metric_status(
                "observability",
                "not_collected",
                "no_system_samples"
            )
        
        # R. Validation
        if m.observability.collection_duration_ms is not None:
            m.validation.expected_samples = int(m.observability.collection_duration_ms / 500)  # 2 Hz
            m.validation.collected_samples = len(self._system_samples)
            m.validation.lost_samples = max(0, m.validation.expected_samples - m.validation.collected_samples)
        else:
            m.validation.expected_samples = None
            m.validation.collected_samples = None
            m.validation.lost_samples = None
            self._mark_metric_status(
                "validation.collected_samples",
                "not_collected",
                "no_system_samples"
            )
            self._mark_metric_status(
                "validation.lost_samples",
                "not_collected",
                "no_system_samples"
            )

        if m.handshake.handshake_success is not None:
            m.validation.success_rate_percent = 100.0 if m.handshake.handshake_success else 0.0
            m.validation.benchmark_pass_fail = "PASS" if m.handshake.handshake_success else "FAIL"
        else:
            m.validation.success_rate_percent = None
            m.validation.benchmark_pass_fail = None
            self._mark_metric_status(
                "validation.benchmark_pass_fail",
                "not_collected",
                "handshake_status_missing"
            )
            self._mark_metric_status(
                "validation.success_rate_percent",
                "not_collected",
                "handshake_status_missing"
            )
        m.validation.metric_status = dict(self._metric_status)
        
        # Merge additional data from peer
        if merge_from:
            self._merge_peer_data(m, merge_from)

        if m.latency_jitter.latency_invalid_reason:
            self._mark_metric_status(
                "latency_jitter.one_way_latency_avg_ms",
                "invalid",
                m.latency_jitter.latency_invalid_reason,
            )
        if m.latency_jitter.rtt_invalid_reason:
            self._mark_metric_status(
                "latency_jitter.rtt_avg_ms",
                "invalid",
                m.latency_jitter.rtt_invalid_reason,
            )

        # Flag missing GCS system metrics
        if all(
            getattr(m.system_gcs, field) is None
            for field in (
                "cpu_usage_avg_percent",
                "cpu_usage_peak_percent",
                "cpu_freq_mhz",
                "memory_rss_mb",
                "memory_vms_mb",
                "thread_count",
                "temperature_c",
                "uptime_s",
                "load_avg_1m",
                "load_avg_5m",
                "load_avg_15m",
            )
        ):
            self._mark_metric_status(
                "system_gcs",
                "not_collected",
                "gcs_system_metrics_missing"
            )
        
        # Save to file
        self._save_metrics(m)
        
        # Clear for next suite
        self._current_metrics = None
        self._system_samples = []
        self._last_proxy_counters = None
        self._metric_status = {}
        
        return m
    
    def _merge_peer_data(self, m: ComprehensiveSuiteMetrics, peer_data: Dict[str, Any]):
        """Merge metrics from peer side."""
        # Merge run context
        if "drone_hostname" in peer_data:
            m.run_context.drone_hostname = peer_data["drone_hostname"]
        if "drone_ip" in peer_data:
            m.run_context.drone_ip = peer_data["drone_ip"]
        if "gcs_hostname" in peer_data:
            m.run_context.gcs_hostname = peer_data["gcs_hostname"]
        if "gcs_ip" in peer_data:
            m.run_context.gcs_ip = peer_data["gcs_ip"]
        if "python_env_gcs" in peer_data:
            m.run_context.python_env_gcs = peer_data["python_env_gcs"]
        if "kernel_version_gcs" in peer_data:
            m.run_context.kernel_version_gcs = peer_data["kernel_version_gcs"]

        gcs_info = peer_data.get("gcs_info") if isinstance(peer_data, dict) else None
        if isinstance(gcs_info, dict):
            m.run_context.gcs_hostname = gcs_info.get("hostname", m.run_context.gcs_hostname)
            m.run_context.gcs_ip = gcs_info.get("ip", m.run_context.gcs_ip)
            m.run_context.python_env_gcs = gcs_info.get("python_env", m.run_context.python_env_gcs)
            m.run_context.kernel_version_gcs = gcs_info.get("kernel_version", m.run_context.kernel_version_gcs)
        
        # Merge handshake timing
        if "handshake_start_time_drone" in peer_data:
            m.handshake.handshake_start_time_drone = peer_data["handshake_start_time_drone"]
        if "handshake_end_time_drone" in peer_data:
            m.handshake.handshake_end_time_drone = peer_data["handshake_end_time_drone"]
        
        # Merge system metrics
        if "system_drone" in peer_data:
            for k, v in peer_data["system_drone"].items():
                if hasattr(m.system_drone, k):
                    setattr(m.system_drone, k, v)

        if "system_gcs" in peer_data:
            for k, v in peer_data["system_gcs"].items():
                if hasattr(m.system_gcs, k):
                    setattr(m.system_gcs, k, v)

        # Merge power metrics
        if "power_energy" in peer_data:
            for k, v in peer_data["power_energy"].items():
                if hasattr(m.power_energy, k):
                    setattr(m.power_energy, k, v)

        # Merge GCS MAVLink metrics (mavlink_validation)
        if "mavlink_validation" in peer_data:
            d = peer_data["mavlink_validation"]
            target = m.mavproxy_gcs

            if d is None:
                self._mark_metric_status(
                    "mavproxy_gcs",
                    "not_collected",
                    "gcs_mavlink_validation_missing"
                )
            else:
            
                # Direct mapping from get_metrics() dict keys to MavProxyGcsMetrics fields
                target.mavproxy_gcs_total_msgs_received = d.get("total_msgs_received")
                target.mavproxy_gcs_seq_gap_count = d.get("seq_gap_count")

        if "latency_jitter" in peer_data and isinstance(peer_data.get("latency_jitter"), dict):
            lj = peer_data.get("latency_jitter", {})
            for key, value in lj.items():
                if hasattr(m.latency_jitter, key) and value is not None:
                    setattr(m.latency_jitter, key, value)

        # Merge GCS-side crypto primitives from proxy_status
        proxy_status = peer_data.get("proxy_status")
        if isinstance(proxy_status, dict):
            counters = proxy_status.get("counters", proxy_status)
            hs_metrics = counters.get("handshake_metrics", {})
            if isinstance(hs_metrics, dict) and hs_metrics:
                cp = m.crypto_primitives
                # GCS-side operations: keygen, decapsulation, signature signing
                # Only fill if not already populated (drone-side takes precedence)
                gcs_ms_fields = {
                    "kem_keygen_ms": "kem_keygen_time_ms",
                    "kem_keygen_avg_ms": "kem_keygen_time_ms",
                    "kem_decaps_ms": "kem_decapsulation_time_ms",
                    "kem_decap_ms": "kem_decapsulation_time_ms",
                    "kem_decaps_avg_ms": "kem_decapsulation_time_ms",
                    "sig_sign_ms": "signature_sign_time_ms",
                    "sig_sign_avg_ms": "signature_sign_time_ms",
                }
                for src_key, dst_field in gcs_ms_fields.items():
                    val = hs_metrics.get(src_key)
                    if val and getattr(cp, dst_field, None) is None:
                        setattr(cp, dst_field, float(val))
                # GCS-side ns fields
                primitives_block = hs_metrics.get("primitives", {})
                kem_block = primitives_block.get("kem", {})
                sig_block = primitives_block.get("signature", {})
                if kem_block.get("keygen_ns") and cp.kem_keygen_ns is None:
                    cp.kem_keygen_ns = int(kem_block["keygen_ns"])
                if kem_block.get("decap_ns") and cp.kem_decaps_ns is None:
                    cp.kem_decaps_ns = int(kem_block["decap_ns"])
                if sig_block.get("sign_ns") and cp.sig_sign_ns is None:
                    cp.sig_sign_ns = int(sig_block["sign_ns"])
                # Artifact sizes (fill if missing)
                if cp.pub_key_size_bytes is None and hs_metrics.get("pub_key_size_bytes"):
                    cp.pub_key_size_bytes = int(hs_metrics["pub_key_size_bytes"])
                if cp.ciphertext_size_bytes is None and hs_metrics.get("ciphertext_size_bytes"):
                    cp.ciphertext_size_bytes = int(hs_metrics["ciphertext_size_bytes"])
                if cp.sig_size_bytes is None and hs_metrics.get("sig_size_bytes"):
                    cp.sig_size_bytes = int(hs_metrics["sig_size_bytes"])
                if cp.shared_secret_size_bytes is None and hs_metrics.get("shared_secret_size_bytes"):
                    cp.shared_secret_size_bytes = int(hs_metrics["shared_secret_size_bytes"])
                # Recalculate total_crypto_time_ms after merge
                total_parts = [
                    cp.kem_keygen_time_ms,
                    cp.kem_encapsulation_time_ms,
                    cp.kem_decapsulation_time_ms,
                    cp.signature_sign_time_ms,
                    cp.signature_verify_time_ms,
                ]
                if all(part is not None for part in total_parts):
                    cp.total_crypto_time_ms = sum(total_parts)

                # Merge GCS AEAD metrics into data_plane
                prim_metrics = counters.get("primitive_metrics", {})
                if prim_metrics:
                    aead_enc = prim_metrics.get("aead_encrypt", {})
                    aead_dec = prim_metrics.get("aead_decrypt_ok", {})
                    dp = m.data_plane
                    if aead_enc.get("count") and dp.aead_encrypt_count is None:
                        dp.aead_encrypt_count = aead_enc["count"]
                        if aead_enc.get("total_ns") and aead_enc["count"] > 0:
                            dp.aead_encrypt_avg_ns = aead_enc["total_ns"] / aead_enc["count"]
                    if aead_dec.get("count") and dp.aead_decrypt_count is None:
                        dp.aead_decrypt_count = aead_dec["count"]
                        if aead_dec.get("total_ns") and aead_dec["count"] > 0:
                            dp.aead_decrypt_avg_ns = aead_dec["total_ns"] / aead_dec["count"]

    def _save_metrics(self, m: ComprehensiveSuiteMetrics):
        """Save metrics to JSON file."""
        filename = f"{m.run_context.run_id}_{m.run_context.suite_id}_{self.role}.json"
        filepath = self.output_dir / filename
        
        try:
            m.save_json(str(filepath))
        except Exception as e:
            print(f"Failed to save metrics: {e}")
    
    def get_current_metrics(self) -> Optional[ComprehensiveSuiteMetrics]:
        """Get current metrics object (if active)."""
        return self._current_metrics
    
    def get_exportable_data(self) -> Dict[str, Any]:
        """
        Get current metrics as dict for sending to peer.
        
        Returns subset of metrics relevant to current role.
        """
        if not self._current_metrics:
            return {}
        
        m = self._current_metrics
        
        if self.role == "drone":
            return {
                "drone_hostname": m.run_context.drone_hostname,
                "drone_ip": m.run_context.drone_ip,
                "python_env_drone": m.run_context.python_env_drone,
                "kernel_version_drone": m.run_context.kernel_version_drone,
                "handshake_start_time_drone": m.handshake.handshake_start_time_drone,
                "handshake_end_time_drone": m.handshake.handshake_end_time_drone,
                "system_drone": {
                    "cpu_usage_avg_percent": m.system_drone.cpu_usage_avg_percent,
                    "cpu_usage_peak_percent": m.system_drone.cpu_usage_peak_percent,
                    "memory_rss_mb": m.system_drone.memory_rss_mb,
                    "temperature_c": m.system_drone.temperature_c,
                },
                "power_energy": {
                    "power_sensor_type": m.power_energy.power_sensor_type,
                    "power_avg_w": m.power_energy.power_avg_w,
                    "power_peak_w": m.power_energy.power_peak_w,
                    "energy_total_j": m.power_energy.energy_total_j,
                    "energy_per_handshake_j": m.power_energy.energy_per_handshake_j,
                },
            }
        else:
            return {
                "gcs_hostname": m.run_context.gcs_hostname,
                "gcs_ip": m.run_context.gcs_ip,
                "python_env_gcs": m.run_context.python_env_gcs,
                "kernel_version_gcs": m.run_context.kernel_version_gcs,
            }
    
    def save_suite_metrics(self, metrics: ComprehensiveSuiteMetrics = None) -> Optional[str]:
        """
        Save suite metrics to JSON file.
        
        Args:
            metrics: ComprehensiveSuiteMetrics to save (or use current if None)
        
        Returns:
            Path to saved file, or None on failure
        """
        m = metrics or self._current_metrics
        if not m:
            return None
        
        try:
            from dataclasses import asdict
            
            # Create filename
            suite_id = m.run_context.suite_id or "unknown"
            run_id = self._run_id or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{suite_id}_{run_id}_{self.role}.json"
            output_path = self.output_dir / filename
            
            # Convert to dict
            data = asdict(m)
            
            # Write to file
            with open(output_path, "w") as f:
                json.dump(data, f, indent=2, default=str)
            
            return str(output_path)
        except Exception as e:
            print(f"Failed to save suite metrics: {e}")
            return None


# =============================================================================
# MAIN - Test aggregator
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("METRICS AGGREGATOR TEST")
    print("=" * 60)
    
    # Create aggregator
    agg = MetricsAggregator(role="auto")
    print(f"Detected role: {agg.role}")
    
    # Simulate benchmark
    agg.set_run_id("test_20260112_120000")
    
    # Start suite
    suite_config = {
        "kem_name": "ML-KEM-512",
        "sig_name": "Falcon-512",
        "aead": "AES-256-GCM",
        "nist_level": "L1",
    }
    
    print("\nStarting suite benchmark...")
    metrics = agg.start_suite("cs-mlkem512-falcon512", suite_config)
    
    # Simulate handshake
    agg.record_handshake_start()
    time.sleep(0.1)  # Simulate 100ms handshake
    agg.record_handshake_end(success=True)
    
    # Record crypto primitives
    agg.record_crypto_primitives({
        "kem_encaps_ns": 500_000,  # 0.5ms
        "sig_verify_ns": 1_200_000,  # 1.2ms
        "pub_key_size_bytes": 800,
        "ciphertext_size_bytes": 768,
        "sig_size_bytes": 666,
    })
    
    # Simulate traffic
    agg.record_traffic_start()
    time.sleep(0.5)  # Simulate 500ms of traffic
    agg.record_traffic_end()
    
    # Record data plane metrics
    agg.record_data_plane_metrics({
        "ptx_in": 100,
        "ptx_out": 100,
        "enc_in": 100,
        "enc_out": 100,
        "drop_replay": 0,
        "drop_auth": 0,
    })
    
    # Finalize
    print("\nFinalizing metrics...")
    final_metrics = agg.finalize_suite()
    
    # Print summary
    print("\n--- METRICS SUMMARY ---")
    print(f"Suite: {final_metrics.run_context.suite_id}")
    print(f"Handshake success: {final_metrics.handshake.handshake_success}")
    print(f"Handshake duration: {final_metrics.handshake.handshake_total_duration_ms:.2f} ms")
    print(f"CPU avg: {final_metrics.system_drone.cpu_usage_avg_percent:.1f}%")
    print(f"Total duration: {final_metrics.lifecycle.suite_total_duration_ms:.2f} ms")
    
    print(f"\nMetrics saved to: {agg.output_dir}")
    print("\nTest completed successfully!")
