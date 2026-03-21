"""Client example — send a message to the traced server.

Start the OTel server first:
    python -m examples.otel.server

Then run this client:
    python -m examples.otel.client

Check the server console or Jaeger UI for trace output.
"""

import asyncio

from a2akit import A2AClient


async def main():
    async with A2AClient("http://localhost:8000") as client:
        print(f"Connected to: {client.agent_name}")
        print("Sending message (check server console for trace spans)...\n")

        result = await client.send("Hello from OTel client!")
        print(f"Response: {result.text}")
        print(f"Task ID: {result.task_id}")


if __name__ == "__main__":
    asyncio.run(main())
