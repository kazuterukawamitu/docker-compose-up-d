"""Treat Bitbank REST as source of truth for balances and open orders."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO


class BalanceClient(Protocol):
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


class ReconciliationManager:
    def __init__(self, cfg: Config, client: BalanceClient | None) -> None:
        self.cfg = cfg
        self.client = client

    def run(
        self,
        *,
        internal_btc: Decimal,
        pending_order_id: str | None,
        paper: bool,
    ) -> ReconcileReport:
        if paper or self.client is None or not self.cfg.has_keys:
            return ReconcileReport(True, "paper_or_no_keys", ZERO, ZERO, 0, "skip")
        try:
            jpy = self.client.free_amount("jpy")
            btc = self.client.free_amount("btc")
            orders = self.client.get_active_orders(self.cfg.pair)
        except Exception as exc:
            slog(
                "ERROR",
                "reconcile fetch failed",
                error=type(exc).__name__,
                function="ReconciliationManager.run",
                pair=self.cfg.pair,
            )
            return ReconcileReport(False, "reconcile_fetch_failed", ZERO, ZERO, 0, "disable_new_orders")
        open_ids = [str(row.get("order_id") or "") for row in orders if row.get("order_id")]
        slog(
            "POSITION_RECONCILED",
            "bitbank snapshot",
            jpy=str(jpy),
            btc=str(btc),
            open_orders=len(orders),
            pending=pending_order_id or "",
            internal_btc=str(internal_btc),
        )
        if pending_order_id and open_ids and pending_order_id not in open_ids:
            # Pending may have filled; caller polls. Not fatal.
            slog(
                "POSITION_RECONCILED",
                "pending not in open orders; poll required",
                order_id=pending_order_id,
            )
        if pending_order_id is None and open_ids:
            slog(
                "POSITION_RECONCILED",
                "open orders exist but bot has no pending",
                count=len(open_ids),
            )
            return ReconcileReport(
                False, "open_order_not_tracked", jpy, btc, len(orders), "disable_new_orders"
            )
        dust = self.cfg.min_amount_btc
        if internal_btc > dust and btc <= ZERO:
            slog("POSITION_RECONCILED", "internal BTC but exchange BTC is 0")
            return ReconcileReport(False, "position_mismatch", jpy, btc, len(orders), "disable_new_orders")
        if internal_btc <= ZERO and btc > dust and pending_order_id is None:
            slog("POSITION_RECONCILED", "exchange BTC without internal position")
            return ReconcileReport(
                True, "exchange_has_btc", jpy, btc, len(orders), "adopt_exchange_btc"
            )
        slog("BALANCE_CHANGED", "reconcile ok", jpy=str(jpy), btc=str(btc))
        return ReconcileReport(True, "ok", jpy, btc, len(orders), "ok")
