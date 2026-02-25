"""WorkerAdapter — orchestrates broker loop, context building, execution, and finalization."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import anyio
from a2a.types import (
    Message,
    MessageSendParams,
    Part,
    Role,
    TaskIdParams,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

from agentserve.broker import Broker, TaskOperation
from agentserve.storage import Storage
from agentserve.worker.base import Worker
from agentserve.worker.context_factory import ContextFactory
from agentserve.worker.result_finalizer import ResultFinalizer

logger = logging.getLogger(__name__)


class WorkerAdapter:
    """Bridges a user Worker to the internal broker loop.

    Delegates context building to ContextFactory and result
    translation to ResultFinalizer — itself only orchestrates
    the lifecycle: receive ops, run/cancel, handle errors.
    """

    def __init__(self, user_worker: Worker, broker: Broker, storage: Storage) -> None:
        self._user_worker = user_worker
        self._broker = broker
        self._storage = storage
        self._context_factory = ContextFactory(broker, storage)
        self._finalizer = ResultFinalizer(broker, storage)
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

        ctx = self._context_factory.build(message, cancel_event)

        await self._storage.update_task(task_id, state=TaskState.working.value)
        await ctx._emit_status(TaskState.working)

        try:
            result = await self._user_worker.handle(ctx)
            await self._finalizer.finalize(ctx, result)
        except anyio.get_cancelled_exc_class():
            await self._mark_canceled(task_id, context_id)
        except Exception as exc:
            logger.exception("Worker error for task %s", task_id)
            await self._mark_failed(task_id, context_id, str(exc))
        finally:
            self._cancel_events.pop(task_id, None)

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
