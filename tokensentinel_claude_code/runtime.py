"""Process-local EngineHandle with SQLite rehydrate across hook processes.

Claude Code runs each hook in a short-lived process (command hook → Node →
Python). In-memory Sentinel history does not survive process exit, so we
rehydrate CallRecords from SQLite before evaluating when the tracer is empty
for that stream.

Deployment path: **command hooks + SQLite rehydrate** (not an HTTP sidecar).

Concurrency: parallel tool calls for the same stream can race on
rehydrate→evaluate→append. We hold a cross-process :class:`StreamLock` for
that span so only one process decides at a time per stream (prevents
duplicate tool_loop / retry_storm messages).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path

from token_sentinel_adapter import EngineHandle, EngineResult
from token_sentinel_adapter.session_store import SqliteSessionStore
from token_sentinel_adapter.types import (
    AdapterEvent,
    Decision,
    DecisionAction,
    RuntimeStatus,
)

from tokensentinel_claude_code.config import PluginConfig
from tokensentinel_claude_code.emit_guard import should_emit_waste
from tokensentinel_claude_code.stream_lock import StreamLock

_lock = threading.Lock()
_engine: EngineHandle | None = None
_engine_key: tuple[str, str, str | None] | None = None


def reset_engine_cache() -> None:
    """Test helper: drop the process-local engine singleton."""
    global _engine, _engine_key
    with _lock:
        _engine = None
        _engine_key = None


def _data_dir() -> Path:
    raw = os.environ.get("CLAUDE_PLUGIN_DATA")
    if raw:
        return Path(raw)
    return Path.home() / ".claude" / "plugins" / "data" / "tokensentinel-tokensentinel"


def get_engine(cfg: PluginConfig) -> EngineHandle:
    """Return a configured EngineHandle (reused within one OS process)."""
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

        inner = EngineHandle(
            project=cfg.project,
            preset=cfg.mode,
            cloud_endpoint=cloud_ep,
            api_key=api_key,
            store=store,
            status=RuntimeStatus.HEALTHY,
        )
        engine = _RehydratingEngine(inner, data_dir=data)

        _engine = engine  # type: ignore[assignment]
        _engine_key = key
        return engine  # type: ignore[return-value]


class _RehydratingEngine:
    """Proxy: stream lock → rehydrate → evaluate → append (via EngineHandle).

    On rehydrate failure: set DEGRADED and attach a visible reason so the host
    can surface a systemMessage (fail-open, not silent-blind).
    """

    def __init__(self, inner: EngineHandle, *, data_dir: Path) -> None:
        self._inner = inner
        self._data_dir = data_dir
        self._degraded_notified = False
        self._last_rehydrate_error: str | None = None

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    @property
    def status(self) -> RuntimeStatus:
        return self._inner.status

    def set_status(self, status: RuntimeStatus) -> None:
        self._inner.set_status(status)

    def handle(self, event: AdapterEvent) -> EngineResult:
        from token_sentinel_adapter.normalize import stream_session_id

        stream_id = stream_session_id(event.host_session_id, event.agent_id or "main")

        # Serialize rehydrate→evaluate→append across parallel OS processes
        # for this stream (Claude PostToolBatch / parallel tools).
        try:
            with StreamLock(self._data_dir, stream_id):
                return self._handle_locked(event, stream_id)
        except TimeoutError as exc:
            self._inner.set_status(RuntimeStatus.DEGRADED)
            result = self._inner.handle(event)
            return self._apply_degraded(
                result,
                f"TimeoutError: {exc}",
            )

    def _handle_locked(self, event: AdapterEvent, stream_id: str) -> EngineResult:
        rehydrate_error: str | None = None

        try:
            session = self._inner.sentinel.tracer.session(stream_id)
            if not session:
                prior = self._inner.store.list_calls(stream_id, limit=200)
                for call in prior:
                    # Replay history without re-running handlers on old rows.
                    self._inner.sentinel.tracer.record(call)
        except Exception as exc:  # noqa: BLE001 — must not crash host; must not hide
            rehydrate_error = f"{type(exc).__name__}: {exc}"
            self._last_rehydrate_error = rehydrate_error
            self._inner.set_status(RuntimeStatus.DEGRADED)

        result = self._inner.handle(event)

        if rehydrate_error is not None:
            result = self._apply_degraded(result, rehydrate_error)
        else:
            result = self._apply_emit_cooldown(result, stream_id)

        return result

    def _apply_emit_cooldown(self, result: EngineResult, stream_id: str) -> EngineResult:
        """Suppress redundant systemMessages for the same waste type in a burst."""
        decision = result.decision
        if not decision.hits:
            return result
        if decision.action == DecisionAction.DENY:
            # Strict: still deny every time; message may repeat (acceptable).
            return result
        if not should_emit_waste(self._data_dir, stream_id, decision.hits):
            # Keep call recorded; silence host noise for this process.
            quiet = Decision(
                action=DecisionAction.ALLOW,
                reason="",
                status=decision.status,
                hits=list(decision.hits),
                agent_id=decision.agent_id,
                host_session_id=decision.host_session_id,
                host_response=None,
            )
            return EngineResult(decision=quiet, call=result.call, events=result.events)
        return result

    def _apply_degraded(self, result: EngineResult, error: str) -> EngineResult:
        decision = result.decision
        msg = (
            "TokenSentinel: session history rehydrate failed "
            f"({error}); waste windows may reset this turn. Mode still fail-open."
        )
        reason = decision.reason or msg
        if decision.reason and not self._degraded_notified:
            reason = f"{decision.reason} | {msg}"
        elif not decision.reason:
            reason = msg

        action = decision.action
        if action == DecisionAction.ALLOW and reason:
            action = DecisionAction.ANNOTATE

        new_decision = Decision(
            action=action,
            reason=reason,
            status=RuntimeStatus.DEGRADED,
            hits=list(decision.hits),
            agent_id=decision.agent_id,
            host_session_id=decision.host_session_id,
            host_response=decision.host_response,
        )
        self._degraded_notified = True
        return EngineResult(decision=new_decision, call=result.call, events=result.events)
