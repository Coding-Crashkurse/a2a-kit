# Client Examples

Three examples showing how to use `A2AClient` to interact with A2A agents.

## Echo Client

Send a message and print the response.

```python
import asyncio

from a2akit import A2AClient


async def main():
    async with A2AClient("http://localhost:8000") as client:
        print(f"Connected to: {client.agent_name}")

        result = await client.send("Hello, agent!")
        print(f"Response: {result.text}")
        print(f"State: {result.state}")
        print(f"Task ID: {result.task_id}")


if __name__ == "__main__":
    asyncio.run(main())
```

### Run it

```bash
# Terminal 1: start the echo server
uvicorn examples.echo.server:app

# Terminal 2: run the client
python -m examples.echo.client
```

## Streaming Client (High-Level)

Use `stream_text()` to receive plain strings.

```python
import asyncio

from a2akit import A2AClient


async def main():
    async with A2AClient("http://localhost:8000") as client:
        print(f"Connected to: {client.agent_name}\n")

        async for chunk in client.stream_text("Hello world from the client"):
            print(chunk, end="", flush=True)

        print("\n\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
```

### Run it

```bash
# Terminal 1: start the streaming server
uvicorn examples.streaming.server:app

# Terminal 2: run the client
python -m examples.streaming.client
```

## Streaming Client (Low-Level)

Use `stream()` for full event control.

```python
import asyncio

from a2akit import A2AClient


async def main():
    async with A2AClient("http://localhost:8000") as client:
        print(f"Connected to: {client.agent_name}\n")

        async for event in client.stream("Hello world from the client"):
            if event.kind == "task":
                print(f"[task] state={event.state}")
            elif event.kind == "status":
                print(f"[status] {event.text or event.state}")
            elif event.kind == "artifact":
                print(f"[artifact:{event.artifact_id}] {event.text}", end="", flush=True)

            if event.is_final:
                print(f"\n[final] state={event.state}")

        print("\nDone!")


if __name__ == "__main__":
    asyncio.run(main())
```

### Run it

```bash
# Terminal 1: start the streaming server
uvicorn examples.streaming.server:app

# Terminal 2: run the client
python -m examples.streaming.client_low_level
```
