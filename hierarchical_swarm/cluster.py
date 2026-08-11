"""
Logical Cluster Representation.

This module provides the `Cluster` class, which represents a logical grouping
of a Cluster Leader and its Follower nodes. It acts as a high-level view
over the `SwarmTopology`, providing convenient methods to query the members
of a specific cluster without duplicating the state stored in the topology.
"""

from typing import List, Optional

from .node import SwarmNode
from .topology import SwarmTopology
from .utils import ClusterId, DroneId, SwarmRole, get_swarm_logger

# --- Setup ---

logger = get_swarm_logger(__name__)


class Cluster:
    """
    Represents a single, logical cluster within the swarm.

    A cluster consists of one Cluster Leader and one or more Followers. This
    class provides a convenient, object-oriented way to interact with the
    members of a cluster by querying the central `SwarmTopology`.
    """

    def __init__(
        self,
        cluster_id: ClusterId,
        leader_id: DroneId,
        topology: SwarmTopology,
    ) -> None:
        """
        Initializes a Cluster view.

        Args:
            cluster_id: The unique identifier for this cluster.
            leader_id: The unique identifier of the node acting as the leader.
            topology: A reference to the global SwarmTopology instance, which
                      is the source of truth for node information.
        """
        if not cluster_id:
            raise ValueError("cluster_id cannot be empty.")
        if not leader_id:
            raise ValueError("leader_id cannot be empty.")

        self.cluster_id = cluster_id
        self.leader_id = leader_id
        self._topology = topology
        logger.debug(
            "Instantiated Cluster view for cluster_id: %s with leader: %s",
            self.cluster_id, self.leader_id
        )

    def get_leader(self) -> Optional[SwarmNode]:
        """
        Retrieves the leader node of this cluster from the topology.

        Returns:
            The SwarmNode object for the leader, or None if it's not found
            or is no longer the leader of this cluster.
        """
        leader_node = self._topology.get_node(self.leader_id)
        if (
            leader_node and
            leader_node.role == SwarmRole.CLUSTER_LEADER and
            leader_node.cluster_id == self.cluster_id
        ):
            return leader_node
        logger.warning(
            "Leader %s not found or has incorrect role/cluster for cluster %s.",
            self.leader_id, self.cluster_id
        )
        return None

    def get_followers(self) -> List[SwarmNode]:
        """
        Retrieves all active follower nodes belonging to this cluster.

        This method queries the central topology to get the most up-to-date
        list of followers for this specific cluster.

        Returns:
            A list of SwarmNode objects for the followers.
        """
        return self._topology.get_cluster_followers(self.cluster_id)

    def __repr__(self) -> str:
        """Provides a developer-friendly representation of the cluster."""
        return (
            f"Cluster(cluster_id='{self.cluster_id}', "
            f"leader_id='{self.leader_id}')"
        )
