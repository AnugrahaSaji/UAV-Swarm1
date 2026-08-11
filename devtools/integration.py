"""
Scheduler Integration for Dev Tools

This module provides integration hooks for the dev tools system.
It allows the scheduler to publish state to the data bus without
modifying the core scheduler or policy logic.

Usage:
    # In scheduler initialization:
    from devtools.integration import DevToolsIntegration
    
    integration = DevToolsIntegration.create_if_enabled()
    if integration:
        integration.start()
    
    # In scheduler tick:
    if integration:
        integration.update_policy(current_suite, action, ...)
        integration.update_telemetry(...)

CRITICAL: All methods are no-ops when dev tools are disabled.
The scheduler code can call these unconditionally.
"""

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from devtools.data_bus import DataBus, StressLevel
    from devtools.battery_sim import BatteryProvider
    from devtools.dashboard import DevDashboard
    from devtools.config import DevToolsConfig
    from devtools.obs_emitter import ObsEmitter, NullEmitter
    from devtools.obs_schema import NodeType

logger = logging.getLogger("devtools.integration")


class DevToolsIntegration:
    """
    Integration layer between scheduler and dev tools.
    
    This class provides a safe, no-op interface when dev tools are disabled,
    allowing scheduler code to call these methods unconditionally.
    
    Observability Plane Integration:
    - When OBS plane is enabled, state updates are also emitted via UDP
    - The emitter is fire-and-forget (no blocking, no backpressure)
    - OBS snapshots are sent to localhost for SSH forwarding to remote dashboard
    """
    
    def __init__(
        self,
        data_bus: "DataBus",
        battery_provider: Optional["BatteryProvider"] = None,
        dashboard: Optional["DevDashboard"] = None,
        config: Optional["DevToolsConfig"] = None,
        obs_emitter: Optional[Union["ObsEmitter", "NullEmitter"]] = None,
        node_type: Optional["NodeType"] = None
    ):
        self._data_bus = data_bus
        self._battery_provider = battery_provider
        self._dashboard = dashboard
        self._config = config
        self._obs_emitter = obs_emitter
        self._node_type = node_type
        self._enabled = True
        self._started = False
        
        # Cache for building OBS snapshots
        self._last_battery_snap = None
        self._last_telemetry_snap = None
        self._last_policy_snap = None
        self._last_proxy_snap = None
        
        logger.info("DevToolsIntegration created")
    
    @classmethod
    def create_if_enabled(
        cls,
        node_type: str = "drone"  # "drone" or "gcs"
    ) -> Optional["DevToolsIntegration"]:
        """
        Create integration if dev tools are enabled.
        
        Args:
            node_type: Either "drone" or "gcs" - determines OBS port
        
        Returns:
            DevToolsIntegration if enabled, None otherwise
        """
        try:
            import devtools
            if not devtools.is_enabled():
                logger.debug("Dev tools disabled, integration not created")
                return None
            
            config = devtools.get_config()
            data_bus = devtools.get_data_bus()
            
            battery_provider = None
            if config.battery_simulation.enabled:
                battery_provider = devtools.get_battery_provider()
            
            dashboard = None
            if config.gui.enabled:
                dashboard = devtools.start_dashboard()
            
            # Create OBS emitter if enabled
            obs_emitter = None
            obs_node_type = None
            if config.observability_plane.enabled:
                from devtools.obs_emitter import ObsEmitter, NullEmitter
                from devtools.obs_schema import NodeType
                
                # Determine node type and port
                if node_type.lower() == "gcs":
                    obs_node_type = NodeType.GCS
                    target_port = config.observability_plane.gcs_port
                else:
                    obs_node_type = NodeType.DRONE
                    target_port = config.observability_plane.drone_port
                
                obs_emitter = ObsEmitter(
                    node=obs_node_type,
                    node_id=config.observability_plane.node_id,
                    target_host="127.0.0.1",  # Always localhost for SSH forwarding
                    target_port=target_port,
                    enabled=True,
                )
                logger.info(f"OBS emitter created for {obs_node_type.value} on port {target_port}")
            
            return cls(
                data_bus=data_bus,
                battery_provider=battery_provider,
                dashboard=dashboard,
                config=config,
                obs_emitter=obs_emitter,
                node_type=obs_node_type
            )
            
        except ImportError:
            logger.debug("Dev tools not available")
            return None
        except Exception as e:
            logger.warning(f"Failed to create dev tools integration: {e}")
            return None
    
    def start(self) -> None:
        """Start the integration (battery provider, OBS emitter, etc.)."""
        if self._started:
            return
        
        if self._battery_provider:
            self._battery_provider.start()
        
        if self._obs_emitter:
            self._obs_emitter.start()
        
        self._started = True
        logger.info("DevToolsIntegration started")
    
    def stop(self) -> None:
        """Stop all dev tools components."""
        if self._obs_emitter:
            try:
                self._obs_emitter.stop()
            except Exception:
                pass
        
        if self._dashboard:
            try:
                self._dashboard.stop()
            except Exception:
                pass
        
        if self._battery_provider:
            try:
                self._battery_provider.stop()
            except Exception:
                pass
        
        if self._data_bus:
            try:
                self._data_bus.stop()
            except Exception:
                pass
        
        self._started = False
        logger.info("DevToolsIntegration stopped")
    
    # =========================================================================
    # State Update Methods (called by scheduler)
    # =========================================================================
    
    def update_policy(
        self,
        current_suite: str,
        current_action: str = "HOLD",
        target_suite: Optional[str] = None,
        reasons: Optional[List[str]] = None,
        confidence: float = 0.0,
        cooldown_remaining_ms: float = 0.0,
        local_epoch: int = 0,
        armed: bool = False
    ) -> None:
        """
        Update policy state in the data bus and emit OBS snapshot.
        
        Call this from the scheduler tick after policy evaluation.
        """
        if not self._enabled:
            return
        
        self._data_bus.update_policy(
            current_suite=current_suite,
            current_action=current_action,
            target_suite=target_suite,
            reasons=reasons,
            confidence=confidence,
            cooldown_remaining_ms=cooldown_remaining_ms,
            local_epoch=local_epoch,
            armed=armed
        )
        
        # Cache and emit OBS snapshot
        if self._obs_emitter:
            from devtools.obs_schema import PolicySnapshot
            self._last_policy_snap = PolicySnapshot(
                current_suite=current_suite,
                current_action=current_action,
                target_suite=target_suite,
                reasons=reasons or [],
                confidence=confidence,
                cooldown_remaining_ms=cooldown_remaining_ms,
                local_epoch=local_epoch,
                armed=armed,
            )
            self._emit_obs_snapshot()
    
    def update_telemetry(
        self,
        rx_pps: float = 0.0,
        gap_p95_ms: float = 0.0,
        blackout_count: int = 0,
        jitter_ms: float = 0.0,
        telemetry_age_ms: float = -1.0,
        sample_count: int = 0
    ) -> None:
        """
        Update telemetry state in the data bus and emit OBS snapshot.
        
        Call this from the telemetry receiver or scheduler tick.
        """
        if not self._enabled:
            return
        
        self._data_bus.update_telemetry(
            rx_pps=rx_pps,
            gap_p95_ms=gap_p95_ms,
            blackout_count=blackout_count,
            jitter_ms=jitter_ms,
            telemetry_age_ms=telemetry_age_ms,
            sample_count=sample_count
        )
        
        # Cache for OBS snapshot (telemetry updates are frequent, don't emit alone)
        if self._obs_emitter:
            from devtools.obs_schema import TelemetrySnapshot
            self._last_telemetry_snap = TelemetrySnapshot(
                rx_pps=rx_pps,
                gap_p95_ms=gap_p95_ms,
                blackout_count=blackout_count,
                jitter_ms=jitter_ms,
                telemetry_age_ms=telemetry_age_ms,
                sample_count=sample_count,
            )
    
    def update_proxy(
        self,
        encrypted_pps: float = 0.0,
        plaintext_pps: float = 0.0,
        replay_drops: int = 0,
        handshake_status: str = "unknown",
        bytes_encrypted: int = 0,
        bytes_decrypted: int = 0
    ) -> None:
        """
        Update proxy state in the data bus.
        
        Call this from the proxy stats collector.
        """
        if not self._enabled:
            return
        
        self._data_bus.update_proxy(
            encrypted_pps=encrypted_pps,
            plaintext_pps=plaintext_pps,
            replay_drops=replay_drops,
            handshake_status=handshake_status,
            bytes_encrypted=bytes_encrypted,
            bytes_decrypted=bytes_decrypted
        )
        
        # Cache for OBS snapshot
        if self._obs_emitter:
            from devtools.obs_schema import ProxySnapshot
            self._last_proxy_snap = ProxySnapshot(
                encrypted_pps=encrypted_pps,
                plaintext_pps=plaintext_pps,
                replay_drops=replay_drops,
                handshake_status=handshake_status,
                bytes_encrypted=bytes_encrypted,
                bytes_decrypted=bytes_decrypted,
            )
    
    def update_battery(
        self,
        voltage_mv: int,
        percentage: int = 0,
        rate_mv_per_sec: float = 0.0,
        stress_level: str = "low",
        source: str = "unknown",
        simulation_mode: str = "stable",
        is_simulated: bool = False
    ) -> None:
        """
        Update battery state in the data bus (alternative to battery provider).
        
        Call this if not using the battery provider simulation.
        """
        if not self._enabled:
            return
        
        from devtools.data_bus import StressLevel
        try:
            sl = StressLevel(stress_level)
        except ValueError:
            sl = StressLevel.LOW
        
        self._data_bus.update_battery(
            voltage_mv=voltage_mv,
            percentage=percentage,
            rate_mv_per_sec=rate_mv_per_sec,
            stress_level=sl,
            source=source,
            simulation_mode=simulation_mode,
            is_simulated=is_simulated
        )
        
        # Cache for OBS snapshot
        if self._obs_emitter:
            from devtools.obs_schema import BatterySnapshot
            self._last_battery_snap = BatterySnapshot(
                voltage_mv=voltage_mv,
                percentage=percentage,
                rate_mv_per_sec=rate_mv_per_sec,
                stress_level=stress_level,
                source=source,
                is_simulated=is_simulated,
                simulation_mode=simulation_mode,
            )
    
    def add_event(
        self,
        event_type: str,
        label: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Add a timeline event.
        
        Event types: "suite_switch", "policy_action", "battery_event", "link_event"
        """
        if not self._enabled:
            return
        
        self._data_bus.add_event(event_type, label, details)
    
    def _emit_obs_snapshot(self) -> None:
        """
        Emit OBS snapshot with all cached state.
        
        Fire-and-forget - no blocking, no backpressure.
        """
        if not self._obs_emitter:
            return
        
        self._obs_emitter.emit_snapshot(
            battery=self._last_battery_snap,
            telemetry=self._last_telemetry_snap,
            policy=self._last_policy_snap,
            proxy=self._last_proxy_snap,
        )
    
    def emit_snapshot_now(self) -> bool:
        """
        Force immediate OBS snapshot emission.
        
        Useful for periodic snapshot regardless of state changes.
        
        Returns:
            True if emitted, False if disabled/not started.
        """
        if not self._obs_emitter:
            return False
        
        return self._obs_emitter.emit_snapshot(
            battery=self._last_battery_snap,
            telemetry=self._last_telemetry_snap,
            policy=self._last_policy_snap,
            proxy=self._last_proxy_snap,
        )
    
    # =========================================================================
    # Battery Provider Access
    # =========================================================================
    
    def get_battery_provider(self) -> Optional["BatteryProvider"]:
        """Get the battery provider (for LocalMonitor override)."""
        return self._battery_provider
    
    def is_battery_simulated(self) -> bool:
        """Check if battery simulation is active."""
        return self._battery_provider is not None and self._battery_provider.is_simulated()
    
    # =========================================================================
    # State Query Methods
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get integration statistics."""
        stats = {
            "enabled": self._enabled,
            "started": self._started,
            "battery_simulated": self.is_battery_simulated(),
            "gui_active": self._dashboard is not None,
            "bus_stats": self._data_bus.get_stats() if self._data_bus else None,
            "obs_plane_active": self._obs_emitter is not None and self._obs_emitter.is_active,
        }
        
        if self._obs_emitter:
            stats["obs_emitter_stats"] = self._obs_emitter.get_stats()
        
        return stats


class NullIntegration:
    """
    No-op integration for when dev tools are disabled.
    
    All methods are safe to call and do nothing.
    """
    
    def start(self) -> None:
        pass
    
    def stop(self) -> None:
        pass
    
    def update_policy(self, *args, **kwargs) -> None:
        pass
    
    def update_telemetry(self, *args, **kwargs) -> None:
        pass
    
    def update_proxy(self, *args, **kwargs) -> None:
        pass
    
    def update_battery(self, *args, **kwargs) -> None:
        pass
    
    def add_event(self, *args, **kwargs) -> None:
        pass
    
    def emit_snapshot_now(self) -> bool:
        return False
    
    def get_battery_provider(self):
        return None
    
    def is_battery_simulated(self) -> bool:
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        return {"enabled": False, "obs_plane_active": False}


def get_integration() -> DevToolsIntegration:
    """
    Get a dev tools integration instance.
    
    Returns DevToolsIntegration if enabled, NullIntegration otherwise.
    This allows scheduler code to use the integration unconditionally.
    
    Usage:
        integration = get_integration()
        integration.update_policy(...)  # Safe even if disabled
    """
    integration = DevToolsIntegration.create_if_enabled()
    if integration is None:
        return NullIntegration()
    return integration
