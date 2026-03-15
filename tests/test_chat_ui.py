"""Tests for the debug chat UI."""

from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager

from a2akit import A2AServer, AgentCardConfig, CapabilitiesConfig, TaskContext, Worker


class _EchoWorker(Worker):
    async def handle(self, ctx: TaskContext) -> None:
        await ctx.complete(f"Echo: {ctx.user_text}")


def _make_app(*, debug: bool = False):
    server = A2AServer(
        worker=_EchoWorker(),
        agent_card=AgentCardConfig(
            name="Test Agent",
            description="Test",
            version="0.0.1",
            protocol="http+json",
            capabilities=CapabilitiesConfig(),
        ),
    )
    return server.as_fastapi_app(debug=debug)


@pytest.fixture
async def debug_client():
    app = _make_app(debug=True)
    async with LifespanManager(app) as mgr:
        transport = httpx.ASGITransport(app=mgr.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
async def no_debug_client():
    app = _make_app(debug=False)
    async with LifespanManager(app) as mgr:
        transport = httpx.ASGITransport(app=mgr.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_debug_true_serves_chat(debug_client: httpx.AsyncClient) -> None:
    resp = await debug_client.get("/chat")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


async def test_debug_false_no_chat(no_debug_client: httpx.AsyncClient) -> None:
    resp = await no_debug_client.get("/chat")
    assert resp.status_code == 404


async def test_chat_html_contains_agent_card_url(debug_client: httpx.AsyncClient) -> None:
    resp = await debug_client.get("/chat")
    assert "/.well-known/agent-card.json" in resp.text


async def test_chat_html_contains_version(debug_client: httpx.AsyncClient) -> None:
    resp = await debug_client.get("/chat")
    # Should not contain the raw placeholder
    assert "{{VERSION}}" not in resp.text


async def test_chat_html_contains_both_views(debug_client: httpx.AsyncClient) -> None:
    resp = await debug_client.get("/chat")
    assert "message:send" in resp.text
    assert "/tasks" in resp.text


async def test_chat_not_in_openapi_schema(debug_client: httpx.AsyncClient) -> None:
    resp = await debug_client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert "/chat" not in schema.get("paths", {})
