"""Bitbank public stream. Failures never crash the REST trading loop."""

from __future__ import annotations

import json
import logging
import random
import threading
import time
from typing import Any, Callable

from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D

OnMessage = Callable[[str, dict[str, Any]], None]


class BitbankWebsocket:
    def __init__(
        self,
        url: str,
        rooms: tuple[str, ...],
        stale_sec: float = 30.0,
        on_message: OnMessage | None = None,
    ) -> None:
        self.url = url
        self.rooms = rooms
        self.stale_sec = stale_sec
        self.on_message = on_message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._last_event_mono = 0.0
        self._connected = False
        self.last_ticker: dict[str, Any] | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        try:
            import websockets  # noqa: F401
        except ImportError:
            slog("WEBSOCKET", "websockets not installed; REST only")
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_forever, name="bitbank-ws", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def is_stale(self) -> bool:
        """True only after we have received data that then went cold.

        Never-connected is not stale: REST candles remain authoritative so
        the DRY_RUN loop does not skip every order at startup.
        """
        if self._last_event_mono <= 0:
            return False
        return (time.monotonic() - self._last_event_mono) > self.stale_sec

    def is_connected(self) -> bool:
        return self._connected and not self.is_stale()

    def last_price(self) -> Any:
        if not self.last_ticker:
            return None
        try:
            value = D(self.last_ticker.get("last") or 0)
        except Exception:
            slog("WEBSOCKET", "bad ticker last; ignoring")
            return None
        return value or None

    def _run_forever(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                self._session()
                attempt = 0
            except Exception as exc:
                self._connected = False
                slog(
                    "WEBSOCKET",
                    "disconnected",
                    level=logging.ERROR,
                    error=type(exc).__name__,
                )
                delay = min(60.0, 1.0 * (2**attempt)) + random.uniform(0, 0.5)
                attempt = min(attempt + 1, 8)
                slog("WEBSOCKET", "reconnect scheduled", delay=round(delay, 2))
                self._stop.wait(delay)

    def _session(self) -> None:
        from websockets.sync.client import connect

        slog("WEBSOCKET", "connecting", url=self.url.split("?")[0])
        with connect(self.url, open_timeout=15, close_timeout=5) as ws:
            ping_interval = 25.0
            opened = time.monotonic()
            while not self._stop.is_set():
                timeout = max(1.0, ping_interval)
                try:
                    raw = ws.recv(timeout=timeout)
                except TimeoutError:
                    if time.monotonic() - opened > ping_interval * 4:
                        raise RuntimeError("websocket recv timeout")
                    continue
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8")
                if not raw:
                    continue
                if raw.startswith("0"):
                    info = json.loads(raw[1:])
                    ping_interval = float(info.get("pingInterval", 25000)) / 1000.0
                    ws.send("40")
                    slog("WEBSOCKET", "engine.io open", ping_interval=ping_interval)
                    continue
                if raw == "2":
                    ws.send("3")
                    continue
                if raw.startswith("40"):
                    self._connected = True
                    for room in self.rooms:
                        ws.send(f'42["join-room","{room}"]')
                    slog("WEBSOCKET", "joined rooms", rooms=",".join(self.rooms))
                    continue
                if raw.startswith("42"):
                    self._handle_42(raw[2:])

    def _handle_42(self, payload: str) -> None:
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            slog("WEBSOCKET", "json decode failed")
            return
        if not isinstance(data, list) or len(data) < 2:
            return
        body = data[1]
        if not isinstance(body, dict):
            return
        room = str(body.get("room_name") or "")
        message = body.get("message") or {}
        inner = message.get("data") if isinstance(message, dict) else body.get("data")
        if not isinstance(inner, dict):
            inner = {}
        with self._lock:
            self._last_event_mono = time.monotonic()
            if room.startswith("ticker_"):
                self.last_ticker = inner
        if self.on_message:
            self.on_message(room, inner)
