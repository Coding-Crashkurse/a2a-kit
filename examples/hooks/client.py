"""Client example — send a message to the hooks server and watch server logs.

Start the hooks server first:
    uvicorn examples.hooks.server:app

Then run this client:
    python -m examples.hooks.client

Watch the server terminal for lifecycle hook output.
"""

import asyncio

from a2akit import A2AClient


async def main():
    async with A2AClient("http://localhost:8000") as client:
        print(f"Connected to: {client.agent_name}")
        print("Sending message (watch the server terminal for hook output)...\n")

        result = await client.send("Hello from hooks client!")
        print(f"Response: {result.text}")
        print(f"State: {result.state}")


if __name__ == "__main__":
    asyncio.run(main())
