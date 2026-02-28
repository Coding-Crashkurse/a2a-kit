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

    Storage is pure CRUD — no business logic, no validation.
    All business rules (terminal guards, role enforcement, state
    transitions) live in :class:`TaskManager`.

    Subclasses MUST implement 3 abstract methods:
        load_task, create_task, update_task

    Optional with sensible defaults:
        list_tasks, delete_task, delete_context, load_context, update_context
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

    @abstractmethod
    async def load_task(
        self,
        task_id: str,
        history_length: int | None = None,
        *,
        include_artifacts: bool = True,
    ) -> Task | None: ...

    async def list_tasks(self, query: ListTasksQuery) -> ListTasksResult:
        """Return filtered and paginated tasks.

        Optional — backends that don't support listing may leave this
        as the default ``NotImplementedError``.
        """
        raise NotImplementedError

    @abstractmethod
    async def create_task(self, context_id: str, message: Message) -> Task:
        """Create a brand-new task from an initial message."""

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

        Pure CRUD — no business-logic validation.  All precondition
        checks (terminal guard, role enforcement, context mismatch)
        are handled by :class:`TaskManager` before this method is called.

        When ``state`` is ``None`` the current state MUST be preserved
        (keep-current semantics) — useful for pure artifact or message
        appends without a state transition.

        Each :class:`ArtifactWrite` carries its own ``append`` flag so
        that callers can mix append and replace operations in a single
        call (e.g. append to artifact A while replacing artifact B).

        When ``task_metadata`` is provided, its key-value pairs are
        merged into the task's ``metadata`` dict.

        Implementations MUST ensure that all changes are applied as a
        single atomic operation.  If any part fails, no changes must be
        visible.  For database backends this means a single transaction.

        **Return value:** The returned Task object is NOT guaranteed to
        contain full history or artifacts.  Use ``load_task()`` for
        reading back complete task state.
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
