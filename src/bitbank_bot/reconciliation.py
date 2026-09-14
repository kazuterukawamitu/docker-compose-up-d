"""Compare bot state to Bitbank balances and open orders. Bitbank wins."""

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
    if pending and count == 0:
        reason = "pending_without_exchange_order"
        ok = False
    elif (not pending) and count > 0:
        reason = "exchange_open_orders_bot_idle"
        ok = False
    elif delta > D(min_amount) and not pending:
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
    )
    if not ok:
        slog("TRADE_BLOCKED", "EXECUTION_BLOCKED", reason=f"reconcile_{reason}")
    return ReconcileReport(ok, reason, D(exchange_jpy), ex_btc, count, bot_btc)
