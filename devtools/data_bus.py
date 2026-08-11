"""
Thread-Safe Data Observability Bus

SINGLE SOURCE OF TRUTH for all dev tool consumers.

The DataBus is:
- Written to by: scheduler, policy executor, telemetry receiver, battery provider, proxy stats
- Read from by: GUI (read-only perspective)
- Thread-safe: All operations use locks
- Decoupled: GUI never imports scheduler/policy modules directly

This bus does NOT modify any production behavior.
It only observes and records data for visualization.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Deque, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from devtools.obs_schema import ObsSnapshot

logger = logging.getLogger("devtools.data_bus")


class StressLevel(str, Enum):
    """Qualitative stress level for battery/system."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class BatteryState:
    """Battery state snapshot."""
    timestamp_mono: float = 0.0
    voltage_mv: int = 0
    percentage: int = 0
    rate_mv_per_sec: float = 0.0
    stress_level: StressLevel = StressLevel.LOW
    source: str = "unknown"  # "mavlink" or "simulated"
    simulation_mode: str = "stable"
    is_simulated: bool = False


@dataclass
class TelemetryState:
    """Telemetry link state snapshot."""
    timestamp_mono: float = 0.0
    rx_pps: float = 0.0
    gap_p95_ms: float = 0.0
    blackout_count: int = 0
    jitter_ms: float = 0.0
    telemetry_age_ms: float = -1.0
    sample_count: int = 0


@dataclass
class PolicyState:
    """Policy/scheduler state snapshot."""
    timestamp_mono: float = 0.0
    current_suite: str = ""
    current_action: str = "HOLD"
    target_suite: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    confidence: float = 0.0
    cooldown_remaining_ms: float = 0.0
    local_epoch: int = 0
    armed: bool = False


@dataclass
class ProxyState:
    """Data plane proxy state snapshot."""
    timestamp_mono: float = 0.0
    encrypted_pps: float = 0.0
    plaintext_pps: float = 0.0
    replay_drops: int = 0
    handshake_status: str = "unknown"  # "pending", "ok", "failed"
    bytes_encrypted: int = 0
    bytes_decrypted: int = 0


@dataclass
class TimelineEvent:
    """Timeline event for visualization."""
    timestamp_mono: float
    timestamp_iso: str
    event_type: str  # "suite_switch", "policy_action", "battery_event", "link_event"
    label: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SystemSnapshot:
    """Complete system state snapshot for GUI."""
    timestamp_mono: float
    timestamp_iso: str
    battery: BatteryState
    telemetry: TelemetryState
    policy: PolicyState
    proxy: ProxyState


class DataBus:
    """
    Thread-safe data observability bus.
    
    Central hub for all system state used by dev tools.
    """
    
    def __init__(self, history_size: int = 1000, log_path: Optional[str] = None):
        self._lock = threading.RLock()
        self._history_size = history_size
        
        # Current state
        self._battery = BatteryState()
        self._telemetry = TelemetryState()
        self._policy = PolicyState()
        self._proxy = ProxyState()
        
        # History for timelines
        self._battery_history: Deque[BatteryState] = deque(maxlen=history_size)
        self._telemetry_history: Deque[TelemetryState] = deque(maxlen=history_size)
        self._policy_history: Deque[PolicyState] = deque(maxlen=history_size)
        self._events: Deque[TimelineEvent] = deque(maxlen=500)
        
        # Subscribers for real-time updates
        self._subscribers: Dict[str, List[Callable[[str, Any], None]]] = {}
        
        # Optional logging
        self._log_path = Path(log_path) if log_path else None
        self._log_file = None
        
        # Stats
        self._update_count = 0
        self._start_time = time.monotonic()
        
        logger.info(f"DataBus initialized (history_size={history_size})")
    
    def _notify(self, channel: str, data: Any) -> None:
        """Notify subscribers on a channel (non-blocking)."""
        callbacks = self._subscribers.get(channel, [])
        for cb in callbacks:
            try:
                cb(channel, data)
            except Exception as e:
                logger.warning(f"Subscriber callback error: {e}")
    
    def _log_update(self, channel: str, data: Any) -> None:
        """Log update to file if enabled."""
        if self._log_path is None:
            return
        try:
            if self._log_file is None:
                self._log_path.parent.mkdir(parents=True, exist_ok=True)
                self._log_file = open(self._log_path, "a", encoding="utf-8")
            
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "mono": time.monotonic(),
                "channel": channel,
                "data": asdict(data) if hasattr(data, "__dataclass_fields__") else data
            }
            self._log_file.write(json.dumps(entry) + "\n")
            self._log_file.flush()
        except Exception as e:
            logger.warning(f"Log write error: {e}")
    
    # =========================================================================
    # WRITE METHODS (called by production components)
    # =========================================================================
    
    def update_battery(
        self,
        voltage_mv: int,
        percentage: int = 0,
        rate_mv_per_sec: float = 0.0,
        stress_level: StressLevel = StressLevel.LOW,
        source: str = "unknown",
        simulation_mode: str = "stable",
        is_simulated: bool = False
    ) -> None:
        """Update battery state (called by battery provider)."""
        with self._lock:
            now = time.monotonic()
            self._battery = BatteryState(
                timestamp_mono=now,
                voltage_mv=voltage_mv,
                percentage=percentage,
                rate_mv_per_sec=rate_mv_per_sec,
                stress_level=stress_level,
                source=source,
                simulation_mode=simulation_mode,
                is_simulated=is_simulated,
            )
            self._battery_history.append(self._battery)
            self._update_count += 1
        
        self._notify("battery", self._battery)
        self._log_update("battery", self._battery)
    
    def update_telemetry(
        self,
        rx_pps: float = 0.0,
        gap_p95_ms: float = 0.0,
        blackout_count: int = 0,
        jitter_ms: float = 0.0,
        telemetry_age_ms: float = -1.0,
        sample_count: int = 0
    ) -> None:
        """Update telemetry state (called by telemetry receiver)."""
        with self._lock:
            now = time.monotonic()
            self._telemetry = TelemetryState(
                timestamp_mono=now,
                rx_pps=rx_pps,
                gap_p95_ms=gap_p95_ms,
                blackout_count=blackout_count,
                jitter_ms=jitter_ms,
                telemetry_age_ms=telemetry_age_ms,
                sample_count=sample_count,
            )
            self._telemetry_history.append(self._telemetry)
            self._update_count += 1
        
        self._notify("telemetry", self._telemetry)
        self._log_update("telemetry", self._telemetry)
    
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
        """Update policy/scheduler state (called by scheduler)."""
        with self._lock:
            now = time.monotonic()
            
            # Detect suite change for timeline
            old_suite = self._policy.current_suite
            if old_suite and old_suite != current_suite:
                self._add_event(
                    "suite_switch",
                    f"{old_suite} → {current_suite}",
                    {"from": old_suite, "to": current_suite, "action": current_action}
                )
            
            # Detect non-HOLD action for timeline
            if current_action != "HOLD":
                self._add_event(
                    "policy_action",
                    f"{current_action}",
                    {"action": current_action, "target": target_suite, "reasons": reasons}
                )
            
            self._policy = PolicyState(
                timestamp_mono=now,
                current_suite=current_suite,
                current_action=current_action,
                target_suite=target_suite,
                reasons=reasons or [],
                confidence=confidence,
                cooldown_remaining_ms=cooldown_remaining_ms,
                local_epoch=local_epoch,
                armed=armed,
            )
            self._policy_history.append(self._policy)
            self._update_count += 1
        
        self._notify("policy", self._policy)
        self._log_update("policy", self._policy)
    
    def update_proxy(
        self,
        encrypted_pps: float = 0.0,
        plaintext_pps: float = 0.0,
        replay_drops: int = 0,
        handshake_status: str = "unknown",
        bytes_encrypted: int = 0,
        bytes_decrypted: int = 0
    ) -> None:
        """Update proxy stats (called by proxy layer)."""
        with self._lock:
            now = time.monotonic()
            self._proxy = ProxyState(
                timestamp_mono=now,
                encrypted_pps=encrypted_pps,
                plaintext_pps=plaintext_pps,
                replay_drops=replay_drops,
                handshake_status=handshake_status,
                bytes_encrypted=bytes_encrypted,
                bytes_decrypted=bytes_decrypted,
            )
            self._update_count += 1
        
        self._notify("proxy", self._proxy)
        self._log_update("proxy", self._proxy)
    
    def add_event(
        self,
        event_type: str,
        label: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a timeline event (external API)."""
        with self._lock:
            self._add_event(event_type, label, details)
    
    def _add_event(
        self,
        event_type: str,
        label: str,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """Add a timeline event (internal, already locked)."""
        now = time.monotonic()
        event = TimelineEvent(
            timestamp_mono=now,
            timestamp_iso=datetime.now(timezone.utc).isoformat(),
            event_type=event_type,
            label=label,
            details=details or {},
        )
        self._events.append(event)
        self._notify("event", event)
        self._log_update("event", event)
    
    # =========================================================================
    # READ METHODS (called by GUI - read-only)
    # =========================================================================
    
    def get_battery(self) -> BatteryState:
        """Get current battery state (thread-safe copy)."""
        with self._lock:
            return BatteryState(**asdict(self._battery))
    
    def get_telemetry(self) -> TelemetryState:
        """Get current telemetry state (thread-safe copy)."""
        with self._lock:
            return TelemetryState(**asdict(self._telemetry))
    
    def get_policy(self) -> PolicyState:
        """Get current policy state (thread-safe copy)."""
        with self._lock:
            return PolicyState(**asdict(self._policy))
    
    def get_proxy(self) -> ProxyState:
        """Get current proxy state (thread-safe copy)."""
        with self._lock:
            return ProxyState(**asdict(self._proxy))
    
    def get_snapshot(self) -> SystemSnapshot:
        """Get complete system snapshot (thread-safe)."""
        with self._lock:
            now = time.monotonic()
            return SystemSnapshot(
                timestamp_mono=now,
                timestamp_iso=datetime.now(timezone.utc).isoformat(),
                battery=BatteryState(**asdict(self._battery)),
                telemetry=TelemetryState(**asdict(self._telemetry)),
                policy=PolicyState(**asdict(self._policy)),
                proxy=ProxyState(**asdict(self._proxy)),
            )
    
    def get_battery_history(self, max_points: int = 300) -> List[BatteryState]:
        """Get battery history for timeline (thread-safe copy)."""
        with self._lock:
            items = list(self._battery_history)
            if len(items) > max_points:
                items = items[-max_points:]
            return items
    
    def get_telemetry_history(self, max_points: int = 300) -> List[TelemetryState]:
        """Get telemetry history for timeline (thread-safe copy)."""
        with self._lock:
            items = list(self._telemetry_history)
            if len(items) > max_points:
                items = items[-max_points:]
            return items
    
    def get_events(self, max_events: int = 100) -> List[TimelineEvent]:
        """Get recent events for timeline (thread-safe copy)."""
        with self._lock:
            items = list(self._events)
            if len(items) > max_events:
                items = items[-max_events:]
            return items
    
    def get_stats(self) -> Dict[str, Any]:
        """Get bus statistics."""
        with self._lock:
            uptime = time.monotonic() - self._start_time
            return {
                "update_count": self._update_count,
                "updates_per_sec": self._update_count / uptime if uptime > 0 else 0,
                "uptime_s": uptime,
                "battery_history_len": len(self._battery_history),
                "telemetry_history_len": len(self._telemetry_history),
                "policy_history_len": len(self._policy_history),
                "events_len": len(self._events),
            }
    
    # =========================================================================
    # SUBSCRIPTION METHODS
    # =========================================================================
    
    def subscribe(self, channel: str, callback: Callable[[str, Any], None]) -> None:
        """
        Subscribe to updates on a channel.
        
        Channels: "battery", "telemetry", "policy", "proxy", "event"
        
        Callback signature: callback(channel: str, data: Any) -> None
        """
        with self._lock:
            if channel not in self._subscribers:
                self._subscribers[channel] = []
            self._subscribers[channel].append(callback)
    
    def unsubscribe(self, channel: str, callback: Callable[[str, Any], None]) -> None:
        """Unsubscribe from a channel."""
        with self._lock:
            if channel in self._subscribers:
                try:
                    self._subscribers[channel].remove(callback)
                except ValueError:
                    pass
    
    # =========================================================================
    # LIFECYCLE
    # =========================================================================
    
    def stop(self) -> None:
        """Stop the data bus and clean up."""
        with self._lock:
            if self._log_file:
                try:
                    self._log_file.close()
                except Exception:
                    pass
                self._log_file = None
            self._subscribers.clear()
        logger.info("DataBus stopped")
    
    def clear_history(self) -> None:
        """Clear all history (for testing)."""
        with self._lock:
            self._battery_history.clear()
            self._telemetry_history.clear()
            self._policy_history.clear()
            self._events.clear()
            self._update_count = 0
    
    # =========================================================================
    # OBSERVABILITY PLANE INTEGRATION
    # =========================================================================
    
    def update_from_obs_snapshot(self, snapshot: "ObsSnapshot", node_key: str = "") -> None:
        """
        Update local state from a remote OBS snapshot.
        
        This is called by ObsReceiver when a snapshot arrives from a remote node.
        The snapshot data is merged into local state with node identification.
        
        Args:
            snapshot: Remote ObsSnapshot object
            node_key: Node identifier (e.g., "drone:drone-01")
        """
        # Import here to avoid circular dependency
        from .obs_schema import ObsSnapshot
        
        if not isinstance(snapshot, ObsSnapshot):
            return
        
        # Build node-prefixed key for identification
        if not node_key:
            node_key = f"{snapshot.node}:{snapshot.node_id}"
        
        with self._lock:
            now = time.monotonic()
            
            # Update battery from snapshot
            if snapshot.battery:
                b = snapshot.battery
                stress = StressLevel.LOW
                try:
                    stress = StressLevel(b.stress_level)
                except ValueError:
                    pass
                
                self._battery = BatteryState(
                    timestamp_mono=now,
                    voltage_mv=b.voltage_mv,
                    percentage=b.percentage,
                    rate_mv_per_sec=b.rate_mv_per_sec,
                    stress_level=stress,
                    source=f"obs:{node_key}",
                    simulation_mode=b.simulation_mode,
                    is_simulated=b.is_simulated,
                )
                self._battery_history.append(self._battery)
            
            # Update telemetry from snapshot
            if snapshot.telemetry:
                t = snapshot.telemetry
                self._telemetry = TelemetryState(
                    timestamp_mono=now,
                    rx_pps=t.rx_pps,
                    gap_p95_ms=t.gap_p95_ms,
                    blackout_count=t.blackout_count,
                    jitter_ms=t.jitter_ms,
                    telemetry_age_ms=t.telemetry_age_ms,
                    sample_count=t.sample_count,
                )
                self._telemetry_history.append(self._telemetry)
            
            # Update policy from snapshot
            if snapshot.policy:
                p = snapshot.policy
                
                # Detect suite change for timeline event
                old_suite = self._policy.current_suite
                if old_suite and old_suite != p.current_suite:
                    self._add_event(
                        "suite_switch",
                        f"{old_suite} → {p.current_suite} ({node_key})",
                        {"from": old_suite, "to": p.current_suite, "node": node_key}
                    )
                
                self._policy = PolicyState(
                    timestamp_mono=now,
                    current_suite=p.current_suite,
                    current_action=p.current_action,
                    target_suite=p.target_suite,
                    reasons=p.reasons or [],
                    confidence=p.confidence,
                    cooldown_remaining_ms=p.cooldown_remaining_ms,
                    local_epoch=p.local_epoch,
                    armed=p.armed,
                )
                self._policy_history.append(self._policy)
            
            # Update proxy from snapshot
            if snapshot.proxy:
                x = snapshot.proxy
                self._proxy = ProxyState(
                    timestamp_mono=now,
                    encrypted_pps=x.encrypted_pps,
                    plaintext_pps=x.plaintext_pps,
                    replay_drops=x.replay_drops,
                    handshake_status=x.handshake_status,
                    bytes_encrypted=x.bytes_encrypted,
                    bytes_decrypted=x.bytes_decrypted,
                )
            
            self._update_count += 1
        
        # Notify subscribers (outside lock)
        self._notify("battery", self._battery)
        self._notify("telemetry", self._telemetry)
        self._notify("policy", self._policy)
        self._notify("proxy", self._proxy)
        self._notify("obs_snapshot", snapshot)
