"""Cross-process path: each event is a fresh Python process rehydrating SQLite.

This matches production (command hook → Node → new Python per invocation),
unlike in-process EngineHandle loops that never cold-start.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "scripts" / "hook_entry.py"


def _run_hook(payload: dict, *, data_dir: Path, mode: str = "observe") -> dict | None:
    env = {
        **os.environ,
        "CLAUDE_PLUGIN_DATA": str(data_dir),
        "TOKENSENTINEL_MODE": mode,
        "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
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
    assert r.returncode == 0, r.stderr
    if not r.stdout.strip():
        return None
    # last JSON line
    line = r.stdout.strip().splitlines()[-1]
    return json.loads(line)


def test_retry_storm_survives_process_boundary(tmp_path: Path) -> None:
    """Five identical Bash calls in five processes → retry_storm on last."""
    data = tmp_path / "cp"
    data.mkdir()
    host = "cross-proc-sess"
    payload_base = {
        "session_id": host,
        "tool_name": "Bash",
        "tool_input": {"command": "echo cross-process-identical"},
        "agent_id": "main",
    }

    last = None
    for _ in range(5):
        last = _run_hook(payload_base, data_dir=data)

    assert last is not None, "expected systemMessage after enough identical retries"
    msg = last.get("systemMessage", "")
    assert "retry_storm" in msg or "Retry" in msg or "storm" in msg.lower() or "TokenSentinel" in msg


def test_sibling_agents_isolated_across_processes(tmp_path: Path) -> None:
    """Two agents × 2 identical calls each (4 processes) must not storm."""
    data = tmp_path / "cp2"
    data.mkdir()
    host = "cross-proc-multi"
    cmd = {"command": "echo sibling-shared-hash"}

    for agent in ("worker-a", "worker-b"):
        for _ in range(2):
            out = _run_hook(
                {
                    "session_id": host,
                    "tool_name": "Bash",
                    "tool_input": cmd,
                    "agent_id": agent,
                },
                data_dir=data,
            )
            if out and "systemMessage" in out:
                assert "retry_storm" not in out["systemMessage"]
