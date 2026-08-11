"""
Observability Plane Receiver

UDP snapshot receiver that feeds the DataBus.

CRITICAL PROPERTIES:
- READ-ONLY from network (no transmissions)
- Background thread (non-blocking)
- Graceful degradation (malformed packets ignored)
- Feeds DataBus for GUI consumption
- Tracks statistics for loss detection

This module is used by the GUI/analysis side to receive
snapshots from remote drone/GCS nodes.
"""

import socket
import threading
import time
import logging
from typing import Callable, Dict, List, Optional, Set
from dataclasses import dataclass, field

from .obs_schema import (
    ObsSnapshot,
    NodeType,
    MAX_SNAPSHOT_BYTES,
)

logger = logging.getLogger("devtools.obs_receiver")


@dataclass
class NodeStats:
    """Per-node receive statistics."""
    last_seq: int = -1
    received_count: int = 0
    dropped_count: int = 0  # Detected from seq gaps
    last_recv_time: float = 0.0
    last_snapshot: Optional[ObsSnapshot] = None


@dataclass 
class ReceiverStats:
    """Overall receiver statistics."""
    total_received: int = 0
    total_malformed: int = 0
    total_oversize: int = 0
    nodes: Dict[str, NodeStats] = field(default_factory=dict)


# Type alias for snapshot callbacks
SnapshotCallback = Callable[[ObsSnapshot], None]


class ObsReceiver:
    """
    UDP snapshot receiver with background listener thread.
    
    Receives observability snapshots from drone/GCS nodes
    and forwards them to registered callbacks (typically DataBus).
    
    Usage:
        receiver = ObsReceiver(
            listen_port=59001,  # Receive drone snapshots
        )
        
        # Register callback
        receiver.add_callback(lambda snap: bus.update_from_obs(snap))
        
        receiver.start()
        
        # ... later ...
        receiver.stop()
    
    SSH Port Forwarding Example:
        # On laptop, forward local port to remote drone
        ssh -L 59001:localhost:59001 user@drone
        
        # Receiver listens on localhost:59001
        # Gets snapshots from drone via SSH tunnel
    """
    
    def __init__(
        self,
        listen_host: str = "127.0.0.1",
        listen_port: int = 59001,
        buffer_size: int = MAX_SNAPSHOT_BYTES + 1024,
    ):
        """
        Initialize receiver.
        
        Args:
            listen_host: IP to listen on (should be localhost for security)
            listen_port: UDP port to listen on
            buffer_size: Socket receive buffer size
        """
        self._listen_host = listen_host
        self._listen_port = listen_port
        self._buffer_size = buffer_size
        
        self._socket: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        
        self._callbacks: List[SnapshotCallback] = []
        self._callbacks_lock = threading.Lock()
        
        self._stats = ReceiverStats()
        self._stats_lock = threading.Lock()
    
    def add_callback(self, callback: SnapshotCallback) -> None:
        """
        Register a callback for received snapshots.
        
        Callbacks are invoked from the receiver thread.
        They should be fast and non-blocking.
        
        Args:
            callback: Function to call with each received snapshot
        """
        with self._callbacks_lock:
            if callback not in self._callbacks:
                self._callbacks.append(callback)
    
    def remove_callback(self, callback: SnapshotCallback) -> None:
        """Remove a previously registered callback."""
        with self._callbacks_lock:
            if callback in self._callbacks:
                self._callbacks.remove(callback)
    
    def start(self) -> bool:
        """
        Start receiver.
        
        Creates UDP socket and starts background listener thread.
        
        Returns:
            True if started successfully, False on error.
        """
        if self._running:
            return True
        
        try:
            # Create UDP socket
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            # Allow address reuse
            self._socket.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_REUSEADDR,
                1,
            )
            
            # Bind to listen address
            self._socket.bind((self._listen_host, self._listen_port))
            
            # Set receive timeout for clean shutdown
            self._socket.settimeout(0.5)
            
            # Start listener thread
            self._running = True
            self._thread = threading.Thread(
                target=self._listen_loop,
                name=f"obs-receiver-{self._listen_port}",
                daemon=True,
            )
            self._thread.start()
            
            logger.info(
                f"OBS receiver started on "
                f"{self._listen_host}:{self._listen_port}"
            )
            return True
            
        except OSError as e:
            logger.error(f"OBS receiver failed to start: {e}")
            if self._socket:
                try:
                    self._socket.close()
                except OSError:
                    pass
                self._socket = None
            return False
    
    def stop(self) -> None:
        """
        Stop receiver.
        
        Stops listener thread and closes socket.
        Safe to call multiple times.
        """
        if not self._running:
            return
        
        self._running = False
        
        # Wait for thread to exit
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        
        # Close socket
        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None
        
        logger.info(
            f"OBS receiver stopped: "
            f"received={self._stats.total_received}, "
            f"malformed={self._stats.total_malformed}"
        )
    
    def _listen_loop(self) -> None:
        """Background thread that receives snapshots."""
        while self._running:
            try:
                # Receive datagram
                data, addr = self._socket.recvfrom(self._buffer_size)
                
                # Check size
                if len(data) > MAX_SNAPSHOT_BYTES:
                    with self._stats_lock:
                        self._stats.total_oversize += 1
                    continue
                
                # Parse snapshot
                snapshot = ObsSnapshot.from_bytes(data)
                
                if snapshot is None:
                    with self._stats_lock:
                        self._stats.total_malformed += 1
                    continue
                
                # Update stats
                self._update_stats(snapshot)
                
                # Invoke callbacks
                self._invoke_callbacks(snapshot)
                
            except socket.timeout:
                # Normal timeout for shutdown check
                continue
                
            except OSError as e:
                if self._running:
                    logger.debug(f"OBS receiver error: {e}")
                break
    
    def _update_stats(self, snapshot: ObsSnapshot) -> None:
        """Update receive statistics for a snapshot."""
        now = time.monotonic()
        node_key = f"{snapshot.node}:{snapshot.node_id}"
        
        with self._stats_lock:
            self._stats.total_received += 1
            
            # Get or create node stats
            if node_key not in self._stats.nodes:
                self._stats.nodes[node_key] = NodeStats()
            
            node_stats = self._stats.nodes[node_key]
            
            # Detect sequence gaps (packet loss)
            if node_stats.last_seq >= 0:
                expected_seq = (node_stats.last_seq + 1) & 0xFFFFFFFF
                if snapshot.seq != expected_seq:
                    # Calculate gap (handle wraparound)
                    if snapshot.seq > node_stats.last_seq:
                        gap = snapshot.seq - node_stats.last_seq - 1
                    else:
                        # Wraparound
                        gap = (0xFFFFFFFF - node_stats.last_seq) + snapshot.seq
                    node_stats.dropped_count += gap
            
            # Update node stats
            node_stats.last_seq = snapshot.seq
            node_stats.received_count += 1
            node_stats.last_recv_time = now
            node_stats.last_snapshot = snapshot
    
    def _invoke_callbacks(self, snapshot: ObsSnapshot) -> None:
        """Invoke registered callbacks for a snapshot."""
        with self._callbacks_lock:
            callbacks = list(self._callbacks)
        
        for callback in callbacks:
            try:
                callback(snapshot)
            except Exception as e:
                logger.warning(f"OBS callback error: {e}")
    
    def get_stats(self) -> ReceiverStats:
        """
        Get receiver statistics.
        
        Returns:
            ReceiverStats with total and per-node statistics.
        """
        with self._stats_lock:
            # Return a copy to avoid race conditions
            return ReceiverStats(
                total_received=self._stats.total_received,
                total_malformed=self._stats.total_malformed,
                total_oversize=self._stats.total_oversize,
                nodes={k: NodeStats(
                    last_seq=v.last_seq,
                    received_count=v.received_count,
                    dropped_count=v.dropped_count,
                    last_recv_time=v.last_recv_time,
                    last_snapshot=v.last_snapshot,
                ) for k, v in self._stats.nodes.items()},
            )
    
    def get_known_nodes(self) -> Set[str]:
        """Get set of node keys that have sent snapshots."""
        with self._stats_lock:
            return set(self._stats.nodes.keys())
    
    def get_last_snapshot(self, node_key: str) -> Optional[ObsSnapshot]:
        """Get last received snapshot from a specific node."""
        with self._stats_lock:
            if node_key in self._stats.nodes:
                return self._stats.nodes[node_key].last_snapshot
            return None
    
    @property
    def is_running(self) -> bool:
        """Check if receiver is running."""
        return self._running
    
    @property
    def listen_address(self) -> tuple:
        """Get listen host and port."""
        return (self._listen_host, self._listen_port)


class MultiReceiver:
    """
    Convenience class to receive from multiple ports.
    
    Useful for dashboard that monitors both drone and GCS.
    
    Usage:
        multi = MultiReceiver({
            "drone": 59001,
            "gcs": 59002,
        })
        multi.add_callback(lambda snap: print(snap))
        multi.start()
    """
    
    def __init__(
        self,
        ports: Dict[str, int],
        listen_host: str = "127.0.0.1",
    ):
        """
        Initialize multi-receiver.
        
        Args:
            ports: Dict mapping channel names to port numbers
            listen_host: IP to listen on
        """
        self._receivers: Dict[str, ObsReceiver] = {}
        
        for name, port in ports.items():
            self._receivers[name] = ObsReceiver(
                listen_host=listen_host,
                listen_port=port,
            )
    
    def add_callback(self, callback: SnapshotCallback) -> None:
        """Add callback to all receivers."""
        for receiver in self._receivers.values():
            receiver.add_callback(callback)
    
    def remove_callback(self, callback: SnapshotCallback) -> None:
        """Remove callback from all receivers."""
        for receiver in self._receivers.values():
            receiver.remove_callback(callback)
    
    def start(self) -> Dict[str, bool]:
        """Start all receivers. Returns dict of name -> success."""
        return {name: recv.start() for name, recv in self._receivers.items()}
    
    def stop(self) -> None:
        """Stop all receivers."""
        for receiver in self._receivers.values():
            receiver.stop()
    
    def get_receiver(self, name: str) -> Optional[ObsReceiver]:
        """Get a specific receiver by name."""
        return self._receivers.get(name)
    
    @property
    def is_running(self) -> bool:
        """Check if any receiver is running."""
        return any(r.is_running for r in self._receivers.values())
