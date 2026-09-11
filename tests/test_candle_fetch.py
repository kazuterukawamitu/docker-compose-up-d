from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

from bitbank_bot.market_data import (
    Candle,
    CandleCache,
    as_jst,
    candle_date_keys,
    candles_are_fresh,
    fetch_candles_detailed,
    ticker_close_mismatch,
)
from bitbank_bot.rest_client import BitbankAPIError
from tests.helpers import cfg

JST = timezone(timedelta(hours=9))


class _CandleClient:
    def __init__(self, by_key: dict[str, list[list[Any]]] | Exception) -> None:
        self.by_key = by_key
        self.calls: list[tuple[str, str, str]] = []

    def get_candlestick(self, pair: str, candle_type: str, date_key: str) -> list[list[Any]]:
        self.calls.append((pair, candle_type, date_key))
        if isinstance(self.by_key, Exception):
            raise self.by_key
        if date_key in self.by_key and isinstance(self.by_key[date_key], Exception):
            raise self.by_key[date_key]  # type: ignore[misc]
        return list(self.by_key.get(date_key) or [])


def test_latest_only_includes_yesterday_for_5min() -> None:
    now = datetime(2026, 9, 11, 0, 2, tzinfo=JST)
    keys = candle_date_keys("5min", now, latest_only=True, lookback_days=14)
    assert "20260911" in keys
    assert "20260910" in keys


def test_fetch_logs_error_and_raises_when_all_keys_fail() -> None:
    err = BitbankAPIError(
        "api success=0 code=10000",
        code=10000,
        http_status=200,
        endpoint="/btc_jpy/candlestick/5min/20260911",
        retry_count=2,
    )
    client = _CandleClient(err)
    c = cfg(candle_type="5min", candle_lookback_days=1)
    with pytest.raises(BitbankAPIError):
        fetch_candles_detailed(client, c, latest_only=True)  # type: ignore[arg-type]
    assert client.calls
    assert all(call[0] == "btc_jpy" and call[1] == "5min" for call in client.calls)


def test_fetch_keeps_real_rows_when_one_date_fails() -> None:
    err = BitbankAPIError("boom", code=1, http_status=500, endpoint="/x")
    now = datetime(2026, 9, 11, 12, 0, tzinfo=JST)
    ts = int((now - timedelta(hours=1)).timestamp() * 1000)
    row = ["100", "110", "90", "105", "1", ts]
    client = _CandleClient({"20260911": err, "20260910": [row]})
    c = cfg(candle_type="5min", candle_lookback_days=1)
    result = fetch_candles_detailed(client, c, latest_only=True, now=now)  # type: ignore[arg-type]
    assert result.market_data_real is True
    assert result.closed_count == 1
    assert result.errors


def test_cache_does_not_merge_synthetic() -> None:
    cache = CandleCache(20)
    real = Candle(Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), 1)
    cache.merge([real], real=True)
    fake = Candle(Decimal("9"), Decimal("9"), Decimal("9"), Decimal("9"), Decimal("1"), 2)
    out = cache.merge([fake], real=False)
    assert len(out) == 1
    assert out[0].close == Decimal("1")
    assert cache.market_data_real is True


def test_utc_now_uses_jst_date_key() -> None:
    utc = datetime(2026, 3, 15, 16, 0, tzinfo=timezone.utc)
    assert as_jst(utc).strftime("%Y%m%d") == "20260316"
    keys = candle_date_keys("5min", utc, latest_only=True, lookback_days=14)
    assert "20260316" in keys
    assert "20260315" in keys
    jst_keys = candle_date_keys(
        "5min", datetime(2026, 3, 15, 16, 0, tzinfo=JST), latest_only=True, lookback_days=1
    )
    assert "20260315" in jst_keys
    assert "20260316" not in jst_keys


def test_lookback_zero_still_includes_today_and_yesterday() -> None:
    now = datetime(2026, 9, 11, 12, 0, tzinfo=JST)
    keys = candle_date_keys("5min", now, latest_only=False, lookback_days=0)
    assert "20260911" in keys
    assert "20260910" in keys


def test_naive_datetime_is_treated_as_jst() -> None:
    naive = datetime(2026, 9, 11, 0, 2)
    keys = candle_date_keys("5min", naive, latest_only=True, lookback_days=1)
    assert keys[0] == "20260911"


def test_ticker_close_mismatch_and_freshness() -> None:
    assert ticker_close_mismatch(Decimal("100"), Decimal("104"), Decimal("0.03"))
    assert not ticker_close_mismatch(Decimal("100"), Decimal("101"), Decimal("0.03"))
    candle = Candle(Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), Decimal("1"), 1_000_000)
    assert candles_are_fresh([candle], "5min", now_ms=1_000_000 + 5 * 60 * 1000)
    assert not candles_are_fresh([candle], "5min", now_ms=1_000_000 + 20 * 60 * 1000)


def test_shift_years_leap_day_does_not_raise() -> None:
    from bitbank_bot.market_data import shift_years

    leap = datetime(2024, 2, 29, 12, 0, tzinfo=JST)
    shifted = shift_years(leap, -1)
    assert shifted.year == 2023
    assert shifted.month == 2
    assert shifted.day == 28


def test_long_candle_keys_on_leap_day() -> None:
    leap = datetime(2024, 2, 29, 15, 0, tzinfo=JST)
    keys = candle_date_keys("1day", leap, latest_only=False, lookback_days=1)
    assert "2024" in keys
    assert "2023" in keys


def test_incomplete_drop_uses_injected_now() -> None:
    now = datetime(2026, 9, 11, 12, 0, tzinfo=JST)
    ts = int(now.timestamp() * 1000)
    row = ["100", "110", "90", "105", "1", ts]
    client = _CandleClient({"20260911": [row], "20260910": []})
    c = cfg(candle_type="5min", candle_lookback_days=1)
    result = fetch_candles_detailed(client, c, latest_only=True, now=now)  # type: ignore[arg-type]
    assert result.fetched_count == 1
    assert result.closed_count == 0
    assert result.market_data_real is False

