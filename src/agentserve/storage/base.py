"""Storage ABC, helpers, and exceptions."""

from __future__ import annotations

import logging
import types
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, Self

from typing_extensions import TypeVar

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


class TaskNotCancelableError(Exception):
    """Raised when a cancel is attempted on a task in a terminal state (A2A §3.1.5)."""


class UnsupportedOperationError(Exception):
    """Raised when an operation is not supported for the current task state."""


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
    next_page_token: str = Field(default="", serialization_alias="nextPageToken")
    page_size: int = Field(default=50, serialization_alias="pageSize")
    total_size: int = Field(default=0, serialization_alias="totalSize")


ContextT = TypeVar("ContextT", default=Any)


@dataclass(frozen=True)
class ArtifactWrite:
    """Per-artifact write descriptor with individual append semantics.

    Replaces the flat ``append_artifact: bool`` parameter on ``update_task``
    which applied a single flag to all artifacts in the list.
    """

    artifact: Artifact
    append: bool = False


def _is_agent_role(role: str | Role | None) -> bool:
    """Check whether a role value represents the agent role."""
    if role is None:
        return False
    return role == "agent" or getattr(role, "value", None) == "agent"


class Storage(ABC, Generic[ContextT]):
    """Abstract storage interface for A2A tasks.

    Subclasses MUST implement 5 abstract methods:
        load_task, list_tasks, create_task, append_message, update_task

    Optional helpers (default ``NotImplementedError``; override if useful):
        transition_state, append_messages, upsert_artifact

    Optional with sensible defaults:
        delete_task, delete_context, load_context, update_context
    """

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
        artifacts: list[ArtifactWrite] | None,
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
        self,
        task_id: str,
        history_length: int | None = None,
        *,
        include_artifacts: bool = True,
    ) -> Task | None: ...

    @abstractmethod
    async def list_tasks(self, query: ListTasksQuery) -> ListTasksResult: ...

    @abstractmethod
    async def create_task(self, context_id: str, message: Message) -> Task:
        """Create a brand-new task from an initial message."""

    @abstractmethod
    async def append_message(self, task_id: str, message: Message) -> Task:
        """Append a follow-up message to an existing task.

        Implementations MUST:
        - Raise ``TaskTerminalStateError`` if the task is in a terminal state.
        - Raise ``ContextMismatchError`` if ``message.context_id`` is set and
          does not match the task's ``context_id``.
        - Transition the task from ``input_required`` to ``submitted`` when
          a user message is appended (the agent asked for input, the user
          provided it, so the task re-enters the processing queue).
        - Validate message roles via ``_enforce_message_roles``: only agent
          messages are allowed when the task is **not** in ``input_required``.
        """

    async def submit_task(self, context_id: str, message: Message) -> Task:
        """Route to create_task or append_message based on message.task_id."""
        if message.task_id:
            return await self.append_message(message.task_id, message)
        return await self.create_task(context_id, message)

    async def transition_state(self, task_id: str, state: TaskState) -> Task:
        """Transition a task to a new state.

        Optional helper for in-memory backends that compose ``update_task``
        from smaller pieces.  DB backends typically handle the state
        transition inline within their ``update_task`` transaction and do
        **not** need to override this method.

        The default implementation raises ``NotImplementedError``.
        """
        raise NotImplementedError

    async def append_messages(self, task_id: str, messages: list[Message]) -> Task:
        """Append messages to a task's history.

        Optional helper for in-memory backends that compose ``update_task``
        from smaller pieces.  DB backends typically handle message insertion
        inline within their ``update_task`` transaction and do **not** need
        to override this method.

        **Important:** This method does **not** handle the
        ``input_required → submitted`` state transition — that logic lives
        in ``append_message`` (singular), which is the public API called by
        ``TaskManager`` for user follow-up messages.  ``append_messages``
        (plural) is an internal helper for agent-role messages inserted
        during task execution via ``update_task``.

        The default implementation raises ``NotImplementedError``.
        """
        raise NotImplementedError

    async def upsert_artifact(
        self, task_id: str, artifact: Artifact, *, append: bool = False
    ) -> Task:
        """Insert or update an artifact on a task.

        Optional helper for in-memory backends that compose ``update_task``
        from smaller pieces.  DB backends typically handle artifact upserts
        inline within their ``update_task`` transaction and do **not** need
        to override this method.

        Semantics based on ``append`` and whether an artifact with
        the same ``artifact_id`` already exists:

        - ``append=True`` + existing  → extend the existing artifact's parts.
        - ``append=False`` + existing → **replace** the entire artifact.
        - not existing                → insert a new artifact.

        The default implementation raises ``NotImplementedError``.
        """
        raise NotImplementedError

    @abstractmethod
    async def update_task(
        self,
        task_id: str,
        state: TaskState | None = None,
        *,
        artifacts: list[ArtifactWrite] | None = None,
        messages: list[Message] | None = None,
        task_metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Persist state change, artifacts, and messages atomically.

        When ``state`` is ``None`` the current state is preserved — useful
        for pure artifact or message appends without a state transition.

        Each :class:`ArtifactWrite` carries its own ``append`` flag so
        that callers can mix append and replace operations in a single
        call (e.g. append to artifact A while replacing artifact B).

        When ``task_metadata`` is provided, its key-value pairs are merged
        into the task's ``metadata`` dict.  This is used for internal
        framework flags (e.g. direct-reply markers) that must survive
        storage round-trips.

        Implementations MUST ensure that all changes are applied as a
        single atomic operation.  If any part fails, no changes must be
        visible.  For database backends this means a single transaction.

        Messages and artifacts are persisted before transitioning state so
        that a terminal state transition does not block their insertion.

        Implementations MUST raise ``TaskTerminalStateError`` when
        messages or artifacts are supplied for a task already in a
        terminal state.  A bare state transition to the same terminal
        state (without messages/artifacts) is a no-op.

        **Return value:** Backends MAY return a lightweight ``Task``
        containing only ``id`` and ``status``.  No caller depends on
        full history or artifact loading from the return value.
        """

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID. Returns True if the task existed."""
        raise NotImplementedError

    async def delete_context(self, context_id: str) -> int:
        """Delete all tasks in a context. Returns the number of deleted tasks."""
        raise NotImplementedError

    async def load_context(self, context_id: str) -> ContextT | None:
        """Load stored context for a context_id. Returns None if not found.

        Default implementation returns None (no context storage).
        """
        return None

    async def update_context(self, context_id: str, context: ContextT) -> None:
        """Store context for a context_id.

        Default implementation is a no-op.
        """
