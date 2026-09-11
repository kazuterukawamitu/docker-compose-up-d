from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import httpx
import pytest

from bitbank_bot.rest_client import BitbankAPIError, RateLimiter, RestClient, coerce_active_orders


def test_create_order_does_not_retry_post() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("boom", request=request)

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = RestClient(
        "https://public.example",
        "https://private.example",
        "k",
        "s",
        max_retries=5,
        http=http,
    )
    try:
        with pytest.raises(BitbankAPIError):
            client.create_order(
                "btc_jpy",
                "0.001",
                "buy",
                "limit",
                "1000000",
                live_confirmed=True,
            )
        assert calls["n"] == 1
    finally:
        client.close()


def test_coerce_active_orders_empty_and_unknown() -> None:
    assert coerce_active_orders(None) == []
    assert coerce_active_orders([]) == []
    assert coerce_active_orders({}) == []
    assert coerce_active_orders({"orders": []}) == []
    assert coerce_active_orders({"orders": None}) == []
    mapped = coerce_active_orders({"9": {"order_id": "9"}})
    assert mapped == [{"order_id": "9"}]
    with pytest.raises(BitbankAPIError, match="active_orders_unreadable"):
        coerce_active_orders("nope")
    with pytest.raises(BitbankAPIError, match="active_orders_unreadable"):
        coerce_active_orders(["not-a-dict"])


def test_get_ticker_rejects_non_object_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": 1, "data": None})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = RestClient(
        "https://public.example",
        "https://private.example",
        http=http,
    )
    try:
        with pytest.raises(BitbankAPIError, match="ticker_unreadable"):
            client.get_ticker("btc_jpy")
    finally:
        client.close()


def test_get_active_orders_normalizes_empty_dict() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"success": 1, "data": {"orders": {}}})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = RestClient(
        "https://public.example",
        "https://private.example",
        "k",
        "s",
        http=http,
    )
    try:
        assert client.get_active_orders("btc_jpy") == []
    finally:
        client.close()


def test_rate_limiter_query_sleep_does_not_block_update() -> None:
    limiter = RateLimiter(query_rps=1, update_rps=10)
    limiter.wait("query")
    started = time.monotonic()
    waiter = threading.Thread(target=lambda: limiter.wait("query"))
    waiter.start()
    time.sleep(0.05)
    limiter.wait("update")
    update_elapsed = time.monotonic() - started
    waiter.join(timeout=5)
    assert waiter.is_alive() is False
    assert update_elapsed < 0.5

