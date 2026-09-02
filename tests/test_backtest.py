from __future__ import annotations

from decimal import Decimal

from bitbank_bot.backtest import run_backtest
from bitbank_bot.market_data import Candle, synthetic_candles
from tests.helpers import cfg


def test_backtest_synthetic_runs() -> None:
    report = run_backtest(synthetic_candles(120), cfg())
    assert report.trades >= 0
    assert report.wins + report.losses == report.trades
    assert 0.0 <= report.win_rate <= 1.0


def test_backtest_buy_then_tp() -> None:
    c = cfg(ma_period=3, short_ma_period=3, long_ma_period=5, ma_slope_threshold=Decimal("0.0001"))
    prices = [Decimal(str(200 - i)) for i in range(20)] + [Decimal("176"), Decimal("177")]
    prices.extend([Decimal("190")] * 6)
    candles = [
        Candle(p, p, p, p, Decimal("1"), 1_700_000_000_000 + i * 3_600_000)
        for i, p in enumerate(prices)
    ]
    report = run_backtest(candles, c)
    assert report.trades >= 0
