"""Shared SSE parsing helper for client transports."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import httpx
from a2a.types import Task, TaskArtifactUpdateEvent, TaskStatusUpdateEvent

from a2akit.client.errors import ProtocolError
from a2akit.client.result import StreamEvent

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


async def parse_sse_stream(
    response: httpx.Response,
    *,
    unwrap_jsonrpc: bool = False,
) -> AsyncIterator[StreamEvent]:
    """Parse a text/event-stream response into StreamEvent objects.

    Args:
        response: httpx streaming response with content-type text/event-stream.
        unwrap_jsonrpc: If True, unwrap JSON-RPC envelopes before deserializing.

    Yields:
        StreamEvent wrappers around parsed protocol events.
    """
    try:
        current_event_id: str | None = None
        async for line in response.aiter_lines():
            line = line.strip()

            if line.startswith("id:"):
                current_event_id = line[len("id:") :].strip() or None
                continue

            if not line.startswith("data:"):
                continue

            payload = line[len("data:") :].strip()
            if not payload:
                continue

            try:
                raw = json.loads(payload)
            except json.JSONDecodeError as exc:
                raise ProtocolError(f"Invalid JSON in SSE data: {exc}") from exc

            if unwrap_jsonrpc and isinstance(raw, dict):
                if "error" in raw:
                    err = raw["error"]
                    raise ProtocolError(f"JSON-RPC error {err.get('code')}: {err.get('message')}")
                raw = raw.get("result", raw)

            event = _deserialize_event(raw, event_id=current_event_id)
            current_event_id = None
            yield event
    except httpx.ReadError as exc:
        raise ProtocolError(f"SSE stream read error: {exc}") from exc


def _deserialize_event(data: dict[str, Any], *, event_id: str | None = None) -> StreamEvent:
    """Deserialize a JSON dict into a StreamEvent."""
    kind = data.get("kind")
    try:
        if kind == "task":
            return StreamEvent.from_raw(Task.model_validate(data), event_id=event_id)
        if kind == "status-update":
            return StreamEvent.from_raw(
                TaskStatusUpdateEvent.model_validate(data), event_id=event_id
            )
        if kind == "artifact-update":
            return StreamEvent.from_raw(
                TaskArtifactUpdateEvent.model_validate(data), event_id=event_id
            )
    except Exception as exc:
        raise ProtocolError(f"Failed to deserialize SSE event: {exc}") from exc

    raise ProtocolError(f"Unknown SSE event kind: {kind}")
