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


def _finite(value: Decimal | None) -> bool:
    if value is None:
        return False
    return not (value.is_nan() or value.is_infinite()) and value > ZERO


def true_range(high: Decimal, low: Decimal, prev_close: Decimal) -> Decimal:
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
    """Wilder ATR. Returns None until the first full period is available."""
    n = min(len(highs), len(lows), len(closes))
    out: list[Decimal | None] = [None] * n
    if period < 1 or n < period + 1:
        return out
    trs: list[Decimal] = []
    for i in range(1, n):
        trs.append(true_range(highs[i], lows[i], closes[i - 1]))
    first = sum(trs[:period], ZERO) / D(period)
    out[period] = first
    prev = first
    for i in range(period, len(trs)):
        prev = (prev * D(period - 1) + trs[i]) / D(period)
        out[i + 1] = prev
    return out


def realized_vol(closes: Sequence[Decimal], period: int = 20) -> Decimal | None:
    """Simple close-to-close percent standard deviation (not annualized)."""
    if period < 2 or len(closes) < period + 1:
        return None
    window = list(closes[-(period + 1) :])
    rets: list[Decimal] = []
    for i in range(1, len(window)):
        prev = window[i - 1]
        if prev <= ZERO:
            return None
        rets.append((window[i] - prev) / prev)
    mean = sum(rets, ZERO) / D(len(rets))
    var = sum((item - mean) ** 2 for item in rets) / D(len(rets))
    if var < ZERO:
        return None
    # Decimal has no sqrt; Newton iteration is enough for a volatility scalar.
    guess = var
    if guess == ZERO:
        return ZERO
    for _ in range(16):
        if guess == ZERO:
            return ZERO
        guess = (guess + var / guess) / D(2)
    return guess


def adx(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    period: int = 14,
) -> list[Decimal | None]:
    """Wilder ADX. Values are 0–100 when defined."""
    n = min(len(highs), len(lows), len(closes))
    out: list[Decimal | None] = [None] * n
    if period < 1 or n < period * 2:
        return out
    plus_dm: list[Decimal] = []
    minus_dm: list[Decimal] = []
    trs: list[Decimal] = []
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm.append(up_move if up_move > down_move and up_move > ZERO else ZERO)
        minus_dm.append(down_move if down_move > up_move and down_move > ZERO else ZERO)
        trs.append(true_range(highs[i], lows[i], closes[i - 1]))
    if len(trs) < period:
        return out

    def _wilder(values: list[Decimal]) -> list[Decimal]:
        first = sum(values[:period], ZERO)
        series = [first]
        prev = first
        for item in values[period:]:
            prev = prev - (prev / D(period)) + item
            series.append(prev)
        return series

    atr_s = _wilder(trs)
    plus_s = _wilder(plus_dm)
    minus_s = _wilder(minus_dm)
    dxs: list[Decimal] = []
    for i, atr_v in enumerate(atr_s):
        if atr_v <= ZERO:
            dxs.append(ZERO)
            continue
        pdi = (plus_s[i] / atr_v) * D(100)
        mdi = (minus_s[i] / atr_v) * D(100)
        denom = pdi + mdi
        dxs.append(ZERO if denom <= ZERO else (abs(pdi - mdi) / denom) * D(100))
    if len(dxs) < period:
        return out
    adx_val = sum(dxs[:period], ZERO) / D(period)
    first_idx = period * 2
    if first_idx < n:
        out[first_idx] = adx_val
    for i, dx in enumerate(dxs[period:], start=first_idx + 1):
        adx_val = (adx_val * D(period - 1) + dx) / D(period)
        if i < n:
            out[i] = adx_val
    return out


def last_valid(series: Sequence[Decimal | None]) -> Decimal | None:
    for value in reversed(series):
        if _finite(value):
            return value
    return None
