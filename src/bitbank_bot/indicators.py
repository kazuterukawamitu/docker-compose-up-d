"""SMA, EMA, MA slope, and linearly interpolated crossovers."""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from typing import Sequence

from bitbank_bot.models import Trend
from bitbank_bot.money import to_decimal

ONE_PCT = Decimal("0.01")
ZERO = Decimal("0")


class IncrementalSMA:
    """Rolling SMA. Call update() only for new closes — never rebuild from full history."""

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError("period must be >= 1")
        self.period = period
        self.window: deque[Decimal] = deque()
        self.total = Decimal("0")
        self.value: Decimal | None = None

    def seed(self, closes: list[Decimal]) -> Decimal | None:
        self.window.clear()
        self.total = Decimal("0")
        self.value = None
        for close in closes:
            self.update(close)
        return self.value

    def update(self, close: Decimal) -> Decimal | None:
        close = to_decimal(close)
        self.window.append(close)
        self.total += close
        if len(self.window) > self.period:
            self.total -= self.window.popleft()
        if len(self.window) == self.period:
            self.value = self.total / Decimal(self.period)
        else:
            self.value = None
        return self.value


class IncrementalEMA:
    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError("period must be >= 1")
        self.period = period
        self.k = Decimal(2) / Decimal(period + 1)
        self._seed: list[Decimal] = []
        self.value: Decimal | None = None

    def seed(self, closes: list[Decimal]) -> Decimal | None:
        self._seed = []
        self.value = None
        for close in closes:
            self.update(close)
        return self.value

    def update(self, close: Decimal) -> Decimal | None:
        close = to_decimal(close)
        if self.value is None:
            self._seed.append(close)
            if len(self._seed) >= self.period:
                total = sum(self._seed[-self.period :], Decimal("0"))
                self.value = total / Decimal(self.period)
            return self.value
        self.value = close * self.k + self.value * (Decimal("1") - self.k)
        return self.value


def sma(values: Sequence[Decimal], period: int) -> Decimal | None:
    if period < 1 or len(values) < period:
        return None
    window = list(values[-period:])
    return sum(window, Decimal("0")) / Decimal(period)


def ema(values: Sequence[Decimal], period: int) -> Decimal | None:
    calc = IncrementalEMA(period)
    return calc.seed(list(values))


def moving_average(values: Sequence[Decimal], period: int, kind: str = "sma") -> Decimal | None:
    if kind == "ema":
        return ema(list(values), period)
    return sma(list(values), period)


def ma_slope(current: Decimal, previous: Decimal) -> Decimal:
    current = to_decimal(current)
    previous = to_decimal(previous)
    if previous == 0:
        return Decimal("0")
    return (current - previous) / previous


def classify_trend(slope: Decimal, threshold: Decimal) -> Trend:
    slope = to_decimal(slope)
    threshold = to_decimal(threshold)
    if slope > threshold:
        return Trend.UP
    if slope < -threshold:
        return Trend.DOWN
    return Trend.FLAT


def ma_trend(ma: Decimal, prev_ma: Decimal, threshold: Decimal) -> Trend:
    return classify_trend(ma_slope(ma, prev_ma), threshold)


def interpolate_crossover(
    price_prev: Decimal,
    price_curr: Decimal,
    ma_prev: Decimal,
    ma_curr: Decimal,
) -> Decimal | None:
    """Linear interpolation of the price/MA intersection on the current bar."""
    p0 = to_decimal(price_prev)
    p1 = to_decimal(price_curr)
    m0 = to_decimal(ma_prev)
    m1 = to_decimal(ma_curr)
    denom = (p1 - p0) - (m1 - m0)
    if denom == 0:
        return None
    t = (m0 - p0) / denom
    if t < 0 or t > 1:
        return None
    return p0 + t * (p1 - p0)


def crossover_bundle(
    price_prev: Decimal,
    price_curr: Decimal,
    ma_prev: Decimal,
    ma_curr: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    price = interpolate_crossover(price_prev, price_curr, ma_prev, ma_curr)
    if price is None:
        return None, None
    return price, price * ONE_PCT


def crossed_up(price_prev: Decimal, price_curr: Decimal, ma_prev: Decimal, ma_curr: Decimal) -> bool:
    return price_prev <= ma_prev and price_curr > ma_curr


def crossed_down(price_prev: Decimal, price_curr: Decimal, ma_prev: Decimal, ma_curr: Decimal) -> bool:
    return price_prev >= ma_prev and price_curr < ma_curr


def golden_cross(
    short_prev: Decimal,
    short_curr: Decimal,
    long_prev: Decimal,
    long_curr: Decimal,
) -> bool:
    return short_prev <= long_prev and short_curr > long_curr


is_golden_cross = golden_cross
