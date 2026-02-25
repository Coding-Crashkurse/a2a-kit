"""Worker ABC, TaskContext, TaskResult, and TaskContextImpl."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Any

import anyio
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from pydantic import BaseModel, Field

from agentserve.event_emitter import EventEmitter

logger = logging.getLogger(__name__)


class TaskResult(BaseModel):
    """Return value from Worker.handle()."""

    text: str | None = None
    parts: list[Part] | None = None
    metadata: dict = Field(default_factory=dict)
    artifacts_emitted: bool = False


class TaskContext(ABC):
    """Execution context passed to ``Worker.handle()``.

    Attributes:
        task_id:    Current task identifier.
        context_id: Optional conversation / context identifier.
        message_id: Identifier of the triggering message.
        user_text:  The user's input as plain text.
        parts:      Raw message parts (text, files, etc.).
        metadata:   Arbitrary metadata forwarded from the request.
    """

    task_id: str
    context_id: str | None
    message_id: str
    user_text: str
    parts: list[Any]
    metadata: dict

    @property
    @abstractmethod
    def is_cancelled(self) -> bool:
        """Check whether cancellation has been requested for this task."""

    @abstractmethod
    async def send_status(self, message: str) -> None:
        """Emit an intermediate status update (state stays 'working')."""

    @abstractmethod
    async def complete(self, message: str | None = None) -> None:
        """Mark the task as completed."""

    @abstractmethod
    async def fail(self, reason: str) -> None:
        """Mark the task as failed."""

    @abstractmethod
    async def request_input(self, question: str) -> None:
        """Transition to input-required state."""

    @abstractmethod
    async def emit_artifact(
        self,
        *,
        artifact_id: str,
        parts: list[Part],
        name: str | None = None,
        append: bool = False,
        last_chunk: bool = False,
        metadata: dict | None = None,
    ) -> None:
        """Emit an artifact update event and persist it."""

    @abstractmethod
    async def emit_text_artifact(
        self,
        text: str,
        *,
        artifact_id: str = "answer",
        append: bool = False,
        last_chunk: bool = False,
    ) -> None:
        """Emit a single-text artifact chunk."""


class TaskContextImpl(TaskContext):
    """Concrete implementation backed by an EventEmitter."""

    def __init__(
        self,
        *,
        task_id: str,
        context_id: str | None = None,
        message_id: str = "",
        user_text: str = "",
        parts: list[Any] | None = None,
        metadata: dict | None = None,
        emitter: EventEmitter,
        cancel_event: anyio.Event,
    ) -> None:
        self.task_id = task_id
        self.context_id = context_id
        self.message_id = message_id
        self.user_text = user_text
        self.parts = parts if parts is not None else []
        self.metadata = metadata if metadata is not None else {}
        self._emitter = emitter
        self._cancel_event = cancel_event

    @property
    def is_cancelled(self) -> bool:
        return self._cancel_event.is_set()

    async def send_status(self, message: str) -> None:
        await self._emit_status(TaskState.working, message_text=message, final=False)

    async def complete(self, message: str | None = None) -> None:
        await self._emitter.update_task(self.task_id, state=TaskState.completed.value)
        await self._emit_status(TaskState.completed, message_text=message)

    async def fail(self, reason: str) -> None:
        await self._emitter.update_task(self.task_id, state=TaskState.failed.value)
        await self._emit_status(TaskState.failed, message_text=reason)

    async def request_input(self, question: str) -> None:
        await self._emitter.update_task(self.task_id, state=TaskState.input_required.value)
        await self._emit_status(TaskState.input_required, message_text=question)

    async def emit_artifact(
        self,
        *,
        artifact_id: str,
        parts: list[Part],
        name: str | None = None,
        append: bool = False,
        last_chunk: bool = False,
        metadata: dict | None = None,
    ) -> None:
        artifact = Artifact(
            artifact_id=artifact_id,
            name=name,
            parts=parts,
            metadata=metadata or {},
        )
        if not append:
            await self._emitter.update_task(
                self.task_id,
                state=TaskState.working.value,
                artifacts=[artifact],
            )
        await self._emitter.send_event(
            self.task_id,
            TaskArtifactUpdateEvent(
                kind="artifact-update",
                task_id=self.task_id,
                context_id=self.context_id,
                artifact=artifact,
                append=append,
                last_chunk=last_chunk,
            ),
        )

    async def emit_text_artifact(
        self,
        text: str,
        *,
        artifact_id: str = "answer",
        append: bool = False,
        last_chunk: bool = False,
    ) -> None:
        await self.emit_artifact(
            artifact_id=artifact_id,
            parts=[Part(TextPart(text=text))],
            append=append,
            last_chunk=last_chunk,
        )

    async def _emit_status(
        self,
        state: TaskState,
        *,
        message_text: str | None = None,
        final: bool | None = None,
    ) -> None:
        """Build and broadcast a TaskStatusUpdateEvent."""
        if final is None:
            final = state in {
                TaskState.completed,
                TaskState.failed,
                TaskState.canceled,
                TaskState.rejected,
            }
        status = TaskStatus(
            state=state,
            timestamp=datetime.now(UTC).isoformat(),
            message=(
                Message(
                    role=Role.agent,
                    parts=[Part(TextPart(text=message_text))],
                    message_id=str(uuid.uuid4()),
                    metadata=self.metadata,
                )
                if message_text
                else None
            ),
        )
        await self._emitter.send_event(
            self.task_id,
            TaskStatusUpdateEvent(
                kind="status-update",
                task_id=self.task_id,
                context_id=self.context_id,
                status=status,
                final=final,
            ),
        )


class Worker(ABC):
    """Abstract base class — implement handle() to build an A2A agent."""

    @abstractmethod
    async def handle(self, ctx: TaskContext) -> TaskResult:
        """Process a task and return the result."""
