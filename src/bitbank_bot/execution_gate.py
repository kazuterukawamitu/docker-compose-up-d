"""Single pre-order gate. Never silent HOLD: every block has a reason code."""

from __future__ import annotations

from dataclasses import dataclass

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.strategy import Signal

LIVE_SIDES = frozenset({"buy", "sell"})


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str
    live: bool
    would_submit: bool


def evaluate(
    cfg: Config,
    signal: Signal,
    *,
    market_data_real: bool,
    kill_switch: bool = False,
    pending_order: bool = False,
    private_api_ok: bool = True,
    amount_ok: bool = True,
    amount_reason: str = "ok",
) -> GateDecision:
    """Decide whether the Bitbank order POST may run.

    DRY_RUN paper fills are allowed when ``allowed`` is True and ``live``
    is False. LIVE_READY sets ``would_submit``. Only ``live`` may POST.
    """
    side = (signal.side or "").lower()
    if side not in LIVE_SIDES:
        return _block("NO_VALID_SIGNAL")
    if not signal.kind or signal.kind == "HOLD":
        return _block("NO_VALID_SIGNAL")
    if kill_switch:
        return _block("KILL_SWITCH")
    if pending_order:
        return _block("ACTIVE_ORDER_EXISTS")
    if not market_data_real:
        if cfg.may_place_live_orders or cfg.live_ready:
            return _block("SYNTHETIC_DATA")
        slog(
            "TRADE_BLOCKED",
            "synthetic/fallback data; paper path only",
            reason="SYNTHETIC_DATA",
            kind=signal.kind,
            side=side,
        )
    if not amount_ok:
        return _block(amount_reason or "MIN_AMOUNT")
    if cfg.live_ready and not cfg.may_place_live_orders:
        slog(
            "WOULD_SUBMIT_ORDER",
            "LIVE_READY: same path as live, no POST /user/spot/order",
            kind=signal.kind,
            side=side,
            reason=signal.reason,
        )
        return GateDecision(True, "LIVE_READY", False, True)
    if cfg.may_place_live_orders:
        if not private_api_ok:
            return _block("API_UNHEALTHY")
        if not cfg.has_keys:
            return _block("MISSING_KEYS")
        return GateDecision(True, "LIVE", True, False)
    if cfg.dry_run:
        slog(
            "TRADE_BLOCKED",
            "DRY_RUN: paper path only",
            reason="DRY_RUN",
            kind=signal.kind,
            side=side,
        )
        return GateDecision(True, "DRY_RUN", False, False)
    return _block("LIVE_BLOCKED")


def _block(reason: str) -> GateDecision:
    slog("TRADE_BLOCKED", "order not sent to Bitbank", reason=reason)
    slog("EXECUTION_BLOCKED", reason, reason=reason)
    return GateDecision(False, reason, False, False)
