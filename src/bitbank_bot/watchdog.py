"""15-minute trade watchdog plus a runtime thread for stale subsystems.

HOLD for 15 minutes is not a failure when market data, strategy, and
risk are healthy. FAIL is reserved for stalled subsystems. The runtime
thread never writes source and never posts orders.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

from bitbank_bot.logging_setup import slog


NORMAL_WAIT = "NORMAL WAIT"
LONG_WAIT = "LONG_WAIT"
FAIL = "FAIL"
SIGNAL = "SIGNAL"


@dataclass(frozen=True)
class WatchdogReport:
    status: str
    reason: str
    uptime_sec: int


def classify(
    *,
    uptime_sec: int,
    timeout_sec: int,
    strategy_evaluations: int,
    market_ok: bool,
    fail_reason: str = "",
    has_order_signal: bool = False,
) -> WatchdogReport:
    """Classify bot health after each loop.

    ``timeout_sec`` defaults to 900 (15 minutes). Crossing it with a
    healthy HOLD becomes LONG_WAIT, not FAIL.
    """
    if fail_reason:
        return WatchdogReport(FAIL, fail_reason, uptime_sec)
    if not market_ok:
        return WatchdogReport(FAIL, "market_data_stale_or_missing", uptime_sec)
    if strategy_evaluations <= 0 and uptime_sec >= timeout_sec:
        return WatchdogReport(FAIL, "strategy_never_executed", uptime_sec)
    if has_order_signal:
        return WatchdogReport(SIGNAL, "buy_or_sell_signal", uptime_sec)
    if uptime_sec >= timeout_sec:
        return WatchdogReport(LONG_WAIT, "market_conditions_not_met", uptime_sec)
    return WatchdogReport(NORMAL_WAIT, "waiting_for_setup", uptime_sec)


class RuntimeWatchdog:
    """Separate daemon thread. Observes health stamps; does not place orders."""

    def __init__(
        self,
        health: object,
        *,
        stale_sec: float = 60.0,
        interval_sec: float = 5.0,
        on_recover: Callable[[list[str]], None] | None = None,
    ) -> None:
        self.health = health
        self.stale_sec = stale_sec
        self.interval_sec = interval_sec
        self.on_recover = on_recover
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_findings: list[str] = []

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="bitbank-watchdog", daemon=True
        )
        self._thread.start()
        slog("WATCHDOG", "runtime thread started", stale_sec=self.stale_sec)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def inspect(self, now: float | None = None) -> list[str]:
        now = time.monotonic() if now is None else now
        findings: list[str] = []
        for name in (
            "last_loop_at",
            "last_ticker_at",
            "last_candle_at",
            "last_ws_at",
            "last_rest_at",
            "last_strategy_at",
            "last_order_check_at",
            "last_balance_at",
        ):
            stamp = float(getattr(self.health, name, 0.0) or 0.0)
            if stamp <= 0:
                continue
            age = now - stamp
            if age > self.stale_sec:
                short = name.replace("last_", "").replace("_at", "")
                findings.append(short)
                slog(
                    "WATCHDOG",
                    "stale subsystem",
                    subsystem=short,
                    age_sec=round(age, 1),
                )
        self.last_findings = findings
        return findings

    def _run(self) -> None:
        while not self._stop.wait(self.interval_sec):
            findings = self.inspect()
            if findings and self.on_recover is not None:
                try:
                    self.on_recover(findings)
                except Exception as exc:
                    slog("WATCHDOG", "recover failed", error=type(exc).__name__)
