"""REST + WebSocket health, stale-data detection, and reconnect hooks."""

from __future__ import annotations

import time
from dataclasses import dataclass

from bitbank_bot.logging_setup import slog
from bitbank_bot.websocket_client import BitbankWebsocket


@dataclass
class ConnectionSnapshot:
    rest_ok: bool
    ws_ok: bool
    rest_age_sec: float | None
    ws_age_sec: float | None
    health_score: int
    connection_state: str
    stale: bool


class ConnectionManager:
    def __init__(self, stale_sec: float = 60.0) -> None:
        self.stale_sec = stale_sec
        self._last_rest_ok = 0.0
        self._last_rest_fail = 0.0
        self._last_ws_event = 0.0
        self._rest_fail_streak = 0
        self._ws: BitbankWebsocket | None = None

    def attach_ws(self, ws: BitbankWebsocket | None) -> None:
        self._ws = ws

    def note_rest_ok(self) -> None:
        self._last_rest_ok = time.monotonic()
        self._rest_fail_streak = 0

    def note_rest_fail(self) -> None:
        self._last_rest_fail = time.monotonic()
        self._rest_fail_streak += 1

    def note_ws_event(self) -> None:
        self._last_ws_event = time.monotonic()

    def snapshot(self) -> ConnectionSnapshot:
        now = time.monotonic()
        rest_age = (now - self._last_rest_ok) if self._last_rest_ok else None
        ws_connected = bool(self._ws and self._ws.is_connected())
        ws_stale = bool(self._ws and self._ws.is_stale())
        if self._ws and self._ws.last_ticker:
            self._last_ws_event = max(self._last_ws_event, getattr(self._ws, "_last_event_mono", 0.0))
        ws_age = (now - self._last_ws_event) if self._last_ws_event else None
        rest_ok = rest_age is not None and rest_age <= self.stale_sec
        ws_ok = ws_connected and not ws_stale
        score = 0
        if rest_ok:
            score += 60
        elif self._last_rest_ok:
            score += 20
        if ws_ok:
            score += 40
        elif self._ws is not None and not ws_stale:
            score += 10
        if rest_ok and ws_ok:
            state = "rest_ws_ok"
        elif rest_ok:
            state = "rest_only"
        elif ws_ok:
            state = "ws_only"
        else:
            state = "disconnected"
        stale = (not rest_ok) and (ws_stale or self._ws is None)
        return ConnectionSnapshot(rest_ok, ws_ok, rest_age, ws_age, score, state, stale)

    def recover_websocket(self) -> None:
        ws = self._ws
        if ws is None:
            return
        try:
            ws.stop()
        except Exception as exc:
            slog("WEBSOCKET", "stop during recover failed", error=type(exc).__name__)
        try:
            ws.start()
            slog("WEBSOCKET", "reconnect requested by ConnectionManager")
        except Exception as exc:
            slog("WEBSOCKET", "reconnect failed", error=type(exc).__name__)
