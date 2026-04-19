"""Internal v1.0 invariants — not wire-level.

Targets section 14 of the migration spec. These are in-memory tests that
exercise the v10 path through storage, TaskManager, and the v03→v10 adapter
without going through HTTP so they can't hang on streaming semantics.
"""

from __future__ import annotations

import pytest
from a2a_pydantic import convert_to_v10, v03, v10

from a2akit._protocol import ProtocolVersion, resolve_protocol_version
from a2akit.schema import TerminalMarker
from a2akit.storage.base import META_TENANT_KEY, ListTasksQuery
from a2akit.storage.memory import InMemoryStorage


class TestProtocolVersion:
    def test_single_version(self) -> None:
        assert resolve_protocol_version("1.0") == ProtocolVersion.V1_0
        assert resolve_protocol_version("0.3") == ProtocolVersion.V0_3

    def test_none_defaults_to_v10(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # conftest sets A2AKIT_DEFAULT_PROTOCOL_VERSION=0.3 for legacy tests;
        # clear it here to test the real framework default.
        monkeypatch.delenv("A2AKIT_DEFAULT_PROTOCOL_VERSION", raising=False)
        assert resolve_protocol_version(None) == ProtocolVersion.V1_0

    def test_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            resolve_protocol_version("2.0")

    def test_set_form_rejected(self) -> None:
        # Dual-mode serving was removed — each server is single-version.
        with pytest.raises(ValueError, match="dual protocol"):
            resolve_protocol_version({"1.0", "0.3"})
        with pytest.raises(ValueError, match="dual protocol"):
            resolve_protocol_version(["1.0"])


class TestV03ToV10Converter:
    def test_role_mapping(self) -> None:
        assert convert_to_v10(v03.Role.user) == v10.Role.role_user
        assert convert_to_v10(v03.Role.agent) == v10.Role.role_agent

    def test_task_state_mapping(self) -> None:
        assert convert_to_v10(v03.TaskState.submitted) == v10.TaskState.task_state_submitted
        assert convert_to_v10(v03.TaskState.completed) == v10.TaskState.task_state_completed
        # ``unknown`` is dropped in v1.0 — spec says map to submitted.
        assert convert_to_v10(v03.TaskState.unknown) == v10.TaskState.task_state_submitted

    def test_text_part(self) -> None:
        p03 = v03.Part(v03.TextPart(text="hello"))
        p10 = convert_to_v10(p03)
        assert p10.text == "hello"

    def test_file_bytes_part(self) -> None:
        p03 = v03.Part(
            v03.FilePart(file=v03.FileWithBytes(bytes="aGVsbG8=", mime_type="text/plain"))
        )
        p10 = convert_to_v10(p03)
        assert p10.raw == "aGVsbG8="
        assert p10.media_type == "text/plain"

    def test_file_uri_part(self) -> None:
        p03 = v03.Part(v03.FilePart(file=v03.FileWithUri(uri="https://x/y", name="y.txt")))
        p10 = convert_to_v10(p03)
        assert p10.url == "https://x/y"
        assert p10.filename == "y.txt"

    def test_data_part(self) -> None:
        p03 = v03.Part(v03.DataPart(data={"k": "v"}))
        p10 = convert_to_v10(p03)
        assert p10.data is not None
        assert p10.data.root == {"k": "v"}

    def test_blocking_inversion(self) -> None:
        # v0.3 blocking=True means "wait" → v1.0 return_immediately=False.
        params_v03 = v03.MessageSendParams(
            message=v03.Message(
                role=v03.Role.user,
                parts=[v03.Part(v03.TextPart(text="x"))],
                message_id="m1",
            ),
            configuration=v03.MessageSendConfiguration(blocking=True),
        )
        req = convert_to_v10(params_v03)
        assert req.configuration is not None
        assert req.configuration.return_immediately is False

    def test_tenant_hint_populated(self) -> None:
        params_v03 = v03.MessageSendParams(
            message=v03.Message(
                role=v03.Role.user,
                parts=[v03.Part(v03.TextPart(text="x"))],
                message_id="m1",
            ),
        )
        req = convert_to_v10(params_v03, tenant="acme")
        assert req.tenant == "acme"


class TestStructMetadataAPI:
    """Verify a2a-pydantic ≥0.0.9 Struct dict-API contract.

    The framework relied on a ``meta_as_dict`` helper across ~15 call sites
    until the library shipped ``.get()`` / ``__iter__`` / ``**-spread``. Once
    those landed, the helper could be deleted. These tests guard the contract
    so a regression in a2a-pydantic gets caught here, not across the app.
    """

    def test_struct_has_mapping_api(self) -> None:
        s = v10.Struct.model_validate({"a": 1, "b": "x"})
        assert s.get("a") == 1
        assert s.get("missing", "default") == "default"
        assert "a" in s
        assert "missing" not in s
        assert {**s} == {"a": 1, "b": "x"}
        assert dict(s) == {"a": 1, "b": "x"}

    def test_dict_assignment_coerced_to_struct(self) -> None:
        """Dict assignment re-validates back to Struct so convert_to_v03 stays sound."""
        t = v10.Task(
            id="1",
            context_id="c",
            status=v10.TaskStatus(
                state=v10.TaskState.task_state_submitted,
                timestamp="2026-04-18T00:00:00Z",
            ),
            history=[],
            artifacts=[],
            metadata={"initial": True},
        )
        t.metadata = {"a": 1, "b": "x"}
        assert type(t.metadata).__name__ == "Struct"
        assert dict(t.metadata) == {"a": 1, "b": "x"}


class TestInMemoryStorageV10:
    async def test_create_and_load(self) -> None:
        storage = InMemoryStorage()
        msg = v10.Message(
            role=v10.Role.role_user,
            parts=[v10.Part(text="hello")],
            message_id="m-1",
        )
        task = await storage.create_task("ctx-1", msg)
        assert task.status.state == v10.TaskState.task_state_submitted
        assert task.history is not None
        assert len(task.history) == 1

        # _a2akit_just_created marker should be present on the returned object.
        md = dict(task.metadata or {})
        assert md.get("_a2akit_just_created") is True

        # Load back — marker should NOT persist in storage.
        loaded = await storage.load_task(task.id)
        assert loaded is not None
        loaded_md = dict(loaded.metadata or {})
        assert "_a2akit_just_created" not in loaded_md

    async def test_tenant_filter(self) -> None:
        storage = InMemoryStorage()
        msg = v10.Message(
            role=v10.Role.role_user,
            parts=[v10.Part(text="x")],
            message_id="m-1",
        )
        t1 = await storage.create_task("ctx-1", msg)
        # Stash a tenant on t1, different tenant on a new task.
        t1.metadata = {**(t1.metadata or {}), META_TENANT_KEY: "acme"}
        storage.tasks[t1.id] = t1

        msg2 = v10.Message(
            role=v10.Role.role_user,
            parts=[v10.Part(text="y")],
            message_id="m-2",
        )
        t2 = await storage.create_task("ctx-2", msg2)
        t2.metadata = {**(t2.metadata or {}), META_TENANT_KEY: "globex"}
        storage.tasks[t2.id] = t2

        result = await storage.list_tasks(ListTasksQuery(tenant="acme"))
        assert len(result.tasks) == 1
        assert result.tasks[0].id == t1.id

        result_all = await storage.list_tasks(ListTasksQuery())
        assert len(result_all.tasks) == 2


class TestTerminalMarker:
    def test_wraps_status_event(self) -> None:
        evt = v10.TaskStatusUpdateEvent(
            task_id="t-1",
            context_id="c-1",
            status=v10.TaskStatus(
                state=v10.TaskState.task_state_completed,
                timestamp="2026-04-18T00:00:00Z",
            ),
        )
        marker = TerminalMarker(event=evt)
        # Marker is frozen — event attribute is the unwrapped status event.
        assert marker.event is evt
        # It's distinguishable from the inner event at runtime so the SSE
        # layer can branch on it.
        assert isinstance(marker, TerminalMarker)
        assert not isinstance(evt, TerminalMarker)
