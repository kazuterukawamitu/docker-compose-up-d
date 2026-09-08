"""Classify runtime errors and recover connection/state — never rewrite source."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from bitbank_bot.logging_setup import slog
from bitbank_bot.rest_client import BitbankAPIError, is_auth_error


class ErrorClass(str, Enum):
    TRANSIENT = "TRANSIENT"
    RECOVERABLE = "RECOVERABLE"
    STATE_ERROR = "STATE_ERROR"
    FATAL = "FATAL"


class RecoveryAction(str, Enum):
    RETRY = "RETRY"
    RECONNECT = "RECONNECT"
    RECONCILE = "RECONCILE"
    RESTART_TASK = "RESTART_TASK"
    QUARANTINE = "QUARANTINE"
    STOP = "STOP"


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreaker:
    failures_to_open: int = 5
    open_sec: float = 30.0
    _failures: int = 0
    _opened_at: float = 0.0
    state: CircuitState = CircuitState.CLOSED

    def allow(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self._opened_at >= self.open_sec:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def on_success(self) -> None:
        self._failures = 0
        self.state = CircuitState.CLOSED

    def on_failure(self) -> None:
        self._failures += 1
        if self.state == CircuitState.HALF_OPEN or self._failures >= self.failures_to_open:
            self.state = CircuitState.OPEN
            self._opened_at = time.monotonic()
            slog("WATCHDOG", "circuit open", failures=self._failures)


def classify_exception(exc: BaseException) -> ErrorClass:
    if isinstance(exc, BitbankAPIError):
        if is_auth_error(exc):
            return ErrorClass.FATAL
        if exc.http_status in {429} or (exc.http_status is not None and exc.http_status >= 500):
            return ErrorClass.TRANSIENT
        if exc.http_status == 408:
            return ErrorClass.TRANSIENT
        return ErrorClass.RECOVERABLE
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timeout" in text or "temporar" in text:
        return ErrorClass.TRANSIENT
    if "connect" in name or "network" in name or "disconnect" in text:
        return ErrorClass.RECOVERABLE
    if "stale" in text or "mismatch" in text:
        return ErrorClass.STATE_ERROR
    return ErrorClass.RECOVERABLE


def action_for(kind: ErrorClass, *, side_effect: bool) -> RecoveryAction:
    if kind == ErrorClass.FATAL:
        return RecoveryAction.STOP
    if kind == ErrorClass.STATE_ERROR:
        return RecoveryAction.RECONCILE
    if side_effect:
        return RecoveryAction.RECONCILE
    if kind == ErrorClass.TRANSIENT:
        return RecoveryAction.RETRY
    return RecoveryAction.RECONNECT


def backoff_seconds(attempt: int, cap: float = 16.0) -> float:
    base = min(cap, 1.0 * (2**attempt))
    return base + random.uniform(0, base * 0.25)


@dataclass
class RuntimeWatch:
    last_trading_loop_at: float = 0.0
    last_ticker_at: float = 0.0
    last_candle_at: float = 0.0
    last_ws_message_at: float = 0.0
    last_rest_success_at: float = 0.0
    last_strategy_at: float = 0.0
    last_order_check_at: float = 0.0
    last_balance_sync_at: float = 0.0
    consecutive_errors: int = 0
    total_errors: int = 0
    restart_counts: dict[str, int] = field(default_factory=dict)

    def mark(self, field_name: str) -> None:
        setattr(self, field_name, time.monotonic())

    def note_error(self) -> None:
        self.consecutive_errors += 1
        self.total_errors += 1

    def note_ok(self) -> None:
        self.consecutive_errors = 0


class TaskSupervisor:
    def __init__(self, max_restarts: int = 5, window_sec: float = 120.0) -> None:
        self.max_restarts = max_restarts
        self.window_sec = window_sec
        self._restarts: dict[str, list[float]] = {}
        self.quarantined: set[str] = set()

    def should_restart(self, name: str) -> bool:
        if name in self.quarantined:
            slog("WATCHDOG", "task quarantined", task_name=name)
            return False
        now = time.monotonic()
        stamps = [t for t in self._restarts.get(name, []) if now - t < self.window_sec]
        if len(stamps) >= self.max_restarts:
            self.quarantined.add(name)
            slog("WATCHDOG", "QUARANTINE", task_name=name, restarts=len(stamps))
            return False
        stamps.append(now)
        self._restarts[name] = stamps
        return True


class SelfHealingEngine:
    def __init__(self, failures_to_open: int = 5) -> None:
        self.watch = RuntimeWatch()
        self.circuit = CircuitBreaker(failures_to_open=failures_to_open)
        self.tasks = TaskSupervisor()
        self.kill_switch = False

    def handle(self, exc: BaseException, *, side_effect: bool = False) -> RecoveryAction:
        kind = classify_exception(exc)
        action = action_for(kind, side_effect=side_effect)
        self.watch.note_error()
        slog(
            "ERROR",
            "self-healing classified",
            error_type=type(exc).__name__,
            error_class=kind.value,
            action=action.value,
            consecutive_errors=self.watch.consecutive_errors,
            detail=str(exc)[:200],
        )
        if action == RecoveryAction.STOP:
            self.kill_switch = True
        if kind in {ErrorClass.TRANSIENT, ErrorClass.RECOVERABLE}:
            self.circuit.on_failure()
        return action

    def recovered(self) -> None:
        self.watch.note_ok()
        self.circuit.on_success()


def retry_get(op: Callable[[], object], *, attempts: int = 5, label: str = "get") -> object:
    last: BaseException | None = None
    for attempt in range(max(1, attempts)):
        try:
            result = op()
            return result
        except Exception as exc:  # noqa: BLE001 — classified below
            last = exc
            kind = classify_exception(exc)
            if kind == ErrorClass.FATAL or attempt + 1 >= attempts:
                slog("ERROR", "GET retry exhausted", label=label, error=type(exc).__name__)
                raise
            delay = backoff_seconds(attempt)
            slog("ERROR", "GET retry", label=label, attempt=attempt, delay=round(delay, 2))
            time.sleep(delay)
    assert last is not None
    raise last
