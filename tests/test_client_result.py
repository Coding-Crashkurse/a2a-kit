"""Tests for ClientResult, StreamEvent, ArtifactInfo, ListResult."""

from __future__ import annotations

from a2a_pydantic.v03 import (
    Artifact,
    DataPart,
    Message,
    Part,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

from a2akit.client.result import ArtifactInfo, ClientResult, ListResult, StreamEvent


def _task(
    state: TaskState = TaskState.completed,
    artifacts: list[Artifact] | None = None,
    status_message: Message | None = None,
) -> Task:
    status = TaskStatus(state=state, message=status_message)
    return Task(
        id="task-1",
        context_id="ctx-1",
        status=status,
        artifacts=artifacts,
    )


def _text_artifact(text: str = "hello", artifact_id: str = "art-1") -> Artifact:
    return Artifact(
        artifact_id=artifact_id,
        parts=[Part(root=TextPart(text=text))],
    )


def _data_artifact(data: dict | None = None, artifact_id: str = "data-art") -> Artifact:
    return Artifact(
        artifact_id=artifact_id,
        parts=[Part(root=DataPart(data=data or {"key": "value"}))],
    )


class TestClientResult:
    def test_from_completed_task(self):
        task = _task(artifacts=[_text_artifact("Hello world")])
        result = ClientResult.from_task(task)
        assert result.task_id == "task-1"
        assert result.context_id == "ctx-1"
        assert result.state == "completed"
        assert result.text == "Hello world"
        assert result.completed
        assert result.is_terminal
        assert not result.failed

    def test_from_failed_task(self):
        msg = Message(
            role="agent",
            message_id="m1",
            parts=[Part(root=TextPart(text="Something went wrong"))],
        )
        task = _task(state=TaskState.failed, status_message=msg)
        result = ClientResult.from_task(task)
        assert result.failed
        assert result.is_terminal
        assert result.text == "Something went wrong"

    def test_from_direct_reply(self):
        message = Message(
            role="agent",
            message_id="m1",
            parts=[Part(root=TextPart(text="Direct response"))],
        )
        result = ClientResult.from_message(message)
        assert result.text == "Direct response"
        assert result.raw_message is message
        assert result.raw_task is None
        assert result.state == "completed"

    def test_from_task_no_artifacts(self):
        task = _task(state=TaskState.submitted)
        result = ClientResult.from_task(task)
        assert result.text is None
        assert result.data is None
        assert result.artifacts == []

    def test_state_properties(self):
        for state, prop in [
            (TaskState.completed, "completed"),
            (TaskState.failed, "failed"),
            (TaskState.input_required, "input_required"),
            (TaskState.auth_required, "auth_required"),
            (TaskState.canceled, "canceled"),
            (TaskState.rejected, "rejected"),
        ]:
            result = ClientResult.from_task(_task(state=state))
            assert getattr(result, prop), f"{prop} should be True for {state}"

    def test_is_terminal(self):
        terminal = [TaskState.completed, TaskState.failed, TaskState.canceled, TaskState.rejected]
        non_terminal = [TaskState.submitted, TaskState.working, TaskState.input_required]
        for state in terminal:
            assert ClientResult.from_task(_task(state=state)).is_terminal
        for state in non_terminal:
            assert not ClientResult.from_task(_task(state=state)).is_terminal

    def test_data_extraction(self):
        task = _task(artifacts=[_data_artifact({"result": 42})])
        result = ClientResult.from_task(task)
        assert result.data == {"result": 42}

    def test_text_from_status_message_fallback(self):
        msg = Message(
            role="agent",
            message_id="m1",
            parts=[Part(root=TextPart(text="Status text"))],
        )
        task = _task(state=TaskState.working, status_message=msg)
        result = ClientResult.from_task(task)
        assert result.text == "Status text"


class TestArtifactInfo:
    def test_from_artifact(self):
        artifact = Artifact(
            artifact_id="art-1",
            name="My Artifact",
            description="A test artifact",
            parts=[Part(root=TextPart(text="content"))],
            metadata={"foo": "bar"},
        )
        info = ArtifactInfo.from_artifact(artifact)
        assert info.artifact_id == "art-1"
        assert info.name == "My Artifact"
        assert info.description == "A test artifact"
        assert info.text == "content"
        assert info.metadata == {"foo": "bar"}

    def test_data_artifact(self):
        artifact = Artifact(
            artifact_id="d1",
            parts=[Part(root=DataPart(data={"x": 1}))],
        )
        info = ArtifactInfo.from_artifact(artifact)
        assert info.data == {"x": 1}
        assert info.text is None


class TestStreamEvent:
    def test_from_task(self):
        task = _task(state=TaskState.completed, artifacts=[_text_artifact("done")])
        event = StreamEvent.from_raw(task)
        assert event.kind == "task"
        assert event.state == "completed"
        assert event.text == "done"
        assert event.is_final

    def test_from_status_update(self):
        status = TaskStatus(
            state=TaskState.working,
            message=Message(
                role="agent",
                message_id="m1",
                parts=[Part(root=TextPart(text="Processing..."))],
            ),
        )
        event_obj = TaskStatusUpdateEvent(
            task_id="t1",
            context_id="c1",
            status=status,
            final=False,
        )
        event = StreamEvent.from_raw(event_obj)
        assert event.kind == "status"
        assert event.state == "working"
        assert event.text == "Processing..."
        assert not event.is_final

    def test_from_status_update_final(self):
        status = TaskStatus(state=TaskState.completed)
        event_obj = TaskStatusUpdateEvent(
            task_id="t1",
            context_id="c1",
            status=status,
            final=True,
        )
        event = StreamEvent.from_raw(event_obj)
        assert event.is_final

    def test_from_artifact_update(self):
        artifact = Artifact(
            artifact_id="art-1",
            parts=[Part(root=TextPart(text="chunk"))],
        )
        event_obj = TaskArtifactUpdateEvent(
            task_id="t1",
            context_id="c1",
            artifact=artifact,
            last_chunk=True,
        )
        event = StreamEvent.from_raw(event_obj)
        assert event.kind == "artifact"
        assert event.artifact_id == "art-1"
        assert event.text == "chunk"
        assert event.is_final


class TestListResult:
    def test_fields(self):
        r = ListResult(
            tasks=[],
            next_page_token="abc",
            total_size=100,
            page_size=50,
        )
        assert r.next_page_token == "abc"
        assert r.total_size == 100
        assert r.page_size == 50
