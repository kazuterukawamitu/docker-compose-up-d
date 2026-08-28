from __future__ import annotations

import logging
from decimal import Decimal
from typing import Protocol

from bitbank_bot.config import Settings
from bitbank_bot.exchange.bitbank_rest import order_from_exchange
from bitbank_bot.logging_setup import log_event
from bitbank_bot.models import OrderRecord
from bitbank_bot.orders.sizing import SizePlan

log = logging.getLogger(__name__)


class OrderClient(Protocol):
    async def create_order(
        self,
        pair: str,
        side: str,
        order_type: str,
        amount: Decimal,
        price: Decimal | None,
    ) -> dict: ...

    async def get_order(self, pair: str, order_id: int) -> dict: ...

    async def active_orders(self, pair: str) -> list[dict]: ...


class OrderManager:
    def __init__(self, settings: Settings, client: OrderClient | None) -> None:
        self.settings = settings
        self.client = client
        self.in_flight = False
        self.last_order: OrderRecord | None = None

    async def submit(self, side: str, plan: SizePlan, reason: str, last_price: Decimal) -> OrderRecord:
        if self.in_flight:
            return _blocked(side, plan, "duplicate in-flight order")
        if plan.planned <= 0:
            return _blocked(side, plan, plan.blocked or "planned amount is zero")

        order_type = self.settings.order_type
        price = plan.price if order_type == "limit" else None
        self.in_flight = True
        try:
            if self.settings.dry_run or self.client is None:
                fill_price = last_price if price is None else price
                record = OrderRecord(
                    client_tag="dry-run",
                    order_id=None,
                    side=side,  # type: ignore[arg-type]
                    order_type=order_type,
                    target_amount=plan.target,
                    planned_amount=plan.planned,
                    actual_amount=plan.planned,
                    price=price,
                    average_price=fill_price,
                    status="DRY_FILLED",
                    dry_run=True,
                    reason=reason,
                    executed_amount=plan.planned,
                    remaining_amount=Decimal("0"),
                )
                log_event(
                    "ORDER_STATUS",
                    status=record.status,
                    side=side,
                    amount=plan.planned,
                    price=fill_price,
                    executed=plan.planned,
                    remaining=0,
                    dry_run=True,
                    order_id="none",
                )
                log_event(
                    "FILL",
                    side=side,
                    executed=plan.planned,
                    average_price=fill_price,
                    status=record.status,
                    dry_run=True,
                )
                self.last_order = record
                return record

            if self.client is None:
                return _blocked(side, plan, "no exchange client")
            active = await self.client.active_orders(self.settings.pair)
            if active:
                return _blocked(side, plan, f"active orders already exist n={len(active)}")
            payload = await self.client.create_order(
                self.settings.pair,
                side,
                order_type,
                plan.planned,
                price,
            )
            record = order_from_exchange(
                payload,
                dry_run=False,
                reason=reason,
                target=plan.target,
                planned=plan.planned,
            )
            if record.order_id is not None and record.executed_amount <= 0:
                live = await self.client.get_order(self.settings.pair, record.order_id)
                record = order_from_exchange(
                    live,
                    dry_run=False,
                    reason=reason,
                    target=plan.target,
                    planned=plan.planned,
                )
            log_event(
                "ORDER_STATUS",
                status=record.status,
                side=side,
                amount=plan.planned,
                executed=record.executed_amount,
                remaining=record.remaining_amount,
                order_id=record.order_id if record.order_id is not None else "none",
                dry_run=False,
            )
            if record.executed_amount > 0:
                log_event(
                    "FILL",
                    side=side,
                    executed=record.executed_amount,
                    average_price=record.average_price,
                    status=record.status,
                    order_id=record.order_id,
                    dry_run=False,
                )
            else:
                log.info(
                    "ORDER ACCEPTED but not filled side=%s status=%s remaining=%s order_id=%s",
                    side,
                    record.status,
                    record.remaining_amount,
                    record.order_id,
                )
            self.last_order = record
            return record
        finally:
            self.in_flight = False


def _blocked(side: str, plan: SizePlan, reason: str) -> OrderRecord:
    log_event("ORDER_STATUS", status="BLOCKED", side=side, reason=reason, amount=plan.planned)
    return OrderRecord(
        client_tag="blocked",
        order_id=None,
        side=side,  # type: ignore[arg-type]
        order_type="",
        target_amount=plan.target,
        planned_amount=plan.planned,
        actual_amount=Decimal("0"),
        price=plan.price,
        average_price=None,
        status="BLOCKED",
        dry_run=True,
        reason=reason,
        executed_amount=Decimal("0"),
    )
