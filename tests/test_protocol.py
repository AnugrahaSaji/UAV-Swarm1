"""Unit, Edge-Case, and Failure Test Suite for Swarm Protocol Engine (protocol.py).
"""

import sys
import unittest
from pathlib import Path

# Ensure project root is discoverable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hierarchical_swarm.protocol import (
    HEADER_SIZE,
    MAX_PAYLOAD_SIZE,
    PROTOCOL_MAGIC,
    PROTOCOL_VERSION,
    InvalidMagicByteError,
    InvalidProtocolVersionError,
    MessageTypeId,
    PacketHeader,
    PayloadTruncatedError,
    SwarmProtocolError,
    UnknownMessageTypeError,
    WireMessage,
)


class TestSwarmProtocolHeader(unittest.TestCase):
    def test_valid_header_packing_and_unpacking(self):
        """Tests packing and unpacking a valid 8-byte PacketHeader."""
        header = PacketHeader(
            magic=PROTOCOL_MAGIC,
            version=PROTOCOL_VERSION,
            msg_type=MessageTypeId.HELLO,
            flags=0x01,
            sequence=1024,
            payload_len=64,
        )
        packed = header.pack()
        self.assertEqual(len(packed), HEADER_SIZE)

        unpacked = PacketHeader.unpack(packed)
        self.assertEqual(unpacked.magic, PROTOCOL_MAGIC)
        self.assertEqual(unpacked.version, PROTOCOL_VERSION)
        self.assertEqual(unpacked.msg_type, MessageTypeId.HELLO)
        self.assertEqual(unpacked.flags, 0x01)
        self.assertEqual(unpacked.sequence, 1024)
        self.assertEqual(unpacked.payload_len, 64)

    def test_invalid_magic_byte_raises_error(self):
        """Failure Test: Unpacking data with corrupted magic byte."""
        corrupted_data = b"\x99" + b"\x02\x01\x00\x00\x01\x00\x10"
        with self.assertRaises(InvalidMagicByteError):
            PacketHeader.unpack(corrupted_data)

    def test_invalid_version_raises_error(self):
        """Failure Test: Unpacking data with incompatible protocol version."""
        corrupted_data = bytes([PROTOCOL_MAGIC, 0x99, 0x01, 0x00, 0x00, 0x01, 0x00, 0x10])
        with self.assertRaises(InvalidProtocolVersionError):
            PacketHeader.unpack(corrupted_data)

    def test_unknown_message_type_raises_error(self):
        """Failure Test: Unpacking data with un-recognized message type ID."""
        corrupted_data = bytes([PROTOCOL_MAGIC, PROTOCOL_VERSION, 0xFF, 0x00, 0x00, 0x01, 0x00, 0x10])
        with self.assertRaises(UnknownMessageTypeError):
            PacketHeader.unpack(corrupted_data)


class TestWireMessageSerialization(unittest.TestCase):
    def test_wire_message_serialize_and_deserialize(self):
        """Tests complete wire message packing with payload."""
        payload = b"Hello UAV Swarm Mesh Network!"
        header = PacketHeader(
            magic=PROTOCOL_MAGIC,
            version=PROTOCOL_VERSION,
            msg_type=MessageTypeId.HEARTBEAT,
            flags=0,
            sequence=42,
            payload_len=len(payload),
        )
        msg = WireMessage(header=header, payload=payload)
        serialized = msg.serialize()
        self.assertEqual(len(serialized), HEADER_SIZE + len(payload))

        deserialized = WireMessage.deserialize(serialized)
        self.assertEqual(deserialized.header.msg_type, MessageTypeId.HEARTBEAT)
        self.assertEqual(deserialized.header.sequence, 42)
        self.assertEqual(deserialized.payload, payload)

    def test_payload_mismatch_raises_error(self):
        """Edge Case: Header payload length mismatch with actual byte payload."""
        header = PacketHeader(
            magic=PROTOCOL_MAGIC,
            version=PROTOCOL_VERSION,
            msg_type=MessageTypeId.JOIN,
            flags=0,
            sequence=1,
            payload_len=100,  # Header says 100
        )
        msg = WireMessage(header=header, payload=b"short payload")  # Actual length 13
        with self.assertRaises(SwarmProtocolError):
            msg.serialize()

    def test_truncated_buffer_raises_error(self):
        """Edge Case: Receiving truncated buffer shorter than header or payload."""
        header = PacketHeader(
            magic=PROTOCOL_MAGIC,
            version=PROTOCOL_VERSION,
            msg_type=MessageTypeId.TELEMETRY,
            flags=0,
            sequence=1,
            payload_len=50,
        )
        msg = WireMessage(header=header, payload=b"X" * 50)
        full_data = msg.serialize()

        # Truncate buffer in half
        truncated_data = full_data[: HEADER_SIZE + 10]
        with self.assertRaises(PayloadTruncatedError):
            WireMessage.deserialize(truncated_data)


if __name__ == "__main__":
    unittest.main()
