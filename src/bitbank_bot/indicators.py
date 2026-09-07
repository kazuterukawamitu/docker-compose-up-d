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
    return value is not None and not value.is_nan() and not value.is_infinite() and value != ZERO


def rsi(closes: Sequence[Decimal], period: int = 14) -> list[Decimal | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[Decimal | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gain = ZERO
    loss = ZERO
    for i in range(1, period + 1):
        delta = closes[i] - closes[i - 1]
        if delta > ZERO:
            gain += delta
        else:
            loss -= delta
    avg_gain = gain / D(period)
    avg_loss = loss / D(period)
    if avg_loss == ZERO:
        out[period] = D(100)
    else:
        rs = avg_gain / avg_loss
        out[period] = D(100) - (D(100) / (ONE + rs))
    for i in range(period + 1, len(closes)):
        delta = closes[i] - closes[i - 1]
        g = delta if delta > ZERO else ZERO
        l = -delta if delta < ZERO else ZERO
        avg_gain = (avg_gain * D(period - 1) + g) / D(period)
        avg_loss = (avg_loss * D(period - 1) + l) / D(period)
        if avg_loss == ZERO:
            out[i] = D(100)
        else:
            rs = avg_gain / avg_loss
            out[i] = D(100) - (D(100) / (ONE + rs))
    return out


def macd(
    closes: Sequence[Decimal],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[Decimal | None], list[Decimal | None], list[Decimal | None]]:
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    line: list[Decimal | None] = []
    for a, b in zip(fast_ema, slow_ema):
        if a is None or b is None:
            line.append(None)
        else:
            line.append(a - b)
    filled = [v if v is not None else ZERO for v in line]
    first = next((i for i, v in enumerate(line) if v is not None), None)
    sig_raw = ema(filled, signal) if first is not None else [None] * len(closes)
    sig: list[Decimal | None] = []
    hist: list[Decimal | None] = []
    for i, value in enumerate(line):
        s = sig_raw[i] if first is not None and i >= first + signal - 1 else None
        if first is not None and i < first:
            s = None
        sig.append(s)
        if value is None or s is None:
            hist.append(None)
        else:
            hist.append(value - s)
    return line, sig, hist


def true_range(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
) -> list[Decimal | None]:
    out: list[Decimal | None] = []
    prev: Decimal | None = None
    for high, low, close in zip(highs, lows, closes):
        span = high - low
        if prev is None:
            out.append(span)
        else:
            out.append(max(span, abs(high - prev), abs(low - prev)))
        prev = close
    return out


def atr(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    period: int = 14,
) -> list[Decimal | None]:
    ranges = [v if v is not None else ZERO for v in true_range(highs, lows, closes)]
    return sma(ranges, period)


def adx(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    period: int = 14,
) -> list[Decimal | None]:
    n = len(closes)
    out: list[Decimal | None] = [None] * n
    if n < period + 2:
        return out
    plus_dm = [ZERO] * n
    minus_dm = [ZERO] * n
    tr = [ZERO] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if up > down and up > ZERO else ZERO
        minus_dm[i] = down if down > up and down > ZERO else ZERO
        span = highs[i] - lows[i]
        tr[i] = max(span, abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
    atr_s = ZERO
    plus = ZERO
    minus = ZERO
    dx_sum = ZERO
    for i in range(1, n):
        if i <= period:
            atr_s += tr[i]
            plus += plus_dm[i]
            minus += minus_dm[i]
            if i == period:
                plus_di = (plus / atr_s) * D(100) if atr_s else ZERO
                minus_di = (minus / atr_s) * D(100) if atr_s else ZERO
                denom = plus_di + minus_di
                dx = abs(plus_di - minus_di) / denom * D(100) if denom else ZERO
                dx_sum = dx
        else:
            atr_s = atr_s - (atr_s / D(period)) + tr[i]
            plus = plus - (plus / D(period)) + plus_dm[i]
            minus = minus - (minus / D(period)) + minus_dm[i]
            plus_di = (plus / atr_s) * D(100) if atr_s else ZERO
            minus_di = (minus / atr_s) * D(100) if atr_s else ZERO
            denom = plus_di + minus_di
            dx = abs(plus_di - minus_di) / denom * D(100) if denom else ZERO
            if i < period * 2:
                dx_sum += dx
                if i == period * 2 - 1:
                    out[i] = dx_sum / D(period)
            else:
                prev = out[i - 1]
                if prev is not None:
                    out[i] = (prev * D(period - 1) + dx) / D(period)
    return out


def realized_vol(closes: Sequence[Decimal], period: int = 14) -> Decimal | None:
    if len(closes) < period + 1:
        return None
    window = list(closes[-(period + 1) :])
    rets: list[Decimal] = []
    for i in range(1, len(window)):
        if window[i - 1] == ZERO:
            continue
        rets.append((window[i] - window[i - 1]) / window[i - 1])
    if len(rets) < 2:
        return None
    mean = sum(rets, ZERO) / D(len(rets))
    var = sum((r - mean) * (r - mean) for r in rets) / D(len(rets))
    if var <= ZERO:
        return ZERO
    # Decimal has no sqrt on older contexts; use exponent
    return var.sqrt()


def last_defined(series: Sequence[Decimal | None]) -> Decimal | None:
    for value in reversed(series):
        if value is None:
            continue
        if value.is_nan() or value.is_infinite():
            return None
        return value
    return None


def atr_is_abnormal(
    atr_value: Decimal | None,
    price: Decimal,
    max_atr_pct: Decimal,
) -> bool:
    if atr_value is None or not _finite(atr_value):
        return True
    if price <= ZERO:
        return True
    return (atr_value / price) > max_atr_pct
