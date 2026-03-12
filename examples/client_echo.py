"""Client example — send a message to the echo server.

Start the echo server first:
    uvicorn examples.echo:app

Then run this client:
    python -m examples.client_echo
"""

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
