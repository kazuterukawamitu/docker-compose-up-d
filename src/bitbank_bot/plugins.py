"""Advisory strategy plugins. They never call the exchange and never size orders.

The engine logs these notes. Live/paper orders still come only from the README
R1–R8 `Strategy` (SELL/EXIT outranks a new BUY while in position).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from bitbank_bot.indicators import Trend
from bitbank_bot.market_data import Candle
from bitbank_bot.money import D, ZERO
from bitbank_bot.strategy import MarketSnapshot, Position, Signal

_HALF = D("0.5")
_SIX = D("0.6")


def granville_pullback(snap: MarketSnapshot) -> Signal:
    """Granville-style bounce: uptrend MA, price stays above MA, dip then rise."""
    if snap.ma_trend != Trend.UP:
        return Signal.hold("granville: MA not in uptrend")
    if snap.close <= snap.ma:
        return Signal.hold("granville: close at or below MA")
    prev_dist = snap.prev_close - snap.prev_ma
    dist = snap.close - snap.ma
    if prev_dist > ZERO and dist > prev_dist and snap.close > snap.prev_close:
        return Signal(
            kind="GRANVILLE_PULLBACK",
            side="buy",
            tp_pct=None,
            reason="granville pullback bounce above rising MA",
            score=_SIX,
        )
    return Signal.hold("granville: no pullback bounce")


def ma_crossover(snap: MarketSnapshot) -> Signal:
    if snap.golden_cross:
        return Signal(
            kind="MA_GOLDEN",
            side="buy",
            tp_pct=None,
            reason="short MA crossed above long MA",
            golden_cross=True,
            score=_HALF,
        )
    if snap.dead_cross:
        return Signal(
            kind="MA_DEAD",
            side="sell",
            tp_pct=None,
            reason="short MA crossed below long MA",
            score=_HALF,
        )
    return Signal.hold("ma_crossover: no golden/dead cross")


def market_regime(snap: MarketSnapshot) -> Signal:
    return Signal.hold(f"regime:{snap.ma_trend.value}")


def _body(candle: Candle) -> Decimal:
    return candle.close - candle.open


def sakata_patterns(candles: Sequence[Candle]) -> Signal:
    """Objectively detectable Sakata-style 3-bar patterns from OHLC only."""
    if len(candles) < 3:
        return Signal.hold("sakata: need 3 candles")
    a, b, c = candles[-3], candles[-2], candles[-1]

    def bull(x: Candle) -> bool:
        return x.close > x.open

    def bear(x: Candle) -> bool:
        return x.close < x.open

    if bull(a) and bull(b) and bull(c) and a.close < b.close < c.close:
        return Signal(
            kind="SAKATA_3_SOLDIERS",
            side="buy",
            tp_pct=None,
            reason="three white soldiers",
            score=_HALF,
        )
    if bear(a) and bear(b) and bear(c) and a.close > b.close > c.close:
        return Signal(
            kind="SAKATA_3_CROWS",
            side="sell",
            tp_pct=None,
            reason="three black crows",
            score=_HALF,
        )
    small = abs(_body(b)) <= abs(_body(a)) * D("0.5")
    if bear(a) and small and bull(c) and c.close > (a.open + a.close) / D(2):
        return Signal(
            kind="SAKATA_MORNING_STAR",
            side="buy",
            tp_pct=None,
            reason="morning star",
            score=_HALF,
        )
    if bull(a) and small and bear(c) and c.close < (a.open + a.close) / D(2):
        return Signal(
            kind="SAKATA_EVENING_STAR",
            side="sell",
            tp_pct=None,
            reason="evening star",
            score=_HALF,
        )
    return Signal.hold("sakata: no pattern")


def advise(
    candles: Sequence[Candle],
    snap: MarketSnapshot,
    position: Position | None,
) -> list[Signal]:
    notes = [
        market_regime(snap),
        granville_pullback(snap),
        ma_crossover(snap),
        sakata_patterns(candles),
    ]
    if position is not None:
        notes.insert(
            0,
            Signal.hold("in_position: EXIT/SELL outranks new BUY (plugins advisory only)"),
        )
    return notes
