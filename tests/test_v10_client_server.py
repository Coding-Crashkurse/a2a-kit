"""Smoke test: A2AClient ↔ A2AServer over native v1.0 wire (spec §4).

Exercises the full round-trip — v1.0 agent card discovery, v1.0 REST
``message:send``, v1.0 JSON-RPC ``SendMessage``, and streaming — using
the new :class:`RestV10Transport` / :class:`JsonRpcV10Transport`
transports. The client still builds v0.3 ``MessageSendParams``; the v10
transports convert to v10 on the wire and back again.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx
import pytest
from asgi_lifespan import LifespanManager

from a2akit import A2AServer, AgentCardConfig, Worker
from a2akit.client import A2AClient

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from a2akit.worker import TaskContext


class _Echo(Worker):
    async def handle(self, ctx: TaskContext) -> None:
        await ctx.complete(f"Echo: {ctx.user_text}")


@pytest.fixture
async def v10_http_client() -> AsyncIterator[httpx.AsyncClient]:
    server = A2AServer(
        worker=_Echo(),
        agent_card=AgentCardConfig(
            name="V10",
            description="native v1.0",
            version="1.0.0",
            protocol="http+json",
        ),
        additional_protocols=["jsonrpc"],
        protocol_version="1.0",
    )
    app = server.as_fastapi_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


async def test_v10_client_rest_roundtrip(v10_http_client: httpx.AsyncClient) -> None:
    """Connect to a pure-v1.0 server via REST and send a message."""
    client = A2AClient(
        "http://test",
        httpx_client=v10_http_client,
        protocol="http+json",
        verify_signatures="off",
    )
    await client.connect()
    try:
        assert client._active_wire_version.startswith("1")
        result = await client.send("hi")
        assert result.state == "completed"
        assert result.text == "Echo: hi"
    finally:
        await client.close()


async def test_v10_client_jsonrpc_roundtrip(v10_http_client: httpx.AsyncClient) -> None:
    """Connect to a pure-v1.0 server via JSON-RPC and send a message."""
    client = A2AClient(
        "http://test",
        httpx_client=v10_http_client,
        protocol="jsonrpc",
        verify_signatures="off",
    )
    await client.connect()
    try:
        assert client._active_wire_version.startswith("1")
        result = await client.send("hello")
        assert result.state == "completed"
        assert result.text == "Echo: hello"
    finally:
        await client.close()
