"""A2A v1.0 HTTP+JSON server — bare paths, flat Parts, uppercase enums.

This example pins the server to v1.0 wire only (``protocol_version="1.0"``)
so the endpoints are mounted at bare paths (``/message:send``, ``/tasks/{id}``)
with v1.0 payload shapes (``role: "ROLE_USER"``, flat ``{text: "..."}`` parts,
``SendMessageResponse`` oneof wrapper, wrapped SSE discriminators).

Run::

    uvicorn examples.v10_http_json.server:app --reload

Then::

    python -m examples.v10_http_json.client
"""

from __future__ import annotations

import asyncio

from a2akit import A2AServer, AgentCardConfig, CapabilitiesConfig, TaskContext, Worker


class GreeterWorker(Worker):
    """Simple worker that greets the caller, streams a short report, and completes.

    Special commands:
        "stream"  — emits a 3-chunk streaming artifact (good for SSE demo)
        "fail"    — demonstrates the google.rpc.Status error envelope
        anything else — completes synchronously with an echo
    """

    async def handle(self, ctx: TaskContext) -> None:
        text = ctx.user_text.strip().lower()

        if text == "fail":
            await ctx.fail("You asked for a failure — here it is.")
            return

        if text == "stream":
            await ctx.send_status("Preparing report...")
            for i, chunk in enumerate(["hello ", "from ", "v1.0"]):
                await ctx.emit_text_artifact(
                    text=chunk,
                    artifact_id="report",
                    append=(i > 0),
                    last_chunk=(i == 2),
                )
                await asyncio.sleep(0.2)
            await ctx.complete()
            return

        await ctx.complete(f"Echo: {ctx.user_text}")


server = A2AServer(
    worker=GreeterWorker(),
    agent_card=AgentCardConfig(
        name="V1.0 Greeter",
        description="Native A2A v1.0 HTTP+JSON demo agent.",
        version="1.0.0",
        protocol="http+json",
        capabilities=CapabilitiesConfig(streaming=True),
    ),
    # Pin to v1.0 wire. Omit this for the framework default (also v1.0), or
    # pass ``{"1.0", "0.3"}`` for dual-mode serving.
    protocol_version="1.0",
)
app = server.as_fastapi_app(debug=True)
