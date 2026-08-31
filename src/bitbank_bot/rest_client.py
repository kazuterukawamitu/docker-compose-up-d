"""Bitbank REST client: public + private ACCESS-TIME-WINDOW auth."""

from __future__ import annotations

import hashlib
import hmac
import json
import random
import threading
import time
from collections import deque
from decimal import Decimal
from typing import Any, Literal
from urllib.parse import urlencode

import httpx

from bitbank_bot.logging_setup import slog
from bitbank_bot.money import D

JSON_SEPARATORS = (",", ":")
AUTH_ERROR_CODES = frozenset({20001, 20002, 20003, 20011})


class BitbankAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        code: int | None = None,
        http_status: int | None = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.body = body


def is_auth_error(exc: BitbankAPIError) -> bool:
    if exc.http_status in {401, 403}:
        return True
    if exc.code in AUTH_ERROR_CODES:
        return True
    msg = str(exc).lower()
    return "api key" in msg or "secret missing" in msg


def dump_json(obj: dict[str, Any]) -> str:
    return json.dumps(obj, separators=JSON_SEPARATORS, ensure_ascii=False)


def sign_access_time_window(
    secret: str,
    request_time: str,
    time_window: str,
    payload: str,
) -> str:
    message = f"{request_time}{time_window}{payload}"
    return hmac.new(
        secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def get_sign_payload(path: str, query: dict[str, Any] | None = None) -> str:
    if not path.startswith("/"):
        path = "/" + path
    payload = "/v1" + path
    if query:
        payload += "?" + urlencode(query, doseq=True)
    return payload


class RateLimiter:
    def __init__(self, query_rps: int = 10, update_rps: int = 6) -> None:
        self.query_rps = query_rps
        self.update_rps = update_rps
        self._q: deque[float] = deque()
        self._u: deque[float] = deque()
        self._lock = threading.Lock()

    def wait(self, kind: Literal["query", "update"]) -> None:
        limit = self.query_rps if kind == "query" else self.update_rps
        bucket = self._q if kind == "query" else self._u
        with self._lock:
            now = time.monotonic()
            while bucket and now - bucket[0] >= 1.0:
                bucket.popleft()
            if len(bucket) >= limit:
                sleep_for = 1.0 - (now - bucket[0]) + 0.02
                if sleep_for > 0:
                    time.sleep(sleep_for)
                now = time.monotonic()
                while bucket and now - bucket[0] >= 1.0:
                    bucket.popleft()
            bucket.append(time.monotonic())


def _backoff_seconds(attempt: int, cap: float = 16.0) -> float:
    base = min(cap, 0.4 * (2**attempt))
    return base + random.uniform(0, base * 0.3)


class RestClient:
    def __init__(
        self,
        public_url: str,
        private_url: str,
        api_key: str = "",
        api_secret: str = "",
        access_time_window_ms: int = 5000,
        timeout_sec: float = 15.0,
        max_retries: int = 5,
        query_rps: int = 10,
        update_rps: int = 6,
        http: httpx.Client | None = None,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.public_url = public_url.rstrip("/")
        self.private_url = private_url.rstrip("/")
        self.api_key = api_key
        self.api_secret = api_secret
        self.access_time_window_ms = access_time_window_ms
        self.max_retries = max_retries
        self._owns_http = http is None
        self.http = http or httpx.Client(timeout=timeout_sec)
        self.limiter = limiter or RateLimiter(query_rps, update_rps)

    def close(self) -> None:
        if self._owns_http:
            self.http.close()

    def __enter__(self) -> "RestClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _request(
        self,
        method: str,
        url: str,
        *,
        kind: Literal["query", "update"],
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        public: bool = False,
    ) -> Any:
        last_error: Exception | None = None
        attempts = max(1, self.max_retries)
        for attempt in range(attempts):
            self.limiter.wait(kind)
            try:
                response = self.http.request(
                    method, url, headers=headers, content=content
                )
            except httpx.HTTPError as exc:
                last_error = exc
                slog("ERROR", "http transport error", error=type(exc).__name__)
                if attempt + 1 >= attempts:
                    break
                time.sleep(_backoff_seconds(attempt))
                continue
            if response.status_code == 429:
                slog("ERROR", "HTTP 429 rate limited", attempt=attempt)
                if attempt + 1 >= attempts:
                    raise BitbankAPIError(
                        "rate limited", http_status=429, body=response.text
                    )
                time.sleep(_backoff_seconds(attempt))
                continue
            if response.status_code >= 500:
                slog("ERROR", "HTTP 5xx", status=response.status_code, attempt=attempt)
                if attempt + 1 >= attempts:
                    raise BitbankAPIError(
                        "server error",
                        http_status=response.status_code,
                        body=response.text,
                    )
                time.sleep(_backoff_seconds(attempt))
                continue
            if response.status_code >= 400:
                raise BitbankAPIError(
                    f"http {response.status_code}",
                    http_status=response.status_code,
                    body=response.text,
                )
            try:
                payload = response.json()
            except json.JSONDecodeError as exc:
                raise BitbankAPIError("invalid json", body=response.text) from exc
            if payload.get("success") != 1:
                data = payload.get("data") or {}
                code = data.get("code") if isinstance(data, dict) else None
                raise BitbankAPIError(
                    f"api success=0 code={code}",
                    code=code,
                    http_status=response.status_code,
                    body=payload,
                )
            stage = "PUBLIC_API" if public else "PRIVATE_API"
            slog(stage, f"{method} ok", url_path=url.split(".cc")[-1][:80])
            return payload.get("data")
        raise BitbankAPIError(f"request failed: {last_error}")

    def public_get(self, path: str) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        url = self.public_url + path
        return self._request("GET", url, kind="query", public=True)

    def get_ticker(self, pair: str) -> dict[str, Any]:
        data = self.public_get(f"/{pair}/ticker")
        slog("PUBLIC_API", "ticker", pair=pair, last=data.get("last"))
        return data

    def get_candlestick(self, pair: str, candle_type: str, date_key: str) -> list[list[Any]]:
        data = self.public_get(f"/{pair}/candlestick/{candle_type}/{date_key}")
        sticks = data.get("candlestick") or []
        if not sticks:
            return []
        return list(sticks[0].get("ohlcv") or [])

    def get_spot_status(self, pair: str | None = None) -> dict[str, Any] | None:
        url = self.private_url + "/spot/status"
        data = self._request("GET", url, kind="query", public=True)
        statuses = data.get("statuses") or []
        if pair is None:
            return data
        for row in statuses:
            if row.get("pair") == pair:
                return row
        return None

    def _private_headers(self, payload: str) -> dict[str, str]:
        if not self.api_key or not self.api_secret:
            raise BitbankAPIError("API key/secret missing")
        request_time = str(int(time.time() * 1000))
        window = str(self.access_time_window_ms)
        signature = sign_access_time_window(
            self.api_secret, request_time, window, payload
        )
        return {
            "Content-Type": "application/json",
            "ACCESS-KEY": self.api_key,
            "ACCESS-REQUEST-TIME": request_time,
            "ACCESS-TIME-WINDOW": window,
            "ACCESS-SIGNATURE": signature,
        }

    def private_get(self, path: str, query: dict[str, Any] | None = None) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        payload = get_sign_payload(path, query)
        qs = ""
        if query:
            qs = "?" + urlencode(query, doseq=True)
        url = self.private_url + path + qs
        headers = self._private_headers(payload)
        return self._request("GET", url, kind="query", headers=headers)

    def private_post(self, path: str, body: dict[str, Any], *, update: bool = True) -> Any:
        if not path.startswith("/"):
            path = "/" + path
        raw = dump_json(body)
        headers = self._private_headers(raw)
        url = self.private_url + path
        kind: Literal["query", "update"] = "update" if update else "query"
        return self._request(
            "POST",
            url,
            kind=kind,
            headers=headers,
            content=raw.encode("utf-8"),
        )

    def get_assets(self) -> dict[str, Any]:
        data = self.private_get("/user/assets")
        slog("ASSET", "assets fetched", count=len(data.get("assets") or []))
        return data

    def free_amount(self, asset: str) -> Decimal:
        data = self.get_assets()
        for row in data.get("assets") or []:
            if row.get("asset") == asset:
                return D(row.get("free_amount") or 0)
        return D(0)

    def create_order(
        self,
        pair: str,
        amount: str,
        side: str,
        order_type: str,
        price: str | None = None,
        post_only: bool | None = None,
        *,
        live_confirmed: bool = False,
    ) -> dict[str, Any]:
        if not live_confirmed:
            raise BitbankAPIError("refusing create_order without live_confirmed")
        body: dict[str, Any] = {
            "pair": pair,
            "amount": amount,
            "side": side,
            "type": order_type,
        }
        if price is not None:
            body["price"] = price
        if post_only is not None:
            body["post_only"] = post_only
        return self.private_post("/user/spot/order", body, update=True)

    def get_active_orders(self, pair: str) -> list[dict[str, Any]]:
        data = self.private_get("/user/spot/active_orders", {"pair": pair})
        return list(data.get("orders") or [])
