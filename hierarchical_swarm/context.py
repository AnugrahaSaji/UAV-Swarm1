"""Swarm Context Facade for Hierarchical UAV Swarm Network.

Provides the central integration facade (`SwarmContext`) that encapsulates and wires
together all 8 sub-modules of the `hierarchical_swarm` package:
    1. SwarmNode
    2. SwarmTopology
    3. DiscoveryEngine
    4. SwarmSecurityManager
    5. HeartbeatManager
    6. RoutingManager
    7. TaskManager
    8. ClusterManager

Initialization Order:
    SwarmNode → SwarmTopology → DiscoveryEngine → SwarmSecurityManager →
    HeartbeatManager → RoutingManager → TaskManager → ClusterManager →
    Register Callbacks → Initialize Modules

Shutdown Order (Reverse):
    ClusterManager → TaskManager → RoutingManager → HeartbeatManager →
    SwarmSecurityManager → DiscoveryEngine → SwarmTopology → SwarmNode

Thread Safety:
    Guarded by a single `threading.RLock` (`_lock`).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Callable, Dict, Any, Optional

from hierarchical_swarm.cluster_manager import ClusterManager
from hierarchical_swarm.discovery import DiscoveryConfig, DiscoveryEngine, DiscoveryTransport
from hierarchical_swarm.heartbeat import HeartbeatConfig, HeartbeatManager
from hierarchical_swarm.node import NodeState, SwarmNode
from hierarchical_swarm.routing import RoutingManager
from hierarchical_swarm.security import SwarmSecurityManager
from hierarchical_swarm.task_manager import TaskManager
from hierarchical_swarm.topology import SwarmTopology
from hierarchical_swarm.utils import ClusterId, DroneId, SwarmRole

try:
    from core.logging_utils import get_logger
    _logger = get_logger("hierarchical_swarm.context")
except ImportError:
    _logger = logging.getLogger("hierarchical_swarm.context")


class SwarmContext:
    """Central facade for the hierarchical UAV swarm system.

    Handles initialization, callback wiring, health reporting, and graceful shutdown.

    Args:
        drone_id: Unique string identifier for this drone.
        role: Initial role string ("ROOT_LEADER", "CLUSTER_LEADER", "FOLLOWER", "CANDIDATE").
        cluster_id: Optional cluster assignment ID.
        parent_id: Optional parent drone ID.
        tree_level: Topology level (0=Root, 1=Leader, 2=Follower).
        send_transport: Optional UDP transmission callback `(bytes) -> None`.
        discovery_transport: Optional custom transport for `DiscoveryEngine`.
        battery_fn: Optional callable returning battery voltage/percentage.
        psk: Optional 32-byte swarm pre-shared key.
        mldsa_pubkey: Optional ML-DSA public key bytes.
    """

    def __init__(
        self,
        drone_id: str,
        role: str = "CANDIDATE",
        cluster_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        tree_level: Optional[int] = None,
        send_transport: Optional[Callable[[bytes], None]] = None,
        discovery_transport: Optional[DiscoveryTransport] = None,
        battery_fn: Callable[[], float] = lambda: 100.0,
        psk: Optional[bytes] = None,
        mldsa_pubkey: Optional[bytes] = None,
    ) -> None:
        self._drone_id_str = drone_id
        self._role_enum = SwarmRole[role] if role in SwarmRole.__members__ else SwarmRole.CANDIDATE

        # Determine default tree level from role if not specified
        if tree_level is None:
            if self._role_enum == SwarmRole.ROOT_LEADER:
                tree_level = 0
            elif self._role_enum == SwarmRole.CLUSTER_LEADER:
                tree_level = 1
            else:
                tree_level = 2

        self._cluster_id_str = cluster_id
        self._parent_id_str = parent_id
        self._tree_level = tree_level

        self._send_transport = send_transport
        self._discovery_transport = discovery_transport
        self._battery_fn = battery_fn
        self._psk = psk
        self._mldsa_pubkey = mldsa_pubkey

        self._lock = threading.RLock()
        self._initialized = False

        # Sub-module references
        self._node: Optional[SwarmNode] = None
        self._topology: Optional[SwarmTopology] = None
        self._discovery: Optional[DiscoveryEngine] = None
        self._security: Optional[SwarmSecurityManager] = None
        self._heartbeat: Optional[HeartbeatManager] = None
        self._routing: Optional[RoutingManager] = None
        self._task_manager: Optional[TaskManager] = None
        self._cluster_manager: Optional[ClusterManager] = None

        _logger.info("SwarmContext constructed for drone=%s, role=%s", drone_id, self._role_enum.name)

    # ------------------------------------------------------------------
    # Properties for Sub-module Access
    # ------------------------------------------------------------------

    @property
    def node(self) -> SwarmNode:
        assert self._node is not None, "SwarmContext not initialized"
        return self._node

    @property
    def topology(self) -> SwarmTopology:
        assert self._topology is not None, "SwarmContext not initialized"
        return self._topology

    @property
    def discovery(self) -> DiscoveryEngine:
        assert self._discovery is not None, "SwarmContext not initialized"
        return self._discovery

    @property
    def security(self) -> SwarmSecurityManager:
        assert self._security is not None, "SwarmContext not initialized"
        return self._security

    @property
    def heartbeat(self) -> HeartbeatManager:
        assert self._heartbeat is not None, "SwarmContext not initialized"
        return self._heartbeat

    @property
    def routing(self) -> RoutingManager:
        assert self._routing is not None, "SwarmContext not initialized"
        return self._routing

    @property
    def task_manager(self) -> TaskManager:
        assert self._task_manager is not None, "SwarmContext not initialized"
        return self._task_manager

    @property
    def cluster_manager(self) -> ClusterManager:
        assert self._cluster_manager is not None, "SwarmContext not initialized"
        return self._cluster_manager

    @property
    def is_initialized(self) -> bool:
        with self._lock:
            return self._initialized

    # ------------------------------------------------------------------
    # Initialization Sequence
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Executes strict 10-step module initialization and wiring sequence."""
        with self._lock:
            if self._initialized:
                _logger.warning("SwarmContext already initialized for %s", self._drone_id_str)
                return

            _logger.info("Initializing SwarmContext for drone=%s...", self._drone_id_str)

            # Step 1: Create SwarmNode
            c_id = ClusterId(self._cluster_id_str) if self._cluster_id_str else None
            p_id = DroneId(self._parent_id_str) if self._parent_id_str else None
            self._node = SwarmNode(
                drone_id=DroneId(self._drone_id_str),
                role=self._role_enum,
                tree_level=self._tree_level,
                parent_id=p_id,
                cluster_id=c_id,
            )

            # Step 2: Create SwarmTopology
            self._topology = SwarmTopology()

            # Step 3: Create SwarmSecurityManager
            self._security = SwarmSecurityManager(
                psk=self._psk,
                mldsa_pubkey=self._mldsa_pubkey,
            )

            # Step 4: Create DiscoveryEngine
            disc_cfg = DiscoveryConfig.from_env()
            self._discovery = DiscoveryEngine(
                local_node=self._node,
                topology=self._topology,
                config=disc_cfg,
                transport=self._discovery_transport,
                security=self._security,
                battery_pct_fn=self._battery_fn,
            )

            # Step 5: Create HeartbeatManager
            hb_cfg = HeartbeatConfig.from_env()
            self._heartbeat = HeartbeatManager(
                local_node=self._node,
                topology=self._topology,
                security=self._security,
                config=hb_cfg,
                send_transport=self._send_transport,
                battery_fn=self._battery_fn,
            )

            # Step 6: Create RoutingManager
            self._routing = RoutingManager(
                topology=self._topology,
                local_node_id=DroneId(self._drone_id_str),
            )

            # Step 7: Create TaskManager
            self._task_manager = TaskManager(
                topology=self._topology,
                routing_manager=self._routing,
                local_node_id=DroneId(self._drone_id_str),
                secure_channel=self._security,
            )

            # Step 8: Create ClusterManager
            self._cluster_manager = ClusterManager(
                topology=self._topology,
            )

            # Step 9: Register Callbacks / Event Hooks (Step 9)
            pass

            # Step 10: Initialize / Start Operational Components
            if self._role_enum == SwarmRole.ROOT_LEADER:
                self._node.mark_online()
                self._topology.add_node(self._node)
                self._heartbeat.start()
            elif self._role_enum == SwarmRole.CLUSTER_LEADER:
                if p_id:
                    # Root must exist or node added cleanly
                    try:
                        self._topology.add_node(self._node, cluster_id=self._cluster_id_str)
                    except Exception:
                        pass
                self._discovery.start_beaconing()
                self._heartbeat.start()
            else:  # FOLLOWER / CANDIDATE
                # Followers initiate passive discovery or start heartbeat if already assigned
                if self._node.state == NodeState.ACTIVE:
                    self._heartbeat.start()

            self._initialized = True
            _logger.info("SwarmContext initialization complete for drone=%s", self._drone_id_str)

    # ------------------------------------------------------------------
    # Shutdown Sequence (Reverse Order)
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Executes graceful shutdown in strict reverse module order."""
        with self._lock:
            if not self._initialized:
                return

            _logger.info("Shutting down SwarmContext for drone=%s...", self._drone_id_str)

            # 1. ClusterManager
            if self._cluster_manager:
                if hasattr(self._cluster_manager, "drain_events"):
                    self._cluster_manager.drain_events()
                self._cluster_manager = None

            # 2. TaskManager
            if self._task_manager:
                if hasattr(self._task_manager, "drain_events"):
                    self._task_manager.drain_events()
                self._task_manager = None

            # 3. RoutingManager
            if self._routing:
                if hasattr(self._routing, "drain_events"):
                    self._routing.drain_events()
                if hasattr(self._routing, "clear_cache"):
                    self._routing.clear_cache()
                self._routing = None

            # 4. HeartbeatManager (Cancel timers)
            if self._heartbeat:
                if hasattr(self._heartbeat, "stop"):
                    self._heartbeat.stop()
                if hasattr(self._heartbeat, "drain_events"):
                    self._heartbeat.drain_events()
                self._heartbeat = None

            # 5. SecurityManager (Zero keys)
            if self._security:
                if hasattr(self._security, "destroy_all_sessions"):
                    self._security.destroy_all_sessions()
                if hasattr(self._security, "drain_events"):
                    self._security.drain_events()
                self._security = None

            # 6. DiscoveryEngine (Stop beaconing / close sockets)
            if self._discovery:
                if hasattr(self._discovery, "stop_beaconing"):
                    try:
                        self._discovery.stop_beaconing()
                    except Exception:
                        pass
                if hasattr(self._discovery, "drain_events"):
                    self._discovery.drain_events()
                self._discovery = None

            # 7. SwarmTopology
            if self._topology:
                if hasattr(self._topology, "drain_events"):
                    self._topology.drain_events()
                self._topology = None

            # 8. SwarmNode
            if self._node:
                if hasattr(self._node, "mark_offline"):
                    self._node.mark_offline()
                self._node = None

            self._initialized = False
            _logger.info("SwarmContext shutdown complete for drone=%s", self._drone_id_str)

    # ------------------------------------------------------------------
    # Health & Status Reporting
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Returns comprehensive status dictionary for monitoring and benchmarking."""
        with self._lock:
            if not self._initialized or not self._node:
                return {"initialized": False, "drone_id": self._drone_id_str}

            sec_active_count = self._security.active_session_count() if self._security else 0
            hb_stats = self._heartbeat.statistics() if (self._heartbeat and hasattr(self._heartbeat, "statistics")) else {}

            active_routes = len(getattr(self._routing, "_routes", {})) if self._routing else 0
            active_tasks = len(getattr(self._task_manager, "_tasks", {})) if self._task_manager else 0
            cluster_state = len(self._cluster_manager.get_all_clusters()) if (self._cluster_manager and hasattr(self._cluster_manager, "get_all_clusters")) else 0

            return {
                "initialized": True,
                "node_state": self._node.state.name,
                "role": self._node.role.name,
                "cluster": self._node.cluster_id,
                "parent": self._node.parent_id,
                "authenticated": self._node.authenticated,
                "active_sessions": sec_active_count,
                "heartbeat": hb_stats,
                "active_routes": active_routes,
                "active_tasks": active_tasks,
                "cluster_state": cluster_state,
                "topology_size": self._topology.size() if self._topology else 0,
            }
