"""Client example — high-level streaming with stream_text().

Start the streaming server first:
    uvicorn examples.streaming:app

Then run this client:
    python -m examples.client_streaming
"""

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
