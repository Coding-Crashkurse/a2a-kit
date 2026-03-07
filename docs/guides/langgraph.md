# LangGraph Integration

a2akit integrates with [LangGraph](https://langchain-ai.github.io/langgraph/) by letting you run a StateGraph inside a Worker and stream results via the A2A protocol.

## Installation

```bash
pip install a2akit[langgraph]
```

## Example

```python
import asyncio
from typing import TypedDict

from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph

from a2akit import A2AServer, AgentCardConfig, TaskContext, Worker

TOTAL = 10
BROKEN = {4, 7}
DELAY = 0.5


class FileProcessingState(TypedDict):
    """Empty state — the graph communicates via custom stream events."""


async def process_node(state: FileProcessingState):
    """Simulate processing files, emitting progress via stream writer."""
    writer = get_stream_writer()
    succeeded = 0
    failed = 0

    for i in range(1, TOTAL + 1):
        name = f"report_{i:03d}.csv"
        await asyncio.sleep(DELAY)

        if i in BROKEN:
            failed += 1
            writer({  # (1)!
                "type": "error",
                "file": name,
                "index": i,
                "total": TOTAL,
            })
        else:
            succeeded += 1
            writer({
                "type": "done",
                "file": name,
                "index": i,
                "total": TOTAL,
            })

    writer({
        "type": "summary",
        "succeeded": succeeded,
        "failed": failed,
        "total": TOTAL,
    })
    return {}


graph = (
    StateGraph(FileProcessingState)
    .add_node("process", process_node)
    .add_edge(START, "process")
    .add_edge("process", END)
    .compile()
)


class LangGraphWorker(Worker):
    """Runs a LangGraph pipeline and streams results via A2A."""

    async def handle(self, ctx: TaskContext) -> None:
        await ctx.send_status("Starting file processing pipeline...")
        lines: list[str] = []

        async for _mode, chunk in graph.astream(  # (2)!
            {}, stream_mode=["custom"]
        ):
            evt_type = chunk.get("type", "")

            if evt_type == "done":
                line = f"[{chunk['index']}/{chunk['total']}] {chunk['file']}"
                lines.append(line)
                await ctx.send_status(line)  # (3)!

            elif evt_type == "error":
                line = f"[{chunk['index']}/{chunk['total']}] {chunk['file']} - FAILED"
                lines.append(line)
                await ctx.send_status(line)

            elif evt_type == "summary":
                lines.append(
                    f"Summary: {chunk['succeeded']}/{chunk['total']} succeeded, "
                    f"{chunk['failed']} failed"
                )

        await ctx.complete("\n".join(lines))  # (4)!


server = A2AServer(
    worker=LangGraphWorker(),
    agent_card=AgentCardConfig(
        name="File Processor",
        description="LangGraph pipeline with streaming status",
        version="0.1.0",
    ),
)
app = server.as_fastapi_app()
```

1. LangGraph's `get_stream_writer()` emits custom events from graph nodes.
2. `astream` with `stream_mode=["custom"]` yields only custom events, not state snapshots.
3. Map LangGraph events to a2akit's `send_status()` for real-time client updates.
4. Collect all results and emit a final artifact on completion.

## Key Patterns

### Mapping LangGraph Events to A2A

| LangGraph | a2akit |
|-----------|--------|
| `get_stream_writer()` events | `ctx.send_status()` for progress, `ctx.emit_text_artifact()` for content |
| Graph completion | `ctx.complete()` with final result |
| Graph exception | Caught by framework, auto-fails the task |

### Streaming Modes

LangGraph offers several stream modes. The most useful for A2A integration:

- **`"custom"`** — Only custom events via `get_stream_writer()`. Best for progress reporting.
- **`"values"`** — Full state after each node. Useful for streaming intermediate results.
- **`"updates"`** — Per-node output diffs. Good for debugging.

### Cancellation

Check `ctx.is_cancelled` between graph steps or within long-running nodes:

```python
async def process_node(state):
    writer = get_stream_writer()
    for item in items:
        # Note: ctx is not available inside LangGraph nodes,
        # so use a shared cancel flag or check at the worker level
        writer({"type": "progress", "item": item})
```

!!! tip "No LLM required"
    The example above doesn't use any LLM — it demonstrates pure graph orchestration with custom streaming. You can add LLM nodes (ChatOpenAI, ChatAnthropic, etc.) as you would in any LangGraph app.
