"""Async Bitbank REST client. Public GETs are always allowed; live orders are gated."""

from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

import aiohttp

from bitbank_bot.config import Settings
from bitbank_bot.exceptions import (
    AuthError,
    CircuitBreakerError,
    ExchangeError,
    OrderUncertainError,
    RateLimitError,
)
from bitbank_bot.exchange.auth import compact_json, private_headers_get, private_headers_post
from bitbank_bot.models import Balance, Candle, OrderBook, OrderType, Side, Ticker

log = logging.getLogger("bitbank_bot.exchange")

_RETRY_STATUSES = {429, 500, 502, 503, 504}


class BitbankRest:
    def __init__(self, settings: Settings, session: aiohttp.ClientSession | None = None) -> None:
        self._settings = settings
        self._session = session
        self._owns_session = session is None

    async def __aenter__(self) -> BitbankRest:
        if self._session is None:
            timeout = aiohttp.ClientTimeout(total=20, connect=8)
            self._session = aiohttp.ClientSession(timeout=timeout)
            self._owns_session = True
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_session and self._session is not None:
            await self._session.close()
            self._session = None

    @property
    def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            raise ExchangeError("HTTP session is not open")
        return self._session

    async def get_ticker(self, pair: str | None = None) -> Ticker:
        pair = pair or self._settings.pair
        data = await self._public_get(f"/{pair}/ticker")
        return Ticker(
            pair=pair,
            last=_d(data["last"]),
            bid=_d(data["buy"]),
            ask=_d(data["sell"]),
            high=_d(data["high"]),
            low=_d(data["low"]),
            volume=_d(data["vol"]),
            timestamp_ms=int(data["timestamp"]),
        )

    async def get_depth(self, pair: str | None = None) -> OrderBook:
        pair = pair or self._settings.pair
        data = await self._public_get(f"/{pair}/depth")
        bids = tuple((_d(p), _d(q)) for p, q in data["bids"])
        asks = tuple((_d(p), _d(q)) for p, q in data["asks"])
        return OrderBook(bids=bids, asks=asks, timestamp_ms=int(data["timestamp"]))

    async def get_candles(
        self,
        pair: str | None = None,
        candle_type: str | None = None,
        yyyymmdd_or_yyyy: str | None = None,
    ) -> list[Candle]:
        pair = pair or self._settings.pair
        candle_type = candle_type or self._settings.candle_type
        if yyyymmdd_or_yyyy is None:
            yyyymmdd_or_yyyy = _candle_path_date(candle_type)
        data = await self._public_get(f"/{pair}/candlestick/{candle_type}/{yyyymmdd_or_yyyy}")
        series = data.get("candlestick") or []
        candles: list[Candle] = []
        for block in series:
            for row in block.get("ohlcv") or []:
                candles.append(
                    Candle(
                        timestamp_ms=int(row[5]),
                        open=_d(row[0]),
                        high=_d(row[1]),
                        low=_d(row[2]),
                        close=_d(row[3]),
                        volume=_d(row[4]),
                    )
                )
        candles.sort(key=lambda c: c.timestamp_ms)
        return candles

    async def get_circuit_break(self, pair: str | None = None) -> dict[str, Any]:
        pair = pair or self._settings.pair
        return await self._public_get(f"/{pair}/circuit_break_info")

    async def assert_spot_open(self) -> None:
        info = await self.get_circuit_break()
        mode = str(info.get("mode") or "NONE")
        if mode != "NONE":
            raise CircuitBreakerError(f"circuit_break mode={mode}")

    async def get_assets(self) -> list[Balance]:
        data = await self._private_get("/v1/user/assets")
        out: list[Balance] = []
        for row in data.get("assets") or []:
            out.append(
                Balance(
                    asset=str(row["asset"]),
                    free=_d(row["free_amount"]),
                    locked=_d(row["locked_amount"]),
                    onhand=_d(row["onhand_amount"]),
                )
            )
        return out

    async def get_balances(self) -> tuple[Balance, Balance]:
        assets = await self.get_assets()
        jpy = next((a for a in assets if a.asset == "jpy"), None)
        btc = next((a for a in assets if a.asset == "btc"), None)
        if jpy is None or btc is None:
            raise ExchangeError("JPY or BTC asset missing from /user/assets")
        return jpy, btc

    async def get_order(self, order_id: int, pair: str | None = None) -> dict[str, Any]:
        pair = pair or self._settings.pair
        return await self._private_get(
            "/v1/user/spot/order",
            {"pair": pair, "order_id": str(order_id)},
        )

    async def get_active_orders(self, pair: str | None = None) -> list[dict[str, Any]]:
        pair = pair or self._settings.pair
        data = await self._private_get("/v1/user/spot/active_orders", {"pair": pair})
        return list(data.get("orders") or [])

    async def create_order(
        self,
        *,
        side: Side,
        amount: Decimal,
        order_type: OrderType,
        price: Decimal | None = None,
        pair: str | None = None,
    ) -> dict[str, Any]:
        if self._settings.dry_run:
            raise ExchangeError("create_order blocked: DRY_RUN=true")
        pair = pair or self._settings.pair
        body: dict[str, Any] = {
            "pair": pair,
            "amount": _amount_str(amount),
            "side": side.value,
            "type": order_type.value,
        }
        if order_type is OrderType.LIMIT:
            if price is None:
                raise ExchangeError("limit orders require a price")
            body["price"] = str(int(price))
        return await self._private_post("/v1/user/spot/order", body, is_order=True)

    async def cancel_order(self, order_id: int, pair: str | None = None) -> dict[str, Any]:
        if self._settings.dry_run:
            raise ExchangeError("cancel_order blocked: DRY_RUN=true")
        pair = pair or self._settings.pair
        return await self._private_post(
            "/v1/user/spot/cancel_order",
            {"pair": pair, "order_id": order_id},
            is_order=True,
        )

    async def _public_get(self, path: str) -> dict[str, Any]:
        url = f"{self._settings.public_rest}{path}"
        payload = await self._request("GET", url, retry=True)
        return _unwrap(payload)

    async def _private_get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        query = f"?{urlencode(params)}" if params else ""
        path_with_query = f"{path}{query}"
        url = f"{self._settings.private_rest}{path_with_query}"
        headers = private_headers_get(self._settings.api_key, self._settings.api_secret, path_with_query)
        payload = await self._request("GET", url, headers=headers, retry=True)
        return _unwrap(payload)

    async def _private_post(self, path: str, body: dict[str, Any], *, is_order: bool) -> dict[str, Any]:
        url = f"{self._settings.private_rest}{path}"
        raw = compact_json(body)
        headers = private_headers_post(self._settings.api_key, self._settings.api_secret, raw)
        payload = await self._request(
            "POST",
            url,
            headers=headers,
            data=raw,
            retry=not is_order,
            uncertain_on_timeout=is_order,
        )
        return _unwrap(payload)

    async def _request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        data: str | None = None,
        retry: bool = False,
        uncertain_on_timeout: bool = False,
        attempts: int = 4,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                async with self.session.request(method, url, headers=headers, data=data) as resp:
                    if resp.status == 401:
                        raise AuthError("Bitbank rejected authentication")
                    text = await resp.text()
                    if resp.status == 429:
                        last_error = RateLimitError("HTTP 429")
                        if retry and attempt < attempts:
                            await asyncio.sleep(_backoff(attempt))
                            continue
                        raise last_error
                    if resp.status >= 500:
                        last_error = ExchangeError(f"HTTP {resp.status}")
                        if retry and attempt < attempts:
                            await asyncio.sleep(_backoff(attempt))
                            continue
                        raise last_error
                    if resp.status >= 400:
                        raise ExchangeError(f"HTTP {resp.status}: {text[:300]}")
                    try:
                        return await resp.json(content_type=None)
                    except Exception as exc:
                        raise ExchangeError(f"invalid JSON from {url}") from exc
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if uncertain_on_timeout:
                    raise OrderUncertainError("order POST timed out; not retrying") from exc
                last_error = ExchangeError(str(exc))
                if retry and attempt < attempts:
                    log.warning("network error %s (attempt %s/%s)", exc, attempt, attempts)
                    await asyncio.sleep(_backoff(attempt))
                    continue
                raise ExchangeError(str(exc)) from exc
        raise last_error or ExchangeError("request failed")


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    if int(payload.get("success", 0)) != 1:
        code = (payload.get("data") or {}).get("code")
        raise ExchangeError(f"bitbank success=0 code={code}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ExchangeError("bitbank payload missing data object")
    return data


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _amount_str(amount: Decimal) -> str:
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def _backoff(attempt: int) -> float:
    return min(8.0, 0.5 * (2 ** (attempt - 1)))


def _candle_path_date(candle_type: str) -> str:
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    if candle_type in {"1min", "5min", "15min", "30min"}:
        return now.strftime("%Y%m%d")
    return now.strftime("%Y")
