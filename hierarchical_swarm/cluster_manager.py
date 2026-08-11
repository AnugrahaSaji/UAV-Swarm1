"""
High-Level Cluster Lifecycle Management.

This module provides the `ClusterManager`, a class responsible for orchestrating
the lifecycle of clusters within the swarm. In this initial milestone, its role
is to create and track logical `Cluster` view objects.

In future milestones, this manager will house the complex logic for dynamic
cluster formation, splitting, and merging based on network topology, node
health, and mission objectives.
"""

import threading
from typing import Dict, List, Optional

from .cluster import Cluster
from .topology import SwarmTopology
from .utils import ClusterId, DroneId, get_swarm_logger

# --- Setup ---

logger = get_swarm_logger(__name__)


class ClusterManager:
    """
    Manages the collection of logical clusters in the swarm.

    This class acts as a factory and registry for `Cluster` objects, providing
    a centralized point for managing the swarm's high-level structure. It relies
    on the `SwarmTopology` as the underlying source of truth for node data.
    """

    def __init__(self, topology: SwarmTopology) -> None:
        """
        Initializes the ClusterManager.

        Args:
            topology: A reference to the global `SwarmTopology` instance.
        """
        self._clusters: Dict[ClusterId, Cluster] = {}
        self._topology = topology
        self._lock = threading.Lock()
        logger.info("ClusterManager initialized.")

    def create_cluster(self, cluster_id: ClusterId, leader_id: DroneId) -> Cluster:
        """
        Creates and registers a new logical cluster view.

        This factory method instantiates a `Cluster` object and adds it to the
        manager's registry.

        Args:
            cluster_id: The unique identifier for the new cluster.
            leader_id: The drone ID of the cluster's designated leader.

        Returns:
            The newly created Cluster object.

        Raises:
            ValueError: If a cluster with the same ID already exists.
        """
        with self._lock:
            if cluster_id in self._clusters:
                raise ValueError(f"Cluster with ID '{cluster_id}' already exists.")

            cluster = Cluster(
                cluster_id=cluster_id,
                leader_id=leader_id,
                topology=self._topology
            )
            self._clusters[cluster_id] = cluster
            logger.info(
                "Created new cluster '%s' with leader '%s'.", cluster_id, leader_id
            )
            return cluster

    def get_cluster(self, cluster_id: ClusterId) -> Optional[Cluster]:
        """
        Retrieves a registered cluster by its ID.

        Args:
            cluster_id: The ID of the cluster to retrieve.

        Returns:
            The `Cluster` object if found, otherwise None.
        """
        with self._lock:
            return self._clusters.get(cluster_id)

    def get_all_clusters(self) -> List[Cluster]:
        """
        Retrieves a list of all currently registered clusters.

        Returns:
            A list of all `Cluster` objects.
        """
        with self._lock:
            return list(self._clusters.values())
