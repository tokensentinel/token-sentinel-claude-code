"""True parallel hook processes (PostToolBatch-shaped concurrency).

Sequential subprocess tests validate rehydrate-across-restarts.
This module launches processes with no wait between starts so multiple
workers rehydrate/evaluate at once — the case that caused duplicate
tool_loop messages without a cross-process stream lock.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "scripts" / "hook_entry.py"


def _popen_hook(payload: dict, *, data_dir: Path) -> subprocess.Popen[str]:
    env = {
        **os.environ,
        "CLAUDE_PLUGIN_DATA": str(data_dir),
        "TOKENSENTINEL_MODE": "observe",
        "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
    }
    return subprocess.Popen(
        [sys.executable, str(ENTRY), "PostToolUse"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
        cwd=str(ROOT),
    )


def _collect(proc: subprocess.Popen[str], payload: dict) -> dict | None:
    assert proc.stdin is not None
    out, err = proc.communicate(json.dumps(payload), timeout=60)
    assert proc.returncode == 0, err
    if not out.strip():
        return None
    line = out.strip().splitlines()[-1]
    return json.loads(line)


def test_parallel_same_stream_single_tool_loop_fire(tmp_path: Path) -> None:
    """Six concurrent identical Reads: at most one tool_loop systemMessage.

    Without a stream lock, several processes each cross the threshold and
    emit redundant-loud messages. With the lock, only the process that
    first crosses the threshold should announce (others see history already
    past threshold / deduped window).
    """
    data = tmp_path / "par"
    data.mkdir()
    host = "parallel-sess"
    # Seed 2 sequential rows so concurrent batch starts near the threshold.
    seed = {
        "session_id": host,
        "tool_name": "Read",
        "tool_input": {"path": "src/app.py", "offset": 0},
        "agent_id": "main",
    }
    for _ in range(2):
        p = _popen_hook(seed, data_dir=data)
        _collect(p, seed)
        time.sleep(0.05)

    payload = dict(seed)
    procs = [_popen_hook(payload, data_dir=data) for _ in range(6)]
    # No delay between launches — true overlap.
    results = [_collect(p, payload) for p in procs]

    loop_msgs = [
        r
        for r in results
        if r
        and "systemMessage" in r
        and "tool_loop" in r.get("systemMessage", "")
    ]
    # Stream lock + emit cooldown: a parallel batch must not spam 3–4 identical
    # tool_loop systemMessages (the failure mode without locking).
    assert len(loop_msgs) <= 1, (
        f"expected at most one tool_loop systemMessage under parallel batch, "
        f"got {len(loop_msgs)}: {[r.get('systemMessage') for r in loop_msgs]}"
    )


def test_parallel_does_not_lose_rows(tmp_path: Path) -> None:
    data = tmp_path / "par2"
    data.mkdir()
    host = "parallel-rows"
    payload = {
        "session_id": host,
        "tool_name": "Bash",
        "tool_input": {"command": "echo parallel-row"},
        "agent_id": "main",
    }
    n = 6
    procs = [_popen_hook(payload, data_dir=data) for _ in range(n)]
    for p in procs:
        _collect(p, payload)

    import sqlite3

    db = data / "sessions.db"
    conn = sqlite3.connect(str(db))
    try:
        stream = f"{host}::main"
        count = conn.execute(
            "SELECT COUNT(*) FROM calls WHERE stream_id = ?", (stream,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert count == n
