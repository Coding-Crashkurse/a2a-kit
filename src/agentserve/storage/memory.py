"""In-memory storage backend for development and testing."""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime

from a2a.types import Artifact, Message, Task, TaskState, TaskStatus

from agentserve.storage.base import (
    ContextMismatchError,
    ListTasksQuery,
    ListTasksResult,
    Storage,
    TaskNotFoundError,
)


class InMemoryStorage(Storage):
    """Simple in-memory storage for development and testing."""

    def __init__(self) -> None:
        """Initialize empty task store."""
        self.tasks: dict[str, Task] = {}

    def _assign_messages(self, task: Task, messages: list[Message]) -> None:
        """Bind messages to the task."""
        for msg_obj in messages:
            msg_obj.task_id = task.id
            msg_obj.context_id = task.context_id

    async def load_task(
        self, task_id: str, history_length: int | None = None
    ) -> Task | None:
        """Load a task by ID, optionally trimming history."""
        task = self.tasks.get(task_id)
        if not task:
            return None
        t = copy.deepcopy(task)
        if history_length and t.history:
            t.history = t.history[-history_length:]
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
            if query.history_length and t.history:
                t.history = t.history[-query.history_length :]
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
        existing = self.tasks.get(task_id)
        if (
            existing
            and message.context_id
            and existing.context_id != message.context_id
        ):
            raise ContextMismatchError(
                f"contextId {message.context_id!r} does not match "
                f"task {task_id!r} contextId {existing.context_id!r}"
            )
        await self.update_task(
            task_id=task_id,
            state=TaskState.submitted,
            messages=[message],
        )
        return self.tasks[task_id]

    async def update_task(
        self,
        task_id: str,
        state: TaskState,
        *,
        artifacts: list[Artifact] | None = None,
        messages: list[Message] | None = None,
        append_artifact: bool = False,
    ) -> None:
        """Update task state, append artifacts and messages."""
        task = self.tasks.get(task_id)
        if task is None:
            raise TaskNotFoundError("task not found")

        current = task.status.state

        if self._handle_terminal_update(current, state, artifacts, messages):
            return

        if messages:
            self._enforce_message_roles(current, messages)
            self._assign_messages(task, messages)

        task.status = TaskStatus(state=state, timestamp=datetime.now(UTC).isoformat())
        if artifacts:
            for new_artifact in artifacts:
                if append_artifact:
                    existing = next(
                        (
                            a
                            for a in task.artifacts
                            if a.artifact_id == new_artifact.artifact_id
                        ),
                        None,
                    )
                    if existing:
                        existing.parts.extend(new_artifact.parts)
                        continue
                task.artifacts.append(new_artifact)
        if messages:
            task.history.extend(messages)
