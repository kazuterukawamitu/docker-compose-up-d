"""JSON persistence for orders and the open position."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from bitbank_bot.models import OrderRecord, OrderStatus, OrderType, Position, Side


class JsonRepository:
    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir
        self._orders_path = data_dir / "orders.json"
        self._position_path = data_dir / "position.json"
        data_dir.mkdir(parents=True, exist_ok=True)

    def load_orders(self) -> list[OrderRecord]:
        if not self._orders_path.exists():
            return []
        raw = json.loads(self._orders_path.read_text(encoding="utf-8"))
        return [_order_from_dict(row) for row in raw]

    def save_orders(self, orders: list[OrderRecord]) -> None:
        payload = [_order_to_dict(row) for row in orders[-500:]]
        self._orders_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_position(self, pair: str) -> Position:
        if not self._position_path.exists():
            return Position(pair=pair)
        raw = json.loads(self._position_path.read_text(encoding="utf-8"))
        return Position(
            pair=str(raw.get("pair") or pair),
            amount_btc=Decimal(str(raw.get("amount_btc") or "0")),
            entry_price=_opt_dec(raw.get("entry_price")),
            take_profit_pct=_opt_dec(raw.get("take_profit_pct")),
            high_water=_opt_dec(raw.get("high_water")),
            opened_at_ms=raw.get("opened_at_ms"),
        )

    def save_position(self, position: Position) -> None:
        payload = {
            "pair": position.pair,
            "amount_btc": str(position.amount_btc),
            "entry_price": None if position.entry_price is None else str(position.entry_price),
            "take_profit_pct": None
            if position.take_profit_pct is None
            else str(position.take_profit_pct),
            "high_water": None if position.high_water is None else str(position.high_water),
            "opened_at_ms": position.opened_at_ms,
        }
        self._position_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _opt_dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _order_to_dict(row: OrderRecord) -> dict[str, Any]:
    return {
        "client_id": row.client_id,
        "pair": row.pair,
        "side": row.side.value,
        "order_type": row.order_type.value,
        "amount": str(row.amount),
        "price": None if row.price is None else str(row.price),
        "status": row.status.value,
        "exchange_order_id": row.exchange_order_id,
        "executed_amount": str(row.executed_amount),
        "average_price": None if row.average_price is None else str(row.average_price),
        "dry_run": row.dry_run,
        "reason": row.reason,
        "created_at_ms": row.created_at_ms,
        "updated_at_ms": row.updated_at_ms,
        "extra": row.extra,
    }


def _order_from_dict(row: dict[str, Any]) -> OrderRecord:
    return OrderRecord(
        client_id=str(row["client_id"]),
        pair=str(row["pair"]),
        side=Side(row["side"]),
        order_type=OrderType(row["order_type"]),
        amount=Decimal(str(row["amount"])),
        price=_opt_dec(row.get("price")),
        status=OrderStatus(row["status"]),
        exchange_order_id=row.get("exchange_order_id"),
        executed_amount=Decimal(str(row.get("executed_amount") or "0")),
        average_price=_opt_dec(row.get("average_price")),
        dry_run=bool(row.get("dry_run", True)),
        reason=str(row.get("reason") or ""),
        created_at_ms=int(row.get("created_at_ms") or 0),
        updated_at_ms=int(row.get("updated_at_ms") or 0),
        extra=dict(row.get("extra") or {}),
    )
