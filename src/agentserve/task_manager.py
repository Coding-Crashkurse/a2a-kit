"""Task submission, streaming, querying, and cancellation."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from a2a.types import (
    Message,
    MessageSendParams,
    Part,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

from agentserve.broker import Broker, CancelRegistry
from agentserve.event_bus.base import EventBus
from agentserve.schema import DIRECT_REPLY_KEY, DirectReply, StreamEvent
from agentserve.storage import Storage
from agentserve.storage.base import (
    TERMINAL_STATES,
    ListTasksQuery,
    ListTasksResult,
    TaskNotCancelableError,
    TaskNotFoundError,
    UnsupportedOperationError,
)

logger = logging.getLogger(__name__)


def _find_direct_reply(task: Task) -> Message | None:
    """Extract direct-reply message if the worker used ``reply_directly()``.

    Checks ``task.metadata`` for the ``_agentserve_direct_reply`` marker
    whose value is the ``message_id`` of the direct-reply message.
    Returns ``None`` for normal task responses.
    """
    task_md = getattr(task, "metadata", None) or {}
    direct_reply_msg_id = task_md.get(DIRECT_REPLY_KEY)
    if not direct_reply_msg_id:
        return None
    if not task.history:
        return None
    for msg in reversed(task.history):
        if getattr(msg, "message_id", None) == direct_reply_msg_id:
            return msg
    return None


@dataclass
class TaskManager:
    """High-level API for submitting, streaming, and managing tasks."""

    broker: Broker
    storage: Storage
    event_bus: EventBus
    cancel_registry: CancelRegistry
    default_blocking_timeout_s: float = 30.0
    cancel_force_timeout_s: float = 60.0
    _background_tasks: set[asyncio.Task[Any]] = field(
        default_factory=set, init=False, repr=False
    )

    async def send_message(self, params: MessageSendParams) -> Task | Message:
        """Submit a task and optionally block until completion.

        Returns a ``Message`` when the worker used ``reply_directly()``
        (direct-message response without task tracking).
        Otherwise returns the ``Task``.
        """
        msg = params.message
        is_new = not msg.task_id
        context_id = msg.context_id or str(uuid.uuid4())
        task = await self.storage.submit_task(context_id, msg)

        params.message.context_id = context_id
        params.message.task_id = task.id

        direct_message: Message | None = None
        if params.configuration and params.configuration.blocking:
            # Subscribe BEFORE starting broker to avoid race condition:
            # events published between broker.run_task and subscribe would
            # be lost if we subscribed after.
            sub = await self.event_bus.subscribe(task.id)

            fut = asyncio.create_task(
                self.broker.run_task(params, is_new_task=is_new)
            )
            self._background_tasks.add(fut)
            fut.add_done_callback(self._background_tasks.discard)

            try:
                async with asyncio.timeout(self.default_blocking_timeout_s):
                    async for ev in sub:
                        if isinstance(ev, DirectReply):
                            direct_message = ev.message
                        if isinstance(ev, TaskStatusUpdateEvent) and ev.final:
                            break
            except TimeoutError:
                logger.info("Blocking wait timed out for task %s", task.id)
        else:
            # Non-blocking: just enqueue and return immediately
            fut = asyncio.create_task(
                self.broker.run_task(params, is_new_task=is_new)
            )
            self._background_tasks.add(fut)
            fut.add_done_callback(self._background_tasks.discard)

        if direct_message is not None:
            return direct_message

        history_len = getattr(
            getattr(params, "configuration", None), "history_length", None
        )
        latest = await self.storage.load_task(task.id, history_length=history_len)
        if latest is not None:
            reply = _find_direct_reply(latest)
            if reply is not None:
                return reply
        return latest or task

    async def stream_message(
        self, params: MessageSendParams
    ) -> AsyncGenerator[StreamEvent, None]:
        """Submit a task, yield initial snapshot, then stream live events.

        Subscribes to the event bus BEFORE starting the broker to prevent
        a race condition where early events could be lost.
        """
        msg = params.message
        is_new = not msg.task_id
        context_id = msg.context_id or str(uuid.uuid4())
        task = await self.storage.submit_task(context_id, msg)
        yield task

        params.message.context_id = context_id
        params.message.task_id = task.id

        # Subscribe BEFORE starting broker — prevents race condition
        # where events published between run_task and subscribe are lost.
        sub = await self.event_bus.subscribe(task.id)

        fut = asyncio.create_task(self.broker.run_task(params, is_new_task=is_new))
        self._background_tasks.add(fut)
        fut.add_done_callback(self._background_tasks.discard)

        async for ev in sub:
            yield ev

    async def subscribe_task(self, task_id: str) -> AsyncGenerator[StreamEvent, None]:
        """Subscribe to updates for an existing task.

        Yields the current task state first, then streams live events.
        Raises ``UnsupportedOperationError`` if the task is in a terminal state.
        """
        task = await self.storage.load_task(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found")
        if task.status.state in TERMINAL_STATES:
            raise UnsupportedOperationError(
                "Task is in a terminal state; cannot subscribe"
            )

        # Subscribe BEFORE yielding — prevents event loss between
        # load_task and subscribe.
        sub = await self.event_bus.subscribe(task_id)

        yield task
        async for ev in sub:
            yield ev

    async def get_task(
        self, task_id: str, history_length: int | None = None
    ) -> Task | None:
        """Load a single task by ID."""
        return await self.storage.load_task(task_id, history_length)

    async def list_tasks(self, query: ListTasksQuery) -> ListTasksResult:
        """Return filtered and paginated tasks."""
        return await self.storage.list_tasks(query)

    async def cancel_task(self, task_id: str) -> Task:
        """Request cancellation of a task and return its current state.

        Signals the cancel registry so the worker can cooperatively cancel.
        If the worker does not transition to ``canceled`` within
        ``cancel_force_timeout_s`` seconds, a background task will
        force the state transition to prevent tasks from being stuck
        in ``working`` forever.

        Raises:
            TaskNotFoundError: If the task does not exist.
            TaskNotCancelableError: If the task is already in a terminal state
                (A2A §3.1.5 — 409 Conflict).
        """
        task = await self.storage.load_task(task_id)
        if task is None:
            raise TaskNotFoundError(f"Task {task_id} not found")

        # Already terminal — spec requires an error, not silent success
        if task.status.state in TERMINAL_STATES:
            raise TaskNotCancelableError(
                f"Task {task_id} is in terminal state {task.status.state.value}"
            )

        await self.cancel_registry.request_cancel(task_id)

        # Instant cancel for tasks not yet picked up by the worker.
        if task.status.state == TaskState.submitted:
            cancel_message = Message(
                role=Role.agent,
                parts=[Part(TextPart(text="Task was canceled."))],
                message_id=str(uuid.uuid4()),
            )
            await self.storage.update_task(
                task_id, state=TaskState.canceled, messages=[cancel_message]
            )
            status = TaskStatus(
                state=TaskState.canceled,
                timestamp=datetime.now(UTC).isoformat(),
                message=cancel_message,
            )
            await self.event_bus.publish(
                task_id,
                TaskStatusUpdateEvent(
                    kind="status-update",
                    task_id=task_id,
                    context_id=task.context_id,
                    status=status,
                    final=True,
                ),
            )
            await self.event_bus.cleanup(task_id)
            # Do NOT call cancel_registry.cleanup() here — the worker
            # may still dequeue this operation and needs the cancel flag
            # to detect early termination.  Cleanup happens in the
            # worker's finally block.
            return await self.storage.load_task(task_id)

        # For working tasks: wait for worker cooperation + force-cancel fallback.
        fut = asyncio.create_task(
            self._force_cancel_after(task_id, self.cancel_force_timeout_s)
        )
        self._background_tasks.add(fut)
        fut.add_done_callback(self._background_tasks.discard)

        return await self.storage.load_task(task_id)

    async def _force_cancel_after(self, task_id: str, timeout: float) -> None:
        """Force-cancel a task if it hasn't reached a terminal state.

        Waits ``timeout`` seconds, then checks Storage.  If the task is
        still non-terminal, transitions it to ``canceled`` directly,
        publishes a final status event so SSE subscribers can close,
        and cleans up EventBus and CancelRegistry resources.
        """
        await asyncio.sleep(timeout)
        try:
            task = await self.storage.load_task(task_id)
            if task is None:
                return
            if task.status.state not in TERMINAL_STATES:
                logger.warning(
                    "Force-canceling task %s after %ss timeout "
                    "(worker did not cooperate)",
                    task_id,
                    timeout,
                )
                cancel_message = Message(
                    role=Role.agent,
                    parts=[Part(TextPart(text="Task was force-canceled after timeout."))],
                    message_id=str(uuid.uuid4()),
                )
                await self.storage.update_task(
                    task_id, state=TaskState.canceled, messages=[cancel_message]
                )
                status = TaskStatus(
                    state=TaskState.canceled,
                    timestamp=datetime.now(UTC).isoformat(),
                    message=cancel_message,
                )
                await self.event_bus.publish(
                    task_id,
                    TaskStatusUpdateEvent(
                        kind="status-update",
                        task_id=task_id,
                        context_id=task.context_id,
                        status=status,
                        final=True,
                    ),
                )
                await self.event_bus.cleanup(task_id)
                await self.cancel_registry.cleanup(task_id)
        except Exception:
            logger.exception("Force-cancel failed for task %s", task_id)