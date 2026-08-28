"""Candle fetch and synthetic series for Bitbank public candlestick API."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable

from bitbank_bot.config import LONG_CANDLE_TYPES, SHORT_CANDLE_TYPES, Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D
from bitbank_bot.rest_client import RestClient

JST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Candle:
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    timestamp_ms: int

    @property
    def ts(self) -> int:
        return self.timestamp_ms


def candle_date_key(candle_type: str, when: datetime) -> str:
    if candle_type in SHORT_CANDLE_TYPES:
        return when.strftime("%Y%m%d")
    if candle_type in LONG_CANDLE_TYPES:
        return when.strftime("%Y")
    raise ValueError(f"unknown candle type {candle_type}")


def parse_ohlcv(row: list[object]) -> Candle:
    return Candle(
        open=D(row[0]),
        high=D(row[1]),
        low=D(row[2]),
        close=D(row[3]),
        volume=D(row[4]),
        timestamp_ms=int(row[5]),
    )


def fetch_candles(client: RestClient, cfg: Config) -> list[Candle]:
    now = datetime.now(JST)
    keys: list[str] = []
    if cfg.candle_type in SHORT_CANDLE_TYPES:
        for i in range(cfg.candle_lookback_days):
            keys.append(candle_date_key(cfg.candle_type, now - timedelta(days=i)))
    else:
        keys.append(candle_date_key(cfg.candle_type, now))
        keys.append(candle_date_key(cfg.candle_type, now.replace(year=now.year - 1)))

    seen: set[int] = set()
    candles: list[Candle] = []
    for key in keys:
        try:
            rows = client.get_candlestick(cfg.pair, cfg.candle_type, key)
        except Exception as exc:
            slog("MARKET", "candlestick fetch skipped", date_key=key, error=type(exc).__name__)
            continue
        for row in rows:
            try:
                candle = parse_ohlcv(row)
            except (IndexError, TypeError, ValueError):
                continue
            if candle.timestamp_ms in seen:
                continue
            seen.add(candle.timestamp_ms)
            candles.append(candle)
    candles.sort(key=lambda c: c.timestamp_ms)
    slog("MARKET", "candles loaded", count=len(candles), candle_type=cfg.candle_type)
    return candles


def aggregate_candles(candles: list[Candle], bucket_ms: int) -> list[Candle]:
    """Build 10min from 5min, 2day from 1day, 2week from 1week."""
    buckets: dict[int, list[Candle]] = {}
    for candle in candles:
        key = candle.timestamp_ms - (candle.timestamp_ms % bucket_ms)
        buckets.setdefault(key, []).append(candle)
    out: list[Candle] = []
    for key in sorted(buckets):
        chunk = buckets[key]
        out.append(
            Candle(
                open=chunk[0].open,
                high=max(c.high for c in chunk),
                low=min(c.low for c in chunk),
                close=chunk[-1].close,
                volume=sum((c.volume for c in chunk), D("0")),
                timestamp_ms=key,
            )
        )
    return out


def synthetic_candles(count: int = 120, start: Decimal = D("10000000")) -> list[Candle]:
    candles: list[Candle] = []
    price = start
    base_ts = 1_700_000_000_000
    for i in range(count):
        wave = D(i % 17) - D(8)
        delta = wave * D("2000")
        price = price + delta
        o = price - D("500")
        h = price + D("1500")
        low = price - D("1500")
        candles.append(
            Candle(
                open=o,
                high=h,
                low=low,
                close=price,
                volume=D("1.5"),
                timestamp_ms=base_ts + i * 900_000,
            )
        )
    return candles


def candles_from_csv(rows: Iterable[list[str]]) -> list[Candle]:
    out: list[Candle] = []
    for row in rows:
        if not row or row[0].lower().startswith("timestamp"):
            continue
        ts = int(row[0])
        out.append(
            Candle(
                open=D(row[1]),
                high=D(row[2]),
                low=D(row[3]),
                close=D(row[4]),
                volume=D(row[5] if len(row) > 5 else "0"),
                timestamp_ms=ts,
            )
        )
    return out
