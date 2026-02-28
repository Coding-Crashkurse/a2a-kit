"""EventEmitter abstraction — decouples TaskContext from EventBus and Storage."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from a2a.types import Message, Task, TaskState

from agentserve.event_bus.base import EventBus
from agentserve.schema import StreamEvent
from agentserve.storage.base import ArtifactWrite, Storage

logger = logging.getLogger(__name__)


class EventEmitter(ABC):
    """Thin interface that TaskContext uses to persist state and broadcast events.

    This keeps TaskContext unaware of EventBus and Storage as separate concepts.
    """

    @abstractmethod
    async def update_task(
        self,
        task_id: str,
        state: TaskState | None = None,
        *,
        artifacts: list[ArtifactWrite] | None = None,
        messages: list[Message] | None = None,
        task_metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Persist a task state change (and optional artifacts/messages).

        When ``state`` is ``None`` the current state is preserved.

        Note: The return value is currently unused by all callers in
        ``TaskContextImpl``.  Storage backends may return a lightweight
        Task shell (without full history/artifacts) to avoid expensive
        reads on write paths.
        """

    @abstractmethod
    async def send_event(self, task_id: str, event: StreamEvent) -> None:
        """Broadcast a stream event to all subscribers of a task."""


class DefaultEventEmitter(EventEmitter):
    """Default implementation that delegates to an EventBus and Storage pair.

    Storage write is authoritative. EventBus failure is logged but not raised,
    providing at-least-once delivery semantics for Storage and best-effort for EventBus.
    """

    def __init__(self, event_bus: EventBus, storage: Storage) -> None:
        self._event_bus = event_bus
        self._storage = storage

    async def update_task(
        self,
        task_id: str,
        state: TaskState | None = None,
        *,
        artifacts: list[ArtifactWrite] | None = None,
        messages: list[Message] | None = None,
        task_metadata: dict[str, Any] | None = None,
    ) -> Task:
        """Persist a task state change via storage."""
        return await self._storage.update_task(
            task_id,
            state=state,
            artifacts=artifacts,
            messages=messages,
            task_metadata=task_metadata,
        )

    async def send_event(self, task_id: str, event: StreamEvent) -> None:
        """Broadcast a stream event via event bus (best-effort)."""
        try:
            await self._event_bus.publish(task_id, event)
        except Exception:
            logger.exception("Failed to publish event for task %s", task_id)
