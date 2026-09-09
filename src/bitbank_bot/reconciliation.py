"""Treat Bitbank balances and open orders as the source of truth."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO
from bitbank_bot.strategy import Position


class ReconcileClient(Protocol):
    def free_amount(self, asset: str) -> Decimal: ...

    def get_active_orders(self, pair: str) -> list[dict[str, Any]]: ...

    def get_order(self, pair: str, order_id: str) -> dict[str, Any]: ...


@dataclass
class ReconcileReport:
    ok: bool
    action: str
    reasons: list[str]
    jpy: Decimal
    btc: Decimal
    open_orders: int
    disable_new_orders: bool = False


class ReconciliationManager:
    def __init__(self, cfg: Config, client: ReconcileClient | None) -> None:
        self.cfg = cfg
        self.client = client

    def run(
        self,
        *,
        position: Position | None,
        pending_order_id: str | None,
        paper: bool,
    ) -> ReconcileReport:
        if paper or self.client is None or not self.cfg.has_keys:
            return ReconcileReport(True, "skipped_paper", [], ZERO, ZERO, 0)
        try:
            jpy = self.client.free_amount("jpy")
            btc = self.client.free_amount("btc")
            orders = self.client.get_active_orders(self.cfg.pair)
        except Exception as exc:
            slog("RECONCILE", "fetch failed", error=type(exc).__name__)
            return ReconcileReport(
                False,
                "fetch_failed",
                [type(exc).__name__],
                ZERO,
                ZERO,
                0,
                disable_new_orders=True,
            )
        reasons: list[str] = []
        disable = False
        action = "aligned"
        open_n = len(orders)
        bot_btc = position.amount if position is not None else ZERO
        if pending_order_id:
            ids = {str(row.get("order_id") or "") for row in orders}
            if pending_order_id not in ids:
                try:
                    raw = self.client.get_order(self.cfg.pair, pending_order_id)
                    status = str(raw.get("status") or "").upper()
                    executed = D(raw.get("executed_amount") or 0)
                    if status in {"CANCELED", "CANCELLED", "REJECTED", "EXPIRED"}:
                        reasons.append("pending_order_gone")
                        action = "clear_pending"
                    elif executed > ZERO:
                        reasons.append("pending_filled_on_exchange")
                        action = "poll_pending"
                    else:
                        reasons.append("pending_missing_ambiguous")
                        disable = True
                        action = "disable_orders"
                except Exception:
                    reasons.append("pending_lookup_failed")
                    disable = True
                    action = "disable_orders"
        elif open_n > 0:
            reasons.append("exchange_open_orders_without_pending")
            action = "adopt_pending"
            disable = True
        if position is not None and btc < self.cfg.min_amount_btc and open_n == 0 and not pending_order_id:
            reasons.append("bot_position_exchange_btc_dust")
            action = "clear_position"
        if position is None and btc >= self.cfg.min_amount_btc and open_n == 0:
            reasons.append("exchange_btc_without_bot_position")
            action = "external_btc"
            disable = True
        if bot_btc > ZERO and btc > ZERO:
            delta = abs(bot_btc - btc)
            if delta > self.cfg.min_amount_btc:
                reasons.append("btc_qty_mismatch")
                disable = True
                if action == "aligned":
                    action = "qty_mismatch"
        ok = not disable
        slog(
            "POSITION_RECONCILED" if ok else "RECONCILE",
            action,
            ok=ok,
            jpy=str(jpy),
            btc=str(btc),
            bot_btc=str(bot_btc),
            open_orders=open_n,
            reasons=",".join(reasons) or "none",
            disable_new_orders=disable,
        )
        slog("BALANCE_CHANGED", "reconcile balances", jpy=str(jpy), btc=str(btc))
        return ReconcileReport(ok, action, reasons, jpy, btc, open_n, disable)
