"""SMA/EMA, MA trend, golden cross, and linear crossover interpolation."""

from __future__ import annotations

from collections import deque
from decimal import Decimal
from enum import Enum
from typing import Sequence

from bitbank_bot.money import D, ZERO


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


def moving_average(values: Sequence[Decimal], period: int, kind: str = "sma") -> list[Decimal | None]:
    if kind == "ema":
        return ema(values, period)
    return sma(values, period)


class IncrementalSMA:
    """Update SMA with each new close; do not rebuild the whole window unless reset."""

    def __init__(self, period: int) -> None:
        if period < 1:
            raise ValueError("period must be >= 1")
        self.period = period
        self._window: deque[Decimal] = deque()
        self._total = ZERO
        self.value: Decimal | None = None

    def update(self, price: Decimal) -> Decimal | None:
        price = D(price)
        self._window.append(price)
        self._total += price
        if len(self._window) > self.period:
            self._total -= self._window.popleft()
        if len(self._window) == self.period:
            self.value = self._total / D(self.period)
        else:
            self.value = None
        return self.value

    def reset(self) -> None:
        self._window.clear()
        self._total = ZERO
        self.value = None


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


def crossed_up(prev_close: Decimal, prev_ma: Decimal, close: Decimal, ma: Decimal) -> bool:
    return prev_close <= prev_ma and close > ma


def crossed_down(prev_close: Decimal, prev_ma: Decimal, close: Decimal, ma: Decimal) -> bool:
    return prev_close >= prev_ma and close < ma


def interpolate_crossover(
    prev_price: Decimal,
    prev_ma: Decimal,
    curr_price: Decimal,
    curr_ma: Decimal,
) -> Decimal | None:
    dp = curr_price - prev_price
    dm = curr_ma - prev_ma
    denom = dp - dm
    if denom == ZERO:
        return None
    t = (prev_ma - prev_price) / denom
    if t < ZERO or t > D("1"):
        return None
    return prev_price + t * dp


def rsi(values: Sequence[Decimal], period: int = 14) -> list[Decimal | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[Decimal | None] = [None]
    gains = ZERO
    losses = ZERO
    for i in range(1, len(values)):
        change = values[i] - values[i - 1]
        gain = change if change > ZERO else ZERO
        loss = -change if change < ZERO else ZERO
        if i <= period:
            gains += gain
            losses += loss
            if i < period:
                out.append(None)
                continue
            avg_gain = gains / D(period)
            avg_loss = losses / D(period)
        else:
            avg_gain = (avg_gain * D(period - 1) + gain) / D(period)
            avg_loss = (avg_loss * D(period - 1) + loss) / D(period)
        if avg_loss == ZERO:
            out.append(D("100") if avg_gain > ZERO else D("50"))
        else:
            rs = avg_gain / avg_loss
            out.append(D("100") - (D("100") / (D("1") + rs)))
    return out


def macd(
    values: Sequence[Decimal],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[Decimal | None], list[Decimal | None], list[Decimal | None]]:
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    line: list[Decimal | None] = []
    for a, b in zip(fast_ema, slow_ema, strict=True):
        if a is None or b is None:
            line.append(None)
        else:
            line.append(a - b)
    compact = [x for x in line if x is not None]
    pad = len(line) - len(compact)
    sig_compact = ema(compact, signal) if compact else []
    sig_line: list[Decimal | None] = [None] * pad + sig_compact
    hist: list[Decimal | None] = []
    for a, b in zip(line, sig_line, strict=True):
        if a is None or b is None:
            hist.append(None)
        else:
            hist.append(a - b)
    return line, sig_line, hist


def atr(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    period: int = 14,
) -> list[Decimal | None]:
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("highs, lows, and closes must be the same length")
    trs: list[Decimal] = []
    for i, (high, low, close) in enumerate(zip(highs, lows, closes, strict=True)):
        if i == 0:
            trs.append(high - low)
            continue
        prev = closes[i - 1]
        span = high - low
        up = high - prev if high > prev else prev - high
        down = low - prev if low > prev else prev - low
        trs.append(max(span, up, down))
    return sma(trs, period)


def bollinger(
    values: Sequence[Decimal],
    period: int = 20,
    k: Decimal = D("2"),
) -> tuple[list[Decimal | None], list[Decimal | None], list[Decimal | None]]:
    mid = sma(values, period)
    upper: list[Decimal | None] = []
    lower: list[Decimal | None] = []
    k = D(k)
    for i, mean in enumerate(mid):
        if mean is None:
            upper.append(None)
            lower.append(None)
            continue
        window = values[i + 1 - period : i + 1]
        var = sum((v - mean) * (v - mean) for v in window) / D(period)
        stdev = var.sqrt()
        band = k * stdev
        upper.append(mean + band)
        lower.append(mean - band)
    return mid, upper, lower
