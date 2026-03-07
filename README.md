# a2akit

[![PyPI](https://img.shields.io/pypi/v/a2akit)](https://pypi.org/project/a2akit/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/pypi/pyversions/a2akit)](https://pypi.org/project/a2akit/)
[![CI](https://github.com/Coding-Crashkurse/a2a-kit/actions/workflows/ci.yml/badge.svg)](https://github.com/Coding-Crashkurse/a2a-kit/actions)

**A2A agent framework in one import.**

Build [Agent-to-Agent (A2A)](https://google.github.io/A2A/) protocol agents with minimal boilerplate.
Streaming, cancellation, multi-turn conversations, and artifact handling — batteries included.

## Install

```bash
pip install a2akit
```

With optional LangGraph support:

```bash
pip install a2akit[langgraph]
```

## Quick Start

```python
from a2akit import A2AServer, AgentCardConfig, TaskContext, Worker


class EchoWorker(Worker):
    async def handle(self, ctx: TaskContext) -> None:
        await ctx.complete(f"Echo: {ctx.user_text}")


server = A2AServer(
    worker=EchoWorker(),
    agent_card=AgentCardConfig(
        name="Echo Agent",
        description="Echoes your input back.",
        version="0.1.0",
    ),
)
app = server.as_fastapi_app()
```

```bash
uvicorn my_agent:app --reload
```

## Features

- **One-liner setup** — `A2AServer` wires storage, broker, event bus, and endpoints
- **Streaming** — word-by-word artifact streaming via SSE
- **Cancellation** — cooperative and force-cancel with timeout fallback
- **Multi-turn** — `request_input()` / `request_auth()` for conversational flows
- **Direct reply** — `reply_directly()` for simple request/response without task tracking
- **Middleware** — pipeline for auth extraction, header injection, payload sanitization
- **Lifecycle hooks** — fire-and-forget callbacks on terminal state transitions
- **Dependency injection** — shared infrastructure with automatic lifecycle management
- **Pluggable backends** — PostgreSQL, SQLite, and more (Redis, RabbitMQ coming soon)
- **Type-safe** — full type hints, `py.typed` marker, PEP 561 compliant

📖 **[Full Documentation](https://markuslang1987.github.io/a2akit/)**

## Links

- [PyPI](https://pypi.org/project/a2akit/)
- [GitHub](https://github.com/markuslang1987/a2akit)
- [Changelog](https://github.com/markuslang1987/a2akit/blob/main/CHANGELOG.md)

## License

MIT
