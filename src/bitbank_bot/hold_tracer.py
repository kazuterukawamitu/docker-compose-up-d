"""Classify why the bot stayed on HOLD / WAIT for 15 minutes."""

from __future__ import annotations

from dataclasses import dataclass

from bitbank_bot.logging_setup import slog

NO_MARKET_DATA = "NO_MARKET_DATA"
NO_SETUP = "NO_SETUP"
SIGNAL_ALWAYS_HOLD = "SIGNAL_ALWAYS_HOLD"
DRY_RUN_BLOCK = "DRY_RUN_BLOCK"
LIVE_READY_BLOCK = "LIVE_READY_BLOCK"
SYNTHETIC_DATA_BLOCK = "SYNTHETIC_DATA_BLOCK"
INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
ACTIVE_ORDER_BLOCK = "ACTIVE_ORDER_BLOCK"
POSITION_BLOCK = "POSITION_BLOCK"
RISK_BLOCK = "RISK_BLOCK"
HTF_BLOCK = "HTF_BLOCK"
STALE_DATA = "STALE_DATA"
API_AUTH_FAILURE = "API_AUTH_FAILURE"
ORDER_REQUEST_NOT_CALLED = "ORDER_REQUEST_NOT_CALLED"
UNKNOWN = "UNKNOWN"


@dataclass
class StallReport:
    status: str
    root_cause: str
    hold_seconds: int
    hold_count: int
    last_reason: str
    last_block: str


def classify_root_cause(
    *,
    signal_reason: str,
    block_reason: str,
    market_data_real: bool,
    trading_mode: str,
    signal_kind: str,
) -> str:
    block = (block_reason or "").lower()
    reason = (signal_reason or "").lower()
    if not market_data_real or "synthetic" in block:
        return SYNTHETIC_DATA_BLOCK
    if "stale" in block or "stale" in reason:
        return STALE_DATA
    if "auth" in block or "auth" in reason:
        return API_AUTH_FAILURE
    if block in {"kill_switch", "circuit_breaker", "max_drawdown", "daily_pnl_floor", "max_daily_loss"}:
        return RISK_BLOCK
    if "htf" in block or "htf" in reason:
        return HTF_BLOCK
    if "pending" in block or "active_order" in block:
        return ACTIVE_ORDER_BLOCK
    if block in {"insufficient", "below_min_amount", "amount_below_minimum"}:
        return INSUFFICIENT_BALANCE
    if "in_position" in reason or "same_entry" in reason:
        return POSITION_BLOCK
    if trading_mode == "live_ready" and signal_kind in {"BUY1", "BUY2", "BUY3", "BUY4", "SELL1", "SELL2", "SELL3", "SELL4", "TP"}:
        return LIVE_READY_BLOCK
    if trading_mode == "dry_run" and signal_kind not in {"HOLD"} and block in {"", "ok"}:
        return DRY_RUN_BLOCK
    if reason in {"no_buy_setup", "no_sell_setup", "tp_not_hit", "no_eval", "not_enough_candles"}:
        return NO_SETUP if reason != "not_enough_candles" else NO_MARKET_DATA
    if signal_kind == "HOLD":
        return SIGNAL_ALWAYS_HOLD
    if block:
        return ORDER_REQUEST_NOT_CALLED
    return UNKNOWN


class HoldTracer:
    def __init__(self) -> None:
        self.hold_count = 0
        self.action_count = 0
        self.last_reason = ""
        self.last_block = ""
        self.last_kind = "HOLD"
        self.last_root = UNKNOWN

    def note(
        self,
        *,
        signal_kind: str,
        signal_reason: str,
        block_reason: str,
        market_data_real: bool,
        trading_mode: str,
        uptime_sec: int,
        timeout_sec: int,
    ) -> StallReport | None:
        self.last_reason = signal_reason
        self.last_block = block_reason
        self.last_kind = signal_kind
        if signal_kind == "HOLD" or signal_kind in {"WAIT"}:
            self.hold_count += 1
        else:
            self.action_count += 1
        root = classify_root_cause(
            signal_reason=signal_reason,
            block_reason=block_reason,
            market_data_real=market_data_real,
            trading_mode=trading_mode,
            signal_kind=signal_kind,
        )
        self.last_root = root
        if uptime_sec < timeout_sec:
            return None
        if self.action_count > 0:
            return None
        report = StallReport(
            status="STALLED",
            root_cause=root,
            hold_seconds=uptime_sec,
            hold_count=self.hold_count,
            last_reason=signal_reason,
            last_block=block_reason,
        )
        slog(
            "WATCHDOG",
            "STATUS=STALLED",
            ROOT_CAUSE=root,
            HOLD_SECONDS=uptime_sec,
            HOLD_COUNT=self.hold_count,
            signal_reason=signal_reason,
            block_reason=block_reason,
        )
        return report
