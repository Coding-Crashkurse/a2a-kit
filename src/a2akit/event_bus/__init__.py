"""EventBus package — 1:N event fan-out for task streaming."""

from a2akit.event_bus.base import EventBus
from a2akit.event_bus.memory import InMemoryEventBus

try:
    from a2akit.event_bus.redis import RedisEventBus
except ImportError:
    RedisEventBus = None  # type: ignore[assignment,misc]

__all__ = [
    "EventBus",
    "InMemoryEventBus",
    "RedisEventBus",
]
