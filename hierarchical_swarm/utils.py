"""
Core Utilities, Constants, and Enumerations for the Hierarchical Swarm.

This module provides common, foundational components used across the entire
`hierarchical_swarm` package, including:
- Type aliases for strong type checking (e.g., DroneId, ClusterId).
- Enumerations for state management (e.g., SwarmRole, NodeStatus).
- A centralized logging factory to ensure consistent log formatting and output.
"""

import logging
from enum import Enum, auto
from typing import NewType

# --- Type Aliases ---

DroneId = NewType("DroneId", str)
"""A unique, string-based identifier for a drone within the swarm."""

ClusterId = NewType("ClusterId", str)
"""A unique, string-based identifier for a cluster within the swarm."""


# --- Enumerations ---

class SwarmRole(Enum):
    """
    Defines the possible roles a node can have within the hierarchical swarm.

    Attributes:
        ROOT_LEADER: The single, top-level leader of the entire swarm.
        CLUSTER_LEADER: A leader of a specific sub-group (cluster) of drones.
        FOLLOWER: A member of a cluster that follows a Cluster Leader.
        CANDIDATE: A node that is not yet part of the swarm but is seeking to join.
    """
    ROOT_LEADER = auto()
    CLUSTER_LEADER = auto()
    FOLLOWER = auto()
    CANDIDATE = auto()


class NodeStatus(Enum):
    """
    Defines the operational status of a node within the swarm.

    Attributes:
        ACTIVE: The node is online and fully participating in the swarm.
        INACTIVE: The node is offline or has not been heard from recently.
        JOINING: The node is in the process of joining the swarm.
        LEAVING: The node is gracefully leaving the swarm.
        REVOKED: The node's credentials have been revoked; it is not trusted.
        UNKNOWN: The status of the node has not yet been determined.
    """
    ACTIVE = auto()
    INACTIVE = auto()
    JOINING = auto()
    LEAVING = auto()
    REVOKED = auto()
    UNKNOWN = auto()


def get_swarm_logger(name: str = "swarm") -> logging.Logger:
    """
    Retrieves a standardized logger for the hierarchical swarm package.

    This function ensures that all parts of the swarm package use a consistent
    logging configuration by returning a logger from the same namespace.
    """
    return logging.getLogger(name)
