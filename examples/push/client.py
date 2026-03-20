"""Client example — send a task with push notification config.

Start server + webhook receiver first:
    uvicorn examples.push.server:app
    uvicorn examples.push.webhook_receiver:app --port 9000

Then:
    python -m examples.push.client
"""

import asyncio

from a2akit import A2AClient


async def main():
    async with A2AClient("http://localhost:8000") as client:
        print(f"Connected to: {client.agent_name}")
        print(f"Push notifications: {client.capabilities.push_notifications}")

        result = await client.send(
            "Generate the Q1 report",
            blocking=False,
            push_url="http://localhost:9000/webhook",
            push_token="my-secret-token",
        )
        print(f"Task created: {result.task_id} (state: {result.state})")

        for _ in range(30):
            task = await client.get_task(result.task_id)
            print(f"  Polling... state={task.state}")
            if task.is_terminal:
                print(f"  Result: {task.text}")
                break
            await asyncio.sleep(1)

        configs = await client.list_push_configs(result.task_id)
        print(f"\nPush configs: {len(configs)}")

        print("\nCheck the webhook receiver for push notifications!")


if __name__ == "__main__":
    asyncio.run(main())
