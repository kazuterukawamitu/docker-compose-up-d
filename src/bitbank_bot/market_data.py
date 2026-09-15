"""Candle fetch, cache, and synthetic series for dry-run."""

from __future__ import annotations

from dataclasses import dataclass, field
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
from bitbank_bot.money import D, ZERO
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


@dataclass
class CandleFetchResult:
    candles: list[Candle]
    market_data_real: bool
    errors: list[dict[str, Any]] = field(default_factory=list)
    date_keys: list[str] = field(default_factory=list)
    fetched_count: int = 0
    closed_count: int = 0


def as_jst(now: datetime | None = None) -> datetime:
    """Interpret naive clocks as JST; convert aware clocks into JST."""
    if now is None:
        return datetime.now(JST)
    if now.tzinfo is None:
        return now.replace(tzinfo=JST)
    return now.astimezone(JST)


def shift_years(when: datetime, years: int) -> datetime:
    """Shift calendar year. Feb 29 maps to Feb 28 when the target year is not a leap year."""
    when = as_jst(when)
    target = when.year + years
    try:
        return when.replace(year=target)
    except ValueError:
        return when.replace(year=target, month=2, day=28)


def candle_date_key(candle_type: str, when: datetime) -> str:
    when = as_jst(when)
    if candle_type in SHORT_CANDLE_TYPES:
        return when.strftime("%Y%m%d")
    if candle_type in LONG_CANDLE_TYPES:
        return when.strftime("%Y")
    raise ValueError(f"unknown candle type {candle_type}")


def candle_date_keys(
    candle_type: str,
    now: datetime,
    *,
    latest_only: bool,
    lookback_days: int,
) -> list[str]:
    now = as_jst(now)
    keys: list[str] = []
    if candle_type in SHORT_CANDLE_TYPES:
        days = 1 if latest_only else max(1, int(lookback_days))
        for i in range(days):
            keys.append(candle_date_key(candle_type, now - timedelta(days=i)))
        yesterday = candle_date_key(candle_type, now - timedelta(days=1))
        if yesterday not in keys:
            keys.append(yesterday)
    else:
        keys.append(candle_date_key(candle_type, now))
        if not latest_only:
            keys.append(candle_date_key(candle_type, shift_years(now, -1)))
    return keys


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


def _log_candle_api_error(
    *,
    pair: str,
    candle_type: str,
    date_key: str,
    exc: Exception,
    retry_count: int = 0,
) -> dict[str, Any]:
    endpoint = ""
    http_status = None
    bitbank_code = None
    if isinstance(exc, BitbankAPIError):
        endpoint = exc.endpoint
        http_status = exc.http_status
        bitbank_code = exc.code
        retry_count = exc.retry_count
    payload = {
        "endpoint": endpoint or f"/{pair}/candlestick/{candle_type}/{date_key}",
        "http_status": http_status,
        "bitbank_code": bitbank_code,
        "pair": pair,
        "candle_type": candle_type,
        "date": date_key,
        "retry_count": retry_count,
        "error": type(exc).__name__,
    }
    slog("CANDLE_API_ERROR", "candlestick fetch failed", **payload)
    return payload


def fetch_candles_detailed(
    client: RestClient,
    cfg: Config,
    *,
    latest_only: bool = False,
    now: datetime | None = None,
) -> CandleFetchResult:
    now = as_jst(now)
    keys = candle_date_keys(
        cfg.candle_type,
        now,
        latest_only=latest_only,
        lookback_days=cfg.candle_lookback_days,
    )
    seen: set[int] = set()
    candles: list[Candle] = []
    errors: list[dict[str, Any]] = []
    last_error: Exception | None = None
    for key in keys:
        try:
            rows = client.get_candlestick(cfg.pair, cfg.candle_type, key)
        except Exception as exc:
            last_error = exc
            errors.append(
                _log_candle_api_error(
                    pair=cfg.pair,
                    candle_type=cfg.candle_type,
                    date_key=key,
                    exc=exc,
                )
            )
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
    slog(
        "MARKET",
        "candles loaded",
        count=len(candles),
        candle_type=cfg.candle_type,
        pair=cfg.pair,
        dates=",".join(keys),
        errors=len(errors),
    )
    closed = drop_incomplete_candle(
        candles, cfg.candle_type, now_ms=int(now.timestamp() * 1000)
    )
    slog(
        "MARKET",
        "closed candles ready",
        count=len(closed),
        fetched=len(candles),
        candle_type=cfg.candle_type,
        market_data_real=bool(closed),
    )
    if not candles and last_error is not None:
        raise last_error
    return CandleFetchResult(
        candles=closed,
        market_data_real=bool(closed),
        errors=errors,
        date_keys=keys,
        fetched_count=len(candles),
        closed_count=len(closed),
    )


def fetch_candles(
    client: RestClient,
    cfg: Config,
    *,
    latest_only: bool = False,
) -> list[Candle]:
    return fetch_candles_detailed(client, cfg, latest_only=latest_only).candles


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


def candles_are_fresh(
    candles: list[Candle],
    candle_type: str,
    *,
    now_ms: int | None = None,
    max_widths: int = 3,
) -> bool:
    if not candles:
        return False
    width = CANDLE_MS.get(candle_type)
    if width is None:
        return True
    if now_ms is None:
        now_ms = int(datetime.now(JST).timestamp() * 1000)
    return now_ms <= candles[-1].timestamp_ms + width * max_widths


def ticker_close_mismatch(
    candle_close: Decimal,
    ticker_last: Decimal | None,
    stale_price_pct: Decimal,
) -> bool:
    if ticker_last is None or ticker_last <= ZERO or candle_close <= ZERO:
        return False
    delta = abs(ticker_last - candle_close) / candle_close
    return delta > D(stale_price_pct)


class CandleCache:
    def __init__(self, ma_period: int = DEFAULT_MA_PERIOD) -> None:
        self._by_ts: dict[int, Candle] = {}
        self.candles: list[Candle] = []
        self.ma_period = ma_period
        self.market_data_real = False

    def merge(self, incoming: Iterable[Candle], *, real: bool = True) -> list[Candle]:
        if not real:
            return list(self.candles)
        for candle in incoming:
            self._by_ts[candle.timestamp_ms] = candle
        self.candles = sorted(self._by_ts.values(), key=lambda c: c.timestamp_ms)
        if incoming:
            self.market_data_real = True
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
