"""
Battery Provider Abstraction and Simulation

Provides:
- BatteryProvider: Abstract interface for battery data
- RealBatteryProvider: Pass-through to MAVLink (production path)
- SimulatedBatteryProvider: Configurable battery simulation for lab testing

Simulation Modes:
- stable: Constant voltage (default)
- slow_drain: Slow linear drain (~5 mV/sec)
- fast_drain: Fast linear drain (~20 mV/sec)
- throttle_drain: Accelerated drain under load
- step_drop: Sudden voltage drop (failure simulation)
- recovery: Voltage recovery/rebound

CRITICAL: This module NEVER modifies scheduler or policy logic.
It only provides battery data through the BatteryProvider interface.
"""

import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from devtools.config import DevToolsConfig, BatterySimConfig
    from devtools.data_bus import DataBus, StressLevel

logger = logging.getLogger("devtools.battery_sim")


class SimulationMode(str, Enum):
    """Battery simulation modes."""
    STABLE = "stable"
    SLOW_DRAIN = "slow_drain"
    FAST_DRAIN = "fast_drain"
    THROTTLE_DRAIN = "throttle_drain"
    STEP_DROP = "step_drop"
    RECOVERY = "recovery"


@dataclass
class BatteryReading:
    """Battery reading snapshot."""
    voltage_mv: int
    percentage: int
    rate_mv_per_sec: float
    timestamp_mono: float
    source: str  # "mavlink" or "simulated"
    simulation_mode: str
    is_simulated: bool


class BatteryProvider(ABC):
    """
    Abstract battery data provider.
    
    This interface allows the scheduler to consume battery data
    without knowing whether it comes from MAVLink or simulation.
    """
    
    @abstractmethod
    def get_battery_mv(self) -> int:
        """Get current battery voltage in millivolts."""
        pass
    
    @abstractmethod
    def get_battery_pct(self) -> int:
        """Get current battery percentage (0-100)."""
        pass
    
    @abstractmethod
    def get_battery_rate(self) -> float:
        """Get battery drain rate in mV/sec (negative = draining)."""
        pass
    
    @abstractmethod
    def get_reading(self) -> BatteryReading:
        """Get complete battery reading."""
        pass
    
    @abstractmethod
    def is_simulated(self) -> bool:
        """Return True if this is a simulated provider."""
        pass
    
    @abstractmethod
    def start(self) -> None:
        """Start the provider (if needed)."""
        pass
    
    @abstractmethod
    def stop(self) -> None:
        """Stop the provider."""
        pass


class RealBatteryProvider(BatteryProvider):
    """
    Real battery provider - pass-through to MAVLink data.
    
    This provider does NOT modify any production behavior.
    It simply reads from the existing LocalMonitor interface.
    """
    
    def __init__(self, local_monitor=None, data_bus: Optional["DataBus"] = None):
        """
        Args:
            local_monitor: Instance of LocalMonitor (from sscheduler/local_mon.py)
            data_bus: Optional DataBus for observability updates
        """
        self._local_monitor = local_monitor
        self._data_bus = data_bus
        self._last_voltage = 0
        self._last_rate = 0.0
        self._last_time = 0.0
    
    def get_battery_mv(self) -> int:
        if self._local_monitor is None:
            return 0
        metrics = self._local_monitor.get_metrics()
        return metrics.battery_mv
    
    def get_battery_pct(self) -> int:
        if self._local_monitor is None:
            return 0
        metrics = self._local_monitor.get_metrics()
        return metrics.battery_pct
    
    def get_battery_rate(self) -> float:
        if self._local_monitor is None:
            return 0.0
        metrics = self._local_monitor.get_metrics()
        # Convert from mV/min to mV/sec
        return metrics.battery_roc / 60.0
    
    def get_reading(self) -> BatteryReading:
        now = time.monotonic()
        voltage = self.get_battery_mv()
        pct = self.get_battery_pct()
        rate = self.get_battery_rate()
        
        reading = BatteryReading(
            voltage_mv=voltage,
            percentage=pct,
            rate_mv_per_sec=rate,
            timestamp_mono=now,
            source="mavlink",
            simulation_mode="none",
            is_simulated=False,
        )
        
        # Update data bus if available
        if self._data_bus:
            from devtools.data_bus import StressLevel
            stress = self._calc_stress(voltage, rate)
            self._data_bus.update_battery(
                voltage_mv=voltage,
                percentage=pct,
                rate_mv_per_sec=rate,
                stress_level=stress,
                source="mavlink",
                is_simulated=False,
            )
        
        return reading
    
    def _calc_stress(self, voltage: int, rate: float) -> "StressLevel":
        """Calculate stress level from voltage and rate."""
        from devtools.data_bus import StressLevel
        if voltage < 14000 or rate < -20:
            return StressLevel.CRITICAL
        if voltage < 14800 or rate < -10:
            return StressLevel.HIGH
        if voltage < 15200 or rate < -5:
            return StressLevel.MEDIUM
        return StressLevel.LOW
    
    def is_simulated(self) -> bool:
        return False
    
    def start(self) -> None:
        logger.info("RealBatteryProvider started (pass-through mode)")
    
    def stop(self) -> None:
        logger.info("RealBatteryProvider stopped")


class SimulatedBatteryProvider(BatteryProvider):
    """
    Simulated battery provider for lab testing.
    
    Supports multiple simulation modes with configurable parameters.
    All state is managed internally - no production code modified.
    """
    
    def __init__(
        self,
        config: "BatterySimConfig",
        data_bus: Optional["DataBus"] = None,
        update_hz: float = 10.0
    ):
        """
        Args:
            config: Battery simulation configuration
            data_bus: Optional DataBus for observability updates
            update_hz: Internal update rate (Hz)
        """
        self._config = config
        self._data_bus = data_bus
        self._update_hz = update_hz
        
        # State
        self._mode = SimulationMode(config.default_mode)
        self._voltage_mv = config.start_mv
        self._rate_mv_per_sec = 0.0
        self._last_update = time.monotonic()
        
        # Mode-specific state
        self._throttle_active = False  # For throttle_drain mode
        self._step_triggered = False   # For step_drop mode (one-shot)
        self._recovery_target = config.max_mv  # For recovery mode
        
        # Threading
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        
        # Callbacks for mode changes
        self._on_mode_change: Optional[Callable[[SimulationMode], None]] = None
        
        logger.info(f"SimulatedBatteryProvider initialized: mode={self._mode.value}, "
                   f"start_mv={self._voltage_mv}")
    
    # =========================================================================
    # BatteryProvider Interface
    # =========================================================================
    
    def get_battery_mv(self) -> int:
        with self._lock:
            return int(self._voltage_mv)
    
    def get_battery_pct(self) -> int:
        with self._lock:
            # Linear mapping from min_mv (0%) to max_mv (100%)
            min_mv = self._config.min_mv
            max_mv = self._config.max_mv
            if max_mv <= min_mv:
                return 50
            pct = (self._voltage_mv - min_mv) / (max_mv - min_mv) * 100
            return max(0, min(100, int(pct)))
    
    def get_battery_rate(self) -> float:
        with self._lock:
            return self._rate_mv_per_sec
    
    def get_reading(self) -> BatteryReading:
        with self._lock:
            return BatteryReading(
                voltage_mv=int(self._voltage_mv),
                percentage=self.get_battery_pct(),
                rate_mv_per_sec=self._rate_mv_per_sec,
                timestamp_mono=time.monotonic(),
                source="simulated",
                simulation_mode=self._mode.value,
                is_simulated=True,
            )
    
    def is_simulated(self) -> bool:
        return True
    
    def start(self) -> None:
        if self._running:
            return
        
        self._running = True
        self._last_update = time.monotonic()
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()
        logger.info(f"SimulatedBatteryProvider started (mode={self._mode.value})")
    
    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("SimulatedBatteryProvider stopped")
    
    # =========================================================================
    # Simulation Control (called by GUI)
    # =========================================================================
    
    def set_mode(self, mode: SimulationMode) -> None:
        """Change simulation mode at runtime."""
        with self._lock:
            old_mode = self._mode
            self._mode = mode
            
            # Reset mode-specific state
            if mode == SimulationMode.STEP_DROP:
                self._step_triggered = False
            if mode == SimulationMode.RECOVERY:
                self._recovery_target = self._config.max_mv
            
            logger.info(f"Battery simulation mode changed: {old_mode.value} -> {mode.value}")
        
        if self._on_mode_change:
            self._on_mode_change(mode)
        
        # Add event to data bus
        if self._data_bus:
            self._data_bus.add_event(
                "battery_event",
                f"Mode: {mode.value}",
                {"old_mode": old_mode.value, "new_mode": mode.value}
            )
    
    def get_mode(self) -> SimulationMode:
        """Get current simulation mode."""
        with self._lock:
            return self._mode
    
    def set_voltage(self, voltage_mv: int) -> None:
        """Manually set voltage (for testing)."""
        with self._lock:
            self._voltage_mv = max(self._config.min_mv, min(self._config.max_mv, voltage_mv))
            logger.debug(f"Battery voltage set to {self._voltage_mv} mV")
    
    def set_throttle_active(self, active: bool) -> None:
        """Set throttle state for throttle_drain mode."""
        with self._lock:
            self._throttle_active = active
    
    def trigger_step_drop(self) -> None:
        """Trigger a step drop (for step_drop mode)."""
        with self._lock:
            if self._mode == SimulationMode.STEP_DROP and not self._step_triggered:
                self._voltage_mv = max(
                    self._config.min_mv,
                    self._voltage_mv - self._config.step_drop_mv
                )
                self._step_triggered = True
                logger.warning(f"Battery step drop triggered: {self._voltage_mv} mV")
    
    def set_drain_rate(self, rate_mv_per_sec: float) -> None:
        """Override drain rate (for custom testing)."""
        with self._lock:
            # This affects slow_drain and fast_drain modes
            if self._mode == SimulationMode.SLOW_DRAIN:
                self._config.slow_drain_mv_per_sec = abs(rate_mv_per_sec)
            elif self._mode == SimulationMode.FAST_DRAIN:
                self._config.fast_drain_mv_per_sec = abs(rate_mv_per_sec)
    
    def reset(self) -> None:
        """Reset to initial state."""
        with self._lock:
            self._voltage_mv = self._config.start_mv
            self._rate_mv_per_sec = 0.0
            self._step_triggered = False
            self._throttle_active = False
            logger.info("Battery simulation reset")
    
    def set_on_mode_change(self, callback: Callable[[SimulationMode], None]) -> None:
        """Set callback for mode changes."""
        self._on_mode_change = callback
    
    # =========================================================================
    # Internal Update Loop
    # =========================================================================
    
    def _update_loop(self) -> None:
        """Internal simulation update loop."""
        interval = 1.0 / self._update_hz
        
        while self._running:
            try:
                now = time.monotonic()
                dt = now - self._last_update
                self._last_update = now
                
                with self._lock:
                    self._simulate_tick(dt)
                    self._update_data_bus()
                
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"Battery simulation error: {e}")
                time.sleep(0.1)
    
    def _simulate_tick(self, dt: float) -> None:
        """Execute one simulation tick (must be called with lock held)."""
        mode = self._mode
        
        if mode == SimulationMode.STABLE:
            # No change
            self._rate_mv_per_sec = 0.0
            
        elif mode == SimulationMode.SLOW_DRAIN:
            rate = self._config.slow_drain_mv_per_sec
            self._voltage_mv = max(
                self._config.min_mv,
                self._voltage_mv - rate * dt
            )
            self._rate_mv_per_sec = -rate
            
        elif mode == SimulationMode.FAST_DRAIN:
            rate = self._config.fast_drain_mv_per_sec
            self._voltage_mv = max(
                self._config.min_mv,
                self._voltage_mv - rate * dt
            )
            self._rate_mv_per_sec = -rate
            
        elif mode == SimulationMode.THROTTLE_DRAIN:
            base_rate = self._config.slow_drain_mv_per_sec
            if self._throttle_active:
                rate = base_rate * self._config.throttle_drain_factor
            else:
                rate = base_rate
            self._voltage_mv = max(
                self._config.min_mv,
                self._voltage_mv - rate * dt
            )
            self._rate_mv_per_sec = -rate
            
        elif mode == SimulationMode.STEP_DROP:
            # Step drop is triggered externally, here we just hold
            self._rate_mv_per_sec = 0.0
            
        elif mode == SimulationMode.RECOVERY:
            rate = self._config.recovery_mv_per_sec
            if self._voltage_mv < self._recovery_target:
                self._voltage_mv = min(
                    self._recovery_target,
                    self._voltage_mv + rate * dt
                )
                self._rate_mv_per_sec = rate
            else:
                self._rate_mv_per_sec = 0.0
    
    def _update_data_bus(self) -> None:
        """Update data bus with current state (must be called with lock held)."""
        if self._data_bus is None:
            return
        
        from devtools.data_bus import StressLevel
        stress = self._calc_stress()
        
        self._data_bus.update_battery(
            voltage_mv=int(self._voltage_mv),
            percentage=self.get_battery_pct(),
            rate_mv_per_sec=self._rate_mv_per_sec,
            stress_level=stress,
            source="simulated",
            simulation_mode=self._mode.value,
            is_simulated=True,
        )
    
    def _calc_stress(self) -> "StressLevel":
        """Calculate stress level based on current state."""
        from devtools.data_bus import StressLevel
        
        v = self._voltage_mv
        rate = self._rate_mv_per_sec
        
        # Critical: very low voltage or very fast drain
        if v < self._config.min_mv + 1000:  # Within 1V of min
            return StressLevel.CRITICAL
        if rate < -15:  # Fast drain
            return StressLevel.CRITICAL
        
        # High: low voltage or moderate drain
        if v < 14800:
            return StressLevel.HIGH
        if rate < -10:
            return StressLevel.HIGH
        
        # Medium: warning zone
        if v < 15200:
            return StressLevel.MEDIUM
        if rate < -5:
            return StressLevel.MEDIUM
        
        return StressLevel.LOW


def create_battery_provider(
    config: "DevToolsConfig",
    local_monitor=None,
    data_bus: Optional["DataBus"] = None
) -> BatteryProvider:
    """
    Factory function to create the appropriate battery provider.
    
    Args:
        config: Dev tools configuration
        local_monitor: Optional LocalMonitor instance for real battery
        data_bus: Optional DataBus for observability
    
    Returns:
        SimulatedBatteryProvider if battery_simulation.enabled
        RealBatteryProvider otherwise
    """
    if config.battery_simulation.enabled:
        logger.info("Creating SimulatedBatteryProvider")
        return SimulatedBatteryProvider(
            config=config.battery_simulation,
            data_bus=data_bus,
        )
    else:
        logger.info("Creating RealBatteryProvider (pass-through)")
        return RealBatteryProvider(
            local_monitor=local_monitor,
            data_bus=data_bus,
        )
