from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from bitbank_bot.rest_client import BitbankAPIError, RestClient


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
