"""Fetch and cache OHLCV, then attach indicator series."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from bitbank_bot.config import Settings
from bitbank_bot.exchange.rest import BitbankRest
from bitbank_bot.market.indicators import (
    atr as atr_fn,
    bollinger,
    classify_ma_trend,
    ema as ema_fn,
    macd as macd_fn,
    rsi as rsi_fn,
    sma as sma_fn,
)
from bitbank_bot.models import Candle, MaTrend, Snapshot, Ticker


def _closes(candles: list[Candle]) -> list[Decimal]:
    return [c.close for c in candles]


def _highs(candles: list[Candle]) -> list[Decimal]:
    return [c.high for c in candles]


def _lows(candles: list[Candle]) -> list[Decimal]:
    return [c.low for c in candles]


class MarketData:
    def __init__(self, settings: Settings, rest: BitbankRest) -> None:
        self._settings = settings
        self._rest = rest
        self._candles: list[Candle] = []

    async def refresh(self, ticker: Ticker | None = None) -> Snapshot:
        candles = await self._load_candles()
        self._candles = candles
        if ticker is None:
            ticker = await self._rest.get_ticker()
        return build_snapshot(candles, ticker, self._settings)

    async def _load_candles(self) -> list[Candle]:
        candle_type = self._settings.candle_type
        dates = _needed_dates(candle_type, days=3)
        merged: dict[int, Candle] = {}
        for stamp in dates:
            try:
                rows = await self._rest.get_candles(yyyymmdd_or_yyyy=stamp)
            except Exception:
                continue
            for candle in rows:
                merged[candle.timestamp_ms] = candle
        return [merged[k] for k in sorted(merged)]


def build_snapshot(candles: list[Candle], ticker: Ticker, settings: Settings) -> Snapshot:
    closes = _closes(candles)
    ma_fn = ema_fn if settings.ma_type == "ema" else sma_fn
    ma = tuple(ma_fn(closes, settings.ma_period))
    fast = tuple(ma_fn(closes, settings.fast_ma))
    slow = tuple(ma_fn(closes, settings.slow_ma))
    rsi = tuple(rsi_fn(closes, 14))
    macd_line, signal_line, _hist = macd_fn(closes)
    atr = tuple(atr_fn(_highs(candles), _lows(candles), closes, 14))
    upper, mid, lower = bollinger(closes, 20, Decimal("2"))
    trend = classify_ma_trend(ma, settings.trend_lookback, settings.trend_threshold)
    prev = classify_ma_trend(ma[:-1], settings.trend_lookback, settings.trend_threshold)
    return Snapshot(
        candles=tuple(candles),
        ticker=ticker,
        ma=ma,
        fast_ma=fast,
        slow_ma=slow,
        rsi=rsi,
        macd=tuple(macd_line),
        macd_signal=tuple(signal_line),
        atr=atr,
        bb_upper=tuple(upper),
        bb_mid=tuple(mid),
        bb_lower=tuple(lower),
        ma_trend=trend,
        prev_ma_trend=prev,
    )


def _needed_dates(candle_type: str, days: int) -> list[str]:
    now = datetime.now(timezone.utc)
    if candle_type in {"1min", "5min", "15min", "30min"}:
        return [(now - timedelta(days=i)).strftime("%Y%m%d") for i in range(days, -1, -1)]
    years = {now.strftime("%Y"), (now - timedelta(days=370)).strftime("%Y")}
    return sorted(years)
