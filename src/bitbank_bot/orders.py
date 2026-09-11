"""Order gate: DRY_RUN never hits create_order; duplicate active orders block."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO, ensure_decimal, quantize_price
from bitbank_bot.rest_client import BitbankAPIError, coerce_active_orders
from bitbank_bot.strategy import Signal


def _fill_status(raw_status: str, executed: Decimal, ordered: Decimal) -> str:
    if executed <= ZERO:
        return "UNFILLED"
    if ordered > ZERO and executed < ordered:
        return "PARTIALLY_FILLED"
    return "FULLY_FILLED"


def _execution_jpy(executed: Decimal, avg: Decimal) -> Decimal | None:
    """Fill notional. Missing/zero average_price must not become a 0-JPY ledger fill."""
    if executed <= ZERO or avg <= ZERO:
        return None
    return executed * avg


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
            return coerce_active_orders(self.client.get_active_orders(self.cfg.pair))
        except Exception as exc:
            slog("ERROR", "active_orders failed", error=type(exc).__name__)
            raise

    def _refresh_order(self, order_id: str) -> dict[str, Any] | None:
        if self.client is None or not hasattr(self.client, "get_order"):
            return None
        try:
            data = self.client.get_order(self.cfg.pair, order_id)
        except Exception as exc:
            slog("ERROR", "get_order failed", error=type(exc).__name__, order_id=order_id)
            return None
        if not isinstance(data, dict):
            slog("ERROR", "get_order returned non-object", order_id=order_id)
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
            if self.cfg.is_live_ready:
                slog(
                    "WOULD_SUBMIT_ORDER",
                    "LIVE_READY: not calling Bitbank create_order",
                    side=plan.side,
                    amount=str(plan.amount),
                    price=str(plan.price),
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
                mode=mode,
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
                "create_order failed; not retrying POST",
                error=type(exc).__name__,
            )
            recovered = self._recover_unconfirmed_submit(plan)
            if recovered is not None:
                return recovered
            raise
        if not isinstance(raw, dict):
            slog("ERROR", "create_order returned non-object; not retrying POST")
            recovered = self._recover_unconfirmed_submit(plan)
            if recovered is not None:
                return recovered
            raise BitbankAPIError("create_order_unreadable")
        order_id = str(raw.get("order_id") or "")
        status = str(raw.get("status") or "")
        slog("ORDER_ACCEPTED", "order accepted", order_id=order_id, status=status)
        executed = D(raw.get("executed_amount") or 0)
        avg = D(raw.get("average_price") or 0)
        amount_ordered = D(raw.get("start_amount") or plan.amount)
        if order_id and (executed <= ZERO or avg <= ZERO):
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
        actual = _execution_jpy(executed, avg)
        if executed <= ZERO or actual is None:
            if executed > ZERO and actual is None:
                slog(
                    "ERROR",
                    "fill missing average_price; keeping unfilled pending",
                    order_id=order_id,
                    executed_amount=str(executed),
                )
            else:
                slog(
                    "ORDER_STATUS",
                    "no fill yet; not logging FILL",
                    order_id=order_id,
                    status=status,
                )
            return OrderResult(
                True, "accepted_unfilled", False, False, order_id, status, ZERO, ZERO, None, raw
            )
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
        return OrderResult(
            True, reason, False, False, order_id, status, executed, avg, actual, raw
        )

    def _recover_unconfirmed_submit(self, plan: AmountPlan) -> OrderResult | None:
        """After a POST timeout, inspect open orders. Never POST again."""
        try:
            active = self.active_orders()
        except Exception as exc:
            slog("ERROR", "cannot list open orders after submit error", error=type(exc).__name__)
            return None
        match = None
        for row in active:
            if str(row.get("side") or "") == plan.side:
                match = row
                break
        if match is None:
            slog("ORDER_STATUS", "no matching open order after submit error")
            return None
        order_id = str(match.get("order_id") or "")
        slog(
            "ORDER_STATUS",
            "recovered order via active_orders; not re-posting",
            order_id=order_id,
        )
        executed = D(match.get("executed_amount") or 0)
        avg = D(match.get("average_price") or 0)
        ordered = D(match.get("start_amount") or plan.amount)
        status = _fill_status(str(match.get("status") or ""), executed, ordered)
        actual = _execution_jpy(executed, avg)
        if executed <= ZERO or actual is None:
            return OrderResult(
                True, "accepted_unfilled", False, False, order_id, status, ZERO, ZERO, None, match
            )
        reason = "partial_fill" if status == "PARTIALLY_FILLED" else "fill"
        return OrderResult(True, reason, False, False, order_id, status, executed, avg, actual, match)

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
        actual = _execution_jpy(executed, avg)
        if executed <= ZERO or actual is None:
            if executed > ZERO and actual is None:
                slog(
                    "ERROR",
                    "poll fill missing average_price; holding pending",
                    order_id=order_id,
                    executed_amount=str(executed),
                )
            return OrderResult(
                True, "accepted_unfilled", False, False, order_id, status, ZERO, ZERO, None, raw
            )
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
