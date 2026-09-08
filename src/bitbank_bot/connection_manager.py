"""REST + WebSocket health, stale-data detection, and a 0–100 health score."""

from __future__ import annotations

import time
from dataclasses import dataclass

from bitbank_bot.config import Config
from bitbank_bot.logging_setup import slog
from bitbank_bot.websocket_client import BitbankWebsocket


@dataclass
class ConnectionHealth:
    rest_ok: bool
    ws_ok: bool
    health_score: int
    connection_state: str
    ticker_age_sec: float
    rest_age_sec: float
    candle_age_sec: float
    loop_age_sec: float
    stale: bool


class ConnectionManager:
    def __init__(self, cfg: Config, ws: BitbankWebsocket | None = None) -> None:
        self.cfg = cfg
        self.ws = ws
        now = time.monotonic()
        self.last_rest_ok_at = 0.0
        self.last_rest_fail_at = 0.0
        self.last_ws_message_at = 0.0
        self.last_ticker_at = 0.0
        self.last_candle_at = 0.0
        self.last_loop_at = now
        self.last_strategy_at = 0.0
        self.last_order_check_at = 0.0
        self.last_balance_sync_at = 0.0
        self._rest_fail_streak = 0

    def attach_ws(self, ws: BitbankWebsocket | None) -> None:
        self.ws = ws

    def note_rest_ok(self) -> None:
        self.last_rest_ok_at = time.monotonic()
        self._rest_fail_streak = 0

    def note_rest_fail(self) -> None:
        self.last_rest_fail_at = time.monotonic()
        self._rest_fail_streak += 1

    def note_candle(self) -> None:
        self.last_candle_at = time.monotonic()

    def note_loop(self) -> None:
        self.last_loop_at = time.monotonic()

    def note_strategy(self) -> None:
        self.last_strategy_at = time.monotonic()

    def note_order_check(self) -> None:
        self.last_order_check_at = time.monotonic()

    def note_balance(self) -> None:
        self.last_balance_sync_at = time.monotonic()

    def _age(self, stamp: float, now: float) -> float:
        if stamp <= 0:
            return 1e9
        return now - stamp

    def snapshot(self) -> ConnectionHealth:
        now = time.monotonic()
        ws = self.ws
        ws_connected = bool(ws and ws.is_connected())
        ticker_age = self._age(ws.last_ticker_mono if ws else 0.0, now) if ws else 1e9
        if ws and ws.last_ticker_mono > 0:
            self.last_ticker_at = ws.last_ticker_mono
            self.last_ws_message_at = max(self.last_ws_message_at, ws.last_message_mono)
        rest_ok = self.last_rest_ok_at > 0 and self._age(self.last_rest_ok_at, now) < max(
            30.0, self.cfg.stale_ws_sec * 2
        )
        if self.last_rest_ok_at > 0 and self.last_rest_fail_at > self.last_rest_ok_at:
            rest_ok = False
        candle_age = self._age(self.last_candle_at, now)
        loop_age = self._age(self.last_loop_at, now)
        stale = False
        if ws is not None and self.cfg.enable_websocket and ws.is_stale():
            stale = True
        score = 100
        if not rest_ok:
            score -= 40
        if self.cfg.enable_websocket and not ws_connected:
            score -= 20
        if stale:
            score -= 25
        if candle_age > max(120.0, self.cfg.poll_sec * 8):
            score -= 15
        score = max(0, min(100, score))
        if rest_ok and ws_connected and not stale:
            state = "rest_ws_ok"
        elif rest_ok:
            state = "rest_only"
        elif ws_connected:
            state = "ws_only"
        else:
            state = "disconnected"
        return ConnectionHealth(
            rest_ok=rest_ok,
            ws_ok=ws_connected,
            health_score=score,
            connection_state=state,
            ticker_age_sec=ticker_age if ticker_age < 1e8 else -1.0,
            rest_age_sec=self._age(self.last_rest_ok_at, now) if self.last_rest_ok_at else -1.0,
            candle_age_sec=candle_age if self.last_candle_at else -1.0,
            loop_age_sec=loop_age,
            stale=stale,
        )

    def allow_orders(self) -> tuple[bool, str]:
        health = self.snapshot()
        if health.stale:
            return False, "stale_websocket"
        if not health.rest_ok and self.last_rest_ok_at > 0:
            return False, "api_unhealthy"
        return True, "ok"

    def slog_heartbeat(self) -> ConnectionHealth:
        health = self.snapshot()
        slog(
            "HEARTBEAT",
            "connection",
            connection_state=health.connection_state,
            health_score=health.health_score,
            rest_ok=health.rest_ok,
            ws_ok=health.ws_ok,
            ticker_age=round(health.ticker_age_sec, 2),
            candle_age=round(health.candle_age_sec, 2),
            loop_age=round(health.loop_age_sec, 2),
        )
        slog("HEARTBEAT", "WebSocket CONNECTED" if health.ws_ok else "WebSocket DISCONNECTED")
        slog("HEARTBEAT", "REST API OK" if health.rest_ok else "REST API DEGRADED")
        return health
