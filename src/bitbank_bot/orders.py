"""Order gate: DRY_RUN never hits create_order; duplicate active orders block."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Protocol

from bitbank_bot.amounts import AmountPlan
from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO, quantize_price
from bitbank_bot.strategy import Signal


def _fill_status(raw_status: str, executed: Decimal, ordered: Decimal) -> str:
    if executed <= ZERO:
        return "UNFILLED"
    if ordered > ZERO and executed < ordered:
        return "PARTIALLY_FILLED"
    return "FULLY_FILLED"


class OrderClient(Protocol):
    def get_active_orders(self, pair: str) -> list[dict[str, Any]]: ...

    def create_order(
        self,
        pair: str,
        amount: str,
        side: str,
        order_type: str,
        price: str | None = None,
        post_only: bool | None = None,
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
        if not plan.ok or plan.amount <= ZERO:
            return OrderResult(
                False, plan.reason, self.cfg.dry_run, False, None, None, ZERO, ZERO, None, None
            )
        active = self.active_orders()
        if active:
            slog("ERROR", "duplicate prevention: active order exists", count=len(active))
            return OrderResult(
                False,
                "active_order_exists",
                self.cfg.dry_run,
                False,
                None,
                None,
                ZERO,
                ZERO,
                None,
                None,
            )
        price_str = None
        if self.cfg.order_type == "limit":
            price_str = str(quantize_price(plan.price, self.cfg.price_tick))
        if self.cfg.dry_run or not self.cfg.live_trading:
            slog(
                "ORDER_INTENT",
                "dry-run; create_order not called",
                kind=signal.kind,
                side=plan.side,
                amount=str(plan.amount),
                order_type=self.cfg.order_type,
            )
            if self.cfg.simulate_fill:
                filled = plan.amount
                avg = plan.price
                actual = filled * avg
                slog(
                    "SIMULATED_FILL",
                    "paper only; Bitbank JPY unchanged",
                    executed_amount=str(filled),
                    average_price=str(avg),
                    actual_execution_jpy=str(actual),
                    bitbank_jpy_unchanged=True,
                )
                return OrderResult(
                    True,
                    "simulated_fill",
                    True,
                    True,
                    "DRY_RUN",
                    "FULLY_FILLED",
                    filled,
                    avg,
                    actual,
                    None,
                )
            return OrderResult(
                True, "intent_only", True, False, None, None, ZERO, ZERO, None, None
            )
        if self.client is None:
            return OrderResult(
                False, "no_client", False, False, None, None, ZERO, ZERO, None, None
            )
        raw = self.client.create_order(
            pair=self.cfg.pair,
            amount=str(plan.amount),
            side=plan.side,
            order_type=self.cfg.order_type,
            price=price_str,
            post_only=self.cfg.post_only if self.cfg.order_type == "limit" else None,
        )
        order_id = str(raw.get("order_id") or "")
        status = str(raw.get("status") or "")
        slog("ORDER_ACCEPTED", "order accepted", order_id=order_id, status=status)
        executed = D(raw.get("executed_amount") or 0)
        avg = D(raw.get("average_price") or 0)
        amount_ordered = D(raw.get("start_amount") or plan.amount)
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
        slog(
            "FILL",
            "fill",
            order_id=order_id,
            executed_amount=str(executed),
            average_price=str(avg),
            actual_execution_jpy=str(actual),
        )
        return OrderResult(
            True, "fill", False, False, order_id, status, executed, avg, actual, raw
        )
