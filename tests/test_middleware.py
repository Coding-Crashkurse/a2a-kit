"""Tests for A2AMiddleware pipeline integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import httpx
import pytest
from asgi_lifespan import LifespanManager

from a2akit import (
    A2AMiddleware,
    A2AServer,
    AgentCardConfig,
    RequestEnvelope,
    TaskContext,
    Worker,
)

if TYPE_CHECKING:
    from fastapi import Request



class EchoContextWorker(Worker):
    """Worker that echoes request_context back as the completion text."""

    async def handle(self, ctx: TaskContext) -> None:
        await ctx.complete(repr(ctx.request_context))



class InjectHeaderMiddleware(A2AMiddleware):
    """Copies the Authorization header into envelope.context."""

    async def before_dispatch(self, envelope: RequestEnvelope, request: Request) -> None:
        if auth := request.headers.get("Authorization"):
            envelope.context["auth"] = auth


class SecretExtractorMiddleware(A2AMiddleware):
    """Moves keys listed in SECRET_KEYS from message metadata to context."""

    SECRET_KEYS: ClassVar[set[str]] = {"user_token", "api_key"}

    async def before_dispatch(self, envelope: RequestEnvelope, request: Request) -> None:
        msg_meta = envelope.params.message.metadata or {}
        for key in self.SECRET_KEYS & msg_meta.keys():
            envelope.context[key] = msg_meta.pop(key)


class AfterDispatchRecorder(A2AMiddleware):
    """Records that after_dispatch was called and stores the result kind."""

    calls: ClassVar[list[dict[str, Any]]] = []

    async def after_dispatch(self, envelope: RequestEnvelope, result: Any) -> None:
        self.calls.append(
            {"context": dict(envelope.context), "result_type": type(result).__name__}
        )


class OrderTracker(A2AMiddleware):
    """Appends its name to envelope.context["order"] to verify pipeline ordering."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def before_dispatch(self, envelope: RequestEnvelope, request: Request) -> None:
        envelope.context.setdefault("order", []).append(f"before:{self.name}")

    async def after_dispatch(self, envelope: RequestEnvelope, result: Any) -> None:
        envelope.context.setdefault("order", []).append(f"after:{self.name}")



def _make_app(worker: Worker, middlewares: list[A2AMiddleware] | None = None):
    server = A2AServer(
        worker=worker,
        agent_card=AgentCardConfig(
            name="Middleware Test",
            description="Tests for middleware pipeline",
            version="0.0.1",
        ),
        middlewares=middlewares,
    )
    return server.as_fastapi_app()


def _send_body(text: str = "hello", metadata: dict[str, Any] | None = None) -> dict:
    import uuid

    msg: dict[str, Any] = {
        "role": "user",
        "messageId": str(uuid.uuid4()),
        "parts": [{"kind": "text", "text": text}],
    }
    if metadata:
        msg["metadata"] = metadata
    return {"message": msg, "configuration": {"blocking": True}}



@pytest.mark.asyncio
async def test_no_middleware():
    """Without middleware the request still works and request_context is empty."""
    raw = _make_app(EchoContextWorker())
    async with LifespanManager(raw) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/v1/message:send", json=_send_body())
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"]["state"] == "completed"
    # request_context should be empty dict
    text = data["artifacts"][0]["parts"][0]["text"]
    assert text == "{}"


@pytest.mark.asyncio
async def test_before_dispatch_injects_header():
    """Middleware can read HTTP headers and inject values into context."""
    raw = _make_app(EchoContextWorker(), middlewares=[InjectHeaderMiddleware()])
    async with LifespanManager(raw) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/v1/message:send",
                json=_send_body(),
                headers={"Authorization": "Bearer test-token"},
            )
    assert resp.status_code == 200
    text = resp.json()["artifacts"][0]["parts"][0]["text"]
    assert "'auth': 'Bearer test-token'" in text


@pytest.mark.asyncio
async def test_secret_extraction_moves_keys_to_context():
    """SecretExtractorMiddleware moves secret keys from metadata to context."""
    raw = _make_app(EchoContextWorker(), middlewares=[SecretExtractorMiddleware()])
    async with LifespanManager(raw) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/v1/message:send",
                json=_send_body(metadata={"user_token": "sk-abc", "trace_id": "t-1"}),
            )
    assert resp.status_code == 200
    text = resp.json()["artifacts"][0]["parts"][0]["text"]
    # user_token should be in request_context
    assert "'user_token': 'sk-abc'" in text
    # trace_id should NOT be in request_context (non-secret)
    assert "trace_id" not in text


@pytest.mark.asyncio
async def test_after_dispatch_called():
    """after_dispatch receives the completed result and the envelope context."""
    recorder = AfterDispatchRecorder()
    recorder.calls.clear()
    raw = _make_app(EchoContextWorker(), middlewares=[recorder])
    async with LifespanManager(raw) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/v1/message:send", json=_send_body())
    assert resp.status_code == 200
    assert len(recorder.calls) == 1
    assert recorder.calls[0]["result_type"] == "Task"


@pytest.mark.asyncio
async def test_middleware_ordering():
    """before_dispatch runs in order; after_dispatch runs in reverse order."""
    tracker_a = OrderTracker("A")
    tracker_b = OrderTracker("B")

    class OrderReporter(Worker):
        async def handle(self, ctx: TaskContext) -> None:
            await ctx.complete(repr(ctx.request_context))

    raw = _make_app(OrderReporter(), middlewares=[tracker_a, tracker_b])
    async with LifespanManager(raw) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/v1/message:send", json=_send_body())
    assert resp.status_code == 200
    text = resp.json()["artifacts"][0]["parts"][0]["text"]
    # before_dispatch: A then B
    assert "'before:A', 'before:B'" in text


@pytest.mark.asyncio
async def test_multiple_middlewares_compose():
    """Multiple middlewares can compose their effects."""
    raw = _make_app(
        EchoContextWorker(),
        middlewares=[InjectHeaderMiddleware(), SecretExtractorMiddleware()],
    )
    async with LifespanManager(raw) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post(
                "/v1/message:send",
                json=_send_body(metadata={"user_token": "secret"}),
                headers={"Authorization": "Bearer jwt"},
            )
    assert resp.status_code == 200
    text = resp.json()["artifacts"][0]["parts"][0]["text"]
    assert "'auth': 'Bearer jwt'" in text
    assert "'user_token': 'secret'" in text


@pytest.mark.asyncio
async def test_noop_middleware_passthrough():
    """A bare A2AMiddleware subclass (no overrides) is a no-op passthrough."""
    noop = A2AMiddleware()
    raw = _make_app(EchoContextWorker(), middlewares=[noop])
    async with LifespanManager(raw) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.post("/v1/message:send", json=_send_body())
    assert resp.status_code == 200
    text = resp.json()["artifacts"][0]["parts"][0]["text"]
    assert text == "{}"


@pytest.mark.asyncio
async def test_request_envelope_defaults():
    """RequestEnvelope starts with an empty context dict."""
    from a2a.types import MessageSendParams

    params = MessageSendParams.model_validate(_send_body())
    env = RequestEnvelope(params=params)
    assert env.context == {}
    assert env.params is params
