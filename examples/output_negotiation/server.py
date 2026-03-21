"""Output negotiation — adapt response format to client preferences.

Uses ctx.accepts() to check which MIME types the client can handle
and returns data in the preferred format.

Run:
    uvicorn examples.output_negotiation.server:app --reload
"""

from a2akit import A2AServer, AgentCardConfig, TaskContext, Worker


class SalesReportWorker(Worker):
    """Returns sales data in the format the client prefers."""

    async def handle(self, ctx: TaskContext) -> None:
        data = {"revenue": 42000, "currency": "EUR", "quarter": "Q1"}

        if ctx.accepts("application/json"):
            await ctx.complete_json(data)
        elif ctx.accepts("text/csv"):
            csv = "revenue,currency,quarter\n42000,EUR,Q1"
            await ctx.complete(csv)
        else:
            await ctx.complete("Revenue: 42,000 EUR (Q1)")


server = A2AServer(
    worker=SalesReportWorker(),
    agent_card=AgentCardConfig(
        name="Sales Report",
        description="Returns sales data in JSON, CSV, or plain text.",
        version="0.1.0",
        protocol="http+json",
    ),
)
app = server.as_fastapi_app(debug=True)
