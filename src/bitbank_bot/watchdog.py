"""15-minute watchdog: distinguish healthy WAIT from a stalled bot.

Never sleeps for the timeout and never forces a trade.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

WatchStatus = Literal["OK", "NORMAL_WAIT", "LONG_WAIT", "FAIL"]


@dataclass(frozen=True)
class WatchInput:
    now_ms: int
    started_ms: int
    timeout_ms: int
    stale_ms: int
    last_market_data_ms: int
    strategy_evaluations: int
    buy_signals: int
    sell_signals: int
    order_attempts: int
    last_signal_kind: str
    last_signal_reason: str
    last_error: str
    last_block_reason: str
    ws_ok: bool


def diagnose(inp: WatchInput) -> tuple[WatchStatus, str]:
    uptime = max(0, inp.now_ms - inp.started_ms)
    timed_out = uptime >= inp.timeout_ms
    market_age = (
        None
        if inp.last_market_data_ms <= 0
        else max(0, inp.now_ms - inp.last_market_data_ms)
    )
    action = inp.last_signal_kind or "n/a"

    if inp.last_market_data_ms <= 0:
        if timed_out:
            return "FAIL", "market data never received"
        return "OK", "waiting for first market data"

    if market_age is not None and market_age > inp.stale_ms:
        if timed_out:
            return "FAIL", f"MARKET_DATA_STALE age_ms={market_age} ws_ok={inp.ws_ok}"
        return "OK", f"market data aging age_ms={market_age}"

    if inp.strategy_evaluations == 0:
        if timed_out:
            return "FAIL", "strategy has never been executed"
        return "OK", "strategy not yet evaluated"

    if (inp.buy_signals > 0 or inp.sell_signals > 0) and inp.order_attempts == 0:
        if inp.last_block_reason:
            if timed_out:
                return "LONG_WAIT", f"signal blocked: {inp.last_block_reason}"
            return "OK", f"signal blocked: {inp.last_block_reason}"
        if timed_out:
            return (
                "FAIL",
                "BUY/SELL signal generated but OrderManager was never called "
                f"buy={inp.buy_signals} sell={inp.sell_signals}",
            )
        return "OK", "signal pending order path"

    if timed_out:
        extra = f" last_error={inp.last_error}" if inp.last_error else ""
        return "LONG_WAIT", f"Market conditions not met last_signal={action}{extra}"

    if action in {"HOLD", "n/a"}:
        return "NORMAL_WAIT", f"conditions not met reason={inp.last_signal_reason or 'n/a'}"
    return "OK", f"last_signal={action}"
