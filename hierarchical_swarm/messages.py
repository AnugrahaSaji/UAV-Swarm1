"""Typed Message Objects for Hierarchical UAV Swarm Network.

Provides memory-compact, slotted dataclass message definitions for all 14 swarm wire protocol messages.
Includes automatic conversion to and from `hierarchical_swarm.protocol.WireMessage` binary structures.
Optimized for Raspberry Pi 4 (Python 3.12+).
"""

from __future__ import annotations

import json
import logging
import struct
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, Final, Optional

from hierarchical_swarm.protocol import (
    HEADER_SIZE,
    PROTOCOL_MAGIC,
    PROTOCOL_VERSION,
    MessageTypeId,
    PacketHeader,
    SwarmProtocolError,
    WireMessage,
)

try:
    from core.logging_utils import METRICS, get_logger
    logger = get_logger("hierarchical_swarm.messages")
except ImportError:
    logger = logging.getLogger("hierarchical_swarm.messages")
    METRICS = None


class MessageValidationError(Exception):
    """Raised when a swarm message payload fails validation."""

    pass


@dataclass(slots=True, frozen=True, kw_only=True)
class BaseSwarmMessage:
    """Abstract base class for all typed swarm messages.

    Attributes:
        sequence: Sequence counter integer.
        flags: Protocol bit flags integer (default 0).
    """

    sequence: int = 0
    flags: int = 0

    def get_message_type(self) -> MessageTypeId:
        """Returns the MessageTypeId corresponding to this message instance."""
        raise NotImplementedError("Subclasses must define get_message_type")

    def encode_payload(self) -> bytes:
        """Encodes message fields into a JSON or binary byte payload."""
        raise NotImplementedError("Subclasses must define encode_payload")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> BaseSwarmMessage:
        """Decodes binary payload bytes into a typed message object."""
        raise NotImplementedError("Subclasses must define decode_payload")

    def to_wire_message(self) -> WireMessage:
        """Converts this typed message object into a binary WireMessage for transmission."""
        payload_bytes = self.encode_payload()
        header = PacketHeader(
            magic=PROTOCOL_MAGIC,
            version=PROTOCOL_VERSION,
            msg_type=self.get_message_type(),
            flags=self.flags,
            sequence=self.sequence,
            payload_len=len(payload_bytes),
        )
        return WireMessage(header=header, payload=payload_bytes)


@dataclass(slots=True, frozen=True, kw_only=True)
class HelloMessage(BaseSwarmMessage):
    """0x01 HELLO: 1-Hop Cluster Leader beacon message."""

    cluster_id: str
    leader_id: str
    smt_root: bytes
    battery_pct: float
    rssi: float

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.HELLO

    def encode_payload(self) -> bytes:
        data = {
            "cluster_id": self.cluster_id,
            "leader_id": self.leader_id,
            "smt_root": self.smt_root.hex(),
            "battery_pct": self.battery_pct,
            "rssi": self.rssi,
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> HelloMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            cluster_id=data["cluster_id"],
            leader_id=data["leader_id"],
            smt_root=bytes.fromhex(data["smt_root"]),
            battery_pct=float(data["battery_pct"]),
            rssi=float(data["rssi"]),
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class RegisterMessage(BaseSwarmMessage):
    """0x02 REGISTER: Candidate drone registration request."""

    candidate_id: str
    pubkey: bytes
    requested_role: str = "follower"

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.REGISTER

    def encode_payload(self) -> bytes:
        data = {
            "candidate_id": self.candidate_id,
            "pubkey": self.pubkey.hex(),
            "requested_role": self.requested_role,
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> RegisterMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            candidate_id=data["candidate_id"],
            pubkey=bytes.fromhex(data["pubkey"]),
            requested_role=data.get("requested_role", "follower"),
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class AuthRequestMessage(BaseSwarmMessage):
    """0x03 AUTH_REQUEST: Challenge nonce sent to candidate."""

    challenge_nonce: str
    smt_root: bytes

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.AUTH_REQUEST

    def encode_payload(self) -> bytes:
        data = {
            "challenge_nonce": self.challenge_nonce,
            "smt_root": self.smt_root.hex(),
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> AuthRequestMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            challenge_nonce=data["challenge_nonce"],
            smt_root=bytes.fromhex(data["smt_root"]),
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class AuthResponseMessage(BaseSwarmMessage):
    """0x04 AUTH_RESPONSE: SMT proof response sent by candidate."""

    candidate_id: str
    smt_proof_bytes: bytes

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.AUTH_RESPONSE

    def encode_payload(self) -> bytes:
        data = {
            "candidate_id": self.candidate_id,
            "smt_proof_bytes": self.smt_proof_bytes.hex(),
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> AuthResponseMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            candidate_id=data["candidate_id"],
            smt_proof_bytes=bytes.fromhex(data["smt_proof_bytes"]),
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class KemKeyExchangeMessage(BaseSwarmMessage):
    """0x05 KEM_KEY_EXCHANGE: ML-KEM post-quantum key exchange payload."""

    sender_id: str
    kem_pubkey_bytes: bytes
    ciphertext_bytes: bytes

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.KEM_KEY_EXCHANGE

    def encode_payload(self) -> bytes:
        data = {
            "sender_id": self.sender_id,
            "kem_pubkey_bytes": self.kem_pubkey_bytes.hex(),
            "ciphertext_bytes": self.ciphertext_bytes.hex(),
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> KemKeyExchangeMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            sender_id=data["sender_id"],
            kem_pubkey_bytes=bytes.fromhex(data["kem_pubkey_bytes"]),
            ciphertext_bytes=bytes.fromhex(data["ciphertext_bytes"]),
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class JoinMessage(BaseSwarmMessage):
    """0x06 JOIN: Cluster join approval or rejection."""

    status: str  # APPROVED or REJECTED
    assigned_cluster: str
    parent_id: str

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.JOIN

    def encode_payload(self) -> bytes:
        data = {
            "status": self.status,
            "assigned_cluster": self.assigned_cluster,
            "parent_id": self.parent_id,
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> JoinMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            status=data["status"],
            assigned_cluster=data["assigned_cluster"],
            parent_id=data["parent_id"],
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class HeartbeatMessage(BaseSwarmMessage):
    """0x07 HEARTBEAT: Follower node liveness and telemetry report."""

    drone_id: str
    role: str
    status: str
    battery_voltage: float
    cpu_load: float

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.HEARTBEAT

    def encode_payload(self) -> bytes:
        data = {
            "drone_id": self.drone_id,
            "role": self.role,
            "status": self.status,
            "battery_voltage": self.battery_voltage,
            "cpu_load": self.cpu_load,
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> HeartbeatMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            drone_id=data["drone_id"],
            role=data["role"],
            status=data["status"],
            battery_voltage=float(data["battery_voltage"]),
            cpu_load=float(data["cpu_load"]),
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class TelemetryMessage(BaseSwarmMessage):
    """0x08 TELEMETRY: Cluster Leader aggregated telemetry summary sent upstream."""

    cluster_id: str
    aggregated_metrics: Dict[str, Any]
    smt_root: bytes

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.TELEMETRY

    def encode_payload(self) -> bytes:
        data = {
            "cluster_id": self.cluster_id,
            "aggregated_metrics": self.aggregated_metrics,
            "smt_root": self.smt_root.hex(),
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> TelemetryMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            cluster_id=data["cluster_id"],
            aggregated_metrics=data["aggregated_metrics"],
            smt_root=bytes.fromhex(data["smt_root"]),
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class TaskAssignMessage(BaseSwarmMessage):
    """0x09 TASK_ASSIGN: Mission task assignment directive."""

    task_id: str
    task_type: str
    target_coordinates: Tuple[float, float, float]
    deadline: float

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.TASK_ASSIGN

    def encode_payload(self) -> bytes:
        data = {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "target_coordinates": list(self.target_coordinates),
            "deadline": self.deadline,
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> TaskAssignMessage:
        data = json.loads(payload.decode("utf-8"))
        coords = tuple(data["target_coordinates"])
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            task_id=data["task_id"],
            task_type=data["task_type"],
            target_coordinates=(float(coords[0]), float(coords[1]), float(coords[2])),
            deadline=float(data["deadline"]),
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class TaskAckMessage(BaseSwarmMessage):
    """0x0A TASK_ACK: Task execution acknowledgement."""

    task_id: str
    status: str  # ACCEPTED, COMPLETED, FAILED
    execution_cost: float

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.TASK_ACK

    def encode_payload(self) -> bytes:
        data = {
            "task_id": self.task_id,
            "status": self.status,
            "execution_cost": self.execution_cost,
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> TaskAckMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            task_id=data["task_id"],
            status=data["status"],
            execution_cost=float(data["execution_cost"]),
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class FailoverMessage(BaseSwarmMessage):
    """0x0B FAILOVER: Leader failover notification and candidate score."""

    failed_leader_id: str
    candidate_id: str
    battery_weight: float

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.FAILOVER

    def encode_payload(self) -> bytes:
        data = {
            "failed_leader_id": self.failed_leader_id,
            "candidate_id": self.candidate_id,
            "battery_weight": self.battery_weight,
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> FailoverMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            failed_leader_id=data["failed_leader_id"],
            candidate_id=data["candidate_id"],
            battery_weight=float(data["battery_weight"]),
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class ReParentMessage(BaseSwarmMessage):
    """0x0C RE_PARENT: Cluster re-parenting directive from new leader."""

    new_leader_id: str
    cluster_id: str
    new_smt_root: bytes

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.RE_PARENT

    def encode_payload(self) -> bytes:
        data = {
            "new_leader_id": self.new_leader_id,
            "cluster_id": self.cluster_id,
            "new_smt_root": self.new_smt_root.hex(),
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> ReParentMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            new_leader_id=data["new_leader_id"],
            cluster_id=data["cluster_id"],
            new_smt_root=bytes.fromhex(data["new_smt_root"]),
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class LeaveMessage(BaseSwarmMessage):
    """0x0D LEAVE: Graceful cluster departure notification."""

    drone_id: str
    reason: str

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.LEAVE

    def encode_payload(self) -> bytes:
        data = {
            "drone_id": self.drone_id,
            "reason": self.reason,
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> LeaveMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            drone_id=data["drone_id"],
            reason=data["reason"],
        )


@dataclass(slots=True, frozen=True, kw_only=True)
class ShutdownMessage(BaseSwarmMessage):
    """0x0E SHUTDOWN: Cluster or swarm shutdown directive."""

    drone_id: str
    grace_period_sec: float

    def get_message_type(self) -> MessageTypeId:
        return MessageTypeId.SHUTDOWN

    def encode_payload(self) -> bytes:
        data = {
            "drone_id": self.drone_id,
            "grace_period_sec": self.grace_period_sec,
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def decode_payload(cls, payload: bytes, header: PacketHeader) -> ShutdownMessage:
        data = json.loads(payload.decode("utf-8"))
        return cls(
            sequence=header.sequence,
            flags=header.flags,
            drone_id=data["drone_id"],
            grace_period_sec=float(data["grace_period_sec"]),
        )


# Registry mapping MessageTypeId to concrete class
MESSAGE_CLASS_MAP: Final[Dict[MessageTypeId, Type[BaseSwarmMessage]]] = {
    MessageTypeId.HELLO: HelloMessage,
    MessageTypeId.REGISTER: RegisterMessage,
    MessageTypeId.AUTH_REQUEST: AuthRequestMessage,
    MessageTypeId.AUTH_RESPONSE: AuthResponseMessage,
    MessageTypeId.KEM_KEY_EXCHANGE: KemKeyExchangeMessage,
    MessageTypeId.JOIN: JoinMessage,
    MessageTypeId.HEARTBEAT: HeartbeatMessage,
    MessageTypeId.TELEMETRY: TelemetryMessage,
    MessageTypeId.TASK_ASSIGN: TaskAssignMessage,
    MessageTypeId.TASK_ACK: TaskAckMessage,
    MessageTypeId.FAILOVER: FailoverMessage,
    MessageTypeId.RE_PARENT: ReParentMessage,
    MessageTypeId.LEAVE: LeaveMessage,
    MessageTypeId.SHUTDOWN: ShutdownMessage,
}


def parse_wire_message(wire_msg: WireMessage) -> BaseSwarmMessage:
    """Parses a WireMessage into a concrete BaseSwarmMessage instance.

    Args:
        wire_msg: The WireMessage binary container.

    Returns:
        Instantiated BaseSwarmMessage object.

    Raises:
        SwarmProtocolError: If message type is un-recognized or payload parsing fails.
    """
    msg_cls = MESSAGE_CLASS_MAP.get(wire_msg.header.msg_type)
    if msg_cls is None:
        raise SwarmProtocolError(f"No message class registered for type {wire_msg.header.msg_type}")

    try:
        return msg_cls.decode_payload(wire_msg.payload, wire_msg.header)
    except Exception as e:
        logger.error("Failed to decode message type %s: %s", wire_msg.header.msg_type, e)
        raise MessageValidationError(f"Invalid payload for {wire_msg.header.msg_type}: {e}") from e
