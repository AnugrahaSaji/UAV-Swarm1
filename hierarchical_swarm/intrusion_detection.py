"""
Swarm Intrusion and Anomaly Detection.

This module provides the `IntrusionDetectionService` (IDS), which is responsible
for monitoring swarm behavior to detect anomalies and potential security threats.
It acts as a central nervous system for security-related events, collecting data
from various services and applying rules to identify suspicious patterns.

The IDS is designed to detect threats such as:
- Message flooding (Denial of Service attempts).
- Repeated authentication failures (e.g., invalid signatures).
- Malformed communication packets.
- Unexpected or illogical state transitions from nodes.

When a threat is detected, the IDS can take actions like logging alerts,
updating a node's trust score, or marking a node for revocation in the
`SwarmTopology`.
"""

import dataclasses
import threading
import time
from collections import defaultdict
from enum import Enum, auto
from typing import Any, DefaultDict, Dict, List, Optional

from .security import SecurityService
from .topology import SwarmTopology
from .utils import DroneId, NodeStatus, get_swarm_logger

# --- Setup ---

logger = get_swarm_logger(__name__)

DEFAULT_IDS_CHECK_INTERVAL_S = 10.0


class AnomalyType(Enum):
    """Defines the types of anomalies the IDS can detect."""
    SIGNATURE_VERIFICATION_FAILED = auto()
    MALFORMED_MESSAGE = auto()
    MESSAGE_FLOODING = auto()
    UNEXPECTED_ROLE_CHANGE = auto()
    RAPID_REJOIN = auto()


@dataclasses.dataclass
class AnomalyEvent:
    """Represents a single detected anomaly or suspicious event."""
    event_type: AnomalyType
    source_id: DroneId
    details: Dict[str, Any] = dataclasses.field(default_factory=dict)
    timestamp: float = dataclasses.field(default_factory=time.time)


class IntrusionDetectionService:
    """
    Monitors swarm activity for signs of intrusion or anomalous behavior.

    This service runs as a background thread, collecting and analyzing security-
    relevant events from across the swarm. It maintains a record of suspicious
    activities and can trigger defensive actions when predefined thresholds
    are exceeded.
    """

    def __init__(
        self,
        topology: SwarmTopology,
        security_service: SecurityService,
        local_node_id: DroneId,
        # The secure_channel is typed as 'Any' as it will be implemented
        # in a future milestone. It is the network interface.
        secure_channel: Any,
        check_interval: float = DEFAULT_IDS_CHECK_INTERVAL_S,
    ) -> None:
        """
        Initializes the IntrusionDetectionService.

        Args:
            topology: A reference to the global `SwarmTopology` instance.
            security_service: A reference to the `SecurityService` instance.
            local_node_id: The ID of the local node running this service.
            secure_channel: The communication channel for sending/receiving messages.
            check_interval: The interval in seconds for periodic analysis.
        """
        self._topology = topology
        self._security_service = security_service
        self._local_node_id = local_node_id
        self._secure_channel = secure_channel
        self._check_interval = check_interval

        self._lock = threading.Lock()
        self._events: List[AnomalyEvent] = []
        self._failed_verification_counts: DefaultDict[DroneId, int] = defaultdict(int)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        logger.info("IntrusionDetectionService initialized for node %s.", local_node_id)

    def start(self) -> None:
        """Starts the IDS in a background thread."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("IntrusionDetectionService is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("IntrusionDetectionService started with a %.1fs check interval.", self._check_interval)

    def stop(self) -> None:
        """Stops the IDS background thread."""
        if self._thread is None or not self._thread.is_alive():
            logger.info("IntrusionDetectionService is not running.")
            return

        self._stop_event.set()
        self._thread.join()
        logger.info("IntrusionDetectionService stopped.")

    def _run_loop(self) -> None:
        """The main loop for the IDS background thread."""
        while not self._stop_event.is_set():
            logger.debug("IDS performing periodic analysis.")
            # In a full implementation, this would analyze message rates,
            # node behavior patterns, etc.
            self._stop_event.wait(self._check_interval)

    def report_anomaly(self, event: AnomalyEvent) -> None:
        """
        Public method for other services to report a suspicious event.

        Args:
            event: An `AnomalyEvent` object describing the suspicious activity.
        """
        with self._lock:
            self._events.append(event)
            logger.warning("Anomaly reported: %s from node %s.", event.event_type.name, event.source_id)

            # Immediate reaction for certain critical events
            if event.event_type == AnomalyType.SIGNATURE_VERIFICATION_FAILED:
                self._failed_verification_counts[event.source_id] += 1
                self._check_failed_verification_threshold(event.source_id)

    def _check_failed_verification_threshold(self, drone_id: DroneId, threshold: int = 3) -> None:
        """
        Checks if a node has exceeded the threshold for failed signature verifications.

        Args:
            drone_id: The ID of the node to check.
            threshold: The number of failures that triggers an action.
        """
        count = self._failed_verification_counts[drone_id]
        if count >= threshold:
            logger.critical(
                "Node %s has exceeded the signature verification failure threshold (%d/%d). "
                "Marking as revoked.",
                drone_id, count, threshold
            )
            self._revoke_node(drone_id)

    def _revoke_node(self, drone_id: DroneId) -> None:
        """
        Marks a node as REVOKED in the swarm topology.

        This is a significant action that effectively bans the node from further
        participation in the swarm until its status is manually reset.

        Args:
            drone_id: The ID of the node to revoke.
        """
        node_to_update = self._topology.get_node(drone_id)
        if node_to_update:
            node_to_update.status = NodeStatus.REVOKED
            self._topology.add_or_update_node(node_to_update)
            logger.info("Node %s has been marked as REVOKED in the topology.", drone_id)
            # In a full implementation, a message would be broadcast to inform other nodes.
        else:
            logger.warning("Attempted to revoke node %s, but it was not found in the topology.", drone_id)
