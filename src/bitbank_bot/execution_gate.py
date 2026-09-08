"""Last checks before Bitbank create_order. Never silent-HOLD on failure."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO, meets_min_amount
from bitbank_bot.strategy import Signal


@dataclass
class GateResult:
    allowed: bool
    reason: str
    checks: dict[str, bool] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.allowed


def evaluate_gate(
    *,
    cfg: Config,
    signal: Signal,
    market_data_real: bool,
    market_data_fresh: bool,
    private_api_ok: bool,
    balance_ok: bool,
    amount: Decimal,
    kill_switch: bool,
    duplicate_order: bool,
    cooldown: bool,
    open_order_conflict: bool,
    connection_ok: bool,
    atr_ok: bool = True,
    explicit_synthetic: bool = False,
    require_live_for_submit: bool = False,
) -> GateResult:
    checks = {
        "signal_valid": signal.side in {"buy", "sell"} and bool(signal.reason),
        "side_buy_or_sell": signal.side in {"buy", "sell"},
        "kill_switch_off": not kill_switch,
        "market_data_real": bool(market_data_real or explicit_synthetic),
        "market_data_fresh": market_data_fresh,
        "private_api_ok": private_api_ok or cfg.dry_run or not cfg.has_keys,
        "balance_ok": balance_ok,
        "amount_valid": meets_min_amount(amount, cfg.min_amount_btc),
        "duplicate_order_free": not duplicate_order,
        "cooldown_clear": not cooldown,
        "open_order_free": not open_order_conflict,
        "connection_ok": connection_ok,
        "atr_ok": atr_ok,
        "not_synthetic_live": not (
            (not market_data_real)
            and (not explicit_synthetic)
            and (cfg.may_place_live_orders or cfg.trading_mode == "live_ready")
        ),
    }
    if require_live_for_submit:
        checks["trading_mode_live"] = cfg.may_place_live_orders
        checks["live_confirm"] = cfg.live_confirm
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        reason = failed[0]
        slog("EXECUTION_BLOCKED", "execution blocked", reason=reason, failed=",".join(failed))
        slog("TRADE_BLOCKED", "trade blocked", reason=reason)
        return GateResult(False, reason, checks)
    slog("RISK_CHECK_PASSED", "execution gate passed", side=signal.side, kind=signal.kind)
    return GateResult(True, "ok", checks)


def block_reason_from_mode(cfg: Config) -> str | None:
    if cfg.dry_run:
        return "dry_run"
    if cfg.trading_mode == "live_ready":
        return "live_ready"
    if not cfg.may_place_live_orders:
        return "live_blocked"
    return None
