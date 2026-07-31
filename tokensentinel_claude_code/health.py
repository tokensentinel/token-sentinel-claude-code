"""Live health probe for TokenSentinel Claude Code plugin."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class HealthReport:
    ok: bool
    status: str
    mode: str
    project: str
    python: str
    plugin_version: str
    sdk_version: str | None
    adapter_version: str | None
    data_dir: str
    sessions_db: str
    sessions_db_ok: bool
    cloud: str
    errors: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


def _data_dir() -> Path:
    raw = os.environ.get("CLAUDE_PLUGIN_DATA")
    if raw:
        return Path(raw)
    return Path.home() / ".claude" / "plugins" / "data" / "tokensentinel-tokensentinel"


def probe_health() -> HealthReport:
    """Inspect imports, config, and session DB — does not require a live session."""
    from tokensentinel_claude_code import __version__ as plugin_version
    from tokensentinel_claude_code.config import load_config

    errors: list[str] = []
    notes: list[str] = []
    cfg = load_config()

    sdk_version: str | None = None
    adapter_version: str | None = None
    try:
        import token_sentinel as ts

        sdk_version = getattr(ts, "__version__", "unknown")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"token_sentinel import failed: {type(exc).__name__}: {exc}")

    try:
        import token_sentinel_adapter as tsa

        adapter_version = getattr(tsa, "__version__", "unknown")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"token_sentinel_adapter import failed: {type(exc).__name__}: {exc}")

    data = _data_dir()
    db_path = data / "sessions.db"
    sessions_db_ok = False
    try:
        data.mkdir(parents=True, exist_ok=True)
        import sqlite3

        conn = sqlite3.connect(str(db_path), timeout=5)
        try:
            conn.execute("PRAGMA busy_timeout=5000")
            conn.execute("SELECT 1")
            # Table may not exist yet before first tool event — still OK.
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='calls'"
            ).fetchone()
            if row is None:
                notes.append("sessions table not created yet (no tool events stored)")
            sessions_db_ok = True
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        errors.append(f"sessions db check failed: {type(exc).__name__}: {exc}")

    cloud = "off"
    if cfg.cloud_endpoint and cfg.api_key:
        cloud = "configured"
    elif cfg.cloud_endpoint or cfg.api_key:
        cloud = "partial"
        notes.append("cloud needs both endpoint and api_key")

    if errors:
        status = "down"
        ok = False
    elif notes and not sessions_db_ok:
        status = "degraded"
        ok = False
    else:
        status = "healthy"
        ok = True

    # Deployment honesty: this plugin uses per-hook processes + SQLite, not HTTP sidecar.
    notes.append("state_path=sqlite_rehydrate (no HTTP sidecar in this release)")

    return HealthReport(
        ok=ok,
        status=status,
        mode=cfg.mode,
        project=cfg.project,
        python=sys.executable,
        plugin_version=plugin_version,
        sdk_version=sdk_version,
        adapter_version=adapter_version,
        data_dir=str(data),
        sessions_db=str(db_path),
        sessions_db_ok=sessions_db_ok,
        cloud=cloud,
        errors=errors,
        notes=notes,
    )


def main() -> int:
    report = probe_health()
    print(report.to_json())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
