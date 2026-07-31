"""Cooldown-process cooldown so the same waste type is not announced many times
in one parallel tool batch.

StreamLock serializes rehydrate→evaluate→append so history is correct.
Even then, each sequential call above the rule threshold can fire again
(3rd, 4th, 5th call…). In a parallel batch those fires land as a burst of
identical systemMessages — redundant-loud.

We only suppress *host notifications* (systemMessage path), not storage.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from token_sentinel_adapter.types import WasteHit


def _db_path(data_dir: Path) -> Path:
    return data_dir / "sessions.db"


def _connect(data_dir: Path) -> sqlite3.Connection:
    path = _db_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS waste_emits (
            stream_id TEXT NOT NULL,
            waste_type TEXT NOT NULL,
            emitted_at REAL NOT NULL,
            PRIMARY KEY (stream_id, waste_type)
        )
        """
    )
    conn.commit()
    return conn


def should_emit_waste(
    data_dir: Path,
    stream_id: str,
    hits: list[WasteHit],
    *,
    cooldown_seconds: float = 3.0,
) -> bool:
    """Return True if we should surface this waste to the host UI.

    Call while holding the stream lock so check+record is atomic w.r.t. peers.
    """
    if not hits:
        return False
    # Loudest / primary type for this turn.
    waste_type = max(hits, key=lambda h: h.confidence).type
    now = time.time()
    conn = _connect(data_dir)
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT emitted_at FROM waste_emits WHERE stream_id = ? AND waste_type = ?",
            (stream_id, waste_type),
        ).fetchone()
        if row is not None and (now - float(row[0])) < cooldown_seconds:
            conn.commit()
            return False
        conn.execute(
            """
            INSERT INTO waste_emits (stream_id, waste_type, emitted_at)
            VALUES (?, ?, ?)
            ON CONFLICT(stream_id, waste_type) DO UPDATE SET emitted_at = excluded.emitted_at
            """,
            (stream_id, waste_type, now),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        # Fail-open on guard errors: better a duplicate message than silent miss.
        return True
    finally:
        conn.close()
