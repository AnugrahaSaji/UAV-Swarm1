#!/usr/bin/env python3
"""
OBS Plane Verification Test

Tests the Observability Plane components:
1. Schema serialization/deserialization
2. Emitter fire-and-forget
3. Receiver callback invocation
4. DataBus integration
5. Loopback verification

Run with: python -m devtools.test_obs_plane
"""

import time
import socket
import threading
import unittest
from datetime import datetime, timezone

# Test the schema
from devtools.obs_schema import (
    ObsSnapshot,
    BatterySnapshot,
    TelemetrySnapshot,
    PolicySnapshot,
    ProxySnapshot,
    NodeType,
    create_snapshot,
    validate_snapshot_size,
    OBS_SCHEMA_VERSION,
    OBS_SCHEMA_NAME,
)

# Test the emitter
from devtools.obs_emitter import ObsEmitter, NullEmitter

# Test the receiver
from devtools.obs_receiver import ObsReceiver, MultiReceiver, ReceiverStats

# Test the data bus integration
from devtools.data_bus import DataBus


class TestObsSchema(unittest.TestCase):
    """Test OBS snapshot schema."""
    
    def test_create_empty_snapshot(self):
        """Test creating an empty snapshot."""
        snap = create_snapshot(
            node=NodeType.DRONE,
            node_id="test-drone",
            seq=1,
        )
        
        self.assertEqual(snap.schema, OBS_SCHEMA_NAME)
        self.assertEqual(snap.schema_version, OBS_SCHEMA_VERSION)
        self.assertEqual(snap.node, "drone")
        self.assertEqual(snap.node_id, "test-drone")
        self.assertEqual(snap.seq, 1)
        self.assertIsInstance(snap.battery, BatterySnapshot)
        self.assertIsInstance(snap.telemetry, TelemetrySnapshot)
        self.assertIsInstance(snap.policy, PolicySnapshot)
        self.assertIsInstance(snap.proxy, ProxySnapshot)
    
    def test_create_full_snapshot(self):
        """Test creating a snapshot with all fields."""
        battery = BatterySnapshot(
            voltage_mv=15500,
            percentage=75,
            rate_mv_per_sec=-5.0,
            stress_level="medium",
            source="simulated",
            is_simulated=True,
            simulation_mode="slow_drain",
        )
        
        telemetry = TelemetrySnapshot(
            rx_pps=25.0,
            gap_p95_ms=50.0,
            blackout_count=1,
            jitter_ms=10.0,
            telemetry_age_ms=100.0,
            sample_count=500,
        )
        
        policy = PolicySnapshot(
            current_suite="KYBER768_ASCON128",
            current_action="DOWNGRADE",
            target_suite="KYBER512_AESGCM128",
            reasons=["battery_stress", "link_degraded"],
            confidence=0.85,
            cooldown_remaining_ms=5000.0,
            local_epoch=42,
            armed=True,
        )
        
        proxy = ProxySnapshot(
            encrypted_pps=100.0,
            plaintext_pps=98.5,
            replay_drops=2,
            handshake_status="ok",
            bytes_encrypted=1000000,
            bytes_decrypted=950000,
        )
        
        snap = create_snapshot(
            node=NodeType.GCS,
            node_id="gcs-01",
            seq=999,
            battery=battery,
            telemetry=telemetry,
            policy=policy,
            proxy=proxy,
        )
        
        self.assertEqual(snap.battery.voltage_mv, 15500)
        self.assertEqual(snap.policy.current_suite, "KYBER768_ASCON128")
        self.assertEqual(snap.telemetry.rx_pps, 25.0)
        self.assertEqual(snap.proxy.handshake_status, "ok")
    
    def test_json_roundtrip(self):
        """Test JSON serialization and deserialization."""
        original = create_snapshot(
            node=NodeType.DRONE,
            node_id="test",
            seq=123,
            battery=BatterySnapshot(voltage_mv=15000, percentage=50),
            policy=PolicySnapshot(current_suite="TEST_SUITE", reasons=["test"]),
        )
        
        # Serialize
        json_str = original.to_json()
        self.assertIsInstance(json_str, str)
        
        # Deserialize
        restored = ObsSnapshot.from_json(json_str)
        self.assertIsNotNone(restored)
        
        # Verify
        self.assertEqual(restored.node, original.node)
        self.assertEqual(restored.node_id, original.node_id)
        self.assertEqual(restored.seq, original.seq)
        self.assertEqual(restored.battery.voltage_mv, original.battery.voltage_mv)
        self.assertEqual(restored.policy.current_suite, original.policy.current_suite)
    
    def test_bytes_roundtrip(self):
        """Test bytes serialization for UDP."""
        original = create_snapshot(
            node=NodeType.GCS,
            node_id="gcs-test",
            seq=456,
        )
        
        # Serialize to bytes
        data = original.to_bytes()
        self.assertIsInstance(data, bytes)
        
        # Deserialize from bytes
        restored = ObsSnapshot.from_bytes(data)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.node_id, original.node_id)
    
    def test_invalid_json_returns_none(self):
        """Test that invalid JSON returns None."""
        result = ObsSnapshot.from_json("not valid json")
        self.assertIsNone(result)
        
        result = ObsSnapshot.from_json('{"wrong": "schema"}')
        self.assertIsNone(result)
    
    def test_snapshot_size_validation(self):
        """Test snapshot size validation."""
        snap = create_snapshot(
            node=NodeType.DRONE,
            node_id="size-test",
            seq=1,
        )
        
        self.assertTrue(validate_snapshot_size(snap))


class TestObsEmitter(unittest.TestCase):
    """Test OBS emitter."""
    
    def test_null_emitter(self):
        """Test NullEmitter no-op behavior."""
        emitter = NullEmitter()
        
        emitter.start()
        result = emitter.emit_snapshot(battery=BatterySnapshot(voltage_mv=15000))
        emitter.stop()
        
        self.assertFalse(result)
        self.assertFalse(emitter.is_active)
        
        stats = emitter.get_stats()
        self.assertEqual(stats["emitted_count"], 0)
    
    def test_emitter_disabled(self):
        """Test emitter with enabled=False."""
        emitter = ObsEmitter(
            node=NodeType.DRONE,
            node_id="disabled-test",
            target_port=59999,
            enabled=False,
        )
        
        emitter.start()
        self.assertFalse(emitter.is_active)
        
        result = emitter.emit_snapshot()
        self.assertFalse(result)
        
        emitter.stop()
    
    def test_emitter_basic(self):
        """Test basic emitter functionality."""
        emitter = ObsEmitter(
            node=NodeType.DRONE,
            node_id="basic-test",
            target_host="127.0.0.1",
            target_port=59999,
            enabled=True,
        )
        
        emitter.start()
        self.assertTrue(emitter.is_active)
        
        # Emit some snapshots (no receiver, fire-and-forget)
        for i in range(5):
            result = emitter.emit_snapshot(
                battery=BatterySnapshot(voltage_mv=15000 - i * 100)
            )
            self.assertTrue(result)
        
        stats = emitter.get_stats()
        self.assertEqual(stats["emitted_count"], 5)
        self.assertEqual(stats["dropped_count"], 0)
        
        emitter.stop()
        self.assertFalse(emitter.is_active)


class TestObsReceiver(unittest.TestCase):
    """Test OBS receiver."""
    
    def test_receiver_basic(self):
        """Test basic receiver functionality."""
        receiver = ObsReceiver(
            listen_host="127.0.0.1",
            listen_port=59901,
        )
        
        self.assertTrue(receiver.start())
        self.assertTrue(receiver.is_running)
        
        receiver.stop()
        self.assertFalse(receiver.is_running)
    
    def test_receiver_callback(self):
        """Test receiver callback invocation."""
        received = []
        
        def callback(snap):
            received.append(snap)
        
        receiver = ObsReceiver(
            listen_host="127.0.0.1",
            listen_port=59902,
        )
        receiver.add_callback(callback)
        receiver.start()
        
        # Give receiver time to start
        time.sleep(0.1)
        
        # Send a test snapshot
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        snap = create_snapshot(
            node=NodeType.DRONE,
            node_id="callback-test",
            seq=1,
        )
        sock.sendto(snap.to_bytes(), ("127.0.0.1", 59902))
        sock.close()
        
        # Wait for callback
        time.sleep(0.2)
        
        receiver.stop()
        
        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].node_id, "callback-test")


class TestObsLoopback(unittest.TestCase):
    """Test emitter-receiver loopback."""
    
    def test_full_loopback(self):
        """Test full emitter -> receiver loopback."""
        received = []
        receive_event = threading.Event()
        
        def on_receive(snap):
            received.append(snap)
            if len(received) >= 3:
                receive_event.set()
        
        # Start receiver
        receiver = ObsReceiver(
            listen_host="127.0.0.1",
            listen_port=59903,
        )
        receiver.add_callback(on_receive)
        receiver.start()
        
        time.sleep(0.1)
        
        # Start emitter
        emitter = ObsEmitter(
            node=NodeType.DRONE,
            node_id="loopback-test",
            target_host="127.0.0.1",
            target_port=59903,
            enabled=True,
        )
        emitter.start()
        
        # Emit snapshots
        for i in range(5):
            emitter.emit_snapshot(
                battery=BatterySnapshot(voltage_mv=15000 + i * 100),
                policy=PolicySnapshot(current_suite=f"SUITE_{i}"),
            )
            time.sleep(0.02)
        
        # Wait for some to arrive
        receive_event.wait(timeout=1.0)
        
        # Stop
        emitter.stop()
        receiver.stop()
        
        # Verify
        self.assertGreaterEqual(len(received), 3)
        self.assertEqual(received[0].node_id, "loopback-test")
        
        # Check stats
        stats = receiver.get_stats()
        self.assertGreater(stats.total_received, 0)


class TestDataBusObsIntegration(unittest.TestCase):
    """Test DataBus OBS snapshot integration."""
    
    def test_update_from_obs_snapshot(self):
        """Test DataBus.update_from_obs_snapshot()."""
        bus = DataBus(history_size=100)
        
        # Create snapshot
        snap = create_snapshot(
            node=NodeType.DRONE,
            node_id="bus-test",
            seq=1,
            battery=BatterySnapshot(voltage_mv=14500, percentage=60, stress_level="medium"),
            telemetry=TelemetrySnapshot(rx_pps=20.0, gap_p95_ms=40.0),
            policy=PolicySnapshot(current_suite="TEST_SUITE", armed=True),
            proxy=ProxySnapshot(encrypted_pps=50.0, handshake_status="ok"),
        )
        
        # Update bus
        bus.update_from_obs_snapshot(snap)
        
        # Verify state updated
        battery = bus.get_battery()
        self.assertEqual(battery.voltage_mv, 14500)
        self.assertEqual(battery.percentage, 60)
        
        telemetry = bus.get_telemetry()
        self.assertEqual(telemetry.rx_pps, 20.0)
        
        policy = bus.get_policy()
        self.assertEqual(policy.current_suite, "TEST_SUITE")
        self.assertTrue(policy.armed)
        
        proxy = bus.get_proxy()
        self.assertEqual(proxy.encrypted_pps, 50.0)
        self.assertEqual(proxy.handshake_status, "ok")
        
        bus.stop()


class TestMultiReceiver(unittest.TestCase):
    """Test MultiReceiver."""
    
    def test_multi_receiver_setup(self):
        """Test MultiReceiver configuration."""
        multi = MultiReceiver(
            ports={"drone": 59904, "gcs": 59905},
            listen_host="127.0.0.1",
        )
        
        results = multi.start()
        self.assertTrue(results.get("drone", False))
        self.assertTrue(results.get("gcs", False))
        self.assertTrue(multi.is_running)
        
        # Test getting individual receivers
        drone_recv = multi.get_receiver("drone")
        self.assertIsNotNone(drone_recv)
        self.assertTrue(drone_recv.is_running)
        
        multi.stop()
        self.assertFalse(multi.is_running)


def run_tests():
    """Run all OBS plane tests."""
    # Set up logging
    import logging
    logging.basicConfig(level=logging.WARNING)
    
    # Run tests
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    suite.addTests(loader.loadTestsFromTestCase(TestObsSchema))
    suite.addTests(loader.loadTestsFromTestCase(TestObsEmitter))
    suite.addTests(loader.loadTestsFromTestCase(TestObsReceiver))
    suite.addTests(loader.loadTestsFromTestCase(TestObsLoopback))
    suite.addTests(loader.loadTestsFromTestCase(TestDataBusObsIntegration))
    suite.addTests(loader.loadTestsFromTestCase(TestMultiReceiver))
    
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    import sys
    sys.exit(run_tests())
