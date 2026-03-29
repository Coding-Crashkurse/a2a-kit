"""a2akit — A2A agent framework in one import."""

from a2akit.agent_card import (
    AgentCardConfig,
    CapabilitiesConfig,
    ExtensionConfig,
    ProviderConfig,
    SignatureConfig,
    SkillConfig,
)
from a2akit.broker import (
    Broker,
    CancelRegistry,
    InMemoryBroker,
    InMemoryCancelRegistry,
)
from a2akit.client import A2AClient, ClientResult
from a2akit.client import StreamEvent as ClientStreamEvent
from a2akit.config import Settings, get_settings
from a2akit.dependencies import Dependency, DependencyContainer
from a2akit.errors import AuthenticationRequiredError
from a2akit.event_bus import EventBus, InMemoryEventBus
from a2akit.event_emitter import DefaultEventEmitter, EventEmitter
from a2akit.hooks import HookableEmitter, LifecycleHooks
from a2akit.middleware import (
    A2AMiddleware,
    ApiKeyMiddleware,
    BearerTokenMiddleware,
    RequestEnvelope,
)
from a2akit.push import (
    InMemoryPushConfigStore,
    PushConfigStore,
    PushNotificationAuthenticationInfo,
    PushNotificationConfig,
    TaskPushNotificationConfig,
)
from a2akit.server import A2AServer
from a2akit.storage import (
    ArtifactWrite,
    ContentTypeNotSupportedError,
    ContextMismatchError,
    InMemoryStorage,
    InvalidAgentResponseError,
    Storage,
    TaskNotAcceptingMessagesError,
    TaskNotCancelableError,
    TaskNotFoundError,
    TaskTerminalStateError,
    UnsupportedOperationError,
)
from a2akit.storage.base import ListTasksQuery, ListTasksResult
from a2akit.task_manager import TaskManager
from a2akit.telemetry import OTEL_ENABLED
from a2akit.worker import FileInfo, TaskContext, Worker

try:
    from a2akit.broker.redis import RedisBroker, RedisCancelRegistry
except ImportError:
    RedisBroker = None  # type: ignore[assignment,misc]
    RedisCancelRegistry = None  # type: ignore[assignment,misc]

try:
    from a2akit.event_bus.redis import RedisEventBus
except ImportError:
    RedisEventBus = None  # type: ignore[assignment,misc]

try:
    from a2akit.storage.redis import RedisStorage
except ImportError:
    RedisStorage = None  # type: ignore[assignment,misc]


__all__ = [
    "OTEL_ENABLED",
    "A2AClient",
    "A2AMiddleware",
    "A2AServer",
    "AgentCardConfig",
    "ApiKeyMiddleware",
    "ArtifactWrite",
    "AuthenticationRequiredError",
    "BearerTokenMiddleware",
    "Broker",
    "CancelRegistry",
    "CapabilitiesConfig",
    "ClientResult",
    "ClientStreamEvent",
    "ContentTypeNotSupportedError",
    "ContextMismatchError",
    "DefaultEventEmitter",
    "Dependency",
    "DependencyContainer",
    "EventBus",
    "EventEmitter",
    "ExtensionConfig",
    "FileInfo",
    "HookableEmitter",
    "InMemoryBroker",
    "InMemoryCancelRegistry",
    "InMemoryEventBus",
    "InMemoryPushConfigStore",
    "InMemoryStorage",
    "InvalidAgentResponseError",
    "LifecycleHooks",
    "ListTasksQuery",
    "ListTasksResult",
    "ProviderConfig",
    "PushConfigStore",
    "PushNotificationAuthenticationInfo",
    "PushNotificationConfig",
    "RedisBroker",
    "RedisCancelRegistry",
    "RedisEventBus",
    "RedisStorage",
    "RequestEnvelope",
    "Settings",
    "SignatureConfig",
    "SkillConfig",
    "Storage",
    "TaskContext",
    "TaskManager",
    "TaskNotAcceptingMessagesError",
    "TaskNotCancelableError",
    "TaskNotFoundError",
    "TaskPushNotificationConfig",
    "TaskTerminalStateError",
    "UnsupportedOperationError",
    "Worker",
    "get_settings",
]
