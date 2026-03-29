"""Simple echo worker — returns the user's input back.

Demonstrates: echo, fail, and multi-turn input flow.

Run:
    uvicorn examples.echo.server:app --reload
"""

import asyncio

from a2akit import A2AServer, AgentCardConfig, CapabilitiesConfig, TaskContext, Worker


class EchoWorker(Worker):
    """Echoes the user's message back as-is.

    Special commands:
        "fail"  — triggers a task failure
        "name"  — starts a multi-turn greeting flow via request_input()
    """

    async def handle(self, ctx: TaskContext) -> None:

        if ctx.user_text == "fail":
            await ctx.fail(f"Echo: {ctx.user_text}")
            return

        if ctx.user_text == "name":
            await ctx.request_input("What is your name?")
            return

        if ctx.history and len(ctx.history) > 1:
            await ctx.complete(f"Hello, {ctx.user_text}!")
            return

        await asyncio.sleep(3)
        await ctx.complete(f"Echo: {ctx.user_text}")


server = A2AServer(
    worker=EchoWorker(),
    agent_card=AgentCardConfig(
        name="Echo",
        description="Echoes your input back.",
        version="0.1.0",
        protocol="http+json",
        capabilities=CapabilitiesConfig(state_transition_history=True),
    ),
)
app = server.as_fastapi_app(debug=True)
