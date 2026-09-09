"""Last-line checks before any Bitbank order POST."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.connection_manager import ConnectionSnapshot
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO, meets_min_amount
from bitbank_bot.rate_engine import RateDecision
from bitbank_bot.strategy import Signal
from bitbank_bot.trading_mode import TradingMode


@dataclass
class GateResult:
    allowed: bool
    reason: str
    would_submit: bool
    checks: dict[str, bool] = field(default_factory=dict)

    @property
    def blocked(self) -> bool:
        return not self.allowed


def _side_ok(signal: Signal) -> bool:
    return signal.side in {"buy", "sell"} and signal.kind != "HOLD"


class ExecutionGate:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def evaluate(
        self,
        *,
        signal: Signal,
        amount: Decimal,
        price: Decimal,
        market_data_real: bool,
        market_data_fresh: bool,
        connection: ConnectionSnapshot | None,
        private_api_ok: bool,
        balance_ok: bool,
        kill_switch: bool,
        pending_order: bool,
        rate: RateDecision | None = None,
        open_orders: int = 0,
    ) -> GateResult:
        mode = TradingMode(self.cfg.trading_mode)
        checks = {
            "trading_mode_not_dry_run": mode is not TradingMode.DRY_RUN,
            "live_confirmation": bool(self.cfg.live_trading_confirm) if mode is TradingMode.LIVE else True,
            "market_data_real": market_data_real,
            "market_data_fresh": market_data_fresh,
            "private_api_ok": private_api_ok if mode is TradingMode.LIVE else True,
            "balance_ok": balance_ok,
            "signal_valid": _side_ok(signal),
            "side_buy_or_sell": signal.side in {"buy", "sell"},
            "kill_switch_off": not kill_switch,
            "amount_valid": meets_min_amount(amount, self.cfg.min_amount_btc),
            "price_valid": D(price) > ZERO,
            "duplicate_order_false": not pending_order,
            "open_order_conflict_false": open_orders <= 0,
            "rate_ok": True if rate is None else bool(rate.ok),
        }
        if connection is not None:
            # A never-used manager is not a REST failure; only stale known REST blocks.
            if connection.last_rest_success_at > 0:
                checks["rest_ok"] = connection.rest_ok
            checks["ws_not_blocking"] = (not connection.ws_stale) or connection.rest_ok or connection.last_rest_success_at <= 0
        failed = [name for name, ok in checks.items() if not ok]
        if failed:
            reason = failed[0]
            slog("EXECUTION_BLOCKED", "gate failed", reason=reason, failed=",".join(failed), **checks)
            slog("TRADE_BLOCKED", f"reason={reason}", kind=signal.kind, side=signal.side)
            return GateResult(False, reason, False, checks)
        if mode is TradingMode.LIVE_READY:
            slog(
                "WOULD_SUBMIT_ORDER",
                "LIVE_READY: full path, no Bitbank POST",
                pair=self.cfg.pair,
                side=signal.side,
                amount=str(amount),
                price=str(price),
                kind=signal.kind,
            )
            return GateResult(False, "live_ready", True, checks)
        if mode is TradingMode.DRY_RUN:
            slog("TRADE_BLOCKED", "reason=DRY_RUN", kind=signal.kind, side=signal.side)
            return GateResult(False, "dry_run", False, checks)
        if mode is TradingMode.LIVE and self.cfg.may_place_live_orders:
            slog("RISK_CHECK_PASSED", "execution gate open", kind=signal.kind, side=signal.side)
            return GateResult(True, "ok", False, checks)
        slog("EXECUTION_BLOCKED", "gate failed", reason="live_not_confirmed")
        return GateResult(False, "live_not_confirmed", False, checks)
