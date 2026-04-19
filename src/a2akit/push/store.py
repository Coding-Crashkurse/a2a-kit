"""Push notification config store - ABC and in-memory implementation."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from typing import Self

from a2akit.push.models import PushNotificationConfig, TaskPushNotificationConfig


class PushConfigStore(ABC):
    """Abstract store for push notification configurations."""

    @abstractmethod
    async def set_config(
        self, task_id: str, config: PushNotificationConfig
    ) -> TaskPushNotificationConfig:
        """Create or update a push config for a task.

        If config.id is None, generate a UUID.
        If config.id exists for this task_id, update it.
        """

    @abstractmethod
    async def get_config(
        self, task_id: str, config_id: str | None = None
    ) -> TaskPushNotificationConfig | None:
        """Get a specific config by task_id and config_id.

        If config_id is None, return the first/default config.
        """

    @abstractmethod
    async def list_configs(self, task_id: str) -> list[TaskPushNotificationConfig]:
        """List all configs for a task."""

    @abstractmethod
    async def delete_config(self, task_id: str, config_id: str) -> bool:
        """Delete a config. Returns True if it existed."""

    @abstractmethod
    async def get_configs_for_delivery(self, task_id: str) -> list[TaskPushNotificationConfig]:
        """Get all active configs for a task (used by delivery engine)."""

    @abstractmethod
    async def delete_configs_for_task(self, task_id: str) -> int:
        """Cascade-delete all configs for a task.

        Called by Storage.delete_task() and Storage.delete_context().
        Returns the number of deleted configs.
        """

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:  # noqa: B027
        """Clean up resources. Override in subclasses."""


class InMemoryPushConfigStore(PushConfigStore):
    """In-memory push config store for development and testing."""

    def __init__(self) -> None:
        # task_id -> {config_id -> TaskPushNotificationConfig}
        self._store: dict[str, dict[str, TaskPushNotificationConfig]] = {}

    async def set_config(
        self, task_id: str, config: PushNotificationConfig
    ) -> TaskPushNotificationConfig:
        config_id = config.id or str(uuid.uuid4())
        config = config.model_copy(update={"id": config_id})

        task_configs = self._store.setdefault(task_id, {})
        tpnc = TaskPushNotificationConfig(
            task_id=task_id,
            id=config_id,
            url=config.url,
            token=config.token,
            authentication=config.authentication,
        )
        task_configs[config_id] = tpnc
        return tpnc

    async def get_config(
        self, task_id: str, config_id: str | None = None
    ) -> TaskPushNotificationConfig | None:
        task_configs = self._store.get(task_id, {})
        if config_id:
            return task_configs.get(config_id)
        return next(iter(task_configs.values()), None)

    async def list_configs(self, task_id: str) -> list[TaskPushNotificationConfig]:
        return list(self._store.get(task_id, {}).values())

    async def delete_config(self, task_id: str, config_id: str) -> bool:
        task_configs = self._store.get(task_id, {})
        return task_configs.pop(config_id, None) is not None

    async def get_configs_for_delivery(self, task_id: str) -> list[TaskPushNotificationConfig]:
        return list(self._store.get(task_id, {}).values())

    async def delete_configs_for_task(self, task_id: str) -> int:
        configs = self._store.pop(task_id, {})
        return len(configs)
