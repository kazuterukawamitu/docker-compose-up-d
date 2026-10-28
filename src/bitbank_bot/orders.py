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


_CANCELED = frozenset(
    {
        "CANCELED",
        "CANCELED_UNFILLED",
        "CANCELED_PARTIALLY_FILLED",
        "REJECTED",
        "EXPIRED",
    }
)


def classify_order(raw_status: str, executed: Decimal, ordered: Decimal) -> tuple[str, str]:
    """Map a Bitbank order to ``(status, reason)``.

    Cancel states are terminal. An unfilled cancel must not stay
    ``accepted_unfilled``, or the engine keeps a pending order forever.
    A cancel that already traded is ``canceled_partial`` so the fill is
    booked and the remainder is dropped.
    """
    status = (raw_status or "").strip().upper()
    canceled = status in _CANCELED or status.startswith("CANCEL")
    if executed <= ZERO:
        if canceled:
            return status or "CANCELED_UNFILLED", "canceled"
        return "UNFILLED", "accepted_unfilled"
    if canceled:
        return status or "CANCELED_PARTIALLY_FILLED", "canceled_partial"
    if ordered > ZERO and executed < ordered:
        return "PARTIALLY_FILLED", "partial_fill"
    return "FULLY_FILLED", "fill"


def incremental_notional(
    previous_notional: Decimal, executed: Decimal, average: Decimal
) -> tuple[Decimal, Decimal]:
    """Split a cumulative average into the new slice's notional.

    ``executed * average`` is the whole order, not the latest slice. Booking
    the slice at the cumulative average mis-states cost when prices differ.
    """
    cumulative = D(executed) * D(average)
    delta = cumulative - D(previous_notional)
    if delta < ZERO:
        delta = ZERO
    return cumulative, delta


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
    fee_btc: Decimal = ZERO
    fee_estimated: bool = False
    cumulative_filled: Decimal | None = None
    cumulative_notional: Decimal | None = None
    cumulative_fee_jpy: Decimal | None = None
    cumulative_fee_btc: Decimal | None = None


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

    def _trade_fees(self, order_id: str) -> tuple[Decimal, Decimal] | None:
        getter = getattr(self.client, "get_trade_history", None)
        if not callable(getter):
            return None
        try:
            trades = getter(self.cfg.pair)
        except Exception as exc:
            slog("ERROR", "trade_history failed", error=type(exc).__name__)
            return None
        if not isinstance(trades, list):
            return None
        matched = [row for row in trades if str(row.get("order_id")) == str(order_id)]
        if not matched:
            return None
        fee_jpy = sum((D(row.get("fee_amount_quote") or 0) for row in matched), ZERO)
        fee_btc = sum((D(row.get("fee_amount_base") or 0) for row in matched), ZERO)
        occurred = sum((D(row.get("fee_occurred_amount") or 0) for row in matched), ZERO)
        return fee_jpy + occurred, fee_btc

    def _fees(
        self,
        raw: dict[str, Any] | None,
        order_id: str,
        executed: Decimal,
        average: Decimal,
    ) -> tuple[Decimal, Decimal, bool]:
        quoted = self._trade_fees(order_id) if order_id and order_id != "dry-run" else None
        if quoted is not None:
            return quoted[0], quoted[1], False
        if raw:
            present = [
                key
                for key in ("fee_amount_quote", "fee_amount_base", "fee_occurred_amount")
                if raw.get(key) not in (None, "")
            ]
            if present:
                fee_jpy = D(raw.get("fee_amount_quote") or 0) + D(raw.get("fee_occurred_amount") or 0)
                return fee_jpy, D(raw.get("fee_amount_base") or 0), False
        notional = executed * average
        rate = D(self.cfg.taker_fee_rate)
        if notional > ZERO and rate > ZERO:
            return notional * rate, ZERO, True
        return ZERO, ZERO, False

    def _from_exchange(
        self,
        raw: dict[str, Any],
        *,
        fallback_amount: Decimal,
        order_id: str,
        unfilled_ok: bool,
    ) -> OrderResult:
        executed = D(raw.get("executed_amount") or 0)
        average = D(raw.get("average_price") or 0)
        ordered = D(raw.get("start_amount") or fallback_amount)
        status, reason = classify_order(str(raw.get("status") or ""), executed, ordered)
        fee_jpy, fee_btc, estimated = self._fees(raw, order_id, executed, average)
        notional = executed * average
        slog(
            "ORDER_STATUS",
            "order status",
            order_id=order_id,
            status=status,
            reason=reason,
            executed_amount=str(executed),
            fee_jpy=str(fee_jpy),
            fee_estimated=estimated,
        )
        if reason == "canceled":
            return OrderResult(
                True,
                "canceled",
                False,
                False,
                order_id,
                status,
                ZERO,
                average,
                None,
                raw,
                fee_jpy,
                fee_btc,
                estimated,
                executed,
                notional,
                fee_jpy,
                fee_btc,
            )
        if executed <= ZERO or reason == "accepted_unfilled":
            if not unfilled_ok:
                return OrderResult(
                    False, "poll_failed", False, False, order_id, status, ZERO, ZERO, None, raw
                )
            return OrderResult(
                True,
                "accepted_unfilled",
                False,
                False,
                order_id,
                status,
                ZERO,
                ZERO,
                None,
                raw,
            )
        stage = "FILL" if reason == "fill" else "ORDER_STATUS"
        slog(
            stage,
            "fill" if reason == "fill" else reason,
            order_id=order_id,
            executed_amount=str(executed),
            average_price=str(average),
            actual_execution_jpy=str(notional),
            status=status,
        )
        return OrderResult(
            True,
            reason,
            False,
            False,
            order_id,
            status,
            executed,
            average,
            notional,
            raw,
            fee_jpy,
            fee_btc,
            estimated,
            executed,
            notional,
            fee_jpy,
            fee_btc,
        )

    def place(
        self,
        signal: Signal,
        plan: AmountPlan,
        *,
        order_type: str | None = None,
    ) -> OrderResult:
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
                fee_jpy, fee_btc, estimated = self._fees(None, "", plan.amount, plan.price)
                slog(
                    "SIMULATED_FILL",
                    "paper fill only; Bitbank JPY unchanged",
                    executed_amount=str(plan.amount),
                    average_price=str(plan.price),
                    actual_execution_jpy=str(actual),
                    fee_jpy=str(fee_jpy),
                    fee_estimated=estimated,
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
                    fee_jpy,
                    fee_btc,
                    estimated,
                    plan.amount,
                    actual,
                    fee_jpy,
                    fee_btc,
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
        chosen = (order_type or self.cfg.order_type).lower()
        if chosen not in {"market", "limit"}:
            chosen = self.cfg.order_type
        price_str: str | None = None
        if chosen == "limit":
            q = quantize_price(plan.price, self.cfg.price_tick)
            price_str = str(int(q)) if q == q.to_integral_value() else str(q)
        raw = self.client.create_order(
            pair=self.cfg.pair,
            amount=str(plan.amount),
            side=plan.side,
            order_type=chosen,
            price=price_str,
            post_only=self.cfg.post_only if chosen == "limit" else None,
            live_confirmed=True,
        )
        order_id = str(raw.get("order_id") or "")
        slog("ORDER_ACCEPTED", "order accepted", order_id=order_id, status=raw.get("status"), type=chosen)
        executed = D(raw.get("executed_amount") or 0)
        if order_id and executed <= ZERO and str(raw.get("status") or "").upper() not in _CANCELED:
            refreshed = self._refresh_order(order_id)
            if refreshed:
                raw = refreshed
        return self._from_exchange(
            raw, fallback_amount=plan.amount, order_id=order_id, unfilled_ok=True
        )

    def poll(self, order_id: str, fallback_amount: Decimal) -> OrderResult:
        """Re-read a live order. Does not place a new order."""
        raw = self._refresh_order(order_id)
        if raw is None:
            return OrderResult(
                False, "poll_failed", False, False, order_id, None, ZERO, ZERO, None, None
            )
        return self._from_exchange(
            raw, fallback_amount=fallback_amount, order_id=order_id, unfilled_ok=True
        )

    def cancel(self, order_id: str) -> OrderResult:
        """Cancel one live order. DRY_RUN does not call the private API."""
        if not self.cfg.may_place_live_orders:
            return OrderResult(
                True,
                "canceled",
                self.cfg.dry_run,
                False,
                order_id,
                "CANCELED_UNFILLED",
                ZERO,
                ZERO,
                None,
                None,
            )
        cancel_fn = getattr(self.client, "cancel_order", None)
        if self.client is None or not callable(cancel_fn):
            return OrderResult(
                False, "cancel_unsupported", False, False, order_id, None, ZERO, ZERO, None, None
            )
        try:
            raw = cancel_fn(self.cfg.pair, order_id)
        except Exception as exc:
            slog("ERROR", "cancel_order failed", error=type(exc).__name__, order_id=order_id)
            return OrderResult(
                False, "cancel_failed", False, False, order_id, None, ZERO, ZERO, None, None
            )
        if not isinstance(raw, dict):
            raw = {"order_id": order_id, "status": "CANCELED_UNFILLED", "executed_amount": "0"}
        slog("ORDER_STATUS", "cancel requested", order_id=order_id, status=raw.get("status"))
        return self._from_exchange(
            raw, fallback_amount=ZERO, order_id=order_id, unfilled_ok=True
        )
