"""Client-specific exceptions for a2akit."""

from __future__ import annotations


class A2AClientError(Exception):
    """Base exception for all a2akit client errors."""


class AgentNotFoundError(A2AClientError):
    """No valid agent card found at the given URL."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"No valid agent found at {url}: {reason}")
        self.url = url
        self.reason = reason


class AgentCapabilityError(A2AClientError):
    """Agent does not support the requested capability."""

    def __init__(self, agent_name: str, capability: str) -> None:
        super().__init__(f"Agent '{agent_name}' does not support {capability}")
        self.agent_name = agent_name
        self.capability = capability


class NotConnectedError(A2AClientError):
    """Client method called before connect() / __aenter__."""

    def __init__(self) -> None:
        super().__init__(
            "Client is not connected. Use 'async with A2AClient(url)' "
            "or call 'await client.connect()' first."
        )


class TaskNotFoundError(A2AClientError):
    """Task ID does not exist on the server."""

    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task '{task_id}' not found")
        self.task_id = task_id


class TaskNotCancelableError(A2AClientError):
    """Task is in a terminal state and cannot be canceled."""

    def __init__(self, task_id: str, state: str = "unknown") -> None:
        super().__init__(f"Task '{task_id}' cannot be canceled (state: {state})")
        self.task_id = task_id
        self.state = state


class TaskTerminalError(A2AClientError):
    """Attempted to send a follow-up to a terminal task."""

    def __init__(self, task_id: str, state: str = "unknown") -> None:
        super().__init__(f"Task '{task_id}' is in terminal state '{state}'")
        self.task_id = task_id
        self.state = state


class ProtocolError(A2AClientError):
    """Unexpected protocol-level error."""

    def __init__(self, description: str) -> None:
        super().__init__(f"Protocol error: {description}")
        self.description = description


class ProtocolVersionMismatchError(A2AClientError):
    """Server rejected the client's A2A wire version.

    Raised when the server's ``/.well-known/agent-card.json`` announces a
    protocol version the client's transport doesn't speak, or when a
    request is rejected with HTTP 400 carrying the ``UNSUPPORTED_VERSION``
    reason (v0.3 JSON-RPC code ``-32009``, v1.0 ``google.rpc.Status`` with
    status ``INVALID_ARGUMENT``). ``client_version`` is what the client sent
    (or inferred from the card), ``server_version`` is what the server
    advertises / accepts.
    """

    def __init__(self, client_version: str, server_version: str, detail: str = "") -> None:
        msg = (
            f"A2A protocol version mismatch: client={client_version!r}, server={server_version!r}"
        )
        if detail:
            msg += f" — {detail}"
        super().__init__(msg)
        self.client_version = client_version
        self.server_version = server_version
        self.detail = detail
