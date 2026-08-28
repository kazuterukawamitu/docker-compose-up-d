from __future__ import annotations

import asyncio
import json
import logging
import random
import time

import websockets

from bitbank_bot.config import Settings
from bitbank_bot.decimal_utils import d
from bitbank_bot.market.cache import MarketCache
from bitbank_bot.models import Ticker

log = logging.getLogger(__name__)


class BitbankPublicWS:
    def __init__(self, settings: Settings, cache: MarketCache) -> None:
        self.settings = settings
        self.cache = cache
        self._stop = asyncio.Event()
        self._backoff = 1.0

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        rooms = [
            f"ticker_{self.settings.pair}",
            f"circuit_break_info_{self.settings.pair}",
        ]
        while not self._stop.is_set():
            try:
                await self._session(rooms)
                self._backoff = 1.0
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("websocket session failed")
                self.cache.ws_connected = False
                delay = min(60.0, self._backoff) + random.random()
                self._backoff = min(60.0, self._backoff * 2)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except TimeoutError:
                    pass

    async def _session(self, rooms: list[str]) -> None:
        async with websockets.connect(self.settings.ws_url, ping_interval=None, close_timeout=5) as ws:
            hello = await ws.recv()
            if not str(hello).startswith("0"):
                raise RuntimeError(f"unexpected engine.io open: {hello!r}")
            await ws.send("40")
            ack = await ws.recv()
            if not str(ack).startswith("40"):
                raise RuntimeError(f"unexpected socket.io ack: {ack!r}")
            for room in rooms:
                await ws.send(f'42["join-room","{room}"]')
            self.cache.ws_connected = True
            log.info("websocket joined rooms %s", rooms)
            while not self._stop.is_set():
                raw = await asyncio.wait_for(ws.recv(), timeout=90)
                text = str(raw)
                if text == "2":
                    await ws.send("3")
                    continue
                if text.startswith("42"):
                    self._handle_event(text[2:])

    def _handle_event(self, payload: str) -> None:
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            log.warning("invalid websocket json")
            return
        if not isinstance(parsed, list) or len(parsed) < 2:
            return
        body = parsed[1]
        if not isinstance(body, dict):
            return
        room = str(body.get("room_name") or "")
        message = body.get("message") or {}
        data = message.get("data") if isinstance(message, dict) else None
        if data is None and isinstance(message, dict) and "last" in message:
            data = message
        if not isinstance(data, dict):
            return
        if room.startswith("ticker_"):
            self.cache.upsert_ticker(
                Ticker(
                    last=d(data["last"]),
                    buy=d(data["buy"]),
                    sell=d(data["sell"]),
                    timestamp_ms=int(data.get("timestamp") or time.time() * 1000),
                    high=d(data["high"]) if data.get("high") is not None else None,
                    low=d(data["low"]) if data.get("low") is not None else None,
                    volume=d(data["vol"]) if data.get("vol") is not None else None,
                ),
                source="ws",
            )
        elif room.startswith("circuit_break_info_"):
            self.cache.circuit_mode = str(data.get("mode") or "NONE")
