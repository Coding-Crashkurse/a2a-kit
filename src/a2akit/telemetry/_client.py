"""Client-side OTel instrumentation helpers."""

from __future__ import annotations

import functools
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar, cast

from a2akit.telemetry._instruments import OTEL_ENABLED, get_tracer
from a2akit.telemetry._semantic import (
    ATTR_AGENT_NAME,
    ATTR_ERROR_TYPE,
    ATTR_PROTOCOL,
    ATTR_TASK_ID,
    ATTR_TASK_STATE,
)

if OTEL_ENABLED:
    from opentelemetry.trace import SpanKind, StatusCode

F = TypeVar("F", bound=Callable[..., Coroutine[Any, Any, Any]])


def traced_client_method(span_name: str) -> Callable[[F], F]:
    """Decorator for A2AClient methods that creates a client span."""

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            if tracer is None:
                return await func(self, *args, **kwargs)

            attributes: dict[str, Any] = {}
            if self.is_connected:
                attributes[ATTR_AGENT_NAME] = self.agent_name
                attributes[ATTR_PROTOCOL] = self.protocol

            with tracer.start_as_current_span(
                span_name, kind=SpanKind.CLIENT, attributes=attributes
            ) as span:
                try:
                    result = await func(self, *args, **kwargs)
                    span.set_status(StatusCode.OK)

                    if hasattr(result, "task_id") and result.task_id:
                        span.set_attribute(ATTR_TASK_ID, result.task_id)
                    if hasattr(result, "state") and result.state:
                        span.set_attribute(ATTR_TASK_STATE, result.state)

                    return result
                except Exception as exc:
                    span.record_exception(exc)
                    span.set_status(StatusCode.ERROR, str(exc))
                    span.set_attribute(ATTR_ERROR_TYPE, type(exc).__name__)
                    raise

        return cast("F", wrapper)

    return decorator


def inject_trace_context(headers: dict[str, str]) -> None:
    """Inject W3C trace context into outgoing headers."""
    if not OTEL_ENABLED:
        return
    from opentelemetry.propagate import inject

    inject(headers)
