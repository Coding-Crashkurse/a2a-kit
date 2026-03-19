"""Webhook receiver — listens for push notifications from A2A agents.

Run:
    uvicorn examples.push_webhook_receiver:app --port 9000
"""

from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse

app = FastAPI(title="Push Notification Receiver")
notifications: list[dict] = []


@app.post("/webhook")
async def receive_notification(
    request: Request,
    x_a2a_notification_token: str | None = Header(None),
) -> JSONResponse:
    body = await request.json()

    expected_token = "my-secret-token"
    if x_a2a_notification_token != expected_token:
        print(f"[WEBHOOK] Invalid token: {x_a2a_notification_token}")
        return JSONResponse(status_code=401, content={"error": "Invalid token"})

    task_id = body.get("id", "unknown")
    state = body.get("status", {}).get("state", "unknown")
    artifacts = body.get("artifacts", [])

    print(f"\n[WEBHOOK] {'=' * 50}")
    print(f"[WEBHOOK] {datetime.now().isoformat()}")
    print(f"[WEBHOOK] Task: {task_id}  State: {state}  Artifacts: {len(artifacts)}")
    for i, art in enumerate(artifacts):
        for part in art.get("parts", []):
            if part.get("kind") == "text":
                print(f"[WEBHOOK] Artifact[{i}]: {part['text'][:100]}")
    print(f"[WEBHOOK] {'=' * 50}\n")

    notifications.append(body)
    return JSONResponse(content={"status": "received"})


@app.get("/notifications")
async def list_notifications():
    return {"count": len(notifications), "notifications": notifications}


@app.delete("/notifications")
async def clear_notifications():
    notifications.clear()
    return {"status": "cleared"}
