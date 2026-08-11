"""
Leader Failover Management for Swarm Resilience.

This module provides the `FailoverService`, which is responsible for
detecting the unresponsiveness of a leader (Root or Cluster) and
triggering a new election to ensure continuous swarm operation.

It operates as a background service, periodically checking the liveness
of the current leader based on the `SwarmTopology`'s view.
"""

import threading
import time
from typing import Any, Optional

from .election import ElectionService, ElectionState
from .leader import LeaderService
from .topology import SwarmTopology
from .utils import DroneId, SwarmRole, get_swarm_logger

# --- Setup ---

logger = get_swarm_logger(__name__)

DEFAULT_LEADER_MONITOR_INTERVAL_S = 5.0
DEFAULT_LEADER_TIMEOUT_S = 15.0


class FailoverService:
    """
    Monitors leader liveness and initiates failover (election) if needed.

    This service runs in a background thread, periodically checking if the
    local node's current leader (either Root or Cluster) is active. If the
    leader is deemed inactive, it triggers the `ElectionService` to start
    a new election.
    """

    def __init__(
        self,
        topology: SwarmTopology,
        leader_service: LeaderService,
        election_service: ElectionService,
        local_node_id: DroneId,
        # The secure_channel is typed as 'Any' as it will be implemented
        # in a future milestone. It is the network interface.
        secure_channel: Any,
        monitor_interval: float = DEFAULT_LEADER_MONITOR_INTERVAL_S,
        leader_timeout: float = DEFAULT_LEADER_TIMEOUT_S,
    ) -> None:
        """
        Initializes the FailoverService.

        Args:
            topology: A reference to the global `SwarmTopology` instance.
            leader_service: A reference to the `LeaderService` instance.
            election_service: A reference to the `ElectionService` instance.
            local_node_id: The ID of the local node running this service.
            secure_channel: The communication channel for sending/receiving messages.
            monitor_interval: How often to check leader liveness in seconds.
            leader_timeout: How long a leader can be unresponsive before failover.
        """
        self._topology = topology
        self._leader_service = leader_service
        self._election_service = election_service
        self._local_node_id = local_node_id
        self._secure_channel = secure_channel  # Placeholder, will be used for communication
        self._monitor_interval = monitor_interval
        self._leader_timeout = leader_timeout

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        logger.info("FailoverService initialized for node %s.", local_node_id)

    def start(self) -> None:
        """Starts the failover monitoring service in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("FailoverService is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("FailoverService started with a %.1fs monitor interval.", self._monitor_interval)

    def stop(self) -> None:
        """Stops the failover monitoring service background thread."""
        if self._thread is None or not self._thread.is_alive():
            logger.info("FailoverService is not running.")
            return

        self._stop_event.set()
        self._thread.join()
        logger.info("FailoverService stopped.")

    def _run_loop(self) -> None:
        """The main loop for the failover background thread."""
        while not self._stop_event.is_set():
            self._monitor_leader_liveness()
            self._stop_event.wait(self._monitor_interval)

    def _monitor_leader_liveness(self) -> None:
        """
        Checks the liveness of the current leader(s) and triggers failover if necessary.

        This method checks both the Root Leader and, if applicable, the Cluster Leader.
        It avoids initiating an election if one is already in progress.
        """
        if self._election_service.get_state() != ElectionState.IDLE:
            logger.debug("Election already in progress, skipping leader liveness check.")
            return

        local_node = self._topology.get_node(self._local_node_id)
        if not local_node:
            logger.warning("Local node %s not found in topology, cannot monitor leader.", self._local_node_id)
            return

        # Monitor Root Leader if this node is not the Root Leader
        if local_node.role != SwarmRole.ROOT_LEADER:
            root_leader = self._topology.get_leader(SwarmRole.ROOT_LEADER)
            if root_leader and not root_leader.is_alive(self._leader_timeout):
                logger.warning(
                    "Root Leader %s detected as inactive. Initiating failover.",
                    root_leader.drone_id
                )
                self._initiate_failover(SwarmRole.ROOT_LEADER, f"Root Leader {root_leader.drone_id} inactive")
                return  # Only initiate one election at a time

        # Monitor Cluster Leader if this node is a Follower
        if local_node.role == SwarmRole.FOLLOWER and local_node.cluster_id:
            cluster_leader = self._topology.get_leader(SwarmRole.CLUSTER_LEADER)
            if cluster_leader and cluster_leader.cluster_id == local_node.cluster_id and \
               not cluster_leader.is_alive(self._leader_timeout):
                logger.warning(
                    "Cluster Leader %s (for cluster %s) detected as inactive. Initiating failover.",
                    cluster_leader.drone_id, cluster_leader.cluster_id
                )
                self._initiate_failover(SwarmRole.CLUSTER_LEADER, f"Cluster Leader {cluster_leader.drone_id} inactive")
                return

    def _initiate_failover(self, election_type: SwarmRole, reason: str) -> None:
        """
        Triggers an election via the ElectionService.

        Args:
            election_type: The type of leader to elect (ROOT_LEADER or CLUSTER_LEADER).
            reason: The reason for initiating the election.
        """
        self._election_service.initiate_election(election_type, reason)
