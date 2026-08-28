from __future__ import annotations

import fcntl
import os
from pathlib import Path
from types import TracebackType


class InstanceLock:
    """Prevent two bot processes from trading the same state directory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh: object | None = None

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+", encoding="utf-8")
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            fh.close()
            raise RuntimeError(f"another bot instance holds {self.path}") from exc
        fh.seek(0)
        fh.truncate()
        fh.write(str(os.getpid()))
        fh.flush()
        self._fh = fh

    def release(self) -> None:
        fh = self._fh
        if fh is None:
            return
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        fh.close()
        self._fh = None

    def __enter__(self) -> InstanceLock:
        self.acquire()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.release()
