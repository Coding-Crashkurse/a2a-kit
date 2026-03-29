"""In-memory event bus for single-process deployments."""

from __future__ import annotations

from collections import deque
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

import anyio
from a2a.types import TaskStatusUpdateEvent

from a2akit.config import Settings, get_settings
from a2akit.event_bus.base import EventBus
from a2akit.schema import StreamEvent

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from anyio.streams.memory import (
        MemoryObjectReceiveStream,
        MemoryObjectSendStream,
    )


@dataclass(frozen=True)
class _BufferedEvent:
    """An event with its assigned monotonic ID."""

    id: int
    event: StreamEvent


class InMemoryEventBus(EventBus):
    """In-memory fan-out event bus backed by anyio memory streams.

    Maintains a bounded per-task ring buffer of recent events for
    best-effort ``Last-Event-ID`` replay (REQ-06).
    """

    def __init__(
        self,
        event_buffer: int | None = None,
        *,
        replay_buffer_size: int | None = None,
        settings: Settings | None = None,
    ) -> None:
        """Initialize buffer size and internal state."""
        s = settings or get_settings()
        self._event_buffer = event_buffer if event_buffer is not None else s.event_buffer
        self._replay_buffer_size = (
            replay_buffer_size if replay_buffer_size is not None else s.event_replay_buffer
        )
        self._subs: dict[str, list[MemoryObjectSendStream[tuple[str, StreamEvent]]]] = {}
        self._subscriber_lock: anyio.Lock = anyio.Lock()
        # Per-task ring buffer for replay and monotonic counter for event IDs.
        self._replay_buffers: dict[str, deque[_BufferedEvent]] = {}
        self._event_counters: dict[str, int] = {}

    async def __aenter__(self) -> Self:
        """Acquire the subscriber lock."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        """Tear down (no-op for in-memory)."""

    async def publish(self, task_id: str, event: StreamEvent) -> str | None:
        """Fan out a stream event to all subscribers of a task.

        Assigns a monotonic event ID and buffers the event for replay.
        Returns the event ID as a string.
        """
        # Assign monotonic event ID.
        counter = self._event_counters.get(task_id, 0) + 1
        self._event_counters[task_id] = counter
        event_id = str(counter)

        # Buffer for replay.
        buf = self._replay_buffers.get(task_id)
        if buf is None:
            buf = deque(maxlen=self._replay_buffer_size)
            self._replay_buffers[task_id] = buf
        buf.append(_BufferedEvent(id=counter, event=event))

        # Fan out to live subscribers.
        async with self._subscriber_lock:
            subscribers = self._subs.get(task_id, [])
            if not subscribers:
                return event_id
            alive: list[MemoryObjectSendStream[tuple[str, StreamEvent]]] = []
            for s in subscribers:
                try:
                    await s.send((event_id, event))
                    alive.append(s)
                except (anyio.ClosedResourceError, anyio.BrokenResourceError):
                    pass
            if alive:
                self._subs[task_id] = alive
            else:
                self._subs.pop(task_id, None)
        return event_id

    @asynccontextmanager
    async def subscribe(
        self, task_id: str, *, after_event_id: str | None = None
    ) -> AsyncIterator[AsyncIterator[tuple[str | None, StreamEvent]]]:
        """Subscribe to stream events. Replays buffered events when after_event_id is provided."""
        send_stream, recv_stream = anyio.create_memory_object_stream[tuple[str, StreamEvent]](
            max_buffer_size=self._event_buffer
        )
        async with self._subscriber_lock:
            self._subs.setdefault(task_id, []).append(send_stream)
        try:
            yield self._iter_events(recv_stream, task_id, after_event_id)
        finally:
            async with self._subscriber_lock:
                lst = self._subs.get(task_id)
                if lst:
                    with suppress(ValueError):
                        lst.remove(send_stream)
                    if not lst:
                        self._subs.pop(task_id, None)
            await send_stream.aclose()
            await recv_stream.aclose()

    async def _iter_events(
        self,
        recv_stream: MemoryObjectReceiveStream[tuple[str, StreamEvent]],
        task_id: str,
        after_event_id: str | None,
    ) -> AsyncIterator[tuple[str | None, StreamEvent]]:
        """Replay buffered events (if requested), then yield live events.

        Tracks ``last_yielded_id`` to skip duplicates that can occur when
        an event is published between subscriber registration and the
        replay buffer snapshot.
        """
        last_yielded_id = 0

        # Replay phase: yield buffered events with ID > after_event_id.
        if after_event_id is not None:
            try:
                after_id = int(after_event_id)
            except (ValueError, TypeError):
                after_id = 0
            buf = self._replay_buffers.get(task_id)
            if buf:
                for buffered in list(buf):
                    if buffered.id > after_id:
                        yield (str(buffered.id), buffered.event)
                        last_yielded_id = buffered.id
                        if (
                            isinstance(buffered.event, TaskStatusUpdateEvent)
                            and buffered.event.final
                        ):
                            return

        # Live phase: yield events from the subscription stream,
        # skipping any already delivered during replay.
        async for event_id, ev in recv_stream:
            eid_int = int(event_id) if event_id else 0
            if eid_int <= last_yielded_id:
                continue
            yield (event_id, ev)
            if isinstance(ev, TaskStatusUpdateEvent) and ev.final:
                break

    async def cleanup(self, task_id: str) -> None:
        """Remove subscriber state and replay buffer for a completed task."""
        async with self._subscriber_lock:
            self._subs.pop(task_id, None)
        self._replay_buffers.pop(task_id, None)
        self._event_counters.pop(task_id, None)
