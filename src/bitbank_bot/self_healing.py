"""Runtime recovery helpers. Never rewrite source; only recover process state."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from bitbank_bot.logging_setup import slog


class ErrorClass(str, Enum):
    TRANSIENT = "TRANSIENT"
    RECOVERABLE = "RECOVERABLE"
    STATE_ERROR = "STATE_ERROR"
    FATAL = "FATAL"


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


TRANSIENT_TYPES = {
    "TimeoutError",
    "ConnectError",
    "ConnectTimeout",
    "ReadTimeout",
    "WriteTimeout",
    "NetworkError",
    "HTTPError",
}
RECOVERABLE_HINTS = ("websocket", "disconnect", "429", "5xx", "server error", "rate limited")
STATE_HINTS = ("stale", "mismatch", "reconcile", "position", "pending")
FATAL_HINTS = ("auth_failure", "kill_switch", "missing_keys", "internal state")


def classify_error(exc: BaseException | None = None, *, reason: str = "") -> ErrorClass:
    text = f"{type(exc).__name__ if exc else ''} {exc} {reason}".lower()
    name = type(exc).__name__ if exc else ""
    if any(hint in text for hint in FATAL_HINTS):
        return ErrorClass.FATAL
    if any(hint in text for hint in STATE_HINTS):
        return ErrorClass.STATE_ERROR
    if name in TRANSIENT_TYPES or "timeout" in text or "connection" in text:
        return ErrorClass.TRANSIENT
    if any(hint in text for hint in RECOVERABLE_HINTS):
        return ErrorClass.RECOVERABLE
    if exc is not None:
        return ErrorClass.RECOVERABLE
    return ErrorClass.TRANSIENT


def backoff_seconds(attempt: int, cap: float = 16.0) -> float:
    base = min(cap, 1.0 * (2**max(0, attempt)))
    return base + random.uniform(0, base * 0.25)


@dataclass
class CircuitBreaker:
    threshold: int = 5
    cooldown_sec: float = 30.0
    failures: int = 0
    opened_at: float = 0.0
    state: CircuitState = CircuitState.CLOSED

    def allow(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.opened_at >= self.cooldown_sec:
                self.state = CircuitState.HALF_OPEN
                slog("WATCHDOG", "circuit half-open")
                return True
            return False
        return True

    def success(self) -> None:
        self.failures = 0
        if self.state != CircuitState.CLOSED:
            slog("WATCHDOG", "circuit closed")
        self.state = CircuitState.CLOSED

    def failure(self) -> None:
        self.failures += 1
        if self.state == CircuitState.HALF_OPEN or self.failures >= self.threshold:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()
            slog("WATCHDOG", "circuit open", failures=self.failures)


@dataclass
class ConnectionHealth:
    last_loop_at: float = 0.0
    last_ticker_at: float = 0.0
    last_candle_at: float = 0.0
    last_ws_at: float = 0.0
    last_rest_at: float = 0.0
    last_strategy_at: float = 0.0
    last_order_check_at: float = 0.0
    last_balance_at: float = 0.0
    rest_ok: bool = False
    ws_ok: bool = False
    consecutive_errors: int = 0
    total_errors: int = 0
    restart_count: int = 0
    health_score: int = 100

    def mark(self, field_name: str) -> None:
        setattr(self, field_name, time.monotonic())

    def note_rest(self, ok: bool) -> None:
        if ok:
            self.last_rest_at = time.monotonic()
            self.rest_ok = True
            self.consecutive_errors = 0
        else:
            self.rest_ok = False
            self.consecutive_errors += 1
            self.total_errors += 1

    def snapshot(self) -> dict[str, object]:
        now = time.monotonic()

        def age(stamp: float) -> float | None:
            if stamp <= 0:
                return None
            return round(now - stamp, 3)

        return {
            "rest_ok": self.rest_ok,
            "ws_ok": self.ws_ok,
            "health_score": self.health_score,
            "loop_age": age(self.last_loop_at),
            "ticker_age": age(self.last_ticker_at),
            "candle_age": age(self.last_candle_at),
            "ws_age": age(self.last_ws_at),
            "rest_age": age(self.last_rest_at),
            "strategy_age": age(self.last_strategy_at),
            "order_check_age": age(self.last_order_check_at),
            "balance_age": age(self.last_balance_at),
            "consecutive_errors": self.consecutive_errors,
            "total_errors": self.total_errors,
            "restart_count": self.restart_count,
        }

    def refresh_score(self, *, market_real: bool, ws_enabled: bool) -> int:
        score = 100
        if not self.rest_ok:
            score -= 40
        if ws_enabled and not self.ws_ok:
            score -= 15
        if not market_real:
            score -= 30
        if self.consecutive_errors:
            score -= min(20, self.consecutive_errors * 4)
        self.health_score = max(0, score)
        return self.health_score


@dataclass
class SelfHealingEngine:
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    health: ConnectionHealth = field(default_factory=ConnectionHealth)
    quarantined: set[str] = field(default_factory=set)
    task_failures: dict[str, int] = field(default_factory=dict)

    def on_success(self, name: str) -> None:
        self.breaker.success()
        self.health.note_rest(True)
        self.task_failures[name] = 0

    def on_error(self, name: str, exc: BaseException | None = None, *, reason: str = "") -> ErrorClass:
        kind = classify_error(exc, reason=reason)
        self.breaker.failure()
        self.health.note_rest(False)
        self.task_failures[name] = self.task_failures.get(name, 0) + 1
        slog(
            "ERROR",
            "classified runtime error",
            task=name,
            error_class=kind.value,
            error=type(exc).__name__ if exc else reason,
            retry_count=self.task_failures[name],
        )
        if self.task_failures[name] >= 8:
            self.quarantined.add(name)
            slog("WATCHDOG", "QUARANTINE", task=name)
        return kind

    def recover_ws(self, starter: Callable[[], None]) -> None:
        try:
            starter()
            self.health.restart_count += 1
            slog("WEBSOCKET", "self-heal reconnect requested")
        except Exception as exc:
            self.on_error("websocket", exc, reason="reconnect")
