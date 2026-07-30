"""Bridge mapping tests."""

from __future__ import annotations

import json
from pathlib import Path

from tokensentinel_claude_code.bridge import claude_payload_to_event

FIXTURES = Path(__file__).parent / "fixtures"


def test_post_tool_main() -> None:
    payload = json.loads((FIXTURES / "post_tool_read.json").read_text())
    ev = claude_payload_to_event(payload, host_event="PostToolUse")
    assert ev is not None
    assert ev.host == "claude-code"
    assert ev.tool_name == "Read"
    assert ev.agent_id == "main"
    assert ev.host_session_id == "sess-fixture-1"


def test_subagent_id() -> None:
    payload = json.loads((FIXTURES / "post_tool_subagent.json").read_text())
    ev = claude_payload_to_event(payload, host_event="PostToolUse")
    assert ev is not None
    assert ev.agent_id == "explore-2"
    assert ev.agent_type == "Explore"


def test_session_start() -> None:
    ev = claude_payload_to_event(
        {"session_id": "s1"},
        host_event="SessionStart",
    )
    assert ev is not None
    assert ev.host_event == "SessionStart"
    assert ev.tool_name is None
