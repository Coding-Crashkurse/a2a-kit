"""Push notification example — long-running task with webhook delivery.

Run:
    uvicorn examples.push_notification:app

Send a request with push config:
    curl -X POST http://localhost:8000/v1/message:send \
      -H 'Content-Type: application/json' \
      -d '{
        "message": {
          "role": "user",
          "messageId": "1",
          "parts": [{"kind": "text", "text": "generate report"}]
        },
        "configuration": {
          "blocking": false
        }
      }'

Then set up a push config:
    curl -X POST http://localhost:8000/v1/tasks/{task_id}/pushNotificationConfig:set \
      -H 'Content-Type: application/json' \
      -d '{"url": "http://localhost:9000/webhook", "token": "my-secret-token"}'
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
    push_allow_http=True,  # Allow HTTP for local dev
)
app = server.as_fastapi_app(debug=True)
