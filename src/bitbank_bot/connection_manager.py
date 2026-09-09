"""REST + WebSocket health, stale-data detection, and a 0-100 health score."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from bitbank_bot.logging_setup import slog
from bitbank_bot.websocket_client import BitbankWebsocket


@dataclass
class ConnectionSnapshot:
    rest_ok: bool
    ws_ok: bool
    ws_stale: bool
    last_rest_success_at: float
    last_ws_message_at: float
    last_ticker_at: float
    last_candle_at: float
    rest_age_sec: float
    ws_age_sec: float
    ticker_age_sec: float
    candle_age_sec: float
    health_score: int
    state: str


class ConnectionManager:
    def __init__(self, *, stale_sec: float = 60.0, ws: BitbankWebsocket | None = None) -> None:
        self.stale_sec = stale_sec
        self.ws = ws
        self.last_rest_success_at = 0.0
        self.last_ticker_at = 0.0
        self.last_candle_at = 0.0
        self.rest_failures = 0
        self.reconnects = 0

    def attach_ws(self, ws: BitbankWebsocket | None) -> None:
        self.ws = ws

    def note_rest_ok(self) -> None:
        self.last_rest_success_at = time.monotonic()
        self.rest_failures = 0

    def note_rest_fail(self) -> None:
        self.rest_failures += 1

    def note_ticker(self) -> None:
        self.last_ticker_at = time.monotonic()

    def note_candle(self) -> None:
        self.last_candle_at = time.monotonic()

    def note_reconnect(self) -> None:
        self.reconnects += 1

    def _age(self, stamp: float, now: float) -> float:
        if stamp <= 0:
            return 1e9
        return now - stamp

    def snapshot(self) -> ConnectionSnapshot:
        now = time.monotonic()
        ws = self.ws
        ws_connected = bool(ws and ws.is_connected())
        ws_stale = bool(ws and ws.is_stale())
        last_ws = 0.0
        if ws is not None:
            last_ws = float(getattr(ws, "_last_event_mono", 0.0) or 0.0)
        rest_age = self._age(self.last_rest_success_at, now)
        ws_age = self._age(last_ws, now)
        ticker_age = self._age(self.last_ticker_at, now)
        candle_age = self._age(self.last_candle_at, now)
        rest_ok = rest_age <= self.stale_sec * 3 or self.last_rest_success_at > 0 and rest_age < 120
        score = 0
        if self.last_rest_success_at > 0 and rest_age < 60:
            score += 40
        elif self.last_rest_success_at > 0 and rest_age < 180:
            score += 20
        if ws_connected and not ws_stale:
            score += 30
        elif last_ws > 0 and ws_age < self.stale_sec * 2:
            score += 10
        if self.last_candle_at > 0 and candle_age < 120:
            score += 20
        elif self.last_candle_at > 0 and candle_age < 300:
            score += 10
        if self.last_ticker_at > 0 and ticker_age < 60:
            score += 10
        if rest_ok and ws_connected and not ws_stale:
            state = "rest_ws_ok"
        elif rest_ok:
            state = "rest_ok_ws_degraded"
        elif ws_connected:
            state = "ws_ok_rest_degraded"
        else:
            state = "degraded"
        return ConnectionSnapshot(
            rest_ok=rest_ok,
            ws_ok=ws_connected and not ws_stale,
            ws_stale=ws_stale,
            last_rest_success_at=self.last_rest_success_at,
            last_ws_message_at=last_ws,
            last_ticker_at=self.last_ticker_at,
            last_candle_at=self.last_candle_at,
            rest_age_sec=round(rest_age if rest_age < 1e8 else -1, 3),
            ws_age_sec=round(ws_age if ws_age < 1e8 else -1, 3),
            ticker_age_sec=round(ticker_age if ticker_age < 1e8 else -1, 3),
            candle_age_sec=round(candle_age if candle_age < 1e8 else -1, 3),
            health_score=score,
            state=state,
        )

    def log_heartbeat(self) -> ConnectionSnapshot:
        snap = self.snapshot()
        slog(
            "CONNECTION",
            "health",
            rest_ok=snap.rest_ok,
            ws_ok=snap.ws_ok,
            health_score=snap.health_score,
            connection_state=snap.state,
            rest_age=snap.rest_age_sec,
            ws_age=snap.ws_age_sec,
            candle_age=snap.candle_age_sec,
            ticker_age=snap.ticker_age_sec,
        )
        return snap
