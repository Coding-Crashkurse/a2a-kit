# LangGraph Worker

Runs a LangGraph file-processing pipeline with custom streaming — no LLM required.

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
    """Empty state -- the graph communicates via custom stream events."""


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
            writer({
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
    """Runs a LangGraph file-processing pipeline and streams results via A2A."""

    async def handle(self, ctx: TaskContext) -> None:
        await ctx.send_status("Starting file processing pipeline...")
        lines: list[str] = []

        async for _mode, chunk in graph.astream({}, stream_mode=["custom"]):
            evt_type = chunk.get("type", "")

            if evt_type == "done":
                line = f"[{chunk['index']}/{chunk['total']}] {chunk['file']}"
                lines.append(line)
                await ctx.send_status(line)

            elif evt_type == "error":
                line = f"[{chunk['index']}/{chunk['total']}] {chunk['file']} - FAILED"
                lines.append(line)
                await ctx.send_status(line)

            elif evt_type == "summary":
                lines.append(
                    f"Summary: {chunk['succeeded']}/{chunk['total']} succeeded, "
                    f"{chunk['failed']} failed"
                )

        await ctx.complete("\n".join(lines))


server = A2AServer(
    worker=LangGraphWorker(),
    agent_card=AgentCardConfig(
        name="File Processor",
        description="LangGraph pipeline that processes files with streaming status",
        version="0.1.0",
    ),
)
app = server.as_fastapi_app()
```

## Run it

```bash
pip install a2akit[langgraph]
uvicorn examples.langgraph.server:app --reload
```

## Test it

```bash
curl -X POST http://localhost:8000/v1/message:send \
  -H "Content-Type: application/json" \
  -d '{"message":{"role":"user","parts":[{"text":"process files"}],"messageId":"1"}}'
```

## Expected output

```json
{
  "artifacts": [
    {
      "artifactId": "final-answer",
      "parts": [{
        "text": "[1/10] report_001.csv\n[2/10] report_002.csv\n[3/10] report_003.csv\n[4/10] report_004.csv - FAILED\n[5/10] report_005.csv\n[6/10] report_006.csv\n[7/10] report_007.csv - FAILED\n[8/10] report_008.csv\n[9/10] report_009.csv\n[10/10] report_010.csv\nSummary: 8/10 succeeded, 2 failed"
      }]
    }
  ]
}
```
