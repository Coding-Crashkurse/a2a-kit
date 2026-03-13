"""Tests for TracingMiddleware — span creation + context propagation."""

from __future__ import annotations

from unittest.mock import MagicMock

from a2a.types import Message, MessageSendParams, Part, Role, TextPart
from opentelemetry import trace
from opentelemetry.trace import SpanKind

from a2akit.middleware import RequestEnvelope
from a2akit.telemetry._middleware import TracingMiddleware


def _make_envelope(task_id="t-1", context_id="c-1", message_id="m-1"):
    """Create a test RequestEnvelope."""
    msg = Message(
        role=Role.user,
        parts=[Part(root=TextPart(text="hello"))],
        message_id=message_id,
        task_id=task_id,
        context_id=context_id,
    )
    return RequestEnvelope(params=MessageSendParams(message=msg))


def _make_request(path="/v1/message:send", headers=None):
    """Create a mock FastAPI Request."""
    req = MagicMock()
    req.url = MagicMock()
    req.url.path = path
    req.headers = headers or {}
    return req


class TestTracingMiddleware:
    async def test_middleware_creates_server_span(self, otel_setup):
        """before_dispatch creates a span, after_dispatch ends it."""
        exporter = otel_setup
        mw = TracingMiddleware()
        envelope = _make_envelope()
        request = _make_request()

        await mw.before_dispatch(envelope, request)
        assert "_otel_span" in envelope.context

        # Simulate a result
        result = MagicMock()
        result.status = MagicMock()
        result.status.state = MagicMock()
        result.status.state.value = "completed"
        result.artifacts = None

        await mw.after_dispatch(envelope, result)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "a2akit.http.request"
        assert spans[0].kind == SpanKind.SERVER

    async def test_middleware_sets_task_id_attribute(self, otel_setup):
        """Span has task_id attribute."""
        exporter = otel_setup
        mw = TracingMiddleware()
        envelope = _make_envelope(task_id="my-task")
        request = _make_request()

        await mw.before_dispatch(envelope, request)

        result = MagicMock()
        result.status = None
        result.artifacts = None
        await mw.after_dispatch(envelope, result)

        spans = exporter.get_finished_spans()
        assert spans[0].attributes["a2akit.task.id"] == "my-task"

    async def test_middleware_extracts_trace_context(self, otel_setup):
        """traceparent header is extracted for context propagation."""
        exporter = otel_setup
        mw = TracingMiddleware()
        envelope = _make_envelope()

        # Create a parent span to generate a valid traceparent
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("parent") as parent_span:
            parent_ctx = parent_span.get_span_context()
            traceparent = (
                f"00-{format(parent_ctx.trace_id, '032x')}-{format(parent_ctx.span_id, '016x')}-01"
            )
            request = _make_request(headers={"traceparent": traceparent})
            await mw.before_dispatch(envelope, request)

        result = MagicMock()
        result.status = None
        result.artifacts = None
        await mw.after_dispatch(envelope, result)

        spans = exporter.get_finished_spans()
        # The middleware span should share the same trace_id as parent
        mw_span = next(s for s in spans if s.name == "a2akit.http.request")
        assert mw_span.context.trace_id == parent_ctx.trace_id

    async def test_middleware_sets_status_ok_on_success(self, otel_setup):
        """Span status is OK after successful dispatch."""
        exporter = otel_setup
        mw = TracingMiddleware()
        envelope = _make_envelope()
        request = _make_request()

        await mw.before_dispatch(envelope, request)
        result = MagicMock()
        result.status = None
        result.artifacts = None
        await mw.after_dispatch(envelope, result)

        spans = exporter.get_finished_spans()
        from opentelemetry.trace import StatusCode

        assert spans[0].status.status_code == StatusCode.OK
