"""
Dev Tools Launcher

Entry point for running the scheduler with dev tools enabled.
This script demonstrates how to integrate dev tools without modifying
the core scheduler code.

Usage:
    # Run drone role with dev tools
    python -m devtools.launcher --role drone
    
    # Run GCS role with dev tools
    python -m devtools.launcher --role gcs
    
    # Run GUI only (receives OBS plane data)
    python -m devtools.launcher --gui-only
    
    # Run standalone demo mode
    python -m devtools.launcher --standalone

The launcher:
1. Checks if dev tools are enabled in settings.json
2. Initializes dev tools components if enabled
3. Launches the scheduler with data bus integration
4. Provides clean shutdown handling

SSH Usage (Lab Setup):
    # On laptop, SSH into drone with X11 and port forwarding:
    ssh -X -L 59001:localhost:59001 dev@100.101.93.23
    
    # On drone (via SSH):
    python -m devtools.launcher --role drone
    
    # On laptop (local terminal):
    python -m devtools.launcher --role gcs
    
    # On laptop (separate terminal, GUI only):
    python -m devtools.launcher --gui-only
"""

import argparse
import atexit
import logging
import signal
import sys
import time
import threading
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S"
)
logger = logging.getLogger("devtools.launcher")


def log(msg: str):
    """Simple timestamped log."""
    print(f"[devtools.launcher] {msg}", flush=True)


def main():
    """Main launcher entry point."""
    parser = argparse.ArgumentParser(
        description="PQC Drone/GCS Scheduler with Dev Tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run as drone with dev tools:
  python -m devtools.launcher --role drone
  
  # Run as GCS with dev tools:
  python -m devtools.launcher --role gcs
  
  # Run GUI only (no scheduler, receives OBS data):
  python -m devtools.launcher --gui-only
  
  # Run OBS receiver only (no GUI, prints to console):
  python -m devtools.launcher --obs-receive
  
SSH Lab Setup:
  # On laptop, SSH into drone:
  ssh -X -L 59001:localhost:59001 dev@100.101.93.23
  
  # Then run drone role on Pi, GCS role locally.
"""
    )
    
    # Role selection
    parser.add_argument(
        "--role",
        choices=["drone", "gcs"],
        default=None,
        help="Run as drone or GCS scheduler role"
    )
    
    # Mode selection
    parser.add_argument(
        "--gui-only",
        action="store_true",
        help="Run GUI only (no scheduler, receives OBS plane data)"
    )
    parser.add_argument(
        "--obs-receive",
        action="store_true",
        help="Run OBS receiver only (no GUI, prints snapshots)"
    )
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Run dev tools standalone with demo data"
    )
    
    # Feature toggles
    parser.add_argument(
        "--no-gui",
        action="store_true",
        help="Disable GUI even if enabled in config"
    )
    parser.add_argument(
        "--no-battery-sim",
        action="store_true",
        help="Disable battery simulation even if enabled in config"
    )
    parser.add_argument(
        "--no-obs",
        action="store_true",
        help="Disable OBS plane even if enabled in config"
    )
    parser.add_argument(
        "--data-bus-only",
        action="store_true",
        help="Enable data bus without GUI or battery simulation"
    )
    
    # Pass remaining args to scheduler
    args, scheduler_args = parser.parse_known_args()
    
    log("=" * 60)
    log("PQC Drone/GCS Dev Tools Launcher")
    log("=" * 60)
    
    # Check dev tools availability
    try:
        import devtools
        from devtools.config import load_devtools_config, DevToolsConfig
        
        config = load_devtools_config()
        
        if not config.enabled:
            log("Dev tools DISABLED in settings.json")
            log("Set dev_tools.enabled = true to enable")
            
            # If running a role without dev tools, fallback to standard scheduler
            if args.role:
                log(f"Falling back to standard {args.role} scheduler...")
                return run_standard_scheduler(args.role, scheduler_args)
            else:
                log("Enable dev_tools in settings.json or use --role to run scheduler")
                return 1
        
        log(f"Dev tools ENABLED")
        log(f"  Battery simulation: {config.battery_simulation.enabled}")
        log(f"  GUI dashboard: {config.gui.enabled}")
        log(f"  OBS plane: {config.observability_plane.enabled}")
        
    except ImportError as e:
        log(f"Dev tools import error: {e}")
        if args.role:
            log(f"Falling back to standard {args.role} scheduler...")
            return run_standard_scheduler(args.role, scheduler_args)
        return 1
    
    # Apply command-line overrides
    if args.no_gui:
        config.gui.enabled = False
        log("  GUI disabled by --no-gui")
    
    if args.no_battery_sim:
        config.battery_simulation.enabled = False
        log("  Battery simulation disabled by --no-battery-sim")
    
    if args.no_obs:
        config.observability_plane.enabled = False
        log("  OBS plane disabled by --no-obs")
    
    if args.data_bus_only:
        config.gui.enabled = False
        config.battery_simulation.enabled = False
        log("  Data bus only mode")
    
    # Dispatch based on mode
    if args.gui_only:
        return run_gui_only(config)
    elif args.obs_receive:
        return run_obs_receiver_only(config)
    elif args.standalone:
        return run_standalone(config)
    elif args.role:
        return run_with_role(args.role, config, scheduler_args)
    else:
        log("No mode specified. Use --role, --gui-only, --obs-receive, or --standalone")
        parser.print_help()
        return 1


def run_standard_scheduler(role: str, args: list) -> int:
    """Run the standard scheduler without dev tools."""
    log(f"Running standard {role} scheduler...")
    
    try:
        if role == "drone":
            from sscheduler import sdrone
            sys.argv = ["sdrone.py"] + args
            return sdrone.main()
        else:
            from sscheduler import sgcs
            sys.argv = ["sgcs.py"] + args
            return sgcs.main()
    except Exception as e:
        log(f"Scheduler error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def run_with_role(role: str, config, scheduler_args: list) -> int:
    """Run scheduler with dev tools integration for a specific role."""
    log(f"\nRunning as {role.upper()} with dev tools...")
    
    # Initialize components
    data_bus = None
    battery_provider = None
    dashboard = None
    obs_emitter = None
    node_type_enum = None
    
    try:
        # Initialize data bus (always)
        from devtools.data_bus import DataBus
        data_bus = DataBus(
            history_size=config.bus_history_size,
            log_path=config.bus_log_path
        )
        log("  DataBus initialized")
        
        # Initialize battery provider if enabled (typically drone only)
        if config.battery_simulation.enabled and role == "drone":
            from devtools.battery_sim import SimulatedBatteryProvider
            battery_provider = SimulatedBatteryProvider(
                config=config.battery_simulation,
                data_bus=data_bus
            )
            battery_provider.start()
            log(f"  Battery simulation started (mode={config.battery_simulation.default_mode})")
        
        # Initialize OBS emitter if enabled
        if config.observability_plane.enabled:
            from devtools.obs_emitter import ObsEmitter
            from devtools.obs_schema import NodeType
            
            node_type_enum = NodeType.DRONE if role == "drone" else NodeType.GCS
            port = config.observability_plane.drone_port if role == "drone" else config.observability_plane.gcs_port
            
            obs_emitter = ObsEmitter(
                node=node_type_enum,
                node_id=config.observability_plane.node_id,
                target_host="127.0.0.1",
                target_port=port,
                enabled=True,
            )
            obs_emitter.start()
            log(f"  OBS emitter started ({node_type_enum.value} on port {port})")
        
        # Initialize dashboard if enabled
        if config.gui.enabled:
            from devtools.dashboard import DevDashboard
            dashboard = DevDashboard(
                data_bus=data_bus,
                battery_provider=battery_provider,
                config=config.gui
            )
            dashboard.start()
            log(f"  Dashboard started (refresh={config.gui.refresh_hz} Hz)")
        
    except Exception as e:
        log(f"Dev tools initialization failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Register cleanup
    cleanup_done = [False]
    
    def cleanup():
        if cleanup_done[0]:
            return
        cleanup_done[0] = True
        log("\nCleaning up dev tools...")
        if obs_emitter:
            try:
                obs_emitter.stop()
            except Exception:
                pass
        if dashboard:
            try:
                dashboard.stop()
            except Exception:
                pass
        if battery_provider:
            try:
                battery_provider.stop()
            except Exception:
                pass
        if data_bus:
            try:
                data_bus.stop()
            except Exception:
                pass
        log("Cleanup complete")
    
    atexit.register(cleanup)
    
    # Handle SIGINT gracefully
    def sigint_handler(sig, frame):
        log("\nInterrupted")
        cleanup()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, sigint_handler)
    
    log("\n" + "=" * 60)
    log(f"{role.upper()} SCHEDULER MODE - Full integration")
    log("=" * 60)
    
    # Create integration for scheduler
    from devtools.integration import DevToolsIntegration
    
    # Manually create integration with our components
    integration = DevToolsIntegration(
        data_bus=data_bus,
        battery_provider=battery_provider,
        dashboard=dashboard,
        config=config,
        obs_emitter=obs_emitter,
        node_type=node_type_enum
    )
    integration.start()
    
    # Store integration globally so scheduler can access it
    import devtools
    devtools._integration = integration
    
    # Run the appropriate scheduler
    try:
        if role == "drone":
            from sscheduler import sdrone
            sys.argv = ["sdrone.py"] + scheduler_args
            return sdrone.main()
        else:
            from sscheduler import sgcs
            sys.argv = ["sgcs.py"] + scheduler_args
            return sgcs.main()
    except Exception as e:
        log(f"Scheduler error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        cleanup()


def run_gui_only(config) -> int:
    """Run GUI with OBS receivers only (no scheduler)."""
    log("\n" + "=" * 60)
    log("GUI-ONLY MODE")
    log("Receives data from OBS plane, displays on dashboard")
    log("Press Ctrl+C to exit")
    log("=" * 60)
    
    data_bus = None
    dashboard = None
    obs_receiver = None
    
    try:
        # Initialize data bus
        from devtools.data_bus import DataBus
        data_bus = DataBus(history_size=config.bus_history_size)
        log("  DataBus initialized")
        
        # Initialize OBS receivers
        if config.observability_plane.enabled:
            from devtools.obs_receiver import MultiReceiver
            
            ports = {}
            if config.observability_plane.receive_drone:
                ports["drone"] = config.observability_plane.drone_port
            if config.observability_plane.receive_gcs:
                ports["gcs"] = config.observability_plane.gcs_port
            
            if ports:
                obs_receiver = MultiReceiver(
                    ports=ports,
                    listen_host=config.observability_plane.listen_host,
                )
                
                # Connect to data bus
                obs_receiver.add_callback(lambda snap: data_bus.update_from_obs_snapshot(snap))
                
                results = obs_receiver.start()
                for name, success in results.items():
                    if success:
                        log(f"  OBS receiver '{name}' listening on port {ports[name]}")
                    else:
                        log(f"  OBS receiver '{name}' FAILED to start")
        
        # Initialize dashboard
        if config.gui.enabled:
            from devtools.dashboard import DevDashboard
            dashboard = DevDashboard(
                data_bus=data_bus,
                battery_provider=None,
                config=config.gui
            )
            dashboard.start()
            log(f"  Dashboard started (refresh={config.gui.refresh_hz} Hz)")
        else:
            log("  GUI disabled in config, enable with gui.enabled=true")
        
        log("\nWaiting for OBS snapshots...")
        log("(Ensure SSH port forwarding is active if receiving from remote nodes)")
        
        # Main loop
        while True:
            time.sleep(1.0)
            
    except KeyboardInterrupt:
        log("\nInterrupted")
    except Exception as e:
        log(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if obs_receiver:
            obs_receiver.stop()
        if dashboard:
            dashboard.stop()
        if data_bus:
            data_bus.stop()
    
    return 0


def run_obs_receiver_only(config) -> int:
    """Run OBS receiver only (no GUI, prints to console)."""
    log("\n" + "=" * 60)
    log("OBS RECEIVER MODE")
    log("Receives OBS snapshots and prints to console")
    log("Press Ctrl+C to exit")
    log("=" * 60)
    
    if not config.observability_plane.enabled:
        log("OBS plane disabled in config!")
        return 1
    
    from devtools.obs_receiver import MultiReceiver
    from devtools.obs_schema import ObsSnapshot
    
    received_count = [0]
    
    def on_snapshot(snap: ObsSnapshot):
        received_count[0] += 1
        print(f"\n[#{received_count[0]}] {snap.node}:{snap.node_id} seq={snap.seq}")
        print(f"  Battery: {snap.battery.voltage_mv}mV ({snap.battery.percentage}%)")
        print(f"  Policy: {snap.policy.current_suite} [{snap.policy.current_action}]")
        print(f"  Telemetry: {snap.telemetry.rx_pps:.1f} pps, gap_p95={snap.telemetry.gap_p95_ms:.1f}ms")
        print(f"  Proxy: {snap.proxy.encrypted_pps:.1f} enc_pps, status={snap.proxy.handshake_status}")
    
    ports = {}
    if config.observability_plane.receive_drone:
        ports["drone"] = config.observability_plane.drone_port
    if config.observability_plane.receive_gcs:
        ports["gcs"] = config.observability_plane.gcs_port
    
    obs_receiver = MultiReceiver(
        ports=ports,
        listen_host=config.observability_plane.listen_host,
    )
    obs_receiver.add_callback(on_snapshot)
    
    results = obs_receiver.start()
    for name, success in results.items():
        if success:
            log(f"  Listening for {name} on port {ports[name]}")
        else:
            log(f"  FAILED to start {name} receiver")
    
    try:
        log("\nWaiting for OBS snapshots...")
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        log(f"\nReceived {received_count[0]} snapshots total")
    finally:
        obs_receiver.stop()
    
    return 0


def run_standalone(config) -> int:
    """Run dev tools standalone with demo data."""
    log("\n" + "=" * 60)
    log("STANDALONE MODE - Demo data")
    log("Press Ctrl+C to exit")
    log("=" * 60)
    
    data_bus = None
    battery_provider = None
    dashboard = None
    
    try:
        # Initialize data bus
        from devtools.data_bus import DataBus
        data_bus = DataBus(history_size=config.bus_history_size)
        log("  DataBus initialized")
        
        # Initialize battery provider if enabled
        if config.battery_simulation.enabled:
            from devtools.battery_sim import SimulatedBatteryProvider
            battery_provider = SimulatedBatteryProvider(
                config=config.battery_simulation,
                data_bus=data_bus
            )
            battery_provider.start()
            log(f"  Battery simulation started")
        
        # Initialize dashboard if enabled
        if config.gui.enabled:
            from devtools.dashboard import DevDashboard
            dashboard = DevDashboard(
                data_bus=data_bus,
                battery_provider=battery_provider,
                config=config.gui
            )
            dashboard.start()
            log(f"  Dashboard started")
        
        # Start demo data generation
        demo_thread = threading.Thread(
            target=lambda: run_demo_data(data_bus, battery_provider),
            daemon=True
        )
        demo_thread.start()
        
        log("\nGenerating demo data...")
        
        while True:
            time.sleep(1.0)
            
    except KeyboardInterrupt:
        log("\nInterrupted")
    finally:
        if dashboard:
            dashboard.stop()
        if battery_provider:
            battery_provider.stop()
        if data_bus:
            data_bus.stop()
    
    return 0


def run_demo_data(data_bus, battery_provider):
    """Generate deterministic baseline demo data for standalone mode."""
    epoch = 0
    suite_names = [
        "cs-mlkem512-aesgcm-mldsa44",
        "cs-mlkem768-aesgcm-mldsa65",
        "cs-mlkem1024-aesgcm-mldsa87",
    ]
    current_suite = suite_names[0]
    bytes_enc = 1_000_000
    bytes_dec = 1_000_000
    
    while True:
        try:
            # Update telemetry with fixed deterministic baseline values
            data_bus.update_telemetry(
                rx_pps=10.0,
                gap_p95_ms=100.0,
                blackout_count=0,
                jitter_ms=10.0,
                telemetry_age_ms=100.0,
                sample_count=50,
            )
            
            # Update policy with fixed deterministic state
            action = "HOLD"
            data_bus.update_policy(
                current_suite=current_suite,
                current_action=action,
                target_suite=None,
                reasons=["demo_mode"],
                confidence=1.0,
                cooldown_remaining_ms=0.0,
                local_epoch=epoch,
                armed=False,
            )
            
            # Update proxy with fixed deterministic metrics
            bytes_enc += 1000
            bytes_dec += 1000
            data_bus.update_proxy(
                encrypted_pps=100.0,
                plaintext_pps=100.0,
                replay_drops=0,
                handshake_status="ok",
                bytes_encrypted=bytes_enc,
                bytes_decrypted=bytes_dec,
            )
            
            time.sleep(0.2)  # 5 Hz
            
        except Exception as e:
            logger.warning(f"Demo data error: {e}")
            time.sleep(1.0)



if __name__ == "__main__":
    sys.exit(main())
