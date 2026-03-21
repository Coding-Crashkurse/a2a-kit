# Push Notification Examples

Three examples demonstrating push notification support: a server with webhook delivery, a webhook receiver, and a client that registers push configs.

## Server with Push Notifications

A long-running task that sends status updates via webhooks.

```python
import asyncio

from a2akit import A2AServer, AgentCardConfig, CapabilitiesConfig, TaskContext, Worker


class ReportWorker(Worker):
    async def handle(self, ctx: TaskContext) -> None:
        await ctx.send_status("Gathering data...")
        await asyncio.sleep(2)
        await ctx.send_status("Generating report...")
        await asyncio.sleep(2)
        await ctx.complete("Report: Q1 revenue was 4.2M, up 15% YoY.")


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
```

### Run it

```bash
uvicorn examples.push.server:app
```

## Webhook Receiver

A simple FastAPI app that listens for push notifications.

```python
from datetime import datetime

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Push Notification Receiver")
notifications = []


@app.post("/webhook")
async def receive(
    request: Request,
    x_a2a_notification_token: str | None = Header(None),
):
    body = await request.json()

    if x_a2a_notification_token != "my-secret-token":
        return JSONResponse(status_code=401, content={"error": "Invalid token"})

    task_id = body.get("id", "unknown")
    state = body.get("status", {}).get("state", "unknown")
    print(f"[WEBHOOK] Task: {task_id}  State: {state}")

    notifications.append(body)
    return JSONResponse(content={"status": "received"})


@app.get("/notifications")
async def list_notifications():
    return {"count": len(notifications), "notifications": notifications}
```

### Run it

```bash
uvicorn examples.push.webhook_receiver:app --port 9000
```

## Client with Push Config

Send a task and register a webhook for updates.

```python
import asyncio

from a2akit import A2AClient


async def main():
    async with A2AClient("http://localhost:8000") as client:
        print(f"Connected to: {client.agent_name}")

        result = await client.send(
            "Generate the Q1 report",
            blocking=False,
            push_url="http://localhost:9000/webhook",
            push_token="my-secret-token",
        )
        print(f"Task created: {result.task_id}")

        for _ in range(30):
            task = await client.get_task(result.task_id)
            print(f"  Polling... state={task.state}")
            if task.is_terminal:
                print(f"  Result: {task.text}")
                break
            await asyncio.sleep(1)

        print("\nCheck the webhook receiver for push notifications!")


if __name__ == "__main__":
    asyncio.run(main())
```

### Run it

```bash
# Terminal 1: start the server
uvicorn examples.push.server:app

# Terminal 2: start the webhook receiver
uvicorn examples.push.webhook_receiver:app --port 9000

# Terminal 3: run the client
python -m examples.push.client
```

The webhook receiver will print task state transitions as they happen.
