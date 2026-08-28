from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

Action = Literal["BUY", "SELL", "HOLD"]
Slope = Literal["up", "flat", "down"]


@dataclass(frozen=True)
class Candle:
    ts: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class Ticker:
    last: Decimal
    buy: Decimal
    sell: Decimal
    timestamp_ms: int
    high: Decimal | None = None
    low: Decimal | None = None
    volume: Decimal | None = None


@dataclass(frozen=True)
class AssetBalance:
    asset: str
    free: Decimal
    onhand: Decimal
    locked: Decimal


@dataclass
class Position:
    amount: Decimal = Decimal("0")
    entry_price: Decimal = Decimal("0")
    take_profit_pct: Decimal = Decimal("0")
    rule_id: str = ""
    opened_ts: int = 0
    bars_held: int = 0

    @property
    def is_open(self) -> bool:
        return self.amount > 0 and self.entry_price > 0

    def unrealized_pnl(self, last: Decimal) -> Decimal:
        if not self.is_open:
            return Decimal("0")
        return (last - self.entry_price) * self.amount


@dataclass(frozen=True)
class Signal:
    action: Action
    rule_id: str
    reason: str
    take_profit_pct: Decimal | None = None
    target_kind: Literal["min_unit", "max_available", "flatten"] = "min_unit"


@dataclass
class OrderRecord:
    client_tag: str
    order_id: int | None
    side: Literal["buy", "sell"]
    order_type: str
    target_amount: Decimal
    planned_amount: Decimal
    actual_amount: Decimal
    price: Decimal | None
    average_price: Decimal | None
    status: str
    dry_run: bool
    reason: str
    executed_amount: Decimal = Decimal("0")
    remaining_amount: Decimal | None = None


@dataclass
class Snapshot:
    candles: list[Candle]
    ticker: Ticker
    position: Position
    jpy_free: Decimal
    btc_free: Decimal
    circuit_mode: str = "NONE"
    ws_ok: bool = False
    now_ms: int = 0


@dataclass
class BotStats:
    started_ms: int = 0
    signals_seen: int = 0
    buys: int = 0
    sells: int = 0
    wins: int = 0
    losses: int = 0
    realized_pnl: Decimal = Decimal("0")
    daily_realized_pnl: Decimal = Decimal("0")
    last_signal: Signal | None = None
    last_block_reason: str = ""
    last_error: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def win_rate(self) -> Decimal:
        closed = self.wins + self.losses
        if closed == 0:
            return Decimal("0")
        return Decimal(self.wins) / Decimal(closed)
