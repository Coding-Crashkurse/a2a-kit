"""Pydantic models for push notification configuration (A2A Spec sections 6.8-6.10)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class PushNotificationAuthenticationInfo(BaseModel):
    """A2A section 6.9 - Auth details for the webhook endpoint."""

    schemes: list[str]
    credentials: str | None = None


class PushNotificationConfig(BaseModel):
    """A2A section 6.8 - Client-provided webhook configuration."""

    id: str | None = None
    url: str
    token: str | None = None
    authentication: PushNotificationAuthenticationInfo | None = None


class TaskPushNotificationConfig(BaseModel):
    """A2A section 6.10 - Binds a config to a specific task."""

    task_id: str = Field(alias="taskId")
    push_notification_config: PushNotificationConfig = Field(alias="pushNotificationConfig")

    model_config = {"populate_by_name": True}
