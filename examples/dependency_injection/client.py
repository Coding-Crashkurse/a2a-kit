"""Client example — send a message to the DI demo server.

Start the DI server first:
    uvicorn examples.dependency_injection.server:app

Then run this client:
    python -m examples.dependency_injection.client
"""

import asyncio

from a2akit import A2AClient


async def main():
    async with A2AClient("http://localhost:8000") as client:
        print(f"Connected to: {client.agent_name}\n")

        result = await client.send("What dependencies are available?")
        print(f"Response:\n{result.text}")


if __name__ == "__main__":
    asyncio.run(main())
