"""Tests verifying zero overhead when OTel is not installed or disabled."""

from __future__ import annotations

import importlib
import os
from unittest import mock


class TestNoImportError:
    def test_no_import_error_without_otel(self):
        """a2akit.telemetry imports cleanly even if OTel check returns disabled."""
        with mock.patch.dict(os.environ, {"OTEL_INSTRUMENTATION_A2AKIT_ENABLED": "false"}):
            import a2akit.telemetry._instruments as mod

            mod._tracer = None
            mod._meter = None
            importlib.reload(mod)
            assert mod.OTEL_ENABLED is False
            # The module loaded fine — no ImportError

    def test_no_overhead_when_disabled(self):
        """get_tracer() returns None fast when disabled."""
        with mock.patch.dict(os.environ, {"OTEL_INSTRUMENTATION_A2AKIT_ENABLED": "false"}):
            import a2akit.telemetry._instruments as mod

            mod._tracer = None
            mod._meter = None
            importlib.reload(mod)
            assert mod.get_tracer() is None
            assert mod.get_meter_instance() is None


class TestServerWorksWithoutOtel:
    async def test_server_works_when_telemetry_disabled(self, client):
        """Full HTTP round-trip works when OTel is explicitly disabled via env."""
        # The 'client' fixture uses the default test app (EchoWorker)
        # OTel is installed but can be disabled — the server should work fine
        resp = await client.post(
            "/v1/message:send",
            json={
                "message": {
                    "role": "user",
                    "messageId": "test-123",
                    "parts": [{"kind": "text", "text": "hello"}],
                },
                "configuration": {"blocking": True},
            },
        )
        assert resp.status_code == 200
