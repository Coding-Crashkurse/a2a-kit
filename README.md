# agentserve

A2A-compliant agent framework. One `Worker` class, one `handle()` method, all endpoints auto-registered.

## Setup

```bash
uv sync
```

For the LangGraph example:

```bash
uv sync --extra langgraph
```

## Examples

Three examples in the project root, each a standalone A2A agent:

| File | Pattern | Description |
| --- | --- | --- |
| `example_1.py` | Simple response | Returns text, framework handles artifacts + completion |
| `example_2.py` | Streaming artifacts | Emits word-by-word chunks via `ctx.emit_text_artifact()` |
| `example_3.py` | LangGraph pipeline | Runs a LangGraph graph with custom streaming, no LLM |

### Run

```bash
uv run uvicorn example_1:app --reload
uv run uvicorn example_2:app --reload
uv run uvicorn example_3:app --reload
```

### Test

```bash
curl http://localhost:8000/v1/health
curl http://localhost:8000/.well-known/agent-card.json

curl -X POST http://localhost:8000/v1/message:send \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "messageId": "00000000-0000-0000-0000-000000000001",
      "parts": [{"kind": "text", "text": "Hello!"}]
    }
  }'

# Stream (SSE)
curl -N -X POST http://localhost:8000/v1/message:stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": {
      "role": "user",
      "messageId": "00000000-0000-0000-0000-000000000002",
      "parts": [{"kind": "text", "text": "Hello!"}]
    }
  }'

# Get task by ID (replace with a real task ID from a previous response)
curl http://localhost:8000/v1/tasks/TASK_ID_HERE
```

## How it works

You implement `Worker.handle(ctx) -> TaskResult`. That's the only thing you write. The framework does everything else: state machine, persistence, streaming, artifact management, agent card discovery.

- **Simple**: return `TaskResult(text="...")` and the framework creates the artifact, persists the message, marks completed.
- **Streaming**: call `ctx.emit_text_artifact(chunk, append=True)` yourself, return `TaskResult(artifacts_emitted=True)`.
- **Progress**: call `ctx.send_status("Step 1...")` for intermediate updates, return a final `TaskResult`.

## TaskContext API

| Method / Property | Description |
| --- | --- |
| `ctx.user_text` | The user's input as plain text |
| `ctx.parts` | Raw message parts (text, files, etc.) |
| `ctx.task_id` | Current task UUID |
| `ctx.is_cancelled` | Check if cancellation was requested |
| `ctx.send_status(msg)` | Emit intermediate status update |
| `ctx.emit_text_artifact(...)` | Emit a text artifact (with streaming) |
| `ctx.emit_artifact(...)` | Emit an artifact with arbitrary parts |
| `ctx.complete(msg?)` | Mark task completed |
| `ctx.fail(reason)` | Mark task failed |
| `ctx.request_input(question)` | Ask user for more input |

## A2A Endpoints (auto-registered)

| Endpoint | Method | Description |
| --- | --- | --- |
| `/v1/message:send` | POST | Submit task (blocking) |
| `/v1/message:stream` | POST | Submit task (SSE stream) |
| `/v1/tasks/{id}` | GET | Get task by ID |
| `/v1/tasks` | GET | List tasks |
| `/v1/tasks/{id}:cancel` | POST | Cancel a task |
| `/.well-known/agent-card.json` | GET | Agent discovery card |
| `/v1/health` | GET | Health check |

## Custom Backends

Implement `Storage` or `Broker` ABCs and pass them to `A2AServer` instead of the default `"memory"` backends.
# a2a-kit
