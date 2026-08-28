from __future__ import annotations

import asyncio
import logging
import time
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import aiohttp

from bitbank_bot.config import Settings
from bitbank_bot.decimal_utils import d
from bitbank_bot.exceptions import AuthError, ExchangeError, RateLimitError
from bitbank_bot.exchange.rate_limiter import TokenBucket
from bitbank_bot.exchange.signing import compact_json, sign_get, sign_post
from bitbank_bot.market.candles import candle_date_keys, merge_candles, parse_ohlcv_row
from bitbank_bot.models import AssetBalance, Candle, OrderRecord, Ticker

log = logging.getLogger(__name__)


class BitbankRest:
    def __init__(self, settings: Settings, session: aiohttp.ClientSession | None = None) -> None:
        self.settings = settings
        self._session = session
        self._own_session = session is None
        self._query = TokenBucket(settings.query_rps)
        self._update = TokenBucket(settings.update_rps)
        self._nonce = int(time.time() * 1000)

    async def __aenter__(self) -> BitbankRest:
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=15)
            self._session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._own_session and self._session is not None:
            await self._session.close()
            self._session = None

    def _next_nonce(self) -> str:
        now = int(time.time() * 1000)
        if now <= self._nonce:
            self._nonce += 1
        else:
            self._nonce = now
        return str(self._nonce)

    async def public_get(self, path: str) -> Any:
        await self._query.acquire()
        url = f"{self.settings.public_base}{path}"
        return await self._request("GET", url, headers={"Accept": "application/json"})

    async def private_get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        if not self.settings.api_key or not self.settings.api_secret:
            raise AuthError("private GET requires API key and secret")
        await self._query.acquire()
        query = f"?{urlencode(params)}" if params else ""
        full_path = f"/v1{path}{query}"
        nonce = self._next_nonce()
        headers = {
            "ACCESS-KEY": self.settings.api_key,
            "ACCESS-NONCE": nonce,
            "ACCESS-SIGNATURE": sign_get(self.settings.api_secret, nonce, full_path),
            "Accept": "application/json",
        }
        url = f"{self.settings.private_base}{full_path}"
        return await self._request("GET", url, headers=headers)

    async def private_post(self, path: str, body: dict[str, Any]) -> Any:
        if not self.settings.api_key or not self.settings.api_secret:
            raise AuthError("private POST requires API key and secret")
        await self._update.acquire()
        payload = compact_json(body)
        nonce = self._next_nonce()
        headers = {
            "ACCESS-KEY": self.settings.api_key,
            "ACCESS-NONCE": nonce,
            "ACCESS-SIGNATURE": sign_post(self.settings.api_secret, nonce, payload),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        url = f"{self.settings.private_base}/v1{path}"
        return await self._request("POST", url, headers=headers, data=payload)

    async def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        data: str | None = None,
        retries: int = 3,
    ) -> Any:
        if self._session is None:
            raise RuntimeError("HTTP session is not open")
        last_error: Exception | None = None
        for attempt in range(retries):
            try:
                async with self._session.request(method, url, headers=headers, data=data) as resp:
                    raw = await resp.text()
                    if resp.status == 429:
                        wait = float(resp.headers.get("Retry-After", 1 + attempt))
                        log.warning("HTTP 429 on %s, sleeping %.1fs", url.split("?")[0], wait)
                        await asyncio.sleep(wait)
                        last_error = RateLimitError("HTTP 429", status=429)
                        continue
                    try:
                        payload = json_loads(raw)
                    except ValueError as exc:
                        raise ExchangeError(f"non-JSON response HTTP {resp.status}", status=resp.status) from exc
                    if resp.status in {401, 403}:
                        raise AuthError(f"auth failed HTTP {resp.status}", status=resp.status)
                    if not isinstance(payload, dict):
                        raise ExchangeError("unexpected payload", status=resp.status)
                    if payload.get("success") != 1:
                        code = None
                        data_obj = payload.get("data") or {}
                        if isinstance(data_obj, dict):
                            code = data_obj.get("code")
                        raise ExchangeError(f"bitbank error code={code}", code=code, status=resp.status)
                    return payload.get("data")
            except (TimeoutError, aiohttp.ClientError) as exc:
                last_error = ExchangeError(str(exc))
                log.warning("network error %s %s: %s", method, url.split("?")[0], exc)
                await asyncio.sleep(0.5 * (2**attempt))
        assert last_error is not None
        raise last_error

    async def fetch_ticker(self, pair: str) -> Ticker:
        data = await self.public_get(f"/{pair}/ticker")
        return Ticker(
            last=d(data["last"]),
            buy=d(data["buy"]),
            sell=d(data["sell"]),
            timestamp_ms=int(data["timestamp"]),
            high=d(data["high"]) if data.get("high") is not None else None,
            low=d(data["low"]) if data.get("low") is not None else None,
            volume=d(data["vol"]) if data.get("vol") is not None else None,
        )

    async def fetch_circuit_break(self, pair: str) -> str:
        data = await self.public_get(f"/{pair}/circuit_break_info")
        return str(data.get("mode") or "NONE")

    async def fetch_candles(self, pair: str, candle_type: str, min_bars: int) -> list[Candle]:
        days = 3
        collected: list[Candle] = []
        while True:
            keys = candle_date_keys(candle_type, days_back=days)
            groups: list[list[Candle]] = []
            for key in keys:
                path = f"/{pair}/candlestick/{candle_type}/{key}"
                try:
                    data = await self.public_get(path)
                except ExchangeError as exc:
                    log.info("no candles for %s (%s)", path, exc)
                    continue
                for stick in data.get("candlestick") or []:
                    rows = stick.get("ohlcv") or []
                    groups.append([parse_ohlcv_row(row) for row in rows])
            collected = merge_candles(*groups)
            if len(collected) >= min_bars or days >= 40:
                break
            days *= 2
        return collected[-max(min_bars, 1) :] if collected else collected

    async def fetch_assets(self) -> dict[str, AssetBalance]:
        data = await self.private_get("/user/assets")
        out: dict[str, AssetBalance] = {}
        for item in data.get("assets") or []:
            asset = str(item["asset"])
            out[asset] = AssetBalance(
                asset=asset,
                free=d(item.get("free_amount", "0")),
                onhand=d(item.get("onhand_amount", "0")),
                locked=d(item.get("locked_amount", "0")),
            )
        return out

    async def create_order(
        self,
        pair: str,
        side: str,
        order_type: str,
        amount: Decimal,
        price: Decimal | None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "pair": pair,
            "side": side,
            "type": order_type,
            "amount": format(amount, "f"),
        }
        if order_type == "limit":
            if price is None:
                raise ValueError("limit order requires price")
            body["price"] = format(price, "f")
        return await self.private_post("/user/spot/order", body)

    async def get_order(self, pair: str, order_id: int) -> dict[str, Any]:
        return await self.private_get("/user/spot/order", {"pair": pair, "order_id": order_id})

    async def cancel_order(self, pair: str, order_id: int) -> dict[str, Any]:
        return await self.private_post("/user/spot/cancel_order", {"pair": pair, "order_id": order_id})

    async def active_orders(self, pair: str) -> list[dict[str, Any]]:
        data = await self.private_get("/user/spot/active_orders", {"pair": pair})
        return list(data.get("orders") or [])


def json_loads(raw: str) -> Any:
    import json

    return json.loads(raw)


def order_from_exchange(payload: dict[str, Any], *, dry_run: bool, reason: str, target: Decimal, planned: Decimal) -> OrderRecord:
    executed = d(payload.get("executed_amount") or "0")
    remaining = payload.get("remaining_amount")
    avg = payload.get("average_price")
    price = payload.get("price")
    return OrderRecord(
        client_tag=str(payload.get("order_id") or "unknown"),
        order_id=int(payload["order_id"]) if payload.get("order_id") is not None else None,
        side=payload.get("side") or "buy",
        order_type=payload.get("type") or "",
        target_amount=target,
        planned_amount=planned,
        actual_amount=executed,
        price=d(price) if price not in (None, "") else None,
        average_price=d(avg) if avg not in (None, "") else None,
        status=str(payload.get("status") or "UNKNOWN"),
        dry_run=dry_run,
        reason=reason,
        executed_amount=executed,
        remaining_amount=d(remaining) if remaining not in (None, "") else None,
    )
