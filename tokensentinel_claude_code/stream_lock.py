"""Cross-process lock for rehydrate → evaluate → append (one stream at a time).

SQLite serializes *writes*, but concurrent hook processes can each rehydrate,
evaluate, and decide before the others commit — causing duplicate tool_loop /
retry_storm systemMessages under parallel tool batches.

This lock covers the full critical section across OS processes (not threads).
"""

from __future__ import annotations

import hashlib
import sys
import time
from pathlib import Path
from types import TracebackType


def _lock_path(data_dir: Path, stream_id: str) -> Path:
    digest = hashlib.sha256(stream_id.encode("utf-8")).hexdigest()[:24]
    return data_dir / "locks" / f"{digest}.lock"


class StreamLock:
    """Exclusive advisory lock for one logical stream_id."""

    def __init__(self, data_dir: Path, stream_id: str, *, timeout_seconds: float = 30.0) -> None:
        self.path = _lock_path(data_dir, stream_id)
        self.timeout_seconds = timeout_seconds
        self._fh: object | None = None

    def __enter__(self) -> StreamLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        self._fh = fh
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            try:
                self._lock(fh)
                return self
            except OSError:
                if time.monotonic() >= deadline:
                    fh.close()
                    self._fh = None
                    raise TimeoutError(f"stream lock timeout: {self.path}")
                time.sleep(0.02)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        fh = self._fh
        if fh is None:
            return
        try:
            self._unlock(fh)
        finally:
            try:
                fh.close()  # type: ignore[union-attr]
            except Exception:
                pass
            self._fh = None

    def _lock(self, fh: object) -> None:
        if sys.platform == "win32":
            import msvcrt

            fh.seek(0)  # type: ignore[union-attr]
            # Lock one byte; LK_NBLCK raises OSError if busy.
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[union-attr]
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[union-attr]

    def _unlock(self, fh: object) -> None:
        if sys.platform == "win32":
            import msvcrt

            try:
                fh.seek(0)  # type: ignore[union-attr]
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[union-attr]
            except OSError:
                pass
        else:
            import fcntl

            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)  # type: ignore[union-attr]
