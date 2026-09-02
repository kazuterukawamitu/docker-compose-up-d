"""Higher-timeframe trend filter (4h + 1d). Does not place orders.

BUY is blocked when both 4-hour and 1-day moving averages slope down.
This is a hard filter, not a second strategy engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from bitbank_bot.config import Config, LONG_CANDLE_TYPES, SHORT_CANDLE_TYPES
from bitbank_bot.indicators import Trend, ma_trend, moving_average
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import CANDLE_MS, Candle, candle_date_key, parse_ohlcv
from bitbank_bot.rest_client import RestClient

JST = timezone(timedelta(hours=9))

HTF_TYPES = ("4hour", "1day")


@dataclass(frozen=True)
class HtfVerdict:
    allow_buy: bool
    reason: str
    trend_4h: str
    trend_1d: str


def _fetch_type(client: RestClient, pair: str, candle_type: str) -> list[Candle]:
    now = datetime.now(JST)
    keys: list[str] = []
    if candle_type in SHORT_CANDLE_TYPES:
        for i in range(3):
            keys.append(candle_date_key(candle_type, now - timedelta(days=i)))
    elif candle_type in LONG_CANDLE_TYPES:
        keys.append(candle_date_key(candle_type, now))
        keys.append(candle_date_key(candle_type, now.replace(year=now.year - 1)))
    else:
        return []
    seen: set[int] = set()
    candles: list[Candle] = []
    for key in keys:
        try:
            rows = client.get_candlestick(pair, candle_type, key)
        except Exception as exc:
            slog("MARKET", "htf fetch skipped", candle_type=candle_type, error=type(exc).__name__)
            continue
        for row in rows:
            try:
                candle = parse_ohlcv(row)
            except Exception:
                continue
            if candle.timestamp_ms in seen:
                continue
            seen.add(candle.timestamp_ms)
            candles.append(candle)
    candles.sort(key=lambda c: c.timestamp_ms)
    width = CANDLE_MS.get(candle_type)
    if candles and width is not None:
        now_ms = int(now.timestamp() * 1000)
        if now_ms < candles[-1].timestamp_ms + width:
            candles = candles[:-1]
    return candles


def _trend_of(candles: list[Candle], period: int, slope: Decimal) -> Trend | None:
    if len(candles) < period + 1:
        return None
    closes = [c.close for c in candles]
    series = moving_average(closes, period, "sma")
    current = series[-1]
    previous = series[-2]
    if current is None or previous is None:
        return None
    return ma_trend(current, previous, slope)


def evaluate_htf(client: RestClient, cfg: Config) -> HtfVerdict:
    """Return whether a new BUY is allowed by 4h+1d slope."""
    trend_4h = _trend_of(_fetch_type(client, cfg.pair, "4hour"), cfg.ma_period, cfg.ma_slope_threshold)
    trend_1d = _trend_of(_fetch_type(client, cfg.pair, "1day"), cfg.ma_period, cfg.ma_slope_threshold)
    label_4h = trend_4h.value if trend_4h is not None else "unknown"
    label_1d = trend_1d.value if trend_1d is not None else "unknown"
    if trend_4h is None or trend_1d is None:
        slog("STRATEGY", "htf unavailable; blocking BUY", trend_4h=label_4h, trend_1d=label_1d)
        return HtfVerdict(False, "htf_unavailable", label_4h, label_1d)
    if trend_4h == Trend.DOWN and trend_1d == Trend.DOWN:
        slog("STRATEGY", "htf downtrend; blocking BUY", trend_4h=label_4h, trend_1d=label_1d)
        return HtfVerdict(False, "htf_downtrend", label_4h, label_1d)
    return HtfVerdict(True, "htf_ok", label_4h, label_1d)


def synthetic_htf_ok() -> HtfVerdict:
    return HtfVerdict(True, "htf_synthetic", "flat", "flat")
