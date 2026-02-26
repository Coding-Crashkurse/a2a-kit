"""Broker ABC and operation types for task scheduling."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
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

    @abstractmethod
    async def ack(self) -> None:
        """Acknowledge successful processing."""

    @abstractmethod
    async def nack(self) -> None:
        """Reject — return operation to queue for retry."""


class CancelScope(ABC):
    """Backend-agnostic cancellation handle."""

    @abstractmethod
    async def wait(self) -> None:
        """Block until cancellation is requested."""

    @abstractmethod
    def is_set(self) -> bool:
        """Check if cancellation was requested without blocking."""


class Broker(ABC):
    """Abstract broker for task scheduling and cancellation."""

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
    def receive_task_operations(self) -> AsyncIterator[OperationHandle]: ...

    @abstractmethod
    async def request_cancel(self, task_id: str) -> None:
        """Signal cancellation for a task through the broker."""

    @abstractmethod
    async def is_cancelled(self, task_id: str) -> bool:
        """Check if cancellation was requested for a task."""

    @abstractmethod
    def on_cancel(self, task_id: str) -> CancelScope:
        """Return a scope that signals when cancellation is requested."""

    async def cleanup_task(self, _task_id: str) -> None:
        """Release resources associated with a completed task.

        Default no-op; override as needed.
        """
