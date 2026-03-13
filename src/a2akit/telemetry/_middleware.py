"""TracingMiddleware — creates root spans per incoming A2A request."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from a2akit.middleware import A2AMiddleware
from a2akit.telemetry._instruments import OTEL_ENABLED, get_tracer
from a2akit.telemetry._semantic import (
    ATTR_ARTIFACT_COUNT,
    ATTR_CONTEXT_ID,
    ATTR_MESSAGE_ID,
    ATTR_METHOD,
    ATTR_TASK_ID,
    ATTR_TASK_STATE,
    SPAN_HTTP_REQUEST,
)

if TYPE_CHECKING:
    from a2a.types import Message, Task
    from fastapi import Request

    from a2akit.middleware import RequestEnvelope

if OTEL_ENABLED:
    from opentelemetry import context as otel_context
    from opentelemetry.propagate import extract
    from opentelemetry.trace import SpanKind, StatusCode, set_span_in_context


def _detect_method(request: Request) -> str:
    """Detect the A2A method from the request."""
    path = request.url.path
    if "send" in path and "stream" not in path.lower():
        return "message/send"
    if "stream" in path.lower():
        return "message/sendStream"
    if "cancel" in path:
        return "tasks/cancel"
    if "subscribe" in path:
        return "tasks/resubscribe"
    if "tasks" in path:
        return "tasks/get"
    return path


class TracingMiddleware(A2AMiddleware):
    """Creates a root span per incoming A2A request.

    Extracts W3C trace context from HTTP headers (context propagation).
    Sets task_id, context_id, method as span attributes.
    """

    async def before_dispatch(
        self,
        envelope: RequestEnvelope,
        request: Request,
    ) -> None:
        """Start a server span for the incoming request."""
        tracer = get_tracer()
        if tracer is None:
            return

        # Extract W3C trace context from incoming headers
        headers: dict[str, str] = dict(request.headers)
        ctx = extract(headers)

        msg = envelope.params.message
        span = tracer.start_span(
            SPAN_HTTP_REQUEST,
            context=ctx,
            kind=SpanKind.SERVER,
            attributes={
                ATTR_TASK_ID: msg.task_id or "",
                ATTR_CONTEXT_ID: msg.context_id or "",
                ATTR_MESSAGE_ID: msg.message_id or "",
                ATTR_METHOD: _detect_method(request),
            },
        )
        envelope.context["_otel_span"] = span
        token = otel_context.attach(set_span_in_context(span))
        envelope.context["_otel_token"] = token

    async def after_dispatch(
        self,
        envelope: RequestEnvelope,
        result: Task | Message,
    ) -> None:
        """End the server span with result attributes."""
        span: Any = envelope.context.get("_otel_span")
        token: Any = envelope.context.get("_otel_token")
        if span is None:
            return

        if hasattr(result, "status") and result.status:
            span.set_attribute(
                ATTR_TASK_STATE,
                result.status.state.value
                if hasattr(result.status.state, "value")
                else str(result.status.state),
            )
        if hasattr(result, "artifacts") and result.artifacts:
            span.set_attribute(ATTR_ARTIFACT_COUNT, len(result.artifacts))

        span.set_status(StatusCode.OK)
        span.end()
        if token is not None:
            otel_context.detach(token)
