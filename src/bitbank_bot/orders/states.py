from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from bitbank_bot.decimal_utils import d
from bitbank_bot.models import Position


def load_position(path: Path) -> Position:
    if not path.is_file():
        return Position()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Position(
        amount=d(raw.get("amount", "0")),
        entry_price=d(raw.get("entry_price", "0")),
        take_profit_pct=d(raw.get("take_profit_pct", "0")),
        rule_id=str(raw.get("rule_id", "")),
        opened_ts=int(raw.get("opened_ts", 0)),
        bars_held=int(raw.get("bars_held", 0)),
    )


def save_position(path: Path, position: Position) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "amount": str(position.amount),
                "entry_price": str(position.entry_price),
                "take_profit_pct": str(position.take_profit_pct),
                "rule_id": position.rule_id,
                "opened_ts": position.opened_ts,
                "bars_held": position.bars_held,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def apply_fill(position: Position, side: str, amount: Decimal, price: Decimal, ts: int, take_profit_pct: Decimal | None, rule_id: str) -> Decimal:
    """Return realized JPY PnL from this fill."""
    if amount <= 0 or price <= 0:
        return Decimal("0")
    if side == "buy":
        if position.is_open:
            total = position.amount + amount
            position.entry_price = ((position.entry_price * position.amount) + (price * amount)) / total
            position.amount = total
        else:
            position.amount = amount
            position.entry_price = price
            position.opened_ts = ts
            position.bars_held = 0
        if take_profit_pct is not None:
            position.take_profit_pct = take_profit_pct
        position.rule_id = rule_id
        return Decimal("0")

    sell_qty = min(amount, position.amount if position.amount > 0 else amount)
    pnl = Decimal("0")
    if position.is_open:
        pnl = (price - position.entry_price) * sell_qty
        position.amount -= sell_qty
        if position.amount <= 0:
            position.amount = Decimal("0")
            position.entry_price = Decimal("0")
            position.take_profit_pct = Decimal("0")
            position.rule_id = ""
            position.bars_held = 0
    return pnl
