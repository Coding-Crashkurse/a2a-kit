# Configuration

a2akit reads settings from environment variables prefixed with `A2AKIT_`. Every setting has a sensible default; explicit constructor parameters always take priority.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `A2AKIT_BLOCKING_TIMEOUT` | `30.0` | Seconds `message:send` blocks for a result |
| `A2AKIT_CANCEL_FORCE_TIMEOUT` | `60.0` | Seconds before force-cancel kicks in |
| `A2AKIT_MAX_CONCURRENT_TASKS` | *(none)* | Worker parallelism (`None` = unlimited) |
| `A2AKIT_MAX_RETRIES` | `3` | Broker retry attempts on worker crash |
| `A2AKIT_BROKER_BUFFER` | `1000` | InMemoryBroker queue depth |
| `A2AKIT_EVENT_BUFFER` | `200` | InMemoryEventBus fan-out buffer per task |
| `A2AKIT_LOG_LEVEL` | *(unset)* | Root `a2akit` logger level (e.g. `DEBUG`) |

## Priority

Settings are resolved in this order (highest priority first):

1. **Constructor parameter** — explicit values passed to `A2AServer()`
2. **Environment variable** — `A2AKIT_*` prefix
3. **Built-in default** — hardcoded in `Settings`

```
Constructor > Env-Var > Default
```

## Example

Set environment variables:

```bash
export A2AKIT_BLOCKING_TIMEOUT=10
export A2AKIT_LOG_LEVEL=DEBUG
export A2AKIT_MAX_CONCURRENT_TASKS=4
```

## Programmatic Override

Use `Settings()` to override defaults programmatically:

```python
from a2akit import A2AServer, Settings

custom = Settings(blocking_timeout=5.0, max_retries=5)
server = A2AServer(worker=..., agent_card=..., settings=custom)
```

## Settings Class

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="A2AKIT_")

    blocking_timeout: float = 30.0
    cancel_force_timeout: float = 60.0
    max_concurrent_tasks: int | None = None
    max_retries: int = 3
    broker_buffer: int = 1000
    event_buffer: int = 200
    log_level: str | None = None
```

The `Settings` class uses [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) for automatic environment variable binding.

## A2AServer Constructor Parameters

These constructor parameters override Settings values:

| Parameter | Settings Field | Description |
|-----------|---------------|-------------|
| `blocking_timeout_s` | `blocking_timeout` | Blocking timeout in seconds |
| `cancel_force_timeout_s` | `cancel_force_timeout` | Force-cancel timeout |
| `max_concurrent_tasks` | `max_concurrent_tasks` | Worker parallelism |

!!! tip "Development vs. Production"
    For development, the defaults work well. For production, consider:

    - Setting `A2AKIT_MAX_CONCURRENT_TASKS` to limit resource usage
    - Reducing `A2AKIT_BLOCKING_TIMEOUT` for faster client feedback
    - Setting `A2AKIT_LOG_LEVEL=INFO` for structured logging
