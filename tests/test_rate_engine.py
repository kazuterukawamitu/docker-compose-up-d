from __future__ import annotations

from decimal import Decimal

from bitbank_bot.market_data import Candle, synthetic_candles
from bitbank_bot.rate_engine import RateEngine, RateMode
from bitbank_bot.strategy import Signal
from tests.helpers import cfg


def test_fixed_keeps_buy1_three_percent() -> None:
    engine = RateEngine(cfg(rate_mode="fixed"))
    signal = Signal("BUY1", "buy", Decimal("0.03"), "t")
    decision = engine.decide(signal, synthetic_candles(80))
    assert decision.ok
    assert decision.mode is RateMode.FIXED
    assert decision.take_profit_pct == Decimal("0.03")


def test_fixed_keeps_golden_eight_percent() -> None:
    engine = RateEngine(cfg(rate_mode="fixed"))
    signal = Signal("BUY2", "buy", Decimal("0.08"), "t", golden_cross=True)
    decision = engine.decide(signal, synthetic_candles(80))
    assert decision.take_profit_pct == Decimal("0.08")


def test_dynamic_clamps_and_rejects_zero_atr() -> None:
    c = cfg(rate_mode="dynamic", min_tp_pct=Decimal("0.01"), max_tp_pct=Decimal("0.12"))
    flat = [
        Candle(
            Decimal("100"),
            Decimal("100"),
            Decimal("100"),
            Decimal("100"),
            Decimal("1"),
            1_700_000_000_000 + i * 60_000,
        )
        for i in range(40)
    ]
    decision = RateEngine(c).decide(Signal("BUY1", "buy", Decimal("0.03"), "t"), flat)
    assert decision.ok is False
    assert decision.reason == "abnormal_atr"


def test_auto_normal_uses_fixed() -> None:
    engine = RateEngine(
        cfg(
            rate_mode="auto",
            trend_adx=Decimal("101"),
            high_vol_atr_pct=Decimal("1"),
            high_vol_realized=Decimal("1"),
        )
    )
    decision = engine.decide(
        Signal("BUY3", "buy", Decimal("0.04"), "t"), synthetic_candles(80)
    )
    assert decision.mode is RateMode.FIXED
    assert decision.take_profit_pct == Decimal("0.04")
