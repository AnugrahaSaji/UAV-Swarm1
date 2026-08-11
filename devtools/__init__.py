"""
Development-Only Tooling for PQC Drone-GCS Secure Proxy

THIS MODULE IS FOR LAB / LAPTOP TESTING ONLY.
When disabled, production behavior remains IDENTICAL to the baseline codebase.

Architecture:
    devtools/
    ├── __init__.py           # Enable/disable logic, safe imports
    ├── config.py             # Dev tools configuration loader
    ├── data_bus.py           # Thread-safe observability bus (single source of truth)
    ├── battery_sim.py        # Battery provider abstraction + simulation modes
    ├── battery_bridge.py     # Non-invasive injection bridge for LocalMonitor
    ├── dashboard.py          # Tkinter GUI dashboard
    ├── obs_schema.py         # Observability Plane schema (OBS snapshot format)
    ├── obs_emitter.py        # Fire-and-forget UDP emitter (drone/GCS side)
    ├── obs_receiver.py       # UDP receiver + DataBus feeder (dashboard side)
    ├── integration.py        # Scheduler integration layer
    └── launcher.py           # Entry point for dev mode

Observability Plane (OBS_PLANE):
    A FOURTH, temporary, DEV-ONLY plane that:
    - Exists ONLY when explicitly enabled
    - Runs alongside existing planes without interfering
    - Works over SSH for laptop-based analysis
    - Supports BOTH Drone (Raspberry Pi) and GCS (Laptop)
    - Feeds a live Tkinter dashboard and offline analysis tools
    
    This plane is observational only — it MUST NOT influence decisions.

Safety Guarantees:
    1. All features controlled via settings.json["dev_tools"]["enabled"]
    2. When disabled, NO dev code paths execute
    3. Production scheduler/policy logic is NEVER modified
    4. GUI cannot affect policy decisions
    5. Battery simulation only active when explicitly enabled
    6. OBS plane is SNAPSHOT-ONLY (no commands, no RPCs, no state mutation)

Usage:
    # In settings.json:
    {
        "dev_tools": {
            "enabled": true,
            "battery_simulation": {"enabled": true, "default_mode": "stable"},
            "gui": {"enabled": true, "refresh_hz": 5},
            "observability_plane": {"enabled": true, "drone_port": 59001, "gcs_port": 59002}
        }
    }
"""

import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING

# Lazy imports to avoid loading heavy modules when disabled
if TYPE_CHECKING:
    from devtools.config import DevToolsConfig
    from devtools.data_bus import DataBus
    from devtools.battery_sim import BatteryProvider
    from devtools.dashboard import DevDashboard
    from devtools.obs_emitter import ObsEmitter
    from devtools.obs_receiver import ObsReceiver, MultiReceiver

__version__ = "1.1.0"
__all__ = [
    "is_enabled",
    "get_config",
    "get_data_bus",
    "get_battery_provider",
    "start_dashboard",
    "stop_all",
    "create_obs_emitter",
    "create_obs_receiver",
    "create_multi_receiver",
]

# Module-level singletons (lazy init)
_config: Optional["DevToolsConfig"] = None
_data_bus: Optional["DataBus"] = None
_battery_provider: Optional["BatteryProvider"] = None
_dashboard: Optional["DevDashboard"] = None
_obs_receiver: Optional["MultiReceiver"] = None
_initialized: bool = False

logger = logging.getLogger("devtools")


def _load_config() -> "DevToolsConfig":
    """Load dev tools configuration from settings.json."""
    global _config
    if _config is None:
        from devtools.config import load_devtools_config
        _config = load_devtools_config()
    return _config


def is_enabled() -> bool:
    """
    Check if dev tools are enabled.
    
    Returns False if:
    - dev_tools.enabled is False or missing in settings.json
    - Any import error occurs (graceful degradation)
    """
    try:
        config = _load_config()
        return config.enabled
    except Exception as e:
        logger.debug(f"Dev tools disabled due to: {e}")
        return False


def get_config() -> "DevToolsConfig":
    """
    Get dev tools configuration.
    
    Raises:
        RuntimeError: If dev tools are disabled
    """
    if not is_enabled():
        raise RuntimeError("Dev tools are disabled. Enable in settings.json")
    return _load_config()


def get_data_bus() -> "DataBus":
    """
    Get the shared data bus singleton.
    
    The data bus is the SINGLE SOURCE OF TRUTH for all dev tool consumers.
    It is updated by production components and read by the GUI.
    
    Raises:
        RuntimeError: If dev tools are disabled
    """
    global _data_bus
    if not is_enabled():
        raise RuntimeError("Dev tools are disabled")
    
    if _data_bus is None:
        from devtools.data_bus import DataBus
        _data_bus = DataBus()
        logger.info("DataBus initialized")
    
    return _data_bus


def get_battery_provider() -> "BatteryProvider":
    """
    Get the battery provider based on configuration.
    
    Returns:
        SimulatedBatteryProvider if battery_simulation.enabled
        RealBatteryProvider otherwise (pass-through to MAVLink)
    
    Raises:
        RuntimeError: If dev tools are disabled
    """
    global _battery_provider
    if not is_enabled():
        raise RuntimeError("Dev tools are disabled")
    
    if _battery_provider is None:
        from devtools.battery_sim import create_battery_provider
        config = _load_config()
        _battery_provider = create_battery_provider(config)
        logger.info(f"BatteryProvider initialized: {type(_battery_provider).__name__}")
    
    return _battery_provider


def start_dashboard() -> Optional["DevDashboard"]:
    """
    Start the Tkinter dashboard if enabled.
    
    The dashboard runs in a separate thread and is non-blocking.
    
    Returns:
        DevDashboard instance if started, None if GUI disabled
    
    Raises:
        RuntimeError: If dev tools are disabled
    """
    global _dashboard
    if not is_enabled():
        raise RuntimeError("Dev tools are disabled")
    
    config = _load_config()
    if not config.gui.enabled:
        logger.info("GUI disabled in configuration")
        return None
    
    if _dashboard is None:
        from devtools.dashboard import DevDashboard
        data_bus = get_data_bus()
        battery_provider = get_battery_provider() if config.battery_simulation.enabled else None
        _dashboard = DevDashboard(data_bus, battery_provider, config.gui)
        _dashboard.start()
        logger.info("Dashboard started")
    
    return _dashboard


def stop_all() -> None:
    """
    Stop all dev tools components gracefully.
    
    Safe to call even if dev tools are disabled.
    """
    global _dashboard, _data_bus, _battery_provider, _obs_receiver, _initialized
    
    logger.info("Stopping dev tools...")
    
    if _obs_receiver is not None:
        try:
            _obs_receiver.stop()
        except Exception as e:
            logger.warning(f"OBS receiver stop error: {e}")
        _obs_receiver = None
    
    if _dashboard is not None:
        try:
            _dashboard.stop()
        except Exception as e:
            logger.warning(f"Dashboard stop error: {e}")
        _dashboard = None
    
    if _data_bus is not None:
        try:
            _data_bus.stop()
        except Exception as e:
            logger.warning(f"DataBus stop error: {e}")
        _data_bus = None
    
    _battery_provider = None
    _initialized = False
    logger.info("Dev tools stopped")


def initialize() -> bool:
    """
    Initialize all enabled dev tools components.
    
    Returns:
        True if dev tools are enabled and initialized
        False if disabled or initialization failed
    """
    global _initialized
    
    if not is_enabled():
        logger.info("Dev tools are disabled in configuration")
        return False
    
    if _initialized:
        return True
    
    try:
        config = _load_config()
        logger.info(f"Initializing dev tools v{__version__}")
        
        # Always initialize data bus when enabled
        get_data_bus()
        
        # Initialize battery provider if simulation enabled
        if config.battery_simulation.enabled:
            get_battery_provider()
        
        # Start dashboard if enabled
        if config.gui.enabled:
            start_dashboard()
        
        # Start OBS receivers if enabled (for dashboard side)
        if config.observability_plane.enabled:
            _start_obs_receivers(config)
        
        _initialized = True
        logger.info("Dev tools initialization complete")
        return True
        
    except Exception as e:
        logger.error(f"Dev tools initialization failed: {e}")
        return False


# =========================================================================
# Observability Plane Functions
# =========================================================================

def create_obs_emitter(
    node_type: str = "drone",
    node_id: str = ""
) -> "ObsEmitter":
    """
    Create an OBS emitter for sending snapshots.
    
    This is used by drone/GCS schedulers to emit state snapshots.
    The emitter sends UDP datagrams to localhost, intended for SSH forwarding.
    
    Args:
        node_type: "drone" or "gcs"
        node_id: Unique node identifier (defaults to hostname)
    
    Returns:
        ObsEmitter instance (already started)
    
    Raises:
        RuntimeError: If dev tools are disabled or OBS plane not enabled
    """
    if not is_enabled():
        raise RuntimeError("Dev tools are disabled")
    
    config = _load_config()
    if not config.observability_plane.enabled:
        raise RuntimeError("Observability plane is disabled in configuration")
    
    from devtools.obs_emitter import ObsEmitter
    from devtools.obs_schema import NodeType
    
    if node_type.lower() == "gcs":
        nt = NodeType.GCS
        port = config.observability_plane.gcs_port
    else:
        nt = NodeType.DRONE
        port = config.observability_plane.drone_port
    
    emitter = ObsEmitter(
        node=nt,
        node_id=node_id or config.observability_plane.node_id,
        target_host="127.0.0.1",
        target_port=port,
        enabled=True,
    )
    emitter.start()
    
    logger.info(f"Created OBS emitter: {node_type} on port {port}")
    return emitter


def create_obs_receiver(
    port: int,
    listen_host: str = "127.0.0.1"
) -> "ObsReceiver":
    """
    Create an OBS receiver for receiving snapshots.
    
    This is used by the dashboard to receive remote snapshots.
    
    Args:
        port: UDP port to listen on
        listen_host: IP to listen on (should be localhost)
    
    Returns:
        ObsReceiver instance (not yet started)
    
    Raises:
        RuntimeError: If dev tools are disabled
    """
    if not is_enabled():
        raise RuntimeError("Dev tools are disabled")
    
    from devtools.obs_receiver import ObsReceiver
    
    receiver = ObsReceiver(
        listen_host=listen_host,
        listen_port=port,
    )
    
    logger.info(f"Created OBS receiver on {listen_host}:{port}")
    return receiver


def create_multi_receiver() -> "MultiReceiver":
    """
    Create a multi-port OBS receiver for both drone and GCS.
    
    Uses ports from configuration.
    
    Returns:
        MultiReceiver instance (not yet started)
    
    Raises:
        RuntimeError: If dev tools or OBS plane are disabled
    """
    if not is_enabled():
        raise RuntimeError("Dev tools are disabled")
    
    config = _load_config()
    if not config.observability_plane.enabled:
        raise RuntimeError("Observability plane is disabled")
    
    from devtools.obs_receiver import MultiReceiver
    
    ports = {}
    if config.observability_plane.receive_drone:
        ports["drone"] = config.observability_plane.drone_port
    if config.observability_plane.receive_gcs:
        ports["gcs"] = config.observability_plane.gcs_port
    
    receiver = MultiReceiver(
        ports=ports,
        listen_host=config.observability_plane.listen_host,
    )
    
    logger.info(f"Created multi-receiver for ports: {ports}")
    return receiver


def _start_obs_receivers(config: "DevToolsConfig") -> None:
    """
    Start OBS receivers and connect them to the data bus.
    
    Internal function called during initialization.
    """
    global _obs_receiver
    
    if _obs_receiver is not None:
        return
    
    from devtools.obs_receiver import MultiReceiver
    
    ports = {}
    if config.observability_plane.receive_drone:
        ports["drone"] = config.observability_plane.drone_port
    if config.observability_plane.receive_gcs:
        ports["gcs"] = config.observability_plane.gcs_port
    
    if not ports:
        logger.info("No OBS receivers configured")
        return
    
    _obs_receiver = MultiReceiver(
        ports=ports,
        listen_host=config.observability_plane.listen_host,
    )
    
    # Connect to data bus
    data_bus = get_data_bus()
    _obs_receiver.add_callback(lambda snap: data_bus.update_from_obs_snapshot(snap))
    
    # Start receivers
    results = _obs_receiver.start()
    for name, success in results.items():
        if success:
            logger.info(f"OBS receiver '{name}' started on port {ports[name]}")
        else:
            logger.warning(f"OBS receiver '{name}' failed to start")
