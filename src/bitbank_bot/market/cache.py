from __future__ import annotations

import time
from decimal import Decimal

from bitbank_bot.models import Candle, Ticker


class MarketCache:
    def __init__(self) -> None:
        self.candles: list[Candle] = []
        self.ticker: Ticker | None = None
        self.circuit_mode: str = "NONE"
        self.ws_connected: bool = False
        self.last_ws_ms: int = 0
        self.last_rest_ms: int = 0

    def set_candles(self, candles: list[Candle]) -> None:
        self.candles = sorted(candles, key=lambda c: c.ts)
        self.last_rest_ms = _now_ms()

    def upsert_ticker(self, ticker: Ticker, source: str) -> None:
        self.ticker = ticker
        now = _now_ms()
        if source == "ws":
            self.last_ws_ms = now
        else:
            self.last_rest_ms = now

    def age_ms(self) -> int | None:
        if self.ticker is None:
            return None
        stamp = max(self.last_ws_ms, self.last_rest_ms, self.ticker.timestamp_ms)
        return max(0, _now_ms() - stamp)

    def last_price(self) -> Decimal | None:
        if self.ticker is not None:
            return self.ticker.last
        if self.candles:
            return self.candles[-1].close
        return None


def _now_ms() -> int:
    return int(time.time() * 1000)
