"""Order gate: DRY_RUN never hits create_order; duplicate active orders block."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO, ensure_decimal, quantize_price
from bitbank_bot.strategy import Signal


def _fill_status(raw_status: str, executed: Decimal, ordered: Decimal) -> str:
    if executed <= ZERO:
        return "UNFILLED"
    if ordered > ZERO and executed < ordered:
        return "PARTIALLY_FILLED"
    return "FULLY_FILLED"


class OrderClient(Protocol):
    def get_active_orders(self, pair: str) -> list[dict[str, Any]]: ...

    def get_order(self, pair: str, order_id: str) -> dict[str, Any]: ...

    def create_order(
        self,
        pair: str,
        amount: str,
        side: str,
        order_type: str,
        price: str | None = None,
        post_only: bool | None = None,
        *,
        live_confirmed: bool = False,
    ) -> dict[str, Any]: ...

    def cancel_order(
        self,
        pair: str,
        order_id: str,
        *,
        live_confirmed: bool = False,
    ) -> dict[str, Any]: ...


@dataclass
class OrderResult:
    ok: bool
    reason: str
    dry_run: bool
    simulated: bool
    order_id: str | None
    status: str | None
    executed_amount: Decimal
    average_price: Decimal
    actual_execution_jpy: Decimal | None
    raw: dict[str, Any] | None


class OrderExecutor:
    def __init__(self, cfg: Config, client: OrderClient | None) -> None:
        self.cfg = cfg
        self.client = client

    def active_orders(self) -> list[dict[str, Any]]:
        if self.client is None:
            return []
        try:
            raw = self.client.get_active_orders(self.cfg.pair)
        except Exception as exc:
            slog("ERROR", "active_orders failed", error=type(exc).__name__)
            raise
        if raw is None:
            return []
        if not isinstance(raw, list):
            slog("ERROR", "active_orders was not a list", type=type(raw).__name__)
            return []
        return raw

    def _refresh_order(self, order_id: str) -> dict[str, Any] | None:
        if self.client is None or not hasattr(self.client, "get_order"):
            return None
        try:
            data = self.client.get_order(self.cfg.pair, order_id)
        except Exception as exc:
            slog("ERROR", "get_order failed", error=type(exc).__name__, order_id=order_id)
            return None
        slog("ORDER_STATUS", "refreshed from GET /user/spot/order", order_id=order_id)
        return data

    def place(self, signal: Signal, plan: AmountPlan) -> OrderResult:
        slog(
            "ORDER_REQUEST",
            "order request",
            kind=signal.kind,
            side=plan.side,
            amount=str(plan.amount),
            price=str(plan.price),
            target_jpy=str(plan.target_jpy),
            planned_order_jpy=str(plan.planned_order_jpy),
            actual_execution_jpy="unset",
        )
        try:
            ensure_decimal(plan.amount, "order_amount")
            ensure_decimal(plan.price, "order_price")
            ensure_decimal(plan.planned_order_jpy, "planned_order_jpy")
        except Exception as exc:
            slog("ERROR", "number expected before order", error=str(exc))
            return OrderResult(
                False,
                "number_expected",
                self.cfg.dry_run,
                False,
                None,
                None,
                ZERO,
                ZERO,
                None,
                None,
            )
        if not plan.ok or plan.amount <= ZERO:
            return OrderResult(
                False,
                plan.reason,
                self.cfg.dry_run,
                False,
                None,
                None,
                ZERO,
                ZERO,
                None,
                None,
            )
        if not self.cfg.may_place_live_orders:
            mode = self.cfg.resolved_trading_mode()
            if mode == "live_ready":
                slog(
                    "WOULD_SUBMIT_ORDER",
                    "LIVE_READY: not calling Bitbank create_order",
                    pair=self.cfg.pair,
                    side=plan.side,
                    amount=str(plan.amount),
                    price=str(plan.price),
                    order_type=self.cfg.order_type,
                    mode="LIVE_READY",
                )
                return OrderResult(
                    True,
                    "would_submit",
                    True,
                    False,
                    None,
                    "UNFILLED",
                    ZERO,
                    ZERO,
                    None,
                    None,
                )
            slog(
                "ORDER_INTENT",
                "DRY_RUN: not calling Bitbank create_order",
                side=plan.side,
                amount=str(plan.amount),
                price=str(plan.price),
                mode="DRY_RUN" if self.cfg.dry_run else "LIVE_BLOCKED",
            )
            if self.cfg.dry_run and self.cfg.simulate_fill:
                actual = plan.amount * plan.price
                slog(
                    "SIMULATED_FILL",
                    "paper fill only; Bitbank JPY unchanged",
                    executed_amount=str(plan.amount),
                    average_price=str(plan.price),
                    actual_execution_jpy=str(actual),
                )
                return OrderResult(
                    True,
                    "simulated",
                    True,
                    True,
                    "dry-run",
                    "FULLY_FILLED",
                    plan.amount,
                    plan.price,
                    actual,
                    None,
                )
            return OrderResult(
                True,
                "intent_only",
                True,
                False,
                None,
                "UNFILLED",
                ZERO,
                ZERO,
                None,
                None,
            )
        if self.client is None:
            slog("ERROR", "live path has no client")
            return OrderResult(
                False, "no_client", False, False, None, None, ZERO, ZERO, None, None
            )
        self._snapshot_depth()
        try:
            active = self.active_orders()
        except Exception as exc:
            slog("ERROR", "cannot list active orders; refusing live order", error=type(exc).__name__)
            raise
        if active:
            slog("RISK", "duplicate active orders; refusing new order", count=len(active))
            return OrderResult(
                False,
                "active_orders",
                False,
                False,
                None,
                None,
                ZERO,
                ZERO,
                None,
                None,
            )
        price_str: str | None = None
        if self.cfg.order_type == "limit":
            q = quantize_price(plan.price, self.cfg.price_tick)
            price_str = str(int(q)) if q == q.to_integral_value() else str(q)
        try:
            raw = self.client.create_order(
                pair=self.cfg.pair,
                amount=str(plan.amount),
                side=plan.side,
                order_type=self.cfg.order_type,
                price=price_str,
                post_only=self.cfg.post_only if self.cfg.order_type == "limit" else None,
                live_confirmed=True,
            )
        except Exception as exc:
            slog(
                "ERROR",
                "create_order uncertain; reconciling instead of retrying POST",
                error=type(exc).__name__,
                side=plan.side,
                amount=str(plan.amount),
            )
            recovered = self._recover_uncertain_order(plan.side, str(plan.amount))
            if recovered is None:
                raise
            raw = recovered
        order_id = str(raw.get("order_id") or "")
        status = str(raw.get("status") or "")
        executed = D(raw.get("executed_amount") or 0)
        slog("ORDER_ACCEPTED", "order accepted", order_id=order_id, status=status)
        slog("ORDER_ID_RECEIVED", "order_id stored", order_id=order_id)
        if executed <= ZERO:
            slog("ORDER_ACTIVE", "accepted and unfilled", order_id=order_id, status=status)
        avg = D(raw.get("average_price") or 0)
        amount_ordered = D(raw.get("start_amount") or plan.amount)
        if order_id and executed <= ZERO:
            refreshed = self._refresh_order(order_id)
            if refreshed:
                raw = refreshed
                status = str(raw.get("status") or status)
                executed = D(raw.get("executed_amount") or 0)
                avg = D(raw.get("average_price") or 0)
                amount_ordered = D(raw.get("start_amount") or amount_ordered)
        status = _fill_status(status, executed, amount_ordered)
        slog(
            "ORDER_STATUS",
            "order status",
            order_id=order_id,
            status=status,
            executed_amount=str(executed),
        )
        if executed <= ZERO:
            slog("ORDER_STATUS", "no fill yet; not logging FILL", order_id=order_id, status=status)
            return OrderResult(
                True, "accepted_unfilled", False, False, order_id, status, ZERO, ZERO, None, raw
            )
        actual = executed * avg
        reason = "partial_fill" if status == "PARTIALLY_FILLED" else "fill"
        slog(
            "FILL" if reason == "fill" else "ORDER_STATUS",
            "fill" if reason == "fill" else "partial fill; keep polling",
            order_id=order_id,
            executed_amount=str(executed),
            average_price=str(avg),
            actual_execution_jpy=str(actual),
            status=status,
        )
        if reason == "partial_fill":
            slog("PARTIALLY_FILLED", "keep polling remainder", order_id=order_id)
        else:
            slog("FULLY_FILLED", "fill complete", order_id=order_id)
        return OrderResult(
            True, reason, False, False, order_id, status, executed, avg, actual, raw
        )

    def _recover_uncertain_order(self, side: str, amount: str) -> dict[str, Any] | None:
        try:
            active = self.active_orders()
        except Exception as exc:
            slog("ERROR", "cannot reconcile after order timeout", error=type(exc).__name__)
            return None
        matches = [
            row
            for row in active
            if str(row.get("side") or "") == side
            and str(row.get("start_amount") or row.get("amount") or "") == amount
        ]
        if len(matches) == 1:
            slog(
                "ORDER_ACCEPTED",
                "recovered order after uncertain POST",
                order_id=str(matches[0].get("order_id") or ""),
            )
            return matches[0]
        slog(
            "ORDER_STATUS",
            "no unique open order after uncertain POST; not resending",
            matches=len(matches),
        )
        return None

    def poll(self, order_id: str, fallback_amount: Decimal) -> OrderResult:
        """Re-read a live order. Does not place a new order."""
        raw = self._refresh_order(order_id)
        if raw is None:
            return OrderResult(
                False, "poll_failed", False, False, order_id, None, ZERO, ZERO, None, None
            )
        executed = D(raw.get("executed_amount") or 0)
        avg = D(raw.get("average_price") or 0)
        ordered = D(raw.get("start_amount") or fallback_amount)
        status = _fill_status(str(raw.get("status") or ""), executed, ordered)
        slog(
            "ORDER_STATUS",
            "pending poll",
            order_id=order_id,
            status=status,
            executed_amount=str(executed),
        )
        if executed <= ZERO:
            return OrderResult(
                True, "accepted_unfilled", False, False, order_id, status, ZERO, ZERO, None, raw
            )
        actual = executed * avg
        reason = "partial_fill" if status == "PARTIALLY_FILLED" else "fill"
        slog(
            "FILL" if reason == "fill" else "ORDER_STATUS",
            "fill after poll" if reason == "fill" else "partial fill after poll",
            order_id=order_id,
            executed_amount=str(executed),
            actual_execution_jpy=str(actual),
            status=status,
        )
        return OrderResult(True, reason, False, False, order_id, status, executed, avg, actual, raw)

    def _snapshot_depth(self) -> None:
        if self.client is None or not hasattr(self.client, "get_depth"):
            return
        try:
            book = self.client.get_depth(self.cfg.pair)
        except Exception as exc:
            slog("MARKET", "depth unavailable", error=type(exc).__name__)
            return
        asks = book.get("asks") if isinstance(book, dict) else None
        bids = book.get("bids") if isinstance(book, dict) else None
        slog(
            "MARKET",
            "depth before order",
            asks=len(asks) if isinstance(asks, list) else 0,
            bids=len(bids) if isinstance(bids, list) else 0,
        )

    def cancel(self, order_id: str) -> bool:
        if not order_id:
            return False
        if not self.cfg.may_place_live_orders:
            slog(
                "ORDER_STATUS",
                "not calling Bitbank cancel_order",
                order_id=order_id,
                mode=self.cfg.resolved_trading_mode(),
            )
            return False
        if self.client is None or not hasattr(self.client, "cancel_order"):
            slog("ERROR", "live path has no cancel_order")
            return False
        try:
            self.client.cancel_order(self.cfg.pair, order_id, live_confirmed=True)
        except Exception as exc:
            slog(
                "ERROR",
                "cancel_order failed; not retrying POST",
                error=type(exc).__name__,
                order_id=order_id,
            )
            return False
        slog("ORDER_STATUS", "cancel accepted", order_id=order_id)
        return True
