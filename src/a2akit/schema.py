"""Union type for streaming events and shared constants."""

from __future__ import annotations

from dataclasses import dataclass

from a2a_pydantic import v10


@dataclass(frozen=True)
class DirectReply:
    """Internal event wrapper marking a Message as a direct reply.

    Emitted by ``reply_directly()`` so that TaskManager and SSE
    endpoints can distinguish a direct-reply message from a normal
    agent message (emitted by ``respond()``).
    """

    message: v10.Message


@dataclass(frozen=True)
class TerminalMarker:
    """Internal-only signal that a status-update is the final stream event.

    v1.0 drops the ``final`` field on ``TaskStatusUpdateEvent`` — streams
    close instead. But the internal event pipeline still needs to know when
    to close, so we wrap the terminal event in this marker. Wire encoders
    unwrap it: v1.0 serializes the bare event and closes; v0.3 sets
    ``final=True`` on the converted v03.TaskStatusUpdateEvent.
    """

    event: v10.TaskStatusUpdateEvent


StreamEvent = (
    v10.Task
    | v10.Message
    | v10.TaskStatusUpdateEvent
    | v10.TaskArtifactUpdateEvent
    | DirectReply
    | TerminalMarker
)

# Internal task-metadata key set by reply_directly().
# Stored in Task.metadata (not Message.metadata) so it survives
# storage round-trips without polluting user-facing message data.
DIRECT_REPLY_KEY = "_a2akit_direct_reply"

__all__ = ["DIRECT_REPLY_KEY", "DirectReply", "StreamEvent", "TerminalMarker"]
