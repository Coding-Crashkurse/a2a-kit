# Streaming Agent

Emits the user's input word-by-word as streaming artifacts with progress updates.

```python
import asyncio
from a2akit import A2AServer, AgentCardConfig, CapabilitiesConfig, TaskContext, Worker


class StreamingWorker(Worker):
    """Streams the user's input back word by word."""

    async def handle(self, ctx: TaskContext) -> None:
        words = ctx.user_text.split()
        await ctx.send_status(f"Streaming {len(words)} words...")

        for i, word in enumerate(words):
            is_last = i == len(words) - 1
            await ctx.emit_text_artifact(
                text=word + ("" if is_last else " "),
                artifact_id="stream",
                append=(i > 0),
                last_chunk=is_last,
            )
            await asyncio.sleep(0.1)

        await ctx.complete()


server = A2AServer(
    worker=StreamingWorker(),
    agent_card=AgentCardConfig(
        name="Streamer",
        description="Word-by-word streaming",
        version="0.1.0",
        capabilities=CapabilitiesConfig(streaming=True),
    ),
)
app = server.as_fastapi_app()
```

## Run it

```bash
uvicorn examples.streaming.server:app --reload
```

## Test it

Use the streaming endpoint to see events arrive in real-time. The framework defaults to A2A v1.0 — use the bare `/message:stream` path and v1.0 wire shape (`"role": "ROLE_USER"`, flat `parts`):

```bash
curl -N -X POST http://localhost:8000/message:stream \
  -H "Content-Type: application/json" \
  -d '{"message":{"role":"ROLE_USER","parts":[{"text":"hello beautiful world"}],"messageId":"1"}}'
```

For v0.3 clients, pass `protocol_version="0.3"` to `A2AServer` and hit `/v1/message:stream` with `"role": "user"` instead.

## Expected output

A stream of SSE events:

1. Task snapshot with `state: TASK_STATE_SUBMITTED` (v1.0) / `submitted` (v0.3)
2. Status update: "Streaming 3 words..."
3. Artifact update: "hello " (append=false)
4. Artifact update: "beautiful " (append=true)
5. Artifact update: "world" (append=true, last_chunk=true)
6. Final status: `state: TASK_STATE_COMPLETED` (v1.0) / `completed` (v0.3)
