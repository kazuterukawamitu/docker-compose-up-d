"""Order intent vs live execution. DRY_RUN never calls create_order."""

from __future__ import annotations

import json
import logging
from decimal import Decimal

from bitbank_bot.config import Settings
from bitbank_bot.exceptions import DuplicateOrderError
from bitbank_bot.models import AmountKind, AmountPlan, OrderRecord, OrderStatus, Signal
from bitbank_bot.money import to_decimal
from bitbank_bot.rest_client import BitbankRestClient

LOGGER = logging.getLogger("bitbank_bot.orders")


def parse_order_status(raw: str | None) -> OrderStatus:
    if not raw:
        return OrderStatus.UNFILLED
    try:
        return OrderStatus(raw)
    except ValueError:
        return OrderStatus.UNFILLED


class OrderManager:
    def __init__(self, rest: BitbankRestClient, settings: Settings) -> None:
        self.rest = rest
        self.settings = settings
        self.last: OrderRecord | None = None

    async def has_active_orders(self) -> bool:
        if self.settings.dry_run or not self.settings.has_keys:
            return False
        orders = await self.rest.active_orders(self.settings.pair)
        return bool(orders)

    async def submit(self, signal: Signal, plan: AmountPlan) -> OrderRecord:
        record = OrderRecord(
            pair=self.settings.pair,
            side=plan.side,
            order_type=self.settings.order_type,
            price=plan.price,
            planned_amount=plan.planned_amount,
            remaining_amount=plan.planned_amount,
            rule=signal.rule,
            dry_run=self.settings.dry_run,
            amount_kind=AmountKind.PLANNED,
            extra={
                "reason": signal.reason,
                "plan_reason": plan.reason,
                "target_amount": str(plan.target_amount),
                "size_hint": signal.size_hint,
                "crossover_price": str(signal.crossover_price) if signal.crossover_price else None,
            },
        )
        intent = {
            "event": "ORDER_INTENT",
            "pair": record.pair,
            "side": record.side,
            "type": record.order_type,
            "price": str(record.price),
            "amount": str(record.planned_amount),
            "rule": record.rule,
            "reason": signal.reason,
            "dry_run": self.settings.dry_run,
            "live_trading": self.settings.live_trading,
        }
        LOGGER.info("%s", json.dumps(intent, ensure_ascii=False))

        if self.settings.dry_run or not self.settings.live_trading:
            record.status = OrderStatus.DRY_RUN_INTENT
            record.executed_amount = plan.planned_amount
            record.remaining_amount = Decimal("0")
            record.average_price = plan.price
            record.amount_kind = AmountKind.ACTUAL_EXECUTION
            record.extra["simulated_fill"] = True
            self.last = record
            return record

        if await self.has_active_orders():
            raise DuplicateOrderError(f"active order already open for {self.settings.pair}")

        raw = await self.rest.create_order(
            pair=self.settings.pair,
            amount=str(plan.planned_amount),
            side=plan.side,
            order_type=self.settings.order_type,
            price=str(plan.price) if self.settings.order_type == "limit" else None,
            post_only=self.settings.post_only,
        )
        return self._from_exchange(record, raw)

    def _from_exchange(self, record: OrderRecord, raw: dict) -> OrderRecord:
        executed = to_decimal(raw.get("executed_amount") or "0")
        remaining = raw.get("remaining_amount")
        record.order_id = int(raw["order_id"]) if raw.get("order_id") is not None else None
        record.executed_amount = executed
        record.remaining_amount = to_decimal(remaining) if remaining is not None else None
        record.status = parse_order_status(raw.get("status"))
        if raw.get("average_price"):
            record.average_price = to_decimal(raw["average_price"])
        record.amount_kind = AmountKind.ACTUAL_EXECUTION
        if not record.is_fill():
            LOGGER.info(
                "order_id=%s status=%s executed_amount=0 — not treating as fill",
                record.order_id,
                record.status.value,
            )
        self.last = record
        return record
