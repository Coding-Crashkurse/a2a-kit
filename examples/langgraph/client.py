"""Client example — stream results from the LangGraph file processor.

Start the LangGraph server first:
    uvicorn examples.langgraph.server:app

Then run this client:
    python -m examples.langgraph.client
"""

import asyncio

from a2akit import A2AClient


async def main():
    async with A2AClient("http://localhost:8000") as client:
        print(f"Connected to: {client.agent_name}\n")

        async for event in client.stream("Process all files"):
            if event.kind == "status" and event.text:
                print(f"[status] {event.text}")
            elif event.kind == "artifact" and event.text:
                print(event.text, end="")

            if event.is_final:
                print(f"\nFinal state: {event.state}")

        print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
