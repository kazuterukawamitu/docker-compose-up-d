from __future__ import annotations

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

TWOPLACES = Decimal("0.01")
BTC_QUANT = Decimal("0.0001")
JPY_TICK = Decimal("1")


def d(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        raise ValueError("cannot convert None to Decimal")
    return Decimal(str(value))


def quantize_btc(amount: Decimal, min_btc: Decimal = BTC_QUANT) -> Decimal:
    step = min_btc if min_btc > 0 else BTC_QUANT
    quantized = d(amount).quantize(step, rounding=ROUND_DOWN)
    return quantized if quantized >= 0 else Decimal("0")


def quantize_price(price: Decimal, tick: Decimal = JPY_TICK) -> Decimal:
    return d(price).quantize(tick, rounding=ROUND_HALF_UP)


def pct_change(lhs: Decimal, rhs: Decimal) -> Decimal:
    if rhs == 0:
        return Decimal("0")
    return (lhs - rhs) / rhs


def clamp_non_negative(value: Decimal) -> Decimal:
    return value if value > 0 else Decimal("0")
