"""Client example — request data in different output formats.

The A2AClient does not yet expose acceptedOutputModes, so this example
uses httpx directly to show the raw HTTP requests.

Uses A2A v1.0 wire: bare ``/message:send`` path, flat ``Part`` shape,
uppercase ``ROLE_USER`` role, ``SendMessageResponse`` oneof wrapper.

Start the output negotiation server first::

    uvicorn examples.output_negotiation.server:app

Then run this client::

    python -m examples.output_negotiation.client
"""

import asyncio
import uuid

import httpx


def _make_body(text: str, output_modes: list[str]) -> dict:
    return {
        "message": {
            "role": "ROLE_USER",
            "messageId": str(uuid.uuid4()),
            "parts": [{"text": text}],
        },
        "configuration": {
            "returnImmediately": False,
            "acceptedOutputModes": output_modes,
        },
    }


async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        card = (await client.get("/.well-known/agent-card.json")).json()
        print(f"Connected to: {card['name']}\n")

        for mode in ["application/json", "text/csv", "text/plain"]:
            resp = await client.post(
                "/message:send",
                json=_make_body("report", [mode]),
            )
            body = resp.json()
            # v1.0 SendMessageResponse oneof: {"task": ...} or {"message": ...}.
            task = body.get("task", body)
            parts = task.get("artifacts", [{}])[0].get("parts", [])
            text = parts[0].get("text", parts[0].get("data", "")) if parts else "(empty)"
            print(f"[{mode}]\n  {text}\n")


if __name__ == "__main__":
    asyncio.run(main())
