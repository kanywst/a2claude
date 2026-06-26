"""Executor lifecycle: eviction and session-continuity bookkeeping."""

from __future__ import annotations

from a2claude import executor as executor_mod
from a2claude.backends import BackendSession, RunRequest, make_backend
from a2claude.executor import ClaudeCodeExecutor


def test_remember_session_moves_reused_context_to_most_recent():
    executor = ClaudeCodeExecutor(make_backend("echo"))
    executor._remember_session("a", "sess-a")
    executor._remember_session("b", "sess-b")
    executor._remember_session("c", "sess-c")

    # Reusing "a" must move it off the eviction front; "b" becomes oldest.
    executor._remember_session("a", "sess-a2")
    assert next(iter(executor._session_ids)) == "b"
    assert executor._session_ids["a"] == "sess-a2"


def test_remember_session_evicts_least_recently_used(monkeypatch):
    monkeypatch.setattr(executor_mod, "_MAX_CONTEXTS", 2)
    executor = ClaudeCodeExecutor(make_backend("echo"))

    executor._remember_session("a", "sess-a")
    executor._remember_session("b", "sess-b")
    # Touch "a" so "b" is now the least recently used, then overflow.
    executor._remember_session("a", "sess-a2")
    executor._remember_session("c", "sess-c")

    assert "b" not in executor._session_ids
    assert set(executor._session_ids) == {"a", "c"}


async def _parked_session() -> BackendSession:
    """An echo session driven up to its permission request and left parked."""
    session = BackendSession()
    session.start(
        lambda s: make_backend("echo").drive(s, RunRequest(prompt="sudo reboot"))
    )
    async for _ in session.drain():
        pass
    assert session.is_parked
    return session


def _running_session() -> BackendSession:
    """A session that is neither parked nor drained (not awaiting input)."""
    session = BackendSession()
    session.start(lambda s: make_backend("echo").drive(s, RunRequest(prompt="hello")))
    assert not session.is_parked
    return session


async def test_eviction_prefers_parked_over_running(monkeypatch):
    monkeypatch.setattr(executor_mod, "_MAX_LIVE", 2)
    executor = ClaudeCodeExecutor(make_backend("echo"))

    running = _running_session()
    parked = await _parked_session()
    # Insert running first so the oldest-by-insertion entry is the running one;
    # a naive "evict oldest" would drop it. The parked one must go instead.
    executor._live["running"] = running
    executor._live["parked"] = parked

    try:
        await executor._evict_if_full()
        assert "parked" not in executor._live
        assert "running" in executor._live
    finally:
        await running.close()


async def test_eviction_falls_back_to_oldest_when_none_parked(monkeypatch):
    monkeypatch.setattr(executor_mod, "_MAX_LIVE", 2)
    executor = ClaudeCodeExecutor(make_backend("echo"))

    first = _running_session()
    second = _running_session()
    executor._live["first"] = first
    executor._live["second"] = second

    try:
        await executor._evict_if_full()
        assert "first" not in executor._live
        assert "second" in executor._live
    finally:
        await second.close()
