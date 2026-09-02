"""15-minute trade watchdog: NORMAL WAIT vs LONG_WAIT vs FAIL.

HOLD for 15 minutes is not a failure when market data, strategy, and
risk are healthy. FAIL is reserved for stalled subsystems.
"""

from __future__ import annotations

from dataclasses import dataclass


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
