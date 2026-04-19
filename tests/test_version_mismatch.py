"""Cross-version wiring: server rejects + client raises ``ProtocolVersionMismatchError``.

Covers:
- ``A2AServer(protocol_version={"1.0", "0.3"})`` raises ``ValueError`` at init
  (dual-mode removed).
- v1.0 server rejects ``A2A-Version: 0.3.0`` request headers with HTTP 400.
- v0.3 server rejects ``A2A-Version: 1.0`` request headers with HTTP 400.
- Client-side: sending to a mismatched transport surfaces the typed
  ``ProtocolVersionMismatchError`` rather than a generic ``A2AClientError``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import httpx
import pytest
from asgi_lifespan import LifespanManager

from a2akit import A2AServer, AgentCardConfig, Worker
from a2akit.client.errors import ProtocolVersionMismatchError
from a2akit.client.transport.jsonrpc import JsonRpcTransport
from a2akit.client.transport.rest import RestTransport

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from a2akit.worker import TaskContext


class _Echo(Worker):
    async def handle(self, ctx: TaskContext) -> None:
        await ctx.complete(f"Echo: {ctx.user_text}")


# -- init-time guard ---------------------------------------------------------


def test_server_rejects_dual_protocol_version_set() -> None:
    with pytest.raises(ValueError, match="dual"):
        A2AServer(
            worker=_Echo(),
            agent_card=AgentCardConfig(
                name="x", description="x", version="1.0.0", protocol="http+json"
            ),
            protocol_version={"1.0", "0.3"},
        )


def test_server_rejects_unsupported_version() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        A2AServer(
            worker=_Echo(),
            agent_card=AgentCardConfig(
                name="x", description="x", version="1.0.0", protocol="http+json"
            ),
            protocol_version="2.0",
        )


# -- server-side header validation ------------------------------------------


@pytest.fixture
async def v10_client() -> AsyncIterator[httpx.AsyncClient]:
    server = A2AServer(
        worker=_Echo(),
        agent_card=AgentCardConfig(
            name="V10", description="v1.0 only", version="1.0.0", protocol="http+json"
        ),
        additional_protocols=["jsonrpc"],
        protocol_version="1.0",
    )
    app = server.as_fastapi_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


@pytest.fixture
async def v03_client() -> AsyncIterator[httpx.AsyncClient]:
    server = A2AServer(
        worker=_Echo(),
        agent_card=AgentCardConfig(
            name="V03", description="v0.3 only", version="1.0.0", protocol="http+json"
        ),
        additional_protocols=["jsonrpc"],
        protocol_version="0.3",
    )
    app = server.as_fastapi_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_v10_server_rejects_v03_version_header(v10_client: httpx.AsyncClient) -> None:
    body = {
        "message": {
            "role": "ROLE_USER",
            "messageId": str(uuid.uuid4()),
            "parts": [{"text": "x"}],
        }
    }
    r = await v10_client.post("/message:send", json=body, headers={"A2A-Version": "0.3.0"})
    assert r.status_code == 400
    assert "Unsupported A2A version" in r.text


async def test_v03_server_rejects_v10_version_header(v03_client: httpx.AsyncClient) -> None:
    body = {
        "message": {
            "role": "user",
            "messageId": str(uuid.uuid4()),
            "parts": [{"kind": "text", "text": "x"}],
            "kind": "message",
        }
    }
    r = await v03_client.post("/v1/message:send", json=body, headers={"A2A-Version": "1.0"})
    assert r.status_code == 400
    assert "Unsupported A2A version" in r.text


# -- client-side raises typed error -----------------------------------------


async def test_rest_v03_client_raises_mismatch_against_v10_server(
    v10_client: httpx.AsyncClient,
) -> None:
    """Point a v0.3 REST transport at the v1.0 server's bare path.

    The v0.3 transport sends ``A2A-Version: 0.3.0``; the v1.0 router's header
    dependency rejects it with HTTP 400 + "Unsupported A2A version", which the
    transport must surface as :class:`ProtocolVersionMismatchError` rather
    than a generic ``A2AClientError``.
    """
    # Use the v1.0 bare path so we exercise the header check, not a 404.
    rest = RestTransport(v10_client, "http://test")
    from a2a_pydantic.v03 import Message, MessageSendParams, Part, Role, TextPart

    params = MessageSendParams(
        message=Message(
            role=Role.user,
            parts=[Part(root=TextPart(text="x"))],
            message_id=str(uuid.uuid4()),
        )
    )
    with pytest.raises(ProtocolVersionMismatchError):
        await rest.send_message(params)


async def test_jsonrpc_v03_client_raises_mismatch_against_v10_server(
    v10_client: httpx.AsyncClient,
) -> None:
    """Point a v0.3 JSON-RPC transport at the v1.0 server.

    The v0.3 JSON-RPC transport sends ``A2A-Version: 0.3.0`` and the
    ``message/send`` method name. The v1.0 server rejects the header first
    (HTTP 400). This must be surfaced as the typed mismatch.
    """
    jrpc = JsonRpcTransport(v10_client, "http://test")
    from a2a_pydantic.v03 import Message, MessageSendParams, Part, Role, TextPart

    params = MessageSendParams(
        message=Message(
            role=Role.user,
            parts=[Part(root=TextPart(text="x"))],
            message_id=str(uuid.uuid4()),
        )
    )
    with pytest.raises(ProtocolVersionMismatchError):
        await jrpc.send_message(params)
