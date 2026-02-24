"""Union type for streaming events used by broker and endpoints."""

from __future__ import annotations

from a2a.types import Message, Task, TaskArtifactUpdateEvent, TaskStatusUpdateEvent

StreamEvent = Task | Message | TaskStatusUpdateEvent | TaskArtifactUpdateEvent

__all__ = ["StreamEvent"]
