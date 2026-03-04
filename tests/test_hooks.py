"""Unit tests for LifecycleHooks and HookableEmitter."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from a2a.types import Message, Part, Role, TaskState, TextPart

from a2akit.hooks import HookableEmitter, LifecycleHooks


def _make_message(text: str = "test") -> Message:
    """Create a minimal Message for testing."""
    return Message(
        role=Role.agent,
        parts=[Part(TextPart(text=text))],
        message_id="msg-1",
        task_id="task-1",
        context_id="ctx-1",
    )


@pytest.fixture
def inner() -> AsyncMock:
    """Mock inner EventEmitter."""
    mock = AsyncMock()
    mock.update_task.return_value = 2
    mock.send_event.return_value = None
    return mock


@pytest.fixture
def hook() -> AsyncMock:
    """Mock on_terminal hook callable."""
    return AsyncMock()


@pytest.fixture
def hooks(hook: AsyncMock) -> LifecycleHooks:
    """LifecycleHooks with a mock on_terminal."""
    return LifecycleHooks(on_terminal=hook)


@pytest.fixture
def emitter(inner: AsyncMock, hooks: LifecycleHooks) -> HookableEmitter:
    """HookableEmitter wrapping a mock inner emitter."""
    return HookableEmitter(inner, hooks)


class TestLifecycleHooksDefaults:
    """Test LifecycleHooks dataclass defaults."""

    async def test_lifecycle_hooks_defaults_all_none(self) -> None:
        """LifecycleHooks() has all fields None."""
        h = LifecycleHooks()
        assert h.on_state_change is None
        assert h.on_working is None
        assert h.on_turn_end is None
        assert h.on_terminal is None


@pytest.mark.parametrize(
    "terminal_state",
    [
        TaskState.completed,
        TaskState.failed,
        TaskState.canceled,
        TaskState.rejected,
    ],
)
class TestHookableEmitterTerminalStates:
    """Hook fires for each terminal state."""

    async def test_hookable_emitter_fires_on_terminal(
        self,
        terminal_state: TaskState,
        emitter: HookableEmitter,
        inner: AsyncMock,
        hook: AsyncMock,
    ) -> None:
        """on_terminal fires after successful write for terminal state."""
        msg = _make_message()
        result = await emitter.update_task("task-1", state=terminal_state, status_message=msg)

        assert result == 2
        inner.update_task.assert_awaited_once()
        hook.assert_awaited_once_with("task-1", terminal_state, msg)


class TestHookableEmitterWorking:
    """on_working fires for working state."""

    async def test_hookable_emitter_fires_on_working(self, inner: AsyncMock) -> None:
        """on_working fires when state=working."""
        hook = AsyncMock()
        em = HookableEmitter(inner, LifecycleHooks(on_working=hook))

        await em.update_task("task-1", state=TaskState.working)

        hook.assert_awaited_once_with("task-1")

    async def test_hookable_emitter_on_working_not_for_terminal(self, inner: AsyncMock) -> None:
        """on_working does NOT fire for terminal states."""
        hook = AsyncMock()
        em = HookableEmitter(inner, LifecycleHooks(on_working=hook))

        await em.update_task("task-1", state=TaskState.completed)

        hook.assert_not_awaited()


@pytest.mark.parametrize(
    "turn_end_state",
    [TaskState.input_required, TaskState.auth_required],
)
class TestHookableEmitterTurnEnd:
    """on_turn_end fires for input_required and auth_required."""

    async def test_hookable_emitter_fires_on_turn_end(
        self, turn_end_state: TaskState, inner: AsyncMock
    ) -> None:
        """on_turn_end fires for turn-end states."""
        hook = AsyncMock()
        msg = _make_message()
        em = HookableEmitter(inner, LifecycleHooks(on_turn_end=hook))

        await em.update_task("task-1", state=turn_end_state, status_message=msg)

        hook.assert_awaited_once_with("task-1", turn_end_state, msg)


class TestHookableEmitterStateChange:
    """on_state_change fires for every non-None state."""

    @pytest.mark.parametrize(
        "state",
        [
            TaskState.working,
            TaskState.completed,
            TaskState.failed,
            TaskState.canceled,
            TaskState.rejected,
            TaskState.input_required,
            TaskState.auth_required,
            TaskState.submitted,
        ],
    )
    async def test_hookable_emitter_fires_on_state_change_for_all(
        self, state: TaskState, inner: AsyncMock
    ) -> None:
        """on_state_change fires for every non-None state transition."""
        hook = AsyncMock()
        msg = _make_message()
        em = HookableEmitter(inner, LifecycleHooks(on_state_change=hook))

        await em.update_task("task-1", state=state, status_message=msg)

        hook.assert_awaited_once_with("task-1", state, msg)

    async def test_hookable_emitter_state_change_and_terminal_both_fire(
        self, inner: AsyncMock
    ) -> None:
        """Both on_state_change and on_terminal fire for terminal states."""
        sc_hook = AsyncMock()
        t_hook = AsyncMock()
        em = HookableEmitter(inner, LifecycleHooks(on_state_change=sc_hook, on_terminal=t_hook))

        msg = _make_message()
        await em.update_task("task-1", state=TaskState.completed, status_message=msg)

        sc_hook.assert_awaited_once_with("task-1", TaskState.completed, msg)
        t_hook.assert_awaited_once_with("task-1", TaskState.completed, msg)

    async def test_hookable_emitter_state_change_and_working_both_fire(
        self, inner: AsyncMock
    ) -> None:
        """Both on_state_change and on_working fire for working state."""
        sc_hook = AsyncMock()
        w_hook = AsyncMock()
        em = HookableEmitter(inner, LifecycleHooks(on_state_change=sc_hook, on_working=w_hook))

        await em.update_task("task-1", state=TaskState.working)

        sc_hook.assert_awaited_once_with("task-1", TaskState.working, None)
        w_hook.assert_awaited_once_with("task-1")


class TestHookableEmitterNoFire:
    """Cases where hooks must NOT fire."""

    async def test_hookable_emitter_no_fire_on_none_state(
        self, emitter: HookableEmitter, hook: AsyncMock
    ) -> None:
        """No hooks fire when state is None (artifact-only writes)."""
        await emitter.update_task("task-1")
        hook.assert_not_awaited()

    async def test_hookable_emitter_no_fire_on_none_state_all_hooks(
        self, inner: AsyncMock
    ) -> None:
        """No hooks fire when state is None, even with all hooks set."""
        all_hooks = LifecycleHooks(
            on_state_change=AsyncMock(),
            on_working=AsyncMock(),
            on_turn_end=AsyncMock(),
            on_terminal=AsyncMock(),
        )
        em = HookableEmitter(inner, all_hooks)

        await em.update_task("task-1")

        all_hooks.on_state_change.assert_not_awaited()
        all_hooks.on_working.assert_not_awaited()
        all_hooks.on_turn_end.assert_not_awaited()
        all_hooks.on_terminal.assert_not_awaited()


class TestHookableEmitterErrorHandling:
    """Error handling behavior."""

    async def test_hookable_emitter_no_fire_on_storage_error(
        self, inner: AsyncMock, hooks: LifecycleHooks, hook: AsyncMock
    ) -> None:
        """Hook does NOT fire when inner update_task raises."""
        inner.update_task.side_effect = RuntimeError("storage boom")
        em = HookableEmitter(inner, hooks)

        with pytest.raises(RuntimeError, match="storage boom"):
            await em.update_task("task-1", state=TaskState.completed)

        hook.assert_not_awaited()

    async def test_hookable_emitter_hook_error_swallowed(
        self, inner: AsyncMock, hook: AsyncMock
    ) -> None:
        """Hook exception is logged, update_task still returns normally."""
        hook.side_effect = ValueError("hook boom")
        em = HookableEmitter(inner, LifecycleHooks(on_terminal=hook))

        result = await em.update_task("task-1", state=TaskState.completed)

        assert result == 2
        hook.assert_awaited_once()

    async def test_hookable_emitter_hook_error_does_not_affect_return(
        self, inner: AsyncMock, hook: AsyncMock
    ) -> None:
        """Return value is from inner emitter, not from hook."""
        hook.side_effect = RuntimeError("kaboom")
        inner.update_task.return_value = 42
        em = HookableEmitter(inner, LifecycleHooks(on_terminal=hook))

        result = await em.update_task("task-1", state=TaskState.failed)

        assert result == 42


class TestHookableEmitterPassthrough:
    """Passthrough behavior when hooks are None."""

    async def test_hookable_emitter_no_hooks_passthrough(self, inner: AsyncMock) -> None:
        """With hooks=None, behaves identically to inner emitter."""
        em = HookableEmitter(inner, hooks=None)
        result = await em.update_task("task-1", state=TaskState.completed)

        assert result == 2
        inner.update_task.assert_awaited_once()

    async def test_hookable_emitter_send_event_delegates(self, inner: AsyncMock) -> None:
        """send_event passes through unchanged."""
        em = HookableEmitter(inner)
        event = {"kind": "status-update"}
        await em.send_event("task-1", event)

        inner.send_event.assert_awaited_once_with("task-1", event)


class TestHookableEmitterArguments:
    """Hook receives correct arguments."""

    async def test_hookable_emitter_receives_status_message(
        self, emitter: HookableEmitter, hook: AsyncMock
    ) -> None:
        """Hook receives the status_message argument."""
        msg = _make_message("done")
        await emitter.update_task("task-1", state=TaskState.completed, status_message=msg)

        hook.assert_awaited_once_with("task-1", TaskState.completed, msg)

    async def test_hookable_emitter_receives_none_status_message(
        self, emitter: HookableEmitter, hook: AsyncMock
    ) -> None:
        """Hook receives None when no status_message is provided."""
        await emitter.update_task("task-1", state=TaskState.completed)

        hook.assert_awaited_once_with("task-1", TaskState.completed, None)


class TestHookDispatchOrder:
    """on_state_change fires before specific hooks."""

    async def test_hook_dispatch_order_terminal(self, inner: AsyncMock) -> None:
        """on_state_change fires before on_terminal."""
        order: list[str] = []

        async def sc_hook(*_args: object) -> None:
            order.append("state_change")

        async def t_hook(*_args: object) -> None:
            order.append("terminal")

        em = HookableEmitter(inner, LifecycleHooks(on_state_change=sc_hook, on_terminal=t_hook))

        await em.update_task("task-1", state=TaskState.completed)

        assert order == ["state_change", "terminal"]

    async def test_hook_dispatch_order_working(self, inner: AsyncMock) -> None:
        """on_state_change fires before on_working."""
        order: list[str] = []

        async def sc_hook(*_args: object) -> None:
            order.append("state_change")

        async def w_hook(*_args: object) -> None:
            order.append("working")

        em = HookableEmitter(inner, LifecycleHooks(on_state_change=sc_hook, on_working=w_hook))

        await em.update_task("task-1", state=TaskState.working)

        assert order == ["state_change", "working"]

    async def test_hook_dispatch_order_turn_end(self, inner: AsyncMock) -> None:
        """on_state_change fires before on_turn_end."""
        order: list[str] = []

        async def sc_hook(*_args: object) -> None:
            order.append("state_change")

        async def te_hook(*_args: object) -> None:
            order.append("turn_end")

        em = HookableEmitter(inner, LifecycleHooks(on_state_change=sc_hook, on_turn_end=te_hook))

        await em.update_task("task-1", state=TaskState.input_required)

        assert order == ["state_change", "turn_end"]
