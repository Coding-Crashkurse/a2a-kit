# Hook Printer

Logs every lifecycle event to stdout, demonstrating all four hook types.

```python
from __future__ import annotations

import asyncio
from datetime import datetime

from a2a.types import Message, TaskState

from a2akit import A2AServer, AgentCardConfig, TaskContext, Worker
from a2akit.hooks import LifecycleHooks


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _msg_text(message: Message | None) -> str:
    if not message or not message.parts:
        return ""
    for part in message.parts:
        root = getattr(part, "root", part)
        if hasattr(root, "text") and root.text:
            return f" -- {root.text}"
    return ""


async def on_state_change(
    task_id: str, state: TaskState, message: Message | None
) -> None:
    short_id = task_id[:8]
    print(f"[{_ts()}] [{short_id}] STATE -> {state.value}{_msg_text(message)}")


async def on_working(task_id: str) -> None:
    short_id = task_id[:8]
    print(f"[{_ts()}] [{short_id}] WORKING -- task started processing")


async def on_turn_end(
    task_id: str, state: TaskState, message: Message | None
) -> None:
    short_id = task_id[:8]
    print(f"[{_ts()}] [{short_id}] {state.value.upper()}{_msg_text(message)}")


async def on_terminal(
    task_id: str, state: TaskState, message: Message | None
) -> None:
    short_id = task_id[:8]
    icon = {
        "completed": "+",
        "failed": "x",
        "canceled": "o",
        "rejected": "!",
    }.get(state.value, "?")
    print(
        f"[{_ts()}] [{short_id}] {icon} {state.value.upper()}{_msg_text(message)}"
    )


class DemoWorker(Worker):
    async def handle(self, ctx: TaskContext) -> None:
        await ctx.send_status("Thinking...")
        await asyncio.sleep(0.5)
        await ctx.send_status("Almost done...")
        await asyncio.sleep(0.5)
        await ctx.complete(f"Processed: {ctx.user_text}")


hooks = LifecycleHooks(
    on_state_change=on_state_change,
    on_working=on_working,
    on_turn_end=on_turn_end,
    on_terminal=on_terminal,
)

server = A2AServer(
    worker=DemoWorker(),
    agent_card=AgentCardConfig(
        name="Hook Printer",
        description="Demonstrates lifecycle hooks by printing every state change",
        version="0.1.0",
    ),
    hooks=hooks,
)
app = server.as_fastapi_app()
```

## Run it

```bash
uvicorn examples.hooks.server:app --reload
```

## Test it

```bash
curl -X POST http://localhost:8000/v1/message:send \
  -H "Content-Type: application/json" \
  -d '{"message":{"role":"user","parts":[{"text":"hello"}],"messageId":"1"}}'
```

## Expected output

In the server console:

```
[14:32:01.123] [a1b2c3d4] STATE -> working
[14:32:01.123] [a1b2c3d4] WORKING -- task started processing
[14:32:01.124] [a1b2c3d4] STATE -> working -- Thinking...
[14:32:01.625] [a1b2c3d4] STATE -> working -- Almost done...
[14:32:02.126] [a1b2c3d4] STATE -> completed
[14:32:02.126] [a1b2c3d4] + COMPLETED -- Processed: hello
```
