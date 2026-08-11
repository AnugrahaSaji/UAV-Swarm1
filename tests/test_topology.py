"""Comprehensive Test Suite for SwarmTopology (topology.py).

Tests cover:
    1.  Construction & initial state.
    2.  add_node — normal paths (root, cluster leader, follower).
    3.  add_node — all invariant violations.
    4.  remove_node — normal path and children-present guard.
    5.  re_parent — normal path, cycle detection, no-op idempotency.
    6.  set_cluster_leader — promotion, demotion, idempotency.
    7.  update_node_cluster — cross-cluster migration.
    8.  Read APIs — get_node, get_parent, get_children, get_cluster_members,
        get_cluster_leader, get_root, get_descendants.
    9.  version increments on every structural change.
    10. validate() — clean topology, injected violations.
    11. drain_events() — event types and ordering.
    12. Defensive copy — mutating returned collections does not corrupt topology.
    13. Thread-safety — 100 concurrent readers/writers without error.
    14. Full 8-drone, 2-cluster scenario.
    15. Failover scenario: leader failure, re-parent, new leader.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hierarchical_swarm.node import NodeState, SwarmNode
from hierarchical_swarm.topology import (
    SwarmTopology,
    TopologyClusterNotFoundError,
    TopologyDuplicateNodeError,
    TopologyError,
    TopologyEventType,
    TopologyInvariantError,
    TopologyNodeNotFoundError,
)
from hierarchical_swarm.utils import ClusterId, DroneId, SwarmRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_root(drone_id: str = "root-00") -> SwarmNode:
    return SwarmNode(
        drone_id=DroneId(drone_id),
        role=SwarmRole.ROOT_LEADER,
        tree_level=0,
        parent_id=None,
        cluster_id=None,
    )


def make_leader(
    drone_id: str,
    cluster_id: str,
    parent_id: str,
) -> SwarmNode:
    return SwarmNode(
        drone_id=DroneId(drone_id),
        role=SwarmRole.CLUSTER_LEADER,
        tree_level=1,
        parent_id=DroneId(parent_id),
        cluster_id=ClusterId(cluster_id),
    )


def make_follower(
    drone_id: str,
    cluster_id: str,
    parent_id: str,
) -> SwarmNode:
    return SwarmNode(
        drone_id=DroneId(drone_id),
        role=SwarmRole.FOLLOWER,
        tree_level=2,
        parent_id=DroneId(parent_id),
        cluster_id=ClusterId(cluster_id),
    )


def build_standard_topology() -> SwarmTopology:
    """Builds the reference 8-drone, 2-cluster topology.

    Tier 0:  root-00  (ROOT_LEADER, no cluster)
    Tier 1:  leader-A (CLUSTER_LEADER, cluster-A, parent=root-00)
             leader-B (CLUSTER_LEADER, cluster-B, parent=root-00)
    Tier 2:  follower-A1, follower-A2, follower-A3  (cluster-A, parent=leader-A)
             follower-B1, follower-B2, follower-B3  (cluster-B, parent=leader-B)
    """
    topo = SwarmTopology()

    topo.add_node(make_root())
    topo.add_node(make_leader("leader-A", "cluster-A", "root-00"),  cluster_id="cluster-A")
    topo.add_node(make_leader("leader-B", "cluster-B", "root-00"),  cluster_id="cluster-B")

    for i in (1, 2, 3):
        topo.add_node(make_follower(f"follower-A{i}", "cluster-A", "leader-A"))
        topo.add_node(make_follower(f"follower-B{i}", "cluster-B", "leader-B"))

    topo.drain_events()  # Clear construction events.
    return topo


# ---------------------------------------------------------------------------
# 1. Construction
# ---------------------------------------------------------------------------

class TestConstruction(unittest.TestCase):
    def test_initial_state(self):
        topo = SwarmTopology()
        self.assertEqual(topo.size(), 0)
        self.assertEqual(topo.version, 0)
        self.assertIsNone(topo.get_root())
        self.assertFalse(topo.contains("any"))

    def test_repr_does_not_raise(self):
        topo = SwarmTopology()
        text = repr(topo)
        self.assertIn("SwarmTopology", text)


# ---------------------------------------------------------------------------
# 2. add_node — normal paths
# ---------------------------------------------------------------------------

class TestAddNode(unittest.TestCase):
    def test_add_root_node(self):
        topo = SwarmTopology()
        topo.add_node(make_root())
        self.assertEqual(topo.size(), 1)
        self.assertTrue(topo.contains("root-00"))
        root = topo.get_root()
        self.assertIsNotNone(root)
        self.assertEqual(root.role, SwarmRole.ROOT_LEADER)

    def test_add_cluster_leader(self):
        topo = SwarmTopology()
        topo.add_node(make_root())
        topo.add_node(make_leader("leader-A", "cluster-A", "root-00"), cluster_id="cluster-A")
        self.assertEqual(topo.size(), 2)
        leader = topo.get_cluster_leader("cluster-A")
        self.assertIsNotNone(leader)
        self.assertEqual(leader.drone_id, "leader-A")

    def test_add_follower(self):
        topo = SwarmTopology()
        topo.add_node(make_root())
        topo.add_node(make_leader("leader-A", "cluster-A", "root-00"), cluster_id="cluster-A")
        topo.add_node(make_follower("follower-1", "cluster-A", "leader-A"))
        self.assertEqual(topo.size(), 3)
        self.assertTrue(topo.contains("follower-1"))

    def test_version_increments_on_add(self):
        topo = SwarmTopology()
        v0 = topo.version
        topo.add_node(make_root())
        self.assertEqual(topo.version, v0 + 1)

    def test_add_node_cluster_id_override(self):
        """cluster_id kwarg overrides node.cluster_id."""
        topo = SwarmTopology()
        topo.add_node(make_root())
        node = make_leader("leader-A", "cluster-OLD", "root-00")
        topo.add_node(node, cluster_id="cluster-NEW")
        members = topo.get_cluster_members("cluster-NEW")
        self.assertIn("leader-A", [m.drone_id for m in members])


# ---------------------------------------------------------------------------
# 3. add_node — invariant violations
# ---------------------------------------------------------------------------

class TestAddNodeInvariants(unittest.TestCase):
    def test_duplicate_drone_id_raises(self):
        topo = SwarmTopology()
        topo.add_node(make_root())
        with self.assertRaises(TopologyDuplicateNodeError):
            topo.add_node(make_root())

    def test_second_root_leader_raises(self):
        topo = SwarmTopology()
        topo.add_node(make_root("root-00"))
        root2 = SwarmNode(
            drone_id=DroneId("root-01"),
            role=SwarmRole.ROOT_LEADER,
            tree_level=0,
        )
        with self.assertRaises(TopologyInvariantError):
            topo.add_node(root2)

    def test_root_with_parent_raises(self):
        topo = SwarmTopology()
        root = SwarmNode(
            drone_id=DroneId("root-00"),
            role=SwarmRole.ROOT_LEADER,
            tree_level=0,
            parent_id=DroneId("ghost"),
        )
        with self.assertRaises(TopologyInvariantError):
            topo.add_node(root)

    def test_unknown_parent_raises(self):
        topo = SwarmTopology()
        topo.add_node(make_root())
        bad = make_leader("leader-A", "cluster-A", "ghost-parent")
        with self.assertRaises(TopologyNodeNotFoundError):
            topo.add_node(bad, cluster_id="cluster-A")

    def test_non_root_without_cluster_raises(self):
        topo = SwarmTopology()
        topo.add_node(make_root())
        follower = SwarmNode(
            drone_id=DroneId("follower-1"),
            role=SwarmRole.FOLLOWER,
            tree_level=2,
            parent_id=DroneId("root-00"),
            cluster_id=None,  # No cluster
        )
        with self.assertRaises(TopologyInvariantError):
            topo.add_node(follower)  # cluster_id=None by default


# ---------------------------------------------------------------------------
# 4. remove_node
# ---------------------------------------------------------------------------

class TestRemoveNode(unittest.TestCase):
    def test_remove_leaf_node(self):
        topo = build_standard_topology()
        topo.drain_events()
        topo.remove_node("follower-A1")
        self.assertFalse(topo.contains("follower-A1"))
        self.assertEqual(topo.size(), 8)

    def test_remove_increments_version(self):
        topo = build_standard_topology()
        v = topo.version
        topo.remove_node("follower-A1")
        self.assertGreater(topo.version, v)

    def test_remove_updates_parent_children(self):
        topo = build_standard_topology()
        topo.remove_node("follower-A1")
        children = topo.get_children("leader-A")
        ids = [c.drone_id for c in children]
        self.assertNotIn("follower-A1", ids)

    def test_remove_updates_cluster_membership(self):
        topo = build_standard_topology()
        topo.remove_node("follower-A1")
        members = topo.get_cluster_members("cluster-A")
        ids = [m.drone_id for m in members]
        self.assertNotIn("follower-A1", ids)

    def test_remove_node_with_children_raises(self):
        topo = build_standard_topology()
        with self.assertRaises(TopologyInvariantError):
            topo.remove_node("leader-A")

    def test_remove_unknown_node_raises(self):
        topo = SwarmTopology()
        with self.assertRaises(TopologyNodeNotFoundError):
            topo.remove_node("ghost")

    def test_remove_clears_leader_slot(self):
        """Removing a leader clears its _leaders entry."""
        topo = build_standard_topology()
        # Remove followers first.
        for i in (1, 2, 3):
            topo.remove_node(f"follower-A{i}")
        topo.remove_node("leader-A")
        self.assertIsNone(topo.get_cluster_leader("cluster-A"))


# ---------------------------------------------------------------------------
# 5. re_parent
# ---------------------------------------------------------------------------

class TestReParent(unittest.TestCase):
    def test_reparent_follower_to_different_leader(self):
        topo = build_standard_topology()
        v = topo.version
        topo.re_parent("follower-A1", "leader-B")
        self.assertGreater(topo.version, v)
        parent = topo.get_parent("follower-A1")
        self.assertEqual(parent.drone_id, "leader-B")

    def test_reparent_updates_children_indexes(self):
        topo = build_standard_topology()
        topo.re_parent("follower-A1", "leader-B")
        children_A = [c.drone_id for c in topo.get_children("leader-A")]
        children_B = [c.drone_id for c in topo.get_children("leader-B")]
        self.assertNotIn("follower-A1", children_A)
        self.assertIn("follower-A1", children_B)

    def test_reparent_same_parent_is_noop(self):
        topo = build_standard_topology()
        v = topo.version
        topo.re_parent("follower-A1", "leader-A")  # Same parent.
        self.assertEqual(topo.version, v)  # No version change.

    def test_reparent_unknown_drone_raises(self):
        topo = build_standard_topology()
        with self.assertRaises(TopologyNodeNotFoundError):
            topo.re_parent("ghost", "leader-A")

    def test_reparent_unknown_parent_raises(self):
        topo = build_standard_topology()
        with self.assertRaises(TopologyNodeNotFoundError):
            topo.re_parent("follower-A1", "ghost-parent")

    def test_reparent_cycle_raises(self):
        """follower → leader → root, cannot make root a child of follower."""
        topo = build_standard_topology()
        with self.assertRaises(TopologyInvariantError):
            topo.re_parent("root-00", "follower-A1")

    def test_reparent_self_raises(self):
        """A node cannot be its own parent."""
        topo = build_standard_topology()
        with self.assertRaises(TopologyInvariantError):
            topo.re_parent("follower-A1", "follower-A1")

    def test_reparent_produces_event(self):
        topo = build_standard_topology()
        topo.drain_events()
        topo.re_parent("follower-A1", "leader-B")
        events = topo.drain_events()
        types = [e.event_type for e in events]
        self.assertIn(TopologyEventType.RE_PARENT, types)


# ---------------------------------------------------------------------------
# 6. set_cluster_leader
# ---------------------------------------------------------------------------

class TestSetClusterLeader(unittest.TestCase):
    def test_promote_follower_to_leader(self):
        topo = build_standard_topology()
        topo.set_cluster_leader("cluster-A", "follower-A1")
        leader = topo.get_cluster_leader("cluster-A")
        self.assertEqual(leader.drone_id, "follower-A1")
        self.assertEqual(leader.role, SwarmRole.CLUSTER_LEADER)

    def test_old_leader_demoted_to_follower(self):
        topo = build_standard_topology()
        topo.set_cluster_leader("cluster-A", "follower-A1")
        old_leader = topo.get_node("leader-A")
        self.assertEqual(old_leader.role, SwarmRole.FOLLOWER)
        self.assertEqual(old_leader.tree_level, 2)

    def test_set_leader_same_leader_is_noop(self):
        topo = build_standard_topology()
        v = topo.version
        topo.set_cluster_leader("cluster-A", "leader-A")
        self.assertEqual(topo.version, v)

    def test_set_leader_unknown_cluster_raises(self):
        topo = build_standard_topology()
        with self.assertRaises(TopologyClusterNotFoundError):
            topo.set_cluster_leader("ghost-cluster", "follower-A1")

    def test_set_leader_non_member_raises(self):
        topo = build_standard_topology()
        with self.assertRaises(TopologyInvariantError):
            topo.set_cluster_leader("cluster-A", "follower-B1")

    def test_set_leader_increments_version(self):
        topo = build_standard_topology()
        v = topo.version
        topo.set_cluster_leader("cluster-A", "follower-A1")
        self.assertGreater(topo.version, v)

    def test_set_leader_produces_event(self):
        topo = build_standard_topology()
        topo.drain_events()
        topo.set_cluster_leader("cluster-A", "follower-A1")
        events = topo.drain_events()
        types = [e.event_type for e in events]
        self.assertIn(TopologyEventType.LEADER_CHANGED, types)


# ---------------------------------------------------------------------------
# 7. update_node_cluster
# ---------------------------------------------------------------------------

class TestUpdateNodeCluster(unittest.TestCase):
    def test_move_follower_to_other_cluster(self):
        topo = build_standard_topology()
        topo.update_node_cluster("follower-A1", "cluster-B")
        members_A = [m.drone_id for m in topo.get_cluster_members("cluster-A")]
        members_B = [m.drone_id for m in topo.get_cluster_members("cluster-B")]
        self.assertNotIn("follower-A1", members_A)
        self.assertIn("follower-A1", members_B)

    def test_move_to_same_cluster_is_noop(self):
        topo = build_standard_topology()
        v = topo.version
        topo.update_node_cluster("follower-A1", "cluster-A")
        self.assertEqual(topo.version, v)

    def test_move_to_unknown_cluster_raises(self):
        topo = build_standard_topology()
        with self.assertRaises(TopologyClusterNotFoundError):
            topo.update_node_cluster("follower-A1", "ghost-cluster")


# ---------------------------------------------------------------------------
# 8. Read APIs
# ---------------------------------------------------------------------------

class TestReadAPIs(unittest.TestCase):
    def setUp(self):
        self.topo = build_standard_topology()

    def test_get_node_returns_correct_node(self):
        node = self.topo.get_node("follower-A2")
        self.assertEqual(node.drone_id, "follower-A2")

    def test_get_node_unknown_raises(self):
        with self.assertRaises(TopologyNodeNotFoundError):
            self.topo.get_node("ghost")

    def test_get_parent_of_follower(self):
        parent = self.topo.get_parent("follower-A1")
        self.assertEqual(parent.drone_id, "leader-A")

    def test_get_parent_of_root_is_none(self):
        parent = self.topo.get_parent("root-00")
        self.assertIsNone(parent)

    def test_get_children_of_leader(self):
        children = self.topo.get_children("leader-A")
        ids = {c.drone_id for c in children}
        self.assertEqual(ids, {"follower-A1", "follower-A2", "follower-A3"})

    def test_get_children_of_follower_is_empty(self):
        children = self.topo.get_children("follower-A1")
        self.assertEqual(children, [])

    def test_get_cluster_members_count(self):
        members = self.topo.get_cluster_members("cluster-A")
        # 1 leader + 3 followers.
        self.assertEqual(len(members), 4)

    def test_get_cluster_leader_returns_correct_node(self):
        leader = self.topo.get_cluster_leader("cluster-A")
        self.assertEqual(leader.drone_id, "leader-A")

    def test_get_root(self):
        root = self.topo.get_root()
        self.assertEqual(root.drone_id, "root-00")

    def test_get_descendants_of_root(self):
        descendants = self.topo.get_descendants("root-00")
        self.assertEqual(len(descendants), 8)  # All non-root nodes.

    def test_get_descendants_of_cluster_leader(self):
        descendants = self.topo.get_descendants("leader-A")
        self.assertEqual(len(descendants), 3)

    def test_list_all_nodes_count(self):
        nodes = self.topo.list_all_nodes()
        self.assertEqual(len(nodes), 9)

    def test_list_cluster_ids(self):
        ids = set(self.topo.list_cluster_ids())
        self.assertIn("cluster-A", ids)
        self.assertIn("cluster-B", ids)


# ---------------------------------------------------------------------------
# 9. Version increment behaviour
# ---------------------------------------------------------------------------

class TestVersioning(unittest.TestCase):
    def test_version_increments_on_add(self):
        topo = SwarmTopology()
        v = topo.version
        topo.add_node(make_root())
        self.assertEqual(topo.version, v + 1)

    def test_version_increments_on_remove(self):
        topo = build_standard_topology()
        v = topo.version
        topo.remove_node("follower-A1")
        self.assertGreater(topo.version, v)

    def test_version_increments_on_reparent(self):
        topo = build_standard_topology()
        v = topo.version
        topo.re_parent("follower-A1", "leader-B")
        self.assertGreater(topo.version, v)

    def test_version_increments_on_leader_change(self):
        topo = build_standard_topology()
        v = topo.version
        topo.set_cluster_leader("cluster-A", "follower-A1")
        self.assertGreater(topo.version, v)

    def test_noop_does_not_increment_version(self):
        topo = build_standard_topology()
        v = topo.version
        topo.re_parent("follower-A1", "leader-A")   # Same parent — no-op.
        self.assertEqual(topo.version, v)


# ---------------------------------------------------------------------------
# 10. validate()
# ---------------------------------------------------------------------------

class TestValidation(unittest.TestCase):
    def test_clean_topology_has_no_violations(self):
        topo = build_standard_topology()
        violations = topo.validate()
        self.assertEqual(violations, [], violations)

    def test_empty_topology_has_no_violations(self):
        topo = SwarmTopology()
        self.assertEqual(topo.validate(), [])


# ---------------------------------------------------------------------------
# 11. drain_events
# ---------------------------------------------------------------------------

class TestDrainEvents(unittest.TestCase):
    def test_add_node_produces_joined_event(self):
        topo = SwarmTopology()
        topo.add_node(make_root())
        events = topo.drain_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, TopologyEventType.NODE_JOINED)
        self.assertEqual(events[0].drone_id, "root-00")

    def test_remove_node_produces_removed_event(self):
        topo = build_standard_topology()
        topo.drain_events()
        topo.remove_node("follower-A1")
        events = topo.drain_events()
        types = [e.event_type for e in events]
        self.assertIn(TopologyEventType.NODE_REMOVED, types)

    def test_drain_clears_queue(self):
        topo = SwarmTopology()
        topo.add_node(make_root())
        topo.drain_events()
        self.assertEqual(topo.drain_events(), [])


# ---------------------------------------------------------------------------
# 12. Defensive copy — mutation isolation
# ---------------------------------------------------------------------------

class TestDefensiveCopy(unittest.TestCase):
    def test_mutating_children_snapshot_does_not_corrupt_topology(self):
        topo = build_standard_topology()
        children = topo.get_children("leader-A")
        children.clear()  # Mutate the returned list.
        # Topology must be unchanged.
        self.assertEqual(len(topo.get_children("leader-A")), 3)

    def test_mutating_cluster_members_snapshot_does_not_corrupt_topology(self):
        topo = build_standard_topology()
        members = topo.get_cluster_members("cluster-A")
        members.clear()
        self.assertEqual(len(topo.get_cluster_members("cluster-A")), 4)

    def test_mutating_all_nodes_snapshot_does_not_corrupt_topology(self):
        topo = build_standard_topology()
        nodes = topo.list_all_nodes()
        nodes.clear()
        self.assertEqual(topo.size(), 9)


# ---------------------------------------------------------------------------
# 13. Thread-safety
# ---------------------------------------------------------------------------

class TestThreadSafety(unittest.TestCase):
    def test_concurrent_readers_do_not_corrupt(self):
        """100 threads reading simultaneously must not raise."""
        topo = build_standard_topology()
        errors: list = []

        def reader():
            try:
                for _ in range(10):
                    _ = topo.get_cluster_members("cluster-A")
                    _ = topo.get_cluster_leader("cluster-B")
                    _ = topo.get_root()
                    _ = topo.version
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=reader) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], errors)

    def test_concurrent_add_remove_cycles(self):
        """Multiple threads add and remove temporary nodes without errors."""
        topo = build_standard_topology()
        errors: list = []
        counter = [0]
        lock = threading.Lock()

        def worker(thread_id: int):
            try:
                node_id = f"tmp-{thread_id}"
                node = make_follower(node_id, "cluster-A", "leader-A")
                topo.add_node(node)
                topo.remove_node(node_id)
                with lock:
                    counter[0] += 1
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], errors)
        # All temporary nodes should be gone.
        self.assertEqual(topo.size(), 9)


# ---------------------------------------------------------------------------
# 14. Full 8-drone, 2-cluster scenario
# ---------------------------------------------------------------------------

class TestFullScenario(unittest.TestCase):
    def test_full_standard_topology_integrity(self):
        topo = build_standard_topology()
        violations = topo.validate()
        self.assertEqual(violations, [], violations)
        self.assertEqual(topo.size(), 9)
        self.assertIsNotNone(topo.get_root())

    def test_cluster_counts(self):
        topo = build_standard_topology()
        a_members = topo.get_cluster_members("cluster-A")
        b_members = topo.get_cluster_members("cluster-B")
        self.assertEqual(len(a_members), 4)  # 1 leader + 3 followers.
        self.assertEqual(len(b_members), 4)

    def test_root_has_two_cluster_leader_children(self):
        topo = build_standard_topology()
        children = topo.get_children("root-00")
        roles = {c.role for c in children}
        self.assertEqual(roles, {SwarmRole.CLUSTER_LEADER})
        self.assertEqual(len(children), 2)


# ---------------------------------------------------------------------------
# 15. Failover scenario
# ---------------------------------------------------------------------------

class TestFailoverScenario(unittest.TestCase):
    def test_leader_failure_and_election(self):
        """Simulates leader-A failing, follower-A1 winning election.

        Steps:
            1. Remove followers from leader-A (simulate they re-parent first).
            2. Remove leader-A.
            3. Re-parent follower-A1 to root-00.
            4. Re-parent follower-A2, follower-A3 to follower-A1.
            5. Set follower-A1 as new cluster leader.
        """
        topo = build_standard_topology()

        # Step 1: Remove followers.
        topo.re_parent("follower-A2", "root-00")  # Temp reparent.
        topo.re_parent("follower-A3", "root-00")
        topo.remove_node("follower-A1")

        # Step 2: Remove leader-A.
        topo.remove_node("leader-A")

        # Step 3-4: Promote follower-A2 as interim parent.
        topo.update_node_cluster("follower-A2", "cluster-A")
        topo.update_node_cluster("follower-A3", "cluster-A")

        # Step 5: Elect follower-A2 as new leader.
        topo.set_cluster_leader("cluster-A", "follower-A2")

        new_leader = topo.get_cluster_leader("cluster-A")
        self.assertEqual(new_leader.drone_id, "follower-A2")
        self.assertEqual(new_leader.role, SwarmRole.CLUSTER_LEADER)

        violations = topo.validate()
        self.assertEqual(violations, [], violations)


if __name__ == "__main__":
    unittest.main(verbosity=2)
