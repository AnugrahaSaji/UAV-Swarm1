"""Binary Protocol Engine for Hierarchical UAV Swarm Network.

Provides high-performance, memory-compact binary serialization and deserialization for all
swarm wire messages using fixed 8-byte binary headers and Big-Endian byte packing.
Optimized for low-bandwidth RF/Wi-Fi mesh communications on Raspberry Pi 4 (Python 3.12+).
"""

from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from enum import IntEnum, unique
from typing import Final, Tuple, Type

try:
    from core.logging_utils import METRICS, get_logger
    logger = get_logger("hierarchical_swarm.protocol")
except ImportError:
    logger = logging.getLogger("hierarchical_swarm.protocol")
    METRICS = None

# Protocol Constants
PROTOCOL_MAGIC: Final[int] = 0x57  # 'W' for Swarm Wire Protocol
PROTOCOL_VERSION: Final[int] = 0x02  # Version 2
HEADER_SIZE: Final[int] = 8  # Fixed 8-byte header size
MAX_PAYLOAD_SIZE: Final[int] = 65535  # Max uint16 payload bytes


class SwarmProtocolError(Exception):
    """Base exception for all binary protocol serialization/deserialization errors."""

    pass


class InvalidMagicByteError(SwarmProtocolError):
    """Raised when an incoming packet header contains an invalid magic byte."""

    pass


class InvalidProtocolVersionError(SwarmProtocolError):
    """Raised when packet version is incompatible."""

    pass


class UnknownMessageTypeError(SwarmProtocolError):
    """Raised when an unknown message type ID is encountered."""

    pass


class PayloadTruncatedError(SwarmProtocolError):
    """Raised when byte buffer is shorter than expected payload length."""

    pass


@unique
class MessageTypeId(IntEnum):
    """Binary message type identifiers for wire transmission."""

    HELLO = 0x01
    REGISTER = 0x02
    AUTH_REQUEST = 0x03
    AUTH_RESPONSE = 0x04
    KEM_KEY_EXCHANGE = 0x05
    JOIN = 0x06
    HEARTBEAT = 0x07
    TELEMETRY = 0x08
    TASK_ASSIGN = 0x09
    TASK_ACK = 0x0A
    FAILOVER = 0x0B
    RE_PARENT = 0x0C
    LEAVE = 0x0D
    SHUTDOWN = 0x0E


@dataclass(slots=True, frozen=True)
class PacketHeader:
    """Fixed 8-byte binary packet header structure.

    Layout:
      [1B Magic (0x57)] [1B Version (0x02)] [1B MsgType ID] [1B Flags] [2B Sequence] [2B Length]
    """

    magic: int
    version: int
    msg_type: MessageTypeId
    flags: int
    sequence: int
    payload_len: int

    def pack(self) -> bytes:
        """Packs the header into 8 binary bytes (Big-Endian)."""
        return struct.pack(
            "!BBBBHH",
            self.magic,
            self.version,
            self.msg_type.value,
            self.flags,
            self.sequence,
            self.payload_len,
        )

    @classmethod
    def unpack(cls, data: bytes) -> PacketHeader:
        """Unpacks 8 binary bytes into a PacketHeader instance."""
        if len(data) < HEADER_SIZE:
            raise PayloadTruncatedError(
                f"Header data too short: {len(data)} < {HEADER_SIZE} bytes"
            )

        magic, version, msg_type_val, flags, sequence, payload_len = struct.unpack(
            "!BBBBHH", data[:HEADER_SIZE]
        )

        if magic != PROTOCOL_MAGIC:
            raise InvalidMagicByteError(f"Invalid magic byte: {hex(magic)} != {hex(PROTOCOL_MAGIC)}")

        if version != PROTOCOL_VERSION:
            raise InvalidProtocolVersionError(
                f"Incompatible protocol version: {version} != {PROTOCOL_VERSION}"
            )

        try:
            msg_type = MessageTypeId(msg_type_val)
        except ValueError:
            raise UnknownMessageTypeError(f"Unknown message type ID: {hex(msg_type_val)}")

        return cls(
            magic=magic,
            version=version,
            msg_type=msg_type,
            flags=flags,
            sequence=sequence,
            payload_len=payload_len,
        )


@dataclass(slots=True, frozen=True)
class WireMessage:
    """Represents a complete wire message combining Header and raw binary Payload."""

    header: PacketHeader
    payload: bytes

    def serialize(self) -> bytes:
        """Serializes header and payload into a contiguous byte string."""
        if len(self.payload) != self.header.payload_len:
            raise SwarmProtocolError(
                f"Payload size mismatch: {len(self.payload)} != {self.header.payload_len}"
            )
        if METRICS:
            METRICS.counter("swarm_packets_serialized").inc()
        return self.header.pack() + self.payload

    @classmethod
    def deserialize(cls, data: bytes) -> WireMessage:
        """Deserializes a complete packet buffer into a WireMessage instance."""
        if len(data) < HEADER_SIZE:
            raise PayloadTruncatedError(f"Data buffer shorter than header size ({HEADER_SIZE}B)")

        header = PacketHeader.unpack(data[:HEADER_SIZE])
        total_expected = HEADER_SIZE + header.payload_len

        if len(data) < total_expected:
            raise PayloadTruncatedError(
                f"Buffer length {len(data)} shorter than expected {total_expected} bytes"
            )

        payload = data[HEADER_SIZE:total_expected]
        if METRICS:
            METRICS.counter("swarm_packets_deserialized").inc()
        return cls(header=header, payload=payload)
