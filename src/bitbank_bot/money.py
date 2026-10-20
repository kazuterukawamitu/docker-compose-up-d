"""Decimal money helpers. Never use float for price, amount, or fee."""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_DOWN, Decimal, InvalidOperation
from typing import Any

ZERO = Decimal("0")
ONE = Decimal("1")
BTC_UNIT = Decimal("0.0001")
JPY_TICK = Decimal("1")


def D(value: object) -> Decimal:
    """Parse exchange strings/ints/Decimals. Empty or None becomes 0.

    JSON numbers from Bitbank arrive as ``int`` or ``float``. Those are
    accepted via ``str(...)`` so candle/ticker parsing cannot raise
    "number expected" / InvalidOperation on otherwise valid market data.
    """
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return ZERO
    if isinstance(value, bool):
        raise TypeError("bool is not allowed for money values")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise InvalidOperation(f"non-finite float {value!r}")
        return Decimal(str(value))
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
    if value is None or value == "":
        raise ValueError("empty money value")
    return D(value)


def ensure_decimal(value: object, name: str) -> Decimal:
    """Validate order fields. Logs the variable name, never secret values."""
    if value is None or value == "":
        raise InvalidOperation(f"{name}: number expected (empty)")
    if isinstance(value, bool):
        raise InvalidOperation(f"{name}: number expected (bool)")
    try:
        parsed = D(value)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise InvalidOperation(f"{name}: number expected ({type(value).__name__})") from exc
    if parsed.is_nan() or parsed.is_infinite():
        raise InvalidOperation(f"{name}: number expected (non-finite)")
    return parsed


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


def incremental_fee_jpy(prev_fee: Decimal, new_fee: Decimal | None) -> Decimal | None:
    """Fee for the new slice when the exchange reports a cumulative quote fee."""
    if new_fee is None:
        return None
    delta = D(new_fee) - D(prev_fee)
    return delta if delta > ZERO else ZERO


def incremental_fill_cost(
    prev_qty: Decimal,
    prev_cost: Decimal,
    new_qty: Decimal,
    new_avg: Decimal,
) -> Decimal:
    """JPY for the new slice: cumulative_cost - previous_cost.

    Bitbank ``average_price`` is cumulative. ``new_avg * (new_qty - prev_qty)``
    understates a rising book.
    """
    total = D(new_qty) * D(new_avg)
    return total - D(prev_cost)


def realized_pnl_after_fees(
    proceeds: Decimal,
    cost: Decimal,
    fee_buffer: Decimal,
    buy_fee: Decimal | None = None,
    sell_fee: Decimal | None = None,
) -> Decimal:
    """Realized JPY after fees on both legs.

    Uses the actual fee when the caller has one; otherwise ``FEE_BUFFER``.
    """
    buy = D(buy_fee) if buy_fee is not None else D(cost) * D(fee_buffer)
    sell = D(sell_fee) if sell_fee is not None else D(proceeds) * D(fee_buffer)
    return D(proceeds) - D(cost) - buy - sell
