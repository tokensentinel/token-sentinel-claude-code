"""hook_entry.py stdin/stdout smoke."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "scripts" / "hook_entry.py"


def test_hook_entry_post_tool(tmp_path, monkeypatch) -> None:
    env = {
        **dict(**{k: v for k, v in __import__("os").environ.items()}),
        "CLAUDE_PLUGIN_DATA": str(tmp_path),
        "TOKENSENTINEL_MODE": "observe",
        "PYTHONPATH": str(ROOT),
    }
    payload = {
        "session_id": "entry-1",
        "tool_name": "Read",
        "tool_input": {"path": "a.py"},
        "agent_id": "main",
    }
    r = subprocess.run(
        [sys.executable, str(ENTRY), "PostToolUse"],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        env=env,
        cwd=str(ROOT),
        check=False,
    )
    assert r.returncode == 0
    # First call usually silent (empty or _empty)
    if r.stdout.strip():
        data = json.loads(r.stdout.strip().splitlines()[-1])
        assert isinstance(data, dict)
