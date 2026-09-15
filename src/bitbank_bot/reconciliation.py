"""Compare bot ledger with Bitbank assets/open orders. Bitbank is source of truth."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO
from bitbank_bot.strategy import Position


class BalanceClient(Protocol):
    def free_amount(self, asset: str) -> Decimal: ...

    def get_active_orders(self, pair: str) -> list[dict[str, Any]]: ...


@dataclass(frozen=True)
class ReconcileReport:
    ok: bool
    reason: str
    jpy: Decimal
    btc: Decimal
    open_orders: int
    position_mismatch: bool


def reconcile(
    client: BalanceClient,
    pair: str,
    position: Position | None,
    *,
    pending_order_id: str | None,
    min_amount: Decimal,
) -> ReconcileReport:
    jpy = client.free_amount("jpy")
    btc = client.free_amount("btc")
    orders = client.get_active_orders(pair)
    open_n = len(orders)
    pos_amt = position.amount if position is not None else ZERO
    mismatch = False
    reason = "ok"
    if pos_amt > min_amount and btc + min_amount < pos_amt:
        mismatch = True
        reason = "bot_position_gt_exchange_btc"
    if pending_order_id and open_n == 0:
        mismatch = True
        reason = "pending_order_missing_on_exchange"
    if open_n > 0 and not pending_order_id:
        slog(
            "POSITION_RECONCILED",
            "exchange has open orders bot did not track",
            count=open_n,
            order_id=str(orders[0].get("order_id") or ""),
        )
        reason = "untracked_open_orders"
        mismatch = True
    slog(
        "POSITION_RECONCILED",
        reason,
        jpy=str(jpy),
        btc=str(btc),
        open_orders=open_n,
        bot_position=str(pos_amt),
        mismatch=mismatch,
    )
    slog("BALANCE_CHANGED", "exchange free_amount", jpy=str(jpy), btc=str(btc))
    return ReconcileReport(
        ok=not mismatch,
        reason=reason,
        jpy=jpy,
        btc=btc,
        open_orders=open_n,
        position_mismatch=mismatch,
    )
