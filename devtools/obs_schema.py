"""
Observability Plane Schema

SNAPSHOT-ONLY data model for passive system observation.
This module defines the wire format for UDP observability snapshots.

CRITICAL PROPERTIES:
- NO commands
- NO RPCs
- NO request/response
- NO state mutation
- Snapshots represent what just happened, not what should happen

Schema Version: 1
Transport: UDP (fire-and-forget)
Encoding: JSON (human-readable for debugging)
"""

import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

# Schema version for forward compatibility
OBS_SCHEMA_VERSION = 1
OBS_SCHEMA_NAME = "uav.pqc.obs.snapshot.v1"

# Maximum UDP payload size (stay well under MTU)
MAX_SNAPSHOT_BYTES = 8192


class NodeType(str, Enum):
    """Node identity for snapshot origin."""
    DRONE = "drone"
    GCS = "gcs"


class StressLevel(str, Enum):
    """Qualitative stress level."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class BatterySnapshot:
    """Battery state at snapshot time."""
    voltage_mv: int = 0
    percentage: int = 0
    rate_mv_per_sec: float = 0.0
    stress_level: str = "low"  # StressLevel value
    source: str = "unknown"    # "mavlink" or "simulated"
    is_simulated: bool = False
    simulation_mode: str = "none"


@dataclass
class TelemetrySnapshot:
    """Link telemetry at snapshot time."""
    rx_pps: float = 0.0
    gap_p95_ms: float = 0.0
    blackout_count: int = 0
    jitter_ms: float = 0.0
    telemetry_age_ms: float = -1.0
    sample_count: int = 0


@dataclass
class PolicySnapshot:
    """Policy/scheduler state at snapshot time."""
    current_suite: str = ""
    current_action: str = "HOLD"
    target_suite: Optional[str] = None
    reasons: List[str] = field(default_factory=list)
    confidence: float = 0.0
    cooldown_remaining_ms: float = 0.0
    local_epoch: int = 0
    armed: bool = False


@dataclass
class ProxySnapshot:
    """Data plane proxy state at snapshot time."""
    encrypted_pps: float = 0.0
    plaintext_pps: float = 0.0
    replay_drops: int = 0
    handshake_status: str = "unknown"
    bytes_encrypted: int = 0
    bytes_decrypted: int = 0


@dataclass
class ObsSnapshot:
    """
    Complete observability snapshot.
    
    This is the root object transmitted over UDP.
    It contains all observable state at a single point in time.
    
    Properties:
    - Immutable once created
    - Self-describing (includes schema info)
    - Contains node identity
    - Contains monotonic and wall-clock timestamps
    """
    # Schema identification
    schema: str = OBS_SCHEMA_NAME
    schema_version: int = OBS_SCHEMA_VERSION
    
    # Node identity
    node: str = "unknown"  # NodeType value
    node_id: str = ""      # Optional unique identifier (e.g., hostname)
    
    # Timestamps
    timestamp_mono_ms: float = 0.0      # time.monotonic() * 1000
    timestamp_iso: str = ""              # ISO 8601 UTC
    
    # Sequence number for loss detection
    seq: int = 0
    
    # State snapshots
    battery: BatterySnapshot = field(default_factory=BatterySnapshot)
    telemetry: TelemetrySnapshot = field(default_factory=TelemetrySnapshot)
    policy: PolicySnapshot = field(default_factory=PolicySnapshot)
    proxy: ProxySnapshot = field(default_factory=ProxySnapshot)
    
    def to_json(self) -> str:
        """Serialize snapshot to JSON string."""
        return json.dumps(asdict(self), separators=(',', ':'))
    
    def to_bytes(self) -> bytes:
        """Serialize snapshot to UTF-8 bytes for UDP transmission."""
        return self.to_json().encode('utf-8')
    
    @classmethod
    def from_json(cls, json_str: str) -> Optional["ObsSnapshot"]:
        """
        Deserialize snapshot from JSON string.
        
        Returns None if parsing fails or schema mismatch.
        """
        try:
            data = json.loads(json_str)
            
            # Validate schema
            if data.get("schema") != OBS_SCHEMA_NAME:
                return None
            if data.get("schema_version", 0) > OBS_SCHEMA_VERSION:
                return None  # Unknown future version
            
            # Parse nested dataclasses
            battery = BatterySnapshot(**data.get("battery", {}))
            telemetry = TelemetrySnapshot(**data.get("telemetry", {}))
            policy_data = data.get("policy", {})
            # Handle None for reasons list
            if policy_data.get("reasons") is None:
                policy_data["reasons"] = []
            policy = PolicySnapshot(**policy_data)
            proxy = ProxySnapshot(**data.get("proxy", {}))
            
            return cls(
                schema=data.get("schema", OBS_SCHEMA_NAME),
                schema_version=data.get("schema_version", OBS_SCHEMA_VERSION),
                node=data.get("node", "unknown"),
                node_id=data.get("node_id", ""),
                timestamp_mono_ms=data.get("timestamp_mono_ms", 0.0),
                timestamp_iso=data.get("timestamp_iso", ""),
                seq=data.get("seq", 0),
                battery=battery,
                telemetry=telemetry,
                policy=policy,
                proxy=proxy,
            )
            
        except (json.JSONDecodeError, TypeError, KeyError):
            return None
    
    @classmethod
    def from_bytes(cls, data: bytes) -> Optional["ObsSnapshot"]:
        """Deserialize snapshot from UTF-8 bytes."""
        try:
            return cls.from_json(data.decode('utf-8'))
        except UnicodeDecodeError:
            return None


def create_snapshot(
    node: NodeType,
    node_id: str,
    seq: int,
    battery: Optional[BatterySnapshot] = None,
    telemetry: Optional[TelemetrySnapshot] = None,
    policy: Optional[PolicySnapshot] = None,
    proxy: Optional[ProxySnapshot] = None,
) -> ObsSnapshot:
    """
    Factory function to create a new snapshot.
    
    Timestamps are captured at creation time.
    """
    now_mono = time.monotonic()
    now_iso = datetime.now(timezone.utc).isoformat()
    
    return ObsSnapshot(
        schema=OBS_SCHEMA_NAME,
        schema_version=OBS_SCHEMA_VERSION,
        node=node.value,
        node_id=node_id,
        timestamp_mono_ms=now_mono * 1000.0,
        timestamp_iso=now_iso,
        seq=seq,
        battery=battery or BatterySnapshot(),
        telemetry=telemetry or TelemetrySnapshot(),
        policy=policy or PolicySnapshot(),
        proxy=proxy or ProxySnapshot(),
    )


def validate_snapshot_size(snapshot: ObsSnapshot) -> bool:
    """
    Check if snapshot fits in UDP payload limit.
    
    Returns True if valid, False if too large.
    """
    return len(snapshot.to_bytes()) <= MAX_SNAPSHOT_BYTES
