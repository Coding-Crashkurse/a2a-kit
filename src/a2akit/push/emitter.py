"""PushDeliveryEmitter - triggers webhook delivery on state transitions."""

from __future__ import annotations

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
            # Dispatch delivery INLINE (not via create_task) to preserve
            # event ordering. With a background task per transition,
            # the ``await get_configs_for_delivery`` becomes a scheduling
            # point where two sibling trigger tasks for back-to-back
            # transitions (e.g. working → completed) can interleave and
            # reach the per-config queue's ``put_nowait`` in reversed
            # order, delivering ``completed`` before ``working``.
            # The actual HTTP send is still async and sequential via
            # the WebhookDeliveryService per-config queue, so this path
            # only adds two awaits (load_task + get_configs) per
            # transition — it does not block on network I/O.
            try:
                task_snapshot = await self._storage.load_task(task_id)
                if task_snapshot:
                    configs = await self._push_store.get_configs_for_delivery(task_id)
                    if configs:
                        await self._delivery.deliver(configs, task_snapshot)
            except Exception:
                logger.exception("Push delivery trigger failed for task %s", task_id)

        return result

    async def shutdown(self) -> None:
        """No-op: delivery is dispatched inline, no background triggers to cancel."""

    async def send_event(self, task_id: str, event: StreamEvent) -> None:
        await self._inner.send_event(task_id, event)
