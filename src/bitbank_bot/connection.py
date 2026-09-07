"""REST/WS health, freshness, and a 0–100 score. Decoupled from strategy."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog


@dataclass
class ConnectionHealth:
    score: int
    rest_ok: bool
    ws_ok: bool
    ticker_age: float | None
    candle_age: float | None
    stale: bool
    reason: str


class ConnectionManager:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.last_ticker_mono = 0.0
        self.last_candle_mono = 0.0
        self.last_rest_ok_mono = 0.0
        self.last_ws_ok_mono = 0.0
        self.last_error = ""
        self._rest_failures = 0

    def note_ticker(self) -> None:
        now = time.monotonic()
        self.last_ticker_mono = now
        self.last_rest_ok_mono = now
        self._rest_failures = 0

    def note_candles(self) -> None:
        now = time.monotonic()
        self.last_candle_mono = now
        self.last_rest_ok_mono = now
        self._rest_failures = 0

    def note_rest_ok(self) -> None:
        self.last_rest_ok_mono = time.monotonic()
        self._rest_failures = 0

    def note_ws_ok(self) -> None:
        self.last_ws_ok_mono = time.monotonic()

    def note_rest_error(self, error: str) -> None:
        self.last_error = error
        self._rest_failures += 1

    def _age(self, stamp: float) -> float | None:
        if stamp <= 0:
            return None
        return time.monotonic() - stamp

    def snapshot(self, *, ws_connected: bool) -> ConnectionHealth:
        ticker_age = self._age(self.last_ticker_mono)
        candle_age = self._age(self.last_candle_mono)
        rest_age = self._age(self.last_rest_ok_mono)
        limit = float(self.cfg.stale_ws_sec)
        stale = False
        reason = "ok"
        if ticker_age is not None and ticker_age > limit:
            stale = True
            reason = "stale_ticker"
        if candle_age is not None and candle_age > max(limit, float(self.cfg.poll_sec) * 4):
            stale = True
            reason = "stale_candles"
        rest_ok = self._rest_failures < 3 and (
            rest_age is None or rest_age <= limit * 2
        )
        ws_ok = ws_connected
        score = 100
        if not rest_ok:
            score -= 40
        if stale:
            score -= 30
        if not ws_ok:
            score -= 15
        if self._rest_failures:
            score -= min(20, self._rest_failures * 5)
        score = max(0, min(100, score))
        if score <= 0:
            reason = "api_disconnect"
        return ConnectionHealth(score, rest_ok, ws_ok, ticker_age, candle_age, stale, reason)

    def is_fresh(self, *, ws_connected: bool) -> bool:
        snap = self.snapshot(ws_connected=ws_connected)
        return not snap.stale and snap.rest_ok

    def backoff_seconds(self, attempt: int, cap: float = 16.0) -> float:
        base = min(cap, 0.4 * (2 ** max(0, attempt)))
        return base + random.uniform(0, base * 0.3)
