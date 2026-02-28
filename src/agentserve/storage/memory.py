"""In-memory storage backend for development and testing."""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime
from typing import Any

from a2a.types import Artifact, Message, Task, TaskState, TaskStatus

from agentserve.storage.base import (
    ArtifactWrite,
    ContextMismatchError,
    ContextT,
    ListTasksQuery,
    ListTasksResult,
    Storage,
    TaskNotFoundError,
    TaskTerminalStateError,
)


class InMemoryStorage(Storage[ContextT]):
    """Simple in-memory storage for development and testing."""

    def __init__(self) -> None:
        """Initialize empty task and context stores."""
        self.tasks: dict[str, Task] = {}
        self.contexts: dict[str, ContextT] = {}

    def _assign_messages(self, task: Task, messages: list[Message]) -> None:
        """Bind messages to the task."""
        for msg_obj in messages:
            msg_obj.task_id = task.id
            msg_obj.context_id = task.context_id

    @staticmethod
    def _trim_history(
        history: list[Message] | None, history_length: int | None
    ) -> list[Message] | None:
        """Trim history to the last N messages.

        Returns the full history when ``history_length`` is ``None``.
        Returns an empty list when ``history_length`` is ``0``.
        This avoids the Python falsy-check pitfall where ``0`` would
        previously skip trimming entirely.
        """
        if history_length is None or history is None:
            return history
        if history_length == 0:
            return []
        return history[-history_length:]

    async def load_task(
        self,
        task_id: str,
        history_length: int | None = None,
        *,
        include_artifacts: bool = True,
    ) -> Task | None:
        """Load a task by ID, optionally trimming history."""
        task = self.tasks.get(task_id)
        if not task:
            return None
        t = copy.deepcopy(task)
        t.history = self._trim_history(t.history, history_length)
        if not include_artifacts:
            t.artifacts = None
        return t

    async def list_tasks(self, query: ListTasksQuery) -> ListTasksResult:
        """Return filtered and paginated tasks."""
        all_tasks = sorted(
            self.tasks.values(),
            key=lambda t: t.status.timestamp or "",
            reverse=True,
        )

        filtered: list[Task] = []
        for t in all_tasks:
            if query.context_id and t.context_id != query.context_id:
                continue
            if query.status and t.status.state != query.status:
                continue
            if (
                query.status_timestamp_after
                and (t.status.timestamp or "") <= query.status_timestamp_after
            ):
                continue
            filtered.append(t)

        total_size = len(filtered)
        offset = int(query.page_token) if query.page_token else 0
        page = filtered[offset : offset + query.page_size]

        results: list[Task] = []
        for t in page:
            t = copy.deepcopy(t)
            t.history = self._trim_history(t.history, query.history_length)
            if not query.include_artifacts:
                t.artifacts = None
            results.append(t)

        next_offset = offset + query.page_size
        next_token = str(next_offset) if next_offset < total_size else ""

        return ListTasksResult(
            tasks=results,
            next_page_token=next_token,
            page_size=query.page_size,
            total_size=total_size,
        )

    async def create_task(self, context_id: str, message: Message) -> Task:
        """Create a brand-new task from an initial message."""
        task_id = str(uuid.uuid4())
        message.task_id = task_id
        message.context_id = context_id

        task = Task(
            id=task_id,
            context_id=context_id,
            kind="task",
            status=TaskStatus(
                state=TaskState.submitted, timestamp=datetime.now(UTC).isoformat()
            ),
            history=[message],
            artifacts=[],
        )
        self.tasks[task_id] = task
        return task

    async def append_message(self, task_id: str, message: Message) -> Task:
        """Append a follow-up message to an existing task."""
        task = self._get_task_or_raise(task_id)
        if message.context_id and task.context_id != message.context_id:
            raise ContextMismatchError(
                f"contextId {message.context_id!r} does not match "
                f"task {task_id!r} contextId {task.context_id!r}"
            )
        current = task.status.state
        if self._is_terminal(current):
            raise TaskTerminalStateError("task is terminal")
        if self._is_input_required(current):
            new_state = TaskState.submitted
        else:
            new_state = current
        self._enforce_message_roles(current, [message])
        self._assign_messages(task, [message])
        task.status = TaskStatus(
            state=new_state, timestamp=datetime.now(UTC).isoformat()
        )
        task.history.extend([message])
        return copy.deepcopy(task)

    def _get_task_or_raise(self, task_id: str) -> Task:
        """Return the task or raise TaskNotFoundError."""
        task = self.tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError("task not found")
        return task

    async def transition_state(self, task_id: str, state: TaskState) -> Task:
        """Transition a task to a new state."""
        task = self._get_task_or_raise(task_id)
        current = task.status.state
        if self._handle_terminal_update(current, state, None, None):
            return copy.deepcopy(task)
        task.status = TaskStatus(state=state, timestamp=datetime.now(UTC).isoformat())
        return copy.deepcopy(task)

    async def append_messages(self, task_id: str, messages: list[Message]) -> Task:
        """Append messages to a task's history."""
        task = self._get_task_or_raise(task_id)
        current = task.status.state
        if self._is_terminal(current):
            raise TaskTerminalStateError("task is terminal")
        self._enforce_message_roles(current, messages)
        self._assign_messages(task, messages)
        task.history.extend(messages)
        return copy.deepcopy(task)

    async def upsert_artifact(
        self, task_id: str, artifact: Artifact, *, append: bool = False
    ) -> Task:
        """Insert or update an artifact on a task."""
        task = self._get_task_or_raise(task_id)
        if self._is_terminal(task.status.state):
            raise TaskTerminalStateError("task is terminal")
        self._apply_artifact(task, artifact, append=append)
        return copy.deepcopy(task)

    async def update_task(
        self,
        task_id: str,
        state: TaskState | None = None,
        *,
        artifacts: list[ArtifactWrite] | None = None,
        messages: list[Message] | None = None,
        task_metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Atomically apply messages, artifacts, and state transition.

        When ``state`` is ``None`` the current state is preserved.
        All precondition checks run before any mutation so that a failure
        in one step never leaves the task in a partially-updated state.
        """
        task = self._get_task_or_raise(task_id)
        current = task.status.state
        effective_state = state if state is not None else current

        # 1. Terminal guard — must be FIRST
        if self._handle_terminal_update(current, effective_state, artifacts, messages):
            return copy.deepcopy(task)

        # 2. Validate all preconditions BEFORE any mutation
        if messages:
            self._enforce_message_roles(current, messages)
        # (artifacts have no precondition beyond terminal, already checked)

        # 3. Apply all mutations
        if messages:
            self._assign_messages(task, messages)
            task.history.extend(messages)

        if artifacts:
            for aw in artifacts:
                self._apply_artifact(task, aw.artifact, append=aw.append)

        if task_metadata:
            if task.metadata is None:
                task.metadata = {}
            task.metadata.update(task_metadata)

        if state is not None:
            task.status = TaskStatus(
                state=state, timestamp=datetime.now(UTC).isoformat()
            )

        return copy.deepcopy(task)

    def _apply_artifact(
        self, task: Task, artifact: Artifact, *, append: bool
    ) -> None:
        """Apply a single artifact upsert to the task (in-place)."""
        existing_idx = next(
            (
                i
                for i, a in enumerate(task.artifacts)
                if a.artifact_id == artifact.artifact_id
            ),
            None,
        )
        if existing_idx is not None:
            if append:
                task.artifacts[existing_idx].parts.extend(artifact.parts)
            else:
                task.artifacts[existing_idx] = artifact
        else:
            task.artifacts.append(artifact)

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task by ID. Returns True if the task existed."""
        return self.tasks.pop(task_id, None) is not None

    async def delete_context(self, context_id: str) -> int:
        """Delete all tasks in a context. Returns the number of deleted tasks."""
        to_delete = [tid for tid, t in self.tasks.items() if t.context_id == context_id]
        for tid in to_delete:
            del self.tasks[tid]
        self.contexts.pop(context_id, None)
        return len(to_delete)

    async def load_context(self, context_id: str) -> ContextT | None:
        """Load stored context for a context_id."""
        return self.contexts.get(context_id)

    async def update_context(self, context_id: str, context: ContextT) -> None:
        """Store context for a context_id."""
        self.contexts[context_id] = context
