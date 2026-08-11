"""SwarmTopology: Central Runtime Database for the Hierarchical UAV Swarm.

This module is the **sole owner** of the swarm's 3-tier tree topology.  No
other module may modify topological state directly.  Every mutation must go
through the public API defined here.

Design follows the approved Topology Design Review exactly:

Internal structures (all private):
    _nodes:    Dict[str, SwarmNode]           – master record store
    _parents:  Dict[str, Optional[str]]       – O(1) upward traversal
    _children: Dict[str, Set[str]]            – O(1) downward traversal
    _clusters: Dict[str, Set[str]]            – O(1) cluster membership
    _leaders:  Dict[str, Optional[str]]       – O(1) cluster leader identity
    _root:     Optional[str]                  – global root identity
    _version:  int                            – monotonic structural change counter

Concurrency:
    A single threading.RLock serialises all writes.
    Read methods acquire the lock and return defensive copies.
    Events are collected inside the lock and published after release.

Invariants enforced on every write:
    I-1  Single root (at most one ROOT_LEADER).
    I-2  No parent cycles.
    I-3  Parent must exist in _nodes (or None for root).
    I-4  Follower nodes cannot have children.
    I-5  One cluster per node.
    I-6  Parent-child index consistency (_parents ↔ _children).
    I-7  Cluster leader must be a member of the cluster.
    I-8  Unique drone IDs.
    I-9  Root node has no parent (parent_id == None).
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Deque, Dict, FrozenSet, List, Optional, Set, Tuple

from hierarchical_swarm.node import NodeState, SwarmNode
from hierarchical_swarm.utils import ClusterId, DroneId, SwarmRole

try:
    from core.logging_utils import METRICS, get_logger
    _logger = get_logger("hierarchical_swarm.topology")
except ImportError:
    _logger = logging.getLogger("hierarchical_swarm.topology")
    METRICS = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class TopologyError(Exception):
    """Base exception for all topology operation failures."""


class TopologyInvariantError(TopologyError):
    """Raised when a write operation would violate a topology invariant."""


class TopologyNodeNotFoundError(TopologyError):
    """Raised when a referenced drone_id does not exist in the topology."""


class TopologyDuplicateNodeError(TopologyError):
    """Raised when attempting to add a drone_id that already exists."""


class TopologyClusterNotFoundError(TopologyError):
    """Raised when a referenced cluster_id is not registered."""


# ---------------------------------------------------------------------------
# Topology Events (prepared here; dispatched by the event bus elsewhere)
# ---------------------------------------------------------------------------

class TopologyEventType(Enum):
    """Categories of structural topology events."""

    NODE_JOINED      = auto()
    NODE_REMOVED     = auto()
    TOPOLOGY_CHANGED = auto()
    LEADER_CHANGED   = auto()
    RE_PARENT        = auto()
    CLUSTER_UPDATED  = auto()


@dataclass(slots=True, frozen=True)
class TopologyEvent:
    """An immutable event record produced by a topology write operation.

    Consumers drain these via ``SwarmTopology.drain_events()`` after the
    lock has been released and process them asynchronously.

    Attributes:
        event_type:  Category of the structural change.
        drone_id:    Primary drone involved (may be empty string if N/A).
        cluster_id:  Cluster involved (may be empty string if N/A).
        extra:       Optional string carrying additional context.
    """

    event_type: TopologyEventType
    drone_id:   str = ""
    cluster_id: str = ""
    extra:      str = ""


# ---------------------------------------------------------------------------
# SwarmTopology
# ---------------------------------------------------------------------------

class SwarmTopology:
    """Thread-safe, indexed 3-tier hierarchical swarm topology database.

    Deployment target:
        8 drones, 2 clusters, static topology (no auto split/merge).
        Memory footprint ≈ 6 KB for the full 8-drone swarm.

    Usage pattern:
        1.  Construct ``SwarmTopology()``.
        2.  Call ``add_node()`` for each drone (root first, then leaders,
            then followers) during swarm initialisation.
        3.  All other modules interact only through the public API.
        4.  After each write, call ``drain_events()`` to retrieve pending
            ``TopologyEvent`` objects for the event bus.

    Thread safety:
        All public methods are safe to call from multiple threads.
        The internal ``_lock`` is a ``threading.RLock`` to support nested
        calls within the same thread.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self) -> None:
        # Master record store — only strong references to SwarmNode objects.
        self._nodes:    Dict[str, SwarmNode]          = {}
        # Upward traversal index.
        self._parents:  Dict[str, Optional[str]]      = {}
        # Downward traversal index.
        self._children: Dict[str, Set[str]]           = {}
        # Cluster membership index.
        self._clusters: Dict[str, Set[str]]           = {}
        # Per-cluster leader index.
        self._leaders:  Dict[str, Optional[str]]      = {}
        # Root leader drone_id (at most one at any time).
        self._root:     Optional[str]                 = None
        # Monotonically increasing structural change counter.
        self._version:  int                           = 0

        # Pending events — drained by the event bus after each write.
        self._pending_events: Deque[TopologyEvent]    = deque()

        # Single reentrant lock serialising all writes.
        self._lock: threading.RLock                   = threading.RLock()

        _logger.info("SwarmTopology initialised")

    # ------------------------------------------------------------------
    # Public Properties
    # ------------------------------------------------------------------

    @property
    def version(self) -> int:
        """Returns the current structural version counter.

        Consumers (e.g. ``routing.py``) cache this value and rebuild
        route tables only when it changes.  The read is lock-free;
        CPython's GIL guarantees atomic int reads.
        """
        return self._version

    # ------------------------------------------------------------------
    # Event Drain
    # ------------------------------------------------------------------

    def drain_events(self) -> List[TopologyEvent]:
        """Returns and clears all pending topology events.

        Call this **after** each write operation from the thread that
        performed the write.  The returned list is a stable snapshot;
        further writes will not mutate it.

        Returns:
            List of ``TopologyEvent`` objects in the order they were produced.
        """
        with self._lock:
            events = list(self._pending_events)
            self._pending_events.clear()
        return events

    # ------------------------------------------------------------------
    # Write Operations
    # ------------------------------------------------------------------

    def add_node(
        self,
        node: SwarmNode,
        cluster_id: Optional[str] = None,
    ) -> None:
        """Registers a new drone node in the topology.

        The node's ``parent_id`` and ``role`` fields (set before calling
        this method) determine how it is indexed.  ``cluster_id`` may be
        supplied as a parameter to override ``node.cluster_id`` — useful
        when the caller constructs a node before knowing its final cluster.

        Invariants checked (raises ``TopologyInvariantError`` on failure):
            I-1  Adding a ROOT_LEADER when one already exists.
            I-3  parent_id referenced but not present in ``_nodes``.
            I-8  drone_id already registered.
            I-9  ROOT_LEADER supplied with a non-None parent_id.

        Args:
            node:       Fully constructed ``SwarmNode``.
            cluster_id: Cluster to register the node under.  If ``None``,
                        ``node.cluster_id`` is used.  Must not be ``None``
                        for non-root nodes.

        Raises:
            TopologyDuplicateNodeError:  drone_id already present.
            TopologyInvariantError:      An invariant would be violated.
            TopologyNodeNotFoundError:   parent_id not in topology.
        """
        effective_cluster = cluster_id or node.cluster_id

        collected_events: List[TopologyEvent] = []

        with self._lock:
            self._check_duplicate(node.drone_id)
            self._check_single_root(node.role, node.drone_id)
            self._check_root_has_no_parent(node.role, node.parent_id)
            self._check_parent_exists(node.parent_id)
            self._check_cluster_for_non_root(node.role, effective_cluster)

            # ---- commit to all indexes atomically ----

            self._nodes[node.drone_id] = node

            self._parents[node.drone_id] = node.parent_id

            # Register as child of parent.
            if node.parent_id is not None:
                self._children.setdefault(node.parent_id, set()).add(node.drone_id)

            # Ensure children bucket exists for this node.
            self._children.setdefault(node.drone_id, set())

            # Cluster membership.
            if effective_cluster:
                self._clusters.setdefault(effective_cluster, set()).add(node.drone_id)
                self._leaders.setdefault(effective_cluster, None)
                # Keep node's own cluster_id field in sync.
                if node.cluster_id != effective_cluster:
                    node.update_cluster(ClusterId(effective_cluster))

            # Root / leader indexes.
            if node.role is SwarmRole.ROOT_LEADER:
                self._root = node.drone_id
            elif node.role is SwarmRole.CLUSTER_LEADER and effective_cluster:
                self._leaders[effective_cluster] = node.drone_id

            self._version += 1

            collected_events.append(TopologyEvent(
                event_type=TopologyEventType.NODE_JOINED,
                drone_id=node.drone_id,
                cluster_id=effective_cluster or "",
            ))

        # Publish after lock release.
        self._extend_pending(collected_events)
        _logger.info(
            "add_node: drone=%s role=%s cluster=%s parent=%s",
            node.drone_id, node.role.name, effective_cluster, node.parent_id,
        )
        if METRICS:
            METRICS.gauge("swarm_topology_node_count").set(len(self._nodes))

    def remove_node(self, drone_id: str) -> None:
        """Removes a drone node from the topology.

        The node must have no children.  Callers (``cluster_manager.py``)
        must re-parent or remove children before calling this method.

        Invariant checked:
            Node must exist.
            Node must have no children (Invariant I-4 enforcement on removal).

        Args:
            drone_id: Identifier of the node to remove.

        Raises:
            TopologyNodeNotFoundError:  Node not in topology.
            TopologyInvariantError:     Node still has children.
        """
        collected_events: List[TopologyEvent] = []

        with self._lock:
            node = self._require_node(drone_id)

            children = self._children.get(drone_id, set())
            if children:
                raise TopologyInvariantError(
                    f"Cannot remove '{drone_id}': it still has children {children}. "
                    "Re-parent or remove children first."
                )

            cluster_id = str(node.cluster_id) if node.cluster_id else ""
            parent_id  = self._parents.get(drone_id)

            # ---- remove from all indexes atomically ----

            # Detach from parent's children bucket.
            if parent_id and parent_id in self._children:
                self._children[parent_id].discard(drone_id)

            # Remove own children bucket.
            self._children.pop(drone_id, None)

            # Cluster membership.
            if cluster_id and cluster_id in self._clusters:
                self._clusters[cluster_id].discard(drone_id)

            # Parent index.
            self._parents.pop(drone_id, None)

            # Root index.
            if self._root == drone_id:
                self._root = None

            # Leader index.
            if cluster_id and self._leaders.get(cluster_id) == drone_id:
                self._leaders[cluster_id] = None

            # Master store — drops the last strong reference.
            del self._nodes[drone_id]

            self._version += 1

            collected_events.append(TopologyEvent(
                event_type=TopologyEventType.NODE_REMOVED,
                drone_id=drone_id,
                cluster_id=cluster_id,
            ))

        self._extend_pending(collected_events)
        _logger.info("remove_node: drone=%s", drone_id)
        if METRICS:
            METRICS.gauge("swarm_topology_node_count").set(len(self._nodes))

    def re_parent(self, drone_id: str, new_parent_id: str) -> None:
        """Moves a node under a new parent within the topology.

        Used by ``cluster_manager.py`` during leader failover to redirect
        followers to the newly elected leader.

        Invariants checked:
            drone_id must exist.
            new_parent_id must exist.
            The move must not introduce a cycle.
            The move must not violate Invariant I-4 (followers cannot have
            children — checked on new parent's role: if the node being
            re-parented has children, the new parent cannot be a Follower).

        Args:
            drone_id:      The node to move.
            new_parent_id: The new parent to attach it to.

        Raises:
            TopologyNodeNotFoundError:  Either ID not in topology.
            TopologyInvariantError:     Operation would create a cycle or
                                        violate hierarchy rules.
        """
        collected_events: List[TopologyEvent] = []

        with self._lock:
            self._require_node(drone_id)
            self._require_node(new_parent_id)

            old_parent_id = self._parents.get(drone_id)

            if old_parent_id == new_parent_id:
                return  # No-op; idempotent.

            # Cycle detection — walk upward from new_parent_id.
            self._check_no_cycle(drone_id, new_parent_id)

            # ---- commit atomically ----

            # Remove from old parent's children.
            if old_parent_id and old_parent_id in self._children:
                self._children[old_parent_id].discard(drone_id)

            # Attach to new parent.
            self._children.setdefault(new_parent_id, set()).add(drone_id)
            self._parents[drone_id] = new_parent_id

            # Keep SwarmNode field in sync.
            node = self._nodes[drone_id]
            node.update_parent(DroneId(new_parent_id))

            self._version += 1

            collected_events.append(TopologyEvent(
                event_type=TopologyEventType.RE_PARENT,
                drone_id=drone_id,
                cluster_id=str(node.cluster_id) if node.cluster_id else "",
                extra=f"old_parent={old_parent_id} new_parent={new_parent_id}",
            ))
            collected_events.append(TopologyEvent(
                event_type=TopologyEventType.TOPOLOGY_CHANGED,
                drone_id=drone_id,
            ))

        self._extend_pending(collected_events)
        _logger.info(
            "re_parent: drone=%s old_parent=%s new_parent=%s",
            drone_id, old_parent_id, new_parent_id,
        )

    def set_cluster_leader(self, cluster_id: str, new_leader_id: str) -> None:
        """Designates a new Cluster Leader for the given cluster.

        Demotes the previous leader (if any) to ``FOLLOWER`` before
        promoting the new one.  Both role changes are committed under a
        single lock acquisition.

        Invariants checked:
            cluster_id must be registered.
            new_leader_id must be a member of cluster_id.

        Args:
            cluster_id:     Target cluster.
            new_leader_id:  drone_id of the new Cluster Leader.

        Raises:
            TopologyClusterNotFoundError: cluster_id not registered.
            TopologyInvariantError:       new_leader_id not in cluster.
            TopologyNodeNotFoundError:    new_leader_id not in topology.
        """
        collected_events: List[TopologyEvent] = []

        with self._lock:
            self._require_cluster(cluster_id)
            self._require_node(new_leader_id)
            self._check_node_in_cluster(new_leader_id, cluster_id)

            old_leader_id = self._leaders.get(cluster_id)

            if old_leader_id == new_leader_id:
                return  # Already the leader; idempotent.

            # Demote old leader.
            if old_leader_id and old_leader_id in self._nodes:
                old_leader = self._nodes[old_leader_id]
                old_leader.update_role(SwarmRole.FOLLOWER, new_tree_level=2)

            # Promote new leader.
            new_leader = self._nodes[new_leader_id]
            new_leader.update_role(SwarmRole.CLUSTER_LEADER, new_tree_level=1)
            self._leaders[cluster_id] = new_leader_id

            self._version += 1

            collected_events.append(TopologyEvent(
                event_type=TopologyEventType.LEADER_CHANGED,
                drone_id=new_leader_id,
                cluster_id=cluster_id,
                extra=f"old_leader={old_leader_id}",
            ))
            collected_events.append(TopologyEvent(
                event_type=TopologyEventType.TOPOLOGY_CHANGED,
                cluster_id=cluster_id,
            ))

        self._extend_pending(collected_events)
        _logger.info(
            "set_cluster_leader: cluster=%s old=%s new=%s",
            cluster_id, old_leader_id, new_leader_id,
        )

    def update_node_cluster(
        self,
        drone_id: str,
        new_cluster_id: str,
    ) -> None:
        """Moves a node from its current cluster to a new one.

        Used during re-parenting when a follower must join a different
        cluster after its original leader fails.

        Args:
            drone_id:       Node to move.
            new_cluster_id: Target cluster (must already be registered).

        Raises:
            TopologyNodeNotFoundError:    drone_id not in topology.
            TopologyClusterNotFoundError: new_cluster_id not registered.
        """
        collected_events: List[TopologyEvent] = []

        with self._lock:
            node = self._require_node(drone_id)
            self._require_cluster(new_cluster_id)

            old_cluster_id = str(node.cluster_id) if node.cluster_id else ""

            if old_cluster_id == new_cluster_id:
                return  # Idempotent.

            # Remove from old cluster.
            if old_cluster_id and old_cluster_id in self._clusters:
                self._clusters[old_cluster_id].discard(drone_id)

            # Add to new cluster.
            self._clusters[new_cluster_id].add(drone_id)
            node.update_cluster(ClusterId(new_cluster_id))

            self._version += 1

            collected_events.append(TopologyEvent(
                event_type=TopologyEventType.CLUSTER_UPDATED,
                drone_id=drone_id,
                cluster_id=new_cluster_id,
                extra=f"old_cluster={old_cluster_id}",
            ))

        self._extend_pending(collected_events)
        _logger.info(
            "update_node_cluster: drone=%s old=%s new=%s",
            drone_id, old_cluster_id, new_cluster_id,
        )

    # ------------------------------------------------------------------
    # Read Operations (all return defensive snapshots)
    # ------------------------------------------------------------------

    def contains(self, drone_id: str) -> bool:
        """Returns ``True`` if the drone_id is registered in the topology."""
        with self._lock:
            return drone_id in self._nodes

    def size(self) -> int:
        """Returns the total number of registered nodes."""
        with self._lock:
            return len(self._nodes)

    def get_node(self, drone_id: str) -> SwarmNode:
        """Returns the live ``SwarmNode`` object for the given drone_id.

        The returned object is the live instance, not a copy.  Callers
        must not mutate it directly; use the node's own mutation methods.

        Args:
            drone_id: Target drone identifier.

        Returns:
            The corresponding ``SwarmNode``.

        Raises:
            TopologyNodeNotFoundError: drone_id not in topology.
        """
        with self._lock:
            return self._require_node(drone_id)

    def get_parent(self, drone_id: str) -> Optional[SwarmNode]:
        """Returns the parent ``SwarmNode`` of the given node, or ``None``
        if it is the Root Leader.

        Args:
            drone_id: Child drone identifier.

        Returns:
            Parent ``SwarmNode``, or ``None`` for the Root Leader.

        Raises:
            TopologyNodeNotFoundError: drone_id not in topology.
        """
        with self._lock:
            self._require_node(drone_id)
            parent_id = self._parents.get(drone_id)
            if parent_id is None:
                return None
            return self._nodes.get(parent_id)

    def get_children(self, drone_id: str) -> List[SwarmNode]:
        """Returns a snapshot list of the direct children of the given node.

        Returns an empty list for Follower nodes (Tier 2).

        Args:
            drone_id: Parent drone identifier.

        Returns:
            List of child ``SwarmNode`` objects (order unspecified).

        Raises:
            TopologyNodeNotFoundError: drone_id not in topology.
        """
        with self._lock:
            self._require_node(drone_id)
            child_ids = list(self._children.get(drone_id, set()))
            return [self._nodes[cid] for cid in child_ids if cid in self._nodes]

    def get_cluster_members(self, cluster_id: str) -> List[SwarmNode]:
        """Returns a snapshot list of all nodes in the given cluster.

        Includes the Cluster Leader.  Order is unspecified.

        Args:
            cluster_id: Target cluster identifier.

        Returns:
            List of ``SwarmNode`` objects.

        Raises:
            TopologyClusterNotFoundError: cluster_id not registered.
        """
        with self._lock:
            self._require_cluster(cluster_id)
            member_ids = list(self._clusters[cluster_id])
            return [self._nodes[mid] for mid in member_ids if mid in self._nodes]

    def get_cluster_leader(self, cluster_id: str) -> Optional[SwarmNode]:
        """Returns the current Cluster Leader node, or ``None`` during an
        election window.

        Args:
            cluster_id: Target cluster identifier.

        Returns:
            ``SwarmNode`` of the Cluster Leader, or ``None``.

        Raises:
            TopologyClusterNotFoundError: cluster_id not registered.
        """
        with self._lock:
            self._require_cluster(cluster_id)
            leader_id = self._leaders.get(cluster_id)
            if leader_id is None:
                return None
            return self._nodes.get(leader_id)

    def get_root(self) -> Optional[SwarmNode]:
        """Returns the Root Leader node, or ``None`` during an L0 election.

        Callers must handle ``None`` gracefully (fall back to the last
        known SMT root hash via ``smt/root_manager.py``).
        """
        with self._lock:
            if self._root is None:
                return None
            return self._nodes.get(self._root)

    def get_descendants(self, drone_id: str) -> List[SwarmNode]:
        """Returns all descendant nodes (BFS) under the given drone.

        This is an $O(N)$ operation — intended only for diagnostics and
        mission fan-out from the Root Leader.

        Args:
            drone_id: Root of the subtree to traverse.

        Returns:
            Flat list of all descendant ``SwarmNode`` objects, excluding
            the starting node itself.

        Raises:
            TopologyNodeNotFoundError: drone_id not in topology.
        """
        with self._lock:
            self._require_node(drone_id)
            return self._bfs_descendants(drone_id)

    def list_all_nodes(self) -> List[SwarmNode]:
        """Returns a snapshot list of every registered node.

        Order is unspecified.  Intended for diagnostics and integrity checks.
        """
        with self._lock:
            return list(self._nodes.values())

    def get_all_nodes(self) -> List[SwarmNode]:
        """Alias for list_all_nodes()."""
        return self.list_all_nodes()

    def list_cluster_ids(self) -> List[str]:
        """Returns a snapshot list of all registered cluster identifiers."""
        with self._lock:
            return list(self._clusters.keys())

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> List[str]:
        """Performs a full invariant audit of the topology.

        Intended for diagnostics, startup checks, and test assertions.
        Does not raise; instead returns a list of violation messages.
        An empty list means the topology is fully consistent.

        Returns:
            List of violation description strings (empty = healthy).
        """
        violations: List[str] = []
        with self._lock:
            violations.extend(self._audit_root_count())
            violations.extend(self._audit_parent_child_consistency())
            violations.extend(self._audit_cluster_membership())
            violations.extend(self._audit_leader_membership())
            violations.extend(self._audit_follower_no_children())
        return violations

    def clear(self) -> None:
        """Removes all nodes and resets all indexes.

        Intended for test teardown only.  Not safe to call during live
        swarm operation.
        """
        with self._lock:
            self._nodes.clear()
            self._parents.clear()
            self._children.clear()
            self._clusters.clear()
            self._leaders.clear()
            self._root = None
            self._version += 1
            self._pending_events.clear()
        _logger.warning("SwarmTopology cleared — all nodes removed")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _require_node(self, drone_id: str) -> SwarmNode:
        """Returns the node or raises ``TopologyNodeNotFoundError``."""
        node = self._nodes.get(drone_id)
        if node is None:
            raise TopologyNodeNotFoundError(
                f"Drone '{drone_id}' not found in topology"
            )
        return node

    def _require_cluster(self, cluster_id: str) -> None:
        """Raises ``TopologyClusterNotFoundError`` if cluster not registered."""
        if cluster_id not in self._clusters:
            raise TopologyClusterNotFoundError(
                f"Cluster '{cluster_id}' not registered in topology"
            )

    def _check_duplicate(self, drone_id: str) -> None:
        """Enforces Invariant I-8: unique drone IDs."""
        if drone_id in self._nodes:
            raise TopologyDuplicateNodeError(
                f"Drone '{drone_id}' is already registered in the topology"
            )

    def _check_parent_exists(self, parent_id: Optional[str]) -> None:
        """Enforces Invariant I-3: parent must exist."""
        if parent_id is not None and parent_id not in self._nodes:
            raise TopologyNodeNotFoundError(
                f"Parent drone '{parent_id}' not found in topology. "
                "Add the parent before the child."
            )

    def _check_single_root(self, role: SwarmRole, drone_id: str) -> None:
        """Enforces Invariant I-1: at most one ROOT_LEADER."""
        if role is SwarmRole.ROOT_LEADER and self._root is not None:
            raise TopologyInvariantError(
                f"Cannot add ROOT_LEADER '{drone_id}': "
                f"'{self._root}' is already the Root Leader. "
                "Demote or remove the existing root first."
            )

    def _check_root_has_no_parent(
        self, role: SwarmRole, parent_id: Optional[str]
    ) -> None:
        """Enforces Invariant I-9: root node has no parent."""
        if role is SwarmRole.ROOT_LEADER and parent_id is not None:
            raise TopologyInvariantError(
                f"ROOT_LEADER must have parent_id=None, got '{parent_id}'"
            )

    def _check_cluster_for_non_root(
        self, role: SwarmRole, cluster_id: Optional[str]
    ) -> None:
        """Non-root nodes must specify a cluster."""
        if role is not SwarmRole.ROOT_LEADER and not cluster_id:
            raise TopologyInvariantError(
                "Non-root nodes must belong to a cluster. "
                "Provide cluster_id in add_node()."
            )

    def _check_node_in_cluster(self, drone_id: str, cluster_id: str) -> None:
        """Enforces Invariant I-7: leader must be a member of the cluster."""
        members = self._clusters.get(cluster_id, set())
        if drone_id not in members:
            raise TopologyInvariantError(
                f"Cannot set '{drone_id}' as leader of '{cluster_id}': "
                "node is not a member of that cluster."
            )

    def _check_no_cycle(self, drone_id: str, new_parent_id: str) -> None:
        """Enforces Invariant I-2: re-parent must not create a cycle.

        Walks upward from ``new_parent_id`` through ``_parents`` for a
        maximum of ``len(_nodes)`` steps.  If ``drone_id`` appears in the
        chain, a cycle would form.
        """
        cursor: Optional[str] = new_parent_id
        steps = 0
        max_steps = len(self._nodes)

        while cursor is not None and steps <= max_steps:
            if cursor == drone_id:
                raise TopologyInvariantError(
                    f"re_parent('{drone_id}', '{new_parent_id}') would "
                    "create a cycle in the topology tree."
                )
            cursor = self._parents.get(cursor)
            steps += 1

    def _bfs_descendants(self, root_id: str) -> List[SwarmNode]:
        """BFS over ``_children`` starting from root_id.

        Returns all descendants excluding root_id itself.
        Called inside the lock.
        """
        result: List[SwarmNode] = []
        queue: List[str] = list(self._children.get(root_id, set()))

        while queue:
            current = queue.pop(0)
            if current in self._nodes:
                result.append(self._nodes[current])
                queue.extend(self._children.get(current, set()))
        return result

    def _extend_pending(self, events: List[TopologyEvent]) -> None:
        """Appends collected events to the pending queue (thread-safe)."""
        with self._lock:
            self._pending_events.extend(events)

    # ------------------------------------------------------------------
    # Audit helpers (called from validate(), always inside lock)
    # ------------------------------------------------------------------

    def _audit_root_count(self) -> List[str]:
        violations: List[str] = []
        root_nodes = [
            n.drone_id
            for n in self._nodes.values()
            if n.role is SwarmRole.ROOT_LEADER
        ]
        if len(root_nodes) > 1:
            violations.append(f"I-1 VIOLATED: Multiple ROOT_LEADERs found: {root_nodes}")
        if self._root is not None and self._root not in self._nodes:
            violations.append(f"I-1 VIOLATED: _root='{self._root}' not in _nodes")
        return violations

    def _audit_parent_child_consistency(self) -> List[str]:
        violations: List[str] = []
        for child_id, parent_id in self._parents.items():
            if parent_id is None:
                continue
            # Child must appear in parent's children set.
            parent_children = self._children.get(parent_id, set())
            if child_id not in parent_children:
                violations.append(
                    f"I-6 VIOLATED: _parents['{child_id}']='{parent_id}' "
                    f"but '{child_id}' ∉ _children['{parent_id}']"
                )
        for parent_id, child_set in self._children.items():
            for child_id in child_set:
                if self._parents.get(child_id) != parent_id:
                    violations.append(
                        f"I-6 VIOLATED: _children['{parent_id}'] contains "
                        f"'{child_id}' but _parents['{child_id}']="
                        f"'{self._parents.get(child_id)}'"
                    )
        return violations

    def _audit_cluster_membership(self) -> List[str]:
        violations: List[str] = []
        # Every node must appear in exactly one cluster (except root with no cluster).
        for drone_id, node in self._nodes.items():
            if node.role is SwarmRole.ROOT_LEADER:
                continue
            membership_count = sum(
                1 for members in self._clusters.values() if drone_id in members
            )
            if membership_count != 1:
                violations.append(
                    f"I-5 VIOLATED: drone '{drone_id}' appears in "
                    f"{membership_count} clusters (expected 1)"
                )
        return violations

    def _audit_leader_membership(self) -> List[str]:
        violations: List[str] = []
        for cluster_id, leader_id in self._leaders.items():
            if leader_id is None:
                continue
            if leader_id not in self._clusters.get(cluster_id, set()):
                violations.append(
                    f"I-7 VIOLATED: leader '{leader_id}' of cluster "
                    f"'{cluster_id}' is not in _clusters['{cluster_id}']"
                )
        return violations

    def _audit_follower_no_children(self) -> List[str]:
        violations: List[str] = []
        for drone_id, node in self._nodes.items():
            if node.role is SwarmRole.FOLLOWER:
                children = self._children.get(drone_id, set())
                if children:
                    violations.append(
                        f"I-4 VIOLATED: FOLLOWER '{drone_id}' has "
                        f"children: {children}"
                    )
        return violations

    def __repr__(self) -> str:
        return (
            f"SwarmTopology(nodes={len(self._nodes)}, "
            f"clusters={list(self._clusters.keys())}, "
            f"root={self._root!r}, version={self._version})"
        )
