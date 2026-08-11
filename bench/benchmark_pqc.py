#!/usr/bin/env python3
"""
PQC Performance & Power Benchmarking Script

THIS IS A MEASUREMENT-ONLY SCRIPT.
No analysis. No conclusions. No optimization recommendations.

Measures:
- KEMs: keygen, encapsulate, decapsulate
- Signatures: keygen, sign, verify
- AEADs: encrypt, decrypt (multiple payload sizes)
- Full Suites: handshake, proxy startup, packet latency

Requirements:
- 200 iterations per measurement (no warm-up discards)
- INA219 power monitoring (optional but recorded)
- Linux perf counters (optional but recorded)
- Raw data + summary output

Usage:
    python bench/benchmark_pqc.py [--iterations 200] [--output-dir bench_results]
"""

import argparse
import csv
import datetime
import hashlib
import json
import os
import platform
import socket
import statistics
import struct
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Sequence

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# =============================================================================
# OQS Compatibility Layer
# =============================================================================
# oqs-python has different import structures depending on version/installation:
#   - Some installs: from oqs.oqs import KeyEncapsulation, Signature
#   - Some installs: from oqs import KeyEncapsulation, Signature  
#   - Some installs: import oqs; oqs.KeyEncapsulation

_OQS_KEM_CLASS = None
_OQS_SIG_CLASS = None
_OQS_ENABLED_KEMS_FUNC = None
_OQS_ENABLED_SIGS_FUNC = None

def _init_oqs_compat():
    """Initialize OQS compatibility layer."""
    global _OQS_KEM_CLASS, _OQS_SIG_CLASS, _OQS_ENABLED_KEMS_FUNC, _OQS_ENABLED_SIGS_FUNC
    
    if _OQS_KEM_CLASS is not None:
        return  # Already initialized
    
    # Try different import styles
    import_errors = []
    
    # Style 1: from oqs.oqs import ... (some pip installs)
    try:
        from oqs.oqs import KeyEncapsulation, Signature
        _OQS_KEM_CLASS = KeyEncapsulation
        _OQS_SIG_CLASS = Signature
        try:
            from oqs.oqs import get_enabled_KEM_mechanisms
            _OQS_ENABLED_KEMS_FUNC = get_enabled_KEM_mechanisms
        except ImportError:
            from oqs.oqs import get_enabled_kem_mechanisms
            _OQS_ENABLED_KEMS_FUNC = get_enabled_kem_mechanisms
        try:
            from oqs.oqs import get_enabled_sig_mechanisms
            _OQS_ENABLED_SIGS_FUNC = get_enabled_sig_mechanisms
        except ImportError:
            from oqs.oqs import get_enabled_SIG_mechanisms
            _OQS_ENABLED_SIGS_FUNC = get_enabled_SIG_mechanisms
        return
    except ImportError as e:
        import_errors.append(f"oqs.oqs: {e}")
    
    # Style 2: from oqs import ... (some venv/conda installs)
    try:
        from oqs import KeyEncapsulation, Signature
        _OQS_KEM_CLASS = KeyEncapsulation
        _OQS_SIG_CLASS = Signature
        try:
            from oqs import get_enabled_KEM_mechanisms
            _OQS_ENABLED_KEMS_FUNC = get_enabled_KEM_mechanisms
        except ImportError:
            from oqs import get_enabled_kem_mechanisms
            _OQS_ENABLED_KEMS_FUNC = get_enabled_kem_mechanisms
        try:
            from oqs import get_enabled_sig_mechanisms
            _OQS_ENABLED_SIGS_FUNC = get_enabled_sig_mechanisms
        except ImportError:
            from oqs import get_enabled_SIG_mechanisms
            _OQS_ENABLED_SIGS_FUNC = get_enabled_SIG_mechanisms
        return
    except ImportError as e:
        import_errors.append(f"oqs: {e}")
    
    # Style 3: import oqs; oqs.X (attribute access)
    try:
        import oqs
        _OQS_KEM_CLASS = oqs.KeyEncapsulation
        _OQS_SIG_CLASS = oqs.Signature
        if hasattr(oqs, 'get_enabled_KEM_mechanisms'):
            _OQS_ENABLED_KEMS_FUNC = oqs.get_enabled_KEM_mechanisms
        else:
            _OQS_ENABLED_KEMS_FUNC = oqs.get_enabled_kem_mechanisms
        if hasattr(oqs, 'get_enabled_sig_mechanisms'):
            _OQS_ENABLED_SIGS_FUNC = oqs.get_enabled_sig_mechanisms
        else:
            _OQS_ENABLED_SIGS_FUNC = oqs.get_enabled_SIG_mechanisms
        return
    except (ImportError, AttributeError) as e:
        import_errors.append(f"oqs module: {e}")
    
    raise ImportError(f"Could not import OQS library. Tried: {'; '.join(import_errors)}")


def get_oqs_kem_class():
    """Return KeyEncapsulation class."""
    _init_oqs_compat()
    return _OQS_KEM_CLASS


def get_oqs_sig_class():
    """Return Signature class."""
    _init_oqs_compat()
    return _OQS_SIG_CLASS


def get_enabled_kems_func():
    """Return function to get enabled KEM mechanisms."""
    _init_oqs_compat()
    return _OQS_ENABLED_KEMS_FUNC


def get_enabled_sigs_func():
    """Return function to get enabled signature mechanisms."""
    _init_oqs_compat()
    return _OQS_ENABLED_SIGS_FUNC


# =============================================================================
# Configuration Constants
# =============================================================================

DEFAULT_ITERATIONS = 200
AEAD_PAYLOAD_SIZES = [64, 256, 1024, 4096]  # bytes


# =============================================================================
# Data Classes for Results
# =============================================================================

@dataclass
class IterationResult:
    """Single iteration measurement."""
    iteration: int
    timestamp_ns: int
    wall_time_ns: int
    perf_time_ns: int
    success: bool
    error: Optional[str] = None
    
    # Power measurements (optional)
    voltage_v: Optional[float] = None
    current_ma: Optional[float] = None
    power_mw: Optional[float] = None
    energy_mj: Optional[float] = None
    power_samples: List[Dict[str, float]] = field(default_factory=list)
    
    # Perf counters (optional)
    perf_cycles: Optional[int] = None
    perf_instructions: Optional[int] = None
    perf_cache_misses: Optional[int] = None
    perf_branch_misses: Optional[int] = None
    perf_context_switches: Optional[int] = None
    perf_cpu_migrations: Optional[int] = None


@dataclass
class BenchmarkResult:
    """Complete benchmark result for a single operation."""
    algorithm_name: str
    algorithm_type: str  # KEM, SIG, AEAD, SUITE
    operation: str  # keygen, encap, decap, sign, verify, encrypt, decrypt, handshake
    payload_size: Optional[int] = None  # For AEAD only
    
    # Metadata
    git_commit: str = ""
    hostname: str = ""
    timestamp_iso: str = ""
    
    # Raw iterations
    iterations: List[IterationResult] = field(default_factory=list)
    
    # Artifact sizes (bytes)
    public_key_bytes: Optional[int] = None
    secret_key_bytes: Optional[int] = None
    ciphertext_bytes: Optional[int] = None
    signature_bytes: Optional[int] = None
    shared_secret_bytes: Optional[int] = None


@dataclass
class EnvironmentInfo:
    """Execution environment metadata."""
    hostname: str
    cpu_model: str
    cpu_freq_governor: str
    kernel_version: str
    python_version: str
    oqs_version: str
    oqs_python_version: str
    git_commit: str
    git_branch: str
    git_clean: bool
    timestamp_iso: str
    cpu_core_pinned: Optional[int] = None
    ambient_temp_c: Optional[float] = None


# =============================================================================
# Power Monitoring (INA219)
# =============================================================================

class PowerMonitor:
    """INA219 power sensor interface."""
    
    def __init__(self):
        self._available = False
        self._ina = None
        self._samples: List[Dict[str, float]] = []
        self._sampling = False
        
        try:
            from ina219 import INA219
            # Standard shunt resistor value for INA219 breakout boards
            self._ina = INA219(shunt_ohms=0.1, max_expected_amps=3.0)
            self._ina.configure()
            self._available = True
        except Exception:
            pass
    
    @property
    def available(self) -> bool:
        return self._available
    
    def read_once(self) -> Dict[str, Optional[float]]:
        """Read single power measurement."""
        if not self._available or self._ina is None:
            return {"voltage_v": None, "current_ma": None, "power_mw": None}
        
        try:
            voltage = self._ina.voltage()
            current = self._ina.current()
            power = self._ina.power()
            return {
                "voltage_v": voltage,
                "current_ma": current,
                "power_mw": power,
                "timestamp_ns": time.time_ns(),
            }
        except Exception:
            return {"voltage_v": None, "current_ma": None, "power_mw": None}
    
    def start_sampling(self) -> None:
        """Start continuous power sampling."""
        self._samples = []
        self._sampling = True
    
    def stop_sampling(self) -> List[Dict[str, float]]:
        """Stop sampling and return all samples."""
        self._sampling = False
        return self._samples
    
    def sample(self) -> None:
        """Take a single sample if sampling is active."""
        if self._sampling and self._available:
            reading = self.read_once()
            if reading.get("voltage_v") is not None:
                self._samples.append(reading)
    
    def compute_energy(self, samples: List[Dict[str, float]], duration_s: float) -> Optional[float]:
        """Compute energy in millijoules from power samples."""
        if not samples or duration_s <= 0:
            return None
        
        # Average power × time = energy
        powers = [s.get("power_mw", 0) for s in samples if s.get("power_mw") is not None]
        if not powers:
            return None
        
        avg_power_mw = sum(powers) / len(powers)
        energy_mj = avg_power_mw * duration_s  # mW × s = mJ
        return energy_mj


# =============================================================================
# Perf Counters
# =============================================================================

class PerfCounters:
    """Linux perf stat interface."""
    
    def __init__(self):
        self._available = False
        self._events = [
            "cycles",
            "instructions",
            "cache-misses",
            "branch-misses",
            "context-switches",
            "cpu-migrations",
        ]
        
        # Check if perf is available
        try:
            result = subprocess.run(
                ["perf", "stat", "--version"],
                capture_output=True,
                timeout=5,
            )
            self._available = result.returncode == 0
        except Exception:
            pass
    
    @property
    def available(self) -> bool:
        return self._available
    
    def run_with_perf(self, command: List[str], timeout: float = 300) -> Dict[str, Optional[int]]:
        """Run command with perf stat and return counters."""
        if not self._available:
            return {e: None for e in self._events}
        
        events_str = ",".join(self._events)
        perf_cmd = [
            "perf", "stat",
            "-e", events_str,
            "-x", ",",  # CSV output
            "--"
        ] + command
        
        try:
            result = subprocess.run(
                perf_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return self._parse_perf_output(result.stderr)
        except Exception:
            return {e: None for e in self._events}
    
    def _parse_perf_output(self, stderr: str) -> Dict[str, Optional[int]]:
        """Parse perf stat CSV output."""
        counters = {e: None for e in self._events}
        
        for line in stderr.split("\n"):
            parts = line.strip().split(",")
            if len(parts) >= 2:
                try:
                    value = int(parts[0]) if parts[0].isdigit() else None
                    event = parts[2] if len(parts) > 2 else ""
                    
                    for e in self._events:
                        if e in event:
                            counters[e] = value
                            break
                except (ValueError, IndexError):
                    pass
        
        return counters


# =============================================================================
# Environment Collection
# =============================================================================

def collect_environment_info() -> EnvironmentInfo:
    """Collect execution environment metadata."""
    
    # CPU model
    cpu_model = "unknown"
    try:
        if os.path.exists("/proc/cpuinfo"):
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu_model = line.split(":")[1].strip()
                        break
        else:
            cpu_model = platform.processor() or "unknown"
    except Exception:
        pass
    
    # CPU frequency governor
    cpu_freq_governor = "unknown"
    try:
        gov_path = "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
        if os.path.exists(gov_path):
            with open(gov_path) as f:
                cpu_freq_governor = f.read().strip()
    except Exception:
        pass
    
    # Kernel version
    kernel_version = "unknown"
    try:
        kernel_version = platform.release()
    except Exception:
        pass
    
    # Python version
    python_version = sys.version
    
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
    git_clean = False
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            git_commit = result.stdout.strip()
        
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            git_branch = result.stdout.strip()
        
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        git_clean = result.returncode == 0 and not result.stdout.strip()
    except Exception:
        pass
    
    return EnvironmentInfo(
        hostname=socket.gethostname(),
        cpu_model=cpu_model,
        cpu_freq_governor=cpu_freq_governor,
        kernel_version=kernel_version,
        python_version=python_version,
        oqs_version=oqs_version,
        oqs_python_version=oqs_python_version,
        git_commit=git_commit,
        git_branch=git_branch,
        git_clean=git_clean,
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
    )


# =============================================================================
# Primitive Discovery
# =============================================================================

def discover_kems() -> List[Dict[str, Any]]:
    """Discover available KEM algorithms."""
    try:
        from core.suites import _KEM_REGISTRY, enabled_kems
        
        available_oqs = set(enabled_kems())
        kems = []
        
        for key, entry in _KEM_REGISTRY.items():
            oqs_name = entry["oqs_name"]
            if oqs_name in available_oqs:
                kems.append({
                    "key": key,
                    "oqs_name": oqs_name,
                    "nist_level": entry["nist_level"],
                })
        
        return kems
    except Exception as e:
        print(f"[ERROR] Failed to discover KEMs: {e}")
        return []


def discover_signatures() -> List[Dict[str, Any]]:
    """Discover available signature algorithms."""
    try:
        from core.suites import _SIG_REGISTRY, enabled_sigs
        
        available_oqs = set(enabled_sigs())
        sigs = []
        
        for key, entry in _SIG_REGISTRY.items():
            oqs_name = entry["oqs_name"]
            if oqs_name in available_oqs:
                sigs.append({
                    "key": key,
                    "oqs_name": oqs_name,
                    "nist_level": entry["nist_level"],
                })
        
        return sigs
    except Exception as e:
        print(f"[ERROR] Failed to discover signatures: {e}")
        return []


def discover_aeads() -> List[Dict[str, Any]]:
    """Discover available AEAD algorithms."""
    try:
        from core.suites import _AEAD_REGISTRY, available_aead_tokens
        
        available = set(available_aead_tokens())
        aeads = []
        
        for key, entry in _AEAD_REGISTRY.items():
            if key in available:
                aeads.append({
                    "key": key,
                    "display_name": entry["display_name"],
                })
        
        return aeads
    except Exception as e:
        print(f"[ERROR] Failed to discover AEADs: {e}")
        return []


def discover_suites() -> List[Dict[str, Any]]:
    """Discover available cryptographic suites."""
    try:
        from core.suites import list_suites
        
        suites = []
        for suite_id, config in list_suites().items():
            suites.append({
                "suite_id": suite_id,
                "kem_name": config["kem_name"],
                "sig_name": config["sig_name"],
                "aead_token": config.get("aead_token", "aesgcm"),
                "nist_level": config["nist_level"],
            })
        
        return suites
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
# KEM Benchmarks
# =============================================================================

def benchmark_kem(
    kem_info: Dict[str, Any],
    iterations: int,
    power_monitor: PowerMonitor,
    env_info: EnvironmentInfo,
) -> List[BenchmarkResult]:
    """Benchmark a single KEM algorithm."""
    KeyEncapsulation = get_oqs_kem_class()
    
    oqs_name = kem_info["oqs_name"]
    results = []
    
    print(f"  Benchmarking KEM: {oqs_name}")
    
    # Keygen benchmark
    print(f"    keygen ({iterations} iterations)...", end="", flush=True)
    keygen_result = BenchmarkResult(
        algorithm_name=oqs_name,
        algorithm_type="KEM",
        operation="keygen",
        git_commit=env_info.git_commit,
        hostname=env_info.hostname,
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
    )
    
    for i in range(iterations):
        power_monitor.start_sampling()
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        kem = None
        
        try:
            # Sample power during operation
            power_monitor.sample()
            kem = KeyEncapsulation(oqs_name)
            power_monitor.sample()
            public_key = kem.generate_keypair()
            power_monitor.sample()
            
            # Record sizes on first iteration
            if i == 0:
                keygen_result.public_key_bytes = len(public_key)
                keygen_result.secret_key_bytes = kem.length_secret_key
        except Exception as e:
            success = False
            error = str(e)
        finally:
            if kem is not None:
                try:
                    kem.free()
                except Exception:
                    pass
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        samples = power_monitor.stop_sampling()
        duration_s = (wall_end - wall_start) / 1e9
        
        # Compute power metrics
        power_reading = power_monitor.read_once()
        energy_mj = power_monitor.compute_energy(samples, duration_s)
        
        keygen_result.iterations.append(IterationResult(
            iteration=i,
            timestamp_ns=timestamp_ns,
            wall_time_ns=wall_end - wall_start,
            perf_time_ns=perf_end - perf_start,
            success=success,
            error=error,
            voltage_v=power_reading.get("voltage_v"),
            current_ma=power_reading.get("current_ma"),
            power_mw=power_reading.get("power_mw"),
            energy_mj=energy_mj,
            power_samples=samples,
        ))
    
    results.append(keygen_result)
    print(" done")
    
    # Encapsulation benchmark
    print(f"    encapsulate ({iterations} iterations)...", end="", flush=True)
    encap_result = BenchmarkResult(
        algorithm_name=oqs_name,
        algorithm_type="KEM",
        operation="encapsulate",
        git_commit=env_info.git_commit,
        hostname=env_info.hostname,
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
    )
    
    # Generate keypair for encapsulation tests
    kem_for_encap = KeyEncapsulation(oqs_name)
    public_key = kem_for_encap.generate_keypair()
    
    for i in range(iterations):
        power_monitor.start_sampling()
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        
        try:
            power_monitor.sample()
            ciphertext, shared_secret = kem_for_encap.encap_secret(public_key)
            power_monitor.sample()
            
            if i == 0:
                encap_result.ciphertext_bytes = len(ciphertext)
                encap_result.shared_secret_bytes = len(shared_secret)
        except Exception as e:
            success = False
            error = str(e)
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        samples = power_monitor.stop_sampling()
        duration_s = (wall_end - wall_start) / 1e9
        
        power_reading = power_monitor.read_once()
        energy_mj = power_monitor.compute_energy(samples, duration_s)
        
        encap_result.iterations.append(IterationResult(
            iteration=i,
            timestamp_ns=timestamp_ns,
            wall_time_ns=wall_end - wall_start,
            perf_time_ns=perf_end - perf_start,
            success=success,
            error=error,
            voltage_v=power_reading.get("voltage_v"),
            current_ma=power_reading.get("current_ma"),
            power_mw=power_reading.get("power_mw"),
            energy_mj=energy_mj,
            power_samples=samples,
        ))
    
    results.append(encap_result)
    print(" done")
    
    # Decapsulation benchmark
    print(f"    decapsulate ({iterations} iterations)...", end="", flush=True)
    decap_result = BenchmarkResult(
        algorithm_name=oqs_name,
        algorithm_type="KEM",
        operation="decapsulate",
        git_commit=env_info.git_commit,
        hostname=env_info.hostname,
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
    )
    
    # Generate ciphertext for decapsulation tests
    ciphertext_for_decap, _ = kem_for_encap.encap_secret(public_key)
    
    for i in range(iterations):
        power_monitor.start_sampling()
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        
        try:
            power_monitor.sample()
            shared_secret = kem_for_encap.decap_secret(ciphertext_for_decap)
            power_monitor.sample()
        except Exception as e:
            success = False
            error = str(e)
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        samples = power_monitor.stop_sampling()
        duration_s = (wall_end - wall_start) / 1e9
        
        power_reading = power_monitor.read_once()
        energy_mj = power_monitor.compute_energy(samples, duration_s)
        
        decap_result.iterations.append(IterationResult(
            iteration=i,
            timestamp_ns=timestamp_ns,
            wall_time_ns=wall_end - wall_start,
            perf_time_ns=perf_end - perf_start,
            success=success,
            error=error,
            voltage_v=power_reading.get("voltage_v"),
            current_ma=power_reading.get("current_ma"),
            power_mw=power_reading.get("power_mw"),
            energy_mj=energy_mj,
            power_samples=samples,
        ))
    
    kem_for_encap.free()
    results.append(decap_result)
    print(" done")
    
    return results


# =============================================================================
# Signature Benchmarks
# =============================================================================

def benchmark_signature(
    sig_info: Dict[str, Any],
    iterations: int,
    power_monitor: PowerMonitor,
    env_info: EnvironmentInfo,
) -> List[BenchmarkResult]:
    """Benchmark a single signature algorithm."""
    Signature = get_oqs_sig_class()
    
    oqs_name = sig_info["oqs_name"]
    results = []
    
    print(f"  Benchmarking Signature: {oqs_name}")
    
    # Test message
    test_message = b"PQC benchmark test message for signature operations" * 10
    
    # Keygen benchmark
    print(f"    keygen ({iterations} iterations)...", end="", flush=True)
    keygen_result = BenchmarkResult(
        algorithm_name=oqs_name,
        algorithm_type="SIG",
        operation="keygen",
        git_commit=env_info.git_commit,
        hostname=env_info.hostname,
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
    )
    
    for i in range(iterations):
        power_monitor.start_sampling()
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        sig = None
        
        try:
            power_monitor.sample()
            sig = Signature(oqs_name)
            power_monitor.sample()
            public_key = sig.generate_keypair()
            power_monitor.sample()
            
            if i == 0:
                keygen_result.public_key_bytes = len(public_key)
                keygen_result.secret_key_bytes = sig.length_secret_key
        except Exception as e:
            success = False
            error = str(e)
        finally:
            if sig is not None:
                try:
                    sig.free()
                except Exception:
                    pass
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        samples = power_monitor.stop_sampling()
        duration_s = (wall_end - wall_start) / 1e9
        
        power_reading = power_monitor.read_once()
        energy_mj = power_monitor.compute_energy(samples, duration_s)
        
        keygen_result.iterations.append(IterationResult(
            iteration=i,
            timestamp_ns=timestamp_ns,
            wall_time_ns=wall_end - wall_start,
            perf_time_ns=perf_end - perf_start,
            success=success,
            error=error,
            voltage_v=power_reading.get("voltage_v"),
            current_ma=power_reading.get("current_ma"),
            power_mw=power_reading.get("power_mw"),
            energy_mj=energy_mj,
            power_samples=samples,
        ))
    
    results.append(keygen_result)
    print(" done")
    
    # Sign benchmark
    print(f"    sign ({iterations} iterations)...", end="", flush=True)
    sign_result = BenchmarkResult(
        algorithm_name=oqs_name,
        algorithm_type="SIG",
        operation="sign",
        git_commit=env_info.git_commit,
        hostname=env_info.hostname,
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
    )
    
    # Generate keypair for signing tests
    sig_for_sign = Signature(oqs_name)
    public_key = sig_for_sign.generate_keypair()
    
    for i in range(iterations):
        power_monitor.start_sampling()
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        
        try:
            power_monitor.sample()
            signature = sig_for_sign.sign(test_message)
            power_monitor.sample()
            
            if i == 0:
                sign_result.signature_bytes = len(signature)
        except Exception as e:
            success = False
            error = str(e)
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        samples = power_monitor.stop_sampling()
        duration_s = (wall_end - wall_start) / 1e9
        
        power_reading = power_monitor.read_once()
        energy_mj = power_monitor.compute_energy(samples, duration_s)
        
        sign_result.iterations.append(IterationResult(
            iteration=i,
            timestamp_ns=timestamp_ns,
            wall_time_ns=wall_end - wall_start,
            perf_time_ns=perf_end - perf_start,
            success=success,
            error=error,
            voltage_v=power_reading.get("voltage_v"),
            current_ma=power_reading.get("current_ma"),
            power_mw=power_reading.get("power_mw"),
            energy_mj=energy_mj,
            power_samples=samples,
        ))
    
    results.append(sign_result)
    print(" done")
    
    # Verify benchmark
    print(f"    verify ({iterations} iterations)...", end="", flush=True)
    verify_result = BenchmarkResult(
        algorithm_name=oqs_name,
        algorithm_type="SIG",
        operation="verify",
        git_commit=env_info.git_commit,
        hostname=env_info.hostname,
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
    )
    
    # Generate signature for verification tests
    signature_for_verify = sig_for_sign.sign(test_message)
    
    for i in range(iterations):
        power_monitor.start_sampling()
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        
        try:
            power_monitor.sample()
            valid = sig_for_sign.verify(test_message, signature_for_verify, public_key)
            power_monitor.sample()
            
            if not valid:
                success = False
                error = "verification returned false"
        except Exception as e:
            success = False
            error = str(e)
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        samples = power_monitor.stop_sampling()
        duration_s = (wall_end - wall_start) / 1e9
        
        power_reading = power_monitor.read_once()
        energy_mj = power_monitor.compute_energy(samples, duration_s)
        
        verify_result.iterations.append(IterationResult(
            iteration=i,
            timestamp_ns=timestamp_ns,
            wall_time_ns=wall_end - wall_start,
            perf_time_ns=perf_end - perf_start,
            success=success,
            error=error,
            voltage_v=power_reading.get("voltage_v"),
            current_ma=power_reading.get("current_ma"),
            power_mw=power_reading.get("power_mw"),
            energy_mj=energy_mj,
            power_samples=samples,
        ))
    
    sig_for_sign.free()
    results.append(verify_result)
    print(" done")
    
    return results


# =============================================================================
# AEAD Benchmarks
# =============================================================================

def benchmark_aead(
    aead_info: Dict[str, Any],
    iterations: int,
    power_monitor: PowerMonitor,
    env_info: EnvironmentInfo,
) -> List[BenchmarkResult]:
    """Benchmark a single AEAD algorithm."""
    from core.aead import _instantiate_aead, _build_nonce, required_key_length_for_aead
    
    aead_key = aead_info["key"]
    display_name = aead_info["display_name"]
    results = []
    
    print(f"  Benchmarking AEAD: {display_name}")
    
    # Generate key material
    key = os.urandom(required_key_length_for_aead(aead_key))
    
    # Get AEAD primitive
    try:
        cipher, nonce_len = _instantiate_aead(aead_key, key)
    except Exception as e:
        print(f"    [ERROR] Failed to instantiate {aead_key}: {e}")
        return []
    
    # Associated data
    aad = b"PQC-UAV-Benchmark-AAD"
    
    for payload_size in AEAD_PAYLOAD_SIZES:
        plaintext = os.urandom(payload_size)
        
        # Encrypt benchmark
        print(f"    encrypt {payload_size}B ({iterations} iterations)...", end="", flush=True)
        encrypt_result = BenchmarkResult(
            algorithm_name=display_name,
            algorithm_type="AEAD",
            operation="encrypt",
            payload_size=payload_size,
            git_commit=env_info.git_commit,
            hostname=env_info.hostname,
            timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
        )
        
        for i in range(iterations):
            nonce = _build_nonce(0, i, nonce_len)
            
            power_monitor.start_sampling()
            
            timestamp_ns = time.time_ns()
            perf_start = time.perf_counter_ns()
            wall_start = time.time_ns()
            
            success = True
            error = None
            
            try:
                power_monitor.sample()
                ciphertext = cipher.encrypt(nonce, plaintext, aad)
                power_monitor.sample()
                
                if i == 0:
                    encrypt_result.ciphertext_bytes = len(ciphertext)
            except Exception as e:
                success = False
                error = str(e)
            
            perf_end = time.perf_counter_ns()
            wall_end = time.time_ns()
            
            samples = power_monitor.stop_sampling()
            duration_s = (wall_end - wall_start) / 1e9
            
            power_reading = power_monitor.read_once()
            energy_mj = power_monitor.compute_energy(samples, duration_s)
            
            encrypt_result.iterations.append(IterationResult(
                iteration=i,
                timestamp_ns=timestamp_ns,
                wall_time_ns=wall_end - wall_start,
                perf_time_ns=perf_end - perf_start,
                success=success,
                error=error,
                voltage_v=power_reading.get("voltage_v"),
                current_ma=power_reading.get("current_ma"),
                power_mw=power_reading.get("power_mw"),
                energy_mj=energy_mj,
                power_samples=samples,
            ))
        
        results.append(encrypt_result)
        print(" done")
        
        # Decrypt benchmark
        print(f"    decrypt {payload_size}B ({iterations} iterations)...", end="", flush=True)
        decrypt_result = BenchmarkResult(
            algorithm_name=display_name,
            algorithm_type="AEAD",
            operation="decrypt",
            payload_size=payload_size,
            git_commit=env_info.git_commit,
            hostname=env_info.hostname,
            timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
        )
        
        # Pre-generate ciphertext for decryption
        ciphertext_for_decrypt = cipher.encrypt(_build_nonce(0, 0, nonce_len), plaintext, aad)
        
        for i in range(iterations):
            nonce = _build_nonce(0, 0, nonce_len)  # Same nonce as encryption
            
            power_monitor.start_sampling()
            
            timestamp_ns = time.time_ns()
            perf_start = time.perf_counter_ns()
            wall_start = time.time_ns()
            
            success = True
            error = None
            
            try:
                power_monitor.sample()
                decrypted = cipher.decrypt(nonce, ciphertext_for_decrypt, aad)
                power_monitor.sample()
                
                if decrypted != plaintext:
                    success = False
                    error = "decryption mismatch"
            except Exception as e:
                success = False
                error = str(e)
            
            perf_end = time.perf_counter_ns()
            wall_end = time.time_ns()
            
            samples = power_monitor.stop_sampling()
            duration_s = (wall_end - wall_start) / 1e9
            
            power_reading = power_monitor.read_once()
            energy_mj = power_monitor.compute_energy(samples, duration_s)
            
            decrypt_result.iterations.append(IterationResult(
                iteration=i,
                timestamp_ns=timestamp_ns,
                wall_time_ns=wall_end - wall_start,
                perf_time_ns=perf_end - perf_start,
                success=success,
                error=error,
                voltage_v=power_reading.get("voltage_v"),
                current_ma=power_reading.get("current_ma"),
                power_mw=power_reading.get("power_mw"),
                energy_mj=energy_mj,
                power_samples=samples,
            ))
        
        results.append(decrypt_result)
        print(" done")
    
    return results


# =============================================================================
# Suite Benchmarks (Handshake)
# =============================================================================

def benchmark_suite_handshake(
    suite_info: Dict[str, Any],
    iterations: int,
    power_monitor: PowerMonitor,
    env_info: EnvironmentInfo,
) -> List[BenchmarkResult]:
    """Benchmark full handshake for a suite."""
    Signature = get_oqs_sig_class()
    from core.handshake import (
        build_server_hello,
        parse_and_verify_server_hello,
        client_encapsulate,
        server_decapsulate,
        derive_transport_keys,
        _drone_psk_bytes,
    )
    from core.config import CONFIG
    
    suite_id = suite_info["suite_id"]
    sig_name = suite_info["sig_name"]
    psk = _drone_psk_bytes()
    results = []
    
    print(f"  Benchmarking Suite Handshake: {suite_id}")
    
    # Generate long-lived signing keypair (simulating GCS identity)
    gcs_sig = Signature(sig_name)
    gcs_sig_pub = gcs_sig.generate_keypair()
    
    # Full handshake benchmark
    print(f"    full_handshake ({iterations} iterations)...", end="", flush=True)
    handshake_result = BenchmarkResult(
        algorithm_name=suite_id,
        algorithm_type="SUITE",
        operation="full_handshake",
        git_commit=env_info.git_commit,
        hostname=env_info.hostname,
        timestamp_iso=datetime.datetime.utcnow().isoformat() + "Z",
    )
    
    for i in range(iterations):
        power_monitor.start_sampling()
        
        timestamp_ns = time.time_ns()
        perf_start = time.perf_counter_ns()
        wall_start = time.time_ns()
        
        success = True
        error = None
        
        try:
            power_monitor.sample()
            
            # GCS side: build server hello
            hello_wire, ephemeral = build_server_hello(suite_id, gcs_sig)
            power_monitor.sample()
            
            # Drone side: parse and verify, then encapsulate
            hello = parse_and_verify_server_hello(
                hello_wire,
                CONFIG["WIRE_VERSION"],
                gcs_sig_pub,
            )
            power_monitor.sample()
            
            kem_ct, drone_shared = client_encapsulate(hello)
            power_monitor.sample()
            
            # GCS side: decapsulate
            gcs_shared = server_decapsulate(ephemeral, kem_ct)
            power_monitor.sample()
            
            # Both sides: derive keys
            drone_send, drone_recv = derive_transport_keys(
                "client",
                hello.session_id,
                hello.challenge,
                hello.kem_name,
                hello.sig_name,
                drone_shared,
                psk,
            )
            power_monitor.sample()
            
            gcs_send, gcs_recv = derive_transport_keys(
                "server",
                ephemeral.session_id,
                ephemeral.challenge,
                ephemeral.kem_name.encode(),
                ephemeral.sig_name.encode(),
                gcs_shared,
                psk,
            )
            power_monitor.sample()
            
            # Verify keys match
            if drone_send != gcs_recv or drone_recv != gcs_send:
                success = False
                error = "key derivation mismatch"
            
            # Record sizes
            if i == 0:
                handshake_result.public_key_bytes = len(hello.kem_pub)
                handshake_result.signature_bytes = len(hello.signature)
                handshake_result.ciphertext_bytes = len(kem_ct)
                handshake_result.shared_secret_bytes = len(drone_shared)
                
        except Exception as e:
            success = False
            error = str(e)
        
        perf_end = time.perf_counter_ns()
        wall_end = time.time_ns()
        
        samples = power_monitor.stop_sampling()
        duration_s = (wall_end - wall_start) / 1e9
        
        power_reading = power_monitor.read_once()
        energy_mj = power_monitor.compute_energy(samples, duration_s)
        
        handshake_result.iterations.append(IterationResult(
            iteration=i,
            timestamp_ns=timestamp_ns,
            wall_time_ns=wall_end - wall_start,
            perf_time_ns=perf_end - perf_start,
            success=success,
            error=error,
            voltage_v=power_reading.get("voltage_v"),
            current_ma=power_reading.get("current_ma"),
            power_mw=power_reading.get("power_mw"),
            energy_mj=energy_mj,
            power_samples=samples,
        ))
    
    gcs_sig.free()
    results.append(handshake_result)
    print(" done")
    
    return results


# =============================================================================
# Result Storage
# =============================================================================

def compute_summary(result: BenchmarkResult) -> Dict[str, Any]:
    """Compute summary statistics from raw iterations."""
    successful = [it for it in result.iterations if it.success]
    failed = [it for it in result.iterations if not it.success]
    
    summary = {
        "algorithm_name": result.algorithm_name,
        "algorithm_type": result.algorithm_type,
        "operation": result.operation,
        "payload_size": result.payload_size,
        "git_commit": result.git_commit,
        "hostname": result.hostname,
        "timestamp_iso": result.timestamp_iso,
        "total_iterations": len(result.iterations),
        "successful_iterations": len(successful),
        "failed_iterations": len(failed),
    }
    
    if successful:
        wall_times_ns = [it.wall_time_ns for it in successful]
        perf_times_ns = [it.perf_time_ns for it in successful]
        
        summary["wall_time_ns"] = {
            "mean": statistics.mean(wall_times_ns),
            "median": statistics.median(wall_times_ns),
            "min": min(wall_times_ns),
            "max": max(wall_times_ns),
            "stdev": statistics.stdev(wall_times_ns) if len(wall_times_ns) > 1 else 0,
        }
        
        summary["perf_time_ns"] = {
            "mean": statistics.mean(perf_times_ns),
            "median": statistics.median(perf_times_ns),
            "min": min(perf_times_ns),
            "max": max(perf_times_ns),
            "stdev": statistics.stdev(perf_times_ns) if len(perf_times_ns) > 1 else 0,
        }
        
        # Power metrics (if available)
        energies = [it.energy_mj for it in successful if it.energy_mj is not None]
        if energies:
            summary["energy_mj"] = {
                "mean": statistics.mean(energies),
                "median": statistics.median(energies),
                "min": min(energies),
                "max": max(energies),
                "stdev": statistics.stdev(energies) if len(energies) > 1 else 0,
            }
    
    # Artifact sizes
    if result.public_key_bytes is not None:
        summary["public_key_bytes"] = result.public_key_bytes
    if result.secret_key_bytes is not None:
        summary["secret_key_bytes"] = result.secret_key_bytes
    if result.ciphertext_bytes is not None:
        summary["ciphertext_bytes"] = result.ciphertext_bytes
    if result.signature_bytes is not None:
        summary["signature_bytes"] = result.signature_bytes
    if result.shared_secret_bytes is not None:
        summary["shared_secret_bytes"] = result.shared_secret_bytes
    
    return summary


def save_raw_result(result: BenchmarkResult, output_dir: Path) -> None:
    """Save raw benchmark result to JSON file."""
    # Convert to dict for JSON serialization
    data = {
        "algorithm_name": result.algorithm_name,
        "algorithm_type": result.algorithm_type,
        "operation": result.operation,
        "payload_size": result.payload_size,
        "git_commit": result.git_commit,
        "hostname": result.hostname,
        "timestamp_iso": result.timestamp_iso,
        "public_key_bytes": result.public_key_bytes,
        "secret_key_bytes": result.secret_key_bytes,
        "ciphertext_bytes": result.ciphertext_bytes,
        "signature_bytes": result.signature_bytes,
        "shared_secret_bytes": result.shared_secret_bytes,
        "iterations": [asdict(it) for it in result.iterations],
    }
    
    # Determine subdirectory
    type_dir = {
        "KEM": "kem",
        "SIG": "sig",
        "AEAD": "aead",
        "SUITE": "suites",
    }.get(result.algorithm_type, "other")
    
    subdir = output_dir / "raw" / type_dir
    subdir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename
    name_safe = result.algorithm_name.replace("-", "_").replace("/", "_").replace(" ", "_")
    op_safe = result.operation.replace("-", "_")
    
    if result.payload_size is not None:
        filename = f"{name_safe}_{op_safe}_{result.payload_size}B.json"
    else:
        filename = f"{name_safe}_{op_safe}.json"
    
    filepath = subdir / filename
    
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def save_summaries(summaries: List[Dict[str, Any]], output_dir: Path, category: str) -> None:
    """Save summary statistics to JSON and CSV files."""
    summary_dir = output_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    
    # JSON summary
    json_path = summary_dir / f"{category}_summary.json"
    with open(json_path, "w") as f:
        json.dump(summaries, f, indent=2)
    
    # CSV summary (flattened)
    csv_path = summary_dir / f"{category}_summary.csv"
    
    if not summaries:
        return
    
    # Flatten nested dicts for CSV
    flat_rows = []
    for s in summaries:
        row = {
            "algorithm_name": s.get("algorithm_name"),
            "algorithm_type": s.get("algorithm_type"),
            "operation": s.get("operation"),
            "payload_size": s.get("payload_size"),
            "total_iterations": s.get("total_iterations"),
            "successful_iterations": s.get("successful_iterations"),
            "failed_iterations": s.get("failed_iterations"),
        }
        
        # Wall time
        wt = s.get("wall_time_ns", {})
        row["wall_time_mean_ns"] = wt.get("mean")
        row["wall_time_median_ns"] = wt.get("median")
        row["wall_time_min_ns"] = wt.get("min")
        row["wall_time_max_ns"] = wt.get("max")
        row["wall_time_stdev_ns"] = wt.get("stdev")
        
        # Perf time
        pt = s.get("perf_time_ns", {})
        row["perf_time_mean_ns"] = pt.get("mean")
        row["perf_time_median_ns"] = pt.get("median")
        row["perf_time_min_ns"] = pt.get("min")
        row["perf_time_max_ns"] = pt.get("max")
        row["perf_time_stdev_ns"] = pt.get("stdev")
        
        # Energy
        en = s.get("energy_mj", {})
        row["energy_mean_mj"] = en.get("mean")
        row["energy_median_mj"] = en.get("median")
        row["energy_min_mj"] = en.get("min")
        row["energy_max_mj"] = en.get("max")
        row["energy_stdev_mj"] = en.get("stdev")
        
        # Sizes
        row["public_key_bytes"] = s.get("public_key_bytes")
        row["secret_key_bytes"] = s.get("secret_key_bytes")
        row["ciphertext_bytes"] = s.get("ciphertext_bytes")
        row["signature_bytes"] = s.get("signature_bytes")
        row["shared_secret_bytes"] = s.get("shared_secret_bytes")
        
        flat_rows.append(row)
    
    if flat_rows:
        fieldnames = list(flat_rows[0].keys())
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(flat_rows)


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="PQC Performance & Power Benchmarking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--iterations", "-n",
        type=int,
        default=DEFAULT_ITERATIONS,
        help=f"Number of iterations per measurement (default: {DEFAULT_ITERATIONS})",
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default="bench_results",
        help="Output directory for results (default: bench_results)",
    )
    parser.add_argument(
        "--skip-kem",
        action="store_true",
        help="Skip KEM benchmarks",
    )
    parser.add_argument(
        "--skip-sig",
        action="store_true",
        help="Skip signature benchmarks",
    )
    parser.add_argument(
        "--skip-aead",
        action="store_true",
        help="Skip AEAD benchmarks",
    )
    parser.add_argument(
        "--skip-suites",
        action="store_true",
        help="Skip suite handshake benchmarks",
    )
    parser.add_argument(
        "--aead",
        action="append",
        default=[],
        help="AEAD token to include (repeatable)",
    )
    parser.add_argument(
        "--exclude-aead",
        action="append",
        default=[],
        help="AEAD token to exclude (repeatable)",
    )
    
    args = parser.parse_args()
    
    print("=" * 70)
    print("PQC PERFORMANCE & POWER BENCHMARKING")
    print("=" * 70)
    print()
    print("NOTICE: This is a MEASUREMENT-ONLY script.")
    print("        No analysis. No conclusions. No optimization.")
    print()
    
    # Collect environment info
    print("[1/6] Collecting environment information...")
    env_info = collect_environment_info()
    print(f"  Hostname: {env_info.hostname}")
    print(f"  CPU: {env_info.cpu_model}")
    print(f"  Governor: {env_info.cpu_freq_governor}")
    print(f"  Kernel: {env_info.kernel_version}")
    print(f"  Python: {env_info.python_version.split()[0]}")
    print(f"  OQS: {env_info.oqs_version}")
    print(f"  oqs-python: {env_info.oqs_python_version}")
    print(f"  Git commit: {env_info.git_commit[:12]}...")
    print(f"  Git clean: {env_info.git_clean}")
    print()
    
    # Initialize power monitor
    print("[2/6] Initializing power monitor...")
    power_monitor = PowerMonitor()
    if power_monitor.available:
        reading = power_monitor.read_once()
        print(f"  INA219 available: {reading}")
    else:
        print("  INA219 NOT available (power measurements will be null)")
    print()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save environment info
    env_path = output_dir / "environment.json"
    with open(env_path, "w") as f:
        json.dump(asdict(env_info), f, indent=2)
    print(f"  Environment saved to: {env_path}")
    print()
    
    # Discover primitives
    print("[3/6] Discovering available primitives...")
    kems = discover_kems()
    sigs = discover_signatures()
    aeads = discover_aeads()
    aeads = filter_aeads(aeads, args.aead, args.exclude_aead)
    suites = discover_suites()
    
    print(f"  KEMs: {len(kems)}")
    for k in kems:
        print(f"    - {k['oqs_name']} ({k['nist_level']})")
    
    print(f"  Signatures: {len(sigs)}")
    for s in sigs:
        print(f"    - {s['oqs_name']} ({s['nist_level']})")
    
    print(f"  AEADs: {len(aeads)}")
    for a in aeads:
        print(f"    - {a['display_name']}")
    
    print(f"  Suites: {len(suites)}")
    print()
    
    iterations = args.iterations
    print(f"Running {iterations} iterations per measurement")
    print()
    
    all_summaries = {
        "kem": [],
        "sig": [],
        "aead": [],
        "suites": [],
    }
    
    # Benchmark KEMs
    if not args.skip_kem and kems:
        print("[4/6] Benchmarking KEMs...")
        for kem_info in kems:
            try:
                results = benchmark_kem(kem_info, iterations, power_monitor, env_info)
                for result in results:
                    save_raw_result(result, output_dir)
                    all_summaries["kem"].append(compute_summary(result))
            except Exception as e:
                print(f"    [ERROR] {kem_info['oqs_name']}: {e}")
                traceback.print_exc()
        print()
    else:
        print("[4/6] Skipping KEM benchmarks")
        print()
    
    # Benchmark Signatures
    if not args.skip_sig and sigs:
        print("[5/6] Benchmarking Signatures...")
        for sig_info in sigs:
            try:
                results = benchmark_signature(sig_info, iterations, power_monitor, env_info)
                for result in results:
                    save_raw_result(result, output_dir)
                    all_summaries["sig"].append(compute_summary(result))
            except Exception as e:
                print(f"    [ERROR] {sig_info['oqs_name']}: {e}")
                traceback.print_exc()
        print()
    else:
        print("[5/6] Skipping Signature benchmarks")
        print()
    
    # Benchmark AEADs
    if not args.skip_aead and aeads:
        print("[6/6] Benchmarking AEADs...")
        for aead_info in aeads:
            try:
                results = benchmark_aead(aead_info, iterations, power_monitor, env_info)
                for result in results:
                    save_raw_result(result, output_dir)
                    all_summaries["aead"].append(compute_summary(result))
            except Exception as e:
                print(f"    [ERROR] {aead_info['display_name']}: {e}")
                traceback.print_exc()
        print()
    else:
        print("[6/6] Skipping AEAD benchmarks")
        print()
    
    # Benchmark Suite Handshakes
    if not args.skip_suites and suites:
        print("[EXTRA] Benchmarking Suite Handshakes...")
        for suite_info in suites:
            try:
                results = benchmark_suite_handshake(suite_info, iterations, power_monitor, env_info)
                for result in results:
                    save_raw_result(result, output_dir)
                    all_summaries["suites"].append(compute_summary(result))
            except Exception as e:
                print(f"    [ERROR] {suite_info['suite_id']}: {e}")
                traceback.print_exc()
        print()
    else:
        print("[EXTRA] Skipping Suite Handshake benchmarks")
        print()
    
    # Save summaries
    print("Saving summaries...")
    for category, summaries in all_summaries.items():
        if summaries:
            save_summaries(summaries, output_dir, category)
            print(f"  {category}: {len(summaries)} results")
    
    print()
    print("=" * 70)
    print("BENCHMARKING COMPLETE")
    print(f"Results saved to: {output_dir.absolute()}")
    print("=" * 70)


if __name__ == "__main__":
    main()
