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


def _wilder_seed(values: Sequence[Decimal], period: int) -> Decimal | None:
    if len(values) < period:
        return None
    total = ZERO
    for item in values[:period]:
        total += item
    return total / D(period)


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
    """Wilder ATR. Index aligned with ``closes``."""
    n = len(closes)
    out: list[Decimal | None] = [None] * n
    if period < 1 or n < period + 1:
        return out
    trs: list[Decimal] = []
    for i in range(1, n):
        trs.append(true_range(highs[i], lows[i], closes[i - 1]))
    seed = _wilder_seed(trs, period)
    if seed is None:
        return out
    # trs[j] corresponds to closes index j+1
    out[period] = seed
    prev = seed
    for i in range(period + 1, n):
        prev = (prev * D(period - 1) + trs[i - 1]) / D(period)
        out[i] = prev
    return out


def rsi(closes: Sequence[Decimal], period: int = 14) -> list[Decimal | None]:
    n = len(closes)
    out: list[Decimal | None] = [None] * n
    if period < 1 or n < period + 1:
        return out
    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for i in range(1, n):
        delta = closes[i] - closes[i - 1]
        gains.append(delta if delta > ZERO else ZERO)
        losses.append(-delta if delta < ZERO else ZERO)
    avg_gain = _wilder_seed(gains, period)
    avg_loss = _wilder_seed(losses, period)
    if avg_gain is None or avg_loss is None:
        return out
    def _rsi(gain: Decimal, loss: Decimal) -> Decimal:
        if loss == ZERO:
            return D(100)
        rs = gain / loss
        return D(100) - (D(100) / (ONE + rs))

    out[period] = _rsi(avg_gain, avg_loss)
    for i in range(period + 1, n):
        avg_gain = (avg_gain * D(period - 1) + gains[i - 1]) / D(period)
        avg_loss = (avg_loss * D(period - 1) + losses[i - 1]) / D(period)
        out[i] = _rsi(avg_gain, avg_loss)
    return out


def macd(
    closes: Sequence[Decimal],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple[list[Decimal | None], list[Decimal | None], list[Decimal | None]]:
    fast_ema = ema(closes, fast)
    slow_ema = ema(closes, slow)
    line: list[Decimal | None] = []
    compact: list[Decimal] = []
    compact_index: list[int] = []
    for i, (a, b) in enumerate(zip(fast_ema, slow_ema)):
        if a is None or b is None:
            line.append(None)
            continue
        value = a - b
        line.append(value)
        compact.append(value)
        compact_index.append(i)
    signal_compact = ema(compact, signal_period) if compact else []
    signal: list[Decimal | None] = [None] * len(closes)
    hist: list[Decimal | None] = [None] * len(closes)
    for idx, value in zip(compact_index, signal_compact):
        signal[idx] = value
        macd_value = line[idx]
        if value is not None and macd_value is not None:
            hist[idx] = macd_value - value
    return line, signal, hist


def adx(
    highs: Sequence[Decimal],
    lows: Sequence[Decimal],
    closes: Sequence[Decimal],
    period: int = 14,
) -> list[Decimal | None]:
    """Wilder ADX aligned with ``closes``."""
    n = len(closes)
    out: list[Decimal | None] = [None] * n
    if period < 1 or n < period * 2:
        return out
    plus_dm = [ZERO] * n
    minus_dm = [ZERO] * n
    trs = [ZERO] * n
    for i in range(1, n):
        up_move = highs[i] - highs[i - 1]
        down_move = lows[i - 1] - lows[i]
        plus_dm[i] = up_move if up_move > down_move and up_move > ZERO else ZERO
        minus_dm[i] = down_move if down_move > up_move and down_move > ZERO else ZERO
        trs[i] = true_range(highs[i], lows[i], closes[i - 1])
    atr_s = [ZERO] * n
    plus_s = [ZERO] * n
    minus_s = [ZERO] * n
    atr_s[period] = sum(trs[1 : period + 1], ZERO)
    plus_s[period] = sum(plus_dm[1 : period + 1], ZERO)
    minus_s[period] = sum(minus_dm[1 : period + 1], ZERO)
    dx: list[Decimal | None] = [None] * n

    def _dx(p_dm: Decimal, m_dm: Decimal, tr: Decimal) -> Decimal | None:
        if tr <= ZERO:
            return None
        p_di = D(100) * p_dm / tr
        m_di = D(100) * m_dm / tr
        denom = p_di + m_di
        if denom <= ZERO:
            return ZERO
        return D(100) * abs(p_di - m_di) / denom

    dx[period] = _dx(plus_s[period], minus_s[period], atr_s[period])
    for i in range(period + 1, n):
        atr_s[i] = atr_s[i - 1] - (atr_s[i - 1] / D(period)) + trs[i]
        plus_s[i] = plus_s[i - 1] - (plus_s[i - 1] / D(period)) + plus_dm[i]
        minus_s[i] = minus_s[i - 1] - (minus_s[i - 1] / D(period)) + minus_dm[i]
        dx[i] = _dx(plus_s[i], minus_s[i], atr_s[i])
    first_adx_idx = period * 2 - 1
    window = [dx[i] for i in range(period, first_adx_idx + 1) if dx[i] is not None]
    if len(window) < period:
        return out
    prev = sum(window, ZERO) / D(period)
    out[first_adx_idx] = prev
    for i in range(first_adx_idx + 1, n):
        if dx[i] is None:
            continue
        prev = (prev * D(period - 1) + dx[i]) / D(period)
        out[i] = prev
    return out


def realized_vol(closes: Sequence[Decimal], period: int = 20) -> Decimal | None:
    """Stdev of simple returns over ``period``. None if undefined."""
    if period < 2 or len(closes) < period + 1:
        return None
    window = closes[-(period + 1) :]
    rets: list[Decimal] = []
    for i in range(1, len(window)):
        prev = window[i - 1]
        if prev <= ZERO:
            return None
        rets.append((window[i] - prev) / prev)
    mean = sum(rets, ZERO) / D(len(rets))
    acc = ZERO
    for ret in rets:
        diff = ret - mean
        acc += diff * diff
    variance = acc / D(len(rets))
    if variance <= ZERO:
        return ZERO
    # Decimal.sqrt is exact for Decimal
    return variance.sqrt()


def is_indicator_sane(value: Decimal | None) -> bool:
    if value is None:
        return False
    if value.is_nan() or value.is_infinite():
        return False
    return value > ZERO
