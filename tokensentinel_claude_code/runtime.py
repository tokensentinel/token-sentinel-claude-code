"""Process-local EngineHandle cache (Phase B: in-process; sidecar HTTP later).

Claude spawns a new process per hook invocation via run_hook.js. Within a
single invocation we only need one EngineHandle. Cross-process state relies
on the adapter's SqliteSessionStore under CLAUDE_PLUGIN_DATA so rule windows
survive process restarts (disk path of Hybrid C).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from token_sentinel_adapter import EngineHandle
from token_sentinel_adapter.session_store import SqliteSessionStore
from token_sentinel_adapter.types import RuntimeStatus

from tokensentinel_claude_code.config import PluginConfig

_lock = threading.Lock()
_engine: EngineHandle | None = None
_engine_key: tuple[str, str, str | None] | None = None


def _data_dir() -> Path:
    raw = os.environ.get("CLAUDE_PLUGIN_DATA")
    if raw:
        return Path(raw)
    return Path.home() / ".claude" / "plugins" / "data" / "tokensentinel-tokensentinel"


def get_engine(cfg: PluginConfig) -> EngineHandle:
    """Return a configured EngineHandle (reused within process)."""
    global _engine, _engine_key
    key = (cfg.mode, cfg.project, cfg.cloud_endpoint)
    with _lock:
        if _engine is not None and _engine_key == key:
            return _engine

        data = _data_dir()
        data.mkdir(parents=True, exist_ok=True)
        store = SqliteSessionStore(data / "sessions.db", max_per_stream=200)

        cloud_ep = cfg.cloud_endpoint if cfg.cloud_endpoint and cfg.api_key else None
        api_key = cfg.api_key if cloud_ep else None

        # Disk-backed store means we rehydrate... EngineHandle's Sentinel is
        # still in-memory. For true multi-process windows we replay store
        # into a fresh handle via _warm_from_store on first use per stream.
        # v0.1: document limitation — full Hybrid C sidecar is Phase B+.
        # We still persist every call for reports and future rehydrate.
        engine = EngineHandle(
            project=cfg.project,
            preset=cfg.mode,
            cloud_endpoint=cloud_ep,
            api_key=api_key,
            store=store,
            status=RuntimeStatus.HEALTHY,
        )
        # Mark degraded note only if we cannot import adapter (handled at import)

        # Warm: subclass-style wrap by patching handle to rehydrate from sqlite
        # before evaluate when stream history empty in tracer.
        engine = _RehydratingEngine(engine)

        _engine = engine
        _engine_key = key
        return engine


class _RehydratingEngine:
    """Proxy that loads SQLite history into Sentinel before first live call."""

    def __init__(self, inner: EngineHandle) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def handle(self, event):  # type: ignore[no-untyped-def]
        from token_sentinel_adapter.normalize import stream_session_id

        stream_id = stream_session_id(event.host_session_id, event.agent_id or "main")
        # If tracer has no history for this stream, replay from sqlite.
        try:
            session = self._inner.sentinel.tracer.session(stream_id)
            if not session:
                prior = self._inner.store.list_calls(stream_id, limit=200)
                for call in prior:
                    # Re-feed without double-firing: use tracer.record only
                    self._inner.sentinel.tracer.record(call)
        except Exception:
            pass
        return self._inner.handle(event)
