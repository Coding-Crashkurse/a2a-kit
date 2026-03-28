# Troubleshooting / FAQ

Common issues and how to resolve them.

## Errors

### TaskNotAcceptingMessagesError

**Symptom:** Client gets a `-32602` error when sending a follow-up message.

**Cause:** The task is in a state that doesn't accept new messages. Only `input-required` and `auth-required` tasks accept follow-ups.

**Fix:** Check `task.status.state` before sending. If the task is `completed`, `failed`, `canceled`, or `rejected`, start a new task instead.

```python
result = await client.send("follow-up", task_id=task.id)
# This fails if task is already completed
```

### ContentTypeNotSupportedError (-32005)

**Symptom:** Client gets a `-32005` error when sending a message.

**Cause:** The agent declared `defaultInputModes` in its agent card, and the message contains parts with incompatible MIME types.

**Fix:** Check the agent card's `defaultInputModes` and send only supported content types. If the agent accepts `text/plain`, send text parts. If it accepts `application/json`, send data parts.

### UnsupportedOperationError on streaming

**Symptom:** Client gets an error when calling `stream()` or `subscribe()`.

**Cause:** The agent doesn't have streaming enabled.

**Fix:** Enable streaming in the agent's capabilities:

```python
AgentCardConfig(
    capabilities=CapabilitiesConfig(streaming=True),
    ...
)
```

### Blocking request returns timeout error

**Symptom:** `configuration.blocking: true` request fails with "did not complete within N seconds".

**Cause:** The task took longer than `default_blocking_timeout_s` (default: 30s).

**Fix:** Either increase the timeout on the server, switch to non-blocking + polling, or use streaming:

```python
# Server-side: increase timeout
server = A2AServer(..., blocking_timeout_s=120)

# Client-side: use streaming instead
async for event in client.stream("long running task"):
    print(event.text, end="")
```

## Task Stuck in Working

**Symptom:** A task stays in `working` state indefinitely.

**Possible causes:**

1. **Worker never calls a lifecycle method.** Every `handle()` invocation must call exactly one of: `complete()`, `fail()`, `reject()`, `request_input()`, `request_auth()`, `respond()`, or `reply_directly()`. If `handle()` returns without calling any of these, the framework auto-fails the task.

2. **Worker is stuck in a long-running operation.** Check `ctx.is_cancelled` periodically in loops:

    ```python
    async def handle(self, ctx: TaskContext) -> None:
        for chunk in long_process():
            if ctx.is_cancelled:
                await ctx.fail("Cancelled by user")
                return
            await ctx.emit_text_artifact(chunk)
        await ctx.complete()
    ```

3. **Force-cancel timeout.** When a cancel is requested, the framework waits `cancel_force_timeout_s` (default: 10s) before force-transitioning to `canceled`. If the worker is blocking on I/O, the force-cancel will kick in.

## SSE Stream Drops

**Symptom:** SSE connection drops after ~60 seconds with no events.

**Cause:** Your reverse proxy or load balancer has a read timeout that closes idle connections.

**Fix:**

- **nginx:** Set `proxy_read_timeout 3600s` on SSE endpoints
- **AWS ALB:** Increase idle timeout (default 60s, max 4000s)
- **Client-side:** Use `subscribe()` with `last_event_id` for automatic reconnection:

    ```python
    result = await client.subscribe(task_id, last_event_id=last_id)
    ```

## Redis Connection Issues

### Broker not picking up tasks

**Symptom:** Tasks stay in `submitted` state, worker never processes them.

**Cause:** The broker consumer group may not exist yet, or the worker isn't running.

**Fix:** `RedisBroker` creates consumer groups automatically on startup. Ensure the server's lifespan completes (check logs for "Redis broker ready"). If using `docker compose`, ensure the `depends_on` health check passes.

### Events not delivered across workers

**Symptom:** SSE subscribers on worker A don't see events from worker B.

**Cause:** You're using `InMemoryEventBus` instead of `RedisEventBus`.

**Fix:** Pass `event_bus="redis://..."` to `A2AServer`. In-memory backends don't share state across processes.

## Storage Issues

### History is None when expected

**Symptom:** `ctx.history` is empty even though multiple messages were sent.

**Cause:** `historyLength=0` was passed in the request configuration, or the task is new (first message).

**Fix:** Check `ctx.history is not None` before accessing. On the first invocation, history contains only the current message context.

### Artifacts missing on polling

**Symptom:** `tasks/get` returns no artifacts even though the stream shows them.

**Cause:** With non-blocking requests, a2akit uses deferred storage — intermediate artifacts are only persisted on the terminal write. SSE subscribers see every chunk in real-time, but polling clients only see the final state.

**Fix:** Use SSE streaming for real-time updates, or poll only after the task reaches a terminal state.

## Debug UI

### /chat returns 404

**Symptom:** Navigating to `http://localhost:8000/chat` returns 404.

**Cause:** The debug UI is not enabled.

**Fix:** Pass `debug=True` when creating the app:

```python
app = server.as_fastapi_app(debug=True)
```

The debug UI is disabled by default and should not be enabled in production.
