from __future__ import annotations

from decimal import Decimal

from bitbank_bot.market_data import CandleCache, drop_incomplete_candle, parse_ohlcv, synthetic_candles


def test_cache_merge_by_timestamp() -> None:
    cache = CandleCache(20)
    first = synthetic_candles(3)
    cache.merge(first)
    again = list(first)
    cache.merge(again)
    assert len(cache.candles) == 3


def test_drop_incomplete() -> None:
    candles = synthetic_candles(5)
    last = candles[-1]
    # still forming
    out = drop_incomplete_candle(list(candles), "1hour", now_ms=last.timestamp_ms + 1000)
    assert len(out) == 4
    complete = drop_incomplete_candle(list(candles), "1hour", now_ms=last.timestamp_ms + 3_600_000)
    assert len(complete) == 5


def test_parse_uses_decimal() -> None:
    c = parse_ohlcv(["1", "2", "0.5", "1.5", "10", 1])
    assert c.open == Decimal("1")
