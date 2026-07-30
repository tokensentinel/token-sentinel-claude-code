"""Map Claude Code hook stdin JSON → AdapterEvent (architecture Layer 1)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from token_sentinel_adapter.types import AdapterEvent

# Host events that produce evaluable tool/call records.
_TOOLISH = frozenset(
    {
        "PreToolUse",
        "PostToolUse",
        "PostToolUseFailure",
        "PermissionRequest",
        "PermissionDenied",
    }
)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _session_id(payload: dict[str, Any]) -> str:
    for key in ("session_id", "sessionId", "conversation_id", "conversationId"):
        v = payload.get(key)
        if v:
            return str(v)
    # Stable fallback so rules still window within one process run
    return "claude-unknown-session"


def _agent_id(payload: dict[str, Any]) -> str:
    for key in ("agent_id", "agentId"):
        v = payload.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return "main"


def _agent_type(payload: dict[str, Any]) -> str | None:
    for key in ("agent_type", "agentType"):
        v = payload.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return None


def _tool_name(payload: dict[str, Any]) -> str | None:
    for key in ("tool_name", "toolName", "name"):
        v = payload.get(key)
        if v:
            return str(v)
    tool = payload.get("tool")
    if isinstance(tool, dict) and tool.get("name"):
        return str(tool["name"])
    return None


def _tool_input(payload: dict[str, Any]) -> Any:
    for key in ("tool_input", "toolInput", "input"):
        if key in payload:
            return payload[key]
    tool = payload.get("tool")
    if isinstance(tool, dict) and "input" in tool:
        return tool["input"]
    return None


def _tool_output(payload: dict[str, Any]) -> Any:
    for key in ("tool_response", "toolResponse", "tool_output", "toolOutput", "output"):
        if key in payload:
            return payload[key]
    return None


def claude_payload_to_event(
    payload: dict[str, Any],
    *,
    host_event: str,
) -> AdapterEvent | None:
    """Convert Claude hook JSON to AdapterEvent.

    Returns None for events the kernel should ignore (empty payload).
    """
    if not payload and host_event not in {"SessionStart", "SessionEnd"}:
        return None

    host_session_id = _session_id(payload)
    agent_id = _agent_id(payload)
    agent_type = _agent_type(payload)
    parent = payload.get("parent_session_id") or payload.get("parentSessionId")
    parent_session_id = str(parent) if parent else host_session_id

    tool_name = _tool_name(payload)
    tool_input = _tool_input(payload)
    tool_output = _tool_output(payload)
    is_error = host_event == "PostToolUseFailure" or bool(
        payload.get("is_error") or payload.get("isError")
    )

    user_facing = False
    messages: list[dict[str, Any]] | None = None
    if host_event == "UserPromptSubmit":
        user_facing = True
        prompt = payload.get("prompt") or payload.get("user_prompt") or payload.get("text")
        if prompt is not None:
            messages = [{"role": "user", "content": str(prompt)}]

    # Session lifecycle without tools — still open a stream for status/report
    if host_event in {"SessionStart", "SessionEnd", "SubagentStart", "SubagentStop"}:
        return AdapterEvent(
            host="claude-code",
            host_event=host_event,
            host_session_id=host_session_id,
            agent_id=agent_id if host_event.startswith("Subagent") else "main",
            agent_type=agent_type,
            parent_session_id=parent_session_id,
            timestamp=datetime.now(timezone.utc),
            raw_payload=_as_dict(payload) if payload else {},
        )

    if host_event in _TOOLISH and not tool_name:
        # Nothing to evaluate
        return AdapterEvent(
            host="claude-code",
            host_event=host_event,
            host_session_id=host_session_id,
            agent_id=agent_id,
            agent_type=agent_type,
            parent_session_id=parent_session_id,
            raw_payload=_as_dict(payload),
        )

    return AdapterEvent(
        host="claude-code",
        host_event=host_event,
        host_session_id=host_session_id,
        agent_id=agent_id,
        agent_type=agent_type,
        parent_session_id=parent_session_id,
        tool_name=tool_name,
        tool_input=(
            tool_input
            if isinstance(tool_input, (dict, list, str)) or tool_input is None
            else str(tool_input)
        ),
        tool_output=tool_output,
        tool_is_error=is_error,
        user_facing_output=user_facing,
        messages=messages,
        timestamp=datetime.now(timezone.utc),
        raw_payload=_as_dict(payload),
    )
