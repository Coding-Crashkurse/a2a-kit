"""Client example — request data in different output formats.

The A2AClient does not yet expose acceptedOutputModes, so this example
uses httpx directly to show the raw HTTP requests.

Start the output negotiation server first:
    uvicorn examples.output_negotiation.server:app

Then run this client:
    python -m examples.output_negotiation.client
"""

import asyncio
import uuid

import httpx


def _make_body(text: str, output_modes: list[str]) -> dict:
    return {
        "message": {
            "role": "user",
            "messageId": str(uuid.uuid4()),
            "parts": [{"kind": "text", "text": text}],
        },
        "configuration": {
            "blocking": True,
            "acceptedOutputModes": output_modes,
        },
    }


async def main():
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        card = (await client.get("/.well-known/agent-card.json")).json()
        print(f"Connected to: {card['name']}\n")

        for mode in ["application/json", "text/csv", "text/plain"]:
            resp = await client.post(
                "/v1/message:send",
                json=_make_body("report", [mode]),
            )
            data = resp.json()
            parts = data.get("artifacts", [{}])[0].get("parts", [])
            text = parts[0].get("text", parts[0].get("data", "")) if parts else "(empty)"
            print(f"[{mode}]\n  {text}\n")


if __name__ == "__main__":
    asyncio.run(main())
