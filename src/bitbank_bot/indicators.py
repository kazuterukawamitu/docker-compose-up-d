"""SMA/EMA, MA trend, golden cross, ATR/ADX/RSI, and crossover interpolation."""

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


def _true_range(high: Decimal, low: Decimal, prev_close: Decimal) -> Decimal:
    return max(high - low, abs(high - prev_close), abs(low - prev_close))


def atr(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    period: int = 14,
) -> list[Decimal | None]:
    """Wilder ATR. Returns None until ``period`` true ranges exist."""
    if period < 1:
        raise ValueError("period must be >= 1")
    if not (len(highs) == len(lows) == len(closes)):
        raise ValueError("high/low/close length mismatch")
    out: list[Decimal | None] = [None] * len(closes)
    if len(closes) < period + 1:
        return out
    trs: list[Decimal] = []
    for i in range(1, len(closes)):
        trs.append(_true_range(highs[i], lows[i], closes[i - 1]))
    first = sum(trs[:period], ZERO) / D(period)
    out[period] = first
    prev = first
    wilder = D(period)
    for i, tr in enumerate(trs[period:], start=period + 1):
        prev = (prev * (wilder - ONE) + tr) / wilder
        out[i] = prev
    return out


def last_finite(
    series: Sequence[Decimal | None], *, require_positive: bool = True
) -> Decimal | None:
    for value in reversed(series):
        if value is None:
            continue
        if value.is_nan() or value.is_infinite():
            return None
        if require_positive and value <= ZERO:
            return None
        return value
    return None


def rsi(closes: Sequence[Decimal], period: int = 14) -> list[Decimal | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[Decimal | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = ZERO
    losses = ZERO
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        if delta >= ZERO:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / D(period)
    avg_loss = losses / D(period)
    if avg_loss == ZERO:
        out[period] = D("100")
    else:
        rs = avg_gain / avg_loss
        out[period] = D("100") - (D("100") / (ONE + rs))
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        gain = delta if delta > ZERO else ZERO
        loss = -delta if delta < ZERO else ZERO
        avg_gain = (avg_gain * D(period - 1) + gain) / D(period)
        avg_loss = (avg_loss * D(period - 1) + loss) / D(period)
        if avg_loss == ZERO:
            out[i] = D("100")
        else:
            rs = avg_gain / avg_loss
            out[i] = D("100") - (D("100") / (ONE + rs))
    return out


def realized_vol(closes: Sequence[Decimal], period: int = 20) -> Decimal | None:
    """Close-to-close standard deviation of simple returns."""
    if period < 2 or len(closes) < period + 1:
        return None
    window = list(closes[-(period + 1) :])
    rets: list[Decimal] = []
    for i in range(1, len(window)):
        if window[i - 1] <= ZERO:
            return None
        rets.append((window[i] - window[i - 1]) / window[i - 1])
    if len(rets) < 2:
        return None
    mean = sum(rets, ZERO) / D(len(rets))
    var = sum((item - mean) ** 2 for item in rets) / D(len(rets) - 1)
    if var < ZERO:
        return None
    return var.sqrt()


def adx(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    period: int = 14,
) -> list[Decimal | None]:
    """Wilder ADX. None until enough bars exist."""
    n = len(closes)
    if not (len(highs) == len(lows) == n):
        raise ValueError("high/low/close length mismatch")
    out: list[Decimal | None] = [None] * n
    if n < (2 * period) + 1 or period < 1:
        return out
    plus_dm = [ZERO] * n
    minus_dm = [ZERO] * n
    tr = [ZERO] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if up > down and up > ZERO else ZERO
        minus_dm[i] = down if down > up and down > ZERO else ZERO
        tr[i] = _true_range(highs[i], lows[i], closes[i - 1])
    atr_s = sum(tr[1 : period + 1], ZERO)
    plus_s = sum(plus_dm[1 : period + 1], ZERO)
    minus_s = sum(minus_dm[1 : period + 1], ZERO)
    dx_vals: list[Decimal] = []
    wilder = D(period)
    for i in range(period + 1, n):
        atr_s = atr_s - (atr_s / wilder) + tr[i]
        plus_s = plus_s - (plus_s / wilder) + plus_dm[i]
        minus_s = minus_s - (minus_s / wilder) + minus_dm[i]
        if atr_s <= ZERO:
            continue
        plus_di = D("100") * plus_s / atr_s
        minus_di = D("100") * minus_s / atr_s
        denom = plus_di + minus_di
        dx = ZERO if denom <= ZERO else (D("100") * abs(plus_di - minus_di) / denom)
        dx_vals.append(dx)
        if len(dx_vals) == period:
            out[i] = sum(dx_vals, ZERO) / wilder
        elif len(dx_vals) > period:
            prev = out[i - 1]
            if prev is None:
                continue
            out[i] = (prev * (wilder - ONE) + dx) / wilder
    return out
