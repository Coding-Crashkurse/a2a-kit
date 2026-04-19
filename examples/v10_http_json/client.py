"""A2A v1.0 HTTP+JSON client — raw wire demo + high-level A2AClient.

The first half uses :mod:`httpx` directly so you can see the exact v1.0 wire
payloads (bare paths, flat Parts, SendMessageResponse oneof, wrapped SSE
discriminator, google.rpc.Status error envelope).

The second half shows the same round-trips via :class:`A2AClient`, which
auto-detects the server's v1.0 card from ``supportedInterfaces[]`` and picks
``RestV10Transport`` transparently.

Start the server first::

    uvicorn examples.v10_http_json.server:app

Then::

    python -m examples.v10_http_json.client
"""

from __future__ import annotations

import asyncio
import json
import uuid

import httpx

from a2akit import A2AClient

BASE_URL = "http://localhost:8000"


# -- raw wire --------------------------------------------------------------


def _v10_body(text: str) -> dict:
    """v1.0 SendMessageRequest on the wire.

    Notice what's different from v0.3:
    - ``role`` is uppercase-prefixed ``ROLE_USER``
    - ``parts`` are flat: ``{"text": "..."}`` — no ``kind`` discriminator
    - ``configuration.returnImmediately`` replaces v0.3's ``blocking`` (inverted)
    """
    return {
        "message": {
            "role": "ROLE_USER",
            "messageId": str(uuid.uuid4()),
            "parts": [{"text": text}],
        },
        "configuration": {"returnImmediately": False},
    }


async def demo_raw_wire(http: httpx.AsyncClient) -> None:
    print("=" * 60)
    print("RAW v1.0 WIRE DEMO")
    print("=" * 60)

    # -- discovery: /.well-known/agent-card.json returns a v1.0 AgentCard -----
    card = (await http.get("/.well-known/agent-card.json")).json()
    print(f"\n[card] {card['name']!r} — protocolVersion:")
    for iface in card["supportedInterfaces"]:
        print(f"  {iface['protocolVersion']:<5} {iface['protocolBinding']:<10} {iface['url']}")

    # -- unary: POST /message:send --------------------------------------------
    # Note the BARE path — v1.0 does not use the /v1/ prefix.
    resp = await http.post("/message:send", json=_v10_body("hi v1.0"))
    body = resp.json()
    # SendMessageResponse is a oneof: {"task": {...}} OR {"message": {...}}.
    # Our GreeterWorker runs a task, so we get {"task": ...}.
    task = body["task"]
    print(f"\n[unary]  state={task['status']['state']} id={task['id']}")
    assert task["status"]["state"] == "TASK_STATE_COMPLETED"

    # -- error path: google.rpc.Status envelope --------------------------------
    err_resp = await http.get("/tasks/does-not-exist")
    err = err_resp.json()["error"]
    print(f"\n[error]  HTTP {err_resp.status_code} status={err['status']}")
    print(f"         reason={err['details'][0]['reason']}")

    # -- streaming: POST /message:stream ---------------------------------------
    # v1.0 SSE events use the WRAPPED discriminator:
    #   {"taskStatusUpdate": {...}} / {"taskArtifactUpdate": {...}, "index": N}
    # Stream-close is the terminal signal — no ``final`` flag on the wire.
    print("\n[stream] POST /message:stream (payload='stream')")
    async with http.stream("POST", "/message:stream", json=_v10_body("stream")) as stream:
        async for line in stream.aiter_lines():
            if not line.startswith("data:"):
                continue
            payload = json.loads(line[len("data:") :])
            kind = next(iter(payload)) if isinstance(payload, dict) else "?"
            print(f"  -> {kind:<22} {json.dumps(payload)[:90]}")


# -- high-level client -----------------------------------------------------


async def demo_a2aclient() -> None:
    print("\n" + "=" * 60)
    print("HIGH-LEVEL A2AClient DEMO (auto-detects v1.0)")
    print("=" * 60)

    # A2AClient reads ``supportedInterfaces[]`` off the card and picks
    # ``RestV10Transport`` automatically. You don't pass a version flag.
    async with A2AClient(BASE_URL, verify_signatures="off") as client:
        print(f"\n[card]    agent={client.agent_name!r}")
        print(f"          protocol={client.protocol!r}")

        result = await client.send("hello from the client")
        print(f"\n[send]    state={result.state}")
        print(f"          text={result.text!r}")

        print("\n[stream]  async for chunk in client.stream_text('stream')")
        async for chunk in client.stream_text("stream"):
            print(f"          chunk={chunk!r}")


async def main() -> None:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as http:
        await demo_raw_wire(http)
    await demo_a2aclient()


if __name__ == "__main__":
    asyncio.run(main())
