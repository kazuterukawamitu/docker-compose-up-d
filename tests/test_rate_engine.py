from __future__ import annotations

from decimal import Decimal

from bitbank_bot.indicators import atr, true_range
from bitbank_bot.market_data import Candle
from bitbank_bot.rate_engine import HIGH_VOL_ATR_PCT, MAX_TP_PCT, MIN_TP_PCT, decide
from bitbank_bot.strategy import Signal
from tests.helpers import cfg


def test_true_range() -> None:
    assert true_range(Decimal("110"), Decimal("90"), Decimal("100")) == Decimal("20")


def test_atr_none_when_short() -> None:
    assert atr([Decimal("1")], [Decimal("1")], [Decimal("1")], 14) is None


def test_fixed_keeps_signal_tp() -> None:
    signal = Signal("BUY1", "buy", Decimal("0.03"), "x")
    candles = [
        Candle(Decimal("100"), Decimal("101"), Decimal("99"), Decimal("100"), Decimal("1"), i)
        for i in range(40)
    ]
    decision = decide(
        cfg(rate_mode="fixed"),
        signal,
        price=Decimal("100"),
        candles=candles,
        trend="FLAT",
    )
    assert decision.mode == "fixed"
    assert decision.take_profit_pct == Decimal("0.03")
    assert decision.size_mult == Decimal("1")


def test_dynamic_clamps_tp() -> None:
    signal = Signal("BUY1", "buy", Decimal("0.03"), "x")
    candles = []
    price = Decimal("100")
    for i in range(40):
        high = price + Decimal("20")
        low = price - Decimal("20")
        candles.append(Candle(price, high, low, price, Decimal("1"), i))
    decision = decide(
        cfg(rate_mode="dynamic"),
        signal,
        price=price,
        candles=candles,
        trend="UP",
    )
    assert decision.mode == "dynamic"
    assert MIN_TP_PCT <= decision.take_profit_pct <= MAX_TP_PCT
    if decision.market_regime == "HIGH_VOLATILITY":
        assert decision.size_mult <= Decimal("1")
        assert decision.size_mult >= Decimal("0.25")
    assert HIGH_VOL_ATR_PCT > 0


def test_auto_range_uses_fixed() -> None:
    signal = Signal("BUY1", "buy", Decimal("0.03"), "x")
    candles = [
        Candle(Decimal("100"), Decimal("100.1"), Decimal("99.9"), Decimal("100"), Decimal("1"), i)
        for i in range(40)
    ]
    decision = decide(
        cfg(rate_mode="auto"),
        signal,
        price=Decimal("100"),
        candles=candles,
        trend="FLAT",
    )
    assert decision.mode == "fixed"
