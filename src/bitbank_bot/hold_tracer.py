"""Map HOLD / block reasons to a stable ROOT_CAUSE for 15-minute stalls."""

from __future__ import annotations

from bitbank_bot.strategy import Signal

ROOT_CAUSES = {
    "no_buy_setup": "NO_SETUP",
    "no_sell_setup": "NO_SETUP",
    "in_position_no_sell_or_tp": "POSITION_BLOCK",
    "same_entry_candle_no_sell": "POSITION_BLOCK",
    "tp_not_hit": "NO_SETUP",
    "not_enough_candles": "NO_MARKET_DATA",
    "synthetic_fallback_no_orders": "SYNTHETIC_DATA_BLOCK",
    "synthetic_market_data": "SYNTHETIC_DATA_BLOCK",
    "stale_market_data": "STALE_MARKET_DATA",
    "stale_websocket": "WEBSOCKET_STALE",
    "pending_order": "ACTIVE_ORDER_BLOCK",
    "ACTIVE_ORDER_EXISTS": "ACTIVE_ORDER_BLOCK",
    "active_orders": "ACTIVE_ORDER_BLOCK",
    "SIGNAL_ONLY": "SIGNAL_ONLY_BLOCK",
    "KILL_SWITCH": "RISK_BLOCK",
    "kill_switch": "RISK_BLOCK",
    "htf_downtrend": "RISK_BLOCK",
    "htf_unavailable": "RISK_BLOCK",
    "INSUFFICIENT_BALANCE": "INSUFFICIENT_BALANCE",
    "insufficient": "INSUFFICIENT_BALANCE",
    "below_min_amount": "INSUFFICIENT_BALANCE",
    "MIN_AMOUNT": "INSUFFICIENT_BALANCE",
    "auth_failure": "API_AUTH_FAILURE",
    "balance_fetch_failed": "API_AUTH_FAILURE",
    "atr_invalid": "RISK_BLOCK",
    "circuit_breaker": "RISK_BLOCK",
    "max_daily_loss": "RISK_BLOCK",
    "max_drawdown": "RISK_BLOCK",
    "max_position": "POSITION_BLOCK",
}


def root_cause(
    signal: Signal,
    *,
    block_reason: str = "",
    synthetic_fallback: bool = False,
    dry_run: bool = True,
) -> str:
    if synthetic_fallback:
        return "SYNTHETIC_DATA_BLOCK"
    for raw in (block_reason, signal.reason, signal.kind):
        if raw in ROOT_CAUSES:
            return ROOT_CAUSES[raw]
    if signal.side in {"buy", "sell"} and block_reason:
        return "ORDER_REQUEST_NOT_CALLED"
    if signal.kind == "HOLD":
        return "NO_SETUP"
    if dry_run:
        return "DRY_RUN_BLOCK"
    return "UNKNOWN"
