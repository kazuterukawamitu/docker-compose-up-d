"""Runtime recovery policy. Recovers process state, never rewrites source."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import random
import time
from typing import Callable, TypeVar

from bitbank_bot.logging_setup import slog
from bitbank_bot.rest_client import BitbankAPIError


class ErrorClass(str, Enum):
    TRANSIENT = "TRANSIENT"
    RECOVERABLE = "RECOVERABLE"
    STATE_ERROR = "STATE_ERROR"
    FATAL = "FATAL"


class HealAction(str, Enum):
    RETRY = "RETRY"
    RECONNECT = "RECONNECT"
    RECONCILE = "RECONCILE"
    RESTART_TASK = "RESTART_TASK"
    QUARANTINE = "QUARANTINE"
    STOP = "STOP"


TRANSIENT_TYPES = (
    TimeoutError,
    ConnectionError,
    OSError,
    BrokenPipeError,
    ConnectionResetError,
    ConnectionAbortedError,
)
TRANSIENT_NAMES = {
    "TimeoutException",
    "ConnectError",
    "ReadTimeout",
    "WriteTimeout",
    "NetworkError",
    "RemoteProtocolError",
    "TemporaryNetworkError",
}


def classify_error(exc: BaseException) -> ErrorClass:
    name = type(exc).__name__
    if isinstance(exc, BitbankAPIError):
        if exc.http_status in {429, 500, 502, 503, 504}:
            return ErrorClass.TRANSIENT
        if exc.code in {10001, 10002, 10003}:
            return ErrorClass.TRANSIENT
        if exc.http_status in {401, 403} or exc.code in {20001, 20002, 20003, 20011}:
            return ErrorClass.FATAL
        msg = str(exc).lower()
        if "live_confirmed" in msg or "secret missing" in msg:
            return ErrorClass.FATAL
        return ErrorClass.RECOVERABLE
    if isinstance(exc, TRANSIENT_TYPES) or name in TRANSIENT_NAMES:
        return ErrorClass.TRANSIENT
    if name in {"JSONDecodeError", "InvalidOperation", "ValueError"}:
        return ErrorClass.STATE_ERROR
    return ErrorClass.RECOVERABLE


def action_for(kind: ErrorClass, *, side_effect: bool = False) -> HealAction:
    if kind is ErrorClass.FATAL:
        return HealAction.STOP
    if kind is ErrorClass.STATE_ERROR:
        return HealAction.RECONCILE
    if kind is ErrorClass.TRANSIENT:
        return HealAction.RETRY if not side_effect else HealAction.RECONCILE
    return HealAction.RECONNECT


def backoff_seconds(attempt: int, cap: float = 16.0) -> float:
    base = min(cap, 1.0 * (2 ** max(0, attempt)))
    return base + random.uniform(0, base * 0.25)


T = TypeVar("T")


def retry_get(
    fn: Callable[[], T],
    *,
    attempts: int = 5,
    label: str = "get",
    side_effect: bool = False,
) -> T:
    """Retry a side-effect-free callable. Never use this for order POST."""
    if side_effect:
        raise RuntimeError("retry_get refused a side-effecting call")
    last: BaseException | None = None
    for attempt in range(max(1, attempts)):
        try:
            return fn()
        except Exception as exc:
            last = exc
            kind = classify_error(exc)
            slog(
                "HEAL",
                "retry_get failed",
                label=label,
                attempt=attempt,
                error=type(exc).__name__,
                error_class=kind.value,
            )
            if kind is ErrorClass.FATAL or attempt + 1 >= attempts:
                break
            time.sleep(backoff_seconds(attempt))
    assert last is not None
    raise last


@dataclass
class CircuitBreaker:
    failures_to_open: int = 5
    cooloff_sec: float = 30.0
    state: str = "CLOSED"
    failures: int = 0
    opened_at: float = 0.0

    def allow(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.monotonic() - self.opened_at >= self.cooloff_sec:
                self.state = "HALF_OPEN"
                slog("HEAL", "circuit half-open")
                return True
            return False
        return True

    def success(self) -> None:
        self.failures = 0
        if self.state != "CLOSED":
            slog("HEAL", "circuit closed")
        self.state = "CLOSED"

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failures_to_open:
            self.state = "OPEN"
            self.opened_at = time.monotonic()
            slog("HEAL", "circuit open", failures=self.failures)


@dataclass
class TaskSupervisor:
    max_restarts: int = 5
    window_sec: float = 120.0
    restarts: dict[str, list[float]] = field(default_factory=dict)

    def record_crash(self, name: str) -> HealAction:
        now = time.monotonic()
        stamps = [t for t in self.restarts.get(name, []) if now - t < self.window_sec]
        stamps.append(now)
        self.restarts[name] = stamps
        if len(stamps) > self.max_restarts:
            slog("HEAL", "task quarantined", task=name, restarts=len(stamps))
            return HealAction.QUARANTINE
        slog("HEAL", "task restart scheduled", task=name, restarts=len(stamps))
        return HealAction.RESTART_TASK
