"""Map kernel Decision → Claude Code hook stdout JSON."""

from __future__ import annotations

from typing import Any

from token_sentinel_adapter.types import Decision, DecisionAction, RuntimeStatus


def to_claude_stdout(decision: Decision, *, host_event: str) -> dict[str, Any] | None:
    """Build Claude hook JSON output.

    - DENY on PreToolUse → permissionDecision deny
    - ANNOTATE → systemMessage
    - ALLOW with empty reason → None / empty (no host noise)
    - DEGRADED/DOWN once → systemMessage about status
    """
    out: dict[str, Any] = {}

    if decision.status in {RuntimeStatus.DEGRADED, RuntimeStatus.DOWN} and decision.reason:
        out["systemMessage"] = decision.reason
    elif decision.action == DecisionAction.ANNOTATE and decision.reason:
        out["systemMessage"] = decision.reason
    elif decision.action == DecisionAction.DENY and decision.reason:
        out["systemMessage"] = decision.reason

    if decision.action == DecisionAction.DENY and host_event == "PreToolUse":
        out["hookSpecificOutput"] = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": decision.reason
            or "TokenSentinel blocked this tool call (strict mode).",
        }
        # Some Claude versions also honor top-level decision
        out["decision"] = "block"
        out["reason"] = decision.reason

    if not out:
        return None
    return out
