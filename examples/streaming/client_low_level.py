"""Client example — low-level streaming with full event control.

Start the streaming server first:
    uvicorn examples.streaming.server:app

Then run this client:
    python -m examples.streaming.client_low_level
"""

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
