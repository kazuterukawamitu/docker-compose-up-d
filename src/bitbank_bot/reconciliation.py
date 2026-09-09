"""Treat Bitbank REST as source of truth for balances and open orders."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO


class AssetClient(Protocol):
    def free_amount(self, asset: str) -> Decimal: ...

    def get_active_orders(self, pair: str) -> list[dict[str, Any]]: ...

    def get_order(self, pair: str, order_id: str) -> dict[str, Any]: ...


@dataclass
class ReconcileReport:
    ok: bool
    reason: str
    jpy: Decimal
    btc: Decimal
    exchange_orders: int
    action: str


def _orders_list(raw: object) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if isinstance(raw, dict):
        inner = raw.get("orders")
        if isinstance(inner, list):
            return [row for row in inner if isinstance(row, dict)]
        return []
    return []


class ReconciliationManager:
    def __init__(self, cfg: Config, client: AssetClient | None) -> None:
        self.cfg = cfg
        self.client = client

    def reconcile(
        self,
        *,
        bot_btc: Decimal,
        pending_order_id: str | None,
        allow_paper: bool,
    ) -> ReconcileReport:
        if self.client is None or not self.cfg.has_keys:
            return ReconcileReport(True, "paper_or_no_keys", ZERO, ZERO, 0, "skip")
        try:
            jpy = self.client.free_amount("jpy")
            btc = self.client.free_amount("btc")
            raw_orders = self.client.get_active_orders(self.cfg.pair)
            orders = _orders_list(raw_orders)
        except Exception as exc:
            slog("ERROR", "reconciliation fetch failed", error=type(exc).__name__)
            return ReconcileReport(False, "reconcile_fetch_failed", ZERO, ZERO, 0, "block")
        slog(
            "BALANCE_CHANGED",
            "exchange balances",
            jpy=str(jpy),
            btc=str(btc),
            open_orders=len(orders),
        )
        if orders:
            for row in orders:
                slog(
                    "ORDER_ACTIVE",
                    "exchange open order",
                    order_id=row.get("order_id"),
                    side=row.get("side"),
                    status=row.get("status"),
                    amount=row.get("start_amount") or row.get("remaining_amount"),
                    executed_amount=row.get("executed_amount"),
                    remaining_amount=row.get("remaining_amount"),
                )
        if pending_order_id and not any(str(row.get("order_id")) == pending_order_id for row in orders):
            try:
                remote = self.client.get_order(self.cfg.pair, pending_order_id)
                status = str(remote.get("status") or "")
                slog("ORDER_STATUS", "pending missing from open book", order_id=pending_order_id, status=status)
                if status.upper() in {"CANCELED", "CANCELLED", "REJECTED", "EXPIRED"}:
                    return ReconcileReport(False, "pending_order_gone", jpy, btc, len(orders), "clear_pending")
            except Exception as exc:
                slog("ERROR", "pending get_order failed", error=type(exc).__name__)
                return ReconcileReport(False, "pending_unknown", jpy, btc, len(orders), "block")
        if not pending_order_id and orders:
            slog("ERROR", "exchange has open orders; bot pending is empty")
            return ReconcileReport(False, "exchange_open_orders", jpy, btc, len(orders), "block")
        delta = abs(D(btc) - D(bot_btc))
        if (not allow_paper) and delta > self.cfg.min_amount_btc:
            slog(
                "POSITION_RECONCILED",
                "btc mismatch; Bitbank is source of truth",
                bot_btc=str(bot_btc),
                exchange_btc=str(btc),
            )
            return ReconcileReport(False, "btc_mismatch", jpy, btc, len(orders), "block")
        slog("POSITION_RECONCILED", "bot and Bitbank agree", btc=str(btc), jpy=str(jpy))
        return ReconcileReport(True, "ok", jpy, btc, len(orders), "ok")
