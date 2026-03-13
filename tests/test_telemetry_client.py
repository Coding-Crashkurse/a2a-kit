"""Tests for client-side OTel instrumentation."""

from __future__ import annotations

import pytest
from opentelemetry import trace
from opentelemetry.trace import SpanKind, StatusCode

from a2akit.telemetry._client import inject_trace_context, traced_client_method


class FakeClient:
    """Minimal fake client for testing the decorator."""

    is_connected = True
    agent_name = "TestAgent"
    protocol = "jsonrpc"

    @traced_client_method("a2akit.client.test")
    async def do_something(self):
        return "ok"

    @traced_client_method("a2akit.client.test_error")
    async def do_error(self):
        raise ValueError("boom")


class TestTracedClientMethod:
    async def test_client_creates_span(self, otel_setup):
        """Decorated method creates a client span."""
        exporter = otel_setup
        client = FakeClient()
        result = await client.do_something()
        assert result == "ok"

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].name == "a2akit.client.test"
        assert spans[0].kind == SpanKind.CLIENT

    async def test_client_span_has_agent_name(self, otel_setup):
        """Span has agent_name attribute."""
        exporter = otel_setup
        client = FakeClient()
        await client.do_something()

        spans = exporter.get_finished_spans()
        assert spans[0].attributes["a2akit.agent.name"] == "TestAgent"
        assert spans[0].attributes["a2akit.protocol"] == "jsonrpc"

    async def test_client_span_records_error(self, otel_setup):
        """Exception is recorded on the span."""
        exporter = otel_setup
        client = FakeClient()
        with pytest.raises(ValueError, match="boom"):
            await client.do_error()

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert spans[0].status.status_code == StatusCode.ERROR
        assert spans[0].attributes["a2akit.error.type"] == "ValueError"

    async def test_client_span_status_ok(self, otel_setup):
        """Successful call sets StatusCode.OK."""
        exporter = otel_setup
        client = FakeClient()
        await client.do_something()

        spans = exporter.get_finished_spans()
        assert spans[0].status.status_code == StatusCode.OK


class TestInjectTraceContext:
    def test_client_injects_trace_context(self, otel_setup):
        """inject_trace_context adds traceparent to headers."""
        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("test"):
            headers: dict[str, str] = {}
            inject_trace_context(headers)
            assert "traceparent" in headers
