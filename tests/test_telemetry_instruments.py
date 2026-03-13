"""Tests for telemetry instruments — OTEL_ENABLED flag, get_tracer, env-var kill-switch."""

from __future__ import annotations

import importlib
import os
from unittest import mock


def _reload_instruments():
    """Reload _instruments module to re-evaluate OTEL_ENABLED."""
    import a2akit.telemetry._instruments as mod

    mod._tracer = None
    mod._meter = None
    importlib.reload(mod)
    return mod


class TestOtelEnabled:
    def test_otel_enabled_by_default(self):
        """OTEL_ENABLED is True when OTel is installed (it is in dev deps)."""
        mod = _reload_instruments()
        assert mod.OTEL_ENABLED is True

    def test_otel_disabled_via_env(self):
        """OTEL_ENABLED is False when env-var is set to false."""
        with mock.patch.dict(os.environ, {"OTEL_INSTRUMENTATION_A2AKIT_ENABLED": "false"}):
            mod = _reload_instruments()
            assert mod.OTEL_ENABLED is False

    def test_otel_disabled_case_insensitive(self):
        """Kill-switch is case-insensitive."""
        with mock.patch.dict(os.environ, {"OTEL_INSTRUMENTATION_A2AKIT_ENABLED": "False"}):
            mod = _reload_instruments()
            assert mod.OTEL_ENABLED is False


class TestGetTracer:
    def test_get_tracer_returns_tracer(self):
        """get_tracer() returns a valid Tracer when OTel is enabled."""
        mod = _reload_instruments()
        tracer = mod.get_tracer()
        assert tracer is not None

    def test_get_tracer_returns_none_when_disabled(self):
        """get_tracer() returns None when OTel is disabled via env."""
        with mock.patch.dict(os.environ, {"OTEL_INSTRUMENTATION_A2AKIT_ENABLED": "false"}):
            mod = _reload_instruments()
            assert mod.get_tracer() is None


class TestGetMeter:
    def test_get_meter_returns_meter(self):
        """get_meter_instance() returns a valid Meter."""
        mod = _reload_instruments()
        meter = mod.get_meter_instance()
        assert meter is not None

    def test_get_meter_returns_none_when_disabled(self):
        """get_meter_instance() returns None when disabled."""
        with mock.patch.dict(os.environ, {"OTEL_INSTRUMENTATION_A2AKIT_ENABLED": "false"}):
            mod = _reload_instruments()
            assert mod.get_meter_instance() is None
