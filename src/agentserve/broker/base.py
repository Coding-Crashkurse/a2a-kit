"""Broker ABC, CancelRegistry, and operation types for task scheduling."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, AsyncIterator
from types import TracebackType
from typing import Generic, Literal, Self, TypeVar

from a2a.types import MessageSendParams
from pydantic import BaseModel

logger = logging.getLogger(__name__)

OperationT = TypeVar("OperationT")
ParamsT = TypeVar("ParamsT")


class _TaskOperation(BaseModel, Generic[OperationT, ParamsT]):
    """Generic wrapper for a broker operation with typed params."""

    operation: OperationT
    params: ParamsT


class _RunTask(_TaskOperation[Literal["run"], MessageSendParams]):
    """Run-task operation with optional new-task hint."""

    is_new_task: bool = False


TaskOperation = _RunTask


class OperationHandle(ABC):
    """Handle for acknowledging or rejecting a broker operation."""

    @property
    @abstractmethod
    def operation(self) -> TaskOperation:
        """Return the wrapped operation."""

    @property
    @abstractmethod
    def attempt(self) -> int:
        """Delivery attempt number (1-based).

        InMemory always returns 1.  Backends with retry tracking
        (e.g. RabbitMQ, Redis) report the actual delivery count.
        """

    @abstractmethod
    async def ack(self) -> None:
        """Acknowledge successful processing."""

    @abstractmethod
    async def nack(self, *, delay_seconds: float = 0) -> None:
        """Reject — return operation to queue for retry.

        ``delay_seconds`` is a hint for backends that support delayed
        re-delivery (e.g. RabbitMQ dead-letter TTL, Redis delayed queue).
        InMemory ignores it and re-enqueues immediately.
        """


class CancelScope(ABC):
    """Backend-agnostic cancellation handle."""

    @abstractmethod
    async def wait(self) -> None:
        """Block until cancellation is requested."""

    @abstractmethod
    def is_set(self) -> bool:
        """Check if cancellation was requested without blocking."""


class CancelRegistry(ABC):
    """Registry for task cancellation signals."""

    @abstractmethod
    async def request_cancel(self, task_id: str) -> None:
        """Signal cancellation for a task."""

    @abstractmethod
    async def is_cancelled(self, task_id: str) -> bool:
        """Check if cancellation was requested."""

    @abstractmethod
    def on_cancel(self, task_id: str) -> CancelScope:
        """Return a scope that signals when cancellation is requested."""

    @abstractmethod
    async def cleanup(self, task_id: str) -> None:
        """Release resources for a completed task.

        MUST be idempotent. Multiple calls with the same task_id
        MUST NOT raise and MUST NOT affect resources for other tasks.
        Called exactly once per task lifecycle by WorkerAdapter.

        NO OTHER COMPONENT may call this method. TaskManager,
        Endpoints, and ContextFactory MUST NOT call cleanup.
        WorkerAdapter is the sole owner of cleanup lifecycle.

        Backends MUST implement this to avoid resource leaks
        (e.g. Redis key cleanup).
        """


class Broker(ABC):
    """Abstract broker for task scheduling."""

    @abstractmethod
    async def run_task(
        self, params: MessageSendParams, *, is_new_task: bool = False
    ) -> None: ...

    @abstractmethod
    async def __aenter__(self) -> Self: ...

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    @abstractmethod
    def receive_task_operations(self) -> AsyncGenerator[OperationHandle, None]:
        """Yield task operations from the queue.

        This is an async generator — implementations yield OperationHandle
        instances directly:

            async def receive_task_operations(self):
                async for msg in self._queue:
                    yield InMemoryOperationHandle(msg)

        The generator runs indefinitely until the broker is shut down.
        Connection lifecycle (connect, channel setup, teardown) is managed
        by the Broker's ``__aenter__``/``__aexit__``.
        """
