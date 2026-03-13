"""Optional OpenTelemetry instrumentation for a2akit.

Install with: pip install a2akit[otel]

When OpenTelemetry is not installed, all instrumentation is a no-op.
"""

from a2akit.telemetry._instruments import OTEL_ENABLED, get_meter_instance, get_tracer

__all__ = [
    "OTEL_ENABLED",
    "TracingEmitter",
    "TracingMiddleware",
    "get_meter_instance",
    "get_tracer",
]


def __getattr__(name: str) -> object:
    if name == "TracingEmitter":
        from a2akit.telemetry._emitter import TracingEmitter

        return TracingEmitter
    if name == "TracingMiddleware":
        from a2akit.telemetry._middleware import TracingMiddleware

        return TracingMiddleware
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
