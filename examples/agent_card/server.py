"""Demonstrates all configurable AgentCard fields (A2A v1.0).

The framework builds a v1.0 AgentCard with ``supportedInterfaces[]`` by default;
pass ``protocol_version="0.3"`` to ``A2AServer`` for the legacy v0.3 shape.

Run:
    uvicorn examples.agent_card.server:app --reload
"""

from a2a_pydantic.v03 import HTTPAuthSecurityScheme

from a2akit import (
    A2AServer,
    AgentCardConfig,
    CapabilitiesConfig,
    ProviderConfig,
    SignatureConfig,
    SkillConfig,
    TaskContext,
    Worker,
)


class TranslateWorker(Worker):
    """Toy translator — just echoes input with a prefix."""

    async def handle(self, ctx: TaskContext) -> None:
        await ctx.complete(f"[translated] {ctx.user_text}")


server = A2AServer(
    worker=TranslateWorker(),
    agent_card=AgentCardConfig(
        name="Full Agent Card Demo",
        description="Demonstrates all configurable AgentCard fields.",
        version="1.0.0",
        protocol="http+json",
        capabilities=CapabilitiesConfig(state_transition_history=True),
        provider=ProviderConfig(
            organization="Acme Corp",
            url="https://acme.example.com",
        ),
        icon_url="https://acme.example.com/icon.png",
        documentation_url="https://docs.acme.example.com/agent",
        security_schemes={
            "bearer": HTTPAuthSecurityScheme(type="http", scheme="bearer"),
        },
        security=[{"bearer": []}],
        signatures=[
            SignatureConfig(
                protected="eyJhbGciOiJSUzI1NiJ9",
                signature="placeholder-signature",
            ),
        ],
        skills=[
            SkillConfig(
                id="translate",
                name="Translator",
                description="Translates text between languages.",
                tags=["translation", "nlp"],
                input_modes=["text/plain"],
                output_modes=["text/plain", "application/json"],
            ),
        ],
    ),
)
app = server.as_fastapi_app(debug=True)
