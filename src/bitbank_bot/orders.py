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


_CANCELED_FLAT = frozenset(
    {
        "CANCELED",
        "CANCELED_UNFILLED",
        "CANCELLED",
        "CANCELLED_UNFILLED",
        "REJECTED",
        "EXPIRED",
    }
)
_CANCELED_PARTIAL = frozenset(
    {
        "CANCELED_PARTIALLY_FILLED",
        "CANCELLED_PARTIALLY_FILLED",
    }
)


def normalize_order_status(raw_status: str) -> str:
    return (raw_status or "").strip().upper().replace("-", "_").replace(" ", "_")


def _fill_status(raw_status: str, executed: Decimal, ordered: Decimal) -> str:
    """Map Bitbank status. A cancel is terminal even when executed size is still zero."""
    raw = normalize_order_status(raw_status)
    if raw in _CANCELED_PARTIAL or (raw in _CANCELED_FLAT and executed > ZERO):
        return "CANCELED_PARTIAL"
    if raw in _CANCELED_FLAT:
        return "CANCELED"
    if executed <= ZERO:
        return "UNFILLED"
    if ordered > ZERO and executed < ordered:
        return "PARTIALLY_FILLED"
    return "FULLY_FILLED"


def _reason_for_status(status: str) -> str:
    if status == "CANCELED":
        return "canceled"
    if status == "CANCELED_PARTIAL":
        return "canceled_partial"
    if status == "PARTIALLY_FILLED":
        return "partial_fill"
    if status == "UNFILLED":
        return "accepted_unfilled"
    return "fill"


def order_fee_jpy(
    raw: dict[str, Any] | None,
    executed: Decimal,
    average: Decimal,
    fee_rate: Decimal,
) -> Decimal:
    """Quote-currency fee for this order snapshot.

    Exchange fields win. ``fee_rate`` applies only when the payload has no fee.
    The returned value is cumulative for ``executed``, not an increment.
    """
    executed = D(executed)
    average = D(average)
    fee_rate = D(fee_rate)
    if isinstance(raw, dict):
        for key in ("fee_amount_quote", "fee_occurred_amount_quote", "fee"):
            if raw.get(key) not in (None, ""):
                return D(raw[key])
        if raw.get("fee_amount_base") not in (None, ""):
            return D(raw["fee_amount_base"]) * average
    if fee_rate > ZERO and executed > ZERO and average > ZERO:
        return executed * average * fee_rate
    return ZERO


def incremental_notional(
    executed: Decimal,
    average: Decimal,
    prev_executed: Decimal,
    prev_notional: Decimal,
) -> tuple[Decimal, Decimal, Decimal]:
    """Split a cumulative fill into the new contracts and their JPY notional.

    ``average`` is the exchange cumulative average. Multiplying only the new
    size by that average mis-states cost when earlier fills had a different price.
    Returns ``(delta_amount, delta_notional, cumulative_notional)``.
    """
    executed = D(executed)
    average = D(average)
    prev_executed = D(prev_executed)
    prev_notional = D(prev_notional)
    if prev_executed > ZERO and prev_notional <= ZERO and average > ZERO:
        prev_notional = prev_executed * average
    cumulative = executed * average if average > ZERO else prev_notional
    delta_amt = executed - prev_executed
    if delta_amt < ZERO:
        delta_amt = ZERO
    delta_notional = cumulative - prev_notional
    if delta_notional < ZERO:
        delta_notional = ZERO
    return delta_amt, delta_notional, cumulative


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
                fee = order_fee_jpy(None, plan.amount, plan.price, self.cfg.fee_rate)
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
        order_type = "market" if signal.kind == "STOP" else self.cfg.order_type
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
        slog("ORDER_ACCEPTED", "order accepted", order_id=order_id, status=status)
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
        reason = _reason_for_status(status)
        fee = order_fee_jpy(raw, executed, avg, self.cfg.fee_rate)
        slog(
            "ORDER_STATUS",
            "order status",
            order_id=order_id,
            status=status,
            executed_amount=str(executed),
        )
        if reason == "canceled":
            slog("ORDER_STATUS", "order canceled before fill", order_id=order_id, status=status)
            return OrderResult(
                True, "canceled", False, False, order_id, status, ZERO, ZERO, None, raw, ZERO
            )
        if executed <= ZERO:
            slog("ORDER_STATUS", "no fill yet; not logging FILL", order_id=order_id, status=status)
            return OrderResult(
                True, "accepted_unfilled", False, False, order_id, status, ZERO, ZERO, None, raw, ZERO
            )
        actual = executed * avg
        slog(
            "FILL" if reason == "fill" else "ORDER_STATUS",
            "fill" if reason == "fill" else "partial fill; keep polling",
            order_id=order_id,
            executed_amount=str(executed),
            average_price=str(avg),
            actual_execution_jpy=str(actual),
            status=status,
            fee_jpy=str(fee),
        )
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
        reason = _reason_for_status(status)
        fee = order_fee_jpy(raw, executed, avg, self.cfg.fee_rate)
        slog(
            "ORDER_STATUS",
            "pending poll",
            order_id=order_id,
            status=status,
            executed_amount=str(executed),
        )
        if reason == "canceled" or executed <= ZERO:
            if reason == "canceled":
                slog("ORDER_STATUS", "pending order canceled", order_id=order_id, status=status)
            return OrderResult(
                True,
                "canceled" if reason == "canceled" else "accepted_unfilled",
                False,
                False,
                order_id,
                status,
                ZERO,
                ZERO,
                None,
                raw,
                ZERO,
            )
        actual = executed * avg
        slog(
            "FILL" if reason == "fill" else "ORDER_STATUS",
            "fill after poll" if reason == "fill" else "pending update after poll",
            order_id=order_id,
            executed_amount=str(executed),
            actual_execution_jpy=str(actual),
            status=status,
            fee_jpy=str(fee),
        )
        return OrderResult(
            True, reason, False, False, order_id, status, executed, avg, actual, raw, fee
        )
