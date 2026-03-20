"""Client example — send a message with metadata to show middleware extraction.

Start the middleware server first:
    uvicorn examples.middleware.server:app

Then run this client:
    python -m examples.middleware.client
"""

import asyncio

from a2akit import A2AClient


async def main():
    async with A2AClient("http://localhost:8000") as client:
        print(f"Connected to: {client.agent_name}\n")

        result = await client.send(
            "Show me what the worker sees",
            metadata={"user_token": "sk-secret-123", "safe_key": "visible"},
        )
        print(f"Response:\n{result.text}")


if __name__ == "__main__":
    asyncio.run(main())
