"""Persistence interfaces and in-memory backend for A2A tasks."""

from __future__ import annotations

import copy
import logging
import types
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Self

from a2a.types import Artifact, Message, Role, Task, TaskState, TaskStatus
from pydantic import BaseModel

logger = logging.getLogger(__name__)

TERMINAL_STATE_NAMES: set[str] = {"completed", "canceled", "failed", "rejected"}
ACCEPTS_INPUT_STATE_NAME: str = TaskState.input_required.value


class TaskNotFoundError(Exception):
    """Raised when a referenced task does not exist."""


class TaskTerminalStateError(Exception):
    """Raised when an operation attempts to modify a terminal task."""


class DuplicateMessageIdError(Exception):
    """Raised when a messageId is reused anywhere in the dataset."""


class MessageIdConflictError(Exception):
    """Raised when a messageId is bound to a different task."""


class TaskNotAcceptingMessagesError(Exception):
    """Raised when a task does not accept new user input in its current state."""

    def __init__(self, state: str | None = None) -> None:
        self.state = state
        super().__init__("Task is not accepting messages")


class MissingMessageIdError(Exception):
    """Raised when a message is missing a required messageId."""


def _utc_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(UTC).isoformat()


def _dump_list(objs: list[BaseModel]) -> list[dict]:
    """Serialize a list of Pydantic models to dicts."""
    return [o.model_dump(mode="json", exclude_none=True) for o in objs]


def _is_agent_role(role: str | Role | None) -> bool:
    """Check whether a role value represents the agent role."""
    if role is None:
        return False
    return role == "agent" or getattr(role, "value", None) == "agent"


def _require_message_id(msg: Message) -> str:
    """Extract and validate the messageId from a Message."""
    mid = msg.message_id
    if not mid:
        raise MissingMessageIdError("messageId is required.")
    return mid


def _new_status(state: TaskState) -> TaskStatus:
    """Create a new TaskStatus with the given state and current timestamp."""
    return TaskStatus(state=state, timestamp=_utc_iso())


class Storage(ABC):
    """Abstract storage interface for A2A tasks."""

    async def __aenter__(self) -> Self:
        """Enter the async context manager."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: types.TracebackType | None,
    ) -> bool:
        """Exit the async context manager."""
        return False

    @staticmethod
    def _is_terminal_name(name: str) -> bool:
        """Check whether a state name is terminal."""
        return name in TERMINAL_STATE_NAMES

    @staticmethod
    def _is_input_required_name(name: str) -> bool:
        """Check whether a state name is input-required."""
        return name == ACCEPTS_INPUT_STATE_NAME

    @staticmethod
    def _to_state_enum_strict(state: str) -> TaskState:
        """Convert a state string to a TaskState enum, raising on invalid values."""
        try:
            return TaskState(state)
        except ValueError as e:
            raise TypeError("state must be a valid TaskState string") from e

    def _handle_terminal_update(
        self,
        current_name: str,
        new_state_name: str,
        new_artifacts: list[Artifact] | None,
        new_messages: list[Message] | None,
    ) -> bool:
        """Return True if the update is a no-op on a terminal task, raise if invalid."""
        if not self._is_terminal_name(current_name):
            return False
        if self._is_terminal_name(new_state_name) and not new_artifacts and not new_messages:
            return True
        raise TaskTerminalStateError("task is terminal")

    def _enforce_message_roles(self, current_name: str, messages: list[Message]) -> None:
        """Raise if non-agent messages are sent to a task not in input-required state."""
        if not messages:
            return
        if not self._is_input_required_name(current_name):
            if not all(_is_agent_role(getattr(m, "role", None)) for m in messages):
                raise TaskNotAcceptingMessagesError(current_name)

    @abstractmethod
    async def load_task(self, task_id: str, history_length: int | None = None) -> Task | None: ...

    @abstractmethod
    async def list_tasks(self, limit: int = 50) -> list[Task]: ...

    @abstractmethod
    async def submit_task(self, context_id: str, message: Message) -> Task: ...

    @abstractmethod
    async def update_task(
        self,
        task_id: str,
        state: str,
        new_artifacts: list[Artifact] | None = None,
        new_messages: list[Message] | None = None,
    ) -> Task: ...


class InMemoryStorage(Storage):
    """Simple in-memory storage for development and testing."""

    def __init__(self) -> None:
        """Initialize empty task and message-id stores."""
        self.tasks: dict[str, Task] = {}
        self._message_ids: dict[str, str] = {}

    def _claim_message_id(self, message_id: str, task_id: str) -> None:
        """Reserve a messageId globally, raising on duplicates."""
        if message_id in self._message_ids:
            raise DuplicateMessageIdError("duplicate messageId")
        self._message_ids[message_id] = task_id

    def _claim_and_assign_messages(self, task: Task, messages: list[Message]) -> None:
        """Claim messageIds and bind messages to the task."""
        for msg_obj in messages:
            mid = _require_message_id(msg_obj)
            self._claim_message_id(mid, task.id)
            msg_obj.task_id = task.id
            msg_obj.context_id = task.context_id

    async def load_task(self, task_id: str, history_length: int | None = None) -> Task | None:
        """Load a task by ID, optionally trimming history."""
        task = self.tasks.get(task_id)
        if not task:
            return None
        t = copy.deepcopy(task)
        if history_length and t.history:
            t.history = t.history[-history_length:]
        return t

    async def list_tasks(self, limit: int = 50) -> list[Task]:
        """Return up to limit tasks."""
        return list(self.tasks.values())[: max(0, limit)]

    async def submit_task(self, context_id: str, message: Message) -> Task:
        """Create a new task or append to an existing one."""
        msg_id = _require_message_id(message)

        if message.task_id:
            return await self.update_task(
                task_id=message.task_id,
                state=TaskState.submitted.value,
                new_messages=[message],
            )

        task_id = str(uuid.uuid4())
        self._claim_message_id(msg_id, task_id)

        message.task_id = task_id
        message.context_id = context_id

        task = Task(
            id=task_id,
            context_id=context_id,
            kind="task",
            status=_new_status(TaskState.submitted),
            history=[message],
            artifacts=[],
        )
        self.tasks[task_id] = task
        return task

    async def update_task(
        self,
        task_id: str,
        state: str,
        new_artifacts: list[Artifact] | None = None,
        new_messages: list[Message] | None = None,
    ) -> Task:
        """Update task state, append artifacts and messages."""
        task = self.tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError("task not found")

        state_enum = self._to_state_enum_strict(state)
        current_name = task.status.state.value
        new_state_name = state_enum.value

        if self._handle_terminal_update(current_name, new_state_name, new_artifacts, new_messages):
            return task

        if new_messages:
            self._enforce_message_roles(current_name, new_messages)
            self._claim_and_assign_messages(task, new_messages)

        task.status = _new_status(state_enum)
        if new_artifacts:
            task.artifacts.extend(new_artifacts)
        if new_messages:
            task.history.extend(new_messages)
        return task
