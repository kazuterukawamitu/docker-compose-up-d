from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from bitbank_bot.market_data import candle_date_key, fetch_candles, synthetic_candles
from bitbank_bot.rest_client import BitbankAPIError
from tests.helpers import cfg

JST = timezone(timedelta(hours=9))


def test_5min_date_key_is_jst_yyyymmdd() -> None:
    when = datetime(2026, 9, 8, 0, 10, tzinfo=JST)
    assert candle_date_key("5min", when) == "20260908"
    utc = datetime(2026, 9, 7, 15, 10, tzinfo=timezone.utc)  # 00:10 JST next day
    assert candle_date_key("5min", utc) == "20260908"


def test_synthetic_5min_closed() -> None:
    candles = synthetic_candles(10, candle_type="5min")
    assert len(candles) == 10
    assert candles[1].timestamp_ms - candles[0].timestamp_ms == 5 * 60 * 1000


def test_fetch_raises_when_all_days_fail() -> None:
    rest = MagicMock()
    rest.get_candlestick.side_effect = BitbankAPIError(
        "boom", http_status=500, code=10000, endpoint="https://public.bitbank.cc/x"
    )
    with pytest.raises(BitbankAPIError):
        fetch_candles(rest, cfg(candle_type="5min", candle_lookback_days=2))


def test_fetch_keeps_partial_days() -> None:
    rest = MagicMock()
    calls = {"n": 0}

    def _get(pair: str, candle_type: str, date_key: str):
        calls["n"] += 1
        if calls["n"] == 1:
            raise BitbankAPIError("skip", http_status=404)
        return [["100", "101", "99", "100", "1", 1_700_000_000_000 + calls["n"]]]

    rest.get_candlestick.side_effect = _get
    candles = fetch_candles(rest, cfg(candle_type="5min", candle_lookback_days=3))
    assert len(candles) >= 1
