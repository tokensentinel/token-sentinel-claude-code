"""Claude stdout shaping."""

from __future__ import annotations

from token_sentinel_adapter.types import Decision, DecisionAction, RuntimeStatus, WasteHit

from tokensentinel_claude_code.host_decision import to_claude_stdout


def test_annotate_system_message() -> None:
    d = Decision(
        action=DecisionAction.ANNOTATE,
        reason="TokenSentinel · tool_loop · agent: main (conf 0.90). Mode: observe.",
        status=RuntimeStatus.HEALTHY,
        hits=[
            WasteHit(
                type="tool_loop",
                rule="v0.tool_loop",
                confidence=0.9,
                estimated_burn=0.0,
                agent_id="main",
                host_session_id="s",
            )
        ],
        agent_id="main",
        host_session_id="s",
    )
    out = to_claude_stdout(d, host_event="PostToolUse")
    assert out is not None
    assert "systemMessage" in out
    assert "tool_loop" in out["systemMessage"]


def test_deny_pre_tool() -> None:
    d = Decision(
        action=DecisionAction.DENY,
        reason="TokenSentinel blocked",
        status=RuntimeStatus.HEALTHY,
        hits=[],
        agent_id="main",
        host_session_id="s",
    )
    out = to_claude_stdout(d, host_event="PreToolUse")
    assert out is not None
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_allow_silent() -> None:
    d = Decision(
        action=DecisionAction.ALLOW,
        reason="",
        status=RuntimeStatus.HEALTHY,
        hits=[],
        agent_id="main",
        host_session_id="s",
    )
    out = to_claude_stdout(d, host_event="PostToolUse")
    assert out is None
