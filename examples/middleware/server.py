"""Middleware example — extract secrets from metadata, echo them in the worker.

Run:
    uvicorn examples.middleware.server:app --reload
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

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


class SecretExtractor(A2AMiddleware):
    """Move sensitive keys from message.metadata into transient context."""

    SECRET_KEYS: ClassVar[set[str]] = {"user_token"}

    async def before_dispatch(self, envelope: RequestEnvelope, request: Request) -> None:
        msg_meta: dict[str, Any] = envelope.params.message.metadata or {}
        envelope.params.message.metadata = msg_meta

        for key in self.SECRET_KEYS & msg_meta.keys():
            envelope.context[key] = msg_meta.pop(key)

        auth: str | None = request.headers.get("Authorization")
        if auth is not None:
            envelope.context["auth_header"] = auth


class EchoSecretsWorker(Worker):
    """Echoes back what the worker sees in metadata vs. request_context."""

    async def handle(self, ctx: TaskContext) -> None:
        lines: list[str] = [
            f"metadata: {ctx.metadata}",
            f"request_context: {ctx.request_context}",
        ]
        await ctx.complete("\n".join(lines))


server: A2AServer = A2AServer(
    worker=EchoSecretsWorker(),
    agent_card=AgentCardConfig(
        name="Secret Echo",
        description="Shows how middleware separates transient secrets from persisted metadata.",
        version="0.1.0",
    ),
    middlewares=[SecretExtractor()],
)
app = server.as_fastapi_app()
