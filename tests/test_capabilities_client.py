"""Client-side capability enforcement tests."""

from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager

from a2akit import A2AServer, AgentCardConfig, CapabilitiesConfig
from a2akit.client import A2AClient, AgentCapabilityError
from conftest import EchoWorker, StreamingWorker


def _make_app(worker, *, protocol="http+json", streaming=False):
    server = A2AServer(
        worker=worker,
        agent_card=AgentCardConfig(
            name="Test Agent",
            description="Test",
            version="0.0.1",
            protocol=protocol,
            capabilities=CapabilitiesConfig(streaming=streaming),
        ),
    )
    return server.as_fastapi_app()


async def _make_client(worker, *, protocol="http+json", streaming=False):
    app = _make_app(worker, protocol=protocol, streaming=streaming)
    manager = LifespanManager(app)
    await manager.__aenter__()
    http = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=manager.app),
        base_url="http://test",
    )
    client = A2AClient("http://test", httpx_client=http, protocol=protocol)
    await client.connect()
    return client, manager, http


class TestClientStreamCapability:
    async def test_stream_raises_when_not_supported(self):
        """stream() on non-streaming agent raises AgentCapabilityError."""
        client, manager, http = await _make_client(EchoWorker(), streaming=False)
        with pytest.raises(AgentCapabilityError, match="does not support streaming"):
            async for _ in client.stream("hello"):
                pass
        await client.close()
        await http.aclose()
        await manager.__aexit__(None, None, None)

    async def test_stream_text_raises_when_not_supported(self):
        """stream_text() on non-streaming agent raises AgentCapabilityError."""
        client, manager, http = await _make_client(EchoWorker(), streaming=False)
        with pytest.raises(AgentCapabilityError, match="does not support streaming"):
            async for _ in client.stream_text("hello"):
                pass
        await client.close()
        await http.aclose()
        await manager.__aexit__(None, None, None)

    async def test_subscribe_raises_when_not_supported(self):
        """subscribe() on non-streaming agent raises AgentCapabilityError."""
        client, manager, http = await _make_client(EchoWorker(), streaming=False)
        with pytest.raises(AgentCapabilityError, match="does not support streaming"):
            async for _ in client.subscribe("some-task-id"):
                pass
        await client.close()
        await http.aclose()
        await manager.__aexit__(None, None, None)

    async def test_stream_works_when_supported(self):
        """stream() on streaming agent works normally."""
        client, manager, http = await _make_client(StreamingWorker(), streaming=True)
        events = []
        async for event in client.stream("hello world"):
            events.append(event)
        assert len(events) > 0
        await client.close()
        await http.aclose()
        await manager.__aexit__(None, None, None)

    async def test_send_always_works(self):
        """send() works regardless of streaming capability."""
        client, manager, http = await _make_client(EchoWorker(), streaming=False)
        result = await client.send("hello")
        assert result.text == "Echo: hello"
        await client.close()
        await http.aclose()
        await manager.__aexit__(None, None, None)

    async def test_get_task_always_works(self):
        """get_task() works regardless of streaming capability."""
        client, manager, http = await _make_client(EchoWorker(), streaming=False)
        result = await client.send("hello")
        fetched = await client.get_task(result.task_id)
        assert fetched.task_id == result.task_id
        await client.close()
        await http.aclose()
        await manager.__aexit__(None, None, None)

    async def test_error_message_contains_agent_name(self):
        """Error message includes the agent's name from card."""
        client, manager, http = await _make_client(EchoWorker(), streaming=False)
        with pytest.raises(AgentCapabilityError, match="Test Agent"):
            async for _ in client.stream("hello"):
                pass
        await client.close()
        await http.aclose()
        await manager.__aexit__(None, None, None)
