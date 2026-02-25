"""In-memory storage backend for development and testing."""

from __future__ import annotations

import copy
import uuid
from datetime import UTC, datetime

from a2a.types import Artifact, Message, Task, TaskState, TaskStatus

from agentserve.storage.base import (
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
        if message.task_id:
            return await self.update_task(
                task_id=message.task_id,
                state=TaskState.submitted.value,
                new_messages=[message],
            )

        task_id = str(uuid.uuid4())
        message.task_id = task_id
        message.context_id = context_id

        task = Task(
            id=task_id,
            context_id=context_id,
            kind="task",
            status=TaskStatus(state=TaskState.submitted, timestamp=datetime.now(UTC).isoformat()),
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
            self._assign_messages(task, new_messages)

        task.status = TaskStatus(state=state_enum, timestamp=datetime.now(UTC).isoformat())
        if new_artifacts:
            task.artifacts.extend(new_artifacts)
        if new_messages:
            task.history.extend(new_messages)
        return task
