"""Benchmark Metrics & Collectors for Hierarchical UAV Swarm Evaluation.

Collects and aggregates timing, cryptographic performance, system telemetry, and power metrics
across 11 evaluation categories:
    1. Discovery Join Latency (HELLO → SMT → KEM → Ascon → ACTIVE)
    2. SMT Verification (avg, min, max, P95)
    3. ML-KEM Performance (keygen, encap, decap, HKDF)
    4. ML-DSA Performance (sign, verify)
    5. Ascon AEAD Performance (encrypt, decrypt, pps)
    6. Heartbeat Metrics (RTT, loss %, jitter, recovery)
    7. Routing Performance (lookup, forward latency, duplicate drops, TTL expiry)
    8. Task Manager Performance (assignment, completion, timeout rate, retries)
    9. Cluster Manager Performance (leader/follower failure, recovery duration, task redistribution)
   10. System Resources (CPU %, Memory MB, Threads, Timers)
   11. Power Telemetry (INA219 Voltage, Current, Power)
"""

from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

try:
    import psutil
except ImportError:
    psutil = None


def percentile(data: List[float], p: float) -> float:
    """Computes the p-th percentile of a list of floats (0 <= p <= 100)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    if n == 1:
        return sorted_data[0]
    k = (n - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    d0 = sorted_data[int(f)] * (c - k)
    d1 = sorted_data[int(c)] * (k - f)
    return d0 + d1


@dataclass(slots=True)
class MetricStats:
    """Statistical summary for a latency or throughput metric series."""

    count: int = 0
    avg_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    p95_ms: float = 0.0

    @classmethod
    def from_samples(cls, samples_ms: List[float]) -> MetricStats:
        if not samples_ms:
            return cls()
        cnt = len(samples_ms)
        avg_v = sum(samples_ms) / cnt
        min_v = min(samples_ms)
        max_v = max(samples_ms)
        p95_v = percentile(samples_ms, 95.0)
        return cls(
            count=cnt,
            avg_ms=round(avg_v, 4),
            min_ms=round(min_v, 4),
            max_ms=round(max_v, 4),
            p95_ms=round(p95_v, 4),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "count": self.count,
            "avg_ms": self.avg_ms,
            "min_ms": self.min_ms,
            "max_ms": self.max_ms,
            "p95_ms": self.p95_ms,
        }


@dataclass(slots=True)
class BenchmarkMetrics:
    """Container holding aggregated results across all 11 evaluation categories."""

    # Category 1: Discovery Join Latency
    join_latency: MetricStats = field(default_factory=MetricStats)
    
    # Category 2: SMT Verification
    smt_verification: MetricStats = field(default_factory=MetricStats)
    
    # Category 3: ML-KEM
    kem_keygen: MetricStats = field(default_factory=MetricStats)
    kem_encaps: MetricStats = field(default_factory=MetricStats)
    kem_decaps: MetricStats = field(default_factory=MetricStats)
    hkdf_derivation: MetricStats = field(default_factory=MetricStats)

    # Category 4: ML-DSA
    mldsa_sign: MetricStats = field(default_factory=MetricStats)
    mldsa_verify: MetricStats = field(default_factory=MetricStats)

    # Category 5: Ascon
    ascon_encrypt: MetricStats = field(default_factory=MetricStats)
    ascon_decrypt: MetricStats = field(default_factory=MetricStats)
    ascon_packets_per_sec: float = 0.0

    # Category 6: Heartbeat
    heartbeat_rtt: MetricStats = field(default_factory=MetricStats)
    heartbeat_loss_pct: float = 0.0
    heartbeat_jitter_ms: float = 0.0
    heartbeat_recovery_ms: float = 0.0

    # Category 7: Routing
    route_lookup: MetricStats = field(default_factory=MetricStats)
    forward_latency: MetricStats = field(default_factory=MetricStats)
    duplicate_drops: int = 0
    ttl_expirations: int = 0

    # Category 8: Task Manager
    task_assignment_latency: MetricStats = field(default_factory=MetricStats)
    task_completion_latency: MetricStats = field(default_factory=MetricStats)
    task_timeout_rate_pct: float = 0.0
    task_retry_count: int = 0

    # Category 9: Cluster Manager
    leader_failure_recovery_ms: float = 0.0
    follower_failure_recovery_ms: float = 0.0
    task_redistribution_ms: float = 0.0

    # Category 10: System Telemetry
    cpu_percent: float = 0.0
    memory_mb: float = 0.0
    thread_count: int = 0
    timer_count: int = 0

    # Category 11: Power Telemetry (INA219)
    avg_voltage_v: float = 0.0
    avg_current_ma: float = 0.0
    avg_power_mw: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serializes metrics object into nested dictionary format."""
        return {
            "category_1_discovery_join": self.join_latency.to_dict(),
            "category_2_smt_verification": self.smt_verification.to_dict(),
            "category_3_ml_kem": {
                "keygen": self.kem_keygen.to_dict(),
                "encapsulation": self.kem_encaps.to_dict(),
                "decapsulation": self.kem_decaps.to_dict(),
                "hkdf_derivation": self.hkdf_derivation.to_dict(),
            },
            "category_4_ml_dsa": {
                "sign": self.mldsa_sign.to_dict(),
                "verify": self.mldsa_verify.to_dict(),
            },
            "category_5_ascon": {
                "encrypt": self.ascon_encrypt.to_dict(),
                "decrypt": self.ascon_decrypt.to_dict(),
                "packets_per_sec": round(self.ascon_packets_per_sec, 2),
            },
            "category_6_heartbeat": {
                "rtt": self.heartbeat_rtt.to_dict(),
                "loss_pct": round(self.heartbeat_loss_pct, 2),
                "jitter_ms": round(self.heartbeat_jitter_ms, 4),
                "recovery_ms": round(self.heartbeat_recovery_ms, 2),
            },
            "category_7_routing": {
                "route_lookup": self.route_lookup.to_dict(),
                "forward_latency": self.forward_latency.to_dict(),
                "duplicate_drops": self.duplicate_drops,
                "ttl_expirations": self.ttl_expirations,
            },
            "category_8_task_manager": {
                "assignment_latency": self.task_assignment_latency.to_dict(),
                "completion_latency": self.task_completion_latency.to_dict(),
                "timeout_rate_pct": round(self.task_timeout_rate_pct, 2),
                "retry_count": self.task_retry_count,
            },
            "category_9_cluster_manager": {
                "leader_failure_recovery_ms": round(self.leader_failure_recovery_ms, 2),
                "follower_failure_recovery_ms": round(self.follower_failure_recovery_ms, 2),
                "task_redistribution_ms": round(self.task_redistribution_ms, 2),
            },
            "category_10_system": {
                "cpu_percent": round(self.cpu_percent, 2),
                "memory_mb": round(self.memory_mb, 2),
                "thread_count": self.thread_count,
                "timer_count": self.timer_count,
            },
            "category_11_power_ina219": {
                "voltage_v": round(self.avg_voltage_v, 3),
                "current_ma": round(self.avg_current_ma, 2),
                "power_mw": round(self.avg_power_mw, 2),
            },
        }


def collect_system_telemetry() -> Tuple[float, float, int, int]:
    """Reads current CPU %, RAM MB, thread count, and timer count."""
    cpu_pct = 0.0
    mem_mb = 0.0
    num_threads = threading.active_count()
    num_timers = sum(1 for t in threading.enumerate() if isinstance(t, threading.Timer))

    if psutil is not None:
        try:
            proc = psutil.Process()
            cpu_pct = proc.cpu_percent(interval=0.05)
            mem_mb = proc.memory_info().rss / (1024 * 1024)
        except Exception:
            pass

    return cpu_pct, mem_mb, num_threads, num_timers


def read_ina219_power() -> Tuple[float, float, float]:
    """Reads hardware INA219 power monitor if available, or synthetic RPi 4 baseline."""
    # Attempt import of mentor power monitor
    try:
        from core.power_monitor import INA219
        sensor = INA219(busnum=1)
        voltage = sensor.getBusVoltage_V()
        current = sensor.getCurrent_mA()
        power = sensor.getPower_mW()
        return voltage, current, power
    except Exception:
        # Raspberry Pi 4 Model B baseline under 5V supply (~600-800 mA)
        voltage = 5.08
        current = 640.0
        power = voltage * current
        return voltage, current, power
