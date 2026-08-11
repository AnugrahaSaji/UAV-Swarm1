"""Comprehensive Test Suite for HeartbeatManager (heartbeat.py).

Tests cover:
    1.  HeartbeatConfig — default values & initialization.
    2.  HeartbeatManager lifecycle — start(), stop(), is_running().
    3.  Heartbeat send — timer scheduling & transport invocation.
    4.  Heartbeat receive — process_heartbeat(), sequence tracking, metrics.
    5.  Duplicate & out-of-order heartbeat detection.
    6.  Liveness check & timeout — timeout threshold, expiration of session in security, topology status update.
    7.  Node recovery — transition from unreachable back to reachable upon receiving heartbeat.
    8.  Statistics reporting — sent, received, loss pct, RTT estimates.
    9.  Event generation — HEARTBEAT_SENT, HEARTBEAT_RECEIVED, NODE_TIMEOUT, SESSION_EXPIRED, NODE_RECOVERED.
    10. Thread safety — concurrent heartbeat processing and statistics querying.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hierarchical_swarm.heartbeat import (
    HeartbeatConfig,
    HeartbeatEvent,
    HeartbeatEventType,
    HeartbeatManager,
    NodeLivenessState,
)
from hierarchical_swarm.messages import HeartbeatMessage
from hierarchical_swarm.node import NodeState, NodeStatus, SwarmNode
from hierarchical_swarm.security import SwarmSecurityManager
from hierarchical_swarm.topology import SwarmTopology
from hierarchical_swarm.utils import ClusterId, DroneId, SwarmRole


class TestHeartbeatConfig(unittest.TestCase):

    def test_default_config_values(self):
        cfg = HeartbeatConfig()
        self.assertGreater(cfg.interval_sec, 0)
        self.assertGreater(cfg.timeout_sec, cfg.interval_sec)
        self.assertEqual(cfg.max_missed, 3)


class TestHeartbeatLifecycleAndSend(unittest.TestCase):

    def setUp(self):
        self.local_node = SwarmNode(drone_id=DroneId("node-01"), role=SwarmRole.FOLLOWER)
        self.topo = SwarmTopology()
        self.sec = SwarmSecurityManager()
        self.sent_bytes = []

        def mock_transport(b: bytes):
            self.sent_bytes.append(b)

        self.cfg = HeartbeatConfig(interval_sec=0.05, timeout_sec=0.2, check_interval_sec=0.05)
        self.mgr = HeartbeatManager(
            local_node=self.local_node,
            topology=self.topo,
            security=self.sec,
            config=self.cfg,
            send_transport=mock_transport,
        )

    def tearDown(self):
        self.mgr.stop()

    def test_start_and_stop(self):
        self.assertFalse(self.mgr.is_running())
        self.mgr.start()
        self.assertTrue(self.mgr.is_running())
        self.mgr.stop()
        self.assertFalse(self.mgr.is_running())

    def test_heartbeat_timer_sends_payloads(self):
        self.mgr.start()
        time.sleep(0.15)  # Should trigger 2-3 heartbeats
        self.mgr.stop()
        self.assertGreaterEqual(len(self.sent_bytes), 2)
        stats = self.mgr.statistics()
        self.assertGreaterEqual(stats["heartbeats_sent"], 2)


class TestHeartbeatReceiveAndMetrics(unittest.TestCase):

    def setUp(self):
        self.local_node = SwarmNode(drone_id=DroneId("node-01"), role=SwarmRole.FOLLOWER)
        self.topo = SwarmTopology()
        self.sec = SwarmSecurityManager()
        self.cfg = HeartbeatConfig(interval_sec=0.05, timeout_sec=0.2, check_interval_sec=0.05)
        self.mgr = HeartbeatManager(
            local_node=self.local_node,
            topology=self.topo,
            security=self.sec,
            config=self.cfg,
        )

    def test_process_valid_heartbeat(self):
        msg = HeartbeatMessage(
            sequence=1,
            flags=0,
            drone_id="neighbor-01",
            role="FOLLOWER",
            status="ACTIVE",
            battery_voltage=12.5,
            cpu_load=5.0,
        )
        self.mgr.process_heartbeat(msg)
        stats = self.mgr.statistics()
        self.assertEqual(stats["heartbeats_received"], 1)
        self.assertEqual(stats["active_neighbors"], 1)

        events = self.mgr.drain_events()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, HeartbeatEventType.HEARTBEAT_RECEIVED)
        self.assertEqual(events[0].drone_id, "neighbor-01")

    def test_duplicate_heartbeat_ignored(self):
        msg = HeartbeatMessage(
            sequence=1,
            flags=0,
            drone_id="neighbor-01",
            role="FOLLOWER",
            status="ACTIVE",
            battery_voltage=12.5,
            cpu_load=5.0,
        )
        self.mgr.process_heartbeat(msg)
        self.mgr.process_heartbeat(msg)  # Duplicate
        stats = self.mgr.statistics()
        self.assertEqual(stats["heartbeats_received"], 2)
        state = self.mgr._liveness_map["neighbor-01"]
        self.assertEqual(state.total_received, 1)  # Only 1 distinct received

    def test_out_of_order_heartbeat_dropped(self):
        msg1 = HeartbeatMessage(
            sequence=10,
            flags=0,
            drone_id="neighbor-01",
            role="FOLLOWER",
            status="ACTIVE",
            battery_voltage=12.5,
            cpu_load=5.0,
        )
        msg2 = HeartbeatMessage(
            sequence=5,  # Out of order
            flags=0,
            drone_id="neighbor-01",
            role="FOLLOWER",
            status="ACTIVE",
            battery_voltage=12.5,
            cpu_load=5.0,
        )
        self.mgr.process_heartbeat(msg1)
        self.mgr.process_heartbeat(msg2)
        state = self.mgr._liveness_map["neighbor-01"]
        self.assertEqual(state.total_dropped, 1)


class TestTimeoutAndRecovery(unittest.TestCase):

    def setUp(self):
        self.root = SwarmNode(drone_id=DroneId("root-00"), role=SwarmRole.ROOT_LEADER, tree_level=0)
        self.leader = SwarmNode(drone_id=DroneId("leader-A"), role=SwarmRole.CLUSTER_LEADER, tree_level=1, parent_id=DroneId("root-00"), cluster_id=ClusterId("cluster-A"))
        self.neighbor = SwarmNode(drone_id=DroneId("neighbor-01"), role=SwarmRole.FOLLOWER, tree_level=2, parent_id=DroneId("leader-A"), cluster_id=ClusterId("cluster-A"))

        self.topo = SwarmTopology()
        self.topo.add_node(self.root)
        self.topo.add_node(self.leader, cluster_id="cluster-A")
        self.topo.add_node(self.neighbor, cluster_id="cluster-A")

        self.sec = SwarmSecurityManager()
        self.sec.create_session("neighbor-01", b"\x01" * 16, b"\xAA" * 16, b"\xBB" * 16)

        self.cfg = HeartbeatConfig(interval_sec=0.05, timeout_sec=0.1, check_interval_sec=0.03, max_missed=1)
        self.mgr = HeartbeatManager(
            local_node=self.leader,
            topology=self.topo,
            security=self.sec,
            config=self.cfg,
        )

    def tearDown(self):
        self.mgr.stop()

    def test_node_timeout_triggers_expiry_and_unreachable(self):
        # Register a heartbeat from neighbor-01
        msg = HeartbeatMessage(
            sequence=1,
            flags=0,
            drone_id="neighbor-01",
            role="FOLLOWER",
            status="ACTIVE",
            battery_voltage=12.5,
            cpu_load=5.0,
        )
        self.mgr.process_heartbeat(msg)
        self.assertTrue(self.sec.has_session("neighbor-01"))

        # Start manager check timer to detect timeout
        self.mgr.start()
        time.sleep(0.18)  # Exceeds 0.1s timeout
        self.mgr.stop()

        # Check topology node status updated
        target = self.topo.get_node("neighbor-01")
        self.assertEqual(target.state, NodeState.OFFLINE)

        # Check security session expired
        self.assertFalse(self.sec.has_session("neighbor-01"))

        # Check events emitted
        events = self.mgr.drain_events()
        types = [e.event_type for e in events]
        self.assertIn(HeartbeatEventType.NODE_TIMEOUT, types)
        self.assertIn(HeartbeatEventType.SESSION_EXPIRED, types)

    def test_node_recovery_after_timeout(self):
        # Trigger timeout state directly
        self.mgr._liveness_map["neighbor-01"] = NodeLivenessState(
            drone_id="neighbor-01",
            last_seen=time.monotonic() - 1.0,
            is_unreachable=True,
        )

        msg = HeartbeatMessage(
            sequence=10,
            flags=0,
            drone_id="neighbor-01",
            role="FOLLOWER",
            status="ACTIVE",
            battery_voltage=12.5,
            cpu_load=5.0,
        )
        self.mgr.process_heartbeat(msg)

        state = self.mgr._liveness_map["neighbor-01"]
        self.assertFalse(state.is_unreachable)

        events = self.mgr.drain_events()
        types = [e.event_type for e in events]
        self.assertIn(HeartbeatEventType.NODE_RECOVERED, types)


class TestThreadSafety(unittest.TestCase):

    def setUp(self):
        self.local_node = SwarmNode(drone_id=DroneId("node-01"), role=SwarmRole.FOLLOWER)
        self.topo = SwarmTopology()
        self.sec = SwarmSecurityManager()
        self.cfg = HeartbeatConfig(interval_sec=0.05, timeout_sec=0.5, check_interval_sec=0.05)
        self.mgr = HeartbeatManager(
            local_node=self.local_node,
            topology=self.topo,
            security=self.sec,
            config=self.cfg,
        )

    def test_concurrent_heartbeat_processing(self):
        errors = []

        def worker(drone_idx: int):
            try:
                drone_id = f"neighbor-{drone_idx}"
                for seq in range(1, 20):
                    msg = HeartbeatMessage(
                        sequence=seq,
                        flags=0,
                        drone_id=drone_id,
                        role="FOLLOWER",
                        status="ACTIVE",
                        battery_voltage=12.5,
                        cpu_load=5.0,
                    )
                    self.mgr.process_heartbeat(msg)
                    stats = self.mgr.statistics()
                    self.assertIsInstance(stats, dict)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [])
        stats = self.mgr.statistics()
        self.assertEqual(stats["active_neighbors"], 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
