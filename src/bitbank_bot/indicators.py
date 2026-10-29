"""SMA/EMA, MA trend, golden cross, Shannon entropy, and daily PnL helpers."""

from __future__ import annotations

import math
from decimal import Decimal
from enum import Enum
from typing import Mapping, Sequence

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


def simple_returns(closes: Sequence[Decimal]) -> list[Decimal]:
    out: list[Decimal] = []
    for i in range(1, len(closes)):
        prev = D(closes[i - 1])
        if prev == ZERO:
            continue
        out.append((D(closes[i]) - prev) / prev)
    return out


def shannon_entropy(returns: Sequence[Decimal], bins: int = 8) -> Decimal:
    """Normalized Shannon entropy of recent returns in [0, 1].

    High entropy means an uncertain / choppy return distribution. Regime only —
    never emits or forces an order by itself.
    """
    if bins < 2 or len(returns) < 2:
        return ZERO
    values = [float(D(item)) for item in returns]
    low = min(values)
    high = max(values)
    if low == high:
        return ZERO
    width = (high - low) / bins
    counts = [0] * bins
    for value in values:
        index = min(int((value - low) / width), bins - 1)
        counts[index] += 1
    total = float(len(values))
    entropy = 0.0
    for count in counts:
        if count == 0:
            continue
        prob = count / total
        entropy -= prob * math.log(prob)
    return D(str(round(entropy / math.log(bins), 8)))


def entropy_regime(
    entropy: Decimal,
    *,
    high: Decimal = D("0.70"),
    low: Decimal = D("0.30"),
) -> str:
    if entropy >= D(high):
        return "CHOP"
    if entropy <= D(low):
        return "DIRECTIONAL"
    return "MIXED"


def realtime_daily_pnl(
    realized: Decimal,
    mark: Decimal,
    position_amount: Decimal = ZERO,
    average_price: Decimal = ZERO,
) -> Decimal:
    """JST-day realized PnL plus mark-to-market on the open position."""
    unrealized = ZERO
    amount = D(position_amount)
    if amount > ZERO:
        unrealized = (D(mark) - D(average_price)) * amount
    return D(realized) + unrealized


def daily_pnl_score(pnl_jpy: Decimal, scale_jpy: Decimal) -> Decimal:
    """Map real-time daily PnL to [-1, 1]. Independent of Granville/pullback."""
    scale = D(scale_jpy)
    if scale <= ZERO:
        scale = D("10000")
    raw = D(pnl_jpy) / scale
    if raw > ONE:
        return ONE
    if raw < -ONE:
        return D("-1")
    return raw


def clause_score(clauses: Mapping[str, bool]) -> Decimal:
    if not clauses:
        return ZERO
    hits = sum(1 for ok in clauses.values() if ok)
    return D(hits) / D(len(clauses))


def granville_pullback_score(rule_clauses: Mapping[str, Mapping[str, bool]]) -> Decimal:
    """Best README/Granville rule completeness in [0, 1]. Partial AND is not a fire."""
    if not rule_clauses:
        return ZERO
    return max((clause_score(clauses) for clauses in rule_clauses.values()), default=ZERO)


def paired_indicator_scores(
    granville: Decimal, daily_pnl: Decimal
) -> tuple[Decimal, Decimal]:
    """Return both scores unchanged. Neither silently overrides the other."""
    return D(granville), D(daily_pnl)
