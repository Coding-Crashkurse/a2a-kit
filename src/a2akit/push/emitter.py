"""PushDeliveryEmitter - triggers webhook delivery on state transitions."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from a2akit.event_emitter import EventEmitter

if TYPE_CHECKING:
    from a2a.types import Message, TaskState

    from a2akit.push.delivery import WebhookDeliveryService
    from a2akit.push.store import PushConfigStore
    from a2akit.schema import StreamEvent
    from a2akit.storage.base import ArtifactWrite, Storage

logger = logging.getLogger(__name__)


class PushDeliveryEmitter(EventEmitter):
    """Decorator that triggers webhook delivery on every state transition.

    Stacking order: PushDeliveryEmitter(TracingEmitter(HookableEmitter(DefaultEventEmitter)))
    """

    def __init__(
        self,
        inner: EventEmitter,
        push_store: PushConfigStore,
        delivery_service: WebhookDeliveryService,
        storage: Storage,
    ) -> None:
        self._inner = inner
        self._push_store = push_store
        self._delivery = delivery_service
        self._storage = storage
        self._background_tasks: set[asyncio.Task[None]] = set()

    async def update_task(
        self,
        task_id: str,
        state: TaskState | None = None,
        *,
        status_message: Message | None = None,
        artifacts: list[ArtifactWrite] | None = None,
        messages: list[Message] | None = None,
        task_metadata: dict[str, Any] | None = None,
        expected_version: int | None = None,
    ) -> int:
        result = await self._inner.update_task(
            task_id,
            state=state,
            status_message=status_message,
            artifacts=artifacts,
            messages=messages,
            task_metadata=task_metadata,
            expected_version=expected_version,
        )

        if state is not None:
            t = asyncio.create_task(self._maybe_deliver(task_id))
            self._background_tasks.add(t)
            t.add_done_callback(self._background_tasks.discard)

        return result

    async def _maybe_deliver(self, task_id: str) -> None:
        try:
            configs = await self._push_store.get_configs_for_delivery(task_id)
            if not configs:
                return
            task = await self._storage.load_task(task_id)
            if task:
                await self._delivery.deliver(configs, task)
        except Exception:
            logger.exception("Push delivery trigger failed for task %s", task_id)

    async def send_event(self, task_id: str, event: StreamEvent) -> None:
        await self._inner.send_event(task_id, event)
