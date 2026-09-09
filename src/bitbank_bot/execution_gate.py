"""Last checks before OrderExecutor. Failures log EXECUTION_BLOCKED with a reason."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import ZERO
from bitbank_bot.rate_engine import RateDecision
from bitbank_bot.strategy import Signal


@dataclass
class GateContext:
    signal: Signal
    market_data_real: bool
    market_data_fresh: bool
    private_api_ok: bool
    balance_ok: bool
    amount_ok: bool
    amount: Decimal
    kill_switch: bool
    pending_order: bool
    cooldown_active: bool
    open_order_conflict: bool
    ws_stale: bool
    explicit_synthetic: bool
    rate: RateDecision | None = None
    extra_reason: str = ""


@dataclass
class GateDecision:
    allowed: bool
    reason: str
    checks: dict[str, bool] = field(default_factory=dict)


class ExecutionGate:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def evaluate(self, ctx: GateContext) -> GateDecision:
        mode = self.cfg.resolved_trading_mode()
        live = self.cfg.may_place_live_orders
        checks = {
            "signal_valid": ctx.signal.side in {"buy", "sell"} and bool(ctx.signal.kind),
            "kill_switch_clear": not ctx.kill_switch,
            "no_pending": not ctx.pending_order,
            "cooldown_clear": not ctx.cooldown_active,
            "no_open_conflict": not ctx.open_order_conflict,
            "market_data_fresh": ctx.market_data_fresh,
            "not_ws_stale": not ctx.ws_stale,
            "signal_only_off": not self.cfg.signal_only,
        }
        if live:
            checks["trading_mode_live"] = mode == "live"
            checks["live_confirmation"] = self.cfg.live_trading_confirm
            checks["market_data_real"] = ctx.market_data_real
            checks["private_api_ok"] = ctx.private_api_ok
            checks["balance_ok"] = ctx.balance_ok
            checks["amount_valid"] = ctx.amount_ok and ctx.amount > ZERO
        elif mode == "live_ready":
            checks["trading_mode_live_ready"] = True
            checks["market_data_real"] = ctx.market_data_real or ctx.explicit_synthetic
            checks["amount_valid"] = ctx.amount_ok and ctx.amount > ZERO
        else:
            checks["dry_run_or_paper"] = True
            if not ctx.explicit_synthetic:
                checks["market_data_usable"] = ctx.market_data_real or not live

        if ctx.rate is not None and not ctx.rate.ok:
            checks["rate_ok"] = False
        if ctx.extra_reason:
            checks[ctx.extra_reason] = False
        if (
            self.cfg.range_suppress_buys
            and ctx.signal.side == "buy"
            and ctx.rate is not None
            and ctx.rate.market_regime == "RANGE"
        ):
            checks["range_allows_buy"] = False

        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            reason = failed[0]
            slog("EXECUTION_BLOCKED", "order gated", reason=reason, checks=checks)
            return GateDecision(False, reason, checks)
        slog("RISK_CHECK_PASSED", "execution gate open", mode=mode, side=ctx.signal.side)
        return GateDecision(True, "ok", checks)
