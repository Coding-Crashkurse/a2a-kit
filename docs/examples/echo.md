# Echo Agent

The simplest possible a2akit agent — echoes the user's input back.

```python
from a2akit import A2AServer, AgentCardConfig, TaskContext, Worker


class EchoWorker(Worker):
    """Echoes the user's message back as-is."""

    async def handle(self, ctx: TaskContext) -> None:
        await ctx.complete(f"Echo: {ctx.user_text}")


server = A2AServer(
    worker=EchoWorker(),
    agent_card=AgentCardConfig(
        name="Echo", description="Echoes input", version="0.1.0"
    ),
)
app = server.as_fastapi_app()
```

## Run it

```bash
uvicorn examples.echo:app --reload
```

## Test it

```bash
curl -X POST http://localhost:8000/v1/message:send \
  -H "Content-Type: application/json" \
  -d '{"message":{"role":"user","parts":[{"text":"hello world"}],"messageId":"1"}}'
```

## Expected output

```json
{
  "id": "...",
  "contextId": "...",
  "status": {"state": "completed", "timestamp": "..."},
  "artifacts": [
    {
      "artifactId": "final-answer",
      "parts": [{"text": "Echo: hello world"}]
    }
  ]
}
```
