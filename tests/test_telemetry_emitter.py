"""Tests for TracingEmitter — span events + metrics on state transitions."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from a2a.types import TaskState
from opentelemetry import trace

from a2akit.event_emitter import EventEmitter
from a2akit.telemetry._emitter import TracingEmitter


class FakeEmitter(EventEmitter):
    """Minimal emitter for testing."""

    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def update_task(self, task_id, state=None, **kwargs) -> int:
        self.calls.append({"task_id": task_id, "state": state, **kwargs})
        return len(self.calls)

    async def send_event(self, task_id, event) -> None:
        pass


class TestTracingEmitter:
    async def test_emitter_delegates_to_inner(self, otel_setup):
        """Inner emitter is always called."""
        inner = FakeEmitter()
        emitter = TracingEmitter(inner)
        await emitter.update_task("task-1", state=TaskState.working)
        assert len(inner.calls) == 1
        assert inner.calls[0]["task_id"] == "task-1"

    async def test_emitter_adds_state_transition_event(self, otel_setup):
        """Span event is added when state changes."""
        exporter = otel_setup
        inner = FakeEmitter()
        emitter = TracingEmitter(inner)

        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("test-span"):
            await emitter.update_task("task-1", state=TaskState.working)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        events = spans[0].events
        assert len(events) == 1
        assert events[0].name == "state_transition"
        assert events[0].attributes["a2akit.task.id"] == "task-1"
        assert events[0].attributes["a2akit.task.state"] == "working"

    async def test_emitter_skips_when_no_state(self, otel_setup):
        """No span event when state is None."""
        exporter = otel_setup
        inner = FakeEmitter()
        emitter = TracingEmitter(inner)

        tracer = trace.get_tracer("test")
        with tracer.start_as_current_span("test-span"):
            await emitter.update_task("task-1", state=None)

        spans = exporter.get_finished_spans()
        assert len(spans) == 1
        assert len(spans[0].events) == 0

    async def test_emitter_send_event_delegates(self, otel_setup):
        """send_event passes through to inner."""
        inner = FakeEmitter()
        inner.send_event = AsyncMock()  # type: ignore[method-assign]
        emitter = TracingEmitter(inner)
        await emitter.send_event("task-1", {"kind": "status-update"})
        inner.send_event.assert_awaited_once_with("task-1", {"kind": "status-update"})
