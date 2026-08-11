"""Unit, Edge-Case, and Failure Test Suite for Swarm Message Dataclasses (messages.py).
"""

import sys
import unittest
from pathlib import Path

# Ensure project root is discoverable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hierarchical_swarm.messages import (
    AuthRequestMessage,
    AuthResponseMessage,
    FailoverMessage,
    HeartbeatMessage,
    HelloMessage,
    JoinMessage,
    KemKeyExchangeMessage,
    LeaveMessage,
    MessageValidationError,
    RegisterMessage,
    ReParentMessage,
    ShutdownMessage,
    TaskAckMessage,
    TaskAssignMessage,
    TelemetryMessage,
    parse_wire_message,
)
from hierarchical_swarm.protocol import MessageTypeId, WireMessage


class TestSwarmMessages(unittest.TestCase):
    def test_hello_message_roundtrip(self):
        msg = HelloMessage(
            sequence=1,
            cluster_id="cluster-01",
            leader_id="leader-01",
            smt_root=b"\x01" * 32,
            battery_pct=95.5,
            rssi=-45.0,
        )
        wire = msg.to_wire_message()
        serialized = wire.serialize()

        recovered_wire = WireMessage.deserialize(serialized)
        recovered_msg = parse_wire_message(recovered_wire)

        self.assertIsInstance(recovered_msg, HelloMessage)
        self.assertEqual(recovered_msg.cluster_id, "cluster-01")
        self.assertEqual(recovered_msg.leader_id, "leader-01")
        self.assertEqual(recovered_msg.smt_root, b"\x01" * 32)
        self.assertEqual(recovered_msg.battery_pct, 95.5)

    def test_register_and_auth_messages_roundtrip(self):
        reg = RegisterMessage(sequence=2, candidate_id="drone-02", pubkey=b"\x02" * 32)
        wire_reg = reg.to_wire_message()
        rec_reg = parse_wire_message(WireMessage.deserialize(wire_reg.serialize()))
        self.assertEqual(rec_reg.candidate_id, "drone-02")

        auth_req = AuthRequestMessage(sequence=3, challenge_nonce="nonce_123", smt_root=b"\x03" * 32)
        wire_req = auth_req.to_wire_message()
        rec_req = parse_wire_message(WireMessage.deserialize(wire_req.serialize()))
        self.assertEqual(rec_req.challenge_nonce, "nonce_123")

        auth_resp = AuthResponseMessage(sequence=4, candidate_id="drone-02", smt_proof_bytes=b"\x04" * 64)
        wire_resp = auth_resp.to_wire_message()
        rec_resp = parse_wire_message(WireMessage.deserialize(wire_resp.serialize()))
        self.assertEqual(rec_resp.smt_proof_bytes, b"\x04" * 64)

    def test_kem_key_exchange_message_roundtrip(self):
        msg = KemKeyExchangeMessage(
            sequence=5,
            sender_id="drone-01",
            kem_pubkey_bytes=b"\x05" * 32,
            ciphertext_bytes=b"\x06" * 64,
        )
        wire = msg.to_wire_message()
        rec = parse_wire_message(WireMessage.deserialize(wire.serialize()))
        self.assertEqual(rec.sender_id, "drone-01")
        self.assertEqual(rec.ciphertext_bytes, b"\x06" * 64)

    def test_heartbeat_and_telemetry_messages(self):
        hb = HeartbeatMessage(
            sequence=6,
            drone_id="drone-01",
            role="follower",
            status="ACTIVE",
            battery_voltage=12.4,
            cpu_load=15.2,
        )
        rec_hb = parse_wire_message(WireMessage.deserialize(hb.to_wire_message().serialize()))
        self.assertEqual(rec_hb.battery_voltage, 12.4)

        telem = TelemetryMessage(
            sequence=7,
            cluster_id="cluster-01",
            aggregated_metrics={"active_drones": 4, "avg_battery": 92.0},
            smt_root=b"\x07" * 32,
        )
        rec_telem = parse_wire_message(WireMessage.deserialize(telem.to_wire_message().serialize()))
        self.assertEqual(rec_telem.aggregated_metrics["active_drones"], 4)

    def test_task_assign_and_ack_messages(self):
        task = TaskAssignMessage(
            sequence=8,
            task_id="task-101",
            task_type="PATROL",
            target_coordinates=(12.9716, 77.5946, 50.0),
            deadline=1700000000.0,
        )
        rec_task = parse_wire_message(WireMessage.deserialize(task.to_wire_message().serialize()))
        self.assertEqual(rec_task.target_coordinates, (12.9716, 77.5946, 50.0))

        ack = TaskAckMessage(sequence=9, task_id="task-101", status="ACCEPTED", execution_cost=0.5)
        rec_ack = parse_wire_message(WireMessage.deserialize(ack.to_wire_message().serialize()))
        self.assertEqual(rec_ack.status, "ACCEPTED")

    def test_failover_reparent_leave_shutdown_messages(self):
        fo = FailoverMessage(sequence=10, failed_leader_id="leader-01", candidate_id="drone-02", battery_weight=88.5)
        self.assertEqual(parse_wire_message(WireMessage.deserialize(fo.to_wire_message().serialize())).battery_weight, 88.5)

        rep = ReParentMessage(sequence=11, new_leader_id="drone-02", cluster_id="cluster-01", new_smt_root=b"\x08"*32)
        self.assertEqual(parse_wire_message(WireMessage.deserialize(rep.to_wire_message().serialize())).new_leader_id, "drone-02")

        leave = LeaveMessage(sequence=12, drone_id="drone-03", reason="BATTERY_LOW")
        self.assertEqual(parse_wire_message(WireMessage.deserialize(leave.to_wire_message().serialize())).reason, "BATTERY_LOW")

        sd = ShutdownMessage(sequence=13, drone_id="drone-leader", grace_period_sec=5.0)
        self.assertEqual(parse_wire_message(WireMessage.deserialize(sd.to_wire_message().serialize())).grace_period_sec, 5.0)

    def test_corrupted_payload_raises_error(self):
        """Failure Test: Parsing wire message with corrupted JSON payload."""
        valid_msg = HelloMessage(
            sequence=1, cluster_id="c1", leader_id="l1", smt_root=b"\x00"*32, battery_pct=90.0, rssi=-50.0
        )
        wire = valid_msg.to_wire_message()
        corrupted_wire = WireMessage(header=wire.header, payload=b"{invalid json content...")

        with self.assertRaises(MessageValidationError):
            parse_wire_message(corrupted_wire)


if __name__ == "__main__":
    unittest.main()
