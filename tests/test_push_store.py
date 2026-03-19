"""Tests for InMemoryPushConfigStore CRUD operations."""

from __future__ import annotations

import pytest

from a2akit.push.models import (
    PushNotificationAuthenticationInfo,
    PushNotificationConfig,
)
from a2akit.push.store import InMemoryPushConfigStore


@pytest.fixture
def push_store():
    return InMemoryPushConfigStore()


async def test_set_config_creates_new(push_store):
    config = PushNotificationConfig(url="https://example.com/webhook")
    result = await push_store.set_config("task-1", config)
    assert result.task_id == "task-1"
    assert result.push_notification_config.url == "https://example.com/webhook"
    assert result.push_notification_config.id is not None


async def test_set_config_with_explicit_id(push_store):
    config = PushNotificationConfig(id="cfg-1", url="https://example.com/webhook")
    result = await push_store.set_config("task-1", config)
    assert result.push_notification_config.id == "cfg-1"


async def test_set_config_update_existing(push_store):
    config = PushNotificationConfig(id="cfg-1", url="https://example.com/webhook")
    await push_store.set_config("task-1", config)

    updated = PushNotificationConfig(id="cfg-1", url="https://example.com/webhook2")
    result = await push_store.set_config("task-1", updated)
    assert result.push_notification_config.url == "https://example.com/webhook2"

    configs = await push_store.list_configs("task-1")
    assert len(configs) == 1


async def test_get_config_existing(push_store):
    config = PushNotificationConfig(id="cfg-1", url="https://example.com/webhook")
    await push_store.set_config("task-1", config)

    result = await push_store.get_config("task-1", "cfg-1")
    assert result is not None
    assert result.push_notification_config.url == "https://example.com/webhook"


async def test_get_config_not_found(push_store):
    result = await push_store.get_config("task-1", "nonexistent")
    assert result is None


async def test_get_config_default(push_store):
    config = PushNotificationConfig(url="https://example.com/webhook")
    await push_store.set_config("task-1", config)

    result = await push_store.get_config("task-1")
    assert result is not None
    assert result.push_notification_config.url == "https://example.com/webhook"


async def test_list_configs_empty(push_store):
    configs = await push_store.list_configs("task-1")
    assert configs == []


async def test_list_configs_multiple(push_store):
    await push_store.set_config("task-1", PushNotificationConfig(id="a", url="https://a.com"))
    await push_store.set_config("task-1", PushNotificationConfig(id="b", url="https://b.com"))
    configs = await push_store.list_configs("task-1")
    assert len(configs) == 2


async def test_delete_config_existing(push_store):
    await push_store.set_config(
        "task-1", PushNotificationConfig(id="cfg-1", url="https://example.com")
    )
    assert await push_store.delete_config("task-1", "cfg-1") is True
    assert await push_store.get_config("task-1", "cfg-1") is None


async def test_delete_config_not_found(push_store):
    assert await push_store.delete_config("task-1", "nonexistent") is False


async def test_configs_isolated_per_task(push_store):
    await push_store.set_config("task-1", PushNotificationConfig(id="cfg-1", url="https://a.com"))
    await push_store.set_config("task-2", PushNotificationConfig(id="cfg-1", url="https://b.com"))
    configs1 = await push_store.list_configs("task-1")
    configs2 = await push_store.list_configs("task-2")
    assert len(configs1) == 1
    assert len(configs2) == 1
    assert configs1[0].push_notification_config.url == "https://a.com"
    assert configs2[0].push_notification_config.url == "https://b.com"


async def test_get_configs_for_delivery(push_store):
    await push_store.set_config("task-1", PushNotificationConfig(id="a", url="https://a.com"))
    await push_store.set_config("task-1", PushNotificationConfig(id="b", url="https://b.com"))
    configs = await push_store.get_configs_for_delivery("task-1")
    assert len(configs) == 2


async def test_delete_configs_for_task(push_store):
    await push_store.set_config("task-1", PushNotificationConfig(id="a", url="https://a.com"))
    await push_store.set_config("task-1", PushNotificationConfig(id="b", url="https://b.com"))
    count = await push_store.delete_configs_for_task("task-1")
    assert count == 2
    assert await push_store.list_configs("task-1") == []


async def test_delete_configs_for_task_empty(push_store):
    count = await push_store.delete_configs_for_task("task-1")
    assert count == 0


async def test_delete_configs_for_task_isolates(push_store):
    await push_store.set_config("task-1", PushNotificationConfig(id="a", url="https://a.com"))
    await push_store.set_config("task-2", PushNotificationConfig(id="b", url="https://b.com"))
    await push_store.delete_configs_for_task("task-1")
    assert await push_store.list_configs("task-1") == []
    assert len(await push_store.list_configs("task-2")) == 1


async def test_set_config_with_auth(push_store):
    auth = PushNotificationAuthenticationInfo(schemes=["Bearer"], credentials="my-token")
    config = PushNotificationConfig(url="https://example.com/webhook", authentication=auth)
    result = await push_store.set_config("task-1", config)
    assert result.push_notification_config.authentication is not None
    assert result.push_notification_config.authentication.schemes == ["Bearer"]
    assert result.push_notification_config.authentication.credentials == "my-token"
