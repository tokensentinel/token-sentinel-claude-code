"""Rehydrate failures must surface DEGRADED (not silent empty history)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from token_sentinel import CallRecord
from token_sentinel_adapter.types import AdapterEvent, DecisionAction, RuntimeStatus

from tokensentinel_claude_code.config import PluginConfig
from tokensentinel_claude_code.host_decision import to_claude_stdout
from tokensentinel_claude_code.runtime import (
    _RehydratingEngine,
    get_engine,
    reset_engine_cache,
)


def test_rehydrate_failure_sets_degraded_and_message(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    reset_engine_cache()

    cfg = PluginConfig(mode="observe", project="test")
    engine = get_engine(cfg)
    assert isinstance(engine, _RehydratingEngine)

    # Force list_calls to throw (corrupt store / schema drift simulation).
    engine._inner.store.list_calls = MagicMock(side_effect=RuntimeError("corrupt row"))  # type: ignore[method-assign]

    # Tracer empty so rehydrate path runs.
    event = AdapterEvent(
        host="claude-code",
        host_event="PostToolUse",
        host_session_id="s-degrade",
        agent_id="main",
        tool_name="Read",
        tool_input={"path": "a.py"},
        timestamp=datetime.now(timezone.utc),
    )
    result = engine.handle(event)

    assert result.decision.status == RuntimeStatus.DEGRADED
    assert "rehydrate failed" in result.decision.reason
    assert result.decision.action == DecisionAction.ANNOTATE

    out = to_claude_stdout(result.decision, host_event="PostToolUse")
    assert out is not None
    assert "systemMessage" in out
    assert "rehydrate failed" in out["systemMessage"]


def test_rehydrate_success_stays_healthy(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    reset_engine_cache()

    cfg = PluginConfig(mode="observe", project="test")
    engine = get_engine(cfg)

    # Seed store with one prior call for the stream.
    prior = CallRecord(
        session_id="s-ok::main",
        timestamp=datetime.now(timezone.utc),
        provider="claude-code",
        model="m",
        method="tool.Read",
        prompt_tokens=0,
        completion_tokens=0,
        latency_ms=1.0,
        request_hash="h1",
        tool_calls=[{"name": "Read", "input": {"path": "a.py"}}],
    )
    engine._inner.store.append(prior)

    event = AdapterEvent(
        host="claude-code",
        host_event="PostToolUse",
        host_session_id="s-ok",
        agent_id="main",
        tool_name="Read",
        tool_input={"path": "a.py"},
        timestamp=datetime.now(timezone.utc),
    )
    result = engine.handle(event)
    assert result.decision.status == RuntimeStatus.HEALTHY
    assert "rehydrate failed" not in (result.decision.reason or "")
