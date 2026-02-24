"""FastAPI router with all A2A protocol endpoints."""

from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator

from a2a.types import AgentCard, MessageSendParams, Task
from fastapi import APIRouter, HTTPException, Path, Request
from sse_starlette import EventSourceResponse

from agentserve.task_manager import TaskManager

logger = logging.getLogger(__name__)

UUID_RE = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"


def _get_tm(request: Request) -> TaskManager:
    """Extract the TaskManager from app state."""
    tm = getattr(request.app.state, "task_manager", None)
    if tm is None:
        raise HTTPException(status_code=503, detail="TaskManager not initialized")
    return tm


def _validate_ids(params: MessageSendParams) -> MessageSendParams:
    """Validate that messageId is present and all IDs are valid UUIDs."""
    msg = params.message
    if not msg.message_id or not msg.message_id.strip():
        raise HTTPException(status_code=400, detail={"code": -32600, "message": "messageId is required."})
    ids = [("message_id", msg.message_id)]
    if msg.task_id:
        ids.append(("task_id", msg.task_id))
    if msg.context_id:
        ids.append(("context_id", msg.context_id))
    for name, value in ids:
        if not re.match(UUID_RE, value):
            raise HTTPException(status_code=400, detail=f"Invalid UUID for '{name}': {value}")
    return params


def build_a2a_router() -> APIRouter:
    """Build and return the complete A2A API router."""
    router = APIRouter()

    @router.post("/v1/message:send")
    async def message_send(request: Request, params: MessageSendParams) -> Task:
        """Submit a message and return the task."""
        params = _validate_ids(params)
        tm = _get_tm(request)
        return await tm.send_message(params)

    @router.post("/v1/message:stream")
    async def message_stream(request: Request, params: MessageSendParams) -> EventSourceResponse:
        """Submit a message and stream events via SSE."""
        params = _validate_ids(params)
        tm = _get_tm(request)
        agen = tm.stream_message(params)
        first_event = await anext(agen)

        async def sse_gen() -> AsyncIterator[str]:
            """Yield JSON-serialized events for the SSE response."""
            try:
                yield first_event.model_dump_json(by_alias=True, exclude_none=True)
                async for ev in agen:
                    yield ev.model_dump_json(by_alias=True, exclude_none=True)
            except Exception:
                logger.exception("SSE stream aborted")
                return

        return EventSourceResponse(sse_gen())

    @router.get("/v1/tasks/{task_id}")
    async def tasks_get(
        request: Request,
        task_id: str = Path(pattern=UUID_RE),
        history_length: int | None = None,
    ) -> Task:
        """Get a single task by ID."""
        tm = _get_tm(request)
        t = await tm.get_task(task_id, history_length)
        if not t:
            raise HTTPException(status_code=404, detail={"code": -32001, "message": "Task not found"})
        return t

    @router.get("/v1/tasks")
    async def tasks_list(request: Request, limit: int = 50) -> list[Task]:
        """List all tasks up to the given limit."""
        tm = _get_tm(request)
        return await tm.list_tasks(limit)

    @router.post("/v1/tasks/{task_id}:cancel")
    async def tasks_cancel(
        request: Request,
        task_id: str = Path(pattern=UUID_RE),
    ) -> Task:
        """Cancel a task by ID."""
        tm = _get_tm(request)
        t = await tm.cancel_task(task_id)
        if not t:
            raise HTTPException(status_code=404, detail={"code": -32001, "message": "Task not found"})
        return t

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
