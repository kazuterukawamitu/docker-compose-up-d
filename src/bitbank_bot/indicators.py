"""SMA/EMA, MA trend, golden cross, and linear crossover interpolation."""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Sequence

from bitbank_bot.money import D, ONE, ZERO


class Trend(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"


def sma(values: Sequence[Decimal], period: int) -> list[Decimal | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[Decimal | None] = []
    running = ZERO
    for i, value in enumerate(values):
        running += value
        if i >= period:
            running -= values[i - period]
        if i + 1 < period:
            out.append(None)
        else:
            out.append(running / D(period))
    return out


def ema(values: Sequence[Decimal], period: int) -> list[Decimal | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    k = D(2) / D(period + 1)
    out: list[Decimal | None] = []
    prev: Decimal | None = None
    running = ZERO
    for i, value in enumerate(values):
        running += value
        if i + 1 < period:
            out.append(None)
            continue
        if prev is None:
            prev = running / D(period)
            out.append(prev)
            continue
        prev = (value - prev) * k + prev
        out.append(prev)
    return out


def moving_average(
    values: Sequence[Decimal], period: int, kind: str = "sma"
) -> list[Decimal | None]:
    if kind == "ema":
        return ema(values, period)
    return sma(values, period)


def crossover_price_bp(cross_price: Decimal | None) -> Decimal | None:
    if cross_price is None:
        return None
    return D(cross_price) * D("0.01")


def ma_trend(ma: Decimal, prev_ma: Decimal, threshold: Decimal) -> Trend:
    if prev_ma == ZERO:
        return Trend.FLAT
    slope = (ma - prev_ma) / prev_ma
    if slope > threshold:
        return Trend.UP
    if slope < -threshold:
        return Trend.DOWN
    return Trend.FLAT


def is_golden_cross(
    short_prev: Decimal,
    long_prev: Decimal,
    short_curr: Decimal,
    long_curr: Decimal,
) -> bool:
    return short_prev <= long_prev and short_curr > long_curr


def is_dead_cross(
    short_prev: Decimal,
    long_prev: Decimal,
    short_curr: Decimal,
    long_curr: Decimal,
) -> bool:
    return short_prev >= long_prev and short_curr < long_curr


def crossed_up(
    prev_close: Decimal, prev_ma: Decimal, close: Decimal, ma: Decimal
) -> bool:
    return prev_close <= prev_ma and close > ma


def crossed_down(
    prev_close: Decimal, prev_ma: Decimal, close: Decimal, ma: Decimal
) -> bool:
    return prev_close >= prev_ma and close < ma


def interpolate_crossover(
    prev_price: Decimal,
    prev_ma: Decimal,
    price: Decimal,
    ma: Decimal,
) -> Decimal | None:
    dp = price - prev_price
    dm = ma - prev_ma
    denom = dp - dm
    if denom == ZERO:
        return None
    t = (prev_ma - prev_price) / denom
    if t < ZERO or t > ONE:
        return None
    return prev_price + t * dp


def true_range(high: Decimal, low: Decimal, prev_close: Decimal) -> Decimal:
    a = high - low
    b = abs(high - prev_close)
    c = abs(low - prev_close)
    return max(a, b, c)


def atr(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    period: int,
) -> list[Decimal | None]:
    """Wilder ATR. Returns None until ``period`` true ranges exist."""
    if period < 1:
        raise ValueError("period must be >= 1")
    n = min(len(highs), len(lows), len(closes))
    out: list[Decimal | None] = [None] * n
    if n < 2:
        return out
    trs: list[Decimal] = []
    for i in range(1, n):
        trs.append(true_range(highs[i], lows[i], closes[i - 1]))
    if len(trs) < period:
        return out
    wilder = sum(trs[:period], ZERO) / D(period)
    out[period] = wilder
    for i in range(period, len(trs)):
        wilder = (wilder * D(period - 1) + trs[i]) / D(period)
        out[i + 1] = wilder
    return out
