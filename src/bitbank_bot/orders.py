"""Order gate: DRY_RUN never hits create_order; duplicate active orders block."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.config import Config
from bitbank_bot.fees import resolve_fee
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO, ensure_decimal, quantize_price
from bitbank_bot.strategy import Signal

_CANCELED_UNFILLED = frozenset(
    {
        "CANCELED_UNFILLED",
        "CANCELLED_UNFILLED",
        "CANCELED",
        "CANCELLED",
        "EXPIRED",
        "INACTIVE",
    }
)
_CANCELED_PARTIAL = frozenset(
    {
        "CANCELED_PARTIALLY_FILLED",
        "CANCELLED_PARTIALLY_FILLED",
    }
)


def _fill_status(raw_status: str, executed: Decimal, ordered: Decimal) -> str:
    """Map Bitbank order status. Cancel/expire always terminal even at 0 fill."""
    status = (raw_status or "").upper().strip()
    if status in _CANCELED_UNFILLED:
        return "CANCELED"
    if status in _CANCELED_PARTIAL:
        return "CANCELED_PARTIAL"
    if executed <= ZERO:
        return "UNFILLED"
    if ordered > ZERO and executed < ordered:
        return "PARTIALLY_FILLED"
    return "FULLY_FILLED"


def _poll_reason(status: str) -> str:
    if status == "CANCELED":
        return "canceled"
    if status == "CANCELED_PARTIAL":
        return "canceled_partial"
    if status == "PARTIALLY_FILLED":
        return "partial_fill"
    if status == "UNFILLED":
        return "accepted_unfilled"
    return "fill"


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

    def cancel_order(self, pair: str, order_id: str) -> dict[str, Any]: ...


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
    fee_jpy: Decimal = ZERO


class OrderExecutor:
    def __init__(self, cfg: Config, client: OrderClient | None) -> None:
        self.cfg = cfg
        self.client = client

    def active_orders(self) -> list[dict[str, Any]]:
        if self.client is None:
            return []
        try:
            return self.client.get_active_orders(self.cfg.pair)
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
                fee = resolve_fee(None, actual, self.cfg.fee_buffer, prefer_estimate=True)
                slog(
                    "SIMULATED_FILL",
                    "paper fill only; Bitbank JPY unchanged",
                    executed_amount=str(plan.amount),
                    average_price=str(plan.price),
                    actual_execution_jpy=str(actual),
                    fee_jpy=str(fee),
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
                    fee,
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
        order_type = self._order_type_for(plan.side, signal.kind)
        price_str: str | None = None
        if order_type == "limit":
            q = quantize_price(plan.price, self.cfg.price_tick)
            price_str = str(int(q)) if q == q.to_integral_value() else str(q)
        raw = self.client.create_order(
            pair=self.cfg.pair,
            amount=str(plan.amount),
            side=plan.side,
            order_type=order_type,
            price=price_str,
            post_only=self.cfg.post_only if order_type == "limit" else None,
            live_confirmed=True,
        )
        order_id = str(raw.get("order_id") or "")
        status = str(raw.get("status") or "")
        slog(
            "ORDER_ACCEPTED",
            "order accepted",
            order_id=order_id,
            status=status,
            order_type=order_type,
        )
        executed = D(raw.get("executed_amount") or 0)
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
        if status == "CANCELED" and executed <= ZERO:
            return OrderResult(
                True, "canceled", False, False, order_id, status, ZERO, ZERO, None, raw
            )
        if executed <= ZERO:
            slog("ORDER_STATUS", "no fill yet; not logging FILL", order_id=order_id, status=status)
            return OrderResult(
                True, "accepted_unfilled", False, False, order_id, status, ZERO, ZERO, None, raw
            )
        actual = executed * avg
        fee = resolve_fee(raw, actual, self.cfg.fee_buffer)
        reason = _poll_reason(status)
        slog(
            "FILL" if reason == "fill" else "ORDER_STATUS",
            "fill" if reason == "fill" else f"{reason}; keep polling" if reason == "partial_fill" else reason,
            order_id=order_id,
            executed_amount=str(executed),
            average_price=str(avg),
            actual_execution_jpy=str(actual),
            fee_jpy=str(fee),
            status=status,
        )
        return OrderResult(
            True, reason, False, False, order_id, status, executed, avg, actual, raw, fee
        )

    def _order_type_for(self, side: str, kind: str) -> str:
        if side == "sell":
            if kind in {"STOP", "EMERGENCY_STOP"} and self.cfg.stop_order_type:
                return self.cfg.stop_order_type
            if self.cfg.exit_order_type:
                return self.cfg.exit_order_type
        return self.cfg.order_type

    def cancel(self, order_id: str) -> OrderResult:
        if self.client is None or not hasattr(self.client, "cancel_order"):
            return OrderResult(
                False, "no_cancel", False, False, order_id, None, ZERO, ZERO, None, None
            )
        try:
            raw = self.client.cancel_order(self.cfg.pair, order_id)
        except Exception as exc:
            slog("ERROR", "cancel_order failed", error=type(exc).__name__, order_id=order_id)
            return OrderResult(
                False, "cancel_failed", False, False, order_id, None, ZERO, ZERO, None, None
            )
        executed = D(raw.get("executed_amount") or 0)
        avg = D(raw.get("average_price") or 0)
        ordered = D(raw.get("start_amount") or 0)
        status = _fill_status(str(raw.get("status") or "CANCELED_UNFILLED"), executed, ordered)
        reason = _poll_reason(status)
        actual = executed * avg if executed > ZERO and avg > ZERO else None
        fee = resolve_fee(raw, actual or ZERO, self.cfg.fee_buffer) if actual else ZERO
        slog("ORDER_STATUS", "canceled", order_id=order_id, status=status, reason=reason)
        return OrderResult(
            True, reason, False, False, order_id, status, executed, avg, actual, raw, fee
        )

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
        reason = _poll_reason(status)
        slog(
            "ORDER_STATUS",
            "pending poll",
            order_id=order_id,
            status=status,
            reason=reason,
            executed_amount=str(executed),
        )
        if status == "CANCELED" and executed <= ZERO:
            return OrderResult(
                True, "canceled", False, False, order_id, status, ZERO, ZERO, None, raw
            )
        if executed <= ZERO:
            return OrderResult(
                True, "accepted_unfilled", False, False, order_id, status, ZERO, ZERO, None, raw
            )
        actual = executed * avg
        fee = resolve_fee(raw, actual, self.cfg.fee_buffer)
        slog(
            "FILL" if reason == "fill" else "ORDER_STATUS",
            "fill after poll" if reason == "fill" else f"{reason} after poll",
            order_id=order_id,
            executed_amount=str(executed),
            actual_execution_jpy=str(actual),
            fee_jpy=str(fee),
            status=status,
        )
        return OrderResult(
            True, reason, False, False, order_id, status, executed, avg, actual, raw, fee
        )
