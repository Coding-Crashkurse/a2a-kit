"""Tests for WebhookDeliveryService."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import httpx
from a2a.types import Task, TaskState, TaskStatus

from a2akit.push.delivery import WebhookDeliveryService, _build_headers
from a2akit.push.models import (
    PushNotificationAuthenticationInfo,
    PushNotificationConfig,
    TaskPushNotificationConfig,
)


def _make_task(task_id: str = "task-1", state: str = "working") -> Task:
    return Task(
        id=task_id,
        context_id="ctx-1",
        kind="task",
        status=TaskStatus(state=TaskState(state), timestamp="2026-01-01T00:00:00Z"),
    )


def _make_config(
    task_id: str = "task-1",
    config_id: str = "cfg-1",
    url: str = "https://example.com/webhook",
    token: str | None = None,
) -> TaskPushNotificationConfig:
    return TaskPushNotificationConfig(
        task_id=task_id,
        push_notification_config=PushNotificationConfig(id=config_id, url=url, token=token),
    )


async def test_delivery_success():
    service = WebhookDeliveryService(max_retries=1, allow_http=True, timeout=5.0)
    await service.startup()

    mock_response = httpx.Response(200)
    with patch.object(service._http_client, "post", return_value=mock_response) as mock_post:
        config = _make_config(url="http://example.com/webhook")
        task = _make_task()
        await service.deliver([config], task)
        # Wait for async queue processing
        await asyncio.sleep(0.1)
        mock_post.assert_called_once()

    await service.shutdown()


async def test_delivery_no_retry_on_400():
    service = WebhookDeliveryService(max_retries=3, allow_http=True, timeout=5.0)
    await service.startup()

    mock_response = httpx.Response(400)
    with patch.object(service._http_client, "post", return_value=mock_response) as mock_post:
        config = _make_config(url="http://example.com/webhook")
        task = _make_task()
        await service.deliver([config], task)
        await asyncio.sleep(0.1)
        # Should not retry on 4xx
        assert mock_post.call_count == 1

    await service.shutdown()


async def test_delivery_rejects_invalid_url():
    service = WebhookDeliveryService(max_retries=1, allow_http=False, timeout=5.0)
    await service.startup()

    with patch.object(service._http_client, "post") as mock_post:
        # HTTP URL rejected in production mode
        config = _make_config(url="http://example.com/webhook")
        task = _make_task()
        await service.deliver([config], task)
        await asyncio.sleep(0.1)
        mock_post.assert_not_called()

    await service.shutdown()


async def test_delivery_strips_internal_metadata():
    """Webhook payload MUST NOT leak framework-internal metadata keys
    (``_idempotency_key``, ``_a2akit_direct_reply``, ...). REST/SSE
    clients get a sanitized Task — webhooks must get the same."""
    service = WebhookDeliveryService(max_retries=1, allow_http=True, timeout=5.0)
    await service.startup()

    task = Task(
        id="task-leak",
        context_id="ctx-1",
        kind="task",
        status=TaskStatus(state=TaskState("working"), timestamp="2026-01-01T00:00:00Z"),
        metadata={
            "_idempotency_key": "super-secret-idem",
            "_a2akit_direct_reply": "msg-123",
            "_a2akit_just_created": True,
            "public_label": "visible",
        },
    )

    captured: dict[str, object] = {}

    async def _fake_post(url, json, headers):
        captured["json"] = json
        return httpx.Response(200)

    with patch.object(service._http_client, "post", side_effect=_fake_post):
        config = _make_config(task_id="task-leak", url="http://example.com/webhook")
        await service.deliver([config], task)
        await asyncio.sleep(0.1)

    await service.shutdown()

    payload = captured.get("json")
    assert isinstance(payload, dict)
    metadata = payload.get("metadata") or {}
    # Internal keys (prefix _) must be stripped.
    assert "_idempotency_key" not in metadata
    assert "_a2akit_direct_reply" not in metadata
    assert "_a2akit_just_created" not in metadata
    # Public keys must survive.
    assert metadata.get("public_label") == "visible"


async def test_delivery_does_not_mutate_original_task():
    """Sanitization must not mutate the Task the worker is still holding."""
    service = WebhookDeliveryService(max_retries=1, allow_http=True, timeout=5.0)
    await service.startup()

    original_metadata = {
        "_idempotency_key": "keep-me",
        "public": "ok",
    }
    task = Task(
        id="task-nomutate",
        context_id="ctx-1",
        kind="task",
        status=TaskStatus(state=TaskState("working"), timestamp="2026-01-01T00:00:00Z"),
        metadata=dict(original_metadata),
    )

    with patch.object(service._http_client, "post", return_value=httpx.Response(200)):
        config = _make_config(task_id="task-nomutate", url="http://example.com/webhook")
        await service.deliver([config], task)
        await asyncio.sleep(0.1)

    await service.shutdown()
    # Original still carries the internal key — only the outbound copy was sanitized.
    assert task.metadata == original_metadata


def test_build_headers_basic():
    config = PushNotificationConfig(url="https://example.com")
    headers = _build_headers(config)
    assert headers["Content-Type"] == "application/json"
    assert headers["User-Agent"] == "a2akit-push/0.1"
    assert "X-A2A-Notification-Token" not in headers
    assert "Authorization" not in headers


def test_build_headers_with_token():
    config = PushNotificationConfig(url="https://example.com", token="secret")
    headers = _build_headers(config)
    assert headers["X-A2A-Notification-Token"] == "secret"


def test_build_headers_with_auth():
    auth = PushNotificationAuthenticationInfo(schemes=["Bearer"], credentials="my-jwt-token")
    config = PushNotificationConfig(url="https://example.com", authentication=auth)
    headers = _build_headers(config)
    assert headers["Authorization"] == "Bearer my-jwt-token"


async def test_startup_shutdown_lifecycle():
    service = WebhookDeliveryService()
    await service.startup()
    assert service._http_client is not None
    await service.shutdown()


async def test_shutdown_cancels_stuck_workers_before_closing_client():
    """Regression: shutdown() used to call ``asyncio.wait(..., timeout=30)``
    which returns on timeout without cancelling the workers. The workers
    then continued to use ``http_client`` concurrently with
    ``http_client.aclose()``, causing races.

    After the fix, workers that exceed the grace period are force-cancelled
    before the HTTP client is closed.
    """
    service = WebhookDeliveryService(
        max_retries=1,
        allow_http=True,
        timeout=5.0,
        shutdown_grace=0.1,
    )
    await service.startup()

    # Inject a worker task that ignores the sentinel and never exits on its own.
    stuck_started = asyncio.Event()

    async def _stuck_worker():
        stuck_started.set()
        await asyncio.sleep(3600)

    key = ("stuck-task", "stuck-cfg")
    service._delivery_queues[key] = asyncio.Queue()
    stuck_task = asyncio.create_task(_stuck_worker())
    service._queue_workers[key] = stuck_task

    await stuck_started.wait()
    await service.shutdown()

    # Worker was force-cancelled and HTTP client closed.
    assert stuck_task.cancelled() or stuck_task.done()


async def test_idle_timeout_cleans_up_queue():
    """Queue workers exit after idle_timeout when no new events arrive."""
    service = WebhookDeliveryService(max_retries=1, allow_http=True, timeout=5.0, idle_timeout=0.2)
    await service.startup()

    mock_response = httpx.Response(200)
    with patch.object(service._http_client, "post", return_value=mock_response):
        config = _make_config(url="http://example.com/webhook")
        task = _make_task()  # state=working, non-terminal
        await service.deliver([config], task)
        await asyncio.sleep(0.05)
        # Worker is alive, queue exists
        assert len(service._queue_workers) == 1

        # Wait for idle timeout to fire
        await asyncio.sleep(0.3)
        # Worker should have exited and cleaned up
        assert len(service._queue_workers) == 0
        assert len(service._delivery_queues) == 0

    await service.shutdown()
