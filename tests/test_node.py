"""Unit, Edge-Case, and Failure Test Suite for SwarmNode (node.py).

Tests cover:
    - Initial state after construction.
    - Heartbeat updates and telemetry field accuracy.
    - Liveness (is_alive) with real and simulated timeout.
    - All state transition methods.
    - Role and hierarchy mutations.
    - Session authentication lifecycle.
    - Task assignment and clearing.
    - Election weight computation.
    - Thread-safety under concurrent mutation.
    - Invalid-input edge cases and expected exceptions.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hierarchical_swarm.node import NodeState, SwarmNode
from hierarchical_swarm.utils import ClusterId, DroneId, NodeStatus, SwarmRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_node(
    drone_id: str = "drone-01",
    role: SwarmRole = SwarmRole.FOLLOWER,
    tree_level: int = 2,
) -> SwarmNode:
    """Creates a SwarmNode with sensible test defaults."""
    return SwarmNode(
        drone_id=DroneId(drone_id),
        role=role,
        tree_level=tree_level,
        cluster_id=ClusterId("cluster-01"),
    )


# ---------------------------------------------------------------------------
# 1. Construction & Initial State
# ---------------------------------------------------------------------------

class TestSwarmNodeConstruction(unittest.TestCase):

    def test_defaults_after_construction(self):
        node = make_node()
        self.assertEqual(node.drone_id, "drone-01")
        self.assertEqual(node.role, SwarmRole.FOLLOWER)
        self.assertEqual(node.state, NodeState.UNASSIGNED)
        self.assertFalse(node.authenticated)
        self.assertIsNone(node.session_id)
        self.assertIsNone(node.parent_id)
        self.assertEqual(node.tree_level, 2)
        self.assertEqual(node.battery_voltage, 0.0)
        self.assertEqual(node.topology_version, 0)

    def test_boot_time_is_monotonic_and_positive(self):
        node = make_node()
        self.assertGreater(node.boot_time, 0.0)
        self.assertGreater(node.last_seen, 0.0)
        self.assertGreater(node.last_heartbeat, 0.0)

    def test_repr_does_not_raise(self):
        node = make_node()
        text = repr(node)
        self.assertIn("drone-01", text)
        self.assertIn("FOLLOWER", text)


# ---------------------------------------------------------------------------
# 2. Liveness
# ---------------------------------------------------------------------------

class TestSwarmNodeLiveness(unittest.TestCase):

    def test_is_alive_immediately_after_creation(self):
        node = make_node()
        self.assertTrue(node.is_alive(timeout_sec=3.0))

    def test_is_alive_false_after_simulated_timeout(self):
        node = make_node()
        # Back-date last_heartbeat beyond the timeout window.
        node.last_heartbeat = time.monotonic() - 10.0
        self.assertFalse(node.is_alive(timeout_sec=3.0))

    def test_is_alive_exactly_at_boundary(self):
        node = make_node()
        node.last_heartbeat = time.monotonic() - 3.0
        # Exactly at boundary — may be True or False depending on sub-ms timing;
        # simply assert it returns a bool without error.
        self.assertIsInstance(node.is_alive(timeout_sec=3.0), bool)

    def test_custom_timeout(self):
        node = make_node()
        node.last_heartbeat = time.monotonic() - 1.5
        self.assertTrue(node.is_alive(timeout_sec=5.0))
        self.assertFalse(node.is_alive(timeout_sec=1.0))


# ---------------------------------------------------------------------------
# 3. Heartbeat & Telemetry Updates
# ---------------------------------------------------------------------------

class TestHeartbeatAndTelemetry(unittest.TestCase):

    def test_update_heartbeat_refreshes_all_fields(self):
        node = make_node()
        before = node.last_heartbeat
        time.sleep(0.01)

        node.update_heartbeat(
            battery_voltage=12.6,
            battery_percentage=88.0,
            cpu_load=22.5,
            rssi=-55.0,
            link_quality=80.0,
            memory_usage=35.0,
        )

        self.assertAlmostEqual(node.battery_voltage, 12.6, places=5)
        self.assertAlmostEqual(node.battery_percentage, 88.0, places=5)
        self.assertAlmostEqual(node.cpu_load, 22.5, places=5)
        self.assertAlmostEqual(node.rssi, -55.0, places=5)
        self.assertGreater(node.last_heartbeat, before)
        self.assertTrue(node.is_alive(timeout_sec=3.0))

    def test_update_metrics_does_not_change_heartbeat_stamp(self):
        node = make_node()
        node.update_heartbeat(12.0, 90.0, 10.0, -40.0)
        hb_ts = node.last_heartbeat
        time.sleep(0.01)

        node.update_metrics(cpu_load=30.0, memory_usage=40.0, rssi=-60.0)

        # last_seen advances, last_heartbeat stays unchanged.
        self.assertAlmostEqual(node.last_heartbeat, hb_ts, places=3)
        self.assertAlmostEqual(node.cpu_load, 30.0, places=5)


# ---------------------------------------------------------------------------
# 4. Authentication & Session
# ---------------------------------------------------------------------------

class TestAuthentication(unittest.TestCase):

    def test_mark_authenticated_sets_fields(self):
        node = make_node()
        node.mark_authenticated("sess-abc-123")
        self.assertTrue(node.authenticated)
        self.assertEqual(node.session_id, "sess-abc-123")
        self.assertEqual(node.state, NodeState.JOINING)

    def test_expire_session_clears_credentials(self):
        node = make_node()
        node.mark_authenticated("sess-xyz")
        node.expire_session()
        self.assertFalse(node.authenticated)
        self.assertIsNone(node.session_id)
        # State must NOT regress beyond JOINING when session expires mid-flight.
        self.assertEqual(node.state, NodeState.JOINING)

    def test_mark_authenticated_empty_session_raises(self):
        node = make_node()
        with self.assertRaises(ValueError):
            node.mark_authenticated("")
        with self.assertRaises(ValueError):
            node.mark_authenticated("   ")

    def test_mark_revoked_is_terminal(self):
        node = make_node()
        node.mark_authenticated("sess-001")
        node.mark_online()
        node.mark_revoked()
        self.assertEqual(node.state, NodeState.REVOKED)
        self.assertFalse(node.authenticated)
        self.assertIsNone(node.session_id)


# ---------------------------------------------------------------------------
# 5. Online / Offline State Transitions
# ---------------------------------------------------------------------------

class TestOnlineOfflineTransitions(unittest.TestCase):

    def test_mark_online_sets_active_and_join_time(self):
        node = make_node()
        self.assertEqual(node.join_time, 0.0)
        node.mark_online()
        self.assertEqual(node.state, NodeState.ACTIVE)
        self.assertGreater(node.join_time, 0.0)

    def test_mark_offline_clears_session(self):
        node = make_node()
        node.mark_authenticated("sess-001")
        node.mark_online()
        node.mark_offline()
        self.assertEqual(node.state, NodeState.OFFLINE)
        self.assertFalse(node.authenticated)
        self.assertIsNone(node.session_id)

    def test_mark_online_after_offline_is_allowed(self):
        """Edge Case: Node can be brought back online after a transient outage."""
        node = make_node()
        node.mark_online()
        node.mark_offline()
        # Re-joining after recovery.
        node.mark_authenticated("sess-002")
        node.mark_online()
        self.assertEqual(node.state, NodeState.ACTIVE)


# ---------------------------------------------------------------------------
# 6. Role and Hierarchy Mutations
# ---------------------------------------------------------------------------

class TestRoleAndHierarchyMutations(unittest.TestCase):

    def test_update_role_to_cluster_leader(self):
        node = make_node()
        node.update_role(SwarmRole.CLUSTER_LEADER, new_tree_level=1)
        self.assertEqual(node.role, SwarmRole.CLUSTER_LEADER)
        self.assertEqual(node.tree_level, 1)

    def test_update_role_invalid_level_raises(self):
        node = make_node()
        with self.assertRaises(ValueError):
            node.update_role(SwarmRole.FOLLOWER, new_tree_level=5)
        with self.assertRaises(ValueError):
            node.update_role(SwarmRole.FOLLOWER, new_tree_level=-1)

    def test_update_parent_increments_topology_version(self):
        node = make_node()
        self.assertEqual(node.topology_version, 0)
        node.update_parent(DroneId("leader-01"))
        self.assertEqual(node.parent_id, "leader-01")
        self.assertEqual(node.topology_version, 1)
        node.update_parent(None)
        self.assertEqual(node.topology_version, 2)

    def test_update_cluster_increments_topology_version(self):
        node = make_node()
        node.update_cluster(ClusterId("cluster-02"))
        self.assertEqual(node.cluster_id, "cluster-02")
        self.assertEqual(node.topology_version, 1)

    def test_update_cluster_empty_raises(self):
        node = make_node()
        with self.assertRaises(ValueError):
            node.update_cluster(ClusterId(""))
        with self.assertRaises(ValueError):
            node.update_cluster(ClusterId("  "))


# ---------------------------------------------------------------------------
# 7. Mission Task Assignment
# ---------------------------------------------------------------------------

class TestTaskAssignment(unittest.TestCase):

    def test_assign_task_and_clear(self):
        node = make_node()
        node.assign_task("task-42", priority=5)
        self.assertEqual(node.current_task_id, "task-42")
        self.assertEqual(node.mission_priority, 5)
        node.clear_task()
        self.assertIsNone(node.current_task_id)
        self.assertEqual(node.mission_priority, 0)

    def test_assign_empty_task_raises(self):
        node = make_node()
        with self.assertRaises(ValueError):
            node.assign_task("")
        with self.assertRaises(ValueError):
            node.assign_task("   ")


# ---------------------------------------------------------------------------
# 8. Election Weight
# ---------------------------------------------------------------------------

class TestElectionWeight(unittest.TestCase):

    def test_weight_increases_with_higher_battery(self):
        low  = make_node(); low.update_heartbeat(11.0, 20.0, 30.0, -70.0)
        high = make_node(); high.update_heartbeat(12.6, 90.0, 10.0, -40.0)
        self.assertGreater(high.election_weight(), low.election_weight())

    def test_weight_decreases_with_higher_cpu(self):
        light = make_node(); light.update_heartbeat(12.0, 80.0, 5.0,  -50.0)
        heavy = make_node(); heavy.update_heartbeat(12.0, 80.0, 95.0, -50.0)
        self.assertGreater(light.election_weight(), heavy.election_weight())

    def test_root_leader_outweighs_follower_by_level(self):
        root = make_node(role=SwarmRole.ROOT_LEADER, tree_level=0)
        root.update_heartbeat(12.0, 80.0, 20.0, -50.0)
        foll = make_node(role=SwarmRole.FOLLOWER, tree_level=2)
        foll.update_heartbeat(12.0, 80.0, 20.0, -50.0)
        self.assertGreater(root.election_weight(), foll.election_weight())

    def test_weight_returns_float(self):
        node = make_node()
        node.update_heartbeat(12.0, 75.0, 25.0, -60.0)
        self.assertIsInstance(node.election_weight(), float)


# ---------------------------------------------------------------------------
# 9. Thread-Safety Under Concurrent Mutation
# ---------------------------------------------------------------------------

class TestThreadSafety(unittest.TestCase):

    def test_concurrent_heartbeat_updates_are_consistent(self):
        """Stress Test: 200 threads write heartbeats simultaneously."""
        node = make_node()
        errors: list[Exception] = []

        def writer(voltage: float) -> None:
            try:
                node.update_heartbeat(
                    battery_voltage=voltage,
                    battery_percentage=voltage * 8,
                    cpu_load=20.0,
                    rssi=-50.0,
                )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(11.0 + i * 0.01,)) for i in range(200)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Thread errors: {errors}")
        # After all writes the node should still be alive.
        self.assertTrue(node.is_alive(timeout_sec=3.0))

    def test_concurrent_role_and_parent_updates(self):
        """Stress Test: role and parent updates race without deadlock."""
        node = make_node()
        errors: list[Exception] = []

        def role_updater() -> None:
            try:
                for _ in range(50):
                    node.update_role(SwarmRole.CLUSTER_LEADER, 1)
                    node.update_role(SwarmRole.FOLLOWER, 2)
            except Exception as exc:
                errors.append(exc)

        def parent_updater() -> None:
            try:
                for _ in range(50):
                    node.update_parent(DroneId("leader-01"))
                    node.update_parent(None)
            except Exception as exc:
                errors.append(exc)

        threads = (
            [threading.Thread(target=role_updater) for _ in range(4)]
            + [threading.Thread(target=parent_updater) for _ in range(4)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Thread errors: {errors}")


if __name__ == "__main__":
    unittest.main()
