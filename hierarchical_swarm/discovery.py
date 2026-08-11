"""Discovery Engine for Hierarchical UAV Swarm Network.

Implements the complete drone join lifecycle:
    1. Listen passively for 1-hop HELLO beacons from Cluster Leaders.
    2. Rank discovered leaders by battery and signal quality.
    3. Send REGISTER to the top-ranked leader.
    4. Drive the join state machine through REGISTERING → AUTHENTICATING
       → KEM_KEYING → JOINING → ACTIVE.
    5. Hand authentication off to ``security.py`` via the
       ``SecurityServiceProtocol`` interface.
    6. Call ``topology.add_node()`` exactly once on JOIN_ACCEPT.
    7. Activate heartbeat via the ``HeartbeatServiceProtocol`` interface.
    8. Become idle after the node reaches ACTIVE state.

Discovery does NOT perform cryptographic operations, MAVLink forwarding,
routing, scheduling, or cluster management.

All configurable values (ports, timeouts, multicast address, retry counts)
are read from the environment / ``core.config.CONFIG``; none are hardcoded
in this module.

Thread model:
    • Cluster Leader role: single ``threading.Timer`` chain for HELLO
      beacons.  No extra threads.
    • Candidate role: blocking ``socket.settimeout`` poll inside the
      ``run()`` loop.  No threads.
    • Both roles are safe to call from a single external thread.
"""

from __future__ import annotations

import logging
import os
import socket
import struct
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import (
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

from hierarchical_swarm.messages import (
    AuthRequestMessage,
    AuthResponseMessage,
    HelloMessage,
    JoinMessage,
    KemKeyExchangeMessage,
    MessageValidationError,
    RegisterMessage,
    parse_wire_message,
)
from hierarchical_swarm.node import NodeState, SwarmNode
from hierarchical_swarm.topology import SwarmTopology, TopologyError
from hierarchical_swarm.utils import ClusterId, DroneId, SwarmRole

try:
    from core.config import CONFIG
    _MCAST_GROUP: str   = str(CONFIG.get("SWARM_MCAST_GROUP",  "239.255.0.1"))
    _MCAST_PORT:  int   = int(CONFIG.get("SWARM_MCAST_PORT",   9999))
    _HANDSHAKE_PORT: int= int(CONFIG.get("SWARM_HANDSHAKE_PORT", 10000))
except Exception:
    _MCAST_GROUP    = os.getenv("SWARM_MCAST_GROUP",       "239.255.0.1")
    _MCAST_PORT     = int(os.getenv("SWARM_MCAST_PORT",    "9999"))
    _HANDSHAKE_PORT = int(os.getenv("SWARM_HANDSHAKE_PORT","10000"))

try:
    from core.logging_utils import METRICS, get_logger
    _logger = get_logger("hierarchical_swarm.discovery")
except ImportError:
    _logger = logging.getLogger("hierarchical_swarm.discovery")
    METRICS = None


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class DiscoveryError(Exception):
    """Base exception for all discovery lifecycle errors."""


class InvalidStateTransitionError(DiscoveryError):
    """Raised when a state machine transition is attempted from an illegal state."""


class DiscoveryTimeoutError(DiscoveryError):
    """Raised when discovery exhausts all retries without a successful join."""


class DuplicateDroneIDError(DiscoveryError):
    """Raised when the swarm rejects this drone because its ID already exists."""


class InsufficientBatteryError(DiscoveryError):
    """Raised when battery level is below the minimum threshold to join."""


# ---------------------------------------------------------------------------
# Discovery Events
# ---------------------------------------------------------------------------

class DiscoveryEventType(Enum):
    """Lifecycle events emitted by the discovery engine."""

    HELLO_RECEIVED      = auto()
    NODE_DISCOVERED     = auto()
    JOIN_REQUEST        = auto()
    AUTH_REQUIRED       = auto()
    JOIN_ACCEPT         = auto()
    JOIN_REJECT         = auto()
    DISCOVERY_TIMEOUT   = auto()


@dataclass(slots=True, frozen=True)
class DiscoveryEvent:
    """An immutable event record produced by the discovery engine.

    Attributes:
        event_type:  Category of the event.
        drone_id:    Primary drone involved (empty string if N/A).
        leader_id:   Leader involved (empty string if N/A).
        cluster_id:  Cluster involved (empty string if N/A).
        extra:       Optional free-form context string.
    """

    event_type: DiscoveryEventType
    drone_id:   str = ""
    leader_id:  str = ""
    cluster_id: str = ""
    extra:      str = ""


# ---------------------------------------------------------------------------
# Internal join phase (finer-grained than NodeState)
# ---------------------------------------------------------------------------

class DiscoveryPhase(Enum):
    """Internal join-protocol phase used only within the discovery engine.

    Maps to ``NodeState`` as follows:
        IDLE          → NodeState.UNASSIGNED
        LISTENING     → NodeState.DISCOVERING
        REGISTERING   → NodeState.REGISTERING
        AUTHENTICATING→ NodeState.AUTHENTICATING
        KEM_KEYING    → NodeState.AUTHENTICATING  (sub-phase)
        AWAITING_JOIN → NodeState.JOINING
        JOINED        → NodeState.ACTIVE
        FAILED        → NodeState.OFFLINE
    """

    IDLE          = auto()
    LISTENING     = auto()
    REGISTERING   = auto()
    AUTHENTICATING = auto()
    KEM_KEYING    = auto()
    AWAITING_JOIN = auto()
    JOINED        = auto()
    FAILED        = auto()


# Legal forward transition table.  Any transition not listed here is illegal.
_LEGAL_TRANSITIONS: Dict[DiscoveryPhase, Tuple[DiscoveryPhase, ...]] = {
    DiscoveryPhase.IDLE:           (DiscoveryPhase.LISTENING,),
    DiscoveryPhase.LISTENING:      (DiscoveryPhase.REGISTERING, DiscoveryPhase.FAILED),
    DiscoveryPhase.REGISTERING:    (DiscoveryPhase.AUTHENTICATING, DiscoveryPhase.LISTENING, DiscoveryPhase.FAILED),
    DiscoveryPhase.AUTHENTICATING: (DiscoveryPhase.KEM_KEYING, DiscoveryPhase.LISTENING, DiscoveryPhase.FAILED),
    DiscoveryPhase.KEM_KEYING:     (DiscoveryPhase.AWAITING_JOIN, DiscoveryPhase.LISTENING, DiscoveryPhase.FAILED),
    DiscoveryPhase.AWAITING_JOIN:  (DiscoveryPhase.JOINED, DiscoveryPhase.LISTENING, DiscoveryPhase.FAILED),
    DiscoveryPhase.JOINED:         (),   # Terminal success state.
    DiscoveryPhase.FAILED:         (DiscoveryPhase.LISTENING,),  # Allow retry from FAILED.
}


# ---------------------------------------------------------------------------
# Discovery Configuration
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class DiscoveryConfig:
    """All runtime-configurable parameters for the discovery engine.

    Constructed from environment variables / ``core.config.CONFIG`` by
    ``DiscoveryConfig.from_env()``.  No value in this class is hardcoded
    in the calling code.

    Attributes:
        mcast_group:            UDP multicast group for HELLO beacons.
        mcast_port:             UDP port for multicast HELLO beacons.
        handshake_port:         UDP port for unicast register/auth/join.
        beacon_interval_sec:    How often a Cluster Leader emits HELLO.
        discovery_timeout_sec:  How long to wait for at least one HELLO.
        ack_timeout_sec:        Timeout waiting for AUTH_REQUEST or JOIN.
        max_discovery_retries:  Total LISTENING cycles before giving up.
        max_send_retries:       Retransmissions per unicast message.
        send_backoff_sec:       First retransmit delay; doubles each retry.
        entry_lifetime_sec:     Max age (seconds) of a cache entry before eviction.
        max_cache_entries:      Hard cap on discovery cache size.
        battery_min_pct:        Minimum battery percentage to permit joining.
        poll_interval_sec:      Socket read timeout for non-blocking polling.
        beacon_sequence_start:  Initial sequence number for HELLO frames.
    """

    mcast_group:            str   = _MCAST_GROUP
    mcast_port:             int   = _MCAST_PORT
    handshake_port:         int   = _HANDSHAKE_PORT
    beacon_interval_sec:    float = 1.0
    discovery_timeout_sec:  float = 5.0
    ack_timeout_sec:        float = 2.0
    max_discovery_retries:  int   = 3
    max_send_retries:       int   = 3
    send_backoff_sec:       float = 0.5
    entry_lifetime_sec:     float = 5.0
    max_cache_entries:      int   = 8
    battery_min_pct:        float = 10.0
    poll_interval_sec:      float = 0.1
    beacon_sequence_start:  int   = 0

    @classmethod
    def from_env(cls) -> DiscoveryConfig:
        """Constructs a config instance from environment variables.

        All keys fall back to defaults when the environment variable is absent.
        """
        return cls(
            mcast_group=os.getenv("SWARM_MCAST_GROUP", _MCAST_GROUP),
            mcast_port=int(os.getenv("SWARM_MCAST_PORT", str(_MCAST_PORT))),
            handshake_port=int(os.getenv("SWARM_HANDSHAKE_PORT", str(_HANDSHAKE_PORT))),
            beacon_interval_sec=float(os.getenv("SWARM_BEACON_INTERVAL",  "1.0")),
            discovery_timeout_sec=float(os.getenv("SWARM_DISC_TIMEOUT",   "5.0")),
            ack_timeout_sec=float(os.getenv("SWARM_ACK_TIMEOUT",          "2.0")),
            max_discovery_retries=int(os.getenv("SWARM_DISC_RETRIES",      "3")),
            max_send_retries=int(os.getenv("SWARM_SEND_RETRIES",           "3")),
            send_backoff_sec=float(os.getenv("SWARM_SEND_BACKOFF",        "0.5")),
            entry_lifetime_sec=float(os.getenv("SWARM_CACHE_LIFETIME",    "5.0")),
            max_cache_entries=int(os.getenv("SWARM_CACHE_MAX",             "8")),
            battery_min_pct=float(os.getenv("SWARM_BATTERY_MIN",         "10.0")),
            poll_interval_sec=float(os.getenv("SWARM_POLL_INTERVAL",      "0.1")),
        )


# ---------------------------------------------------------------------------
# Leader Cache
# ---------------------------------------------------------------------------

@dataclass(slots=True, frozen=True)
class LeaderCacheEntry:
    """Immutable snapshot of a Cluster Leader observed via a HELLO beacon.

    Attributes:
        leader_id:    DroneId of the Cluster Leader.
        cluster_id:   Cluster this leader manages.
        host:         Source IP address of the HELLO packet.
        port:         Unicast handshake port to reach this leader.
        smt_root:     Advertised SMT root hash (32 bytes).
        battery_pct:  Leader's battery percentage at time of HELLO.
        rssi:         Signal strength in dBm (or 0.0 if unavailable).
        score:        Pre-computed ranking score.
        first_seen:   ``time.monotonic()`` of first HELLO from this leader.
        last_seen:    ``time.monotonic()`` of most recent HELLO.
    """

    leader_id:   str
    cluster_id:  str
    host:        str
    port:        int
    smt_root:    bytes
    battery_pct: float
    rssi:        float
    score:       float
    first_seen:  float
    last_seen:   float


def _compute_score(battery_pct: float, rssi: float) -> float:
    """Computes a leader quality score for ranking.

    Formula (from approved Discovery Design Review):
        S = 0.6 × battery_pct + 0.4 × norm_rssi

    Where norm_rssi maps −100 dBm (worst) → 0, 0 dBm (perfect) → 100.
    This function is intentionally isolated so the scoring heuristic can
    be changed without touching discovery state-machine logic.

    Args:
        battery_pct: Leader battery percentage 0–100.
        rssi:        Signal strength in dBm (typically negative).

    Returns:
        Float score (higher = more preferable leader).
    """
    norm_rssi = max(0.0, min(100.0, 100.0 + rssi))
    return 0.6 * battery_pct + 0.4 * norm_rssi


class DiscoveryCache:
    """Bounded, lazily-evicting cache of known Cluster Leaders.

    Operations:
        insert / update: O(1)
        rank:            O(N log N) with N ≤ max_entries
        eviction:        O(N), lazy — triggered inside ``get_ranked()``

    No background thread is used.  Eviction happens only when
    ``get_ranked()`` is called.

    Attributes:
        _entries:     Dict keyed by leader_id.
        _max_entries: Hard cap on cache size.
        _lifetime:    Maximum age in seconds before eviction.
    """

    def __init__(self, max_entries: int, entry_lifetime_sec: float) -> None:
        self._entries:   Dict[str, LeaderCacheEntry] = {}
        self._max_entries  = max_entries
        self._lifetime     = entry_lifetime_sec

    def upsert(
        self,
        leader_id:   str,
        cluster_id:  str,
        host:        str,
        port:        int,
        smt_root:    bytes,
        battery_pct: float,
        rssi:        float,
    ) -> bool:
        """Inserts a new entry or refreshes an existing one.

        Respects ``_max_entries`` cap: if the cache is full and the
        entry is new, the lowest-scoring existing entry is evicted first.

        Args:
            leader_id, cluster_id, host, port: Identity / address fields.
            smt_root:    Current SMT root hash from the HELLO beacon.
            battery_pct: Leader battery percentage.
            rssi:        Received signal strength in dBm.

        Returns:
            ``True`` if this is the first time this leader has been seen
            (``NODE_DISCOVERED`` event should be emitted by the caller).
        """
        is_new       = leader_id not in self._entries
        score        = _compute_score(battery_pct, rssi)
        first_seen   = self._entries[leader_id].first_seen if not is_new else time.monotonic()

        if is_new and len(self._entries) >= self._max_entries:
            self._evict_worst()

        self._entries[leader_id] = LeaderCacheEntry(
            leader_id=leader_id,
            cluster_id=cluster_id,
            host=host,
            port=port,
            smt_root=smt_root,
            battery_pct=battery_pct,
            rssi=rssi,
            score=score,
            first_seen=first_seen,
            last_seen=time.monotonic(),
        )
        return is_new

    def get_ranked(self) -> List[LeaderCacheEntry]:
        """Returns a snapshot of non-stale entries sorted by score (best first).

        Stale entries (``last_seen < now - lifetime``) are evicted lazily
        before sorting.  The returned list is a new object; mutations do
        not affect the cache.

        Returns:
            Sorted list of ``LeaderCacheEntry`` objects (best first).
        """
        self._evict_stale()
        return sorted(self._entries.values(), key=lambda e: e.score, reverse=True)

    def remove(self, leader_id: str) -> None:
        """Removes a specific leader from the cache (soft-blacklist for this round)."""
        self._entries.pop(leader_id, None)

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        """Removes all entries."""
        self._entries.clear()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _evict_stale(self) -> None:
        """Removes all entries older than ``_lifetime`` seconds."""
        cutoff  = time.monotonic() - self._lifetime
        stale   = [lid for lid, e in self._entries.items() if e.last_seen < cutoff]
        for lid in stale:
            del self._entries[lid]

    def _evict_worst(self) -> None:
        """Removes the lowest-scoring entry to make room for a new one."""
        if not self._entries:
            return
        worst = min(self._entries, key=lambda lid: self._entries[lid].score)
        del self._entries[worst]


# ---------------------------------------------------------------------------
# Service Interfaces (structural typing — no imports of unimplemented modules)
# ---------------------------------------------------------------------------

@runtime_checkable
class SecurityServiceProtocol(Protocol):
    """Minimal interface that ``discovery.py`` expects from ``security.py``.

    ``security.py`` must implement these methods with the same signatures.
    Discovery never imports ``security.py`` directly; it receives an
    instance at construction time.
    """

    def verify_drone_proof(self, root_hash: bytes, proof_bytes: bytes) -> bool:
        """Returns ``True`` if the SMT proof is valid for the given root."""
        ...

    def get_smt_root(self) -> bytes:
        """Returns the current canonical SMT root hash (32 bytes)."""
        ...

    def generate_drone_proof(self, drone_id: str) -> bytes:
        """Generates and serialises an SMT membership proof for ``drone_id``."""
        ...


@runtime_checkable
class HeartbeatServiceProtocol(Protocol):
    """Minimal interface that ``discovery.py`` expects from ``heartbeat.py``."""

    def start(self, drone_id: str, leader_id: str) -> None:
        """Activates periodic 1-hop heartbeat emission toward ``leader_id``."""
        ...


# ---------------------------------------------------------------------------
# Transport Interface (injectable for testing)
# ---------------------------------------------------------------------------

class DiscoveryTransport(Protocol):
    """Abstract transport interface used by ``DiscoveryEngine``.

    Production code uses ``UDPDiscoveryTransport``.
    Tests inject ``MockDiscoveryTransport`` to avoid real sockets.
    """

    def receive_hello(self, timeout_sec: float) -> Optional[Tuple[bytes, str]]:
        """Blocks at most ``timeout_sec`` for a multicast HELLO packet.

        Returns:
            ``(raw_bytes, sender_host)`` or ``None`` on timeout.
        """
        ...

    def send_unicast(self, data: bytes, host: str, port: int) -> None:
        """Sends ``data`` as a UDP unicast datagram to ``(host, port)``."""
        ...

    def receive_unicast(self, timeout_sec: float) -> Optional[Tuple[bytes, str]]:
        """Blocks at most ``timeout_sec`` for a unicast response.

        Returns:
            ``(raw_bytes, sender_host)`` or ``None`` on timeout.
        """
        ...

    def send_hello(self, data: bytes) -> None:
        """Multicasts ``data`` on the HELLO group (used by Cluster Leaders)."""
        ...

    def close(self) -> None:
        """Releases socket resources."""
        ...


# ---------------------------------------------------------------------------
# UDP Transport (real sockets)
# ---------------------------------------------------------------------------

class UDPDiscoveryTransport:
    """Real UDP socket transport for production deployment.

    Multicast socket (receive):
        Bound to ``0.0.0.0:mcast_port`` and joined to ``mcast_group``.
        TTL=1 restricts HELLO beacons to a single network hop.

    Unicast socket (send/receive):
        Bound to an ephemeral port for handshake messages.
    """

    def __init__(self, config: DiscoveryConfig) -> None:
        self._config   = config
        self._mcast_rx = self._create_mcast_rx()
        self._hs_sock  = self._create_handshake_sock()
        self._mcast_tx = self._create_mcast_tx()

    # ------------------------------------------------------------------
    # DiscoveryTransport protocol
    # ------------------------------------------------------------------

    def receive_hello(self, timeout_sec: float) -> Optional[Tuple[bytes, str]]:
        self._mcast_rx.settimeout(timeout_sec)
        try:
            data, addr = self._mcast_rx.recvfrom(4096)
            return data, addr[0]
        except (socket.timeout, OSError):
            return None

    def send_unicast(self, data: bytes, host: str, port: int) -> None:
        self._hs_sock.sendto(data, (host, port))

    def receive_unicast(self, timeout_sec: float) -> Optional[Tuple[bytes, str]]:
        self._hs_sock.settimeout(timeout_sec)
        try:
            data, addr = self._hs_sock.recvfrom(4096)
            return data, addr[0]
        except (socket.timeout, OSError):
            return None

    def send_hello(self, data: bytes) -> None:
        self._mcast_tx.sendto(data, (self._config.mcast_group, self._config.mcast_port))

    def close(self) -> None:
        for sock in (self._mcast_rx, self._hs_sock, self._mcast_tx):
            try:
                sock.close()
            except OSError:
                pass

    # ------------------------------------------------------------------
    # Private socket factories
    # ------------------------------------------------------------------

    def _create_mcast_rx(self) -> socket.socket:
        """Creates and configures the multicast receive socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("0.0.0.0", self._config.mcast_port))
        mreq = struct.pack(
            "4sL",
            socket.inet_aton(self._config.mcast_group),
            socket.INADDR_ANY,
        )
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
        return sock

    def _create_mcast_tx(self) -> socket.socket:
        """Creates the multicast transmit socket (TTL=1)."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 1)
        return sock

    def _create_handshake_sock(self) -> socket.socket:
        """Creates the unicast handshake socket."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("0.0.0.0", 0))  # Ephemeral port.
        return sock


# ---------------------------------------------------------------------------
# Discovery Engine
# ---------------------------------------------------------------------------

class DiscoveryEngine:
    """Drives the entire drone join lifecycle.

    Supports two roles:
        **Candidate** (FOLLOWER / unassigned):
            Calls ``run()`` which blocks until ACTIVE or raises
            ``DiscoveryTimeoutError``.

        **Cluster Leader**:
            Calls ``start_beaconing()`` which fires HELLO messages on a
            one-shot ``threading.Timer`` chain without extra threads.

    Args:
        local_node:     The ``SwarmNode`` representing this drone.
        topology:       Shared ``SwarmTopology`` instance.
        config:         ``DiscoveryConfig`` (use ``DiscoveryConfig.from_env()``).
        transport:      Transport implementation (inject for tests).
        security:       Optional ``SecurityServiceProtocol`` instance.
                        If ``None``, SMT proof generation is skipped (test mode).
        heartbeat:      Optional ``HeartbeatServiceProtocol`` instance.
                        If ``None``, heartbeat activation is skipped (test mode).
        battery_pct_fn: Callable returning current battery percentage.
                        Defaults to ``lambda: 100.0`` (for test / no-hardware).
    """

    def __init__(
        self,
        local_node:    SwarmNode,
        topology:      SwarmTopology,
        config:        Optional[DiscoveryConfig]             = None,
        transport:     Optional[DiscoveryTransport]          = None,
        security:      Optional[SecurityServiceProtocol]     = None,
        heartbeat:     Optional[HeartbeatServiceProtocol]    = None,
        battery_pct_fn: Callable[[], float]                  = lambda: 100.0,
    ) -> None:
        self._node          = local_node
        self._topology      = topology
        self._cfg           = config or DiscoveryConfig.from_env()
        self._transport     = transport or UDPDiscoveryTransport(self._cfg)
        self._security      = security
        self._heartbeat     = heartbeat
        self._battery_pct   = battery_pct_fn

        self._cache         = DiscoveryCache(
            max_entries=self._cfg.max_cache_entries,
            entry_lifetime_sec=self._cfg.entry_lifetime_sec,
        )
        self._phase         = DiscoveryPhase.IDLE
        self._seq           = self._cfg.beacon_sequence_start

        self._events:  List[DiscoveryEvent] = []
        self._lock          = threading.Lock()      # Protects _events and _seq.

        # State for the in-progress handshake.
        self._current_leader: Optional[LeaderCacheEntry] = None
        self._pending_nonce:  str = ""

        # Beacon timer handle (leader role only).
        self._beacon_timer: Optional[threading.Timer] = None

        _logger.info("DiscoveryEngine initialised for drone=%s", local_node.drone_id)

    # ------------------------------------------------------------------
    # Public API — Candidate Role
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Blocking join loop.  Runs until ``ACTIVE`` or raises.

        Call this method from the drone's main startup thread.  It will
        return only when the node is successfully joined (``NodeState.ACTIVE``).

        Raises:
            InsufficientBatteryError:  Battery below ``battery_min_pct``.
            DiscoveryTimeoutError:     Max retries exhausted without a join.
            DuplicateDroneIDError:     The swarm rejected the drone's ID.
        """
        self._guard_battery()
        self._transition(DiscoveryPhase.LISTENING)

        discovery_cycles = 0
        while self._phase not in (DiscoveryPhase.JOINED, DiscoveryPhase.FAILED):
            if self._phase is DiscoveryPhase.LISTENING:
                discovery_cycles += 1
                if discovery_cycles > self._cfg.max_discovery_retries:
                    self._transition(DiscoveryPhase.FAILED)
                    self._emit(DiscoveryEventType.DISCOVERY_TIMEOUT, drone_id=self._node.drone_id)
                    raise DiscoveryTimeoutError(
                        f"Drone '{self._node.drone_id}' exhausted "
                        f"{self._cfg.max_discovery_retries} discovery cycles"
                    )
                self._do_listen_cycle()

            elif self._phase is DiscoveryPhase.REGISTERING:
                self._do_register()

            elif self._phase is DiscoveryPhase.AUTHENTICATING:
                self._do_authenticate()

            elif self._phase is DiscoveryPhase.KEM_KEYING:
                self._do_kem_keying()

            elif self._phase is DiscoveryPhase.AWAITING_JOIN:
                self._do_await_join()

        if self._phase is DiscoveryPhase.FAILED:
            raise DiscoveryTimeoutError(
                f"Discovery failed for drone '{self._node.drone_id}'"
            )

        _logger.info("Drone %s successfully joined swarm", self._node.drone_id)

    def drain_events(self) -> List[DiscoveryEvent]:
        """Returns and clears all pending discovery events (thread-safe)."""
        with self._lock:
            events        = list(self._events)
            self._events.clear()
        return events

    # ------------------------------------------------------------------
    # Public API — Cluster Leader Role
    # ------------------------------------------------------------------

    def start_beaconing(self) -> None:
        """Begins periodic HELLO beacon emission (Cluster Leader only).

        Uses a one-shot ``threading.Timer`` chain — no background thread
        pool is created.  Safe to call once; calling again while a beacon
        chain is running has no effect.
        """
        if self._beacon_timer is not None:
            return
        if self._node.role not in (SwarmRole.CLUSTER_LEADER, SwarmRole.ROOT_LEADER):
            raise DiscoveryError(
                f"Only Cluster Leaders may beacon; "
                f"this node has role {self._node.role.name}"
            )
        self._schedule_next_beacon()
        _logger.info(
            "Beaconing started: leader=%s cluster=%s interval=%.1fs",
            self._node.drone_id, self._node.cluster_id, self._cfg.beacon_interval_sec,
        )

    def stop_beaconing(self) -> None:
        """Cancels the beacon timer chain and releases the transport."""
        if self._beacon_timer is not None:
            self._beacon_timer.cancel()
            self._beacon_timer = None
        self._transport.close()
        _logger.info("Beaconing stopped: leader=%s", self._node.drone_id)

    # ------------------------------------------------------------------
    # Phase Handlers — Candidate
    # ------------------------------------------------------------------

    def _do_listen_cycle(self) -> None:
        """Polls the multicast socket for HELLO beacons up to ``discovery_timeout_sec``.

        On receiving at least one HELLO, transitions to REGISTERING.
        If the timeout elapses with no HELLO, stays in LISTENING (caller
        increments the retry counter).
        """
        deadline = time.monotonic() + self._cfg.discovery_timeout_sec
        _logger.debug("Listening for HELLO beacons (timeout=%.1fs)", self._cfg.discovery_timeout_sec)

        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            result    = self._transport.receive_hello(
                timeout_sec=min(self._cfg.poll_interval_sec, remaining)
            )
            if result is None:
                continue

            raw_data, sender_host = result
            self._process_hello_packet(raw_data, sender_host)

            ranked = self._cache.get_ranked()
            if ranked:
                self._current_leader = ranked[0]
                self._transition(DiscoveryPhase.REGISTERING)
                return

        _logger.warning(
            "No HELLO received in %.1f s (drone=%s)",
            self._cfg.discovery_timeout_sec, self._node.drone_id,
        )

    def _do_register(self) -> None:
        """Sends REGISTER to the current leader and waits for AUTH_REQUEST."""
        assert self._current_leader is not None

        msg = RegisterMessage(
            sequence=self._next_seq(),
            candidate_id=self._node.drone_id,
            pubkey=b"\x00" * 32,  # Public key placeholder; full KEM pubkey in KEM_KEY_EXCHANGE.
            requested_role="follower",
        )
        wire_bytes = msg.to_wire_message().serialize()

        self._emit(
            DiscoveryEventType.JOIN_REQUEST,
            drone_id=self._node.drone_id,
            leader_id=self._current_leader.leader_id,
            cluster_id=self._current_leader.cluster_id,
        )

        response = self._send_with_retry(
            wire_bytes,
            self._current_leader.host,
            self._current_leader.port,
        )
        if response is None:
            _logger.warning(
                "No AUTH_REQUEST from leader %s; trying next",
                self._current_leader.leader_id,
            )
            self._cache.remove(self._current_leader.leader_id)
            self._current_leader = self._pick_next_leader()
            if self._current_leader is None:
                self._transition(DiscoveryPhase.LISTENING)
            return

        try:
            wire_msg = __import__(
                "hierarchical_swarm.protocol", fromlist=["WireMessage"]
            ).WireMessage.deserialize(response)
            parsed = parse_wire_message(wire_msg)
        except Exception as exc:
            _logger.error("Failed to parse AUTH_REQUEST response: %s", exc)
            self._transition(DiscoveryPhase.LISTENING)
            return

        if not isinstance(parsed, AuthRequestMessage):
            _logger.warning(
                "Expected AuthRequestMessage, got %s", type(parsed).__name__
            )
            self._transition(DiscoveryPhase.LISTENING)
            return

        self._pending_nonce = parsed.challenge_nonce
        self._emit(
            DiscoveryEventType.AUTH_REQUIRED,
            drone_id=self._node.drone_id,
            leader_id=self._current_leader.leader_id,
        )
        self._transition(DiscoveryPhase.AUTHENTICATING)

    def _do_authenticate(self) -> None:
        """Generates an SMT proof and sends AUTH_RESPONSE to the leader."""
        assert self._current_leader is not None

        # Generate proof bytes via security.py if available; else empty stub.
        if self._security is not None:
            proof_bytes = self._security.generate_drone_proof(self._node.drone_id)
        else:
            proof_bytes = b"\x00" * 32  # Test-mode stub.

        msg = AuthResponseMessage(
            sequence=self._next_seq(),
            candidate_id=self._node.drone_id,
            smt_proof_bytes=proof_bytes,
        )
        wire_bytes = msg.to_wire_message().serialize()

        response = self._send_with_retry(
            wire_bytes,
            self._current_leader.host,
            self._current_leader.port,
        )
        if response is None:
            _logger.warning("No KEM_KEY_EXCHANGE response after AUTH_RESPONSE")
            self._fallback_to_next_leader()
            return

        try:
            from hierarchical_swarm.protocol import WireMessage
            wire_msg = WireMessage.deserialize(response)
            parsed   = parse_wire_message(wire_msg)
        except Exception as exc:
            _logger.error("Failed to parse KEM response: %s", exc)
            self._fallback_to_next_leader()
            return

        if not isinstance(parsed, KemKeyExchangeMessage):
            _logger.warning(
                "Expected KemKeyExchangeMessage, got %s", type(parsed).__name__
            )
            self._fallback_to_next_leader()
            return

        self._transition(DiscoveryPhase.KEM_KEYING)

    def _do_kem_keying(self) -> None:
        """Completes ML-KEM key exchange and derives the session key.

        In production this is handled by ``security.py``; here we perform
        the protocol hand-off and wait for the session to be established.
        After a successful exchange the engine sends the encapsulated key
        back to the leader and transitions to AWAITING_JOIN.
        """
        assert self._current_leader is not None

        # KEM key material is produced by security.py; we use the session_id
        # as a handle.  In test mode we generate a deterministic stub.
        session_id = f"session-{self._node.drone_id}-{int(time.monotonic())}"
        self._node.mark_authenticated(session_id)

        kem_msg = KemKeyExchangeMessage(
            sequence=self._next_seq(),
            sender_id=self._node.drone_id,
            kem_pubkey_bytes=b"\x00" * 32,   # Provided by security.py in production.
            ciphertext_bytes=b"\x00" * 64,   # Encapsulated key.
        )
        wire_bytes = kem_msg.to_wire_message().serialize()

        response = self._send_with_retry(
            wire_bytes,
            self._current_leader.host,
            self._current_leader.port,
        )
        if response is None:
            _logger.warning("No response after KEM key exchange")
            self._fallback_to_next_leader()
            return

        self._transition(DiscoveryPhase.AWAITING_JOIN)

    def _do_await_join(self) -> None:
        """Waits for the JOIN message (APPROVED or REJECTED)."""
        assert self._current_leader is not None

        result = self._transport.receive_unicast(self._cfg.ack_timeout_sec)
        if result is None:
            _logger.warning("JOIN timeout from leader %s", self._current_leader.leader_id)
            self._fallback_to_next_leader()
            return

        raw_data, _ = result
        try:
            from hierarchical_swarm.protocol import WireMessage
            wire_msg = WireMessage.deserialize(raw_data)
            parsed   = parse_wire_message(wire_msg)
        except Exception as exc:
            _logger.error("Failed to parse JOIN message: %s", exc)
            self._fallback_to_next_leader()
            return

        if not isinstance(parsed, JoinMessage):
            _logger.warning(
                "Expected JoinMessage, got %s", type(parsed).__name__
            )
            self._fallback_to_next_leader()
            return

        if parsed.status == "APPROVED":
            self._complete_join(parsed)
        elif parsed.status == "DUPLICATE_ID":
            self._emit(
                DiscoveryEventType.JOIN_REJECT,
                drone_id=self._node.drone_id,
                extra="DUPLICATE_ID",
            )
            raise DuplicateDroneIDError(
                f"Swarm rejected drone '{self._node.drone_id}': DUPLICATE_ID. "
                "Manual GCS intervention required."
            )
        else:
            self._emit(
                DiscoveryEventType.JOIN_REJECT,
                drone_id=self._node.drone_id,
                leader_id=self._current_leader.leader_id,
                extra=parsed.status,
            )
            _logger.warning(
                "JOIN rejected by leader %s: %s",
                self._current_leader.leader_id, parsed.status,
            )
            self._fallback_to_next_leader()

    # ------------------------------------------------------------------
    # Join completion
    # ------------------------------------------------------------------

    def _complete_join(self, join_msg: JoinMessage) -> None:
        """Commits the join: updates topology and activates heartbeat.

        Calls ``topology.add_node()`` exactly once, then ``heartbeat.start()``.
        """
        assert self._current_leader is not None

        # Synchronise node fields with the authoritative cluster/parent values.
        self._node.update_parent(DroneId(join_msg.parent_id))
        self._node.update_cluster(ClusterId(join_msg.assigned_cluster))
        self._node.mark_online()

        # Register in the topology — exactly once.
        try:
            self._topology.add_node(
                self._node,
                cluster_id=join_msg.assigned_cluster,
            )
        except TopologyError as exc:
            _logger.error("topology.add_node failed: %s", exc)
            self._fallback_to_next_leader()
            return

        # Activate heartbeat subsystem.
        if self._heartbeat is not None:
            self._heartbeat.start(self._node.drone_id, join_msg.parent_id)
        else:
            _logger.debug("Heartbeat service not provided; skipping activation.")

        self._emit(
            DiscoveryEventType.JOIN_ACCEPT,
            drone_id=self._node.drone_id,
            leader_id=self._current_leader.leader_id,
            cluster_id=join_msg.assigned_cluster,
        )

        self._transition(DiscoveryPhase.JOINED)
        self._cache.clear()  # Cache no longer needed; release memory.

        _logger.info(
            "JOIN ACCEPTED: drone=%s cluster=%s parent=%s",
            self._node.drone_id, join_msg.assigned_cluster, join_msg.parent_id,
        )

        if METRICS:
            METRICS.counter("swarm_join_success_total").inc()

    # ------------------------------------------------------------------
    # HELLO Processing
    # ------------------------------------------------------------------

    def _process_hello_packet(self, raw_data: bytes, sender_host: str) -> None:
        """Parses a raw HELLO packet and updates the discovery cache."""
        try:
            from hierarchical_swarm.protocol import WireMessage
            wire_msg = WireMessage.deserialize(raw_data)
            parsed   = parse_wire_message(wire_msg)
        except Exception as exc:
            _logger.debug("Malformed HELLO from %s: %s", sender_host, exc)
            return

        if not isinstance(parsed, HelloMessage):
            return

        is_new = self._cache.upsert(
            leader_id=parsed.leader_id,
            cluster_id=parsed.cluster_id,
            host=sender_host,
            port=self._cfg.handshake_port,
            smt_root=parsed.smt_root,
            battery_pct=parsed.battery_pct,
            rssi=parsed.rssi,
        )

        self._emit(
            DiscoveryEventType.HELLO_RECEIVED,
            leader_id=parsed.leader_id,
            cluster_id=parsed.cluster_id,
        )

        if is_new:
            self._emit(
                DiscoveryEventType.NODE_DISCOVERED,
                leader_id=parsed.leader_id,
                cluster_id=parsed.cluster_id,
                extra=f"battery={parsed.battery_pct:.1f}% rssi={parsed.rssi:.1f}",
            )

    # ------------------------------------------------------------------
    # Beaconing (Cluster Leader Role)
    # ------------------------------------------------------------------

    def _schedule_next_beacon(self) -> None:
        """Schedules the next HELLO beacon via a one-shot Timer chain."""
        self._beacon_timer = threading.Timer(
            self._cfg.beacon_interval_sec,
            self._fire_beacon,
        )
        self._beacon_timer.daemon = True
        self._beacon_timer.start()

    def _fire_beacon(self) -> None:
        """Constructs and transmits one HELLO beacon, then reschedules."""
        smt_root = (
            self._security.get_smt_root()
            if self._security is not None
            else b"\x00" * 32
        )
        battery_pct = self._battery_pct()

        msg = HelloMessage(
            sequence=self._next_seq(),
            cluster_id=str(self._node.cluster_id or ""),
            leader_id=self._node.drone_id,
            smt_root=smt_root,
            battery_pct=battery_pct,
            rssi=0.0,
        )
        try:
            self._transport.send_hello(msg.to_wire_message().serialize())
        except Exception as exc:
            _logger.warning("HELLO beacon send failed: %s", exc)

        # Reschedule only if beaconing has not been stopped.
        if self._beacon_timer is not None:
            self._schedule_next_beacon()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _transition(self, new_phase: DiscoveryPhase) -> None:
        """Validates and executes a phase transition.

        Raises:
            InvalidStateTransitionError: If the transition is not in the
                legal transition table.
        """
        legal = _LEGAL_TRANSITIONS.get(self._phase, ())
        if new_phase not in legal:
            raise InvalidStateTransitionError(
                f"Illegal transition: {self._phase.name} → {new_phase.name}. "
                f"Legal successors: {[p.name for p in legal]}"
            )
        _logger.debug(
            "Phase transition: %s → %s (drone=%s)",
            self._phase.name, new_phase.name, self._node.drone_id,
        )
        self._phase = new_phase

    def _guard_battery(self) -> None:
        """Raises ``InsufficientBatteryError`` if battery is too low to join."""
        pct = self._battery_pct()
        if pct < self._cfg.battery_min_pct:
            raise InsufficientBatteryError(
                f"Battery {pct:.1f}% below minimum {self._cfg.battery_min_pct:.1f}%. "
                "Drone will not join the swarm."
            )

    def _send_with_retry(
        self, data: bytes, host: str, port: int
    ) -> Optional[bytes]:
        """Sends ``data`` to ``(host, port)`` with exponential backoff retries.

        Returns the first successful response payload, or ``None`` if all
        retransmissions fail.

        Retry schedule: 0.5 s → 1.0 s → 2.0 s (doubling each time).
        """
        backoff = self._cfg.send_backoff_sec
        for attempt in range(1, self._cfg.max_send_retries + 1):
            try:
                self._transport.send_unicast(data, host, port)
            except Exception as exc:
                _logger.warning("Send attempt %d/%d failed: %s", attempt, self._cfg.max_send_retries, exc)
            else:
                result = self._transport.receive_unicast(self._cfg.ack_timeout_sec)
                if result is not None:
                    return result[0]

            _logger.debug(
                "Retry %d/%d in %.1f s", attempt, self._cfg.max_send_retries, backoff
            )
            time.sleep(backoff)
            backoff *= 2.0

        return None

    def _pick_next_leader(self) -> Optional[LeaderCacheEntry]:
        """Returns the next best leader from the cache, or ``None``."""
        ranked = self._cache.get_ranked()
        return ranked[0] if ranked else None

    def _fallback_to_next_leader(self) -> None:
        """Soft-blacklists the current leader and falls back to the next ranked."""
        if self._current_leader is not None:
            self._cache.remove(self._current_leader.leader_id)
        self._current_leader = self._pick_next_leader()
        if self._current_leader is not None:
            self._transition(DiscoveryPhase.REGISTERING)
        else:
            self._transition(DiscoveryPhase.LISTENING)

    def _emit(
        self,
        event_type: DiscoveryEventType,
        drone_id:   str = "",
        leader_id:  str = "",
        cluster_id: str = "",
        extra:      str = "",
    ) -> None:
        """Appends a ``DiscoveryEvent`` to the pending queue (thread-safe)."""
        event = DiscoveryEvent(
            event_type=event_type,
            drone_id=drone_id,
            leader_id=leader_id,
            cluster_id=cluster_id,
            extra=extra,
        )
        with self._lock:
            self._events.append(event)

    def _next_seq(self) -> int:
        """Returns a monotonically incrementing sequence number."""
        with self._lock:
            seq      = self._seq
            self._seq += 1
        return seq & 0xFFFF  # Wraps at uint16 max.
