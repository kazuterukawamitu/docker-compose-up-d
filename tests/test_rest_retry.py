from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from bitbank_bot.rest_client import BitbankAPIError, OrderSubmitUncertain, RestClient


def test_create_order_refuses_without_live_confirmed() -> None:
    client = RestClient("https://public.example", "https://private.example", "k", "s")
    try:
        with pytest.raises(BitbankAPIError, match="live_confirmed"):
            client.create_order("btc_jpy", "0.001", "buy", "limit", "1000000")
    finally:
        client.close()


def test_order_post_does_not_retry_on_timeout() -> None:
    http = MagicMock()
    http.request.side_effect = httpx.ReadTimeout("slow")
    client = RestClient(
        "https://public.example",
        "https://private.example",
        "k",
        "s",
        http=http,
        max_retries=5,
    )
    with pytest.raises(OrderSubmitUncertain):
        client.create_order(
            "btc_jpy", "0.001", "buy", "limit", "1000000", live_confirmed=True
        )
    assert http.request.call_count == 1


def test_get_retries_on_timeout() -> None:
    http = MagicMock()
    http.request.side_effect = [httpx.ReadTimeout("slow"), MagicMock(
        status_code=200,
        json=lambda: {"success": 1, "data": {"last": "1"}},
        text="{}",
    )]
    client = RestClient(
        "https://public.example",
        "https://private.example",
        http=http,
        max_retries=3,
    )
    data = client.get_ticker("btc_jpy")
    assert data["last"] == "1"
    assert http.request.call_count == 2
