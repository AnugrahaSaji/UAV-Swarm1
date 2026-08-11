#!/usr/bin/env python3
"""
Metrics Collectors - Base and System Collectors
core/metrics_collectors.py

Provides collectors for gathering metrics from various sources:
- System resources (CPU, memory, temperature)
- Power monitoring (INA219, RPi5 PMIC)
- Environment info (git, python, kernel)
- Network statistics

Usage:
    from core.metrics_collectors import SystemCollector, PowerCollector
    
    sys_collector = SystemCollector()
    metrics = sys_collector.collect()
"""

import os
import sys
import time
import json
import socket
import platform
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass
from datetime import datetime, timezone

# Try importing optional dependencies
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

# smbus2 for direct INA219 register access (fixes adafruit library bug with 9-bit ADC)
try:
    import smbus2
    HAS_SMBUS2 = True
except ImportError:
    HAS_SMBUS2 = False

# INA219 bus-voltage gain correction — see power_monitor.py for full rationale.
# The breakout's counterfeit INA219 ADC reads ~16% low; shunt/current is fine.
_VBUS_GAIN = float(os.environ.get("INA219_VBUS_GAIN", "1.22"))


def _warmup_i2c_bus(busnum: int = 1, address: int = 0x40) -> None:
    """BCM2835 I2C first-transaction workaround.

    The first I2C_SMBUS ioctl after opening /dev/i2c-N on RPi4 always
    returns EIO.  A single throwaway ``read_byte_data`` (which includes a
    register-select write phase) clears the condition for the remainder of
    the process.  Using ``read_byte`` (no write phase) would corrupt the
    bus — only ``read_byte_data`` works reliably.
    """
    if not HAS_SMBUS2:
        return
    try:
        bus = smbus2.SMBus(busnum)
        try:
            bus.read_byte_data(address, 0x00)
        except OSError:
            pass  # expected first-fail on BCM2835
        finally:
            bus.close()
    except Exception:
        pass

# Optional INA219 dependency – prefer adafruit_ina219 (CircuitPython) over
# the legacy pi-ina219 package.  The two libraries have incompatible APIs:
#   adafruit:   INA219(i2c)  -> .bus_voltage, .current (mA), .power (mW)
#   pi-ina219:  INA219(shunt_ohms, address, busnum) -> .voltage(), .current() (mA), .power() (mW)
_INA219_BACKEND = None  # "adafruit" | "pi" | None
HAS_INA219 = False
INA219 = None  # type: ignore

try:
    import adafruit_ina219 as _adafruit_ina219_mod  # type: ignore
    import board as _board_mod  # type: ignore
    HAS_INA219 = True
    _INA219_BACKEND = "adafruit"
except (ImportError, NotImplementedError):
    _adafruit_ina219_mod = None  # type: ignore
    _board_mod = None  # type: ignore

if not HAS_INA219:
    try:
        from ina219 import INA219  # type: ignore
        HAS_INA219 = True
        _INA219_BACKEND = "pi"
    except ImportError:
        INA219 = None  # type: ignore

# =============================================================================
# BASE COLLECTOR
# =============================================================================

class BaseCollector:
    """Base class for all metric collectors."""
    
    def __init__(self, name: str = "base"):
        self.name = name
        self.is_drone = self._detect_platform() == "linux_arm"
        self.is_gcs = not self.is_drone
        self._last_collect_time = 0.0
        self._collect_count = 0
    
    def _detect_platform(self) -> str:
        """Detect running platform."""
        system = platform.system().lower()
        machine = platform.machine().lower()
        
        if system == "linux" and ("arm" in machine or "aarch" in machine):
            return "linux_arm"
        elif system == "windows":
            return "windows"
        elif system == "linux":
            return "linux_x86"
        return "unknown"
    
    def collect(self) -> Dict[str, Any]:
        """Override in subclass to collect metrics."""
        raise NotImplementedError
    
    def collect_timed(self) -> Tuple[Dict[str, Any], float]:
        """Collect metrics and return with timing."""
        start = time.perf_counter()
        data = self.collect()
        elapsed_ms = (time.perf_counter() - start) * 1000
        self._last_collect_time = elapsed_ms
        self._collect_count += 1
        return data, elapsed_ms


# =============================================================================
# ENVIRONMENT COLLECTOR
# =============================================================================

class EnvironmentCollector(BaseCollector):
    """Collects environment and context information."""
    
    def __init__(self):
        super().__init__("environment")
        self._git_info_cache = None
        self._oqs_version_cache = None
    
    def collect(self) -> Dict[str, Any]:
        """Collect environment metrics."""
        return {
            "hostname": socket.gethostname(),
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "cwd": os.getcwd(),
            "pid": os.getpid(),
            "kernel_version": self._get_kernel_version(),
            "git_commit": self._get_git_commit(),
            "git_dirty": self._is_git_dirty(),
            "liboqs_version": self._get_oqs_version(),
            "conda_env": os.environ.get("CONDA_DEFAULT_ENV", ""),
            "virtual_env": os.environ.get("VIRTUAL_ENV", ""),
            "timestamp_wall": datetime.now(timezone.utc).isoformat(),
            "timestamp_mono": time.monotonic(),
        }
    
    def _get_kernel_version(self) -> str:
        """Get kernel version."""
        try:
            if platform.system() == "Linux":
                return platform.release()
            elif platform.system() == "Windows":
                return platform.version()
            return platform.release()
        except Exception:
            return ""
    
    def _get_git_commit(self) -> str:
        """Get current git commit hash."""
        if self._git_info_cache is not None:
            return self._git_info_cache.get("commit", "")
        
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                commit = result.stdout.strip()[:12]
                self._git_info_cache = {"commit": commit}
                return commit
        except Exception:
            pass
        return ""
    
    def _is_git_dirty(self) -> bool:
        """Check if git working directory is dirty."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True, text=True, timeout=5
            )
            return bool(result.stdout.strip())
        except Exception:
            return False
    
    def _get_oqs_version(self) -> str:
        """Get liboqs version if available."""
        if self._oqs_version_cache is not None:
            return self._oqs_version_cache
        
        try:
            import oqs
            version = getattr(oqs, '__version__', '')
            if not version:
                # Try to get from oqs.oqs
                try:
                    from oqs import oqs as oqs_mod
                    version = getattr(oqs_mod, '__version__', 'unknown')
                except Exception:
                    version = 'installed'
            self._oqs_version_cache = version
            return version
        except ImportError:
            self._oqs_version_cache = "not_installed"
            return "not_installed"
    
    def get_ip_address(self, interface: str = None) -> str:
        """Get IP address."""
        try:
            if interface and HAS_PSUTIL:
                addrs = psutil.net_if_addrs()
                if interface in addrs:
                    for addr in addrs[interface]:
                        if addr.family == socket.AF_INET:
                            return addr.address
            
            # Fallback: create UDP socket to get default route IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            try:
                s.connect(("8.8.8.8", 80))
                return s.getsockname()[0]
            except Exception:
                return "127.0.0.1"
            finally:
                s.close()
        except Exception:
            return ""


# =============================================================================
# SYSTEM RESOURCE COLLECTOR
# =============================================================================

class SystemCollector(BaseCollector):
    """Collects system resource metrics (CPU, memory, temperature)."""
    
    def __init__(self):
        super().__init__("system")
        self._cpu_samples: List[float] = []
        self._sample_window = 10  # Keep last N samples
    
    def collect(self) -> Dict[str, Any]:
        """Collect system resource metrics."""
        metrics = {
            "timestamp": time.time(),
            "cpu_percent": None,
            "cpu_freq_mhz": None,
            "memory_rss_mb": None,
            "memory_vms_mb": None,
            "memory_percent": None,
            "thread_count": None,
            "temperature_c": None,
            "load_avg_1m": None,
            "load_avg_5m": None,
            "load_avg_15m": None,
            "uptime_s": None,
        }
        
        if HAS_PSUTIL:
            try:
                try:
                    metrics["cpu_percent"] = psutil.cpu_percent(interval=None)
                    self._cpu_samples.append(metrics["cpu_percent"])
                    if len(self._cpu_samples) > self._sample_window:
                        self._cpu_samples.pop(0)
                except Exception as e:
                    metrics["cpu_error"] = str(e)

                try:
                    freq = psutil.cpu_freq()
                    if freq:
                        metrics["cpu_freq_mhz"] = freq.current
                except Exception as e:
                    metrics["cpu_freq_error"] = str(e)

                proc = psutil.Process()

                try:
                    mem_info = proc.memory_info()
                    metrics["memory_rss_mb"] = mem_info.rss / (1024 * 1024)
                    metrics["memory_vms_mb"] = mem_info.vms / (1024 * 1024)
                except Exception as e:
                    metrics["memory_info_error"] = str(e)

                try:
                    metrics["memory_percent"] = proc.memory_percent()
                except Exception as e:
                    metrics["memory_percent_error"] = str(e)

                try:
                    metrics["thread_count"] = proc.num_threads()
                except Exception as e:
                    metrics["thread_count_error"] = str(e)

                try:
                    vm = psutil.virtual_memory()
                    metrics["system_memory_percent"] = vm.percent
                    metrics["system_memory_available_mb"] = vm.available / (1024 * 1024)
                except Exception as e:
                    metrics["system_memory_error"] = str(e)

                try:
                    metrics["uptime_s"] = max(0.0, time.time() - psutil.boot_time())
                except Exception as e:
                    metrics["uptime_error"] = str(e)

            except Exception as e:
                metrics["error"] = str(e)
        
        # Linux-specific
        if platform.system() == "Linux":
            try:
                load = os.getloadavg()
                metrics["load_avg_1m"] = load[0]
                metrics["load_avg_5m"] = load[1]
                metrics["load_avg_15m"] = load[2]
            except Exception:
                pass
            
            # Temperature (RPi)
            metrics["temperature_c"] = self._read_temperature()
            metrics["thermal_throttled"] = self._check_throttling()
        
        return metrics
    
    def _read_temperature(self) -> float:
        """Read CPU temperature on Linux."""
        # Try thermal zone
        try:
            with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                return float(f.read().strip()) / 1000.0
        except Exception:
            pass
        
        # Try vcgencmd on RPi
        try:
            result = subprocess.run(
                ["vcgencmd", "measure_temp"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                # Output: temp=45.0'C
                temp_str = result.stdout.strip()
                return float(temp_str.split("=")[1].replace("'C", ""))
        except Exception:
            pass
        
        return 0.0
    
    def _check_throttling(self) -> bool:
        """Check if RPi is thermally throttled."""
        try:
            result = subprocess.run(
                ["vcgencmd", "get_throttled"],
                capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                # Output: throttled=0x0
                value = result.stdout.strip().split("=")[1]
                return int(value, 16) != 0
        except Exception:
            pass
        return False
    
    def get_cpu_stats(self) -> Dict[str, float]:
        """Get CPU statistics from collected samples."""
        if not self._cpu_samples:
            return {"avg": 0.0, "peak": 0.0, "min": 0.0}
        
        return {
            "avg": sum(self._cpu_samples) / len(self._cpu_samples),
            "peak": max(self._cpu_samples),
            "min": min(self._cpu_samples),
        }


# =============================================================================
# POWER COLLECTOR
# =============================================================================

class PowerCollector(BaseCollector):
    """Collects power and energy metrics from hardware sensors."""
    
    def __init__(self, backend: str = "auto"):
        super().__init__("power")
        self.backend = backend
        self._ina219 = None
        self._ina_backend: Optional[str] = None  # "smbus2_direct" | "pi" | "adafruit" | None
        self._ina_busnum: Optional[int] = None
        self._ina_address: int = 0x40
        self._sampling = False
        self._samples: List[Dict[str, float]] = []
        self._sample_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._smbus: Optional[object] = None  # cached smbus2.SMBus for direct reads
        self._shunt_ohm: float = float(os.environ.get("INA219_SHUNT_OHM", "0.1"))
        
        # Detect available backend
        if backend == "auto":
            self.backend = self._detect_backend()
        
        # Initialize INA219 if available
        if self.backend == "ina219":
            self._init_ina219()
    
    def _detect_backend(self) -> str:
        """Detect available power monitoring backend.

        Priority order:
        1. smbus2_direct — uses proven read_word_data with BCM2835 warm-up/retry.
           Most reliable on RPi4 where the I2C controller has first-fail bugs
           that break higher-level libraries (pi-ina219, adafruit_ina219).
        2. pi-ina219 — simpler I2C path.
        3. adafruit_ina219 — CircuitPython Blinka backend.
        4. RPi5 PMIC / hwmon.
        """
        if platform.system() != "Linux":
            return "none"

        # BCM2835 I2C first-transaction warm-up — must happen before any
        # library (pi-ina219 or adafruit) tries to access the bus.
        _warmup_i2c_bus(busnum=1, address=self._ina_address)

        # ---- 0. smbus2 direct (most reliable on RPi4) ----
        if HAS_SMBUS2:
            busnum = 1
            env_bus = os.environ.get("INA219_BUSNUM") or os.environ.get("INA219_I2C_BUS")
            if env_bus:
                try:
                    busnum = int(env_bus)
                except Exception:
                    pass
            addr = self._ina_address
            try:
                bus = smbus2.SMBus(busnum)
                # BCM2835 warm-up
                try:
                    bus.read_byte_data(addr, 0x00)
                except OSError:
                    pass
                # Verify we can read config register (retry for post-warmup EIO)
                for _attempt in range(3):
                    try:
                        word_le = bus.read_word_data(addr, 0x00)
                        raw = ((word_le & 0xFF) << 8) | ((word_le >> 8) & 0xFF)
                        if raw != 0:  # valid config register
                            self._smbus = bus
                            self._ina_busnum = busnum
                            self._ina_address = addr
                            self._ina_backend = "smbus2_direct"
                            return "ina219"
                    except OSError:
                        pass
                bus.close()
            except Exception:
                pass

        _MAX_RETRIES = int(os.environ.get("INA219_DETECT_RETRIES", "3"))
        _RETRY_DELAY = float(os.environ.get("INA219_DETECT_DELAY", "0.3"))

        # Shunt resistor value from env (.denv) or config.py, default 0.1 Ω
        _SHUNT_OHM = float(os.environ.get("INA219_SHUNT_OHM", "0.1"))
        _MAX_AMPS = float(os.environ.get("INA219_MAX_AMPS", "3.0"))

        # ---- 1. pi-ina219 (preferred – simpler I2C path, like bench_ddos_v2) ----
        if HAS_INA219:
            # Resolve bus / address candidates from env
            bus_candidates: list[int] = []
            env_bus = os.environ.get("INA219_BUSNUM") or os.environ.get("INA219_I2C_BUS")
            if env_bus:
                try:
                    bus_candidates.append(int(env_bus))
                except Exception:
                    pass
            bus_candidates.extend([1, 0, 20, 21])

            addr_candidates: list[int] = []
            env_addr = os.environ.get("INA219_ADDRESS") or os.environ.get("INA219_ADDR")
            if env_addr:
                try:
                    addr_candidates.append(int(env_addr, 0))
                except Exception:
                    pass
            if 0x40 not in addr_candidates:
                addr_candidates.append(0x40)

            # Try to import pi-ina219 regardless of _INA219_BACKEND
            _pi_INA219 = None
            if _INA219_BACKEND == "pi":
                _pi_INA219 = INA219
            else:
                try:
                    from ina219 import INA219 as _pi_INA219  # type: ignore
                except ImportError:
                    pass

            if _pi_INA219 is not None:
                for busnum in bus_candidates:
                    for addr in addr_candidates:
                        for retry in range(_MAX_RETRIES):
                            try:
                                ina = _pi_INA219(
                                    shunt_ohms=_SHUNT_OHM,
                                    max_expected_amps=_MAX_AMPS,
                                    address=addr,
                                    busnum=busnum,
                                )
                                ina.configure()
                                self._ina_busnum = busnum
                                self._ina_address = addr
                                self._ina219 = ina
                                self._ina_backend = "pi"
                                return "ina219"
                            except Exception:
                                import time as _t
                                _t.sleep(_RETRY_DELAY)
                                continue

        # ---- 2. adafruit_ina219 fallback ----
        if _INA219_BACKEND == "adafruit" or (HAS_INA219 and _adafruit_ina219_mod is not None):
            for retry in range(_MAX_RETRIES):
                try:
                    i2c = _board_mod.I2C()
                    sensor = _adafruit_ina219_mod.INA219(i2c)
                    _ = sensor.bus_voltage  # probe read
                    self._ina219 = sensor
                    self._ina_backend = "adafruit"
                    return "ina219"
                except Exception:
                    import time as _t
                    _t.sleep(_RETRY_DELAY)

        # ---- 3. RPi5 PMIC / hwmon ----
        if Path("/sys/class/hwmon").exists():
            for hwmon in Path("/sys/class/hwmon").iterdir():
                name_file = hwmon / "name"
                if name_file.exists():
                    try:
                        name = name_file.read_text().strip()
                        if "pmic" in name.lower():
                            return "rpi5_hwmon"
                        if "rpi" in name.lower():
                            has_voltage = any((hwmon / f).exists() for f in
                                              ("in1_input", "in0_input", "voltage0_input"))
                            has_current = any((hwmon / f).exists() for f in
                                              ("curr1_input", "curr0_input", "current0_input"))
                            if has_voltage and has_current:
                                return "rpi5_hwmon"
                    except Exception:
                        pass

        return "none"
    
    def _init_ina219(self):
        """Initialize INA219 sensor.

        If ``_detect_backend()`` already created and configured the sensor
        (stored in ``self._ina219``), skip re-initialisation.  Otherwise
        attempt pi-ina219 first, then adafruit, matching the priority in
        ``_detect_backend()``.
        """
        # smbus2_direct path — everything is already set up via _detect_backend.
        if self._ina_backend == "smbus2_direct" and self._smbus is not None:
            return

        # Sensor already created & configured during detection – nothing to do.
        if self._ina219 is not None:
            # If the detection chose adafruit, apply calibration / ADC settings.
            if self._ina_backend == "adafruit":
                try:
                    self._ina219.set_calibration_32V_2A()
                    self._ina219.bus_adc_resolution = _adafruit_ina219_mod.ADCResolution.ADCRES_9BIT_1S
                    self._ina219.shunt_adc_resolution = _adafruit_ina219_mod.ADCResolution.ADCRES_9BIT_1S
                except Exception:
                    pass
            return

        # Fallback: try to create sensor from scratch with retries
        _MAX = 3
        _DELAY = 0.3

        _SHUNT = float(os.environ.get("INA219_SHUNT_OHM", "0.1"))
        _AMPS = float(os.environ.get("INA219_MAX_AMPS", "3.0"))

        # Try pi-ina219 first
        try:
            from ina219 import INA219 as _pi_INA219  # type: ignore
            busnum = self._ina_busnum
            if busnum is None:
                env_bus = os.environ.get("INA219_BUSNUM") or os.environ.get("INA219_I2C_BUS")
                busnum = int(env_bus) if env_bus else 1
            addr = self._ina_address or 0x40
            env_addr = os.environ.get("INA219_ADDRESS") or os.environ.get("INA219_ADDR")
            if env_addr:
                try:
                    addr = int(env_addr, 0)
                except Exception:
                    pass
            for _ in range(_MAX):
                try:
                    ina = _pi_INA219(
                        shunt_ohms=_SHUNT,
                        max_expected_amps=_AMPS,
                        address=addr,
                        busnum=busnum,
                    )
                    ina.configure()
                    self._ina219 = ina
                    self._ina_backend = "pi"
                    return
                except Exception:
                    import time as _t
                    _t.sleep(_DELAY)
        except ImportError:
            pass

        # Try adafruit
        if _adafruit_ina219_mod is not None and _board_mod is not None:
            for _ in range(_MAX):
                try:
                    i2c = _board_mod.I2C()
                    sensor = _adafruit_ina219_mod.INA219(i2c)
                    sensor.set_calibration_32V_2A()
                    self._ina219 = sensor
                    self._ina_backend = "adafruit"
                    return
                except Exception:
                    import time as _t
                    _t.sleep(_DELAY)

        # All attempts failed
        self._ina219 = None
        self.backend = "none"
    
    def _is_adafruit_sensor(self) -> bool:
        """Check if the active INA219 sensor is adafruit (vs pi-ina219).

        Uses the ``_ina_backend`` tag set during detection instead of
        ``hasattr(…, 'bus_voltage')`` — the latter triggers an I2C read
        (``bus_voltage`` is a property) which can throw Errno 5 on
        intermittent buses and crash the caller.
        """
        return self._ina_backend == "adafruit"
    
    def _read_ina219_bus_voltage_direct(self) -> Optional[float]:
        """Read INA219 bus voltage directly from register (workaround for adafruit bug).
        
        The adafruit_ina219 library has a bug where the bus_voltage property returns
        incorrect values (~3.9V instead of ~5.0V) when 9-bit ADC resolution is set.
        This method reads the register directly via smbus2 to get the correct value.
        
        Uses a cached SMBus connection to avoid repeatedly opening/closing fds
        which resets the BCM2835 I2C controller warm-up state.
        
        Returns:
            Bus voltage in volts, or None if smbus2 is not available or read fails.
        """
        if not HAS_SMBUS2 or self._ina_address is None:
            return None
        
        try:
            if not hasattr(self, "_direct_bus") or self._direct_bus is None:
                busnum = self._ina_busnum if self._ina_busnum is not None else 1
                self._direct_bus = smbus2.SMBus(busnum)
                # BCM2835 warm-up on first open
                try:
                    self._direct_bus.read_byte_data(self._ina_address, 0x00)
                except OSError:
                    pass
            # Read bus voltage register (0x02) via read_word_data (safe).
            # SMBus returns little-endian; INA219 is big-endian -> swap.
            for _attempt in range(3):
                try:
                    word_le = self._direct_bus.read_word_data(self._ina_address, 0x02)
                    raw = ((word_le & 0xFF) << 8) | ((word_le >> 8) & 0xFF)
                    voltage = ((raw >> 3) & 0x1FFF) * 0.004 * _VBUS_GAIN
                    return voltage
                except OSError:
                    pass
            return None
        except Exception:
            return None
    
    def collect(self) -> Dict[str, Any]:
        """Collect single power reading."""
        metrics = {
            "timestamp": time.time(),
            "backend": self.backend,
            "voltage_v": None,
            "current_a": None,
            "power_w": None,
        }
        
        if self.backend == "ina219" and (self._ina219 or self._smbus):
            try:
                if self._ina_backend == "smbus2_direct" and self._smbus is not None:
                    # Direct smbus2 register reads — most reliable on BCM2835.
                    # INA219 registers are big-endian; SMBus returns little-endian.
                    bus = self._smbus
                    addr = self._ina_address
                    for _att in range(3):
                        try:
                            # Bus voltage (reg 0x02): bits[15:3] × 4mV
                            w = bus.read_word_data(addr, 0x02)
                            raw_v = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
                            voltage_v = ((raw_v >> 3) & 0x1FFF) * 0.004 * _VBUS_GAIN
                            # BCM2835 idle bug: after >~50ms idle, first read
                            # returns 0 without raising OSError.  Retry.
                            if voltage_v < 0.1 and _att < 2:
                                continue
                            # Shunt voltage (reg 0x01): signed, 10µV LSB
                            w = bus.read_word_data(addr, 0x01)
                            raw_sh = ((w & 0xFF) << 8) | ((w >> 8) & 0xFF)
                            if raw_sh & 0x8000:
                                raw_sh -= 1 << 16
                            shunt_v = raw_sh * 10e-6
                            current_a = abs(shunt_v / self._shunt_ohm)
                            metrics["voltage_v"] = voltage_v
                            metrics["current_a"] = current_a
                            metrics["power_w"] = voltage_v * current_a
                            break
                        except OSError:
                            pass
                elif self._is_adafruit_sensor():
                    # adafruit_ina219: use the library directly.
                    # The direct SMBus register read (_read_ina219_bus_voltage_direct)
                    # is avoided during repeated calls because a second open fd to
                    # /dev/i2c-1 contends with the adafruit library's fd, causing
                    # register reads to return 0.  The adafruit bus_voltage is
                    # slightly underread (~3.9V vs ~4.5V actual) with 9-bit ADC
                    # but is correct enough for power calculations.
                    voltage_v = self._ina219.bus_voltage * _VBUS_GAIN
                    
                    metrics["voltage_v"] = voltage_v
                    metrics["current_a"] = abs(self._ina219.current) / 1000.0  # mA -> A
                    metrics["power_w"] = metrics["voltage_v"] * metrics["current_a"]  # V*A = W
                else:
                    # pi-ina219: methods return V, mA, mW
                    metrics["voltage_v"] = self._ina219.voltage() * _VBUS_GAIN
                    metrics["current_a"] = abs(self._ina219.current()) / 1000.0  # mA -> A
                    metrics["power_w"] = metrics["voltage_v"] * metrics["current_a"]
            except Exception as e:
                metrics["error"] = str(e)
        
        elif self.backend == "rpi5_hwmon":
            metrics.update(self._read_rpi5_hwmon())
        
        return metrics
    
    def _read_rpi5_hwmon(self) -> Dict[str, float]:
        """Read power from RPi5 hwmon."""
        result = {"voltage_v": 0.0, "current_a": 0.0, "power_w": 0.0}
        
        try:
            hwmon_base = Path("/sys/class/hwmon")
            for hwmon in hwmon_base.iterdir():
                name_file = hwmon / "name"
                if name_file.exists():
                    name = name_file.read_text().strip()
                    if "rpi" in name.lower():
                        # Read voltage (in1_input is in mV)
                        volt_file = hwmon / "in1_input"
                        if volt_file.exists():
                            result["voltage_v"] = float(volt_file.read_text()) / 1000.0
                        
                        # Read current (curr1_input is in mA)
                        curr_file = hwmon / "curr1_input"
                        if curr_file.exists():
                            result["current_a"] = float(curr_file.read_text()) / 1000.0
                        
                        result["power_w"] = result["voltage_v"] * result["current_a"]
                        break
        except Exception:
            pass
        
        return result
    
    def start_sampling(self, rate_hz: float = 100.0):
        """Start continuous power sampling in background thread.
        
        Uses perf_counter-based tick scheduling (same approach as
        core/power_monitor.py Ina219PowerMonitor) for accurate timing
        at high sample rates (e.g. 1kHz).
        """
        if self._sampling:
            return
        
        self._sampling = True
        self._samples = []
        self._stop_event.clear()
        
        interval = 1.0 / rate_hz
        
        def sample_loop():
            next_tick = time.perf_counter()
            while not self._stop_event.is_set():
                sample = self.collect()
                sample["mono_time"] = time.monotonic()
                self._samples.append(sample)
                next_tick += interval
                sleep_for = next_tick - time.perf_counter()
                if sleep_for > 0:
                    time.sleep(sleep_for)
        
        self._sample_thread = threading.Thread(target=sample_loop, daemon=True)
        self._sample_thread.start()
    
    def stop_sampling(self) -> List[Dict[str, float]]:
        """Stop sampling and return collected samples."""
        if not self._sampling:
            return []
        
        self._stop_event.set()
        if self._sample_thread:
            self._sample_thread.join(timeout=1.0)
        
        self._sampling = False
        samples = self._samples.copy()
        self._samples = []
        return samples
    
    def get_energy_stats(self, samples: List[Dict[str, float]] = None) -> Dict[str, float]:
        """Calculate energy statistics from samples."""
        if samples is None:
            samples = self._samples
        
        if len(samples) < 2:
            return {
                "energy_total_j": None,
                "power_avg_w": None,
                "power_peak_w": None,
                "duration_s": None,
            }
        
        # Filter out samples with None power_w (e.g., from failed sensor reads)
        valid_samples = [
            s for s in samples
            if isinstance(s.get("power_w"), (int, float))
        ]
        if len(valid_samples) < 2:
            return {
                "energy_total_j": None,
                "power_avg_w": None,
                "power_peak_w": None,
                "duration_s": None,
            }

        # Calculate energy using trapezoidal integration
        energy_j = 0.0
        powers = []
        voltages = []
        currents = []
        
        for i in range(1, len(valid_samples)):
            dt = valid_samples[i]["mono_time"] - valid_samples[i-1]["mono_time"]
            p_avg = (valid_samples[i]["power_w"] + valid_samples[i-1]["power_w"]) / 2.0
            energy_j += p_avg * dt
            powers.append(valid_samples[i]["power_w"])
            voltages.append(valid_samples[i].get("voltage_v", 0.0) or 0.0)
            currents.append(valid_samples[i].get("current_a", 0.0) or 0.0)
        
        duration = valid_samples[-1]["mono_time"] - valid_samples[0]["mono_time"]
        
        return {
            "energy_total_j": energy_j,
            "power_avg_w": sum(powers) / len(powers) if powers else 0.0,
            "power_peak_w": max(powers) if powers else 0.0,
            "power_min_w": min(powers) if powers else 0.0,
            "voltage_avg_v": sum(voltages) / len(voltages) if voltages else 0.0,
            "current_avg_a": sum(currents) / len(currents) if currents else 0.0,
            "duration_s": duration,
            "sample_count": len(samples),
        }


# =============================================================================
# NETWORK COLLECTOR
# =============================================================================

class NetworkCollector(BaseCollector):
    """Collects network statistics."""
    
    def __init__(self, interface: str = None):
        super().__init__("network")
        self.interface = interface
        self._last_stats = None
        self._last_time = None
    
    def collect(self) -> Dict[str, Any]:
        """Collect network statistics."""
        metrics = {
            "timestamp": time.time(),
            "rx_bytes": 0,
            "tx_bytes": 0,
            "rx_packets": 0,
            "tx_packets": 0,
            "rx_errors": 0,
            "tx_errors": 0,
            "rx_dropped": 0,
            "tx_dropped": 0,
        }
        
        if not HAS_PSUTIL:
            return metrics
        
        try:
            counters = psutil.net_io_counters(pernic=True)
            
            if self.interface and self.interface in counters:
                stats = counters[self.interface]
            else:
                # Use total
                stats = psutil.net_io_counters()
            
            metrics["rx_bytes"] = stats.bytes_recv
            metrics["tx_bytes"] = stats.bytes_sent
            metrics["rx_packets"] = stats.packets_recv
            metrics["tx_packets"] = stats.packets_sent
            metrics["rx_errors"] = stats.errin
            metrics["tx_errors"] = stats.errout
            metrics["rx_dropped"] = stats.dropin
            metrics["tx_dropped"] = stats.dropout
            
            # Calculate rates if we have previous reading
            if self._last_stats and self._last_time:
                dt = metrics["timestamp"] - self._last_time
                if dt > 0:
                    metrics["rx_rate_mbps"] = (metrics["rx_bytes"] - self._last_stats["rx_bytes"]) * 8 / dt / 1_000_000
                    metrics["tx_rate_mbps"] = (metrics["tx_bytes"] - self._last_stats["tx_bytes"]) * 8 / dt / 1_000_000
            
            self._last_stats = metrics.copy()
            self._last_time = metrics["timestamp"]
            
        except Exception as e:
            metrics["error"] = str(e)
        
        return metrics


# =============================================================================
# LATENCY TRACKER
# =============================================================================

class LatencyTracker:
    """Tracks packet latency using timestamps."""
    
    def __init__(self, max_samples: int = 10000):
        self.max_samples = max_samples
        self._samples: List[float] = []
        self._lock = threading.Lock()
    
    def record(self, latency_ms: float):
        """Record a latency sample."""
        with self._lock:
            self._samples.append(latency_ms)
            if len(self._samples) > self.max_samples:
                self._samples.pop(0)
    
    def get_stats(self) -> Dict[str, float]:
        """Get latency statistics."""
        with self._lock:
            samples = self._samples.copy()
        
        if not samples:
            return {
                "avg_ms": 0.0,
                "p50_ms": 0.0,
                "p95_ms": 0.0,
                "p99_ms": 0.0,
                "max_ms": 0.0,
                "min_ms": 0.0,
                "count": 0,
            }
        
        samples_sorted = sorted(samples)
        n = len(samples_sorted)
        
        return {
            "avg_ms": sum(samples) / n,
            "p50_ms": samples_sorted[int(n * 0.50)],
            "p95_ms": samples_sorted[int(n * 0.95)] if n >= 20 else samples_sorted[-1],
            "p99_ms": samples_sorted[int(n * 0.99)] if n >= 100 else samples_sorted[-1],
            "max_ms": samples_sorted[-1],
            "min_ms": samples_sorted[0],
            "count": n,
        }

    def get_samples(self) -> List[float]:
        """Return a copy of raw latency samples."""
        with self._lock:
            return self._samples.copy()
    
    def clear(self):
        """Clear all samples."""
        with self._lock:
            self._samples.clear()


# =============================================================================
# MAIN - Test collectors
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("METRICS COLLECTORS TEST")
    print("=" * 60)
    
    # Test Environment Collector
    print("\n--- Environment Collector ---")
    env = EnvironmentCollector()
    env_metrics = env.collect()
    for k, v in env_metrics.items():
        print(f"  {k}: {v}")
    
    # Test System Collector
    print("\n--- System Collector ---")
    sys_coll = SystemCollector()
    sys_metrics = sys_coll.collect()
    for k, v in sys_metrics.items():
        print(f"  {k}: {v}")
    
    # Test Power Collector
    print("\n--- Power Collector ---")
    pwr = PowerCollector(backend="auto")
    print(f"  Backend: {pwr.backend}")
    if pwr.backend != "none":
        pwr_metrics = pwr.collect()
        for k, v in pwr_metrics.items():
            print(f"  {k}: {v}")
    else:
        print("  No power sensor available")
    
    # Test Network Collector
    print("\n--- Network Collector ---")
    net = NetworkCollector()
    net_metrics = net.collect()
    for k, v in net_metrics.items():
        print(f"  {k}: {v}")
    
    print("\n" + "=" * 60)
    print("All collectors tested successfully!")
