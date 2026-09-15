from __future__ import annotations

from decimal import Decimal

from bitbank_bot.market_data import Candle, synthetic_candles
from bitbank_bot.rate_engine import RateEngine
from bitbank_bot.strategy import Signal
from tests.helpers import cfg


def test_fixed_preserves_strategy_tps() -> None:
    engine = RateEngine(cfg(rate_mode="fixed"))
    for kind, tp in (("BUY1", "0.03"), ("BUY3", "0.04"), ("BUY4", "0.05")):
        decision = engine.decide(
            Signal(kind, "buy", Decimal(tp), "t"),
            synthetic_candles(40),
        )
        assert decision.ok
        assert decision.take_profit_pct == Decimal(tp)
    golden = engine.decide(
        Signal("BUY2", "buy", Decimal("0.08"), "t", golden_cross=True),
        synthetic_candles(40),
    )
    assert golden.take_profit_pct == Decimal("0.08")


def test_dynamic_halts_on_stale_or_empty_atr() -> None:
    engine = RateEngine(cfg(rate_mode="dynamic", atr_period=14))
    stale = engine.decide(Signal("BUY1", "buy", Decimal("0.03"), "t"), synthetic_candles(40), stale=True)
    assert not stale.ok
    assert stale.reason == "stale_data"
    empty = engine.decide(Signal("BUY1", "buy", Decimal("0.03"), "t"), [])
    assert not empty.ok
    assert empty.reason == "atr_unavailable"


def test_auto_falls_back_to_fixed() -> None:
    engine = RateEngine(cfg(rate_mode="auto"))
    decision = engine.decide(Signal("BUY1", "buy", Decimal("0.03"), "t"), [], stale=True)
    assert decision.ok
    assert decision.mode == "fixed"
    assert decision.take_profit_pct == Decimal("0.03")


def _wide_range_candles(n: int = 40) -> list[Candle]:
    from datetime import datetime, timedelta, timezone

    from bitbank_bot.market_data import Candle

    jst = timezone(timedelta(hours=9))
    hour = 3_600_000
    now_ms = int(datetime.now(jst).timestamp() * 1000)
    last_close = now_ms - (now_ms % hour) - hour
    base_ts = last_close - (n - 1) * hour
    price = Decimal("10000000")
    candles: list[Candle] = []
    for i in range(n):
        p = price
        # ~3% high-low so ATR/price is high-volatility
        span = Decimal("400000")
        candles.append(Candle(p + span, p - span, p, p, Decimal("1"), base_ts + i * hour))
    return candles


def test_dynamic_scales_tp_and_shrinks_size_on_high_atr() -> None:
    engine = RateEngine(cfg(rate_mode="dynamic", atr_period=14, high_vol_size_mult=Decimal("0.5")))
    decision = engine.decide(Signal("BUY1", "buy", Decimal("0.03"), "t"), _wide_range_candles())
    assert decision.ok
    assert decision.market_regime == "HIGH_VOLATILITY"
    assert decision.size_mult == Decimal("0.5")
    assert decision.take_profit_pct is not None
    assert decision.take_profit_pct >= Decimal("0.03")
    assert decision.stop_loss_pct is not None


def test_auto_uses_fixed_in_range_regime() -> None:
    engine = RateEngine(cfg(rate_mode="auto"))
    decision = engine.decide(Signal("BUY1", "buy", Decimal("0.03"), "t"), synthetic_candles(40))
    assert decision.ok
    assert decision.mode == "fixed"
    assert decision.take_profit_pct == Decimal("0.03")
    assert "fixed" in decision.reason
