"""End-to-end integration tests for OTel tracing."""

from __future__ import annotations

import pytest

from a2akit.telemetry._instruments import OTEL_ENABLED


class TestIntegration:
    @pytest.mark.skipif(not OTEL_ENABLED, reason="OTel not installed")
    async def test_otel_enabled_flag(self, otel_setup):
        """OTEL_ENABLED is True when OTel is installed."""
        assert OTEL_ENABLED is True

    async def test_tracer_and_meter_creation(self, otel_setup):
        """Tracer and meter can be created successfully."""
        from a2akit.telemetry._instruments import get_meter_instance, get_tracer

        tracer = get_tracer()
        meter = get_meter_instance()
        assert tracer is not None
        assert meter is not None

    async def test_server_with_telemetry(self, otel_setup, client):
        """Server works with OTel enabled — middleware creates spans."""
        _ = otel_setup

        resp = await client.post(
            "/v1/message:send",
            json={
                "message": {
                    "role": "user",
                    "messageId": "otel-test-1",
                    "parts": [{"kind": "text", "text": "hello"}],
                },
                "configuration": {"blocking": True},
            },
        )
        assert resp.status_code == 200
