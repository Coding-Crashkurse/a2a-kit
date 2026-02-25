"""ContextFactory — builds TaskContextImpl from A2A Message objects."""

from __future__ import annotations

import anyio
from a2a.types import Message, Part

from agentserve.broker import Broker
from agentserve.event_emitter import DefaultEventEmitter
from agentserve.storage import Storage
from agentserve.worker.base import TaskContextImpl


class ContextFactory:
    """Translates an A2A Message into a clean TaskContextImpl."""

    def __init__(self, broker: Broker, storage: Storage) -> None:
        self._broker = broker
        self._storage = storage

    def build(self, message: Message, cancel_event: anyio.Event) -> TaskContextImpl:
        """Construct a TaskContextImpl from a broker message."""
        user_text = self._extract_text(message.parts)
        return TaskContextImpl(
            task_id=message.task_id,
            context_id=message.context_id,
            message_id=message.message_id or "",
            user_text=user_text,
            parts=message.parts,
            metadata=message.metadata or {},
            emitter=DefaultEventEmitter(self._broker, self._storage),
            cancel_event=cancel_event,
        )

    @staticmethod
    def _extract_text(parts: list[Part]) -> str:
        """Join all text parts of a message into a single string."""
        texts: list[str] = []
        for part in parts:
            try:
                text = part.root.text
            except AttributeError:
                continue
            if text:
                texts.append(text)
        return "\n".join(texts)
