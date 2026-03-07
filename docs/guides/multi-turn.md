# Multi-Turn Conversations

a2akit supports multi-turn interactions where the agent asks the user for additional input or authentication before completing a task.

## Requesting Input

Use `ctx.request_input()` to pause the task and ask the user a question:

```python
from a2akit import Worker, TaskContext


class ClarifyWorker(Worker):
    async def handle(self, ctx: TaskContext) -> None:
        if not ctx.history:  # (1)!
            await ctx.request_input("What format do you want? (json/csv)")
            return

        # Second turn — user provided the format
        format_choice = ctx.user_text.lower()  # (2)!
        first_message = ctx.history[0].text  # (3)!
        await ctx.complete(
            f"Here is '{first_message}' in {format_choice} format: ..."
        )
```

1. On the first turn, there's no history. Ask for clarification.
2. On the follow-up turn, `ctx.user_text` contains the user's answer.
3. `ctx.history` gives you all previous messages in this task.

The task lifecycle looks like:

```
submitted -> working -> input_required -> submitted -> working -> completed
```

## Requesting Authentication

Use `ctx.request_auth()` when secondary credentials are needed:

```python
class AuthWorker(Worker):
    async def handle(self, ctx: TaskContext) -> None:
        token = ctx.request_context.get("user_token")
        if not token:
            await ctx.request_auth("Please provide your API token.")
            return

        # Token available — proceed
        result = await call_api(token)
        await ctx.complete(f"Result: {result}")
```

## History and Previous Artifacts

### `ctx.history`

Returns all previous messages in this task as `list[HistoryMessage]`, excluding the current message:

```python
for msg in ctx.history:
    print(f"[{msg.role}] {msg.text}")
    print(f"  message_id: {msg.message_id}")
    print(f"  parts: {msg.parts}")
```

Each `HistoryMessage` has:

| Field | Type | Description |
|-------|------|-------------|
| `role` | `str` | `"user"` or `"agent"` |
| `text` | `str` | Concatenated text from all text parts |
| `parts` | `list[Any]` | Raw A2A message parts |
| `message_id` | `str` | Unique message identifier |

### `ctx.previous_artifacts`

Returns artifacts from prior turns as `list[PreviousArtifact]`:

```python
for artifact in ctx.previous_artifacts:
    print(f"Artifact: {artifact.artifact_id}")
    print(f"  name: {artifact.name}")
    print(f"  parts: {artifact.parts}")
```

## Context Storage

For persistent conversation state beyond message history, use context storage:

```python
class StatefulWorker(Worker):
    async def handle(self, ctx: TaskContext) -> None:
        # Load previous context
        state = await ctx.load_context() or {"turns": 0}
        state["turns"] += 1

        # Save updated context
        await ctx.update_context(state)

        if state["turns"] < 3:
            await ctx.request_input(
                f"Turn {state['turns']}: Tell me more."
            )
        else:
            await ctx.complete(
                f"Completed after {state['turns']} turns!"
            )
```

!!! note "Context is per-conversation"
    Context is stored per `context_id`, not per task. Multiple tasks sharing the same `context_id` share the same stored context. If `context_id` is `None`, context operations are no-ops.

!!! tip "History vs. Context"
    Use `ctx.history` for reading previous messages (read-only, maintained by the framework). Use `ctx.load_context()` / `ctx.update_context()` for arbitrary persistent state you manage yourself.
