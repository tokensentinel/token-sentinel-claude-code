#!/usr/bin/env python3
"""Claude Code hook entry — stdin JSON → EngineHandle → stdout JSON.

Fail-open: any unexpected error exits 0 with empty stdout (host continues).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Ensure package import when run as a script
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from tokensentinel_claude_code.bridge import claude_payload_to_event  # noqa: E402
from tokensentinel_claude_code.config import load_config  # noqa: E402
from tokensentinel_claude_code.host_decision import to_claude_stdout  # noqa: E402
from tokensentinel_claude_code.runtime import get_engine  # noqa: E402


def _read_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def main(argv: list[str]) -> int:
    host_event = argv[1] if len(argv) > 1 else "PostToolUse"
    try:
        payload = _read_stdin()
        # Prefer explicit arg; fall back to payload field
        host_event = payload.get("hook_event_name") or payload.get("hookEventName") or host_event

        cfg = load_config()
        engine = get_engine(cfg)
        event = claude_payload_to_event(payload, host_event=str(host_event))
        if event is None:
            return 0

        result = engine.handle(event)
        out = to_claude_stdout(result.decision, host_event=str(host_event))
        if out:
            sys.stdout.write(json.dumps(out) + "\n")
        return 0
    except Exception as exc:  # noqa: BLE001 — never brick Claude Code
        try:
            sys.stderr.write(f"tokensentinel hook error: {type(exc).__name__}: {exc}\n")
        except Exception:
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
