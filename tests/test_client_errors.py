"""Tests for client error types."""

from __future__ import annotations

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


class TestErrorInheritance:
    def test_all_inherit_from_base(self):
        errors = [
            AgentNotFoundError("http://x", "nope"),
            AgentCapabilityError("Agent", "streaming"),
            NotConnectedError(),
            TaskNotFoundError("t1"),
            TaskNotCancelableError("t1", "completed"),
            TaskTerminalError("t1", "completed"),
            ProtocolError("bad"),
        ]
        for err in errors:
            assert isinstance(err, A2AClientError)
            assert isinstance(err, Exception)


class TestErrorMessages:
    def test_agent_not_found(self):
        err = AgentNotFoundError("http://x", "404")
        assert "http://x" in str(err)
        assert "404" in str(err)
        assert err.url == "http://x"

    def test_agent_capability(self):
        err = AgentCapabilityError("MyAgent", "streaming")
        assert "MyAgent" in str(err)
        assert "streaming" in str(err)

    def test_not_connected(self):
        err = NotConnectedError()
        assert "not connected" in str(err).lower()

    def test_task_not_found(self):
        err = TaskNotFoundError("t123")
        assert "t123" in str(err)
        assert err.task_id == "t123"

    def test_task_not_cancelable(self):
        err = TaskNotCancelableError("t1", "completed")
        assert "t1" in str(err)
        assert "completed" in str(err)

    def test_task_terminal(self):
        err = TaskTerminalError("t1", "failed")
        assert "t1" in str(err)
        assert "failed" in str(err)

    def test_protocol_error(self):
        err = ProtocolError("bad json")
        assert "bad json" in str(err)
