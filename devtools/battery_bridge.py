"""
Battery Provider Bridge

Non-invasive injection point for battery data providers.
This module allows dev tools to override battery readings WITHOUT
modifying the LocalMonitor, scheduler, or policy code.

Architecture:
    1. LocalMonitorBridge wraps LocalMonitor
    2. When dev tools enabled: uses BatteryProvider for battery data
    3. When dev tools disabled: passes through to original LocalMonitor
    4. Scheduler code imports LocalMonitorBridge instead of LocalMonitor directly

CRITICAL: This bridge maintains 100% backward compatibility.
When dev_tools.enabled = false, behavior is IDENTICAL to using LocalMonitor directly.
"""

import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from devtools.battery_sim import BatteryProvider
    from devtools.data_bus import DataBus

# Import production LocalMonitor and LocalMetrics
from sscheduler.local_mon import LocalMonitor, LocalMetrics

logger = logging.getLogger("devtools.battery_bridge")


class LocalMonitorBridge:
    """
    Bridge wrapper for LocalMonitor with optional battery override.
    
    This class provides the EXACT same interface as LocalMonitor,
    but allows battery data to be sourced from a BatteryProvider
    when dev tools are enabled.
    
    Usage:
        # In scheduler code:
        from devtools.battery_bridge import LocalMonitorBridge as LocalMonitor
        
        # Or with explicit creation:
        monitor = LocalMonitorBridge.create_with_devtools()
    """
    
    def __init__(
        self,
        mav_port: int = 14555,
        battery_provider: Optional["BatteryProvider"] = None,
        data_bus: Optional["DataBus"] = None
    ):
        """
        Args:
            mav_port: MAVLink port for real LocalMonitor
            battery_provider: Optional BatteryProvider for battery override
            data_bus: Optional DataBus for observability
        """
        # Create real LocalMonitor
        self._real_monitor = LocalMonitor(mav_port=mav_port)
        self._battery_provider = battery_provider
        self._data_bus = data_bus
        self._override_enabled = battery_provider is not None
        
        logger.info(f"LocalMonitorBridge created (override_enabled={self._override_enabled})")
    
    @classmethod
    def create_with_devtools(
        cls,
        mav_port: int = 14555,
        local_monitor: Optional[LocalMonitor] = None
    ) -> "LocalMonitorBridge":
        """
        Factory method that automatically configures dev tools if enabled.
        
        This is the recommended way to create a LocalMonitorBridge.
        
        Args:
            mav_port: MAVLink port for real LocalMonitor
            local_monitor: Optional existing LocalMonitor to wrap
        
        Returns:
            LocalMonitorBridge configured based on dev_tools settings
        """
        battery_provider = None
        data_bus = None
        
        try:
            import devtools
            if devtools.is_enabled():
                config = devtools.get_config()
                data_bus = devtools.get_data_bus()
                
                if config.battery_simulation.enabled:
                    battery_provider = devtools.get_battery_provider()
                    logger.info("Dev tools battery simulation enabled")
        except ImportError:
            logger.debug("Dev tools not available")
        except Exception as e:
            logger.warning(f"Dev tools initialization error: {e}")
        
        bridge = cls(
            mav_port=mav_port,
            battery_provider=battery_provider,
            data_bus=data_bus
        )
        
        # If existing monitor provided, copy its state
        if local_monitor is not None:
            bridge._real_monitor = local_monitor
        
        return bridge
    
    # =========================================================================
    # LocalMonitor Interface (pass-through)
    # =========================================================================
    
    def start(self) -> None:
        """Start the underlying monitor."""
        self._real_monitor.start()
        
        # Start battery provider if available
        if self._battery_provider:
            self._battery_provider.start()
    
    def stop(self) -> None:
        """Stop the underlying monitor."""
        self._real_monitor.stop()
        
        # Stop battery provider if available
        if self._battery_provider:
            self._battery_provider.stop()
    
    def get_metrics(self) -> LocalMetrics:
        """
        Return metrics snapshot with optional battery override.
        
        When battery_provider is set:
        - battery_mv, battery_pct, battery_roc come from provider
        - All other metrics come from real LocalMonitor
        
        When battery_provider is None:
        - Returns unmodified LocalMetrics from real monitor
        """
        # Get real metrics
        real_metrics = self._real_monitor.get_metrics()
        
        # If no override, return as-is
        if not self._override_enabled or not self._battery_provider:
            # Update data bus with real data
            if self._data_bus:
                self._update_data_bus(real_metrics, is_simulated=False)
            return real_metrics
        
        # Override battery values
        reading = self._battery_provider.get_reading()
        
        # Create new LocalMetrics with overridden battery
        overridden = LocalMetrics(
            temp_c=real_metrics.temp_c,
            temp_roc=real_metrics.temp_roc,
            cpu_pct=real_metrics.cpu_pct,
            battery_mv=reading.voltage_mv,
            battery_pct=reading.percentage,
            battery_roc=reading.rate_mv_per_sec * 60.0,  # Convert mV/s to mV/min
            armed=real_metrics.armed,
            mav_age_s=real_metrics.mav_age_s,
        )
        
        # Update data bus
        if self._data_bus:
            self._update_data_bus(overridden, is_simulated=True, mode=reading.simulation_mode)
        
        return overridden
    
    def _update_data_bus(
        self,
        metrics: LocalMetrics,
        is_simulated: bool,
        mode: str = "none"
    ) -> None:
        """Update data bus with current metrics."""
        if not self._data_bus:
            return
        
        from devtools.data_bus import StressLevel
        
        # Calculate stress level
        v = metrics.battery_mv
        rate = metrics.battery_roc / 60.0  # Convert to mV/s
        
        if v < 14000 or rate < -20:
            stress = StressLevel.CRITICAL
        elif v < 14800 or rate < -10:
            stress = StressLevel.HIGH
        elif v < 15200 or rate < -5:
            stress = StressLevel.MEDIUM
        else:
            stress = StressLevel.LOW
        
        self._data_bus.update_battery(
            voltage_mv=metrics.battery_mv,
            percentage=metrics.battery_pct,
            rate_mv_per_sec=metrics.battery_roc / 60.0,
            stress_level=stress,
            source="simulated" if is_simulated else "mavlink",
            simulation_mode=mode,
            is_simulated=is_simulated,
        )
    
    # =========================================================================
    # Additional Properties (for compatibility)
    # =========================================================================
    
    @property
    def running(self) -> bool:
        """Check if monitor is running."""
        return self._real_monitor.running
    
    @property
    def battery_mv(self) -> int:
        """Get current battery voltage."""
        if self._override_enabled and self._battery_provider:
            return self._battery_provider.get_battery_mv()
        return self._real_monitor.battery_mv
    
    @property
    def battery_pct(self) -> int:
        """Get current battery percentage."""
        if self._override_enabled and self._battery_provider:
            return self._battery_provider.get_battery_pct()
        return self._real_monitor.battery_pct
    
    @property
    def armed(self) -> bool:
        """Get armed state."""
        return self._real_monitor.armed
    
    @property
    def temp_c(self) -> float:
        """Get temperature."""
        return self._real_monitor.temp_c
    
    @property
    def cpu_pct(self) -> float:
        """Get CPU percentage."""
        return self._real_monitor.cpu_pct
    
    # =========================================================================
    # Dev Tools Control
    # =========================================================================
    
    def set_battery_provider(self, provider: Optional["BatteryProvider"]) -> None:
        """Set or clear the battery provider at runtime."""
        self._battery_provider = provider
        self._override_enabled = provider is not None
        logger.info(f"Battery provider {'set' if provider else 'cleared'}")
    
    def is_override_enabled(self) -> bool:
        """Check if battery override is active."""
        return self._override_enabled


def get_local_monitor(mav_port: int = 14555) -> LocalMonitorBridge:
    """
    Get a LocalMonitor instance with dev tools support.
    
    This is the recommended way to get a local monitor in scheduler code.
    It automatically enables dev tools features when configured.
    
    Args:
        mav_port: MAVLink port for real LocalMonitor
    
    Returns:
        LocalMonitorBridge (compatible with LocalMonitor interface)
    """
    return LocalMonitorBridge.create_with_devtools(mav_port=mav_port)
