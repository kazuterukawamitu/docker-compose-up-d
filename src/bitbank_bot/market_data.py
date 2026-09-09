"""Candle fetch, cache, and synthetic series for dry-run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable

from bitbank_bot.config import (
    DEFAULT_MA_PERIOD,
    LONG_CANDLE_TYPES,
    SHORT_CANDLE_TYPES,
    Config,
)
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D
from bitbank_bot.rest_client import BitbankAPIError

JST = timezone(timedelta(hours=9))

CANDLE_MS: dict[str, int] = {
    "1min": 60_000,
    "5min": 5 * 60 * 1000,
    "15min": 15 * 60 * 1000,
    "30min": 30 * 60 * 1000,
    "1hour": 60 * 60 * 1000,
    "4hour": 4 * 60 * 60 * 1000,
    "8hour": 8 * 60 * 60 * 1000,
    "12hour": 12 * 60 * 60 * 1000,
    "1day": 24 * 60 * 60 * 1000,
    "1week": 7 * 24 * 60 * 60 * 1000,
    "1month": 30 * 24 * 60 * 60 * 1000,
}


@dataclass(frozen=True)
class Candle:
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    timestamp_ms: int


def candle_date_key(candle_type: str, when: datetime) -> str:
    if candle_type in SHORT_CANDLE_TYPES:
        return when.strftime("%Y%m%d")
    if candle_type in LONG_CANDLE_TYPES:
        return when.strftime("%Y")
    raise ValueError(f"unknown candle type {candle_type}")


def parse_ohlcv(row: list[object]) -> Candle:
    if len(row) < 6:
        raise ValueError("ohlcv row too short")
    return Candle(
        open=D(row[0]),
        high=D(row[1]),
        low=D(row[2]),
        close=D(row[3]),
        volume=D(row[4]),
        timestamp_ms=int(row[5]),
    )


def fetch_candles(
    client: Any,
    cfg: Config,
    *,
    latest_only: bool = False,
) -> list[Candle]:
    now = datetime.now(JST)
    keys: list[str] = []
    if cfg.candle_type in SHORT_CANDLE_TYPES:
        # Bitbank returns HTTP 404 / code 10000 for today's YYYYMMDD until that
        # date file exists. Always include yesterday on latest_only so a new
        # JST day does not empty the book and trip synthetic fallback.
        days = 2 if latest_only else cfg.candle_lookback_days
        for i in range(days):
            keys.append(candle_date_key(cfg.candle_type, now - timedelta(days=i)))
    else:
        keys.append(candle_date_key(cfg.candle_type, now))
        if not latest_only:
            keys.append(candle_date_key(cfg.candle_type, now.replace(year=now.year - 1)))

    seen: set[int] = set()
    candles: list[Candle] = []
    for key in keys:
        rows: list[list[object]] = []
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                rows = client.get_candlestick(cfg.pair, cfg.candle_type, key)
                last_error = None
                break
            except BitbankAPIError as exc:
                last_error = exc
                missing = exc.http_status == 404 or exc.code == 10000
                slog(
                    "CANDLE_API_ERROR",
                    "date file missing" if missing else ("fetch retry" if attempt == 0 else "fetch failed"),
                    pair=cfg.pair,
                    candle_type=cfg.candle_type,
                    date=key,
                    endpoint=exc.endpoint,
                    http_status=exc.http_status,
                    bitbank_code=exc.code,
                    retry_count=attempt + 1,
                )
                if missing:
                    break
            except Exception as exc:
                last_error = exc
                slog(
                    "CANDLE_API_ERROR",
                    "candlestick fetch skipped",
                    pair=cfg.pair,
                    candle_type=cfg.candle_type,
                    date=key,
                    error=type(exc).__name__,
                    retry_count=attempt + 1,
                )
        if last_error is not None:
            continue
        for row in rows:
            try:
                candle = parse_ohlcv(row)
            except (IndexError, TypeError, ValueError, InvalidOperation):
                slog("ERROR", "skipping malformed ohlcv row")
                continue
            if candle.timestamp_ms in seen:
                continue
            seen.add(candle.timestamp_ms)
            candles.append(candle)
    candles.sort(key=lambda c: c.timestamp_ms)
    slog("MARKET", "candles loaded", count=len(candles), candle_type=cfg.candle_type)
    return drop_incomplete_candle(candles, cfg.candle_type)


def drop_incomplete_candle(
    candles: list[Candle],
    candle_type: str,
    now_ms: int | None = None,
) -> list[Candle]:
    if not candles:
        return candles
    width = CANDLE_MS.get(candle_type)
    if width is None:
        return candles
    if now_ms is None:
        now_ms = int(datetime.now(JST).timestamp() * 1000)
    last = candles[-1]
    if now_ms < last.timestamp_ms + width:
        slog(
            "MARKET",
            "WAIT incomplete candle dropped",
            candle_type=candle_type,
            ts=last.timestamp_ms,
        )
        return candles[:-1]
    return candles


class CandleCache:
    def __init__(self, ma_period: int = DEFAULT_MA_PERIOD) -> None:
        self._by_ts: dict[int, Candle] = {}
        self.candles: list[Candle] = []
        self.ma_period = ma_period

    def merge(self, incoming: Iterable[Candle]) -> list[Candle]:
        for candle in incoming:
            self._by_ts[candle.timestamp_ms] = candle
        self.candles = sorted(self._by_ts.values(), key=lambda c: c.timestamp_ms)
        return self.candles


def synthetic_candles(n: int = 80) -> list[Candle]:
    """Closed hourly bars so --once --synthetic never waits on a forming candle."""
    hour = 3_600_000
    now_ms = int(datetime.now(JST).timestamp() * 1000)
    last_close = now_ms - (now_ms % hour) - hour
    base_ts = last_close - (n - 1) * hour
    price = Decimal("10000000")
    candles: list[Candle] = []
    for i in range(n):
        p = price - Decimal(i) * Decimal("5000")
        candles.append(Candle(p, p, p, p, Decimal("1"), base_ts + i * hour))
    return candles
