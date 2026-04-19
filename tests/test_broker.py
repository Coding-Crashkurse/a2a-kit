"""Unit tests for InMemoryBroker enqueue/dequeue and nack/requeue."""

from __future__ import annotations

from a2a_pydantic.v10 import Message, Part, Role, SendMessageRequest


def _params(text: str = "hello") -> SendMessageRequest:
    """Create minimal SendMessageRequest."""
    msg = Message(
        role=Role.role_user,
        parts=[Part(text=text)],
        message_id="msg1",
    )
    return SendMessageRequest(message=msg)


async def test_enqueue_dequeue(broker):
    """Enqueuing a task and receiving it yields the correct operation."""
    await broker.run_task(_params("ping"))

    async for handle in broker.receive_task_operations():
        assert handle.operation.operation == "run"
        assert handle.operation.params.message.parts[0].text == "ping"
        assert handle.attempt == 1
        await handle.ack()
        break  # only consume one


async def test_nack_requeue(broker):
    """Nacking an operation re-enqueues it with attempt incremented."""
    await broker.run_task(_params("retry-me"))

    attempts_seen: list[int] = []
    async for handle in broker.receive_task_operations():
        attempts_seen.append(handle.attempt)
        if handle.attempt < 2:
            await handle.nack()
        else:
            await handle.ack()
            break

    assert attempts_seen == [1, 2]
