from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from bitbank_bot.engine import Engine
from bitbank_bot.indicators import Trend, atr
from bitbank_bot.market_data import Candle, CandleCache, fetch_candles
from bitbank_bot.money import D
from bitbank_bot.rate_engine import decide_rate, last_atr
from bitbank_bot.rest_client import BitbankAPIError
from bitbank_bot.strategy import Signal
from tests.helpers import cfg

JST = timezone(timedelta(hours=9))


def test_atr_constant_range() -> None:
    highs = [D("10"), D("11"), D("12"), D("13"), D("14")]
    lows = [D("9"), D("10"), D("11"), D("12"), D("13")]
    closes = [D("9.5"), D("10.5"), D("11.5"), D("12.5"), D("13.5")]
    out = atr(highs, lows, closes, 3)
    assert out[-1] is not None
    assert out[-1] > 0


def test_fixed_rate_keeps_buy1_tp() -> None:
    c = cfg(rate_mode="fixed")
    candles = [
        Candle(D("100"), D("101"), D("99"), D("100"), D("1"), 1),
        Candle(D("100"), D("101"), D("99"), D("100"), D("1"), 2),
    ]
    decision = decide_rate(
        c, Signal("BUY1", "buy", D("0.03"), "t"), candles, Trend.FLAT, D("100")
    )
    assert decision.mode == "fixed"
    assert decision.take_profit_pct == D("0.03")


def test_dynamic_blocks_on_bad_atr() -> None:
    c = cfg(rate_mode="dynamic", atr_period=14)
    candles = [Candle(D("100"), D("101"), D("99"), D("100"), D("1"), 1)]
    decision = decide_rate(
        c, Signal("BUY1", "buy", D("0.03"), "t"), candles, Trend.UP, D("100")
    )
    assert decision.reason == "abnormal_atr"
    assert decision.size_mult == 0


def test_last_atr_from_wide_bars() -> None:
    candles = []
    price = D("10000000")
    for i in range(40):
        high = price + D("50000")
        low = price - D("50000")
        candles.append(Candle(price, high, low, price, D("1"), i))
    value = last_atr(candles, 14)
    assert value is not None
    decision = decide_rate(
        cfg(rate_mode="dynamic"),
        Signal("BUY1", "buy", D("0.03"), "t"),
        candles,
        Trend.UP,
        price,
    )
    assert decision.mode == "dynamic"
    assert decision.reason != "abnormal_atr"
    assert decision.take_profit_pct is not None
    assert D("0.01") <= decision.take_profit_pct <= D("0.12")


def test_fetch_candles_logs_bitbank_error() -> None:
    rest = MagicMock()
    rest.get_candlestick.side_effect = BitbankAPIError(
        "api success=0 code=10000",
        code=10000,
        http_status=200,
        endpoint="/btc_jpy/candlestick/5min/20200101",
    )
    c = cfg(candle_type="5min", candle_lookback_days=1)
    out = fetch_candles(rest, c)
    assert out == []
    assert rest.get_candlestick.call_count >= 1


def test_cache_used_when_latest_fetch_fails(tmp_path) -> None:
    c = cfg(
        state_path=str(tmp_path / "state.json"),
        lock_path=str(tmp_path / "bot.lock"),
        log_dir=str(tmp_path / "logs"),
        enable_websocket=False,
        dry_run=True,
        poll_sec=0.05,
        candle_type="1hour",
    )
    now_ms = int(datetime.now(JST).timestamp() * 1000)
    hour = 3_600_000
    last = now_ms - (now_ms % hour) - hour
    cache = CandleCache(20)
    cache.merge(
        [
            Candle(D("100"), D("101"), D("99"), D("100"), D("1"), last - hour),
            Candle(D("100"), D("101"), D("99"), D("100"), D("1"), last),
        ]
    )
    rest = MagicMock()
    rest.get_candlestick.side_effect = RuntimeError("no net")
    rest.get_ticker.return_value = {"last": "100"}
    engine = Engine(c, client=rest)
    engine.cache = cache
    incoming = engine._candles_for_cycle(rest, latest_only=True, force_synthetic=False)
    assert incoming == []
    assert engine.used_synthetic_fallback is False
    assert engine.market_data_real is True
    rest.create_order = MagicMock(side_effect=AssertionError("live order"))
