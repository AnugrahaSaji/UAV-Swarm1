"""
Dev Tools Configuration Loader

Loads dev_tools configuration from settings.json.
Provides strongly-typed configuration dataclasses.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger("devtools.config")

SETTINGS_PATH = Path(__file__).parent.parent / "settings.json"


@dataclass
class BatterySimConfig:
    """Battery simulation configuration."""
    enabled: bool = False
    default_mode: str = "stable"
    start_mv: int = 16000
    min_mv: int = 13000
    max_mv: int = 17000
    
    # Mode-specific defaults
    slow_drain_mv_per_sec: float = 5.0      # ~300 mV/min
    fast_drain_mv_per_sec: float = 20.0     # ~1200 mV/min  
    throttle_drain_factor: float = 2.0      # Multiplier under load
    step_drop_mv: int = 2000                # Sudden voltage drop
    recovery_mv_per_sec: float = 10.0       # Recovery rate
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "BatterySimConfig":
        return cls(
            enabled=d.get("enabled", False),
            default_mode=d.get("default_mode", "stable"),
            start_mv=d.get("start_mv", 16000),
            min_mv=d.get("min_mv", 13000),
            max_mv=d.get("max_mv", 17000),
            slow_drain_mv_per_sec=d.get("slow_drain_mv_per_sec", 5.0),
            fast_drain_mv_per_sec=d.get("fast_drain_mv_per_sec", 20.0),
            throttle_drain_factor=d.get("throttle_drain_factor", 2.0),
            step_drop_mv=d.get("step_drop_mv", 2000),
            recovery_mv_per_sec=d.get("recovery_mv_per_sec", 10.0),
        )


@dataclass
class GuiConfig:
    """GUI dashboard configuration."""
    enabled: bool = False
    refresh_hz: float = 5.0
    window_width: int = 1200
    window_height: int = 800
    timeline_points: int = 300  # ~60 seconds at 5Hz
    graph_update_hz: float = 2.0  # Graph update rate (can be slower than data)
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "GuiConfig":
        return cls(
            enabled=d.get("enabled", False),
            refresh_hz=d.get("refresh_hz", 5.0),
            window_width=d.get("window_width", 1200),
            window_height=d.get("window_height", 800),
            timeline_points=d.get("timeline_points", 300),
            graph_update_hz=d.get("graph_update_hz", 2.0),
        )


@dataclass
class ObservabilityPlaneConfig:
    """
    Observability Plane configuration.
    
    SSH Port Forwarding Setup:
      # On laptop, forward drone's OBS port:
      ssh -L 59001:localhost:59001 user@drone-pi
      
      # On laptop, forward GCS's OBS port (if GCS is remote):
      ssh -L 59002:localhost:59002 user@gcs-host
    
    Ports:
      - drone_port: UDP port for drone snapshots (default 59001)
      - gcs_port: UDP port for GCS snapshots (default 59002)
      
    Node Identity:
      - node_id: Unique identifier for this node (defaults to hostname)
    """
    enabled: bool = False
    
    # Node identity
    node_id: str = ""  # Empty = use hostname
    
    # UDP ports (localhost only for SSH forwarding)
    drone_port: int = 59001
    gcs_port: int = 59002
    listen_host: str = "127.0.0.1"  # SECURITY: localhost only
    
    # Emitter settings
    emit_interval_ms: float = 200.0  # 5 Hz default
    emit_on_change: bool = True      # Also emit on state change
    
    # Receiver settings (for dashboard)
    receive_drone: bool = True       # Listen for drone snapshots
    receive_gcs: bool = True         # Listen for GCS snapshots
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ObservabilityPlaneConfig":
        return cls(
            enabled=d.get("enabled", False),
            node_id=d.get("node_id", ""),
            drone_port=d.get("drone_port", 59001),
            gcs_port=d.get("gcs_port", 59002),
            listen_host=d.get("listen_host", "127.0.0.1"),
            emit_interval_ms=d.get("emit_interval_ms", 200.0),
            emit_on_change=d.get("emit_on_change", True),
            receive_drone=d.get("receive_drone", True),
            receive_gcs=d.get("receive_gcs", True),
        )


@dataclass
class DevToolsConfig:
    """Root dev tools configuration."""
    enabled: bool = False
    battery_simulation: BatterySimConfig = field(default_factory=BatterySimConfig)
    gui: GuiConfig = field(default_factory=GuiConfig)
    observability_plane: ObservabilityPlaneConfig = field(default_factory=ObservabilityPlaneConfig)
    
    # Data bus settings
    bus_history_size: int = 1000  # Samples to retain
    bus_log_enabled: bool = False
    bus_log_path: Optional[str] = None
    
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "DevToolsConfig":
        return cls(
            enabled=d.get("enabled", False),
            battery_simulation=BatterySimConfig.from_dict(d.get("battery_simulation", {})),
            gui=GuiConfig.from_dict(d.get("gui", {})),
            observability_plane=ObservabilityPlaneConfig.from_dict(d.get("observability_plane", {})),
            bus_history_size=d.get("bus_history_size", 1000),
            bus_log_enabled=d.get("bus_log_enabled", False),
            bus_log_path=d.get("bus_log_path"),
        )


def load_devtools_config() -> DevToolsConfig:
    """
    Load dev tools configuration from settings.json.
    
    Returns:
        DevToolsConfig with enabled=False if section missing or error
    """
    try:
        if not SETTINGS_PATH.exists():
            logger.debug(f"settings.json not found at {SETTINGS_PATH}")
            return DevToolsConfig(enabled=False)
        
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        dev_tools_section = data.get("dev_tools", {})
        
        if not dev_tools_section:
            logger.debug("No dev_tools section in settings.json")
            return DevToolsConfig(enabled=False)
        
        config = DevToolsConfig.from_dict(dev_tools_section)
        logger.info(f"Loaded dev_tools config: enabled={config.enabled}, "
                   f"battery_sim={config.battery_simulation.enabled}, "
                   f"gui={config.gui.enabled}")
        return config
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in settings.json: {e}")
        return DevToolsConfig(enabled=False)
    except Exception as e:
        logger.error(f"Failed to load dev_tools config: {e}")
        return DevToolsConfig(enabled=False)


def save_devtools_config(config: DevToolsConfig) -> bool:
    """
    Save dev tools configuration back to settings.json.
    
    Preserves all other settings in the file.
    
    Returns:
        True if saved successfully, False otherwise
    """
    try:
        # Load existing settings
        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
        
        # Update dev_tools section
        data["dev_tools"] = {
            "enabled": config.enabled,
            "battery_simulation": {
                "enabled": config.battery_simulation.enabled,
                "default_mode": config.battery_simulation.default_mode,
                "start_mv": config.battery_simulation.start_mv,
                "min_mv": config.battery_simulation.min_mv,
                "max_mv": config.battery_simulation.max_mv,
                "slow_drain_mv_per_sec": config.battery_simulation.slow_drain_mv_per_sec,
                "fast_drain_mv_per_sec": config.battery_simulation.fast_drain_mv_per_sec,
                "throttle_drain_factor": config.battery_simulation.throttle_drain_factor,
                "step_drop_mv": config.battery_simulation.step_drop_mv,
                "recovery_mv_per_sec": config.battery_simulation.recovery_mv_per_sec,
            },
            "gui": {
                "enabled": config.gui.enabled,
                "refresh_hz": config.gui.refresh_hz,
                "window_width": config.gui.window_width,
                "window_height": config.gui.window_height,
                "timeline_points": config.gui.timeline_points,
                "graph_update_hz": config.gui.graph_update_hz,
            },
            "observability_plane": {
                "enabled": config.observability_plane.enabled,
                "node_id": config.observability_plane.node_id,
                "drone_port": config.observability_plane.drone_port,
                "gcs_port": config.observability_plane.gcs_port,
                "listen_host": config.observability_plane.listen_host,
                "emit_interval_ms": config.observability_plane.emit_interval_ms,
                "emit_on_change": config.observability_plane.emit_on_change,
                "receive_drone": config.observability_plane.receive_drone,
                "receive_gcs": config.observability_plane.receive_gcs,
            },
            "bus_history_size": config.bus_history_size,
            "bus_log_enabled": config.bus_log_enabled,
            "bus_log_path": config.bus_log_path,
        }
        
        # Write back
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        
        logger.info("Saved dev_tools configuration")
        return True
        
    except Exception as e:
        logger.error(f"Failed to save dev_tools config: {e}")
        return False
