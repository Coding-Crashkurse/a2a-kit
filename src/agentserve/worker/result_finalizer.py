"""ResultFinalizer — translates TaskResult into A2A artifacts, messages, and events."""

from __future__ import annotations

import uuid

from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TextPart,
)

from agentserve.broker import Broker
from agentserve.storage import Storage
from agentserve.worker.base import TaskContextImpl, TaskResult


class ResultFinalizer:
    """Converts a TaskResult into A2A protocol objects and persists them."""

    def __init__(self, broker: Broker, storage: Storage) -> None:
        self._broker = broker
        self._storage = storage

    async def finalize(self, ctx: TaskContextImpl, result: TaskResult) -> None:
        """Finalize task execution — persist artifacts and complete the task."""
        if result.artifacts_emitted:
            await self._finalize_emitted(ctx)
        else:
            await self._finalize_result(ctx, result)

    async def _finalize_emitted(self, ctx: TaskContextImpl) -> None:
        """Worker streamed its own artifacts — just complete if not already terminal."""
        task = await self._storage.load_task(ctx.task_id)
        if task and task.status.state.value not in {
            "completed", "failed", "canceled", "rejected",
        }:
            await ctx.complete()

    async def _finalize_result(self, ctx: TaskContextImpl, result: TaskResult) -> None:
        """Translate TaskResult into an artifact + message, persist, and complete."""
        parts = self._build_parts(result)
        artifact = Artifact(
            artifact_id="final-answer",
            parts=parts,
            metadata=result.metadata,
        )
        agent_message = Message(
            role=Role.agent,
            parts=parts,
            message_id=str(uuid.uuid4()),
            metadata=ctx.metadata,
        )

        await self._storage.update_task(
            ctx.task_id,
            state="working",
            new_messages=[agent_message],
            new_artifacts=[artifact],
        )
        await self._broker.send_stream_event(
            ctx.task_id,
            TaskArtifactUpdateEvent(
                kind="artifact-update",
                task_id=ctx.task_id,
                context_id=ctx.context_id,
                artifact=artifact,
                append=False,
                last_chunk=True,
            ),
        )
        await ctx.complete()

    @staticmethod
    def _build_parts(result: TaskResult) -> list[Part]:
        """Extract or construct the final parts list from a TaskResult."""
        if result.parts:
            return result.parts
        if result.text:
            return [Part(TextPart(text=result.text))]
        return [Part(TextPart(text="(no result)"))]
