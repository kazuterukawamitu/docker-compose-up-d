"""Runtime recovery only. Never rewrites source. Never retries order POST."""

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


class HealAction(str, Enum):
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
class Heartbeats:
    last_loop_at: float = 0.0
    last_ticker_at: float = 0.0
    last_candle_at: float = 0.0
    last_ws_at: float = 0.0
    last_rest_at: float = 0.0
    last_strategy_at: float = 0.0
    last_order_check_at: float = 0.0
    last_balance_at: float = 0.0


@dataclass
class CircuitBreaker:
    failures: int = 0
    opened_at: float = 0.0
    state: CircuitState = CircuitState.CLOSED
    threshold: int = 5
    cooloff_sec: float = 30.0

    def allow(self) -> bool:
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.opened_at >= self.cooloff_sec:
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def success(self) -> None:
        self.failures = 0
        self.state = CircuitState.CLOSED

    def failure(self) -> None:
        self.failures += 1
        if self.failures >= self.threshold:
            self.state = CircuitState.OPEN
            self.opened_at = time.monotonic()


@dataclass
class TaskRecord:
    restarts: int = 0
    last_crash: float = 0.0
    quarantined: bool = False


@dataclass
class SelfHealingEngine:
    circuit: CircuitBreaker = field(default_factory=CircuitBreaker)
    beats: Heartbeats = field(default_factory=Heartbeats)
    tasks: dict[str, TaskRecord] = field(default_factory=dict)
    consecutive_fatal: int = 0

    def classify(self, exc: BaseException) -> ErrorClass:
        if isinstance(exc, BitbankAPIError) and is_auth_error(exc):
            return ErrorClass.FATAL
        if isinstance(exc, (TimeoutError, ConnectionError)):
            return ErrorClass.TRANSIENT
        name = type(exc).__name__
        if name in {"HTTPError", "ConnectError", "ReadTimeout", "NetworkError"}:
            return ErrorClass.TRANSIENT
        if isinstance(exc, BitbankAPIError):
            if exc.http_status in {429, 500, 502, 503, 504}:
                return ErrorClass.RECOVERABLE
            return ErrorClass.RECOVERABLE
        return ErrorClass.RECOVERABLE

    def action_for(self, klass: ErrorClass) -> HealAction:
        if klass == ErrorClass.TRANSIENT:
            return HealAction.RETRY
        if klass == ErrorClass.RECOVERABLE:
            return HealAction.RECONNECT
        if klass == ErrorClass.STATE_ERROR:
            return HealAction.RECONCILE
        return HealAction.STOP

    def backoff(self, attempt: int, cap: float = 16.0) -> float:
        base = min(cap, 1.0 * (2**max(0, attempt)))
        return base + random.uniform(0, base * 0.25)

    def note(self, field_name: str) -> None:
        setattr(self.beats, field_name, time.monotonic())

    def stale(self, field_name: str, limit_sec: float) -> bool:
        stamp = float(getattr(self.beats, field_name) or 0.0)
        if stamp <= 0:
            return False
        return (time.monotonic() - stamp) > limit_sec

    def record_task_crash(self, name: str, limit: int = 5, window_sec: float = 120.0) -> HealAction:
        rec = self.tasks.setdefault(name, TaskRecord())
        now = time.monotonic()
        if rec.quarantined:
            return HealAction.QUARANTINE
        if now - rec.last_crash > window_sec:
            rec.restarts = 0
        rec.restarts += 1
        rec.last_crash = now
        if rec.restarts >= limit:
            rec.quarantined = True
            slog("WATCHDOG", "task quarantined", task=name, restarts=rec.restarts)
            return HealAction.QUARANTINE
        slog("WATCHDOG", "task restart", task=name, restarts=rec.restarts)
        return HealAction.RESTART_TASK

    def handle_loop_error(
        self,
        exc: BaseException,
        *,
        reconnect: Callable[[], None] | None = None,
    ) -> HealAction:
        klass = self.classify(exc)
        action = self.action_for(klass)
        slog(
            "ERROR",
            "self-heal",
            error=type(exc).__name__,
            klass=klass.value,
            action=action.value,
        )
        if action == HealAction.RECONNECT and reconnect is not None:
            reconnect()
        if klass == ErrorClass.FATAL:
            self.consecutive_fatal += 1
        else:
            self.consecutive_fatal = 0
        self.circuit.failure()
        return action

    def optional_sentry(self, dsn: str) -> None:
        if not dsn:
            return
        try:
            import sentry_sdk
        except ImportError:
            slog("BOOT", "sentry-sdk not installed; continuing without Sentry")
            return
        sentry_sdk.init(
            dsn=dsn,
            send_default_pii=False,
            before_send=_sentry_strip_secrets,
        )
        sentry_sdk.set_tag("exchange", "bitbank")
        sentry_sdk.set_tag("pair", "btc_jpy")
        slog("BOOT", "Sentry enabled (secrets stripped)")


def _sentry_strip_secrets(event: dict, _hint: object) -> dict | None:
    text = str(event)
    lowered = text.lower()
    if "api_secret" in lowered or "access-signature" in lowered or "authorization" in lowered:
        return None
    return event
