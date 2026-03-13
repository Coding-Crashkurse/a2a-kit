"""Lazy tracer and meter singletons for a2akit OpenTelemetry instrumentation."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

_ENV_VAR = "OTEL_INSTRUMENTATION_A2AKIT_ENABLED"

try:
    import opentelemetry  # noqa: F401

    _HAS_OTEL = True
except ImportError:
    _HAS_OTEL = False


def _is_enabled() -> bool:
    """Check if OTel instrumentation is enabled."""
    if not _HAS_OTEL:
        return False
    val = os.getenv(_ENV_VAR, "true")
    return val.lower() == "true"


# Module-level flag
OTEL_ENABLED: bool = _is_enabled()

# Lazy singletons
_tracer: Any = None
_meter: Any = None


def get_tracer() -> Any:
    """Return the a2akit tracer. Returns None if OTel is disabled."""
    global _tracer
    if not OTEL_ENABLED:
        return None
    if _tracer is None:
        from opentelemetry import trace

        from a2akit.telemetry._semantic import TRACER_NAME, TRACER_VERSION

        _tracer = trace.get_tracer(TRACER_NAME, TRACER_VERSION)
    return _tracer


def get_meter_instance() -> Any:
    """Return the a2akit meter. Returns None if OTel is disabled."""
    global _meter
    if not OTEL_ENABLED:
        return None
    if _meter is None:
        from opentelemetry.metrics import get_meter

        from a2akit.telemetry._semantic import METER_NAME, TRACER_VERSION

        _meter = get_meter(METER_NAME, TRACER_VERSION)
    return _meter
