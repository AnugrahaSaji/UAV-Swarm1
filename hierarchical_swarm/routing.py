"""
Hierarchical Message Routing Management.

This module provides the `RoutingManager`, a class responsible for determining
the next hop for a message within the hierarchical swarm topology. It does not
manage a complex routing table but instead computes routes dynamically based on
the roles and cluster affiliations of nodes stored in the `SwarmTopology`.
"""

from typing import Optional

from .node import SwarmNode
from .topology import SwarmTopology
from .utils import ClusterId, DroneId, SwarmRole, get_swarm_logger

# --- Setup ---

logger = get_swarm_logger(__name__)


class RoutingManager:
    """
    Determines the next hop for messages based on the swarm hierarchy.

    This manager implements the core routing logic for the hierarchical swarm.
    It uses the live `SwarmTopology` to make decisions, ensuring that messages
    are forwarded up or down the cluster tree correctly.

    Routing Rules:
    - A Follower always sends messages to its Cluster Leader.
    - A Cluster Leader sends messages for other clusters to the Root Leader.
    - A Cluster Leader sends messages for its own followers directly.
    - The Root Leader sends messages to the appropriate Cluster Leader.
    """

    def __init__(self, topology: SwarmTopology, local_node_id: DroneId) -> None:
        """
        Initializes the RoutingManager.

        Args:
            topology: A reference to the global SwarmTopology instance.
            local_node_id: The ID of the local node running this service.
        """
        self._topology = topology
        self._local_node_id = local_node_id
        logger.info("RoutingManager initialized for node %s.", local_node_id)

    def get_next_hop(self, destination_id: DroneId) -> Optional[DroneId]:
        """
        Calculates the next hop required to send a message to a destination.

        Args:
            destination_id: The final destination for the message.

        Returns:
            The DroneId of the next node to forward the message to, or None if
            no route can be determined (e.g., destination is self, or nodes
            are not in the topology).
        """
        if destination_id == self._local_node_id:
            logger.debug("Destination is self; no next hop required.")
            return None

        local_node = self._topology.get_node(self._local_node_id)
        destination_node = self._topology.get_node(destination_id)

        if not local_node:
            logger.error("Cannot determine next hop: local node %s not in topology.", self._local_node_id)
            return None
        if not destination_node:
            logger.warning("Cannot determine next hop: destination node %s not in topology.", destination_id)
            return None

        # --- Routing logic based on the local node's role ---

        if local_node.role == SwarmRole.FOLLOWER:
            # Followers always route through their Cluster Leader.
            if not local_node.cluster_id:
                logger.warning("Follower %s has no cluster_id, cannot find leader.", self._local_node_id)
                return None
            cluster_leader = self._find_cluster_leader(local_node.cluster_id)
            if not cluster_leader:
                logger.warning("Could not find leader for cluster %s.", local_node.cluster_id)
                return None
            return cluster_leader.drone_id

        elif local_node.role == SwarmRole.CLUSTER_LEADER:
            # If destination is in the same cluster, send directly.
            if destination_node.cluster_id == local_node.cluster_id:
                return destination_id
            # Otherwise, route up to the Root Leader.
            root_leader = self._topology.get_leader(SwarmRole.ROOT_LEADER)
            if not root_leader:
                logger.warning("Could not find Root Leader to route message to %s.", destination_id)
                return None
            return root_leader.drone_id

        elif local_node.role == SwarmRole.ROOT_LEADER:
            # If destination is a Cluster Leader, send directly.
            if destination_node.role == SwarmRole.CLUSTER_LEADER:
                return destination_id
            # If destination is a Follower, find its Cluster Leader and route there.
            if destination_node.role == SwarmRole.FOLLOWER:
                if not destination_node.cluster_id:
                    logger.warning("Destination follower %s has no cluster_id.", destination_id)
                    return None
                target_leader = self._find_cluster_leader(destination_node.cluster_id)
                if not target_leader:
                    logger.warning("Could not find leader for destination cluster %s.", destination_node.cluster_id)
                    return None
                return target_leader.drone_id

        logger.error(
            "Unhandled routing case from %s (role: %s) to %s (role: %s).",
            self._local_node_id, local_node.role.name,
            destination_id, destination_node.role.name
        )
        return None

    def _find_cluster_leader(self, cluster_id: ClusterId) -> Optional[SwarmNode]:
        """Helper method to find the leader of a specific cluster."""
        all_nodes = self._topology.get_all_nodes()
        for node in all_nodes:
            if node.role == SwarmRole.CLUSTER_LEADER and node.cluster_id == cluster_id:
                return node
        return None
