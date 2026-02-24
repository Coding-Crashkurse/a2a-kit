"""A2AServer – one-liner setup for a fully functional A2A agent."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agentserve.agent_card import AgentCardConfig
from agentserve.broker import Broker, InMemoryBroker
from agentserve.endpoints import build_a2a_router, build_discovery_router
from agentserve.storage import (
    DuplicateMessageIdError,
    InMemoryStorage,
    MessageIdConflictError,
    MissingMessageIdError,
    Storage,
    TaskNotAcceptingMessagesError,
    TaskNotFoundError,
    TaskTerminalStateError,
)
from agentserve.task_manager import TaskManager
from agentserve.worker import Worker, _WorkerAdapter

logger = logging.getLogger(__name__)


class A2AServer:
    """High-level server that wires storage, broker, worker, and endpoints."""

    def __init__(
        self,
        *,
        worker: Worker,
        agent_card: AgentCardConfig,
        storage: str | Storage = "memory",
        broker: str | Broker = "memory",
        blocking_timeout_s: float = 30.0,
    ) -> None:
        """Store configuration for lazy initialization at startup."""
        self._worker = worker
        self._card_config = agent_card
        self._storage_spec = storage
        self._broker_spec = broker
        self._blocking_timeout_s = blocking_timeout_s

    def _build_storage(self) -> Storage:
        """Resolve the storage spec into a Storage instance."""
        if isinstance(self._storage_spec, Storage):
            return self._storage_spec
        if self._storage_spec == "memory":
            return InMemoryStorage()
        msg = f"Unknown storage backend: {self._storage_spec!r}. Use 'memory' or pass a Storage instance."
        raise ValueError(msg)

    def _build_broker(self) -> Broker:
        """Resolve the broker spec into a Broker instance."""
        if isinstance(self._broker_spec, Broker):
            return self._broker_spec
        if self._broker_spec == "memory":
            return InMemoryBroker()
        msg = f"Unknown broker backend: {self._broker_spec!r}. Use 'memory' or pass a Broker instance."
        raise ValueError(msg)

    def as_fastapi_app(self, **fastapi_kwargs: Any) -> FastAPI:
        """Create a fully configured FastAPI application."""
        server = self

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Initialize and tear down storage, broker, and worker adapter."""
            storage = server._build_storage()
            broker = server._build_broker()
            adapter = _WorkerAdapter(server._worker, broker, storage)
            tm = TaskManager(
                broker=broker,
                storage=storage,
                default_blocking_timeout_s=server._blocking_timeout_s,
            )

            app.state.task_manager = tm
            app.state.storage = storage
            app.state.broker = broker

            async with storage, broker, adapter.run():
                try:
                    yield
                finally:
                    del app.state.task_manager
                    del app.state.broker
                    del app.state.storage

        fastapi_kwargs.setdefault("title", self._card_config.name)
        fastapi_kwargs.setdefault("version", self._card_config.version)
        fastapi_kwargs.setdefault("description", self._card_config.description)

        app = FastAPI(lifespan=lifespan, **fastapi_kwargs)
        _register_exception_handlers(app)
        app.include_router(build_a2a_router())
        app.include_router(build_discovery_router(self._card_config))

        return app


def _register_exception_handlers(app: FastAPI) -> None:
    """Register JSON-RPC style exception handlers for A2A storage errors."""

    @app.exception_handler(TaskNotFoundError)
    async def _(_req: Request, _exc: TaskNotFoundError):
        return JSONResponse(status_code=404, content={"code": -32001, "message": "Task not found"})

    @app.exception_handler(TaskTerminalStateError)
    async def _(_req: Request, _exc: TaskTerminalStateError):
        return JSONResponse(status_code=409, content={"code": -32004, "message": "Task is terminal; cannot continue"})

    @app.exception_handler(MessageIdConflictError)
    async def _(_req: Request, _exc: MessageIdConflictError):
        return JSONResponse(status_code=409, content={"code": -32602, "message": "messageId bound to different task"})

    @app.exception_handler(DuplicateMessageIdError)
    async def _(_req: Request, _exc: DuplicateMessageIdError):
        return JSONResponse(status_code=409, content={"code": -32602, "message": "Duplicate messageId"})

    @app.exception_handler(TaskNotAcceptingMessagesError)
    async def _(_req: Request, exc: TaskNotAcceptingMessagesError):
        state = getattr(exc, "state", None)
        msg = f"Task is in state {state} and does not accept messages." if state else "Task does not accept messages."
        return JSONResponse(status_code=422, content={"code": -32602, "message": msg})

    @app.exception_handler(MissingMessageIdError)
    async def _(_req: Request, _exc: MissingMessageIdError):
        return JSONResponse(status_code=400, content={"code": -32600, "message": "messageId is required"})
