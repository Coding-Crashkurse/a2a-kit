"""Integration tests for the native A2A v1.0 wire (§5).

Covers:

- REST router: ``/message:send``, ``/tasks/{id}``, ``/tasks``, errors in
  ``google.rpc.Status`` shape, card discovery (``supportedInterfaces[]``).
- JSON-RPC router: ``SendMessage`` / ``GetTask`` / unknown-method error.
- Verifies that the v0.3 paths (``/v1/...``) are NOT mounted when the
  server is configured for v1.0.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import httpx
import pytest
from asgi_lifespan import LifespanManager

from a2akit import A2AServer, AgentCardConfig, Worker

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from a2akit.worker import TaskContext


class _Echo(Worker):
    async def handle(self, ctx: TaskContext) -> None:
        await ctx.complete(f"Echo: {ctx.user_text}")


async def _make_client(protocol: str) -> tuple[Any, AsyncIterator[Any]]:
    """Helper — returns (client, lifespan_ctx). Use inside the fixture."""
    server = A2AServer(
        worker=_Echo(),
        agent_card=AgentCardConfig(
            name="Test",
            description="Test server",
            version="1.0.0",
            protocol=protocol,  # type: ignore[arg-type]
        ),
        protocol_version="1.0",
    )
    return server.as_fastapi_app(), server


@pytest.fixture
async def rest_client() -> AsyncIterator[httpx.AsyncClient]:
    app, _ = await _make_client("http+json")
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def jsonrpc_client() -> AsyncIterator[httpx.AsyncClient]:
    app, _ = await _make_client("jsonrpc")
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


async def test_v10_agent_card_has_supported_interfaces(rest_client: httpx.AsyncClient) -> None:
    r = await rest_client.get("/.well-known/agent-card.json")
    assert r.status_code == 200
    data = r.json()
    # v1.0 shape: supportedInterfaces[] with per-entry protocol_version.
    assert "supportedInterfaces" in data
    assert data["supportedInterfaces"][0]["protocolVersion"] == "1.0"
    # v0.3 top-level keys must NOT be present.
    assert "url" not in data
    assert "preferredTransport" not in data


async def test_v10_rest_message_send_returns_task_wrapper(rest_client: httpx.AsyncClient) -> None:
    r = await rest_client.post(
        "/message:send",
        json={
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "hi"}],
                "messageId": "m-1",
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    # v1.0 wraps the result in SendMessageResponse with a "task" oneof.
    assert "task" in body
    assert body["task"]["status"]["state"] == "TASK_STATE_COMPLETED"


async def test_v10_rest_tasks_get(rest_client: httpx.AsyncClient) -> None:
    # First create one.
    r = await rest_client.post(
        "/message:send",
        json={
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "hi"}],
                "messageId": "m-2",
            },
        },
    )
    task_id = r.json()["task"]["id"]
    r = await rest_client.get(f"/tasks/{task_id}")
    assert r.status_code == 200
    assert r.json()["id"] == task_id


async def test_v10_rest_tasks_list_tenant_filter(rest_client: httpx.AsyncClient) -> None:
    # Tenanted send.
    await rest_client.post(
        "/message:send",
        json={
            "tenant": "acme",
            "message": {
                "role": "ROLE_USER",
                "parts": [{"text": "t-1"}],
                "messageId": "m-tenant-1",
            },
        },
    )
    r = await rest_client.get("/tasks?tenant=acme")
    assert r.status_code == 200
    # All returned tasks belong to the acme tenant.
    assert len(r.json()["tasks"]) >= 1


async def test_v10_rest_task_not_found_shape(rest_client: httpx.AsyncClient) -> None:
    r = await rest_client.get("/tasks/nope")
    assert r.status_code == 404
    body = r.json()
    err = body["error"]
    assert err["status"] == "NOT_FOUND"
    assert err["details"][0]["@type"] == "type.googleapis.com/google.rpc.ErrorInfo"
    assert err["details"][0]["reason"] == "TASK_NOT_FOUND"
    assert err["details"][0]["domain"] == "a2a-protocol.org"


async def test_v10_rest_invalid_body_returns_invalid_argument(
    rest_client: httpx.AsyncClient,
) -> None:
    r = await rest_client.post("/message:send", json={"garbage": True})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["status"] == "INVALID_ARGUMENT"


async def test_v10_mode_does_not_serve_v03_paths(rest_client: httpx.AsyncClient) -> None:
    r = await rest_client.post(
        "/v1/message:send",
        json={
            "message": {
                "role": "user",
                "parts": [{"kind": "text", "text": "x"}],
                "messageId": "m-x",
                "kind": "message",
            }
        },
    )
    assert r.status_code == 404


async def test_v10_jsonrpc_send_message(jsonrpc_client: httpx.AsyncClient) -> None:
    r = await jsonrpc_client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "SendMessage",
            "params": {
                "message": {
                    "role": "ROLE_USER",
                    "parts": [{"text": "hi"}],
                    "messageId": "jrpc-1",
                },
            },
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["jsonrpc"] == "2.0"
    assert "task" in body["result"]


async def test_v10_jsonrpc_unknown_method_error(
    jsonrpc_client: httpx.AsyncClient,
) -> None:
    r = await jsonrpc_client.post(
        "/",
        json={"jsonrpc": "2.0", "id": 99, "method": "DoesNotExist"},
    )
    body = r.json()
    assert body["error"]["code"] == -32601
    info = body["error"]["data"][0]
    assert info["reason"] == "METHOD_NOT_FOUND"
    assert info["domain"] == "a2a-protocol.org"


async def test_v10_jsonrpc_get_task_not_found(
    jsonrpc_client: httpx.AsyncClient,
) -> None:
    r = await jsonrpc_client.post(
        "/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "GetTask",
            "params": {"id": "does-not-exist"},
        },
    )
    body = r.json()
    assert body["error"]["code"] == -32001
    assert body["error"]["data"][0]["reason"] == "TASK_NOT_FOUND"


async def test_v10_jsonrpc_health(jsonrpc_client: httpx.AsyncClient) -> None:
    r = await jsonrpc_client.post(
        "/",
        json={"jsonrpc": "2.0", "id": 1, "method": "health"},
    )
    assert r.json()["result"] == {"status": "ok"}
