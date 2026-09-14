"""Order gate: DRY_RUN never hits create_order; duplicate active orders block."""

from __future__ import annotations

import time
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

    def get_trade_history(self, pair: str) -> list[dict[str, Any]]: ...

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
            return self.client.get_active_orders(self.cfg.pair)
        except Exception as exc:
            slog("ERROR", "active_orders failed", error=type(exc).__name__)
            raise

    def _recover_from_trades(self, side: str) -> dict[str, Any] | None:
        """If the POST filled immediately, it is gone from active_orders."""
        if self.client is None or not hasattr(self.client, "get_trade_history"):
            return None
        try:
            trades = list(self.client.get_trade_history(self.cfg.pair) or [])
        except Exception as exc:
            slog("ERROR", "trade_history failed during POST recovery", error=type(exc).__name__)
            return None
        now_ms = int(time.time() * 1000)
        window_ms = 120_000
        matches: list[dict[str, Any]] = []
        for row in trades:
            if str(row.get("side") or "").lower() != side.lower():
                continue
            if str(row.get("pair") or self.cfg.pair) != self.cfg.pair:
                continue
            executed_at = int(row.get("executed_at") or 0)
            if executed_at and executed_at < 10**12:
                executed_at *= 1000
            if not executed_at or now_ms - executed_at > window_ms:
                continue
            matches.append(row)
        order_ids = {str(row.get("order_id") or "") for row in matches if row.get("order_id")}
        if len(order_ids) != 1:
            slog(
                "ORDER_STATUS",
                "ambiguous post-timeout trades; refusing duplicate POST",
                count=len(matches),
                order_ids=len(order_ids),
                side=side,
            )
            return None
        order_id = next(iter(order_ids))
        refreshed = self._refresh_order(order_id)
        if refreshed:
            slog(
                "ORDER_ACCEPTED",
                "recovered filled order after uncertain POST",
                order_id=order_id,
            )
            return refreshed
        filled = ZERO
        notional = ZERO
        for row in matches:
            amt = D(row.get("amount") or 0)
            px = D(row.get("price") or 0)
            filled += amt
            notional += amt * px
        avg = (notional / filled) if filled > ZERO else ZERO
        slog(
            "ORDER_ACCEPTED",
            "recovered fill from trade_history after uncertain POST",
            order_id=order_id,
        )
        return {
            "order_id": order_id,
            "pair": self.cfg.pair,
            "side": side,
            "status": "FULLY_FILLED",
            "executed_amount": str(filled),
            "average_price": str(avg),
            "start_amount": str(filled),
        }

    def _recover_uncertain_order(self, side: str) -> dict[str, Any] | None:
        """After a POST timeout, reuse a matching open or just-filled order. Never POST again."""
        try:
            active = self.active_orders()
        except Exception:
            active = []
        matches = [
            row
            for row in active
            if str(row.get("side") or "").lower() == side.lower()
            and str(row.get("pair") or self.cfg.pair) == self.cfg.pair
        ]
        if len(matches) == 1:
            slog(
                "ORDER_ACCEPTED",
                "recovered order after uncertain POST",
                order_id=str(matches[0].get("order_id") or ""),
            )
            return matches[0]
        if len(matches) > 1:
            slog(
                "ORDER_STATUS",
                "ambiguous post-timeout orders; refusing duplicate POST",
                count=len(matches),
                side=side,
            )
            return None
        return self._recover_from_trades(side)

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
            if self.cfg.is_live_ready:
                slog(
                    "WOULD_SUBMIT_ORDER",
                    "LIVE_READY: not calling Bitbank create_order",
                    side=plan.side,
                    amount=str(plan.amount),
                    price=str(plan.price),
                    kind=signal.kind,
                    pair=self.cfg.pair,
                )
            slog(
                "ORDER_INTENT",
                "DRY_RUN: not calling Bitbank create_order"
                if not self.cfg.is_live_ready
                else "LIVE_READY intent only",
                side=plan.side,
                amount=str(plan.amount),
                price=str(plan.price),
                mode=self.cfg.trading_mode.upper(),
            )
            if self.cfg.dry_run and self.cfg.simulate_fill and not self.cfg.is_live_ready:
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
                "create_order failed; reconciling before any retry",
                error=type(exc).__name__,
            )
            recovered = self._recover_uncertain_order(plan.side)
            if recovered is None:
                detail = f"{type(exc).__name__} {exc}".lower()
                transient = any(
                    token in detail
                    for token in (
                        "timeout",
                        "timed out",
                        "connecterror",
                        "network",
                        "temporarily",
                    )
                )
                if transient:
                    slog(
                        "TRADE_BLOCKED",
                        "EXECUTION_BLOCKED",
                        reason="uncertain_order",
                        error=type(exc).__name__,
                    )
                    return OrderResult(
                        False,
                        "uncertain_order",
                        False,
                        False,
                        None,
                        None,
                        ZERO,
                        ZERO,
                        None,
                        None,
                    )
                raise
            raw = recovered
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
        return OrderResult(
            True, reason, False, False, order_id, status, executed, avg, actual, raw
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
