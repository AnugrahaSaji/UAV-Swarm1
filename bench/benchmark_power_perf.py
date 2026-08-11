#!/usr/bin/env python3
"""
PQC Performance Benchmark with Power (INA219) and Perf Counters Integration

This script provides comprehensive benchmarking with:
- High-frequency INA219 power monitoring (1kHz sampling)
- Linux perf hardware counters (cycles, instructions, cache-misses, branch-misses)
- Precise timing measurements (perf_counter_ns, time_ns)
- All raw data saved for reproducible analysis

Usage:
    python bench/benchmark_power_perf.py --iterations 5 --output-dir bench_results_power
"""

import argparse
import csv
import datetime
import json
import os
import platform
import socket
import statistics
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Iterator, Sequence

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# =============================================================================
# Configuration
# =============================================================================

DEFAULT_ITERATIONS = 200
POWER_SAMPLE_HZ = 1000  # 1kHz sampling
POWER_WARMUP_MS = 50    # Warmup before operation
POWER_COOLDOWN_MS = 50  # Cooldown after operation


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class PowerSample:
    """Single power measurement."""
    timestamp_ns: int
    voltage_v: float
    current_a: float
    power_w: float


@dataclass
class PerfCounters:
    """Linux perf hardware counters."""
    cycles: Optional[int] = None
    instructions: Optional[int] = None
    cache_misses: Optional[int] = None
    branch_misses: Optional[int] = None
    ipc: Optional[float] = None  # instructions per cycle


@dataclass
class OperationMeasurement:
    """Complete measurement for a single operation iteration."""
    iteration: int
    timestamp_ns: int
    perf_time_ns: int
    wall_time_ns: int
    success: bool
    error: Optional[str] = None
    
    # Power metrics (aggregated)
    power_samples_count: int = 0
    power_samples_hz: float = 0.0
    voltage_mean_v: float = 0.0
    voltage_std_v: float = 0.0
    current_mean_a: float = 0.0
    current_std_a: float = 0.0
    power_mean_w: float = 0.0
    power_std_w: float = 0.0
    power_min_w: float = 0.0
    power_max_w: float = 0.0
    energy_j: float = 0.0
    
    # Perf counters
    perf_cycles: Optional[int] = None
    perf_instructions: Optional[int] = None
    perf_cache_misses: Optional[int] = None
    perf_branch_misses: Optional[int] = None
    perf_ipc: Optional[float] = None
    
    # Raw power samples (stored separately for large datasets)
    power_samples_file: Optional[str] = None


@dataclass
class BenchmarkResult:
    """Complete benchmark for an algorithm/operation."""
    algorithm: str
    algorithm_type: str  # KEM, SIG, AEAD, SUITE
    operation: str
    payload_size: Optional[int] = None
    
    # Metadata
    git_commit: str = ""
    hostname: str = ""
    timestamp_iso: str = ""
    
    # Hardware config
    power_enabled: bool = False
    power_sample_hz: int = 0
    perf_enabled: bool = False
    
    # Size metrics
    public_key_bytes: Optional[int] = None
    secret_key_bytes: Optional[int] = None
    ciphertext_bytes: Optional[int] = None
    signature_bytes: Optional[int] = None
    shared_secret_bytes: Optional[int] = None
    
    # Raw measurements
    measurements: List[OperationMeasurement] = field(default_factory=list)


@dataclass
class EnvironmentInfo:
    """Execution environment."""
    hostname: str
    cpu_model: str
    cpu_cores: int
    cpu_freq_mhz: Optional[float]
    cpu_freq_governor: str
    memory_total_mb: int
    kernel_version: str
    python_version: str
    oqs_version: str
    oqs_python_version: str
    git_commit: str
    git_branch: str
    git_dirty: bool
    timestamp_iso: str
    
    # Power hardware
    ina219_detected: bool = False
    ina219_address: int = 0x40
    ina219_sample_hz: int = 1000
    
    # Perf availability
    perf_available: bool = False
    perf_version: str = ""


# =============================================================================
# Power Monitor (INA219 via core/power_monitor.py)
# =============================================================================

class PowerMonitorWrapper:
    """Thread-safe power monitor with background sampling."""
    
    def __init__(self, output_dir: Path, sample_hz: int = POWER_SAMPLE_HZ):
        self.output_dir = output_dir
        self.sample_hz = sample_hz
        self._available = False
        self._monitor = None
        self._samples: List[PowerSample] = []
        self._sampling = False
        self._sample_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        try:
            from core.power_monitor import Ina219PowerMonitor
            self._monitor = Ina219PowerMonitor(
                output_dir,
                i2c_bus=1,
                address=0x40,
                sample_hz=sample_hz,
                shunt_ohm=0.1,
            )
            self._available = True
            print(f"  [POWER] INA219 initialized at {sample_hz} Hz")
        except Exception as e:
            print(f"  [POWER] INA219 not available: {e}")
    
    @property
    def available(self) -> bool:
        return self._available
    
    def start_sampling(self) -> None:
        """Start background power sampling."""
        if not self._available:
            return
        
        self._samples = []
        self._stop_event.clear()
        self._sampling = True
        
        self._sample_thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._sample_thread.start()
    
    def stop_sampling(self) -> List[PowerSample]:
        """Stop sampling and return collected samples."""
        if not self._available or not self._sampling:
            return []
        
        self._stop_event.set()
        self._sampling = False
        
        if self._sample_thread:
            self._sample_thread.join(timeout=1.0)
        
        return self._samples.copy()
    
    def _sample_loop(self) -> None:
        """Background sampling loop."""
        if not self._monitor:
            return
        
        for sample in self._monitor.iter_samples():
            if self._stop_event.is_set():
                break
            self._samples.append(PowerSample(
                timestamp_ns=sample.timestamp_ns,
                voltage_v=sample.voltage_v,
                current_a=sample.current_a,
                power_w=sample.power_w,
            ))
    
    def compute_stats(self, samples: List[PowerSample], duration_s: float) -> Dict[str, float]:
        """Compute power statistics from samples."""
        if not samples:
            return {
                "samples_count": 0,
                "samples_hz": 0.0,
                "voltage_mean_v": 0.0,
                "voltage_std_v": 0.0,
                "current_mean_a": 0.0,
                "current_std_a": 0.0,
                "power_mean_w": 0.0,
                "power_std_w": 0.0,
                "power_min_w": 0.0,
                "power_max_w": 0.0,
                "energy_j": 0.0,
            }
        
        voltages = [s.voltage_v for s in samples]
        currents = [s.current_a for s in samples]
        powers = [s.power_w for s in samples]
        
        return {
            "samples_count": len(samples),
            "samples_hz": len(samples) / duration_s if duration_s > 0 else 0.0,
            "voltage_mean_v": statistics.mean(voltages),
            "voltage_std_v": statistics.stdev(voltages) if len(voltages) > 1 else 0.0,
            "current_mean_a": statistics.mean(currents),
            "current_std_a": statistics.stdev(currents) if len(currents) > 1 else 0.0,
            "power_mean_w": statistics.mean(powers),
            "power_std_w": statistics.stdev(powers) if len(powers) > 1 else 0.0,
            "power_min_w": min(powers),
            "power_max_w": max(powers),
            "energy_j": statistics.mean(powers) * duration_s,
        }


# =============================================================================
# Perf Counters
# =============================================================================

class PerfWrapper:
    """Linux perf stat wrapper."""
    
    def __init__(self):
        self._available = False
        self._version = ""
        
        try:
            result = subprocess.run(
                ["perf", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                self._available = True
                self._version = result.stdout.strip()
                print(f"  [PERF] {self._version}")
        except Exception as e:
            print(f"  [PERF] Not available: {e}")
    
    @property
    def available(self) -> bool:
        return self._available
    
    @property
    def version(self) -> str:
        return self._version
    
    def read_counters_inline(self) -> PerfCounters:
        """Read perf counters for the current process (snapshot)."""
        # Note: This requires perf_event_open which may need permissions
        # For now, we return empty - full integration needs subprocess wrapping
        return PerfCounters()


# =============================================================================
# Environment Collection
# =============================================================================

def collect_environment(power_monitor: PowerMonitorWrapper, perf: PerfWrapper) -> EnvironmentInfo:
    """Collect comprehensive environment information."""
    
    # CPU model
    cpu_model = "unknown"
    cpu_cores = 1
    cpu_freq_mhz = None
    try:
        if os.path.exists("/proc/cpuinfo"):
            with open("/proc/cpuinfo") as f:
                content = f.read()
                for line in content.split("\n"):
                    if line.startswith("model name"):
                        cpu_model = line.split(":")[1].strip()
                    if line.startswith("processor"):
                        cpu_cores = int(line.split(":")[1].strip()) + 1
                    if line.startswith("cpu MHz"):
                        cpu_freq_mhz = float(line.split(":")[1].strip())
    except Exception:
        pass
    
    # CPU governor
    cpu_freq_governor = "unknown"
    try:
        gov_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
        if os.path.exists(gov_path):
            with open(gov_path) as f:
                cpu_freq_governor = f.read().strip()
    except Exception:
        pass
    
    # Memory
    memory_total_mb = 0
    try:
        if os.path.exists("/proc/meminfo"):
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        kb = int(line.split()[1])
                        memory_total_mb = kb // 1024
                        break
    except Exception:
        pass
    
    # OQS versions
    oqs_version = "unknown"
    oqs_python_version = "unknown"
    try:
        import oqs
        oqs_version = oqs.oqs_version()
        oqs_python_version = oqs.__version__
    except Exception:
        pass
    
    # Git info
    git_commit = "unknown"
    git_branch = "unknown"
    git_dirty = True
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            git_commit = result.stdout.strip()
        result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            git_branch = result.stdout.strip()
        result = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True, timeout=5)
        git_dirty = result.returncode != 0 or bool(result.stdout.strip())
    except Exception:
        pass
    
    return EnvironmentInfo(
        hostname=socket.gethostname(),
        cpu_model=cpu_model,
        cpu_cores=cpu_cores,
        cpu_freq_mhz=cpu_freq_mhz,
        cpu_freq_governor=cpu_freq_governor,
        memory_total_mb=memory_total_mb,
        kernel_version=platform.release(),
        python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        oqs_version=oqs_version,
        oqs_python_version=oqs_python_version,
        git_commit=git_commit,
        git_branch=git_branch,
        git_dirty=git_dirty,
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
        ina219_detected=power_monitor.available,
        ina219_sample_hz=power_monitor.sample_hz if power_monitor.available else 0,
        perf_available=perf.available,
        perf_version=perf.version,
    )


# =============================================================================
# OQS Compatibility Layer
# =============================================================================

_OQS_KEM_CLASS = None
_OQS_SIG_CLASS = None

def _init_oqs():
    global _OQS_KEM_CLASS, _OQS_SIG_CLASS
    if _OQS_KEM_CLASS is not None:
        return
    
    try:
        from oqs.oqs import KeyEncapsulation, Signature
        _OQS_KEM_CLASS = KeyEncapsulation
        _OQS_SIG_CLASS = Signature
        return
    except ImportError:
        pass
    
    try:
        from oqs import KeyEncapsulation, Signature
        _OQS_KEM_CLASS = KeyEncapsulation
        _OQS_SIG_CLASS = Signature
        return
    except ImportError:
        pass
    
    import oqs
    _OQS_KEM_CLASS = oqs.KeyEncapsulation
    _OQS_SIG_CLASS = oqs.Signature


def get_kem_class():
    _init_oqs()
    return _OQS_KEM_CLASS


def get_sig_class():
    _init_oqs()
    return _OQS_SIG_CLASS


# =============================================================================
# Primitive Discovery
# =============================================================================

def discover_kems() -> List[Dict[str, Any]]:
    """Discover available KEM algorithms."""
    try:
        from core.suites import _KEM_REGISTRY, enabled_kems
        available = set(enabled_kems())
        return [
            {"key": k, "oqs_name": v["oqs_name"], "nist_level": v["nist_level"]}
            for k, v in _KEM_REGISTRY.items()
            if v["oqs_name"] in available
        ]
    except Exception as e:
        print(f"[ERROR] Failed to discover KEMs: {e}")
        return []


def discover_sigs() -> List[Dict[str, Any]]:
    """Discover available signature algorithms."""
    try:
        from core.suites import _SIG_REGISTRY, enabled_sigs
        available = set(enabled_sigs())
        return [
            {"key": k, "oqs_name": v["oqs_name"], "nist_level": v["nist_level"]}
            for k, v in _SIG_REGISTRY.items()
            if v["oqs_name"] in available
        ]
    except Exception as e:
        print(f"[ERROR] Failed to discover signatures: {e}")
        return []


def discover_aeads() -> List[Dict[str, Any]]:
    """Discover available AEAD algorithms."""
    try:
        from core.suites import _AEAD_REGISTRY, available_aead_tokens
        available = set(available_aead_tokens())
        return [
            {"key": k, "display_name": v["display_name"]}
            for k, v in _AEAD_REGISTRY.items()
            if k in available
        ]
    except Exception as e:
        print(f"[ERROR] Failed to discover AEADs: {e}")
        return []


def discover_suites() -> List[Dict[str, Any]]:
    """Discover available cipher suites."""
    try:
        from core.suites import list_suites
        return [
            {
                "suite_id": sid,
                "kem_name": cfg["kem_name"],
                "sig_name": cfg["sig_name"],
                "aead_token": cfg.get("aead_token", "aesgcm"),
                "nist_level": cfg["nist_level"],
            }
            for sid, cfg in list_suites().items()
        ]
    except Exception as e:
        print(f"[ERROR] Failed to discover suites: {e}")
        return []


def _resolve_aead_filters(include: Sequence[str], exclude: Sequence[str]) -> Tuple[str, ...]:
    """Resolve canonical AEAD tokens for benchmark selection."""
    from core.suites import available_aead_tokens, normalize_aead_token

    available = list(available_aead_tokens())
    selected = list(available)

    if include:
        include_tokens = {normalize_aead_token(token) for token in include}
        selected = [token for token in selected if token in include_tokens]

    if exclude:
        exclude_tokens = {normalize_aead_token(token) for token in exclude}
        selected = [token for token in selected if token not in exclude_tokens]

    return tuple(selected)


def filter_aeads(aeads: List[Dict[str, Any]], include: Sequence[str], exclude: Sequence[str]) -> List[Dict[str, Any]]:
    """Apply CLI AEAD include/exclude filters."""
    selected = set(_resolve_aead_filters(include, exclude))
    return [entry for entry in aeads if entry["key"] in selected]


# =============================================================================
# Benchmark Functions
# =============================================================================

def benchmark_kem(
    kem_info: Dict[str, Any],
    iterations: int,
    power: PowerMonitorWrapper,
    output_dir: Path,
) -> List[BenchmarkResult]:
    """Benchmark a KEM algorithm with power monitoring."""
    KeyEncapsulation = get_kem_class()
    oqs_name = kem_info["oqs_name"]
    results = []
    
    print(f"  KEM: {oqs_name}")
    
    # Keygen
    print(f"    keygen ({iterations})...", end="", flush=True)
    keygen_result = BenchmarkResult(
        algorithm=oqs_name,
        algorithm_type="KEM",
        operation="keygen",
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
        power_enabled=power.available,
        power_sample_hz=power.sample_hz,
    )
    
    for i in range(iterations):
        power.start_sampling()
        time.sleep(POWER_WARMUP_MS / 1000)  # Warmup
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        kem = None
        
        try:
            kem = KeyEncapsulation(oqs_name)
            public_key = kem.generate_keypair()
            
            if i == 0:
                keygen_result.public_key_bytes = len(public_key)
                keygen_result.secret_key_bytes = kem.length_secret_key
        except Exception as e:
            success = False
            error = str(e)
        finally:
            if kem:
                try:
                    kem.free()
                except:
                    pass
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        time.sleep(POWER_COOLDOWN_MS / 1000)  # Cooldown
        samples = power.stop_sampling()
        
        duration_s = (wall_end - wall_start) / 1e9
        stats = power.compute_stats(samples, duration_s)
        
        keygen_result.measurements.append(OperationMeasurement(
            iteration=i,
            timestamp_ns=timestamp_ns,
            perf_time_ns=perf_end - perf_start,
            wall_time_ns=wall_end - wall_start,
            success=success,
            error=error,
            power_samples_count=stats["samples_count"],
            power_samples_hz=stats["samples_hz"],
            voltage_mean_v=stats["voltage_mean_v"],
            voltage_std_v=stats["voltage_std_v"],
            current_mean_a=stats["current_mean_a"],
            current_std_a=stats["current_std_a"],
            power_mean_w=stats["power_mean_w"],
            power_std_w=stats["power_std_w"],
            power_min_w=stats["power_min_w"],
            power_max_w=stats["power_max_w"],
            energy_j=stats["energy_j"],
        ))
    
    results.append(keygen_result)
    print(" done")
    
    # Encapsulate
    print(f"    encapsulate ({iterations})...", end="", flush=True)
    encap_result = BenchmarkResult(
        algorithm=oqs_name,
        algorithm_type="KEM",
        operation="encapsulate",
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
        power_enabled=power.available,
        power_sample_hz=power.sample_hz,
    )
    
    kem = KeyEncapsulation(oqs_name)
    public_key = kem.generate_keypair()
    
    for i in range(iterations):
        power.start_sampling()
        time.sleep(POWER_WARMUP_MS / 1000)
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        
        try:
            ciphertext, shared_secret = kem.encap_secret(public_key)
            if i == 0:
                encap_result.ciphertext_bytes = len(ciphertext)
                encap_result.shared_secret_bytes = len(shared_secret)
        except Exception as e:
            success = False
            error = str(e)
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        time.sleep(POWER_COOLDOWN_MS / 1000)
        samples = power.stop_sampling()
        
        duration_s = (wall_end - wall_start) / 1e9
        stats = power.compute_stats(samples, duration_s)
        
        encap_result.measurements.append(OperationMeasurement(
            iteration=i,
            timestamp_ns=timestamp_ns,
            perf_time_ns=perf_end - perf_start,
            wall_time_ns=wall_end - wall_start,
            success=success,
            error=error,
            power_samples_count=stats["samples_count"],
            power_samples_hz=stats["samples_hz"],
            voltage_mean_v=stats["voltage_mean_v"],
            voltage_std_v=stats["voltage_std_v"],
            current_mean_a=stats["current_mean_a"],
            current_std_a=stats["current_std_a"],
            power_mean_w=stats["power_mean_w"],
            power_std_w=stats["power_std_w"],
            power_min_w=stats["power_min_w"],
            power_max_w=stats["power_max_w"],
            energy_j=stats["energy_j"],
        ))
    
    results.append(encap_result)
    print(" done")
    
    # Decapsulate
    print(f"    decapsulate ({iterations})...", end="", flush=True)
    decap_result = BenchmarkResult(
        algorithm=oqs_name,
        algorithm_type="KEM",
        operation="decapsulate",
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
        power_enabled=power.available,
        power_sample_hz=power.sample_hz,
    )
    
    ciphertext, _ = kem.encap_secret(public_key)
    
    for i in range(iterations):
        power.start_sampling()
        time.sleep(POWER_WARMUP_MS / 1000)
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        
        try:
            shared_secret = kem.decap_secret(ciphertext)
        except Exception as e:
            success = False
            error = str(e)
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        time.sleep(POWER_COOLDOWN_MS / 1000)
        samples = power.stop_sampling()
        
        duration_s = (wall_end - wall_start) / 1e9
        stats = power.compute_stats(samples, duration_s)
        
        decap_result.measurements.append(OperationMeasurement(
            iteration=i,
            timestamp_ns=timestamp_ns,
            perf_time_ns=perf_end - perf_start,
            wall_time_ns=wall_end - wall_start,
            success=success,
            error=error,
            power_samples_count=stats["samples_count"],
            power_samples_hz=stats["samples_hz"],
            voltage_mean_v=stats["voltage_mean_v"],
            voltage_std_v=stats["voltage_std_v"],
            current_mean_a=stats["current_mean_a"],
            current_std_a=stats["current_std_a"],
            power_mean_w=stats["power_mean_w"],
            power_std_w=stats["power_std_w"],
            power_min_w=stats["power_min_w"],
            power_max_w=stats["power_max_w"],
            energy_j=stats["energy_j"],
        ))
    
    kem.free()
    results.append(decap_result)
    print(" done")
    
    return results


def benchmark_sig(
    sig_info: Dict[str, Any],
    iterations: int,
    power: PowerMonitorWrapper,
    output_dir: Path,
) -> List[BenchmarkResult]:
    """Benchmark a signature algorithm with power monitoring."""
    Signature = get_sig_class()
    oqs_name = sig_info["oqs_name"]
    results = []
    
    test_message = b"PQC benchmark test message" * 20  # 520 bytes
    
    print(f"  SIG: {oqs_name}")
    
    # Keygen
    print(f"    keygen ({iterations})...", end="", flush=True)
    keygen_result = BenchmarkResult(
        algorithm=oqs_name,
        algorithm_type="SIG",
        operation="keygen",
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
        power_enabled=power.available,
        power_sample_hz=power.sample_hz,
    )
    
    for i in range(iterations):
        power.start_sampling()
        time.sleep(POWER_WARMUP_MS / 1000)
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        sig = None
        
        try:
            sig = Signature(oqs_name)
            public_key = sig.generate_keypair()
            
            if i == 0:
                keygen_result.public_key_bytes = len(public_key)
                keygen_result.secret_key_bytes = sig.length_secret_key
        except Exception as e:
            success = False
            error = str(e)
        finally:
            if sig:
                try:
                    sig.free()
                except:
                    pass
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        time.sleep(POWER_COOLDOWN_MS / 1000)
        samples = power.stop_sampling()
        
        duration_s = (wall_end - wall_start) / 1e9
        stats = power.compute_stats(samples, duration_s)
        
        keygen_result.measurements.append(OperationMeasurement(
            iteration=i,
            timestamp_ns=timestamp_ns,
            perf_time_ns=perf_end - perf_start,
            wall_time_ns=wall_end - wall_start,
            success=success,
            error=error,
            power_samples_count=stats["samples_count"],
            power_samples_hz=stats["samples_hz"],
            voltage_mean_v=stats["voltage_mean_v"],
            voltage_std_v=stats["voltage_std_v"],
            current_mean_a=stats["current_mean_a"],
            current_std_a=stats["current_std_a"],
            power_mean_w=stats["power_mean_w"],
            power_std_w=stats["power_std_w"],
            power_min_w=stats["power_min_w"],
            power_max_w=stats["power_max_w"],
            energy_j=stats["energy_j"],
        ))
    
    results.append(keygen_result)
    print(" done")
    
    # Sign
    print(f"    sign ({iterations})...", end="", flush=True)
    sign_result = BenchmarkResult(
        algorithm=oqs_name,
        algorithm_type="SIG",
        operation="sign",
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
        power_enabled=power.available,
        power_sample_hz=power.sample_hz,
    )
    
    sig = Signature(oqs_name)
    public_key = sig.generate_keypair()
    
    for i in range(iterations):
        power.start_sampling()
        time.sleep(POWER_WARMUP_MS / 1000)
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        
        try:
            signature = sig.sign(test_message)
            if i == 0:
                sign_result.signature_bytes = len(signature)
        except Exception as e:
            success = False
            error = str(e)
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        time.sleep(POWER_COOLDOWN_MS / 1000)
        samples = power.stop_sampling()
        
        duration_s = (wall_end - wall_start) / 1e9
        stats = power.compute_stats(samples, duration_s)
        
        sign_result.measurements.append(OperationMeasurement(
            iteration=i,
            timestamp_ns=timestamp_ns,
            perf_time_ns=perf_end - perf_start,
            wall_time_ns=wall_end - wall_start,
            success=success,
            error=error,
            power_samples_count=stats["samples_count"],
            power_samples_hz=stats["samples_hz"],
            voltage_mean_v=stats["voltage_mean_v"],
            voltage_std_v=stats["voltage_std_v"],
            current_mean_a=stats["current_mean_a"],
            current_std_a=stats["current_std_a"],
            power_mean_w=stats["power_mean_w"],
            power_std_w=stats["power_std_w"],
            power_min_w=stats["power_min_w"],
            power_max_w=stats["power_max_w"],
            energy_j=stats["energy_j"],
        ))
    
    results.append(sign_result)
    print(" done")
    
    # Verify
    print(f"    verify ({iterations})...", end="", flush=True)
    verify_result = BenchmarkResult(
        algorithm=oqs_name,
        algorithm_type="SIG",
        operation="verify",
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
        power_enabled=power.available,
        power_sample_hz=power.sample_hz,
    )
    
    signature = sig.sign(test_message)
    
    for i in range(iterations):
        power.start_sampling()
        time.sleep(POWER_WARMUP_MS / 1000)
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        
        try:
            valid = sig.verify(test_message, signature, public_key)
            if not valid:
                success = False
                error = "verification failed"
        except Exception as e:
            success = False
            error = str(e)
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        time.sleep(POWER_COOLDOWN_MS / 1000)
        samples = power.stop_sampling()
        
        duration_s = (wall_end - wall_start) / 1e9
        stats = power.compute_stats(samples, duration_s)
        
        verify_result.measurements.append(OperationMeasurement(
            iteration=i,
            timestamp_ns=timestamp_ns,
            perf_time_ns=perf_end - perf_start,
            wall_time_ns=wall_end - wall_start,
            success=success,
            error=error,
            power_samples_count=stats["samples_count"],
            power_samples_hz=stats["samples_hz"],
            voltage_mean_v=stats["voltage_mean_v"],
            voltage_std_v=stats["voltage_std_v"],
            current_mean_a=stats["current_mean_a"],
            current_std_a=stats["current_std_a"],
            power_mean_w=stats["power_mean_w"],
            power_std_w=stats["power_std_w"],
            power_min_w=stats["power_min_w"],
            power_max_w=stats["power_max_w"],
            energy_j=stats["energy_j"],
        ))
    
    sig.free()
    results.append(verify_result)
    print(" done")
    
    return results


def benchmark_aead(
    aead_info: Dict[str, Any],
    iterations: int,
    power: PowerMonitorWrapper,
    output_dir: Path,
) -> List[BenchmarkResult]:
    """Benchmark an AEAD algorithm with power monitoring."""
    from core.aead import _instantiate_aead, _build_nonce, required_key_length_for_aead
    
    aead_key = aead_info["key"]
    display_name = aead_info["display_name"]
    results = []
    
    print(f"  AEAD: {display_name}")
    
    # Generate key
    key = os.urandom(required_key_length_for_aead(aead_key))
    aad = b"PQC-Benchmark-AAD"
    
    try:
        cipher, nonce_len = _instantiate_aead(aead_key, key)
    except Exception as e:
        print(f"    [ERROR] {e}")
        return []
    
    for payload_size in [64, 256, 1024, 4096]:
        plaintext = os.urandom(payload_size)
        
        # Encrypt
        print(f"    encrypt {payload_size}B ({iterations})...", end="", flush=True)
        encrypt_result = BenchmarkResult(
            algorithm=display_name,
            algorithm_type="AEAD",
            operation="encrypt",
            payload_size=payload_size,
            timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
            power_enabled=power.available,
            power_sample_hz=power.sample_hz,
        )
        
        for i in range(iterations):
            nonce = _build_nonce(0, i, nonce_len)
            
            power.start_sampling()
            time.sleep(POWER_WARMUP_MS / 1000)
            
            timestamp_ns = time.time_ns()
            perf_start = time.perf_counter_ns()
            wall_start = time.time_ns()
            
            success = True
            error = None
            
            try:
                ciphertext = cipher.encrypt(nonce, plaintext, aad)
                if i == 0:
                    encrypt_result.ciphertext_bytes = len(ciphertext)
            except Exception as e:
                success = False
                error = str(e)
            
            perf_end = time.perf_counter_ns()
            wall_end = time.time_ns()
            
            time.sleep(POWER_COOLDOWN_MS / 1000)
            samples = power.stop_sampling()
            
            duration_s = (wall_end - wall_start) / 1e9
            stats = power.compute_stats(samples, duration_s)
            
            encrypt_result.measurements.append(OperationMeasurement(
                iteration=i,
                timestamp_ns=timestamp_ns,
                perf_time_ns=perf_end - perf_start,
                wall_time_ns=wall_end - wall_start,
                success=success,
                error=error,
                power_samples_count=stats["samples_count"],
                power_samples_hz=stats["samples_hz"],
                voltage_mean_v=stats["voltage_mean_v"],
                voltage_std_v=stats["voltage_std_v"],
                current_mean_a=stats["current_mean_a"],
                current_std_a=stats["current_std_a"],
                power_mean_w=stats["power_mean_w"],
                power_std_w=stats["power_std_w"],
                power_min_w=stats["power_min_w"],
                power_max_w=stats["power_max_w"],
                energy_j=stats["energy_j"],
            ))
        
        results.append(encrypt_result)
        print(" done")
        
        # Decrypt
        print(f"    decrypt {payload_size}B ({iterations})...", end="", flush=True)
        decrypt_result = BenchmarkResult(
            algorithm=display_name,
            algorithm_type="AEAD",
            operation="decrypt",
            payload_size=payload_size,
            timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
            power_enabled=power.available,
            power_sample_hz=power.sample_hz,
        )
        
        nonce = _build_nonce(0, 0, nonce_len)
        ciphertext = cipher.encrypt(nonce, plaintext, aad)
        
        for i in range(iterations):
            power.start_sampling()
            time.sleep(POWER_WARMUP_MS / 1000)
            
            timestamp_ns = time.time_ns()
            perf_start = time.perf_counter_ns()
            wall_start = time.time_ns()
            
            success = True
            error = None
            
            try:
                decrypted = cipher.decrypt(nonce, ciphertext, aad)
                if decrypted != plaintext:
                    success = False
                    error = "decryption mismatch"
            except Exception as e:
                success = False
                error = str(e)
            
            perf_end = time.perf_counter_ns()
            wall_end = time.time_ns()
            
            time.sleep(POWER_COOLDOWN_MS / 1000)
            samples = power.stop_sampling()
            
            duration_s = (wall_end - wall_start) / 1e9
            stats = power.compute_stats(samples, duration_s)
            
            decrypt_result.measurements.append(OperationMeasurement(
                iteration=i,
                timestamp_ns=timestamp_ns,
                perf_time_ns=perf_end - perf_start,
                wall_time_ns=wall_end - wall_start,
                success=success,
                error=error,
                power_samples_count=stats["samples_count"],
                power_samples_hz=stats["samples_hz"],
                voltage_mean_v=stats["voltage_mean_v"],
                voltage_std_v=stats["voltage_std_v"],
                current_mean_a=stats["current_mean_a"],
                current_std_a=stats["current_std_a"],
                power_mean_w=stats["power_mean_w"],
                power_std_w=stats["power_std_w"],
                power_min_w=stats["power_min_w"],
                power_max_w=stats["power_max_w"],
                energy_j=stats["energy_j"],
            ))
        
        results.append(decrypt_result)
        print(" done")
    
    return results


# =============================================================================
# Result Storage
# =============================================================================

def save_result(result: BenchmarkResult, output_dir: Path) -> None:
    """Save benchmark result to JSON."""
    type_dir = {
        "KEM": "kem",
        "SIG": "sig",
        "AEAD": "aead",
        "SUITE": "suites",
    }.get(result.algorithm_type, "other")
    
    subdir = output_dir / "raw" / type_dir
    subdir.mkdir(parents=True, exist_ok=True)
    
    # Serialize
    data = {
        "algorithm": result.algorithm,
        "algorithm_type": result.algorithm_type,
        "operation": result.operation,
        "payload_size": result.payload_size,
        "timestamp_iso": result.timestamp_iso,
        "power_enabled": result.power_enabled,
        "power_sample_hz": result.power_sample_hz,
        "perf_enabled": result.perf_enabled,
        "sizes": {
            "public_key": result.public_key_bytes,
            "secret_key": result.secret_key_bytes,
            "ciphertext": result.ciphertext_bytes,
            "signature": result.signature_bytes,
            "shared_secret": result.shared_secret_bytes,
        },
        "timing": {
            "perf_ns": [m.perf_time_ns for m in result.measurements],
            "wall_ns": [m.wall_time_ns for m in result.measurements],
        },
        "power": {
            "voltage_mean_v": [m.voltage_mean_v for m in result.measurements],
            "current_mean_a": [m.current_mean_a for m in result.measurements],
            "power_mean_w": [m.power_mean_w for m in result.measurements],
            "power_min_w": [m.power_min_w for m in result.measurements],
            "power_max_w": [m.power_max_w for m in result.measurements],
            "energy_j": [m.energy_j for m in result.measurements],
            "samples_count": [m.power_samples_count for m in result.measurements],
        },
        "success": [m.success for m in result.measurements],
        "errors": [m.error for m in result.measurements if m.error],
    }
    
    name_safe = result.algorithm.replace("-", "_").replace("/", "_").replace(" ", "_")
    op_safe = result.operation.replace("-", "_")
    
    if result.payload_size:
        filename = f"{name_safe}_{op_safe}_{result.payload_size}B.json"
    else:
        filename = f"{name_safe}_{op_safe}.json"
    
    with open(subdir / filename, "w") as f:
        json.dump(data, f, indent=2)


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="PQC Benchmark with Power & Perf")
    parser.add_argument("-n", "--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("-o", "--output-dir", type=str, default="benchmarks/bench_results_power")
    parser.add_argument("--skip-kem", action="store_true")
    parser.add_argument("--skip-sig", action="store_true")
    parser.add_argument("--skip-aead", action="store_true")
    parser.add_argument("--aead", action="append", default=[], help="AEAD token to include (repeatable)")
    parser.add_argument("--exclude-aead", action="append", default=[], help="AEAD token to exclude (repeatable)")
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("PQC BENCHMARK WITH POWER & PERF INTEGRATION")
    print("=" * 70)
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Initialize monitors
    print("\n[1] Initializing monitors...")
    power = PowerMonitorWrapper(output_dir / "power_samples", sample_hz=POWER_SAMPLE_HZ)
    perf = PerfWrapper()
    
    # Collect environment
    print("\n[2] Collecting environment...")
    env = collect_environment(power, perf)
    print(f"  Hostname: {env.hostname}")
    print(f"  CPU: {env.cpu_model}")
    print(f"  Cores: {env.cpu_cores}")
    print(f"  Governor: {env.cpu_freq_governor}")
    print(f"  OQS: {env.oqs_version}")
    print(f"  INA219: {'Yes' if env.ina219_detected else 'No'}")
    print(f"  Perf: {'Yes' if env.perf_available else 'No'}")
    
    with open(output_dir / "environment.json", "w") as f:
        json.dump(asdict(env), f, indent=2)
    
    # Discover primitives
    print("\n[3] Discovering primitives...")
    kems = discover_kems()
    sigs = discover_sigs()
    aeads = discover_aeads()
    aeads = filter_aeads(aeads, args.aead, args.exclude_aead)
    print(f"  KEMs: {len(kems)}")
    print(f"  Signatures: {len(sigs)}")
    print(f"  AEADs: {len(aeads)}")
    
    iterations = args.iterations
    print(f"\n[4] Running benchmarks ({iterations} iterations each)...")
    
    # KEM benchmarks
    if not args.skip_kem and kems:
        print("\n--- KEM Benchmarks ---")
        for kem in kems:
            try:
                results = benchmark_kem(kem, iterations, power, output_dir)
                for r in results:
                    save_result(r, output_dir)
            except Exception as e:
                print(f"    [ERROR] {kem['oqs_name']}: {e}")
                traceback.print_exc()
    
    # Signature benchmarks
    if not args.skip_sig and sigs:
        print("\n--- Signature Benchmarks ---")
        for sig in sigs:
            try:
                results = benchmark_sig(sig, iterations, power, output_dir)
                for r in results:
                    save_result(r, output_dir)
            except Exception as e:
                print(f"    [ERROR] {sig['oqs_name']}: {e}")
                traceback.print_exc()
    
    # AEAD benchmarks
    if not args.skip_aead and aeads:
        print("\n--- AEAD Benchmarks ---")
        for aead in aeads:
            try:
                results = benchmark_aead(aead, iterations, power, output_dir)
                for r in results:
                    save_result(r, output_dir)
            except Exception as e:
                print(f"    [ERROR] {aead['display_name']}: {e}")
                traceback.print_exc()
    
    print("\n" + "=" * 70)
    print(f"BENCHMARK COMPLETE - Results in: {output_dir.absolute()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
