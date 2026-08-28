"""Optional Socket.IO ticker stream with exponential reconnect."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from decimal import Decimal

import websockets

from bitbank_bot.config import Settings
from bitbank_bot.models import Ticker

log = logging.getLogger("bitbank_bot.ws")

TickerHandler = Callable[[Ticker], Awaitable[None]]


class TickerStream:
    def __init__(self, settings: Settings, on_ticker: TickerHandler) -> None:
        self._settings = settings
        self._on_ticker = on_ticker
        self._stop = asyncio.Event()

    def stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        delay = 1.0
        while not self._stop.is_set():
            try:
                await self._connect_once()
                delay = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("websocket disconnected: %s; retry in %.1fs", exc, delay)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=delay)
                except TimeoutError:
                    pass
                delay = min(30.0, delay * 2)

    async def _connect_once(self) -> None:
        pair = self._settings.pair
        async with websockets.connect(self._settings.ws_url, ping_interval=20, ping_timeout=20) as ws:
            log.info("websocket connected")
            while not self._stop.is_set():
                raw = await asyncio.wait_for(ws.recv(), timeout=60)
                if not isinstance(raw, str):
                    continue
                if raw.startswith("0"):
                    await ws.send("40")
                    continue
                if raw.startswith("40"):
                    await ws.send(f'42["join-room","ticker_{pair}"]')
                    continue
                if raw.startswith("2"):
                    await ws.send("3")
                    continue
                if raw.startswith("42"):
                    ticker = parse_ticker_event(raw, pair)
                    if ticker is not None:
                        await self._on_ticker(ticker)


def parse_ticker_event(raw: str, pair: str) -> Ticker | None:
    try:
        payload = json.loads(raw[2:])
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list) or len(payload) < 2:
        return None
    body = payload[1]
    if not isinstance(body, dict):
        return None
    message = body.get("message") or body
    if not isinstance(message, dict):
        return None
    try:
        last = Decimal(str(message["last"]))
        return Ticker(
            pair=pair,
            last=last,
            bid=Decimal(str(message.get("buy") or message.get("bid") or last)),
            ask=Decimal(str(message.get("sell") or message.get("ask") or last)),
            high=Decimal(str(message.get("high") or last)),
            low=Decimal(str(message.get("low") or last)),
            volume=Decimal(str(message.get("vol") or "0")),
            timestamp_ms=int(message.get("timestamp") or 0),
        )
    except (KeyError, ValueError, TypeError):
        return None
