"""Poll Bitbank order status until fill, cancel, or rejection. Never treats order_id as a fill."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D, ZERO
from bitbank_bot.orders import OrderExecutor, OrderResult


@dataclass
class ExecutionSnapshot:
    order_id: str
    status: str
    executed_amount: Decimal
    remaining_amount: Decimal
    average_price: Decimal
    reason: str


class ExecutionMonitor:
    def __init__(self, executor: OrderExecutor) -> None:
        self.executor = executor

    def check(self, order_id: str, ordered_amount: Decimal) -> ExecutionSnapshot:
        result = self.executor.poll(order_id, ordered_amount)
        executed = result.executed_amount if result.ok else ZERO
        remaining = max(ZERO, D(ordered_amount) - executed)
        status = result.status or "UNKNOWN"
        slog(
            "ORDER_ACTIVE" if executed <= ZERO else (
                "PARTIALLY_FILLED" if result.reason == "partial_fill" else "FULLY_FILLED"
            ),
            "execution monitor",
            order_id=order_id,
            status=status,
            executed_amount=str(executed),
            remaining_amount=str(remaining),
            ok=result.ok,
            reason=result.reason,
        )
        return ExecutionSnapshot(
            order_id=order_id,
            status=status,
            executed_amount=executed,
            remaining_amount=remaining,
            average_price=result.average_price,
            reason=result.reason,
        )

    def result_from_poll(self, order_id: str, ordered_amount: Decimal) -> OrderResult:
        return self.executor.poll(order_id, ordered_amount)
