"""Order gate: DRY_RUN/LIVE_READY never hit create_order; live POST is not retried."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO, ensure_decimal, quantize_price
from bitbank_bot.rest_client import BitbankAPIError
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
        identifier: str | None = None,
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

    def place(
        self, signal: Signal, plan: AmountPlan, request_id: str | None = None
    ) -> OrderResult:
        slog(
            "ORDER_REQUESTED",
            "order request",
            kind=signal.kind,
            side=plan.side,
            amount=str(plan.amount),
            price=str(plan.price),
            target_jpy=str(plan.target_jpy),
            planned_order_jpy=str(plan.planned_order_jpy),
            actual_execution_jpy="unset",
            request_id=request_id or "",
            pair=self.cfg.pair,
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
            mode = self.cfg.trading_mode.upper() if self.cfg.trading_mode else (
                "DRY_RUN" if self.cfg.dry_run else "LIVE_READY"
            )
            if self.cfg.trading_mode == "live_ready" or (
                not self.cfg.dry_run and not self.cfg.may_place_live_orders
            ):
                slog(
                    "WOULD_SUBMIT_ORDER",
                    "LIVE_READY: not calling Bitbank create_order",
                    pair=self.cfg.pair,
                    side=plan.side,
                    amount=str(plan.amount),
                    price=str(plan.price),
                    request_id=request_id or "",
                    mode=mode,
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
        identifier = f"bb{(request_id or uuid.uuid4().hex)[:16]}"
        try:
            raw = self.client.create_order(
                pair=self.cfg.pair,
                amount=str(plan.amount),
                side=plan.side,
                order_type=self.cfg.order_type,
                price=price_str,
                post_only=self.cfg.post_only if self.cfg.order_type == "limit" else None,
                identifier=identifier,
                live_confirmed=True,
            )
        except BitbankAPIError as exc:
            recovered = self._recover_unknown_submit(identifier, plan, exc)
            if recovered is not None:
                raw = recovered
            else:
                slog(
                    "ERROR",
                    "create_order failed; not retrying POST",
                    error=type(exc).__name__,
                    endpoint=getattr(exc, "endpoint", ""),
                    http_status=getattr(exc, "http_status", None),
                    bitbank_code=getattr(exc, "code", None),
                    unknown_submit=bool(getattr(exc, "unknown_submit", False)),
                )
                raise
        except Exception:
            recovered = self._recover_unknown_submit(identifier, plan, None)
            if recovered is None:
                raise
            raw = recovered
        order_id = str(raw.get("order_id") or "")
        status = str(raw.get("status") or "")
        slog("ORDER_ACCEPTED", "order accepted", order_id=order_id, status=status)
        slog("ORDER_ID_RECEIVED", "order id", order_id=order_id, identifier=identifier)
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
        if executed <= ZERO:
            slog("ORDER_ACTIVE", "no fill yet; not logging FILL", order_id=order_id, status=status)
            slog("ORDER_STATUS", "no fill yet; not logging FILL", order_id=order_id, status=status)
            return OrderResult(
                True, "accepted_unfilled", False, False, order_id, status, ZERO, ZERO, None, raw
            )
        actual = executed * avg
        reason = "partial_fill" if status == "PARTIALLY_FILLED" else "fill"
        slog(
            "PARTIALLY_FILLED" if reason == "partial_fill" else "FULLY_FILLED",
            "fill" if reason == "fill" else "partial fill; keep polling",
            order_id=order_id,
            executed_amount=str(executed),
            average_price=str(avg),
            actual_execution_jpy=str(actual),
            remaining_amount=str(max(ZERO, amount_ordered - executed)),
            status=status,
        )
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

    def _recover_unknown_submit(
        self,
        identifier: str,
        plan: AmountPlan,
        exc: BaseException | None,
    ) -> dict[str, Any] | None:
        unknown = bool(getattr(exc, "unknown_submit", False)) if exc is not None else True
        if not unknown or self.client is None:
            return None
        slog(
            "ORDER_STATUS",
            "POST outcome unknown; searching open orders before any resend",
            identifier=identifier,
            error=type(exc).__name__ if exc else "unknown",
        )
        try:
            active = self.active_orders()
        except Exception as list_exc:
            slog("ERROR", "cannot list orders after unknown submit", error=type(list_exc).__name__)
            return None
        for row in active:
            if str(row.get("identifier") or "") == identifier:
                slog("ORDER_ACCEPTED", "recovered order by identifier", order_id=row.get("order_id"))
                return row
            if (
                str(row.get("side") or "") == plan.side
                and D(row.get("start_amount") or 0) == plan.amount
            ):
                slog("ORDER_ACCEPTED", "recovered matching open order", order_id=row.get("order_id"))
                return row
        slog("ORDER_STATUS", "no matching open order after unknown submit; not resending")
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
