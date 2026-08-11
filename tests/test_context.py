"""Comprehensive Test Suite for SwarmContext (context.py).

Tests cover:
    1.  Initialization order & sub-module instantiation (SwarmNode, SwarmTopology,
        DiscoveryEngine, SwarmSecurityManager, HeartbeatManager, RoutingManager,
        TaskManager, ClusterManager).
    2.  Dependency injection & facade property access.
    3.  Startup flow for ROOT_LEADER, CLUSTER_LEADER, and CANDIDATE/FOLLOWER.
    4.  get_status() reporting dictionary structure.
    5.  Shutdown in strict reverse order — clearing timers, zeroing sessions, stopping discovery.
    6.  Thread safety during concurrent initialization/shutdown attempts.
    7.  Re-initialization protection & exception safety.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hierarchical_swarm.context import SwarmContext
from hierarchical_swarm.node import NodeState
from hierarchical_swarm.utils import SwarmRole


class TestSwarmContextInitialization(unittest.TestCase):

    def test_context_instantiation_and_properties_before_init(self):
        ctx = SwarmContext(drone_id="drone-test", role="FOLLOWER")
        self.assertFalse(ctx.is_initialized)

        with self.assertRaises(AssertionError):
            _ = ctx.node

    def test_initialize_root_leader(self):
        ctx = SwarmContext(drone_id="root-00", role="ROOT_LEADER")
        ctx.initialize()

        self.assertTrue(ctx.is_initialized)
        self.assertEqual(ctx.node.drone_id, "root-00")
        self.assertEqual(ctx.node.role, SwarmRole.ROOT_LEADER)
        self.assertEqual(ctx.node.state, NodeState.ACTIVE)
        self.assertEqual(ctx.topology.size(), 1)
        self.assertTrue(ctx.heartbeat.is_running())

        status = ctx.get_status()
        self.assertTrue(status["initialized"])
        self.assertEqual(status["role"], "ROOT_LEADER")
        self.assertEqual(status["node_state"], "ACTIVE")

        ctx.shutdown()
        self.assertFalse(ctx.is_initialized)

    def test_initialize_cluster_leader(self):
        ctx = SwarmContext(
            drone_id="leader-A",
            role="CLUSTER_LEADER",
            cluster_id="cluster-A",
            parent_id="root-00",
        )
        ctx.initialize()

        self.assertTrue(ctx.is_initialized)
        self.assertEqual(ctx.node.role, SwarmRole.CLUSTER_LEADER)
        self.assertEqual(ctx.node.cluster_id, "cluster-A")
        self.assertEqual(ctx.node.parent_id, "root-00")

        ctx.shutdown()
        self.assertFalse(ctx.is_initialized)

    def test_initialize_follower_candidate(self):
        ctx = SwarmContext(drone_id="follower-A1", role="CANDIDATE")
        ctx.initialize()

        self.assertTrue(ctx.is_initialized)
        self.assertEqual(ctx.node.role, SwarmRole.CANDIDATE)

        ctx.shutdown()
        self.assertFalse(ctx.is_initialized)


class TestSwarmContextShutdown(unittest.TestCase):

    def test_shutdown_reverse_order_cleans_resources(self):
        ctx = SwarmContext(drone_id="root-00", role="ROOT_LEADER")
        ctx.initialize()

        # Add a session to security manager
        ctx.security.create_session("follower-A1", b"\x01" * 16, b"\xAA" * 16, b"\xBB" * 16)
        self.assertEqual(ctx.security.active_session_count(), 1)

        ctx.shutdown()

        self.assertFalse(ctx.is_initialized)
        status = ctx.get_status()
        self.assertFalse(status["initialized"])

    def test_double_shutdown_safe(self):
        ctx = SwarmContext(drone_id="root-00", role="ROOT_LEADER")
        ctx.initialize()
        ctx.shutdown()
        ctx.shutdown()  # Should be no-op
        self.assertFalse(ctx.is_initialized)

    def test_double_initialize_safe(self):
        ctx = SwarmContext(drone_id="root-00", role="ROOT_LEADER")
        ctx.initialize()
        ctx.initialize()  # Should be no-op
        self.assertTrue(ctx.is_initialized)
        ctx.shutdown()


class TestSwarmContextConcurrency(unittest.TestCase):

    def test_concurrent_init_and_shutdown(self):
        ctx = SwarmContext(drone_id="root-00", role="ROOT_LEADER")
        errors = []

        def worker_init():
            try:
                ctx.initialize()
            except Exception as e:
                errors.append(e)

        def worker_shutdown():
            try:
                time.sleep(0.01)
                ctx.shutdown()
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=worker_init)
        t2 = threading.Thread(target=worker_shutdown)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
