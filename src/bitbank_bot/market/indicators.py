from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from bitbank_bot.decimal_utils import d, pct_change
from bitbank_bot.models import Candle, Slope


def sma(values: Sequence[Decimal], period: int) -> list[Decimal | None]:
    out: list[Decimal | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    window = Decimal("0")
    for i, value in enumerate(values):
        window += value
        if i >= period:
            window -= values[i - period]
        if i >= period - 1:
            out[i] = window / Decimal(period)
    return out


def ema(values: Sequence[Decimal], period: int) -> list[Decimal | None]:
    out: list[Decimal | None] = [None] * len(values)
    if period <= 0 or len(values) < period:
        return out
    seed = sum(values[:period], Decimal("0")) / Decimal(period)
    out[period - 1] = seed
    multiplier = Decimal("2") / Decimal(period + 1)
    prev = seed
    for i in range(period, len(values)):
        prev = (values[i] - prev) * multiplier + prev
        out[i] = prev
    return out


def ma_series(values: Sequence[Decimal], period: int, kind: str) -> list[Decimal | None]:
    if kind == "sma":
        return sma(values, period)
    return ema(values, period)


def slope_of(current: Decimal, previous: Decimal, threshold: Decimal) -> Slope:
    change = pct_change(current, previous)
    if change > threshold:
        return "up"
    if change < -threshold:
        return "down"
    return "flat"


def true_ranges(candles: Sequence[Candle]) -> list[Decimal]:
    out: list[Decimal] = []
    prev_close: Decimal | None = None
    for bar in candles:
        high_low = bar.high - bar.low
        if prev_close is None:
            out.append(high_low)
        else:
            out.append(max(high_low, abs(bar.high - prev_close), abs(bar.low - prev_close)))
        prev_close = bar.close
    return out


def atr(candles: Sequence[Candle], period: int = 14) -> list[Decimal | None]:
    return sma(true_ranges(candles), period)


def rsi(values: Sequence[Decimal], period: int = 14) -> list[Decimal | None]:
    out: list[Decimal | None] = [None] * len(values)
    if len(values) <= period:
        return out
    gains = Decimal("0")
    losses = Decimal("0")
    for i in range(1, period + 1):
        delta = values[i] - values[i - 1]
        if delta >= 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / Decimal(period)
    avg_loss = losses / Decimal(period)
    out[period] = _rsi_from_avgs(avg_gain, avg_loss)
    for i in range(period + 1, len(values)):
        delta = values[i] - values[i - 1]
        gain = delta if delta > 0 else Decimal("0")
        loss = -delta if delta < 0 else Decimal("0")
        avg_gain = (avg_gain * Decimal(period - 1) + gain) / Decimal(period)
        avg_loss = (avg_loss * Decimal(period - 1) + loss) / Decimal(period)
        out[i] = _rsi_from_avgs(avg_gain, avg_loss)
    return out


def _rsi_from_avgs(avg_gain: Decimal, avg_loss: Decimal) -> Decimal:
    if avg_loss == 0:
        return Decimal("100") if avg_gain > 0 else Decimal("50")
    rs = avg_gain / avg_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + rs))


def macd(
    values: Sequence[Decimal],
    fast: int = 12,
    slow: int = 26,
    signal_period: int = 9,
) -> tuple[list[Decimal | None], list[Decimal | None], list[Decimal | None]]:
    fast_line = ema(values, fast)
    slow_line = ema(values, slow)
    macd_line: list[Decimal | None] = []
    for a, b in zip(fast_line, slow_line, strict=True):
        if a is None or b is None:
            macd_line.append(None)
        else:
            macd_line.append(a - b)
    compact = [x for x in macd_line if x is not None]
    signal_compact = ema(compact, signal_period)
    signal_line: list[Decimal | None] = [None] * len(macd_line)
    idx = 0
    for i, value in enumerate(macd_line):
        if value is None:
            continue
        signal_line[i] = signal_compact[idx]
        idx += 1
    hist: list[Decimal | None] = []
    for macd_v, sig in zip(macd_line, signal_line, strict=True):
        if macd_v is None or sig is None:
            hist.append(None)
        else:
            hist.append(macd_v - sig)
    return macd_line, signal_line, hist


def bollinger(
    values: Sequence[Decimal],
    period: int = 20,
    stdevs: Decimal = Decimal("2"),
) -> tuple[list[Decimal | None], list[Decimal | None], list[Decimal | None]]:
    mid = sma(values, period)
    upper: list[Decimal | None] = [None] * len(values)
    lower: list[Decimal | None] = [None] * len(values)
    for i, mean in enumerate(mid):
        if mean is None:
            continue
        window = values[i - period + 1 : i + 1]
        var = sum((x - mean) ** 2 for x in window) / Decimal(period)
        sd = _sqrt(var)
        upper[i] = mean + stdevs * sd
        lower[i] = mean - stdevs * sd
    return upper, mid, lower


def _sqrt(value: Decimal) -> Decimal:
    if value <= 0:
        return Decimal("0")
    return value.sqrt()


def deviation(price: Decimal, ma: Decimal) -> Decimal:
    return pct_change(price, ma)


def crossed_above(prev_price: Decimal, prev_ma: Decimal, price: Decimal, ma: Decimal) -> bool:
    return prev_price < prev_ma and price >= ma


def crossed_below(prev_price: Decimal, prev_ma: Decimal, price: Decimal, ma: Decimal) -> bool:
    return prev_price > prev_ma and price <= ma


def interpolate_cross(
    prev_price: Decimal,
    price: Decimal,
    prev_ma: Decimal,
    ma: Decimal,
) -> Decimal | None:
    """Approximate the price where price and MA lines meet on this bar."""
    dp = (price - prev_price) - (ma - prev_ma)
    if dp == 0:
        return None
    t = (prev_ma - prev_price) / dp
    if t < 0 or t > 1:
        return None
    return prev_price + t * (price - prev_price)


def d_list(values: Sequence[float | int | str | Decimal]) -> list[Decimal]:
    return [d(v) for v in values]
