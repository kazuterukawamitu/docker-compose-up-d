"""Order lifecycle: NEW → OPEN → PARTIAL/FILLED/CANCEL/ERROR. Dry-run never hits POST /order."""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal

from bitbank_bot.config import Settings
from bitbank_bot.exchange.auth import unix_ms
from bitbank_bot.exchange.rest import BitbankRest
from bitbank_bot.models import OrderRecord, OrderStatus, OrderType, Position, Side, Ticker
from bitbank_bot.orders.amount import (
    limit_price,
    order_payload_amount,
    validate_order_amount,
)
from bitbank_bot.orders.repository import JsonRepository

log = logging.getLogger("bitbank_bot.orders")

_STATUS_MAP = {
    "UNFILLED": OrderStatus.OPEN,
    "PARTIALLY_FILLED": OrderStatus.PARTIAL,
    "FULLY_FILLED": OrderStatus.FILLED,
    "CANCELED_UNFILLED": OrderStatus.CANCEL,
    "CANCELED_PARTIALLY_FILLED": OrderStatus.CANCEL,
    "INACTIVE": OrderStatus.OPEN,
}


class OrderManager:
    def __init__(self, settings: Settings, rest: BitbankRest, repo: JsonRepository) -> None:
        self._settings = settings
        self._rest = rest
        self._repo = repo
        self.orders = repo.load_orders()
        self.position = repo.load_position(settings.pair)

    def persist(self) -> None:
        self._repo.save_orders(self.orders)
        self._repo.save_position(self.position)

    async def submit(
        self,
        *,
        side: Side,
        amount_btc: Decimal,
        ticker: Ticker,
        jpy_free: Decimal,
        btc_free: Decimal,
        reason: str,
        take_profit_pct: Decimal | None = None,
    ) -> OrderRecord:
        price = limit_price(side, ticker.last, ticker.bid, ticker.ask)
        sized = validate_order_amount(
            side, amount_btc, price, jpy_free, btc_free, self._settings
        )
        now = unix_ms()
        record = OrderRecord(
            client_id=str(uuid.uuid4()),
            pair=self._settings.pair,
            side=side,
            order_type=self._settings.order_type,
            amount=sized,
            price=price if self._settings.order_type is OrderType.LIMIT else None,
            status=OrderStatus.NEW,
            dry_run=self._settings.dry_run,
            reason=reason,
            created_at_ms=now,
            updated_at_ms=now,
        )
        self.orders.append(record)
        self.persist()
        log.info(
            "order NEW %s %s %s BTC @ %s (%s) dry_run=%s",
            side.value,
            self._settings.pair_display,
            sized,
            price,
            reason,
            self._settings.dry_run,
        )
        if self._settings.dry_run:
            self._fill_dry_run(record, price)
            self._apply_fill(record, take_profit_pct)
            self.persist()
            return record

        await self._rest.assert_spot_open()
        payload_amount = order_payload_amount(
            side, self._settings.order_type, sized, price, self._settings
        )
        try:
            raw = await self._rest.create_order(
                side=side,
                amount=payload_amount,
                order_type=self._settings.order_type,
                price=price if self._settings.order_type is OrderType.LIMIT else None,
            )
        except Exception:
            record.status = OrderStatus.ERROR
            record.updated_at_ms = unix_ms()
            self.persist()
            raise
        record.exchange_order_id = int(raw.get("order_id") or 0) or None
        record.status = _STATUS_MAP.get(str(raw.get("status") or ""), OrderStatus.OPEN)
        record.executed_amount = Decimal(str(raw.get("executed_amount") or "0"))
        avg = raw.get("average_price")
        record.average_price = Decimal(str(avg)) if avg not in (None, "") else None
        record.updated_at_ms = unix_ms()
        if record.status is OrderStatus.FILLED:
            self._apply_fill(record, take_profit_pct)
        self.persist()
        return record

    async def sync_open(self) -> None:
        if self._settings.dry_run:
            return
        opens = [o for o in self.orders if o.status in {OrderStatus.OPEN, OrderStatus.PARTIAL} and o.exchange_order_id]
        for record in opens:
            raw = await self._rest.get_order(record.exchange_order_id)
            record.status = _STATUS_MAP.get(str(raw.get("status") or ""), record.status)
            record.executed_amount = Decimal(str(raw.get("executed_amount") or record.executed_amount))
            avg = raw.get("average_price")
            if avg not in (None, ""):
                record.average_price = Decimal(str(avg))
            record.updated_at_ms = unix_ms()
            if record.status is OrderStatus.FILLED:
                self._apply_fill(record, None)
        self.persist()

    def _fill_dry_run(self, record: OrderRecord, price: Decimal) -> None:
        record.status = OrderStatus.FILLED
        record.executed_amount = record.amount
        record.average_price = price
        record.updated_at_ms = unix_ms()
        log.info("DRY_RUN fill %s %s @ %s", record.side.value, record.amount, price)

    def _apply_fill(self, record: OrderRecord, take_profit_pct: Decimal | None) -> None:
        fill_px = record.average_price or record.price
        if fill_px is None:
            return
        if record.side is Side.BUY:
            self.position.pair = record.pair
            self.position.amount_btc = record.executed_amount
            self.position.entry_price = fill_px
            self.position.take_profit_pct = take_profit_pct
            self.position.high_water = fill_px
            self.position.opened_at_ms = record.updated_at_ms
            return
        self.position = Position(pair=record.pair)
