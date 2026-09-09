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


def _wilder_smooth(values: Sequence[Decimal], period: int) -> list[Decimal | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[Decimal | None] = []
    acc = ZERO
    prev: Decimal | None = None
    for i, value in enumerate(values):
        if i + 1 < period:
            acc += value
            out.append(None)
            continue
        if prev is None:
            acc += value
            prev = acc / D(period)
            out.append(prev)
            continue
        prev = prev - (prev / D(period)) + value
        out.append(prev)
    return out


def true_range(
    high: Decimal, low: Decimal, prev_close: Decimal
) -> Decimal:
    span = high - low
    up = abs(high - prev_close)
    down = abs(low - prev_close)
    return max(span, up, down)


def atr(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    period: int = 14,
) -> list[Decimal | None]:
    if len(highs) != len(lows) or len(highs) != len(closes):
        raise ValueError("atr series length mismatch")
    ranges: list[Decimal] = []
    for i, (high, low, close) in enumerate(zip(highs, lows, closes)):
        prev = closes[i - 1] if i else close
        ranges.append(true_range(high, low, prev))
    return _wilder_smooth(ranges, period)


def realized_vol_pct(closes: Sequence[Decimal], period: int = 14) -> Decimal | None:
    if period < 1 or len(closes) < period + 1:
        return None
    total = ZERO
    for i in range(len(closes) - period, len(closes)):
        prev = closes[i - 1]
        if prev <= ZERO:
            return None
        total += abs(closes[i] - prev) / prev
    return total / D(period)


def adx(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    period: int = 14,
) -> list[Decimal | None]:
    """Wilder ADX. None until enough bars exist; never raises on short series."""
    n = len(closes)
    if n != len(highs) or n != len(lows) or n < 2:
        return [None] * n
    plus_dm: list[Decimal] = []
    minus_dm: list[Decimal] = []
    ranges: list[Decimal] = []
    for i in range(n):
        if i == 0:
            plus_dm.append(ZERO)
            minus_dm.append(ZERO)
            ranges.append(highs[i] - lows[i])
            continue
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm.append(up_move if up_move > down_move and up_move > ZERO else ZERO)
        minus_dm.append(down_move if down_move > up_move and down_move > ZERO else ZERO)
        ranges.append(true_range(highs[i], lows[i], closes[i - 1]))
    tr_s = _wilder_smooth(ranges, period)
    plus_s = _wilder_smooth(plus_dm, period)
    minus_s = _wilder_smooth(minus_dm, period)
    dx_series: list[Decimal] = []
    dx_index: list[int] = []
    plus_di_last: Decimal | None = None
    minus_di_last: Decimal | None = None
    for i in range(n):
        tr_v, p_v, m_v = tr_s[i], plus_s[i], minus_s[i]
        if tr_v is None or p_v is None or m_v is None or tr_v <= ZERO:
            continue
        plus_di = (p_v / tr_v) * D(100)
        minus_di = (m_v / tr_v) * D(100)
        plus_di_last = plus_di
        minus_di_last = minus_di
        denom = plus_di + minus_di
        if denom <= ZERO:
            continue
        dx_series.append((abs(plus_di - minus_di) / denom) * D(100))
        dx_index.append(i)
    adx_out: list[Decimal | None] = [None] * n
    if len(dx_series) < period:
        return adx_out
    smoothed = _wilder_smooth(dx_series, period)
    for pos, value in zip(dx_index, smoothed):
        adx_out[pos] = value
    # last DI values are computed for callers that only need the latest ADX
    _ = (plus_di_last, minus_di_last)
    return adx_out


def last_defined(series: Sequence[Decimal | None]) -> Decimal | None:
    for value in reversed(series):
        if value is not None:
            return value
    return None
