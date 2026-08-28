"""Shared dataclasses used across market, strategy, risk, and orders."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from typing import Literal


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    LIMIT = "limit"
    MARKET = "market"


class OrderStatus(StrEnum):
    NEW = "NEW"
    OPEN = "OPEN"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCEL = "CANCEL"
    ERROR = "ERROR"


class MaTrend(StrEnum):
    UP = "up"
    DOWN = "down"
    FLAT = "flat"


@dataclass(frozen=True, slots=True)
class Candle:
    timestamp_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @property
    def time(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp_ms / 1000, tz=timezone.utc)


@dataclass(frozen=True, slots=True)
class Ticker:
    pair: str
    last: Decimal
    bid: Decimal
    ask: Decimal
    high: Decimal
    low: Decimal
    volume: Decimal
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class OrderBook:
    bids: tuple[tuple[Decimal, Decimal], ...]
    asks: tuple[tuple[Decimal, Decimal], ...]
    timestamp_ms: int


@dataclass(frozen=True, slots=True)
class Balance:
    asset: str
    free: Decimal
    locked: Decimal
    onhand: Decimal


@dataclass(frozen=True, slots=True)
class Signal:
    side: Side | None
    reason: str
    rule_id: int | None = None
    take_profit_pct: Decimal | None = None
    size_mode: Literal["max_available", "all"] = "max_available"

    @classmethod
    def hold(cls, reason: str = "no setup") -> Signal:
        return cls(side=None, reason=reason, rule_id=None)


@dataclass(slots=True)
class Position:
    pair: str
    amount_btc: Decimal = Decimal("0")
    entry_price: Decimal | None = None
    take_profit_pct: Decimal | None = None
    high_water: Decimal | None = None
    opened_at_ms: int | None = None

    @property
    def is_open(self) -> bool:
        return self.amount_btc > 0 and self.entry_price is not None


@dataclass(slots=True)
class OrderRecord:
    client_id: str
    pair: str
    side: Side
    order_type: OrderType
    amount: Decimal
    price: Decimal | None
    status: OrderStatus
    exchange_order_id: int | None = None
    executed_amount: Decimal = Decimal("0")
    average_price: Decimal | None = None
    dry_run: bool = True
    reason: str = ""
    created_at_ms: int = 0
    updated_at_ms: int = 0
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Snapshot:
    candles: tuple[Candle, ...]
    ticker: Ticker
    ma: tuple[Decimal, ...]
    fast_ma: tuple[Decimal, ...]
    slow_ma: tuple[Decimal, ...]
    rsi: tuple[Decimal, ...]
    macd: tuple[Decimal, ...]
    macd_signal: tuple[Decimal, ...]
    atr: tuple[Decimal, ...]
    bb_upper: tuple[Decimal, ...]
    bb_mid: tuple[Decimal, ...]
    bb_lower: tuple[Decimal, ...]
    ma_trend: MaTrend
    prev_ma_trend: MaTrend
