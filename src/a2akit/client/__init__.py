"""Public API for a2akit client."""

from __future__ import annotations

from a2akit.client.base import A2AClient
from a2akit.client.errors import (
    A2AClientError,
    AgentCapabilityError,
    AgentNotFoundError,
    NotConnectedError,
    ProtocolError,
    TaskNotCancelableError,
    TaskNotFoundError,
    TaskTerminalError,
)
from a2akit.client.result import ArtifactInfo, ClientResult, ListResult, StreamEvent

__all__ = [
    "A2AClient",
    "A2AClientError",
    "AgentCapabilityError",
    "AgentNotFoundError",
    "ArtifactInfo",
    "ClientResult",
    "ListResult",
    "NotConnectedError",
    "ProtocolError",
    "StreamEvent",
    "TaskNotCancelableError",
    "TaskNotFoundError",
    "TaskTerminalError",
]
