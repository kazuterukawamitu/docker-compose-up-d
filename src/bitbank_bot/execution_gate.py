"""Last checks before OrderExecutor. Failures log EXECUTION_BLOCKED / TRADE_BLOCKED."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from bitbank_bot.config import MODE_DRY_RUN, MODE_LIVE, MODE_LIVE_READY, Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import ZERO
from bitbank_bot.strategy import Signal


@dataclass
class GateContext:
    signal: Signal
    market_data_real: bool
    market_data_fresh: bool
    amount: Decimal
    amount_ok: bool
    kill_switch: bool
    pending_order: bool
    open_order_conflict: bool
    ws_stale: bool
    explicit_synthetic: bool
    ticker_mismatch: bool = False
    rate_ok: bool = True
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
            "no_open_conflict": not ctx.open_order_conflict,
            "market_data_fresh": ctx.market_data_fresh,
            "not_ws_stale": not ctx.ws_stale,
            "not_ticker_mismatch": not ctx.ticker_mismatch,
            "rate_ok": ctx.rate_ok,
            "amount_valid": ctx.amount_ok and ctx.amount > ZERO,
        }
        if live or mode == MODE_LIVE_READY:
            if ctx.explicit_synthetic:
                checks["market_data_real"] = True
            else:
                checks["market_data_real"] = ctx.market_data_real
        elif mode == MODE_DRY_RUN and not ctx.explicit_synthetic:
            checks["market_data_usable"] = ctx.market_data_real or ctx.explicit_synthetic
        if live:
            checks["trading_mode_live"] = mode == MODE_LIVE
            checks["live_confirmation"] = self.cfg.live_trading_confirm
        if ctx.extra_reason:
            checks[ctx.extra_reason] = False
        if not ctx.market_data_real and not ctx.explicit_synthetic:
            checks["market_data_real"] = False

        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            reason = failed[0]
            if reason in {"market_data_real", "market_data_usable"}:
                reason = "synthetic_market_data"
            elif reason == "market_data_fresh" or reason == "not_ticker_mismatch":
                reason = "STALE_MARKET_DATA"
            elif reason == "kill_switch_clear":
                reason = "kill_switch"
            slog(
                "EXECUTION_BLOCKED",
                "order gated",
                reason=reason,
                mode=mode,
                side=ctx.signal.side,
                checks=checks,
            )
            slog("TRADE_BLOCKED", "execution gate closed", reason=reason, mode=mode)
            return GateDecision(False, reason, checks)
        slog("RISK_CHECK_PASSED", "execution gate open", mode=mode, side=ctx.signal.side)
        return GateDecision(True, "ok", checks)
