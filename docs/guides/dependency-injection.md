# Dependency Injection

Register shared infrastructure (database pools, HTTP clients, config objects) on the server and access them in your worker via `ctx.deps`.

## Example

```python
from dataclasses import dataclass
from a2akit import A2AServer, AgentCardConfig, Dependency, TaskContext, Worker


class HttpClient(Dependency):  # (1)!
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self._session = None

    async def startup(self) -> None:  # (2)!
        self._session = ...  # open connection pool

    async def shutdown(self) -> None:  # (3)!
        ...  # close connection pool


@dataclass
class AppConfig:  # (4)!
    model: str = "claude-sonnet"


class MyWorker(Worker):
    def __init__(self, system_prompt: str = "You are helpful.") -> None:
        self.system_prompt = system_prompt  # (5)!

    async def handle(self, ctx: TaskContext) -> None:
        client = ctx.deps[HttpClient]  # (6)!
        config = ctx.deps[AppConfig]
        api_key = ctx.deps.get("api_key", "fallback")  # (7)!
        await ctx.complete(f"Model: {config.model}")


server = A2AServer(
    worker=MyWorker(system_prompt="Analyze data."),
    agent_card=AgentCardConfig(
        name="Agent", description="...", version="0.1.0"
    ),
    dependencies={
        HttpClient: HttpClient(base_url="https://api.example.com"),
        AppConfig: AppConfig(model="claude-sonnet"),
        "api_key": "sk-...",
    },
)
app = server.as_fastapi_app()
```

1. Subclass `Dependency` for resources that need lifecycle management.
2. `startup()` is called during server startup, before the first request.
3. `shutdown()` is called during server shutdown, after the last request.
4. Plain values (dataclasses, dicts, strings) don't need `Dependency`.
5. Worker-specific config goes into the constructor — no DI needed.
6. Access by type key with `ctx.deps[Type]`. Raises `KeyError` if not registered.
7. Access by string key with `ctx.deps.get(key, default)`.

## Three Patterns

| Pattern | Registration | Lifecycle? | Access |
|---------|-------------|------------|--------|
| **Lifecycle-managed** | `{DbPool: pool}` where pool subclasses `Dependency` | `startup()` / `shutdown()` | `ctx.deps[DbPool]` |
| **Plain value** | `{AppConfig: config}` or `{"key": value}` | No | `ctx.deps[AppConfig]` or `ctx.deps.get("key")` |
| **Constructor injection** | `MyWorker(prompt="...")` | No | `self.prompt` in handle() |

### When to use which?

- **Lifecycle-managed**: Connection pools, HTTP sessions, cache clients — anything that needs explicit open/close.
- **Plain value**: Configuration objects, feature flags, static data — no lifecycle needed.
- **Constructor injection**: Worker-specific settings (system prompts, model names) that differ per worker instance.

## DependencyContainer

The `DependencyContainer` is a simple key-value store:

```python
container[HttpClient]          # get by type key (KeyError if missing)
container.get("api_key")       # get by string key (None if missing)
container.get("key", default)  # get with default
"api_key" in container         # check if registered
```

## Lifecycle Management

Dependencies that subclass `Dependency` get automatic lifecycle management:

- **`startup()`** is called in registration order during server startup.
- **`shutdown()`** is called in reverse order during server shutdown.
- **Rollback on failure**: If a dependency fails during startup, all already-started dependencies are shut down before the error is re-raised.
- **Idempotent**: A second call to `startup()` is a no-op.

!!! tip "Testing"
    In tests, you can pass different dependency registrations to `A2AServer` to swap real services for test doubles — no mocking framework needed.
