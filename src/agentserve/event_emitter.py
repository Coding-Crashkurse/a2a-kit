"""EventEmitter abstraction â€" decouples TaskContext from Broker and Storage."""

from __future__ import annotations

from abc import ABC, abstractmethod

from a2a.types import Artifact, Message

from agentserve.schema import StreamEvent


class EventEmitter(ABC):
    """Thin interface that TaskContext uses to persist state and broadcast events.

    This keeps TaskContext unaware of Broker and Storage as separate concepts.
    """

    @abstractmethod
    async def update_task(
        self,
        task_id: str,
        state: str,
        *,
        artifacts: list[Artifact] | None = None,
        messages: list[Message] | None = None,
    ) -> None:
        """Persist a task state change (and optional artifacts/messages)."""

    @abstractmethod
    async def send_event(self, task_id: str, event: StreamEvent) -> None:
        """Broadcast a stream event to all subscribers of a task."""


class DefaultEventEmitter(EventEmitter):
    """Default implementation that delegates to a Broker and Storage pair."""

    def __init__(self, broker, storage) -> None:
        self._broker = broker
        self._storage = storage

    async def update_task(
        self,
        task_id: str,
        state: str,
        *,
        artifacts: list[Artifact] | None = None,
        messages: list[Message] | None = None,
    ) -> None:
        await self._storage.update_task(
            task_id, state=state, new_artifacts=artifacts, new_messages=messages,
        )

    async def send_event(self, task_id: str, event: StreamEvent) -> None:
        await self._broker.send_stream_event(task_id, event)