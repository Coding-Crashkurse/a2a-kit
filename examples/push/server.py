"""Push notification example — long-running task with webhook delivery.

Run:
    uvicorn examples.push.server:app
"""

import asyncio

from a2akit import A2AServer, AgentCardConfig, CapabilitiesConfig, TaskContext, Worker


class ReportWorker(Worker):
    """Simulates a long-running report generation."""

    async def handle(self, ctx: TaskContext) -> None:
        await ctx.send_status("Gathering data...")
        await asyncio.sleep(2)
        await ctx.send_status("Generating report...")
        await asyncio.sleep(2)
        await ctx.complete("Report: Q1 revenue was €4.2M, up 15% YoY.")


server = A2AServer(
    worker=ReportWorker(),
    agent_card=AgentCardConfig(
        name="Report Generator",
        description="Generates reports with push notification support.",
        version="0.1.0",
        protocol="http+json",
        capabilities=CapabilitiesConfig(
            streaming=True,
            push_notifications=True,
        ),
    ),
    push_allow_http=True,
)
app = server.as_fastapi_app(debug=True)
