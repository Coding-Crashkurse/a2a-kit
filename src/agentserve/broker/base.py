"""Broker ABC and operation types for task scheduling and event fan-out."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from types import TracebackType
from typing import Generic, Literal, Self, TypeVar

from a2a.types import MessageSendParams, TaskIdParams
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
