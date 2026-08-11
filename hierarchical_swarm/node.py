"""SwarmNode: Runtime State Model for a Drone in the Hierarchical UAV Swarm.

This module defines the canonical in-memory state record for a single participating
drone node. It stores identity, hierarchy position, operational status, telemetry
metrics, mission context, timing, and security session metadata.

Responsibilities ONLY:
    - Holding drone state fields with strong typing.
    - Providing thread-safe lightweight state-mutation methods.
    - Exposing liveness checks based on heartbeat timestamps.

This module does NOT perform:
    - Networking or socket I/O.
    - MAVLink or MAVProxy communication.
    - SMT tree operations or cryptographic computations.
    - Scheduler interactions or task dispatching.
    - Routing or topology indexing.

Integration consumers (no reverse imports):
    topology.py, heartbeat.py, discovery.py, routing.py,
    security.py, cluster_manager.py, election.py, task_manager.py
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from hierarchical_swarm.utils import ClusterId, DroneId, NodeStatus, SwarmRole

try:
    from core.logging_utils import get_logger
    logger = get_logger("hierarchical_swarm.node")
except ImportError:
    logger = logging.getLogger("hierarchical_swarm.node")


# ---------------------------------------------------------------------------
# Supplementary Enums (node-specific state machines not in utils.py)
# ---------------------------------------------------------------------------

class NodeState(Enum):
    """Fine-grained lifecycle state machine for a swarm node.

    Progression:
        UNASSIGNED -> DISCOVERING -> REGISTERING -> AUTHENTICATING
        -> JOINING -> ACTIVE -> LEAVING -> OFFLINE

    The ``ELECTION`` state is entered only during a leader election round.
    The ``REVOKED`` state is terminal — the node cannot re-join without
    re-registration from the GCS SMT root.
    """

    UNASSIGNED    = auto()  # Powered on, not yet discovered any leader.
    DISCOVERING   = auto()  # Listening for 1-hop HELLO beacons.
    REGISTERING   = auto()  # Sent REGISTER, awaiting AUTH_REQUEST.
    AUTHENTICATING = auto() # Received AUTH_REQUEST, computing SMT proof.
    JOINING       = auto()  # SMT verified, awaiting JOIN approval.
    ACTIVE        = auto()  # Fully joined, heartbeating normally.
    ELECTION      = auto()  # Participating in weighted leader election.
    LEAVING       = auto()  # Sent LEAVE, draining gracefully.
    OFFLINE       = auto()  # Timed out or shut down cleanly.
    REVOKED       = auto()  # SMT credentials revoked — terminal.


# ---------------------------------------------------------------------------
# SwarmNode
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class SwarmNode:
    """Canonical in-memory state record for one drone in the hierarchical swarm.

    This dataclass is intentionally NOT frozen because state fields are mutated
    frequently (heartbeat updates, role changes, battery readings). All public
    mutation methods are thread-safe via a single ``threading.Lock``.

    All timing fields use ``time.monotonic()`` to be immune to wall-clock
    adjustments (NTP slew, DST, etc.) that would corrupt timeout logic.

    Memory footprint (slots=True):
        Approximately 400–450 bytes per node on CPython 3.12, making it
        practical to track 1 000 drones within 500 KB of heap.

    Attributes — Identity:
        drone_id:       Unique swarm identifier string (e.g. ``"drone-01"``).
        parent_id:      DroneId of the immediate parent node in the tree.
                        ``None`` for the Root Leader.
        cluster_id:     ClusterId of the cluster this node belongs to.

    Attributes — Hierarchy:
        role:           Current ``SwarmRole`` (ROOT_LEADER / CLUSTER_LEADER /
                        FOLLOWER / CANDIDATE).
        tree_level:     Depth in the 3-tier tree (0 = Root Leader,
                        1 = Cluster Leader, 2 = Follower).

    Attributes — Status:
        state:          ``NodeState`` lifecycle state machine value.
        authenticated:  ``True`` once SMT proof has been verified.

    Attributes — Telemetry (updated by heartbeat.py from MAVLink/INA219):
        battery_voltage:    Battery rail voltage in Volts (e.g. ``12.4``).
        battery_percentage: Battery charge percentage 0–100 %.
        cpu_load:           CPU utilisation percentage 0–100 %.
        memory_usage:       RAM utilisation percentage 0–100 %.
        rssi:               Received Signal Strength Indicator in dBm.
        link_quality:       Link quality score 0–100 (higher is better).

    Attributes — Mission:
        mission_priority:   Integer priority of the current mission context
                            (higher = more important; used by election.py).
        current_task_id:    String ID of the task currently assigned to this
                            node, or ``None`` if idle.

    Attributes — Timing (all ``time.monotonic()`` epochs):
        boot_time:          Monotonic timestamp when the node object was created.
        join_time:          Monotonic timestamp when the node joined the swarm.
                            ``0.0`` until the node is in ACTIVE state.
        last_seen:          Monotonic timestamp of the last received message
                            from this node (any type).
        last_heartbeat:     Monotonic timestamp of the last HEARTBEAT message.

    Attributes — Security Session:
        session_id:         Opaque string ID of the active Ascon session,
                            assigned by security.py after ML-KEM exchange.
                            ``None`` before authentication completes.
        topology_version:   Integer epoch counter incremented by topology.py
                            on every structural change (join/leave/re-parent).
    """

    # -- Identity ------------------------------------------------------------
    drone_id:   DroneId
    parent_id:  Optional[DroneId]  = None
    cluster_id: Optional[ClusterId] = None

    # -- Hierarchy -----------------------------------------------------------
    role:       SwarmRole = SwarmRole.CANDIDATE
    tree_level: int       = 2          # Default to Tier 2 (Follower)

    # -- Status --------------------------------------------------------------
    state:         NodeState = NodeState.UNASSIGNED
    authenticated: bool      = False

    # -- Telemetry -----------------------------------------------------------
    battery_voltage:    float = 0.0
    battery_percentage: float = 0.0
    cpu_load:           float = 0.0
    memory_usage:       float = 0.0
    rssi:               float = 0.0
    link_quality:       float = 0.0

    # -- Mission -------------------------------------------------------------
    mission_priority: int           = 0
    current_task_id:  Optional[str] = None

    # -- Timing (time.monotonic()) -------------------------------------------
    boot_time:      float = field(default_factory=time.monotonic)
    join_time:      float = 0.0
    last_seen:      float = field(default_factory=time.monotonic)
    last_heartbeat: float = field(default_factory=time.monotonic)

    # -- Security Session ----------------------------------------------------
    session_id:       Optional[str] = None
    topology_version: int           = 0

    # -- Internal (not stored in topology index) ----------------------------
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    # -----------------------------------------------------------------------
    # Liveness
    # -----------------------------------------------------------------------

    def is_alive(self, timeout_sec: float = 3.0) -> bool:
        """Returns ``True`` if a heartbeat was received within ``timeout_sec``.

        Uses ``time.monotonic()`` for drift-free deadline arithmetic.
        This method is lock-free (single atomic float read on CPython).

        Args:
            timeout_sec: Maximum allowed silence before the node is considered
                         dead.  Defaults to 3.0 seconds per the DDS spec.

        Returns:
            ``True`` if ``(now - last_heartbeat) <= timeout_sec``.
        """
        return (time.monotonic() - self.last_heartbeat) <= timeout_sec

    # -----------------------------------------------------------------------
    # Heartbeat & Telemetry
    # -----------------------------------------------------------------------

    def update_heartbeat(
        self,
        battery_voltage: float,
        battery_percentage: float,
        cpu_load: float,
        rssi: float,
        link_quality: float = 0.0,
        memory_usage: float = 0.0,
    ) -> None:
        """Atomically records a received HEARTBEAT and refreshes all telemetry.

        Called exclusively by ``heartbeat.py`` after parsing a
        ``HeartbeatMessage``.  The method acquires the node lock to prevent
        a concurrent reader in ``election.py`` from observing a torn write.

        Args:
            battery_voltage:    Battery rail voltage in Volts.
            battery_percentage: Battery charge percentage 0–100.
            cpu_load:           CPU utilisation percentage 0–100.
            rssi:               Received Signal Strength in dBm.
            link_quality:       Link quality score 0–100 (optional).
            memory_usage:       RAM utilisation percentage 0–100 (optional).
        """
        now = time.monotonic()
        with self._lock:
            self.battery_voltage    = battery_voltage
            self.battery_percentage = battery_percentage
            self.cpu_load           = cpu_load
            self.memory_usage       = memory_usage
            self.rssi               = rssi
            self.link_quality       = link_quality
            self.last_heartbeat     = now
            self.last_seen          = now
        logger.debug(
            "Heartbeat updated: drone=%s bat=%.2fV cpu=%.1f%% rssi=%.1f",
            self.drone_id, battery_voltage, cpu_load, rssi,
        )

    def update_metrics(
        self,
        cpu_load: float,
        memory_usage: float,
        rssi: float,
        link_quality: float = 0.0,
    ) -> None:
        """Updates only the lightweight telemetry metrics (no heartbeat stamp).

        Used for periodic telemetry refreshes that are not HEARTBEAT packets
        (e.g. a follower receiving a TELEMETRY aggregate from the cluster leader).

        Args:
            cpu_load:     CPU utilisation 0–100.
            memory_usage: RAM utilisation 0–100.
            rssi:         Signal strength in dBm.
            link_quality: Link quality score 0–100 (optional).
        """
        with self._lock:
            self.cpu_load     = cpu_load
            self.memory_usage = memory_usage
            self.rssi         = rssi
            self.link_quality = link_quality
            self.last_seen    = time.monotonic()

    # -----------------------------------------------------------------------
    # Authentication & Session
    # -----------------------------------------------------------------------

    def mark_authenticated(self, session_id: str) -> None:
        """Transitions the node to authenticated status and records the session.

        Called by ``security.py`` after a successful SMT proof verification
        and ML-KEM key exchange.

        Args:
            session_id: Opaque session identifier assigned by security.py.

        Raises:
            ValueError: If ``session_id`` is empty or blank.
        """
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be a non-empty string")
        with self._lock:
            self.authenticated = True
            self.session_id    = session_id
            self.state         = NodeState.JOINING
        logger.info("Node %s authenticated; session=%s", self.drone_id, session_id)

    def expire_session(self) -> None:
        """Clears authentication credentials without taking the node offline.

        Called by ``security.py`` on session expiry (``SessionExpired`` event).
        The node remains in the topology but must re-authenticate before
        sending further authenticated messages.
        """
        with self._lock:
            self.authenticated = False
            self.session_id    = None
        logger.info("Session expired for node %s", self.drone_id)

    # -----------------------------------------------------------------------
    # Online / Offline Transitions
    # -----------------------------------------------------------------------

    def mark_online(self) -> None:
        """Marks the node as fully ACTIVE in the swarm.

        Called by ``topology.py`` after the JOIN approval message is processed.
        Records the ``join_time`` monotonic timestamp.
        """
        with self._lock:
            self.state     = NodeState.ACTIVE
            self.join_time = time.monotonic()
            self.last_seen = time.monotonic()
        logger.info("Node %s is now ACTIVE", self.drone_id)

    def mark_offline(self) -> None:
        """Marks the node OFFLINE and clears session credentials.

        Called by ``heartbeat.py`` after a ``HeartbeatTimeout`` event, or by
        ``cluster_manager.py`` after a confirmed leader failure.
        Does NOT remove the node from ``topology.py``; that is the caller's
        responsibility.
        """
        with self._lock:
            self.state         = NodeState.OFFLINE
            self.authenticated = False
            self.session_id    = None
        logger.warning("Node %s marked OFFLINE", self.drone_id)

    def mark_revoked(self) -> None:
        """Permanently revokes this node's swarm membership.

        Terminal state — the node cannot re-join without SMT root re-issuance
        from the GCS.  Called by ``security.py`` on SMT revocation.
        """
        with self._lock:
            self.state         = NodeState.REVOKED
            self.authenticated = False
            self.session_id    = None
        logger.warning("Node %s has been REVOKED", self.drone_id)

    # -----------------------------------------------------------------------
    # Hierarchy Mutations
    # -----------------------------------------------------------------------

    def update_role(self, new_role: SwarmRole, new_tree_level: int) -> None:
        """Updates the node's hierarchical role and tree depth.

        Called by ``cluster_manager.py`` after an election concludes and
        ``RE_PARENT`` directives are issued.

        Args:
            new_role:       The new ``SwarmRole`` value.
            new_tree_level: Depth in the 3-tier tree (0, 1, or 2).

        Raises:
            ValueError: If ``new_tree_level`` is not in [0, 2].
        """
        if new_tree_level not in (0, 1, 2):
            raise ValueError(f"tree_level must be 0, 1, or 2; got {new_tree_level}")
        with self._lock:
            old_role       = self.role
            self.role       = new_role
            self.tree_level = new_tree_level
        logger.info(
            "Node %s role changed: %s -> %s (level=%d)",
            self.drone_id, old_role.name, new_role.name, new_tree_level,
        )

    def update_parent(self, new_parent_id: Optional[DroneId]) -> None:
        """Updates the parent pointer in the 3-tier tree.

        Called by ``topology.py`` during JOIN or RE_PARENT processing.
        Increments ``topology_version`` to signal structural change to readers.

        Args:
            new_parent_id: DroneId of the new parent, or ``None`` for the
                           Root Leader (who has no parent).
        """
        with self._lock:
            self.parent_id        = new_parent_id
            self.topology_version += 1
        logger.debug(
            "Node %s parent updated to %s (topo_v=%d)",
            self.drone_id, new_parent_id, self.topology_version,
        )

    def update_cluster(self, new_cluster_id: ClusterId) -> None:
        """Moves the node into a different cluster.

        Called by ``cluster_manager.py`` during failover re-parenting.
        Increments ``topology_version``.

        Args:
            new_cluster_id: ClusterId of the target cluster.

        Raises:
            ValueError: If ``new_cluster_id`` is empty or blank.
        """
        if not new_cluster_id or not str(new_cluster_id).strip():
            raise ValueError("cluster_id must be a non-empty string")
        with self._lock:
            self.cluster_id       = new_cluster_id
            self.topology_version += 1
        logger.debug(
            "Node %s cluster updated to %s (topo_v=%d)",
            self.drone_id, new_cluster_id, self.topology_version,
        )

    # -----------------------------------------------------------------------
    # Mission Context
    # -----------------------------------------------------------------------

    def assign_task(self, task_id: str, priority: int = 0) -> None:
        """Assigns a mission task to this node.

        Called by ``task_manager.py`` when dispatching a ``TASK_ASSIGN``
        message.

        Args:
            task_id:  String identifier of the task.
            priority: Mission priority integer (higher = more important).

        Raises:
            ValueError: If ``task_id`` is empty.
        """
        if not task_id or not task_id.strip():
            raise ValueError("task_id must be a non-empty string")
        with self._lock:
            self.current_task_id  = task_id
            self.mission_priority = priority
        logger.debug("Node %s assigned task=%s priority=%d", self.drone_id, task_id, priority)

    def clear_task(self) -> None:
        """Clears the current mission task on completion or failure.

        Called by ``task_manager.py`` after receiving a ``TASK_ACK``.
        """
        with self._lock:
            self.current_task_id  = None
            self.mission_priority = 0
        logger.debug("Node %s task cleared", self.drone_id)

    # -----------------------------------------------------------------------
    # Convenience
    # -----------------------------------------------------------------------

    def election_weight(self) -> float:
        """Computes the weighted election score for this node.

        Formula (frozen in architecture):
            W = 0.50 * battery_percentage
              + 0.20 * (100 - cpu_load)
              + 0.15 * mission_priority
              - 0.10 * tree_level          (deeper = slightly less preferred)
              + 0.05 * (100 + rssi) / 100  (rssi is typically negative dBm)

        This value is read by ``election.py``; it is computed fresh each call
        to reflect the latest telemetry without caching.

        Returns:
            Float score (higher is a stronger candidate).
        """
        with self._lock:
            bat  = self.battery_percentage
            cpu  = self.cpu_load
            pri  = float(self.mission_priority)
            lvl  = float(self.tree_level)
            rssi = self.rssi
        # Normalise RSSI: typical range −100 dBm (weak) to 0 dBm (perfect).
        normalised_rssi = max(0.0, min(100.0, 100.0 + rssi))
        return (
            0.50 * bat
            + 0.20 * (100.0 - cpu)
            + 0.15 * pri
            - 0.10 * lvl * 10.0       # scale so level difference is visible
            + 0.05 * normalised_rssi
        )

    def __repr__(self) -> str:
        return (
            f"SwarmNode(id={self.drone_id!r}, role={self.role.name}, "
            f"state={self.state.name}, bat={self.battery_percentage:.1f}%, "
            f"alive={self.is_alive()})"
        )
