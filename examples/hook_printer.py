"""Hook printer example — logs every lifecycle event to stdout."""

from __future__ import annotations

import asyncio
from datetime import datetime

from a2a.types import Message, TaskState

from a2akit import A2AServer, AgentCardConfig, TaskContext, Worker
from a2akit.hooks import LifecycleHooks


def _ts() -> str:
    """Short timestamp for log lines."""
    return datetime.now().strftime("%H:%M:%S.%f")[:-3]


def _msg_text(message: Message | None) -> str:
    """Extract text from a status message, if any."""
    if not message or not message.parts:
        return ""
    for part in message.parts:
        root = getattr(part, "root", part)
        if hasattr(root, "text") and root.text:
            return f" — {root.text}"
    return ""


async def on_state_change(task_id: str, state: TaskState, message: Message | None) -> None:
    """Catch-all: prints every state transition."""
    short_id = task_id[:8]
    print(f"[{_ts()}] [{short_id}] STATE → {state.value}{_msg_text(message)}")


async def on_working(task_id: str) -> None:
    """Prints when a task starts processing."""
    short_id = task_id[:8]
    print(f"[{_ts()}] [{short_id}] ⚙ WORKING — task started processing")


async def on_turn_end(task_id: str, state: TaskState, message: Message | None) -> None:
    """Prints when a task pauses for input."""
    short_id = task_id[:8]
    print(f"[{_ts()}] [{short_id}] ⏸ {state.value.upper()}{_msg_text(message)}")


async def on_terminal(task_id: str, state: TaskState, message: Message | None) -> None:
    """Prints when a task reaches a terminal state."""
    short_id = task_id[:8]
    icon = {"completed": "✓", "failed": "✗", "canceled": "⊘", "rejected": "⊗"}.get(
        state.value, "?"
    )
    print(f"[{_ts()}] [{short_id}] {icon} {state.value.upper()}{_msg_text(message)}")


# --- Worker that does a bit of everything to show all hooks ---


class DemoWorker(Worker):
    """Processes tasks with intermediate status updates to demonstrate hooks."""

    async def handle(self, ctx: TaskContext) -> None:
        """Handle a task with status updates before completing."""
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
        protocol="http+json",
    ),
    hooks=hooks,
)
app = server.as_fastapi_app()

# Run with: uvicorn examples.hook_printer:app --reload
#
# Expected output for a single message:
#
# [14:32:01.123] [a1b2c3d4] STATE → working
# [14:32:01.123] [a1b2c3d4] ⚙ WORKING — task started processing
# [14:32:01.124] [a1b2c3d4] STATE → working — Thinking...
# [14:32:01.124] [a1b2c3d4] ⚙ WORKING — task started processing
# [14:32:01.625] [a1b2c3d4] STATE → working — Almost done...
# [14:32:01.625] [a1b2c3d4] ⚙ WORKING — task started processing
# [14:32:02.126] [a1b2c3d4] STATE → completed
# [14:32:02.126] [a1b2c3d4] ✓ COMPLETED — Processed: hello
