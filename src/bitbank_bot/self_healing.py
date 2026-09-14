"""Runtime recovery helpers. Never rewrites source on the VPS.

Classifies errors, backs off GET-type calls (delegated to RestClient),
and exposes a circuit breaker for repeated subsystem failures.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum

from bitbank_bot.logging_setup import slog

TRANSIENT = "TRANSIENT"
RECOVERABLE = "RECOVERABLE"
STATE_ERROR = "STATE_ERROR"
FATAL = "FATAL"


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


def classify_error(exc: BaseException) -> str:
    name = type(exc).__name__
    text = str(exc).lower()
    if name in {"TimeoutError", "ConnectError", "ConnectTimeout", "ReadTimeout", "NetworkError"}:
        return TRANSIENT
    if "429" in text or "rate limited" in text:
        return TRANSIENT
    if "5xx" in text or "server error" in text:
        return RECOVERABLE
    if "auth" in text or "20001" in text or "20002" in text:
        return FATAL
    if "stale" in text or "mismatch" in text:
        return STATE_ERROR
    return RECOVERABLE


@dataclass
class CircuitBreaker:
    failures_needed: int = 5
    open_sec: float = 30.0
    state: CircuitState = CircuitState.CLOSED
    failures: int = 0
    opened_at: float = 0.0

    def allow(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.opened_at >= self.open_sec:
                self.state = CircuitState.HALF_OPEN
                slog("HEAL", "circuit half-open")
                return True
            return False
        return True

    def ok(self) -> None:
        self.failures = 0
        self.state = CircuitState.CLOSED

    def fail(self) -> None:
        self.failures += 1
        if self.state == CircuitState.HALF_OPEN or self.failures >= self.failures_needed:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()
            slog("HEAL", "circuit open", failures=self.failures)
