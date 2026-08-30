from datetime import datetime, timezone

from bitbank_bot.config import TIMEFRAMES
from bitbank_bot.market_data import Candle, drop_incomplete_candle
from bitbank_bot.money import D
from bitbank_bot.multi_timeframe import TimeframeHealth, higher_tf_ready


def test_timeframes_map_has_eight_bitbank_types() -> None:
    assert TIMEFRAMES == {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1hour",
        "4h": "4hour",
        "1d": "1day",
        "1w": "1week",
    }


def test_drop_incomplete_last_candle() -> None:
    now = datetime(2026, 8, 30, 12, 30, tzinfo=timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    hour = 60 * 60 * 1000
    complete = Candle(D("1"), D("1"), D("1"), D("1"), D("1"), now_ms - hour)
    forming = Candle(D("2"), D("2"), D("2"), D("2"), D("2"), now_ms - 10_000)
    out = drop_incomplete_candle([complete, forming], "1hour", now_ms=now_ms)
    assert [c.timestamp_ms for c in out] == [complete.timestamp_ms]


def test_keep_closed_last_candle() -> None:
    now_ms = 2_000_000_000_000
    hour = 60 * 60 * 1000
    closed = Candle(D("1"), D("1"), D("1"), D("1"), D("1"), now_ms - hour)
    out = drop_incomplete_candle([closed], "1hour", now_ms=now_ms)
    assert len(out) == 1


def test_higher_tf_ready_requires_week_day_four_hour() -> None:
    ok = TimeframeHealth("1w", "1week", True, 2, 1, "ok")
    missing = {
        "1w": ok,
        "1d": TimeframeHealth("1d", "1day", False, 0, None, "WAIT"),
        "4h": ok,
    }
    allowed, reason = higher_tf_ready(missing)
    assert not allowed
    assert reason == "mtf_wait_1d"
    ready = {
        "1w": ok,
        "1d": TimeframeHealth("1d", "1day", True, 2, 1, "ok"),
        "4h": TimeframeHealth("4h", "4hour", True, 2, 1, "ok"),
    }
    assert higher_tf_ready(ready) == (True, "ok")
