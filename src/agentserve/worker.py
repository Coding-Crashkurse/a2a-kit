"""Worker ABC, TaskContext, and TaskResult for agentserve."""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import anyio
from a2a.types import (
    Artifact,
    Message,
    MessageSendParams,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskIdParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from agentserve.broker import Broker, TaskOperation
from agentserve.event_emitter import DefaultEventEmitter, EventEmitter
from agentserve.storage import Storage

logger = logging.getLogger(__name__)


class TaskResult(BaseModel):
    """Return value from Worker.handle()."""

    text: str | None = None
    parts: list[Part] | None = None
    metadata: dict = Field(default_factory=dict)
    artifacts_emitted: bool = False


class TaskContext(BaseModel):
    """Execution context passed to Worker.handle()."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    task_id: str
    context_id: str | None = None
    message_id: str = ""
    user_text: str = ""
    parts: list[Any] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    _emitter: EventEmitter = PrivateAttr()
    _cancel_event: anyio.Event = PrivateAttr()

    @property
    def is_cancelled(self) -> bool:
        """Check whether cancellation has been requested for this task."""
        return self._cancel_event.is_set()

    async def send_status(self, message: str) -> None:
        """Emit an intermediate status update (state stays 'working')."""
        await self._emit_status(TaskState.working, message_text=message, final=False)

    async def complete(self, message: str | None = None) -> None:
        """Mark the task as completed."""
        await self._emitter.update_task(self.task_id, state=TaskState.completed.value)
        await self._emit_status(TaskState.completed, message_text=message)

    async def fail(self, reason: str) -> None:
        """Mark the task as failed."""
        await self._emitter.update_task(self.task_id, state=TaskState.failed.value)
        await self._emit_status(TaskState.failed, message_text=reason)

    async def request_input(self, question: str) -> None:
        """Transition to input-required state."""
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
        """Emit an artifact update event and persist it."""
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
        """Emit a single-text artifact chunk."""
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
    """Abstract base class â€" implement handle() to build an A2A agent."""

    @abstractmethod
    async def handle(self, ctx: TaskContext) -> TaskResult:
        """Process a task and return the result."""


class _WorkerAdapter:
    """Bridges a user Worker to the internal broker loop."""

    def __init__(self, user_worker: Worker, broker: Broker, storage: Storage) -> None:
        """Store references to the worker, broker, and storage."""
        self._user_worker = user_worker
        self._broker = broker
        self._storage = storage
        self._cancel_events: dict[str, anyio.Event] = {}

    @asynccontextmanager
    async def run(self) -> AsyncIterator[None]:
        """Start the broker consumption loop as a background task."""
        async with anyio.create_task_group() as tg:
            tg.start_soon(self._broker_loop)
            try:
                yield
            finally:
                tg.cancel_scope.cancel()

    async def _broker_loop(self) -> None:
        """Continuously receive and dispatch broker operations."""
        async for op in self._broker.receive_task_operations():
            await self._dispatch(op)

    async def _dispatch(self, op: TaskOperation) -> None:
        """Route an operation to the appropriate handler."""
        try:
            if op.operation == "run":
                await self._run_task(op.params)
            elif op.operation == "cancel":
                await self._cancel_task(op.params)
        except Exception:
            task_id = self._extract_task_id(op.params)
            if task_id:
                try:
                    await self._storage.update_task(task_id, state="failed")
                except Exception:
                    logger.exception("Failed to mark task %s as failed", task_id)
            logger.exception("Worker error handling operation")

    async def _run_task(self, params: MessageSendParams) -> None:
        """Execute the user worker for a submitted task."""
        message = params.message
        task_id = message.task_id
        context_id = message.context_id
        if not task_id:
            raise ValueError("message.task_id is missing")

        cancel_event = self._cancel_events.setdefault(task_id, anyio.Event())
        if cancel_event.is_set():
            await self._mark_canceled(task_id, context_id)
            return

        ctx = self._build_context(message, cancel_event)

        await self._storage.update_task(task_id, state=TaskState.working.value)
        await ctx._emit_status(TaskState.working)

        try:
            result = await self._user_worker.handle(ctx)
            await self._finalize(ctx, result)
        except anyio.get_cancelled_exc_class():
            await self._mark_canceled(task_id, context_id)
        except Exception as exc:
            logger.exception("Worker error for task %s", task_id)
            await self._mark_failed(task_id, context_id, str(exc))
        finally:
            self._cancel_events.pop(task_id, None)

    async def _finalize(self, ctx: TaskContext, result: TaskResult) -> None:
        """Persist the final result and mark the task completed."""
        if result.artifacts_emitted:
            task = await self._storage.load_task(ctx.task_id)
            if task and task.status.state.value not in {
                "completed", "failed", "canceled", "rejected",
            }:
                await ctx.complete()
            return

        if result.parts:
            final_parts = result.parts
        elif result.text:
            final_parts = [Part(TextPart(text=result.text))]
        else:
            final_parts = [Part(TextPart(text="(no result)"))]

        artifact = Artifact(
            artifact_id="final-answer",
            parts=final_parts,
            metadata=result.metadata,
        )
        agent_message = Message(
            role=Role.agent,
            parts=final_parts,
            message_id=str(uuid.uuid4()),
            metadata=ctx.metadata,
        )
        await self._storage.update_task(
            ctx.task_id,
            state=TaskState.working.value,
            new_messages=[agent_message],
            new_artifacts=[artifact],
        )

        await self._broker.send_stream_event(
            ctx.task_id,
            TaskArtifactUpdateEvent(
                kind="artifact-update",
                task_id=ctx.task_id,
                context_id=ctx.context_id,
                artifact=artifact,
                append=False,
                last_chunk=True,
            ),
        )

        await ctx.complete()

    def _build_context(self, message: Message, cancel_event: anyio.Event) -> TaskContext:
        """Construct a TaskContext from a broker message."""
        user_text = self._extract_text(message.parts)
        ctx = TaskContext(
            task_id=message.task_id,
            context_id=message.context_id,
            message_id=message.message_id or "",
            user_text=user_text,
            parts=message.parts,
            metadata=message.metadata or {},
        )
        ctx._emitter = DefaultEventEmitter(self._broker, self._storage)
        ctx._cancel_event = cancel_event
        return ctx

    async def _cancel_task(self, params: TaskIdParams) -> None:
        """Signal cancellation for a task."""
        task_id = params.id
        if task_id:
            self._cancel_events.setdefault(task_id, anyio.Event()).set()

    async def _mark_canceled(self, task_id: str, context_id: str | None) -> None:
        """Persist canceled state and emit a final status event."""
        await self._storage.update_task(task_id, state=TaskState.canceled.value)
        status = TaskStatus(state=TaskState.canceled, timestamp=datetime.now(UTC).isoformat())
        await self._broker.send_stream_event(
            task_id,
            TaskStatusUpdateEvent(
                kind="status-update", task_id=task_id, context_id=context_id,
                status=status, final=True,
            ),
        )

    async def _mark_failed(self, task_id: str, context_id: str | None, reason: str) -> None:
        """Persist failed state and emit a final status event with the error."""
        await self._storage.update_task(task_id, state=TaskState.failed.value)
        status = TaskStatus(
            state=TaskState.failed,
            timestamp=datetime.now(UTC).isoformat(),
            message=Message(
                role=Role.agent,
                parts=[Part(TextPart(text=reason))],
                message_id=str(uuid.uuid4()),
            ),
        )
        await self._broker.send_stream_event(
            task_id,
            TaskStatusUpdateEvent(
                kind="status-update", task_id=task_id, context_id=context_id,
                status=status, final=True,
            ),
        )

    @staticmethod
    def _extract_text(parts: list[Part]) -> str:
        """Join all text parts of a message into a single string."""
        texts: list[str] = []
        for part in parts:
            try:
                text = part.root.text
            except AttributeError:
                continue
            if text:
                texts.append(text)
        return "\n".join(texts)

    @staticmethod
    def _extract_task_id(params: Any) -> str | None:
        """Try to extract a task_id from various param types."""
        if params is None:
            return None
        if hasattr(params, "id") and params.id:
            return params.id
        message = getattr(params, "message", None)
        if message:
            return getattr(message, "task_id", None) or getattr(message, "taskId", None)
        return None