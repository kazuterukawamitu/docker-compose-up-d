"""Decimal money helpers. Never use float for price, amount, or fee."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_DOWN, Decimal, InvalidOperation
from typing import Any

ZERO = Decimal("0")
ONE = Decimal("1")
BTC_UNIT = Decimal("0.0001")
JPY_TICK = Decimal("1")


def D(value: object) -> Decimal:
    """Parse exchange strings/ints/Decimals. Empty or None becomes 0."""
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return ZERO
    if isinstance(value, bool):
        raise TypeError("bool is not allowed for money values")
    if isinstance(value, float):
        raise TypeError("float is not allowed for price/amount; pass str or Decimal")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise InvalidOperation(f"cannot convert {value!r} to Decimal") from exc


def to_decimal(value: Any) -> Decimal:
    """Strict parser used on order amounts — rejects empty/float/bool."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise TypeError("bool is not allowed for money values")
    if isinstance(value, float):
        raise TypeError("float is not allowed for price/amount; pass str or Decimal")
    if value is None or value == "":
        raise ValueError("empty money value")
    return D(value)


def truncate(value: Decimal, step: Decimal) -> Decimal:
    value = D(value)
    step = D(step)
    if step <= ZERO:
        raise ValueError("step must be positive")
    return (value // step) * step


def floor_btc(amount: Decimal | str | int) -> Decimal:
    return truncate(D(amount), BTC_UNIT)


def quantize_price(price: Decimal, tick: Decimal) -> Decimal:
    return truncate(D(price), D(tick))


def jpy_tick(price: Decimal | str | int, *, side: str | None = None) -> Decimal:
    price = D(price)
    if side and side.lower() == "sell":
        return price.to_integral_value(rounding=ROUND_CEILING)
    return price.to_integral_value(rounding=ROUND_DOWN)


def meets_min_amount(amount: Decimal, min_amount: Decimal) -> bool:
    return D(amount) >= D(min_amount) and D(amount) > ZERO


def pct_offset(price: Decimal, pct: Decimal) -> Decimal:
    return D(price) * (ONE + D(pct))
