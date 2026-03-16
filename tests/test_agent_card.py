"""Tests for agent card discovery endpoint."""

from __future__ import annotations

import httpx
import pytest
from a2a.types import HTTPAuthSecurityScheme
from asgi_lifespan import LifespanManager

from a2akit import (
    A2AServer,
    AgentCardConfig,
    CapabilitiesConfig,
    ProviderConfig,
    SignatureConfig,
    SkillConfig,
)
from conftest import EchoWorker, _make_app


@pytest.fixture
async def client():
    app = _make_app(EchoWorker())
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            yield c


async def test_agent_card_discovery(client: httpx.AsyncClient):
    """GET /.well-known/agent-card.json should return the agent card with expected fields."""
    resp = await client.get("/.well-known/agent-card.json")
    assert resp.status_code == 200

    card = resp.json()
    assert card["name"] == "Test Agent"
    assert card["description"] == "Test agent for unit tests"
    assert card["version"] == "0.0.1"
    assert "/v1" in card["url"]
    assert card["protocolVersion"] == "0.3.0"


async def test_agent_card_full_spec_fields():
    """Agent card with all new fields should serialize them correctly over HTTP."""
    server = A2AServer(
        worker=EchoWorker(),
        agent_card=AgentCardConfig(
            name="Full Agent",
            description="All spec fields.",
            version="2.0.0",
            protocol="http+json",
            capabilities=CapabilitiesConfig(),
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
                    signature="abc123",
                ),
            ],
            skills=[
                SkillConfig(
                    id="translate",
                    name="Translator",
                    description="Translates text.",
                    tags=["translation"],
                    input_modes=["text/plain"],
                    output_modes=["text/plain", "application/json"],
                    security=[{"bearer": []}],
                ),
            ],
        ),
    )
    app = server.as_fastapi_app()
    async with LifespanManager(app) as manager:
        transport = httpx.ASGITransport(app=manager.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            resp = await c.get("/.well-known/agent-card.json")

    assert resp.status_code == 200
    card = resp.json()

    # Provider
    assert card["provider"]["organization"] == "Acme Corp"
    assert card["provider"]["url"] == "https://acme.example.com"

    # Icon & docs
    assert card["iconUrl"] == "https://acme.example.com/icon.png"
    assert card["documentationUrl"] == "https://docs.acme.example.com/agent"

    # Security schemes
    assert "bearer" in card["securitySchemes"]
    assert card["securitySchemes"]["bearer"]["scheme"] == "bearer"

    # Security
    assert card["security"] == [{"bearer": []}]

    # Signatures
    assert len(card["signatures"]) == 1
    assert card["signatures"][0]["protected"] == "eyJhbGciOiJSUzI1NiJ9"
    assert card["signatures"][0]["signature"] == "abc123"

    # Skill with modes and security
    skill = card["skills"][0]
    assert skill["id"] == "translate"
    assert skill["inputModes"] == ["text/plain"]
    assert skill["outputModes"] == ["text/plain", "application/json"]
    assert skill["security"] == [{"bearer": []}]
