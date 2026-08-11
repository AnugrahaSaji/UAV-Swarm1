"""
Leader Role Management and Subordinate Identification.

This module provides the `LeaderService` class, which allows a node to
determine its current role within the hierarchical swarm (Root Leader,
Cluster Leader, or Follower) and to identify the nodes directly subordinate
to it.

It acts as a query interface over the `SwarmTopology`, providing a high-level
view of the leadership structure relevant to the local node.
"""

from typing import List, Optional

from .cluster import Cluster
from .cluster_manager import ClusterManager
from .node import SwarmNode
from .topology import SwarmTopology
from .utils import ClusterId, DroneId, SwarmRole, get_swarm_logger

# --- Setup ---

logger = get_swarm_logger(__name__)


class LeaderService:
    """
    Manages the local node's leadership status and identifies its subordinates.

    This service provides methods to query the local node's role and to retrieve
    lists of nodes that are directly managed by this node if it is a leader.
    It relies on the `SwarmTopology` for the overall state of the swarm.
    """

    def __init__(
        self,
        topology: SwarmTopology,
        cluster_manager: ClusterManager,
        local_node_id: DroneId,
    ) -> None:
        """
        Initializes the LeaderService.

        Args:
            topology: A reference to the global `SwarmTopology` instance.
            cluster_manager: A reference to the `ClusterManager` instance.
            local_node_id: The ID of the local node running this service.
        """
        self._topology = topology
        self._cluster_manager = cluster_manager
        self._local_node_id = local_node_id
        logger.info("LeaderService initialized for node %s.", local_node_id)

    def get_my_role(self) -> SwarmRole:
        """
        Retrieves the current role of the local node.

        Returns:
            The `SwarmRole` of the local node. Defaults to CANDIDATE if not found.
        """
        local_node = self._topology.get_node(self._local_node_id)
        return local_node.role if local_node else SwarmRole.CANDIDATE

    def is_root_leader(self) -> bool:
        """Checks if the local node is currently the Root Leader."""
        return self.get_my_role() == SwarmRole.ROOT_LEADER

    def is_cluster_leader(self) -> bool:
        """Checks if the local node is currently a Cluster Leader."""
        return self.get_my_role() == SwarmRole.CLUSTER_LEADER

    def get_my_cluster_id(self) -> Optional[ClusterId]:
        """
        Retrieves the cluster ID of the local node.

        Returns:
            The `ClusterId` of the local node, or None if it does not belong
            to a cluster.
        """
        local_node = self._topology.get_node(self._local_node_id)
        return local_node.cluster_id if local_node else None

    def get_subordinate_nodes(self) -> List[SwarmNode]:
        """
        Retrieves a list of nodes directly subordinate to this leader.

        - If the local node is the Root Leader, it returns all active Cluster Leaders.
        - If the local node is a Cluster Leader, it returns all active Followers
          within its cluster.
        - Otherwise, it returns an empty list.

        Returns:
            A list of `SwarmNode` objects representing the subordinates.
        """
        local_node = self._topology.get_node(self._local_node_id)
        if not local_node:
            return []

        if local_node.role == SwarmRole.ROOT_LEADER:
            return [
                node for node in self._topology.get_all_nodes()
                if node.role == SwarmRole.CLUSTER_LEADER
            ]
        elif local_node.role == SwarmRole.CLUSTER_LEADER and local_node.cluster_id:
            return self._topology.get_cluster_followers(local_node.cluster_id)
        return []

    def get_subordinate_clusters(self) -> List[Cluster]:
        """
        Retrieves a list of `Cluster` objects directly subordinate to the Root Leader.

        This method is only relevant if the local node is the Root Leader.

        Returns:
            A list of `Cluster` objects if the local node is the Root Leader,
            otherwise an empty list.
        """
        if self.is_root_leader():
            return self._cluster_manager.get_all_clusters()
        return []
