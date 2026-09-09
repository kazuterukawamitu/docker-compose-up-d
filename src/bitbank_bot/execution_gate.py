"""Single pre-order gate. Never places an order; only allows or blocks."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO, meets_min_amount
from bitbank_bot.rate_engine import RateDecision
from bitbank_bot.strategy import Signal


@dataclass
class GateContext:
    market_data_real: bool
    market_data_fresh: bool
    private_api_ok: bool
    balance_ok: bool
    kill_switch: bool
    amount: Decimal
    duplicate_order: bool
    open_order_conflict: bool
    cooldown: bool = False
    connection_healthy: bool = True
    stale_price: bool = False
    synthetic: bool = False
    signal_valid: bool = True


@dataclass
class GateResult:
    allowed: bool
    reason: str
    would_submit: bool
    proceed: bool
    checks: dict[str, bool] = field(default_factory=dict)


def evaluate_gate(
    cfg: Config,
    signal: Signal,
    rate: RateDecision,
    ctx: GateContext,
) -> GateResult:
    checks: dict[str, bool] = {
        "signal_side": signal.side in {"buy", "sell"},
        "signal_valid": ctx.signal_valid and bool(signal.reason),
        "rate_ok": rate.ok,
        "market_data_real": ctx.market_data_real,
        "market_data_fresh": ctx.market_data_fresh,
        "not_synthetic": not ctx.synthetic,
        "not_stale_price": not ctx.stale_price,
        "private_api_ok": ctx.private_api_ok or cfg.dry_run or cfg.live_ready,
        "balance_ok": ctx.balance_ok,
        "kill_switch_off": not ctx.kill_switch,
        "amount_valid": meets_min_amount(ctx.amount, cfg.min_amount_btc),
        "duplicate_order": not ctx.duplicate_order,
        "open_order_conflict": not ctx.open_order_conflict,
        "cooldown_clear": not ctx.cooldown,
        "connection_healthy": ctx.connection_healthy,
    }
    if cfg.dry_run:
        checks["trading_mode"] = True
    elif cfg.live_ready:
        checks["trading_mode"] = True
    else:
        checks["trading_mode"] = cfg.may_place_live_orders
        checks["live_confirmation"] = cfg.live_trading_confirm or cfg.may_place_live_orders

    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        reason = failed[0]
        if reason == "not_synthetic":
            reason = "synthetic_market_data"
        elif reason == "market_data_real":
            reason = "synthetic_market_data"
        elif reason == "amount_valid":
            reason = "amount_below_minimum"
        elif reason == "kill_switch_off":
            reason = "kill_switch"
        elif reason == "trading_mode" and cfg.dry_run:
            reason = "dry_run"
        slog("EXECUTION_BLOCKED", "TRADE_BLOCKED", reason=reason, failed=",".join(failed))
        return GateResult(False, reason, False, False, checks)

    if cfg.dry_run:
        slog("TRADE_BLOCKED", "DRY_RUN; paper path only", reason="dry_run")
        return GateResult(False, "dry_run", False, True, checks)
    if cfg.live_ready or not cfg.may_place_live_orders:
        slog(
            "WOULD_SUBMIT_ORDER",
            "LIVE_READY; Bitbank create_order not called",
            side=signal.side,
            amount=str(ctx.amount),
        )
        return GateResult(False, "live_ready", True, True, checks)
    slog("RISK_CHECK_PASSED", "execution gate open", side=signal.side, amount=str(ctx.amount))
    return GateResult(True, "ok", False, True, checks)


def stale_price_deviation(close: Decimal, ticker: Decimal | None, limit: Decimal) -> bool:
    if ticker is None or close <= ZERO:
        return False
    ticker = D(ticker)
    if ticker <= ZERO:
        return False
    return abs(ticker - close) / close > D(limit)
