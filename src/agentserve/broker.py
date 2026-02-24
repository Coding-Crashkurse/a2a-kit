"""Broker abstractions for task scheduling and stream event fan-out."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, suppress
from types import TracebackType
from typing import Generic, Literal, Self, TypeVar

import anyio
from a2a.types import MessageSendParams, TaskIdParams, TaskStatusUpdateEvent
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from pydantic import BaseModel

from agentserve.schema import StreamEvent

logger = logging.getLogger(__name__)

OperationT = TypeVar("OperationT")
ParamsT = TypeVar("ParamsT")


class _TaskOperation(BaseModel, Generic[OperationT, ParamsT]):
    """Generic wrapper for a broker operation with typed params."""

    operation: OperationT
    params: ParamsT


_RunTask = _TaskOperation[Literal["run"], MessageSendParams]
_CancelTask = _TaskOperation[Literal["cancel"], TaskIdParams]
TaskOperation = _RunTask | _CancelTask


class Broker(ABC):
    """Abstract broker for task scheduling and event fan-out."""

    @abstractmethod
    async def run_task(self, params: MessageSendParams) -> None: ...

    @abstractmethod
    async def cancel_task(self, params: TaskIdParams) -> None: ...

    @abstractmethod
    async def send_stream_event(self, task_id: str, event: StreamEvent) -> None: ...

    @abstractmethod
    def subscribe_to_stream(self, task_id: str) -> AsyncIterator[StreamEvent]: ...

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(self, exc_type: type[BaseException] | None, exc_value: BaseException | None, traceback: TracebackType | None) -> None: ...

    @abstractmethod
    def receive_task_operations(self) -> AsyncIterator[TaskOperation]: ...


class InMemoryBroker(Broker):
    """In-memory broker suitable for single-process deployments."""

    def __init__(self, ops_buffer: int = 1000, event_buffer: int = 200) -> None:
        """Initialize buffer sizes and internal state."""
        self._ops_buffer = ops_buffer
        self._event_buffer = event_buffer
        self._event_subscribers: dict[str, list[MemoryObjectSendStream[StreamEvent]]] = {}
        self._subscriber_lock: anyio.Lock | None = None
        self._aexit_stack: AsyncExitStack | None = None
        self._ops_write: MemoryObjectSendStream[TaskOperation] | None = None
        self._ops_read: MemoryObjectReceiveStream[TaskOperation] | None = None

    async def __aenter__(self) -> Self:
        """Create memory streams and acquire the subscriber lock."""
        self._aexit_stack = AsyncExitStack()
        await self._aexit_stack.__aenter__()
        self._ops_write, self._ops_read = anyio.create_memory_object_stream[TaskOperation](
            max_buffer_size=self._ops_buffer
        )
        await self._aexit_stack.enter_async_context(self._ops_write)
        await self._aexit_stack.enter_async_context(self._ops_read)
        self._subscriber_lock = anyio.Lock()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """Tear down the exit stack."""
        if self._aexit_stack is not None:
            await self._aexit_stack.__aexit__(exc_type, exc_value, traceback)

    async def run_task(self, params: MessageSendParams) -> None:
        """Enqueue a run-task operation."""
        await self._ops_write.send(_RunTask(operation="run", params=params))

    async def cancel_task(self, params: TaskIdParams) -> None:
        """Enqueue a cancel-task operation."""
        await self._ops_write.send(_CancelTask(operation="cancel", params=params))

    async def send_stream_event(self, task_id: str, event: StreamEvent) -> None:
        """Fan out a stream event to all subscribers of a task."""
        async with self._subscriber_lock:
            subscribers = self._event_subscribers.get(task_id, [])
            if not subscribers:
                return
            alive: list[MemoryObjectSendStream[StreamEvent]] = []
            for s in subscribers:
                try:
                    await s.send(event)
                    alive.append(s)
                except (anyio.ClosedResourceError, anyio.BrokenResourceError):
                    pass
            if alive:
                self._event_subscribers[task_id] = alive
            else:
                self._event_subscribers.pop(task_id, None)

    def subscribe_to_stream(self, task_id: str) -> AsyncIterator[StreamEvent]:
        """Return an async iterator of stream events for a task."""
        return self._subscribe_iter(task_id)

    async def _subscribe_iter(self, task_id: str) -> AsyncIterator[StreamEvent]:
        """Yield events until a final status event arrives."""
        send_stream, recv_stream = anyio.create_memory_object_stream[StreamEvent](
            max_buffer_size=self._event_buffer
        )
        async with self._subscriber_lock:
            self._event_subscribers.setdefault(task_id, []).append(send_stream)
        try:
            async with recv_stream:
                async for ev in recv_stream:
                    yield ev
                    if isinstance(ev, TaskStatusUpdateEvent) and ev.final:
                        break
        finally:
            async with self._subscriber_lock:
                lst = self._event_subscribers.get(task_id)
                if lst:
                    with suppress(ValueError):
                        lst.remove(send_stream)
                    if not lst:
                        self._event_subscribers.pop(task_id, None)
            await send_stream.aclose()

    def receive_task_operations(self) -> AsyncIterator[TaskOperation]:
        """Return an async iterator of queued task operations."""
        return self._receive_ops()

    async def _receive_ops(self) -> AsyncIterator[TaskOperation]:
        """Yield operations from the internal queue."""
        async with self._ops_read:
            async for op in self._ops_read:
                yield op
