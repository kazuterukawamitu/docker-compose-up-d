"""Self-healing runtime: classify, retry GET, circuit-break, quarantine, kill.

Does not restart a crashing loop blindly. Order POST is never retried here.
"""

from __future__ import annotations

import random
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, TypeVar

from bitbank_bot.logging_setup import slog

T = TypeVar("T")


class ErrorClass(str, Enum):
    TRANSIENT = "TRANSIENT"
    RECOVERABLE = "RECOVERABLE"
    STATE_ERROR = "STATE_ERROR"
    FATAL = "FATAL"


class BreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


TRANSIENT_NAMES = frozenset(
    {
        "TimeoutException",
        "ConnectError",
        "ReadTimeout",
        "WriteTimeout",
        "NetworkError",
        "RemoteProtocolError",
        "TransportError",
    }
)
STATE_NAMES = frozenset({"OrderSubmitUncertain", "ReconcileError"})
FATAL_NAMES = frozenset({"KeyboardInterrupt", "SystemExit"})


@dataclass
class ErrorRecord:
    name: str
    message: str
    function: str
    classification: ErrorClass
    when: float
    pair: str = ""
    endpoint: str = ""
    retry: int = 0


class ErrorClassifier:
    def classify(self, exc: BaseException) -> ErrorClass:
        name = type(exc).__name__
        if name in FATAL_NAMES:
            return ErrorClass.FATAL
        if name in STATE_NAMES:
            return ErrorClass.STATE_ERROR
        if name in TRANSIENT_NAMES or "timeout" in name.lower() or name == "BitbankAPIError":
            code = getattr(exc, "http_status", None)
            if code in {429, 500, 502, 503, 504} or code is None:
                return ErrorClass.TRANSIENT
            if code in {401, 403}:
                return ErrorClass.FATAL
            return ErrorClass.RECOVERABLE
        return ErrorClass.RECOVERABLE


class ErrorCollector:
    def __init__(self, limit: int = 50) -> None:
        self._items: deque[ErrorRecord] = deque(maxlen=limit)

    def add(self, record: ErrorRecord) -> None:
        self._items.append(record)
        slog(
            "ERROR",
            "collected",
            error=record.name,
            detail=record.message[:200],
            function=record.function,
            classification=record.classification.value,
            pair=record.pair or None,
            endpoint=record.endpoint or None,
            retry=record.retry,
        )

    def recent(self) -> list[ErrorRecord]:
        return list(self._items)


class RetryManager:
    """GET-only retries with exponential backoff and jitter."""

    def __init__(self, max_attempts: int = 5, cap: float = 16.0) -> None:
        self.max_attempts = max_attempts
        self.cap = cap

    def sleep_seconds(self, attempt: int) -> float:
        base = min(self.cap, 0.4 * (2 ** max(0, attempt)))
        return base + random.uniform(0, base * 0.3)

    def call_get(self, fn: Callable[[], T], *, label: str) -> T:
        last: BaseException | None = None
        for attempt in range(self.max_attempts):
            try:
                return fn()
            except Exception as exc:
                last = exc
                if attempt + 1 >= self.max_attempts:
                    break
                delay = self.sleep_seconds(attempt)
                slog(
                    "ERROR",
                    "GET retry",
                    function=label,
                    error=type(exc).__name__,
                    retry=attempt + 1,
                    delay=round(delay, 3),
                )
                time.sleep(delay)
        assert last is not None
        raise last


class CircuitBreaker:
    def __init__(self, failures: int = 5, reset_sec: float = 30.0) -> None:
        self.failures_needed = failures
        self.reset_sec = reset_sec
        self.state = BreakerState.CLOSED
        self._fails = 0
        self._opened_at = 0.0

    def allow(self) -> bool:
        if self.state == BreakerState.CLOSED:
            return True
        if self.state == BreakerState.OPEN:
            if time.monotonic() - self._opened_at >= self.reset_sec:
                self.state = BreakerState.HALF_OPEN
                slog("WATCHDOG", "circuit HALF_OPEN")
                return True
            return False
        return True

    def success(self) -> None:
        self._fails = 0
        if self.state != BreakerState.CLOSED:
            slog("WATCHDOG", "circuit CLOSED")
        self.state = BreakerState.CLOSED

    def failure(self) -> None:
        self._fails += 1
        if self.state == BreakerState.HALF_OPEN or self._fails >= self.failures_needed:
            self.state = BreakerState.OPEN
            self._opened_at = time.monotonic()
            slog("WATCHDOG", "circuit OPEN", fails=self._fails)


class QuarantineManager:
    def __init__(self) -> None:
        self._names: set[str] = set()

    def quarantine(self, name: str, reason: str) -> None:
        self._names.add(name)
        slog("WATCHDOG", "quarantine", task=name, reason=reason)

    def is_quarantined(self, name: str) -> bool:
        return name in self._names

    def any(self) -> bool:
        return bool(self._names)


class KillSwitch:
    def __init__(self, path: str) -> None:
        self.path = path
        self.latched = False

    def tripped(self, cfg_flag: bool = False) -> bool:
        if cfg_flag or self.latched or Path(self.path).exists():
            return True
        return False

    def latch(self, reason: str) -> None:
        self.latched = True
        slog("RISK", "kill switch latched", reason=reason)


class TaskSupervisor:
    def __init__(self, crash_limit: int = 3) -> None:
        self.crash_limit = crash_limit
        self.crashes = 0

    def note_success(self) -> None:
        self.crashes = 0

    def note_crash(self, exc: BaseException) -> bool:
        """Return True if the task should be quarantined (do not keep restarting)."""
        self.crashes += 1
        slog(
            "ERROR",
            "task crash",
            error=type(exc).__name__,
            detail=str(exc)[:200],
            function="trading_loop",
            retry=self.crashes,
        )
        return self.crashes >= self.crash_limit


@dataclass
class Heartbeats:
    last_trading_loop: float = 0.0
    last_ticker: float = 0.0
    last_candle: float = 0.0
    last_ws: float = 0.0
    last_rest: float = 0.0
    last_strategy: float = 0.0
    last_order_check: float = 0.0
    last_balance_sync: float = 0.0

    def touch(self, name: str) -> None:
        now = time.monotonic()
        if hasattr(self, f"last_{name}"):
            setattr(self, f"last_{name}", now)

    def age(self, name: str) -> float | None:
        stamp = getattr(self, f"last_{name}", 0.0)
        if stamp <= 0:
            return None
        return time.monotonic() - stamp


@dataclass
class SelfHealingRuntime:
    collector: ErrorCollector = field(default_factory=ErrorCollector)
    classifier: ErrorClassifier = field(default_factory=ErrorClassifier)
    retries: RetryManager = field(default_factory=RetryManager)
    breaker: CircuitBreaker = field(default_factory=CircuitBreaker)
    quarantine: QuarantineManager = field(default_factory=QuarantineManager)
    supervisor: TaskSupervisor = field(default_factory=TaskSupervisor)
    kill: KillSwitch = field(default_factory=lambda: KillSwitch("data/KILL"))
    beats: Heartbeats = field(default_factory=Heartbeats)

    def record(
        self,
        exc: BaseException,
        *,
        function: str,
        pair: str = "",
        endpoint: str = "",
        retry: int = 0,
    ) -> ErrorClass:
        klass = self.classifier.classify(exc)
        self.collector.add(
            ErrorRecord(
                type(exc).__name__,
                str(exc),
                function,
                klass,
                time.monotonic(),
                pair=pair,
                endpoint=endpoint,
                retry=retry,
            )
        )
        if klass is ErrorClass.FATAL:
            self.kill.latch(type(exc).__name__)
        return klass
