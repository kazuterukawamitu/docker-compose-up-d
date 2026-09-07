from __future__ import annotations

from decimal import Decimal

from bitbank_bot.market_data import Candle
from bitbank_bot.rate_engine import MarketRegime, RateEngine, classify_regime
from bitbank_bot.strategy import Signal
from tests.helpers import cfg


def _bars(n: int = 40, step: int = 10000) -> list[Candle]:
    out = []
    width = 300_000
    price = Decimal("10000000")
    for i in range(n):
        p = price + Decimal(i * step)
        out.append(Candle(p, p + 50, p - 50, p, Decimal("1"), 1_700_000_000_000 + i * width))
    return out


def test_fixed_preserves_buy1_three_percent() -> None:
    c = cfg(rate_mode="fixed")
    engine = RateEngine(c)
    signal = Signal("BUY1", "buy", c.buy1_tp, "granville")
    decision = engine.decide(signal, _bars())
    assert decision.mode == "fixed"
    assert decision.take_profit_pct == Decimal("0.03")
    assert decision.suppress is False


def test_fixed_golden_cross_eight_percent() -> None:
    c = cfg(rate_mode="fixed")
    signal = Signal("BUY2", "buy", c.buy2_golden_tp, "gc", golden_cross=True)
    decision = RateEngine(c).decide(signal, _bars())
    assert decision.take_profit_pct == Decimal("0.08")


def test_fixed_pullback_four_percent() -> None:
    c = cfg(rate_mode="fixed")
    signal = Signal("BUY3", "buy", c.buy3_tp, "pullback")
    decision = RateEngine(c).decide(signal, _bars())
    assert decision.take_profit_pct == Decimal("0.04")


def test_dynamic_clamps_risk() -> None:
    c = cfg(rate_mode="dynamic", max_risk_per_trade=Decimal("0.02"))
    signal = Signal("BUY1", "buy", c.buy1_tp, "x")
    decision = RateEngine(c).decide(signal, _bars(60, step=200000))
    assert decision.risk_pct <= c.max_risk_per_trade
    if decision.stop_loss_pct is not None:
        assert c.min_sl_pct <= decision.stop_loss_pct <= c.max_sl_pct


def test_stale_suppresses_dynamic() -> None:
    c = cfg(rate_mode="dynamic")
    signal = Signal("BUY1", "buy", c.buy1_tp, "x")
    decision = RateEngine(c).decide(signal, _bars(), stale=True)
    assert decision.suppress
    assert decision.mode == "fixed"


def test_regime_high_vol() -> None:
    c = cfg(high_vol_atr_pct=Decimal("0.01"))
    assert classify_regime(atr_pct=Decimal("0.05"), adx_value=Decimal("10"), cfg=c) == (
        MarketRegime.HIGH_VOL
    )
