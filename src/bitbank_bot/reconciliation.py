"""Compare bot state to Bitbank balances and open orders. Exchange wins."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO


@dataclass(frozen=True)
class ReconcileReport:
    ok: bool
    reason: str
    jpy: Decimal
    btc: Decimal
    open_orders: int
    bot_btc: Decimal
    adopted_order_id: str | None = None


def reconcile(
    *,
    exchange_jpy: Decimal,
    exchange_btc: Decimal,
    open_orders: list[dict[str, Any]],
    bot_position_btc: Decimal,
    pending: bool,
    min_amount: Decimal,
) -> ReconcileReport:
    orders = list(open_orders or [])
    count = len(orders)
    bot_btc = D(bot_position_btc)
    ex_btc = D(exchange_btc)
    delta = abs(ex_btc - bot_btc)
    reason = "ok"
    ok = True
    adopted: str | None = None
    if pending and count == 0:
        reason = "pending_without_exchange_order"
        ok = False
    elif (not pending) and count == 1:
        reason = "exchange_open_order_adopted"
        ok = True
        adopted = str(orders[0].get("order_id") or "") or None
    elif (not pending) and count > 1:
        reason = "multiple_exchange_open_orders"
        ok = False
    elif delta > D(min_amount) and not pending and count == 0:
        reason = "btc_position_mismatch"
        ok = False
    slog(
        "POSITION_RECONCILED" if ok else "RECONCILE",
        reason,
        jpy=str(D(exchange_jpy)),
        btc=str(ex_btc),
        bot_btc=str(bot_btc),
        open_orders=count,
        ok=ok,
        adopted_order_id=adopted or "",
    )
    if not ok:
        slog("TRADE_BLOCKED", "EXECUTION_BLOCKED", reason=f"reconcile_{reason}")
    return ReconcileReport(
        ok, reason, D(exchange_jpy), ex_btc, count, bot_btc, adopted
    )


def adopt_position_from_exchange(
    exchange_btc: Decimal,
    mark: Decimal,
    *,
    min_amount: Decimal,
    default_tp: Decimal,
) -> tuple[Decimal, Decimal] | None:
    """If exchange holds BTC and bot has none, size a paper/live position shell."""
    btc = D(exchange_btc)
    if btc < D(min_amount):
        return None
    price = D(mark)
    if price <= ZERO:
        return None
    return btc, price
