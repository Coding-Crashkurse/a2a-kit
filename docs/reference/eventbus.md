# EventBus

The EventBus provides 1:N event fan-out for streaming task events to SSE subscribers.

## EventBus ABC

::: a2akit.event_bus.base.EventBus
    options:
      members:
        - publish
        - subscribe
        - cleanup

### `publish(task_id, event) -> str | None`

Publish a stream event to all subscribers of a task. Returns an event ID if the backend supports it (e.g. Redis Streams), or `None` for backends that don't assign IDs.

Events MUST be delivered in the order they were published for a given `task_id`.

### `subscribe(task_id, *, after_event_id=None)`

Subscribe to stream events for a task. MUST be used as an async context manager:

```python
async with event_bus.subscribe(task_id) as stream:
    async for event in stream:
        process(event)
```

When `after_event_id` is provided, backends that support replay (e.g. Redis Streams) deliver events published after that ID.

### `cleanup(task_id)`

Release subscriber resources for a completed task. Must be idempotent.

## InMemoryEventBus

The default event bus for development. Uses `asyncio.Queue` for fan-out.

```python
from a2akit import A2AServer

server = A2AServer(
    worker=MyWorker(),
    agent_card=AgentCardConfig(...),
    event_bus="memory",  # default
)
```

The buffer size is configurable:

```bash
export A2AKIT_EVENT_BUFFER=200  # default
```

## EventEmitter

The `EventEmitter` is a facade that `TaskContext` uses to persist state (Storage) and broadcast events (EventBus) without knowing about either directly.

::: a2akit.event_emitter.EventEmitter
    options:
      members:
        - update_task
        - send_event

### Call Order Contract

1. `update_task()` — Storage write (authoritative, must succeed)
2. `send_event()` — EventBus publish (best-effort, may fail)

If `send_event` fails, the state is still correct in Storage. Clients polling via GET will see the right state.

## DefaultEventEmitter

The standard implementation that delegates to an EventBus and Storage pair:

- Storage write is authoritative
- EventBus failure is logged but not raised

## Stream Event Types

The `StreamEvent` union type covers all possible events:

```python
StreamEvent = (
    Task
    | Message
    | TaskStatusUpdateEvent
    | TaskArtifactUpdateEvent
    | DirectReply
)
```

| Type | Description |
|------|-------------|
| `Task` | Initial task snapshot (first event in a stream) |
| `TaskStatusUpdateEvent` | State transition with optional message |
| `TaskArtifactUpdateEvent` | Artifact creation or update |
| `DirectReply` | Internal wrapper for `reply_directly()` messages |
