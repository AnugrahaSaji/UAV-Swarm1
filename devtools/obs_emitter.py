"""
Observability Plane Emitter

Fire-and-forget UDP snapshot transmitter.

CRITICAL PROPERTIES:
- WRITE-ONLY (never reads from network)
- Non-blocking (fire and forget)
- Zero backpressure (drops if buffer full)
- Fails silently (no exceptions to callers)
- Thread-safe emit()

This module is used by the scheduler/policy to emit snapshots
whenever state changes. It does NOT wait for acknowledgments.
"""

import socket
import threading
import time
import logging
from typing import Optional, Tuple

from .obs_schema import (
    ObsSnapshot,
    NodeType,
    BatterySnapshot,
    TelemetrySnapshot,
    PolicySnapshot,
    ProxySnapshot,
    create_snapshot,
    MAX_SNAPSHOT_BYTES,
)

logger = logging.getLogger("devtools.obs_emitter")


class ObsEmitter:
    """
    Fire-and-forget UDP snapshot emitter.
    
    Transmits observability snapshots to a local UDP port.
    Designed for SSH port forwarding to remote analysis tools.
    
    Usage:
        emitter = ObsEmitter(
            node=NodeType.DRONE,
            node_id="drone-01",
            target_port=59001,
        )
        emitter.start()
        
        # Emit snapshots as state changes
        emitter.emit_snapshot(
            battery=battery_snap,
            policy=policy_snap,
        )
        
        # On shutdown
        emitter.stop()
    
    Thread Safety:
        emit_snapshot() is thread-safe and can be called from any thread.
    """
    
    def __init__(
        self,
        node: NodeType,
        node_id: str = "",
        target_host: str = "127.0.0.1",
        target_port: int = 59001,
        enabled: bool = True,
    ):
        """
        Initialize emitter.
        
        Args:
            node: NodeType (DRONE or GCS)
            node_id: Optional unique identifier for this node
            target_host: Target IP address (should be localhost for SSH forwarding)
            target_port: Target UDP port
            enabled: Whether to actually transmit (False = silent no-op)
        """
        self._node = node
        self._node_id = node_id or socket.gethostname()[:32]
        self._target = (target_host, target_port)
        self._enabled = enabled
        
        self._socket: Optional[socket.socket] = None
        self._lock = threading.Lock()
        self._seq = 0
        self._started = False
        
        # Stats (for debugging)
        self._stats_lock = threading.Lock()
        self._emitted_count = 0
        self._dropped_count = 0
        self._last_emit_time: Optional[float] = None
        
    def start(self) -> None:
        """
        Start emitter.
        
        Creates UDP socket with non-blocking mode.
        Safe to call multiple times.
        """
        with self._lock:
            if self._started or not self._enabled:
                return
                
            try:
                # Create non-blocking UDP socket
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._socket.setblocking(False)
                
                # Set socket options for fire-and-forget
                # Reduce send buffer to minimize stale data
                try:
                    self._socket.setsockopt(
                        socket.SOL_SOCKET,
                        socket.SO_SNDBUF,
                        16 * 1024,  # 16KB send buffer
                    )
                except OSError:
                    pass  # Not all platforms support this
                
                self._started = True
                logger.info(
                    f"OBS emitter started: {self._node.value}@{self._node_id} "
                    f"-> {self._target[0]}:{self._target[1]}"
                )
                
            except OSError as e:
                logger.warning(f"OBS emitter failed to start: {e}")
                self._socket = None
    
    def stop(self) -> None:
        """
        Stop emitter and release socket.
        
        Safe to call multiple times.
        """
        with self._lock:
            if not self._started:
                return
                
            if self._socket:
                try:
                    self._socket.close()
                except OSError:
                    pass
                self._socket = None
            
            self._started = False
            logger.info(
                f"OBS emitter stopped: emitted={self._emitted_count}, "
                f"dropped={self._dropped_count}"
            )
    
    def emit_snapshot(
        self,
        battery: Optional[BatterySnapshot] = None,
        telemetry: Optional[TelemetrySnapshot] = None,
        policy: Optional[PolicySnapshot] = None,
        proxy: Optional[ProxySnapshot] = None,
    ) -> bool:
        """
        Emit a snapshot with current state.
        
        This is a fire-and-forget operation:
        - Non-blocking
        - No acknowledgment
        - Silent failure
        - No exceptions raised
        
        Args:
            battery: Battery state snapshot
            telemetry: Telemetry state snapshot
            policy: Policy/scheduler state snapshot
            proxy: Data plane proxy state snapshot
            
        Returns:
            True if snapshot was emitted, False if dropped or disabled.
        """
        if not self._enabled:
            return False
        
        with self._lock:
            if not self._started or not self._socket:
                return False
            
            # Increment sequence number
            self._seq = (self._seq + 1) & 0xFFFFFFFF
            
            try:
                # Create snapshot
                snapshot = create_snapshot(
                    node=self._node,
                    node_id=self._node_id,
                    seq=self._seq,
                    battery=battery,
                    telemetry=telemetry,
                    policy=policy,
                    proxy=proxy,
                )
                
                # Serialize to bytes
                data = snapshot.to_bytes()
                
                # Check size
                if len(data) > MAX_SNAPSHOT_BYTES:
                    logger.warning(
                        f"Snapshot too large: {len(data)} > {MAX_SNAPSHOT_BYTES}"
                    )
                    with self._stats_lock:
                        self._dropped_count += 1
                    return False
                
                # Fire and forget
                self._socket.sendto(data, self._target)
                
                with self._stats_lock:
                    self._emitted_count += 1
                    self._last_emit_time = time.monotonic()
                
                return True
                
            except BlockingIOError:
                # Socket buffer full - drop silently
                with self._stats_lock:
                    self._dropped_count += 1
                return False
                
            except OSError as e:
                # Network error - drop silently
                logger.debug(f"OBS emit error: {e}")
                with self._stats_lock:
                    self._dropped_count += 1
                return False
    
    def emit_raw(self, snapshot: ObsSnapshot) -> bool:
        """
        Emit a pre-constructed snapshot.
        
        Lower-level API for cases where the caller has already
        constructed the full snapshot.
        
        Args:
            snapshot: Pre-constructed snapshot object
            
        Returns:
            True if emitted, False if dropped or disabled.
        """
        if not self._enabled:
            return False
        
        with self._lock:
            if not self._started or not self._socket:
                return False
            
            try:
                data = snapshot.to_bytes()
                
                if len(data) > MAX_SNAPSHOT_BYTES:
                    with self._stats_lock:
                        self._dropped_count += 1
                    return False
                
                self._socket.sendto(data, self._target)
                
                with self._stats_lock:
                    self._emitted_count += 1
                    self._last_emit_time = time.monotonic()
                
                return True
                
            except (BlockingIOError, OSError):
                with self._stats_lock:
                    self._dropped_count += 1
                return False
    
    def get_stats(self) -> dict:
        """
        Get emitter statistics.
        
        Returns:
            dict with emitted_count, dropped_count, last_emit_time
        """
        with self._stats_lock:
            return {
                "emitted_count": self._emitted_count,
                "dropped_count": self._dropped_count,
                "last_emit_time": self._last_emit_time,
            }
    
    @property
    def is_active(self) -> bool:
        """Check if emitter is started and enabled."""
        return self._enabled and self._started
    
    @property
    def target(self) -> Tuple[str, int]:
        """Get target host and port."""
        return self._target


class NullEmitter:
    """
    No-op emitter for when OBS plane is disabled.
    
    Drop-in replacement that does nothing.
    Used to avoid if-checks throughout the codebase.
    """
    
    def start(self) -> None:
        pass
    
    def stop(self) -> None:
        pass
    
    def emit_snapshot(self, **kwargs) -> bool:
        return False
    
    def emit_raw(self, snapshot) -> bool:
        return False
    
    def get_stats(self) -> dict:
        return {"emitted_count": 0, "dropped_count": 0, "last_emit_time": None}
    
    @property
    def is_active(self) -> bool:
        return False
    
    @property
    def target(self) -> Tuple[str, int]:
        return ("127.0.0.1", 0)
