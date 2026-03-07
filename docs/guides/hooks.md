# Lifecycle Hooks

Register callbacks that fire after state transitions. Hooks are fire-and-forget — errors are logged and swallowed, never affecting task processing.

## Example

```python
import logging
from a2a.types import Message, TaskState
from a2akit import A2AServer, AgentCardConfig, TaskContext, Worker
from a2akit.hooks import LifecycleHooks

logger = logging.getLogger(__name__)


async def on_terminal(
    task_id: str, state: TaskState, message: Message | None
) -> None:
    """Called once per task when it reaches a terminal state."""
    if state == TaskState.completed:
        logger.info("Task %s completed successfully", task_id)
    elif state == TaskState.failed:
        logger.warning("Task %s failed: %s", task_id, message)


class MyWorker(Worker):
    async def handle(self, ctx: TaskContext) -> None:
        await ctx.complete(f"Done: {ctx.user_text}")


server = A2AServer(
    worker=MyWorker(),
    agent_card=AgentCardConfig(
        name="Hooked Agent", description="...", version="0.1.0"
    ),
    hooks=LifecycleHooks(on_terminal=on_terminal),  # (1)!
)
app = server.as_fastapi_app()
```

1. Pass a `LifecycleHooks` instance with only the callbacks you need. All are optional.

## Available Hooks

### `on_state_change(task_id, state, message)`

Called on **every** state transition. Catch-all for audit logs, debug tracing, and state-machine visualization.

```python
async def on_state_change(
    task_id: str, state: TaskState, message: Message | None
) -> None:
    print(f"Task {task_id} -> {state.value}")
```

### `on_working(task_id)`

Called when a task starts processing (state becomes `working`). Use for metrics (start duration timer) or "agent is typing" indicators.

```python
async def on_working(task_id: str) -> None:
    start_timer(task_id)
```

### `on_turn_end(task_id, state, message)`

Called when a task pauses for input (`input_required` or `auth_required`). Use for user notifications, timeout timers, or conversation tracking.

```python
async def on_turn_end(
    task_id: str, state: TaskState, message: Message | None
) -> None:
    await notify_user(task_id, "Agent needs your input")
```

### `on_terminal(task_id, state, message)`

Called when a task reaches a terminal state (`completed`, `failed`, `canceled`, `rejected`). Use for metrics, alerting, and cleanup.

```python
async def on_terminal(
    task_id: str, state: TaskState, message: Message | None
) -> None:
    record_metric("task_completed", tags={"state": state.value})
```

## Hook Dispatch Order

For a single `update_task` call, hooks fire in this order:

1. `on_state_change` (if state is not None)
2. Exactly one of: `on_working`, `on_turn_end`, or `on_terminal` (based on the new state)

## HookableEmitter

Hooks are implemented via `HookableEmitter`, a decorator around any `EventEmitter`. It fires hooks **after** successful Storage writes:

- If the write succeeds, the hook fires.
- If the write throws (`ConcurrencyError`, `TaskTerminalStateError`), the hook does **not** fire.

This provides **exactly-once** hook delivery per successful state transition without any external coordination.

!!! warning "Hooks are fire-and-forget"
    Hook errors are logged and swallowed. A failing hook will never prevent a task from completing or cause a retry. Design your hooks to be resilient — use try/except internally if needed.

!!! tip "Exactly-once delivery"
    The Storage terminal-state guard ensures that once a task reaches a terminal state, no further state transitions can occur. Combined with the HookableEmitter pattern, this guarantees that `on_terminal` fires exactly once per task.
