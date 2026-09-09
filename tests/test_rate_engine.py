from __future__ import annotations

from decimal import Decimal

from bitbank_bot.market_data import Candle
from bitbank_bot.rate_engine import RateEngine, detect_regime
from bitbank_bot.strategy import Signal
from tests.helpers import cfg


def _candles(n: int = 40, vol: int = 50) -> list[Candle]:
    out: list[Candle] = []
    price = Decimal("10000000")
    for i in range(n):
        high = price + Decimal(vol)
        low = price - Decimal(vol)
        out.append(
            Candle(price, high, low, price, Decimal("1"), 1_700_000_000_000 + i * 3_600_000)
        )
        price += Decimal(vol // 2)
    return out


def test_fixed_keeps_buy1_tp() -> None:
    c = cfg(rate_mode="fixed")
    decision = RateEngine(c).decide(Signal("BUY1", "buy", Decimal("0.03"), "t"), _candles())
    assert decision.ok
    assert decision.mode == "fixed"
    assert decision.take_profit_pct == Decimal("0.03")


def test_dynamic_clamps_and_uses_atr() -> None:
    c = cfg(rate_mode="dynamic", min_tp_pct=Decimal("0.01"), max_tp_pct=Decimal("0.12"))
    decision = RateEngine(c).decide(Signal("BUY1", "buy", Decimal("0.03"), "t"), _candles(80, 200000))
    assert decision.ok
    assert decision.mode == "dynamic"
    assert c.min_tp_pct <= decision.take_profit_pct <= c.max_tp_pct
    assert c.min_sl_pct <= decision.stop_loss_pct <= c.max_sl_pct


def test_dynamic_abnormal_atr_on_short_series() -> None:
    c = cfg(rate_mode="dynamic")
    decision = RateEngine(c).decide(Signal("BUY1", "buy", Decimal("0.03"), "t"), _candles(3))
    assert decision.ok is False
    assert decision.reason == "abnormal_atr"


def test_regime_high_vol() -> None:
    c = cfg(regime_atr_high=Decimal("0.01"))
    assert detect_regime(c, atr_pct=Decimal("0.05"), adx_value=Decimal("10")) == "HIGH_VOLATILITY"
