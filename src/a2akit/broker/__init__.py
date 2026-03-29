"""Broker package — task scheduling, cancellation, and event fan-out."""

from a2akit.broker.base import (
    Broker,
    CancelRegistry,
    CancelScope,
    OperationHandle,
    TaskOperation,
)
from a2akit.broker.memory import InMemoryBroker, InMemoryCancelRegistry

try:
    from a2akit.broker.redis import RedisBroker, RedisCancelRegistry
except ImportError:
    RedisBroker = None  # type: ignore[assignment,misc]
    RedisCancelRegistry = None  # type: ignore[assignment,misc]

__all__ = [
    "Broker",
    "CancelRegistry",
    "CancelScope",
    "InMemoryBroker",
    "InMemoryCancelRegistry",
    "OperationHandle",
    "RedisBroker",
    "RedisCancelRegistry",
    "TaskOperation",
]
