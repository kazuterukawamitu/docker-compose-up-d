"""Single pre-order gate. Failures log EXECUTION_BLOCKED; never silent HOLD."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.config import MODE_DRY_RUN, MODE_LIVE, MODE_LIVE_READY, Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import ZERO, meets_min_amount
from bitbank_bot.strategy import Signal


@dataclass(frozen=True)
class GateDecision:
    ok: bool
    reason: str
    live_submit: bool
    would_submit: bool


class ExecutionGate:
    """Checks that must pass before OrderExecutor.submit_order runs."""

    def evaluate(
        self,
        *,
        cfg: Config,
        signal: Signal,
        market_data_real: bool,
        market_data_fresh: bool,
        private_api_ok: bool,
        balance_ok: bool,
        risk_ok: bool,
        risk_reason: str,
        kill_switch: bool,
        amount: Decimal,
        price: Decimal,
        duplicate: bool,
        open_order_conflict: bool,
        atr_ok: bool,
        connection_ok: bool,
        recon_ok: bool,
        quarantined: bool,
        unknown_order: bool,
    ) -> GateDecision:
        live = cfg.may_place_live_orders
        would = cfg.trading_mode in {MODE_DRY_RUN, MODE_LIVE_READY, MODE_LIVE}
        checks: list[tuple[bool, str]] = [
            (signal.side in {"buy", "sell"}, "signal_invalid"),
            (bool(signal.kind and signal.reason), "signal_invalid"),
            (market_data_real, "synthetic_market_data"),
            (market_data_fresh, "stale_market_data"),
            (atr_ok, "abnormal_atr"),
            (connection_ok, "api_disconnect"),
            (recon_ok, "reconcile_ambiguous"),
            (not quarantined, "quarantined"),
            (not unknown_order, "unknown_order_status"),
            (not kill_switch, "kill_switch"),
            (risk_ok, risk_reason or "risk_blocked"),
            (balance_ok, "insufficient_balance"),
            (price > ZERO, "invalid_price"),
            (meets_min_amount(amount, cfg.min_amount_btc), "amount_below_minimum"),
            (not duplicate, "duplicate_order"),
            (not open_order_conflict, "open_order_conflict"),
        ]
        if cfg.trading_mode == MODE_LIVE:
            checks.append((cfg.live_trading_confirmed, "live_confirmation"))
            checks.append((cfg.has_keys, "private_api_missing_keys"))
            checks.append((private_api_ok, "private_api_not_ok"))
            checks.append((live, "live_not_authorized"))
        for passed, reason in checks:
            if not passed:
                slog("EXECUTION_BLOCKED", "execution blocked", reason=reason, side=signal.side)
                return GateDecision(False, reason, False, False)
        if cfg.trading_mode == MODE_LIVE and live:
            return GateDecision(True, "ok", True, True)
        if cfg.trading_mode == MODE_LIVE_READY:
            return GateDecision(True, "live_ready_would_submit", False, True)
        if cfg.trading_mode == MODE_DRY_RUN:
            return GateDecision(True, "dry_run_would_submit", False, True)
        slog("EXECUTION_BLOCKED", "execution blocked", reason="trading_mode")
        return GateDecision(False, "trading_mode", False, False)
