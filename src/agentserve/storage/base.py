"""Storage ABC, helpers, and exceptions."""

from __future__ import annotations

import logging
import types
from abc import ABC, abstractmethod
from typing import Self

from a2a.types import Artifact, Message, Role, Task, TaskState
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

TERMINAL_STATES: set[TaskState] = {
    TaskState.completed,
    TaskState.canceled,
    TaskState.failed,
    TaskState.rejected,
}


class TaskNotFoundError(Exception):
    """Raised when a referenced task does not exist."""


class TaskTerminalStateError(Exception):
    """Raised when an operation attempts to modify a terminal task."""


class TaskNotAcceptingMessagesError(Exception):
    """Raised when a task does not accept new user input in its current state."""

    def __init__(self, state: TaskState | None = None) -> None:
        self.state = state
        super().__init__("Task is not accepting messages")


class ContextMismatchError(Exception):
    """Raised when message contextId doesn't match the task's contextId."""


class ListTasksQuery(BaseModel):
    """Filter and pagination parameters for listing tasks."""

    context_id: str | None = None
    status: TaskState | None = None
    page_size: int = Field(default=50, ge=1, le=100)
    page_token: str | None = None
    history_length: int | None = None
    status_timestamp_after: str | None = None
    include_artifacts: bool = False


class ListTasksResult(BaseModel):
    """Paginated result from listing tasks."""

    tasks: list[Task] = Field(default_factory=list)
    next_page_token: str = ""
    page_size: int = 50
    total_size: int = 0


def _is_agent_role(role: str | Role | None) -> bool:
    """Check whether a role value represents the agent role."""
    if role is None:
        return False
    return role == "agent" or getattr(role, "value", None) == "agent"


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
    def _is_terminal(state: TaskState) -> bool:
        """Check whether a state is terminal."""
        return state in TERMINAL_STATES

    @staticmethod
    def _is_input_required(state: TaskState) -> bool:
        """Check whether a state is input-required."""
        return state is TaskState.input_required

    def _handle_terminal_update(
        self,
        current: TaskState,
        new_state: TaskState,
        artifacts: list[Artifact] | None,
        messages: list[Message] | None,
    ) -> bool:
        """Return True if the update is a no-op on a terminal task, raise if invalid."""
        if not self._is_terminal(current):
            return False
        if self._is_terminal(new_state) and not artifacts and not messages:
            return True
        raise TaskTerminalStateError("task is terminal")

    def _enforce_message_roles(
        self, current: TaskState, messages: list[Message]
    ) -> None:
        """Raise if non-agent messages are sent to a task not in input-required state."""
        if not messages:
            return
        if not self._is_input_required(current):
            if not all(_is_agent_role(getattr(m, "role", None)) for m in messages):
                raise TaskNotAcceptingMessagesError(current)

    @abstractmethod
    async def load_task(
        self, task_id: str, history_length: int | None = None
    ) -> Task | None: ...

    @abstractmethod
    async def list_tasks(self, query: ListTasksQuery) -> ListTasksResult: ...

    @abstractmethod
    async def create_task(self, context_id: str, message: Message) -> Task:
        """Create a brand-new task from an initial message."""

    @abstractmethod
    async def append_message(self, task_id: str, message: Message) -> Task:
        """Append a follow-up message to an existing task."""

    async def submit_task(self, context_id: str, message: Message) -> Task:
        """Route to create_task or append_message based on message.task_id."""
        if message.task_id:
            return await self.append_message(message.task_id, message)
        return await self.create_task(context_id, message)

    @abstractmethod
    async def update_task(
        self,
        task_id: str,
        state: TaskState,
        *,
        artifacts: list[Artifact] | None = None,
        messages: list[Message] | None = None,
        append_artifact: bool = False,
    ) -> None: ...
