from datetime import datetime, timezone

from bitbank_bot.market_data import (
    DERIVED_SOURCE,
    Candle,
    CandleCache,
    aggregate_candles,
    candle_date_key,
)
from bitbank_bot.money import D


def _c(ts: int, o: str, h: str, low: str, close: str, vol: str = "1") -> Candle:
    return Candle(D(o), D(h), D(low), D(close), D(vol), ts)


def test_aggregate_10min_from_5min() -> None:
    candles = [
        _c(0, "1", "2", "1", "1.5", "1"),
        _c(5 * 60 * 1000, "1.5", "3", "1", "2", "2"),
        _c(10 * 60 * 1000, "2", "2.5", "2", "2.2", "1"),
    ]
    out = aggregate_candles(candles, DERIVED_SOURCE["10min"][1])
    assert len(out) == 2
    assert out[0].open == D("1")
    assert out[0].close == D("2")
    assert out[0].high == D("3")
    assert out[0].volume == D("3")


def test_candle_date_key_short_vs_long() -> None:
    when = datetime(2026, 8, 28, tzinfo=timezone.utc)
    assert candle_date_key("1hour", when) == "20260828"
    assert candle_date_key("1day", when) == "2026"
    assert candle_date_key("4hour", when) == "2026"
    assert candle_date_key("10min", when) == "20260828"


def test_candle_cache_merges_without_dropping_history() -> None:
    cache = CandleCache(ma_period=2)
    first = [_c(1, "1", "1", "1", "1"), _c(2, "2", "2", "2", "2")]
    cache.merge(first)
    cache.merge([_c(3, "3", "3", "3", "3")])
    assert [c.timestamp_ms for c in cache.candles] == [1, 2, 3]
    assert cache.sma.value == D("2.5")
