"""Storage ABC, helpers, and exceptions."""

from __future__ import annotations

import logging
import types
from abc import ABC, abstractmethod
from typing import Self

from a2a.types import Artifact, Message, Role, Task, TaskState

logger = logging.getLogger(__name__)

TERMINAL_STATE_NAMES: set[str] = {"completed", "canceled", "failed", "rejected"}
ACCEPTS_INPUT_STATE_NAME: str = TaskState.input_required.value


class TaskNotFoundError(Exception):
    """Raised when a referenced task does not exist."""


class TaskTerminalStateError(Exception):
    """Raised when an operation attempts to modify a terminal task."""


class TaskNotAcceptingMessagesError(Exception):
    """Raised when a task does not accept new user input in its current state."""

    def __init__(self, state: str | None = None) -> None:
        self.state = state
        super().__init__("Task is not accepting messages")


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
