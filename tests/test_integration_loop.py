"""End-to-end: fixture tools through engine via bridge."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tokensentinel_claude_code.bridge import claude_payload_to_event
from tokensentinel_claude_code.config import PluginConfig
from tokensentinel_claude_code.host_decision import to_claude_stdout
from tokensentinel_claude_code.runtime import get_engine


def test_tool_loop_produces_system_message(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path))
    # Reset module engine cache
    import tokensentinel_claude_code.runtime as rt

    rt._engine = None
    rt._engine_key = None

    cfg = PluginConfig(mode="observe", project="test")
    engine = get_engine(cfg)
    base = datetime.now(timezone.utc)
    saw_loop_hit = False
    saw_host_message = False
    for i in range(4):
        payload = {
            "session_id": "int-sess",
            "tool_name": "Read",
            "tool_input": {"path": "src/app.py", "offset": 0},
            "agent_id": "main",
        }
        ev = claude_payload_to_event(payload, host_event="PostToolUse")
        assert ev is not None
        ev.timestamp = base + timedelta(seconds=i)
        result = engine.handle(ev)
        if any(h.type == "tool_loop" for h in result.decision.hits):
            saw_loop_hit = True
        out = to_claude_stdout(result.decision, host_event="PostToolUse")
        if out and "systemMessage" in out:
            saw_host_message = True

    assert saw_loop_hit, "expected tool_loop hits after repeated Reads"
    # Emit cooldown may silence later turns; at least one host message for the loop.
    assert saw_host_message, "expected at least one systemMessage for the loop"


def test_sibling_agents_isolated(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CLAUDE_PLUGIN_DATA", str(tmp_path / "b"))
    import tokensentinel_claude_code.runtime as rt

    rt._engine = None
    rt._engine_key = None

    cfg = PluginConfig(mode="observe", project="test")
    engine = get_engine(cfg)
    base = datetime.now(timezone.utc)
    payload_cmd = {"command": "echo hi"}

    for agent in ("a", "b"):
        for i in range(2):
            payload = {
                "session_id": "multi",
                "tool_name": "Bash",
                "tool_input": payload_cmd,
                "agent_id": agent,
            }
            ev = claude_payload_to_event(payload, host_event="PostToolUse")
            assert ev is not None
            ev.timestamp = base + timedelta(seconds=i + (0 if agent == "a" else 10))
            r = engine.handle(ev)
            assert "retry_storm" not in {h.type for h in r.decision.hits}
