"""Align bot-internal position/orders with Bitbank balances and open orders."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO
from bitbank_bot.strategy import Position


class AssetClient(Protocol):
    def free_amount(self, asset: str) -> Decimal: ...

    def get_active_orders(self, pair: str) -> list[dict[str, Any]]: ...


@dataclass
class ReconcileReport:
    ok: bool
    reason: str
    jpy: Decimal
    btc: Decimal
    open_orders: int
    action: str
    disable_new_orders: bool = False


def _pos_btc(position: Position | None) -> Decimal:
    return position.amount if position is not None else ZERO


def reconcile(
    *,
    cfg: Config,
    client: AssetClient | None,
    position: Position | None,
    pending_order_id: str | None,
    market_data_real: bool,
) -> ReconcileReport:
    if client is None or not cfg.has_keys:
        slog("POSITION_RECONCILED", "skip; no private client")
        return ReconcileReport(True, "no_private_client", ZERO, ZERO, 0, "skip")
    try:
        jpy = client.free_amount("jpy")
        btc = client.free_amount("btc")
        opens = client.get_active_orders(cfg.pair)
    except Exception as exc:
        slog(
            "ERROR",
            "reconcile fetch failed",
            error=type(exc).__name__,
            function="reconcile",
            pair=cfg.pair,
        )
        return ReconcileReport(
            False,
            "reconcile_fetch_failed",
            ZERO,
            ZERO,
            0,
            "warn",
            disable_new_orders=True,
        )
    open_ids = {str(row.get("order_id") or "") for row in opens}
    pending_missing = bool(pending_order_id) and pending_order_id not in open_ids and pending_order_id not in {
        "dry-run",
        "",
    }
    pos_btc = _pos_btc(position)
    # Free BTC can be below position while an exit is pending; warn only on
    # a clear "bot long / exchange flat" or "bot flat / exchange long" gap.
    dust = cfg.min_amount_btc
    bot_long = pos_btc >= dust
    exch_long = btc >= dust
    mismatch = False
    reason = "ok"
    action = "aligned"
    disable = False
    if pending_order_id and pending_missing and not opens:
        # Order may have filled; caller should poll. Not fatal.
        reason = "pending_not_in_open_orders"
        action = "poll_order"
    if bot_long and not exch_long and not opens:
        mismatch = True
        reason = "bot_position_exchange_flat"
        action = "disable_new_orders"
        disable = True
    if exch_long and not bot_long and not opens and not pending_order_id:
        mismatch = True
        reason = "exchange_btc_bot_flat"
        action = "adopt_or_warn"
        disable = True
    if opens and not pending_order_id:
        mismatch = True
        reason = "open_orders_without_pending"
        action = "adopt_open_order"
        disable = True
    ok = not mismatch
    slog(
        "POSITION_RECONCILED",
        "reconcile",
        ok=ok,
        reason=reason,
        jpy=str(jpy),
        btc=str(btc),
        bot_btc=str(pos_btc),
        open_orders=len(opens),
        pending_order_id=pending_order_id or "",
        market_data_real=market_data_real,
        action=action,
    )
    slog("BALANCE_CHANGED", "exchange free amounts", jpy=str(jpy), btc=str(btc))
    return ReconcileReport(ok, reason, jpy, btc, len(opens), action, disable_new_orders=disable)
