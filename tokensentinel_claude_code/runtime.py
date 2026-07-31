"""Process-local EngineHandle with SQLite rehydrate across hook processes.

Claude Code runs each hook in a short-lived process (command hook → Node →
Python). In-memory Sentinel history does not survive process exit, so we
rehydrate CallRecords from SQLite before evaluating when the tracer is empty
for that stream.

This is the **disk-rehydrate deployment path** (not an HTTP sidecar). Failures
during rehydrate must surface as DEGRADED, not silent empty history.
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
        engine = _RehydratingEngine(inner)

        _engine = engine  # type: ignore[assignment]
        _engine_key = key
        return engine  # type: ignore[return-value]


class _RehydratingEngine:
    """Proxy that loads SQLite history into Sentinel before first live call.

    On rehydrate failure: set DEGRADED and attach a visible reason so the host
    can surface a systemMessage (fail-open, not silent-blind).
    """

    def __init__(self, inner: EngineHandle) -> None:
        self._inner = inner
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
        rehydrate_error: str | None = None

        try:
            session = self._inner.sentinel.tracer.session(stream_id)
            if not session:
                prior = self._inner.store.list_calls(stream_id, limit=200)
                for call in prior:
                    # Replay history without re-running handlers/rules on old rows.
                    self._inner.sentinel.tracer.record(call)
        except Exception as exc:  # noqa: BLE001 — must not crash host; must not hide
            rehydrate_error = f"{type(exc).__name__}: {exc}"
            self._last_rehydrate_error = rehydrate_error
            self._inner.set_status(RuntimeStatus.DEGRADED)

        result = self._inner.handle(event)

        if rehydrate_error is not None:
            # Ensure decision carries visible degraded status + reason once.
            result = self._apply_degraded(result, rehydrate_error)

        return result

    def _apply_degraded(self, result: EngineResult, error: str) -> EngineResult:
        decision = result.decision
        msg = (
            "TokenSentinel: session history rehydrate failed "
            f"({error}); waste windows may reset this turn. Mode still fail-open."
        )
        # Preserve deny/annotate reasons; otherwise surface rehydrate failure.
        reason = decision.reason or msg
        if decision.reason and not self._degraded_notified:
            reason = f"{decision.reason} | {msg}"
        elif not decision.reason:
            reason = msg

        new_decision = Decision(
            action=decision.action,
            reason=reason,
            status=RuntimeStatus.DEGRADED,
            hits=list(decision.hits),
            agent_id=decision.agent_id,
            host_session_id=decision.host_session_id,
            host_response=decision.host_response,
        )
        # Force annotate path so host_decision emits systemMessage even if ALLOW.
        if new_decision.action == DecisionAction.ALLOW and reason:
            new_decision = Decision(
                action=DecisionAction.ANNOTATE,
                reason=reason,
                status=RuntimeStatus.DEGRADED,
                hits=list(decision.hits),
                agent_id=decision.agent_id,
                host_session_id=decision.host_session_id,
                host_response=decision.host_response,
            )
        self._degraded_notified = True
        return EngineResult(decision=new_decision, call=result.call, events=result.events)
