"""Candle fetch, cache, and synthetic series for dry-run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Iterable

from bitbank_bot.config import (
    DEFAULT_MA_PERIOD,
    LONG_CANDLE_TYPES,
    SHORT_CANDLE_TYPES,
    Config,
)
from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D
from bitbank_bot.rest_client import BitbankAPIError, RestClient

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
    local = when.astimezone(JST) if when.tzinfo else when.replace(tzinfo=JST)
    if candle_type in SHORT_CANDLE_TYPES:
        return local.strftime("%Y%m%d")
    if candle_type in LONG_CANDLE_TYPES:
        return local.strftime("%Y")
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


def _date_keys(cfg: Config, now: datetime, *, latest_only: bool) -> list[str]:
    keys: list[str] = []
    if cfg.candle_type in SHORT_CANDLE_TYPES:
        days = 2 if latest_only else cfg.candle_lookback_days
        # Always include today + yesterday on latest_only so JST midnight
        # cannot return an empty "today" file as a total miss.
        for i in range(days):
            keys.append(candle_date_key(cfg.candle_type, now - timedelta(days=i)))
    else:
        keys.append(candle_date_key(cfg.candle_type, now))
        if not latest_only:
            keys.append(candle_date_key(cfg.candle_type, now.replace(year=now.year - 1)))
    # unique, today first
    seen: set[str] = set()
    out: list[str] = []
    for key in keys:
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def fetch_candles(
    client: RestClient,
    cfg: Config,
    *,
    latest_only: bool = False,
) -> list[Candle]:
    now = datetime.now(JST)
    keys = _date_keys(cfg, now, latest_only=latest_only)
    seen: set[int] = set()
    candles: list[Candle] = []
    errors: list[BitbankAPIError] = []
    for key in keys:
        try:
            rows = client.get_candlestick(cfg.pair, cfg.candle_type, key)
        except BitbankAPIError as exc:
            slog(
                "CANDLE_API_ERROR",
                "candlestick fetch failed",
                pair=cfg.pair,
                type=cfg.candle_type,
                date=key,
                http_status=exc.http_status,
                bitbank_code=exc.code,
                endpoint=exc.endpoint or f"/{cfg.pair}/candlestick/{cfg.candle_type}/{key}",
                retry_count=exc.retry_count,
                error=type(exc).__name__,
            )
            errors.append(exc)
            continue
        except Exception as exc:
            slog(
                "CANDLE_API_ERROR",
                "candlestick fetch failed",
                pair=cfg.pair,
                type=cfg.candle_type,
                date=key,
                http_status=None,
                bitbank_code=None,
                endpoint=f"{cfg.public_url}/{cfg.pair}/candlestick/{cfg.candle_type}/{key}",
                retry_count=0,
                error=type(exc).__name__,
                function="fetch_candles",
            )
            errors.append(BitbankAPIError(str(exc)))
            continue
        for row in rows:
            try:
                candle = parse_ohlcv(row)
            except (IndexError, TypeError, ValueError, InvalidOperation) as exc:
                slog(
                    "ERROR",
                    "skipping malformed ohlcv row",
                    error=type(exc).__name__,
                    function="parse_ohlcv",
                    pair=cfg.pair,
                )
                continue
            if candle.timestamp_ms in seen:
                continue
            seen.add(candle.timestamp_ms)
            candles.append(candle)
    candles.sort(key=lambda c: c.timestamp_ms)
    closed = drop_incomplete_candle(candles, cfg.candle_type)
    slog(
        "MARKET",
        "candles loaded",
        count=len(closed),
        raw_count=len(candles),
        candle_type=cfg.candle_type,
        date_keys=len(keys),
        errors=len(errors),
        closed_ready=len(closed),
    )
    if not closed and errors:
        raise errors[-1]
    return closed


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
        self.real = False

    def merge(self, incoming: Iterable[Candle], *, real: bool = True) -> list[Candle]:
        for candle in incoming:
            self._by_ts[candle.timestamp_ms] = candle
        self.candles = sorted(self._by_ts.values(), key=lambda c: c.timestamp_ms)
        if real and self.candles:
            self.real = True
        return self.candles


def synthetic_candles(n: int = 80, candle_type: str = "5min") -> list[Candle]:
    """Closed bars so --once --synthetic never waits on a forming candle."""
    width = CANDLE_MS.get(candle_type, CANDLE_MS["5min"])
    now_ms = int(datetime.now(JST).timestamp() * 1000)
    last_close = now_ms - (now_ms % width) - width
    base_ts = last_close - (n - 1) * width
    price = Decimal("10000000")
    candles: list[Candle] = []
    for i in range(n):
        p = price - Decimal(i) * Decimal("5000")
        candles.append(Candle(p, p, p, p, Decimal("1"), base_ts + i * width))
    return candles
