from __future__ import annotations

from decimal import Decimal

from datetime import datetime, timedelta

from bitbank_bot.market_data import (
    CandleCache,
    cache_is_fresh,
    candle_date_key,
    drop_incomplete_candle,
    parse_ohlcv,
    synthetic_candles,
)
from bitbank_bot.config import SHORT_CANDLE_TYPES


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


def test_5min_and_1hour_use_yyyymmdd() -> None:
    when = datetime(2026, 9, 9, 12, 0)
    assert candle_date_key("5min", when) == "20260909"
    assert candle_date_key("1hour", when) == "20260909"
    assert "5min" in SHORT_CANDLE_TYPES
    assert candle_date_key("1day", when) == "2026"


def test_cache_freshness_on_closed_hour() -> None:
    candles = synthetic_candles(5)
    last = candles[-1]
    assert cache_is_fresh(candles, "1hour", now_ms=last.timestamp_ms + 3_600_000)
    assert not cache_is_fresh(candles, "1hour", now_ms=last.timestamp_ms + 10 * 3_600_000)
