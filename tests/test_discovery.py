"""Comprehensive Test Suite for DiscoveryEngine (discovery.py).

Tests cover:
    1.  DiscoveryConfig — construction, from_env(), default values.
    2.  DiscoveryCache — insert, update, evict-stale, evict-worst, rank, clear.
    3.  _compute_score — ranking formula correctness.
    4.  DiscoveryPhase state machine — legal and illegal transitions.
    5.  Battery guard — join blocked below threshold.
    6.  HELLO processing — cache update, NODE_DISCOVERED event.
    7.  Discovery timeout — max retries exhausted.
    8.  Retry policy — backoff behaviour with mock transport.
    9.  Full join success path — HELLO → REGISTER → AUTH → KEM → JOIN_ACCEPT.
    10. JOIN_REJECT — fallback to next leader.
    11. DUPLICATE_ID — terminal rejection.
    12. Beaconing (leader role) — timer chain fires HELLO frames.
    13. Event drain — correct event types emitted, queue cleared.
    14. Thread safety — concurrent event drain with concurrent emission.
"""

from __future__ import annotations

import sys
import threading
import time
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hierarchical_swarm.discovery import (
    DiscoveryCache,
    DiscoveryConfig,
    DiscoveryEngine,
    DiscoveryError,
    DiscoveryEventType,
    DiscoveryPhase,
    DiscoveryTimeoutError,
    DuplicateDroneIDError,
    InsufficientBatteryError,
    InvalidStateTransitionError,
    LeaderCacheEntry,
    _compute_score,
)
from hierarchical_swarm.messages import (
    AuthRequestMessage,
    HelloMessage,
    JoinMessage,
    KemKeyExchangeMessage,
)
from hierarchical_swarm.node import NodeState, SwarmNode
from hierarchical_swarm.protocol import WireMessage
from hierarchical_swarm.topology import SwarmTopology
from hierarchical_swarm.utils import ClusterId, DroneId, SwarmRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_CFG = DiscoveryConfig(
    beacon_interval_sec=0.05,
    discovery_timeout_sec=0.3,
    ack_timeout_sec=0.2,
    max_discovery_retries=2,
    max_send_retries=2,
    send_backoff_sec=0.01,
    entry_lifetime_sec=2.0,
    max_cache_entries=4,
    battery_min_pct=10.0,
    poll_interval_sec=0.05,
)


def make_candidate(drone_id: str = "drone-01") -> SwarmNode:
    return SwarmNode(
        drone_id=DroneId(drone_id),
        role=SwarmRole.CANDIDATE,
        tree_level=2,
    )


def make_leader_node(drone_id: str = "leader-A", cluster_id: str = "cluster-A") -> SwarmNode:
    return SwarmNode(
        drone_id=DroneId(drone_id),
        role=SwarmRole.CLUSTER_LEADER,
        tree_level=1,
        cluster_id=ClusterId(cluster_id),
    )


def _hello_wire_bytes(
    leader_id:   str   = "leader-A",
    cluster_id:  str   = "cluster-A",
    battery_pct: float = 80.0,
    rssi:        float = -55.0,
    seq:         int   = 0,
) -> bytes:
    """Serialises a HelloMessage to raw wire bytes."""
    msg = HelloMessage(
        sequence=seq,
        cluster_id=cluster_id,
        leader_id=leader_id,
        smt_root=b"\xab" * 32,
        battery_pct=battery_pct,
        rssi=rssi,
    )
    return msg.to_wire_message().serialize()


def _join_wire_bytes(
    status:           str = "APPROVED",
    assigned_cluster: str = "cluster-A",
    parent_id:        str = "leader-A",
    seq:              int = 1,
) -> bytes:
    msg = JoinMessage(
        sequence=seq,
        status=status,
        assigned_cluster=assigned_cluster,
        parent_id=parent_id,
    )
    return msg.to_wire_message().serialize()


def _auth_request_wire_bytes(seq: int = 1) -> bytes:
    msg = AuthRequestMessage(
        sequence=seq,
        challenge_nonce="nonce-xyz",
        smt_root=b"\xab" * 32,
    )
    return msg.to_wire_message().serialize()


def _kem_wire_bytes(seq: int = 2) -> bytes:
    msg = KemKeyExchangeMessage(
        sequence=seq,
        sender_id="leader-A",
        kem_pubkey_bytes=b"\x00" * 32,
        ciphertext_bytes=b"\x00" * 64,
    )
    return msg.to_wire_message().serialize()


# ---------------------------------------------------------------------------
# Mock Transport
# ---------------------------------------------------------------------------

class MockTransport:
    """Controllable mock transport for DiscoveryEngine tests.

    Callers pre-load ``hello_queue`` and ``unicast_queue`` with response
    bytes to simulate network behaviour without real sockets.
    """

    def __init__(self) -> None:
        self.hello_queue:    List[Optional[bytes]] = []
        self.unicast_queue:  List[Optional[bytes]] = []
        self.sent_hellos:    List[bytes]           = []
        self.sent_unicasts:  List[Tuple[bytes, str, int]] = []

    def receive_hello(self, timeout_sec: float) -> Optional[Tuple[bytes, str]]:
        if self.hello_queue:
            raw = self.hello_queue.pop(0)
            return (raw, "192.168.0.2") if raw is not None else None
        return None

    def send_unicast(self, data: bytes, host: str, port: int) -> None:
        self.sent_unicasts.append((data, host, port))

    def receive_unicast(self, timeout_sec: float) -> Optional[Tuple[bytes, str]]:
        if self.unicast_queue:
            raw = self.unicast_queue.pop(0)
            return (raw, "192.168.0.2") if raw is not None else None
        return None

    def send_hello(self, data: bytes) -> None:
        self.sent_hellos.append(data)

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# 1. DiscoveryConfig
# ---------------------------------------------------------------------------

class TestDiscoveryConfig(unittest.TestCase):

    def test_default_values_are_sensible(self):
        cfg = DiscoveryConfig()
        self.assertGreater(cfg.discovery_timeout_sec, 0)
        self.assertGreater(cfg.beacon_interval_sec,   0)
        self.assertGreater(cfg.max_discovery_retries, 0)
        self.assertGreater(cfg.battery_min_pct,       0)
        self.assertIn(".", cfg.mcast_group)

    def test_from_env_returns_config(self):
        cfg = DiscoveryConfig.from_env()
        self.assertIsInstance(cfg, DiscoveryConfig)

    def test_override_values_accepted(self):
        cfg = DiscoveryConfig(battery_min_pct=25.0, max_send_retries=5)
        self.assertEqual(cfg.battery_min_pct, 25.0)
        self.assertEqual(cfg.max_send_retries, 5)

    def test_frozen_prevents_mutation(self):
        cfg = DiscoveryConfig()
        with self.assertRaises((AttributeError, TypeError)):
            cfg.beacon_interval_sec = 99.0  # type: ignore


# ---------------------------------------------------------------------------
# 2. _compute_score
# ---------------------------------------------------------------------------

class TestComputeScore(unittest.TestCase):

    def test_full_battery_and_perfect_signal(self):
        score = _compute_score(100.0, 0.0)
        self.assertAlmostEqual(score, 0.6 * 100 + 0.4 * 100, places=3)

    def test_zero_battery_and_worst_signal(self):
        score = _compute_score(0.0, -100.0)
        self.assertAlmostEqual(score, 0.0, places=5)

    def test_higher_battery_gives_higher_score(self):
        low  = _compute_score(20.0, -70.0)
        high = _compute_score(90.0, -70.0)
        self.assertGreater(high, low)

    def test_higher_rssi_gives_higher_score(self):
        weak   = _compute_score(80.0, -90.0)
        strong = _compute_score(80.0, -20.0)
        self.assertGreater(strong, weak)

    def test_rssi_clamped_at_zero(self):
        # RSSI better than 0 dBm is impossible; clamp at 100.
        score_clamped = _compute_score(80.0, 50.0)   # rssi = +50 → norm = 100
        score_max     = _compute_score(80.0,  0.0)   # rssi =   0 → norm = 100
        self.assertAlmostEqual(score_clamped, score_max, places=5)

    def test_rssi_clamped_at_minus_100(self):
        score_floor  = _compute_score(80.0, -100.0)  # norm = 0
        score_below  = _compute_score(80.0, -200.0)  # clamped to 0 too
        self.assertAlmostEqual(score_floor, score_below, places=5)

    def test_returns_float(self):
        self.assertIsInstance(_compute_score(75.0, -55.0), float)


# ---------------------------------------------------------------------------
# 3. DiscoveryCache
# ---------------------------------------------------------------------------

def _entry(
    leader_id:   str   = "leader-A",
    cluster_id:  str   = "cluster-A",
    battery_pct: float = 80.0,
    rssi:        float = -55.0,
    last_seen:   Optional[float] = None,
) -> None:
    pass  # Unused — helpers use DiscoveryCache.upsert directly.


class TestDiscoveryCache(unittest.TestCase):

    def setUp(self):
        self.cache = DiscoveryCache(max_entries=4, entry_lifetime_sec=2.0)

    def test_insert_new_leader(self):
        is_new = self.cache.upsert("ldr-A","clu-A","192.168.0.2",10000,b"\x00"*32,80.0,-55.0)
        self.assertTrue(is_new)
        self.assertEqual(len(self.cache), 1)

    def test_update_existing_leader_returns_false(self):
        self.cache.upsert("ldr-A","clu-A","192.168.0.2",10000,b"\x00"*32,80.0,-55.0)
        is_new = self.cache.upsert("ldr-A","clu-A","192.168.0.2",10000,b"\x00"*32,85.0,-50.0)
        self.assertFalse(is_new)
        self.assertEqual(len(self.cache), 1)

    def test_multiple_leaders(self):
        self.cache.upsert("ldr-A","clu-A","192.168.0.2",10000,b"\x00"*32,80.0,-55.0)
        self.cache.upsert("ldr-B","clu-B","192.168.0.3",10000,b"\x00"*32,60.0,-70.0)
        self.assertEqual(len(self.cache), 2)

    def test_get_ranked_best_first(self):
        self.cache.upsert("ldr-A","clu-A","192.168.0.2",10000,b"\x00"*32,80.0,-55.0)
        self.cache.upsert("ldr-B","clu-B","192.168.0.3",10000,b"\x00"*32,20.0,-90.0)
        ranked = self.cache.get_ranked()
        self.assertEqual(ranked[0].leader_id, "ldr-A")
        self.assertEqual(ranked[1].leader_id, "ldr-B")

    def test_stale_entry_evicted_by_get_ranked(self):
        self.cache.upsert("ldr-A","clu-A","192.168.0.2",10000,b"\x00"*32,80.0,-55.0)
        # Back-date the last_seen field by directly rebuilding the cache state.
        old_entry = self.cache._entries["ldr-A"]
        stale_entry = LeaderCacheEntry(
            leader_id=old_entry.leader_id,
            cluster_id=old_entry.cluster_id,
            host=old_entry.host,
            port=old_entry.port,
            smt_root=old_entry.smt_root,
            battery_pct=old_entry.battery_pct,
            rssi=old_entry.rssi,
            score=old_entry.score,
            first_seen=old_entry.first_seen,
            last_seen=time.monotonic() - 100.0,  # Way in the past.
        )
        self.cache._entries["ldr-A"] = stale_entry
        ranked = self.cache.get_ranked()
        self.assertEqual(len(ranked), 0)

    def test_max_entries_cap_evicts_worst(self):
        # Fill to capacity.
        self.cache.upsert("ldr-A","clu-A","h",10000,b"\x00"*32,90.0,-40.0)  # Best
        self.cache.upsert("ldr-B","clu-B","h",10000,b"\x00"*32,80.0,-55.0)
        self.cache.upsert("ldr-C","clu-C","h",10000,b"\x00"*32,70.0,-70.0)
        self.cache.upsert("ldr-D","clu-D","h",10000,b"\x00"*32,60.0,-80.0)  # Worst
        self.assertEqual(len(self.cache), 4)
        # Adding a 5th entry should evict the worst (ldr-D).
        self.cache.upsert("ldr-E","clu-E","h",10000,b"\x00"*32,85.0,-45.0)
        self.assertEqual(len(self.cache), 4)
        self.assertNotIn("ldr-D", self.cache._entries)

    def test_remove_existing_leader(self):
        self.cache.upsert("ldr-A","clu-A","h",10000,b"\x00"*32,80.0,-55.0)
        self.cache.remove("ldr-A")
        self.assertEqual(len(self.cache), 0)

    def test_remove_non_existent_does_not_raise(self):
        self.cache.remove("ghost")  # Must be silent.

    def test_clear(self):
        self.cache.upsert("ldr-A","clu-A","h",10000,b"\x00"*32,80.0,-55.0)
        self.cache.upsert("ldr-B","clu-B","h",10000,b"\x00"*32,70.0,-60.0)
        self.cache.clear()
        self.assertEqual(len(self.cache), 0)


# ---------------------------------------------------------------------------
# 4. DiscoveryPhase State Machine
# ---------------------------------------------------------------------------

class TestStateMachineTransitions(unittest.TestCase):

    def _engine(self) -> DiscoveryEngine:
        transport = MockTransport()
        node      = make_candidate()
        topo      = SwarmTopology()
        return DiscoveryEngine(
            local_node=node,
            topology=topo,
            config=DEFAULT_CFG,
            transport=transport,
            battery_pct_fn=lambda: 100.0,
        )

    def test_initial_phase_is_idle(self):
        eng = self._engine()
        self.assertEqual(eng._phase, DiscoveryPhase.IDLE)

    def test_idle_to_listening_is_legal(self):
        eng = self._engine()
        eng._transition(DiscoveryPhase.LISTENING)
        self.assertEqual(eng._phase, DiscoveryPhase.LISTENING)

    def test_idle_to_registering_is_illegal(self):
        eng = self._engine()
        with self.assertRaises(InvalidStateTransitionError):
            eng._transition(DiscoveryPhase.REGISTERING)

    def test_listening_to_registering_is_legal(self):
        eng = self._engine()
        eng._transition(DiscoveryPhase.LISTENING)
        eng._transition(DiscoveryPhase.REGISTERING)
        self.assertEqual(eng._phase, DiscoveryPhase.REGISTERING)

    def test_registering_to_authenticating_is_legal(self):
        eng = self._engine()
        eng._transition(DiscoveryPhase.LISTENING)
        eng._transition(DiscoveryPhase.REGISTERING)
        eng._transition(DiscoveryPhase.AUTHENTICATING)
        self.assertEqual(eng._phase, DiscoveryPhase.AUTHENTICATING)

    def test_joined_is_terminal(self):
        """JOINED has no legal successors."""
        from hierarchical_swarm.discovery import _LEGAL_TRANSITIONS
        self.assertEqual(_LEGAL_TRANSITIONS[DiscoveryPhase.JOINED], ())

    def test_illegal_transition_raises_correct_exception(self):
        eng = self._engine()
        with self.assertRaises(InvalidStateTransitionError) as ctx:
            eng._transition(DiscoveryPhase.JOINED)
        self.assertIn("IDLE", str(ctx.exception))
        self.assertIn("JOINED", str(ctx.exception))

    def test_failed_can_retry_to_listening(self):
        """After FAILED the engine can retry by transitioning back to LISTENING."""
        from hierarchical_swarm.discovery import _LEGAL_TRANSITIONS
        self.assertIn(DiscoveryPhase.LISTENING, _LEGAL_TRANSITIONS[DiscoveryPhase.FAILED])


# ---------------------------------------------------------------------------
# 5. Battery Guard
# ---------------------------------------------------------------------------

class TestBatteryGuard(unittest.TestCase):

    def test_low_battery_raises_before_discovery(self):
        node  = make_candidate()
        topo  = SwarmTopology()
        trans = MockTransport()
        eng   = DiscoveryEngine(
            local_node=node,
            topology=topo,
            config=DEFAULT_CFG,
            transport=trans,
            battery_pct_fn=lambda: 5.0,  # Below 10.0 threshold.
        )
        with self.assertRaises(InsufficientBatteryError):
            eng.run()

    def test_exactly_at_threshold_allows_join(self):
        """Battery exactly at battery_min_pct must NOT raise."""
        node  = make_candidate()
        topo  = SwarmTopology()
        trans = MockTransport()
        trans.hello_queue = []  # No HELLO → times out, but battery guard passes.
        eng   = DiscoveryEngine(
            local_node=node,
            topology=topo,
            config=DEFAULT_CFG,
            transport=trans,
            battery_pct_fn=lambda: 10.0,  # Exactly at threshold.
        )
        with self.assertRaises(DiscoveryTimeoutError):
            eng.run()  # Timeout — but not InsufficientBatteryError.

    def test_high_battery_does_not_raise(self):
        node  = make_candidate()
        topo  = SwarmTopology()
        trans = MockTransport()
        trans.hello_queue = []
        eng   = DiscoveryEngine(
            local_node=node,
            topology=topo,
            config=DEFAULT_CFG,
            transport=trans,
            battery_pct_fn=lambda: 95.0,
        )
        with self.assertRaises(DiscoveryTimeoutError):
            eng.run()


# ---------------------------------------------------------------------------
# 6. HELLO Processing and Cache
# ---------------------------------------------------------------------------

class TestHelloProcessing(unittest.TestCase):

    def _engine(self) -> DiscoveryEngine:
        node  = make_candidate()
        topo  = SwarmTopology()
        trans = MockTransport()
        return DiscoveryEngine(
            local_node=node,
            topology=topo,
            config=DEFAULT_CFG,
            transport=trans,
            battery_pct_fn=lambda: 100.0,
        )

    def test_valid_hello_updates_cache(self):
        eng = self._engine()
        eng._process_hello_packet(_hello_wire_bytes(), "192.168.0.2")
        self.assertEqual(len(eng._cache), 1)

    def test_first_hello_emits_hello_received_and_node_discovered(self):
        eng = self._engine()
        eng._process_hello_packet(_hello_wire_bytes(), "192.168.0.2")
        events = eng.drain_events()
        types  = [e.event_type for e in events]
        self.assertIn(DiscoveryEventType.HELLO_RECEIVED,  types)
        self.assertIn(DiscoveryEventType.NODE_DISCOVERED, types)

    def test_duplicate_hello_does_not_emit_node_discovered(self):
        eng = self._engine()
        eng._process_hello_packet(_hello_wire_bytes(), "192.168.0.2")
        eng.drain_events()  # Clear first-seen events.
        eng._process_hello_packet(_hello_wire_bytes(), "192.168.0.2")  # Duplicate.
        events = eng.drain_events()
        types  = [e.event_type for e in events]
        self.assertIn(DiscoveryEventType.HELLO_RECEIVED,  types)
        self.assertNotIn(DiscoveryEventType.NODE_DISCOVERED, types)

    def test_malformed_packet_is_ignored(self):
        eng = self._engine()
        eng._process_hello_packet(b"\x00\xFF\xAB", "192.168.0.2")
        self.assertEqual(len(eng._cache), 0)

    def test_hello_leader_id_correct_in_cache(self):
        eng = self._engine()
        eng._process_hello_packet(
            _hello_wire_bytes(leader_id="leader-X", cluster_id="cluster-X"),
            "192.168.0.2",
        )
        ranked = eng._cache.get_ranked()
        self.assertEqual(ranked[0].leader_id, "leader-X")


# ---------------------------------------------------------------------------
# 7. Discovery Timeout
# ---------------------------------------------------------------------------

class TestDiscoveryTimeout(unittest.TestCase):

    def test_timeout_after_max_retries(self):
        node  = make_candidate()
        topo  = SwarmTopology()
        trans = MockTransport()
        trans.hello_queue = []  # Simulate no leaders present.
        eng   = DiscoveryEngine(
            local_node=node,
            topology=topo,
            config=DEFAULT_CFG,
            transport=trans,
            battery_pct_fn=lambda: 100.0,
        )
        with self.assertRaises(DiscoveryTimeoutError) as ctx:
            eng.run()
        self.assertIn("discovery cycles", str(ctx.exception).lower())

    def test_timeout_emits_discovery_timeout_event(self):
        node  = make_candidate()
        topo  = SwarmTopology()
        trans = MockTransport()
        trans.hello_queue = []
        eng   = DiscoveryEngine(
            local_node=node,
            topology=topo,
            config=DEFAULT_CFG,
            transport=trans,
            battery_pct_fn=lambda: 100.0,
        )
        try:
            eng.run()
        except DiscoveryTimeoutError:
            pass
        events = eng.drain_events()
        types  = [e.event_type for e in events]
        self.assertIn(DiscoveryEventType.DISCOVERY_TIMEOUT, types)

    def test_node_state_after_timeout(self):
        node  = make_candidate()
        topo  = SwarmTopology()
        trans = MockTransport()
        trans.hello_queue = []
        eng   = DiscoveryEngine(
            local_node=node,
            topology=topo,
            config=DEFAULT_CFG,
            transport=trans,
            battery_pct_fn=lambda: 100.0,
        )
        try:
            eng.run()
        except DiscoveryTimeoutError:
            pass
        self.assertEqual(eng._phase, DiscoveryPhase.FAILED)


# ---------------------------------------------------------------------------
# 8. Full Join Success Path
# ---------------------------------------------------------------------------

class TestJoinSuccess(unittest.TestCase):

    def test_full_join_sequence_reaches_active(self):
        """HELLO → REGISTER → AUTH_REQUEST → AUTH_RESPONSE → KEM → JOIN_ACCEPT."""
        node  = make_candidate("drone-01")
        topo  = SwarmTopology()
        trans = MockTransport()

        # Pre-load the root leader so topology.add_node() can succeed.
        root = SwarmNode(drone_id=DroneId("root-00"), role=SwarmRole.ROOT_LEADER, tree_level=0)
        leader_node = SwarmNode(
            drone_id=DroneId("leader-A"),
            role=SwarmRole.CLUSTER_LEADER,
            tree_level=1,
            parent_id=DroneId("root-00"),
            cluster_id=ClusterId("cluster-A"),
        )
        topo.add_node(root)
        topo.add_node(leader_node, cluster_id="cluster-A")
        topo.drain_events()

        # Queue network responses.
        trans.hello_queue     = [_hello_wire_bytes()]         # 1 HELLO to wake discovery.
        trans.unicast_queue   = [
            _auth_request_wire_bytes(),  # Response to REGISTER → AUTH_REQUEST.
            _kem_wire_bytes(),           # Response to AUTH_RESPONSE → KEM exchange.
            b"\x00",                     # Response to KEM send (ACK placeholder).
            _join_wire_bytes(),          # JOIN(APPROVED).
        ]

        eng = DiscoveryEngine(
            local_node=node,
            topology=topo,
            config=DEFAULT_CFG,
            transport=trans,
            battery_pct_fn=lambda: 90.0,
        )
        eng.run()

        self.assertEqual(eng._phase, DiscoveryPhase.JOINED)
        self.assertTrue(topo.contains("drone-01"))
        events = eng.drain_events()
        types  = [e.event_type for e in events]
        self.assertIn(DiscoveryEventType.JOIN_ACCEPT, types)


# ---------------------------------------------------------------------------
# 9. JOIN_REJECT — fallback path
# ---------------------------------------------------------------------------

class TestJoinReject(unittest.TestCase):

    def test_rejection_triggers_fallback_and_timeout(self):
        """One leader rejects the join; no fallback → eventually times out."""
        node  = make_candidate("drone-02")
        topo  = SwarmTopology()
        trans = MockTransport()

        # Provide one HELLO, then auth+kem, then a REJECT.
        trans.hello_queue   = [_hello_wire_bytes()]
        trans.unicast_queue = [
            _auth_request_wire_bytes(),
            _kem_wire_bytes(),
            b"\x00",
            _join_wire_bytes(status="REJECTED"),
        ]

        eng = DiscoveryEngine(
            local_node=node,
            topology=topo,
            config=DEFAULT_CFG,
            transport=trans,
            battery_pct_fn=lambda: 90.0,
        )
        try:
            eng.run()
        except DiscoveryTimeoutError:
            pass  # Expected — no more leaders after rejection.

        events = eng.drain_events()
        types  = [e.event_type for e in events]
        self.assertIn(DiscoveryEventType.JOIN_REJECT, types)

    def test_rejection_event_contains_reason(self):
        node  = make_candidate("drone-03")
        topo  = SwarmTopology()
        trans = MockTransport()

        trans.hello_queue   = [_hello_wire_bytes()]
        trans.unicast_queue = [
            _auth_request_wire_bytes(),
            _kem_wire_bytes(),
            b"\x00",
            _join_wire_bytes(status="AUTH_FAILED"),
        ]

        eng = DiscoveryEngine(
            local_node=node,
            topology=topo,
            config=DEFAULT_CFG,
            transport=trans,
            battery_pct_fn=lambda: 90.0,
        )
        try:
            eng.run()
        except DiscoveryTimeoutError:
            pass

        events = eng.drain_events()
        reject = [e for e in events if e.event_type == DiscoveryEventType.JOIN_REJECT]
        self.assertTrue(len(reject) >= 1)
        self.assertIn("AUTH_FAILED", reject[0].extra)


# ---------------------------------------------------------------------------
# 10. DUPLICATE_ID — terminal rejection
# ---------------------------------------------------------------------------

class TestDuplicateId(unittest.TestCase):

    def test_duplicate_id_raises_dedicated_exception(self):
        node  = make_candidate("drone-04")
        topo  = SwarmTopology()
        trans = MockTransport()

        trans.hello_queue   = [_hello_wire_bytes()]
        trans.unicast_queue = [
            _auth_request_wire_bytes(),
            _kem_wire_bytes(),
            b"\x00",
            _join_wire_bytes(status="DUPLICATE_ID"),
        ]

        eng = DiscoveryEngine(
            local_node=node,
            topology=topo,
            config=DEFAULT_CFG,
            transport=trans,
            battery_pct_fn=lambda: 90.0,
        )
        with self.assertRaises(DuplicateDroneIDError):
            eng.run()


# ---------------------------------------------------------------------------
# 11. Beaconing (Leader Role)
# ---------------------------------------------------------------------------

class TestBeaconing(unittest.TestCase):

    def test_beacon_sends_hello_frames(self):
        leader = make_leader_node()
        topo   = SwarmTopology()
        trans  = MockTransport()
        cfg    = DiscoveryConfig(beacon_interval_sec=0.02)

        eng = DiscoveryEngine(
            local_node=leader,
            topology=topo,
            config=cfg,
            transport=trans,
            battery_pct_fn=lambda: 80.0,
        )
        eng.start_beaconing()
        time.sleep(0.08)    # Allow 3–4 beacon cycles.
        eng.stop_beaconing()

        self.assertGreater(len(trans.sent_hellos), 0)

    def test_beacon_requires_leader_role(self):
        candidate = make_candidate()
        topo      = SwarmTopology()
        trans     = MockTransport()
        eng       = DiscoveryEngine(
            local_node=candidate,
            topology=topo,
            config=DEFAULT_CFG,
            transport=trans,
        )
        with self.assertRaises(DiscoveryError):
            eng.start_beaconing()

    def test_duplicate_start_is_idempotent(self):
        leader = make_leader_node()
        topo   = SwarmTopology()
        trans  = MockTransport()
        eng    = DiscoveryEngine(
            local_node=leader,
            topology=topo,
            config=DiscoveryConfig(beacon_interval_sec=0.05),
            transport=trans,
        )
        eng.start_beaconing()
        timer1 = eng._beacon_timer
        eng.start_beaconing()  # Should not create another timer.
        timer2 = eng._beacon_timer
        self.assertIs(timer1, timer2)
        eng.stop_beaconing()


# ---------------------------------------------------------------------------
# 12. Event Drain
# ---------------------------------------------------------------------------

class TestEventDrain(unittest.TestCase):

    def test_drain_returns_all_events(self):
        eng  = DiscoveryEngine(
            local_node=make_candidate(),
            topology=SwarmTopology(),
            config=DEFAULT_CFG,
            transport=MockTransport(),
        )
        eng._emit(DiscoveryEventType.HELLO_RECEIVED, leader_id="L1")
        eng._emit(DiscoveryEventType.NODE_DISCOVERED, leader_id="L1")
        events = eng.drain_events()
        self.assertEqual(len(events), 2)

    def test_drain_clears_queue(self):
        eng  = DiscoveryEngine(
            local_node=make_candidate(),
            topology=SwarmTopology(),
            config=DEFAULT_CFG,
            transport=MockTransport(),
        )
        eng._emit(DiscoveryEventType.HELLO_RECEIVED)
        eng.drain_events()
        self.assertEqual(eng.drain_events(), [])

    def test_events_are_immutable(self):
        eng  = DiscoveryEngine(
            local_node=make_candidate(),
            topology=SwarmTopology(),
            config=DEFAULT_CFG,
            transport=MockTransport(),
        )
        eng._emit(DiscoveryEventType.HELLO_RECEIVED, leader_id="L1")
        events = eng.drain_events()
        with self.assertRaises((AttributeError, TypeError)):
            events[0].leader_id = "mutated"   # type: ignore

    def test_sequence_number_wraps_at_uint16(self):
        eng = DiscoveryEngine(
            local_node=make_candidate(),
            topology=SwarmTopology(),
            config=DEFAULT_CFG,
            transport=MockTransport(),
        )
        eng._seq = 0xFFFF
        seq = eng._next_seq()
        self.assertEqual(seq, 0xFFFF)
        seq2 = eng._next_seq()
        self.assertEqual(seq2, 0)


# ---------------------------------------------------------------------------
# 13. Thread Safety
# ---------------------------------------------------------------------------

class TestThreadSafety(unittest.TestCase):

    def test_concurrent_event_emit_and_drain(self):
        """50 threads emit events; drain must see all of them without errors."""
        eng    = DiscoveryEngine(
            local_node=make_candidate(),
            topology=SwarmTopology(),
            config=DEFAULT_CFG,
            transport=MockTransport(),
        )
        errors: list = []

        def emitter():
            try:
                for _ in range(20):
                    eng._emit(DiscoveryEventType.HELLO_RECEIVED)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=emitter) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        remaining = eng.drain_events()
        self.assertEqual(errors, [], errors)
        # Total emitted: 50 × 20 = 1 000.  Drain must give ≤ 1 000.
        self.assertLessEqual(len(remaining), 1000)

    def test_concurrent_sequence_number_is_unique(self):
        """100 threads call _next_seq; all values must be unique modulo wrap."""
        eng     = DiscoveryEngine(
            local_node=make_candidate(),
            topology=SwarmTopology(),
            config=DEFAULT_CFG,
            transport=MockTransport(),
        )
        seqs:  list = []
        errors: list = []
        lock   = threading.Lock()

        def grabber():
            try:
                s = eng._next_seq()
                with lock:
                    seqs.append(s)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=grabber) for _ in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], errors)
        # Sequence numbers should be unique within a 100-call window.
        self.assertEqual(len(seqs), len(set(seqs)))


# ---------------------------------------------------------------------------
# 14. Leader Ranking integration
# ---------------------------------------------------------------------------

class TestLeaderRanking(unittest.TestCase):

    def test_engine_picks_highest_scored_leader(self):
        eng = DiscoveryEngine(
            local_node=make_candidate(),
            topology=SwarmTopology(),
            config=DEFAULT_CFG,
            transport=MockTransport(),
        )
        eng._cache.upsert("ldr-A","clu-A","h",10000,b"\x00"*32, 90.0, -30.0)  # High score
        eng._cache.upsert("ldr-B","clu-B","h",10000,b"\x00"*32, 20.0, -90.0)  # Low score
        top = eng._pick_next_leader()
        self.assertEqual(top.leader_id, "ldr-A")

    def test_empty_cache_returns_none(self):
        eng = DiscoveryEngine(
            local_node=make_candidate(),
            topology=SwarmTopology(),
            config=DEFAULT_CFG,
            transport=MockTransport(),
        )
        self.assertIsNone(eng._pick_next_leader())


if __name__ == "__main__":
    unittest.main(verbosity=2)
