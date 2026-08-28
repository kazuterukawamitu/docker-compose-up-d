"""SMA, EMA, MACD, RSI, ATR, Bollinger. Decimal-friendly wrappers over numpy."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

import numpy as np

from bitbank_bot.models import MaTrend

ZERO = Decimal("0")


def _arr(values: Sequence[Decimal | float | int]) -> np.ndarray:
    return np.array([float(v) for v in values], dtype=np.float64)


def _dec_series(values: np.ndarray) -> list[Decimal]:
    out: list[Decimal] = []
    for value in values:
        if np.isnan(value):
            out.append(ZERO)
        else:
            out.append(Decimal(str(round(float(value), 8))))
    return out


def sma(values: Sequence[Decimal | float | int], period: int) -> list[Decimal]:
    data = _arr(values)
    out = np.full_like(data, np.nan)
    if period <= 0 or len(data) == 0:
        return _dec_series(out)
    for i in range(period - 1, len(data)):
        out[i] = data[i - period + 1 : i + 1].mean()
    return _dec_series(out)


def ema(values: Sequence[Decimal | float | int], period: int) -> list[Decimal]:
    data = _arr(values)
    out = np.full_like(data, np.nan, dtype=np.float64)
    if len(data) < period or period <= 0:
        return _dec_series(out)
    alpha = 2.0 / (period + 1)
    out[period - 1] = data[:period].mean()
    for i in range(period, len(data)):
        out[i] = alpha * data[i] + (1 - alpha) * out[i - 1]
    return _dec_series(out)


def rsi(values: Sequence[Decimal | float | int], period: int = 14) -> list[Decimal]:
    data = _arr(values)
    out = np.full_like(data, np.nan)
    if len(data) < period + 1:
        return _dec_series(out)
    delta = np.diff(data, prepend=data[0])
    gains = np.where(delta > 0, delta, 0.0)
    losses = np.where(delta < 0, -delta, 0.0)
    avg_gain = gains[1 : period + 1].mean()
    avg_loss = losses[1 : period + 1].mean()
    out[period] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    for i in range(period + 1, len(data)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - (100.0 / (1.0 + avg_gain / avg_loss))
    return _dec_series(out)


def macd(
    values: Sequence[Decimal | float | int],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    fast_line = _arr(ema(values, fast))
    slow_line = _arr(ema(values, slow))
    macd_line = fast_line - slow_line
    signal_line = _arr(ema([Decimal(str(x)) if not np.isnan(x) else Decimal("0") for x in macd_line], signal))
    # Recompute signal only where MACD is defined
    hist = macd_line - signal_line
    return _dec_series(macd_line), _dec_series(signal_line), _dec_series(hist)


def atr(
    highs: Sequence[Decimal | float | int],
    lows: Sequence[Decimal | float | int],
    closes: Sequence[Decimal | float | int],
    period: int = 14,
) -> list[Decimal]:
    high = _arr(highs)
    low = _arr(lows)
    close = _arr(closes)
    n = len(close)
    tr = np.full(n, np.nan)
    if n == 0:
        return []
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    out = np.full(n, np.nan)
    if n < period:
        return _dec_series(out)
    out[period - 1] = np.nanmean(tr[:period])
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return _dec_series(out)


def bollinger(
    values: Sequence[Decimal | float | int],
    period: int = 20,
    num_std: Decimal = Decimal("2"),
) -> tuple[list[Decimal], list[Decimal], list[Decimal]]:
    data = _arr(values)
    mid = _arr(sma(values, period))
    upper = np.full_like(data, np.nan)
    lower = np.full_like(data, np.nan)
    k = float(num_std)
    for i in range(period - 1, len(data)):
        window = data[i - period + 1 : i + 1]
        std = window.std(ddof=0)
        upper[i] = mid[i] + k * std
        lower[i] = mid[i] - k * std
    return _dec_series(upper), _dec_series(mid), _dec_series(lower)


def classify_ma_trend(
    ma: Sequence[Decimal],
    lookback: int,
    threshold: Decimal,
) -> MaTrend:
    valid = [v for v in ma if v > 0]
    if len(valid) < lookback + 1:
        return MaTrend.FLAT
    current = valid[-1]
    past = valid[-1 - lookback]
    if past == 0:
        return MaTrend.FLAT
    slope = (current - past) / past
    if slope > threshold:
        return MaTrend.UP
    if slope < -threshold:
        return MaTrend.DOWN
    return MaTrend.FLAT


def crossed_above(prev_price: Decimal, prev_ma: Decimal, price: Decimal, ma: Decimal) -> bool:
    return prev_price <= prev_ma and price > ma


def crossed_below(prev_price: Decimal, prev_ma: Decimal, price: Decimal, ma: Decimal) -> bool:
    return prev_price >= prev_ma and price < ma
