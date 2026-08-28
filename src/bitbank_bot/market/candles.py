from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from bitbank_bot.decimal_utils import d
from bitbank_bot.models import Candle

JST = ZoneInfo("Asia/Tokyo")

_DAY_TYPES = {"1min", "5min", "15min", "30min", "1hour"}


def parse_ohlcv_row(row: list[Any]) -> Candle:
    return Candle(
        ts=int(row[5]),
        open=d(row[0]),
        high=d(row[1]),
        low=d(row[2]),
        close=d(row[3]),
        volume=d(row[4]),
    )


def candle_date_keys(candle_type: str, days_back: int = 10) -> list[str]:
    now = datetime.now(JST)
    keys: list[str] = []
    if candle_type in _DAY_TYPES:
        for i in range(days_back):
            day = now - timedelta(days=i)
            keys.append(day.strftime("%Y%m%d"))
    else:
        year = now.year
        keys.append(str(year))
        if now.month == 1:
            keys.append(str(year - 1))
    return keys


def merge_candles(*groups: list[Candle]) -> list[Candle]:
    by_ts: dict[int, Candle] = {}
    for group in groups:
        for candle in group:
            by_ts[candle.ts] = candle
    return sorted(by_ts.values(), key=lambda c: c.ts)


def from_csv_rows(rows: list[dict[str, str]]) -> list[Candle]:
    candles: list[Candle] = []
    for row in rows:
        ts_raw = row.get("ts") or row.get("timestamp") or row.get("time")
        if ts_raw is None:
            raise ValueError("CSV row missing ts/timestamp")
        ts = int(ts_raw)
        if ts < 10_000_000_000:
            ts *= 1000
        candles.append(
            Candle(
                ts=ts,
                open=d(row["open"]),
                high=d(row["high"]),
                low=d(row["low"]),
                close=d(row["close"]),
                volume=d(row.get("volume", "0")),
            )
        )
    return sorted(candles, key=lambda c: c.ts)


def synthetic_trend(
    start: Decimal,
    steps: list[Decimal],
    start_ts: int = 1_700_000_000_000,
    step_ms: int = 300_000,
) -> list[Candle]:
    candles: list[Candle] = []
    price = start
    ts = start_ts
    for delta in steps:
        nxt = price + delta
        high = max(price, nxt)
        low = min(price, nxt)
        candles.append(Candle(ts=ts, open=price, high=high, low=low, close=nxt, volume=Decimal("1")))
        price = nxt
        ts += step_ms
    return candles


def utc_ms_to_iso(ts_ms: int) -> str:
    return datetime.fromtimestamp(ts_ms / 1000, tz=UTC).isoformat()
