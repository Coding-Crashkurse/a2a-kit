"""Test for the health check endpoints."""

from __future__ import annotations


async def test_health_check(client):
    """GET /v1/health returns 200 with status ok."""
    r = await client.get("/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


async def test_readiness_check(client):
    """GET /v1/health/ready returns 200 with component status."""
    r = await client.get("/v1/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    for name in ("storage", "broker", "event_bus"):
        assert body["components"][name]["status"] == "ok"
        assert "type" in body["components"][name]
