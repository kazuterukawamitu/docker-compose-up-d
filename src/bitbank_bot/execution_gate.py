"""Single pre-order checklist. Failures log EXECUTION_BLOCKED with a reason."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import ZERO
from bitbank_bot.strategy import Signal


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    reason: str


def evaluate(
    cfg: Config,
    signal: Signal,
    *,
    market_data_real: bool,
    market_data_fresh: bool,
    private_api_ok: bool,
    balance_ok: bool,
    amount_ok: bool,
    kill_switch: bool,
    duplicate_order: bool,
    open_order_conflict: bool,
    stale_websocket: bool,
) -> GateResult:
    checks: list[tuple[str, bool]] = [
        ("signal_only", not cfg.signal_only),
        ("kill_switch", not kill_switch),
        ("market_data_real", market_data_real),
        ("market_data_fresh", market_data_fresh),
        ("stale_websocket", not stale_websocket),
        ("signal_side", signal.side in {"buy", "sell"}),
        ("private_api_ok", private_api_ok or not cfg.may_place_live_orders),
        ("balance_ok", balance_ok),
        ("amount_ok", amount_ok),
        ("duplicate_order", not duplicate_order),
        ("open_order_conflict", not open_order_conflict),
    ]
    for name, ok in checks:
        if not ok:
            reason = {
                "signal_only": "SIGNAL_ONLY",
                "kill_switch": "KILL_SWITCH",
                "market_data_real": "synthetic_market_data",
                "market_data_fresh": "stale_market_data",
                "stale_websocket": "stale_websocket",
                "signal_side": "NO_VALID_SIGNAL",
                "private_api_ok": "API_UNHEALTHY",
                "balance_ok": "INSUFFICIENT_BALANCE",
                "amount_ok": "MIN_AMOUNT",
                "duplicate_order": "duplicate_order",
                "open_order_conflict": "ACTIVE_ORDER_EXISTS",
            }[name]
            slog("EXECUTION_BLOCKED", "TRADE_BLOCKED", reason=reason)
            return GateResult(False, reason)
    if cfg.trading_mode == "live_ready" or not cfg.may_place_live_orders:
        if cfg.dry_run and cfg.trading_mode != "live_ready" and cfg.simulate_fill:
            return GateResult(True, "dry_run_simulate")
        slog(
            "WOULD_SUBMIT_ORDER",
            "LIVE_READY or DRY_RUN: not calling Bitbank create_order",
            trading_mode=cfg.trading_mode,
            dry_run=cfg.dry_run,
            live_trading=cfg.live_trading,
            side=signal.side,
        )
        return GateResult(True, "would_submit")
    slog("RISK_CHECK_PASSED", "execution gate open", side=signal.side)
    return GateResult(True, "live")


def amount_valid(amount: Decimal, min_amount: Decimal) -> bool:
    return amount >= min_amount and amount > ZERO
