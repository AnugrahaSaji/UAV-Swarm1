"""
Swarm Task Management and Execution.

This module provides the `TaskManager` class, responsible for creating,
dispatching, and tracking the status of tasks assigned to nodes within the
swarm. It includes data structures for representing tasks and their lifecycle.

The TaskManager is designed to:
- Provide a simple interface for submitting new tasks.
- Maintain a queue of pending tasks.
- Use the `RoutingManager` to dispatch tasks to the correct nodes.
- Handle incoming messages related to task status updates.
"""

import dataclasses
import threading
import time
import uuid
from collections import deque
from enum import Enum, auto
from typing import Any, Deque, Dict, Optional

from .messages import BaseSwarmMessage
from .routing import RoutingManager
from .topology import SwarmTopology
from .utils import DroneId, get_swarm_logger

# --- Setup ---

logger = get_swarm_logger(__name__)


class TaskStatus(Enum):
    """Defines the lifecycle status of a task."""
    PENDING = auto()
    DISPATCHED = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    CANCELED = auto()


class TaskPriority(Enum):
    """Defines the execution priority of a task."""
    LOW = auto()
    NORMAL = auto()
    HIGH = auto()
    CRITICAL = auto()


@dataclasses.dataclass
class Task:
    """
    Represents a single, assignable task within the swarm.

    Attributes:
        task_id: A unique identifier for the task.
        task_type: A string defining the type of task (e.g., 'GOTO_WAYPOINT').
        destination_id: The ID of the node the task is assigned to.
        payload: A dictionary containing task-specific data.
        priority: The execution priority of the task.
        status: The current status of the task in its lifecycle.
        created_at: The monotonic timestamp when the task was created.
        updated_at: The monotonic timestamp of the last status update.
    """
    task_id: str
    task_type: str
    destination_id: DroneId
    payload: Dict[str, Any]
    priority: TaskPriority
    status: TaskStatus = TaskStatus.PENDING
    created_at: float = dataclasses.field(default_factory=time.monotonic)
    updated_at: float = dataclasses.field(default_factory=time.monotonic)


class TaskManager:
    """
    Manages the lifecycle of tasks within the swarm.

    This class provides an interface to create and submit tasks, and it will
    (in future milestones) handle dispatching them to the appropriate nodes
    and tracking their execution status.
    """

    def __init__(
        self,
        topology: SwarmTopology,
        routing_manager: RoutingManager,
        local_node_id: DroneId,
        # The secure_channel is typed as 'Any' as it will be implemented
        # in a future milestone. It is the network interface.
        secure_channel: Any,
    ) -> None:
        """
        Initializes the TaskManager.

        Args:
            topology: A reference to the global `SwarmTopology` instance.
            routing_manager: A reference to the `RoutingManager` for message dispatch.
            local_node_id: The ID of the local node running this service.
            secure_channel: The communication channel for sending/receiving messages.
        """
        self._topology = topology
        self._routing_manager = routing_manager
        self._local_node_id = local_node_id
        self._secure_channel = secure_channel

        self._tasks: Dict[str, Task] = {}
        self._task_queue: Deque[Task] = deque()
        self._lock = threading.Lock()
        logger.info("TaskManager initialized for node %s.", local_node_id)

    def submit_task(
        self,
        task_type: str,
        destination_id: DroneId,
        payload: Dict[str, Any],
        priority: TaskPriority = TaskPriority.NORMAL,
    ) -> str:
        """
        Creates a new task and adds it to the pending queue.

        Args:
            task_type: A string defining the type of task.
            destination_id: The ID of the target node for the task.
            payload: A dictionary of data for the task.
            priority: The priority of the task.

        Returns:
            The unique ID of the newly created task.
        """
        task_id = str(uuid.uuid4())
        task = Task(
            task_id=task_id,
            task_type=task_type,
            destination_id=destination_id,
            payload=payload,
            priority=priority,
        )
        with self._lock:
            self._tasks[task_id] = task
            self._task_queue.append(task)
        logger.info("Submitted new task %s for node %s.", task_id, destination_id)
        return task_id

    def get_task_status(self, task_id: str) -> Optional[TaskStatus]:
        """
        Retrieves the status of a specific task.

        Args:
            task_id: The ID of the task to query.

        Returns:
            The `TaskStatus` if the task is found, otherwise None.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            return task.status if task else None

    def handle_task_message(self, message: BaseSwarmMessage) -> None:
        """
        Processes an incoming message related to a task.

        This method will handle messages such as task assignments from a leader
        or status updates from a subordinate.

        Args:
            message: The received swarm message.
        """
        raise NotImplementedError(
            "Task message handling is not yet implemented."
        )