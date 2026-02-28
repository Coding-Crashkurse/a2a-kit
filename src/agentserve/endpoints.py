"""FastAPI router with all A2A protocol endpoints."""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator

from a2a.types import (
    AgentCard,
    Message,
    MessageSendParams,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
)
from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import JSONResponse
from sse_starlette import EventSourceResponse

from pydantic import BaseModel

from agentserve.schema import DirectReply, StreamEvent
from agentserve.storage.base import ListTasksQuery, TaskNotCancelableError, TaskNotFoundError
from agentserve.task_manager import TaskManager

logger = logging.getLogger(__name__)


class SendMessageResponse(BaseModel):
    """Spec-conformant response wrapper for message:send (§11.4)."""

    task: Task | None = None
    message: Message | None = None


def _wrap_stream_event(event: StreamEvent) -> str:
    """Wrap a stream event in the spec-conformant StreamResponse envelope."""
    # DirectReply is a dataclass wrapping a Message — handle before model_dump.
    if isinstance(event, DirectReply):
        raw = event.message.model_dump(mode="json", by_alias=True, exclude_none=True)
        return json.dumps({"message": raw})
    raw = event.model_dump(mode="json", by_alias=True, exclude_none=True)
    if isinstance(event, Task):
        return json.dumps({"task": raw})
    if isinstance(event, TaskStatusUpdateEvent):
        return json.dumps({"statusUpdate": raw})
    if isinstance(event, TaskArtifactUpdateEvent):
        return json.dumps({"artifactUpdate": raw})
    if isinstance(event, Message):
        return json.dumps({"message": raw})
    return json.dumps(raw)


def _get_tm(request: Request) -> TaskManager:
    """Extract the TaskManager from app state."""
    tm = getattr(request.app.state, "task_manager", None)
    if tm is None:
        raise HTTPException(status_code=503, detail="TaskManager not initialized")
    return tm


def _validate_ids(params: MessageSendParams) -> MessageSendParams:
    """Validate that messageId is present."""
    msg = params.message
    if not msg.message_id or not msg.message_id.strip():
        raise HTTPException(
            status_code=400,
            detail={"code": -32600, "message": "messageId is required."},
        )
    return params


def build_a2a_router() -> APIRouter:
    """Build and return the complete A2A API router."""
    router = APIRouter()

    @router.post("/v1/message:send")
    async def message_send(
        request: Request, params: MessageSendParams
    ) -> SendMessageResponse:
        """Submit a message and return the task wrapped in a SendMessageResponse."""
        params = _validate_ids(params)
        tm = _get_tm(request)
        result = await tm.send_message(params)
        if isinstance(result, Message):
            return SendMessageResponse(message=result)
        return SendMessageResponse(task=result)

    @router.post("/v1/message:stream")
    async def message_stream(
        request: Request, params: MessageSendParams
    ) -> EventSourceResponse:
        """Submit a message and stream events via SSE."""
        params = _validate_ids(params)
        tm = _get_tm(request)
        agen = tm.stream_message(params)
        first_event = await anext(agen)

        async def sse_gen() -> AsyncIterator[str]:
            """Yield JSON-serialized events for the SSE response."""
            try:
                yield _wrap_stream_event(first_event)
                async for ev in agen:
                    yield _wrap_stream_event(ev)
            except Exception:
                logger.exception("SSE stream aborted")
                return

        return EventSourceResponse(sse_gen())

    @router.get("/v1/tasks/{task_id}")
    async def tasks_get(
        request: Request,
        task_id: str = Path(),
        history_length: int | None = None,
    ) -> Task:
        """Get a single task by ID."""
        tm = _get_tm(request)
        t = await tm.get_task(task_id, history_length)
        if not t:
            raise HTTPException(
                status_code=404, detail={"code": -32001, "message": "Task not found"}
            )
        return t

    @router.get("/v1/tasks")
    async def tasks_list(
        request: Request,
        context_id: str | None = Query(None, alias="contextId"),
        status: TaskState | None = None,
        page_size: int = Query(50, alias="pageSize"),
        page_token: str | None = Query(None, alias="pageToken"),
        history_length: int | None = Query(None, alias="historyLength"),
        status_timestamp_after: str | None = Query(None, alias="statusTimestampAfter"),
        include_artifacts: bool = Query(False, alias="includeArtifacts"),
    ) -> JSONResponse:
        """List tasks with optional filters and pagination."""
        tm = _get_tm(request)
        query = ListTasksQuery(
            context_id=context_id,
            status=status,
            page_size=page_size,
            page_token=page_token,
            history_length=history_length,
            status_timestamp_after=status_timestamp_after,
            include_artifacts=include_artifacts,
        )
        result = await tm.list_tasks(query)
        return JSONResponse(
            content=json.loads(
                result.model_dump_json(by_alias=True, exclude_none=True)
            )
        )

    @router.post("/v1/tasks/{task_id}:cancel")
    async def tasks_cancel(
        request: Request,
        task_id: str = Path(),
    ) -> Task:
        """Cancel a task by ID."""
        tm = _get_tm(request)
        try:
            return await tm.cancel_task(task_id)
        except TaskNotFoundError:
            raise HTTPException(
                status_code=404, detail={"code": -32001, "message": "Task not found"}
            )
        except TaskNotCancelableError:
            raise HTTPException(
                status_code=409, detail={"code": -32002, "message": "Task is not cancelable"}
            )

    @router.post("/v1/tasks/{task_id}:subscribe")
    async def tasks_subscribe(
        request: Request, task_id: str = Path()
    ) -> EventSourceResponse:
        """Subscribe to updates for an existing task via SSE."""
        tm = _get_tm(request)
        agen = tm.subscribe_task(task_id)
        first_event = await anext(agen)

        async def sse_gen() -> AsyncIterator[str]:
            """Yield JSON-serialized events for the SSE response."""
            try:
                yield _wrap_stream_event(first_event)
                async for ev in agen:
                    yield _wrap_stream_event(ev)
            except Exception:
                logger.exception("SSE subscribe stream aborted")
                return

        return EventSourceResponse(sse_gen())

    @router.get("/v1/health")
    async def health_check():
        """Return a simple health status."""
        return {"status": "ok"}

    return router


def build_discovery_router(card_config) -> APIRouter:
    """Build the agent card discovery router."""
    from agentserve.agent_card import build_agent_card, external_base_url

    router = APIRouter()

    @router.get("/.well-known/agent-card.json")
    async def get_agent_card(request: Request) -> AgentCard:
        """Serve the agent discovery card with the correct base URL."""
        base_url = external_base_url(
            dict(request.headers),
            request.url.scheme,
            request.url.netloc,
        )
        return build_agent_card(card_config, base_url)

    return router
