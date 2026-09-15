from __future__ import annotations

import httpx
import pytest

from bitbank_bot.rest_client import (
    BitbankAPIError,
    RestClient,
    get_sign_payload,
    sign_access_time_window,
)
from tests.helpers import cfg


def test_sign_is_hmac_sha256_hex() -> None:
    sig = sign_access_time_window("secret", "1000", "5000", '{"pair":"btc_jpy"}')
    assert len(sig) == 64
    assert sig == sign_access_time_window("secret", "1000", "5000", '{"pair":"btc_jpy"}')
    assert sig != sign_access_time_window("secret", "1001", "5000", '{"pair":"btc_jpy"}')


def test_official_time_window_sample() -> None:
    # https://github.com/bitbankinc/bitbank-api-docs/blob/master/rest-api.md
    sig = sign_access_time_window(
        "hoge",
        "1721121776490",
        "1000",
        "/v1/user/assets",
    )
    assert sig == "9ec5745960d05573c8fb047cdd9191bd0c6ede26f07700bb40ecf1a3920abae8"


def test_get_sign_payload_includes_v1() -> None:
    assert get_sign_payload("/user/assets") == "/v1/user/assets"
    assert "pair=btc_jpy" in get_sign_payload("/user/spot/active_orders", {"pair": "btc_jpy"})


def test_create_order_refuses_without_live_confirmed() -> None:
    client = RestClient("https://public.example", "https://private.example", "k", "s")
    try:
        raised = False
        try:
            client.create_order("btc_jpy", "0.001", "buy", "limit", "1000000")
        except BitbankAPIError as exc:
            raised = True
            assert "live_confirmed" in str(exc)
        assert raised
    finally:
        client.close()


def test_cfg_pair_used() -> None:
    assert cfg().pair == "btc_jpy"


def test_private_post_is_not_retried() -> None:
    class CountingTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.n = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            self.n += 1
            raise httpx.ConnectError("offline")

    transport = CountingTransport()
    client = RestClient(
        "https://public.example",
        "https://private.example/v1",
        "k",
        "s",
        max_retries=5,
        http=httpx.Client(transport=transport),
    )
    try:
        with pytest.raises(BitbankAPIError):
            client.create_order(
                "btc_jpy", "0.001", "buy", "limit", "1000000", live_confirmed=True
            )
        assert transport.n == 1
    finally:
        client.close()


def test_public_get_retries_on_transport_error() -> None:
    class CountingTransport(httpx.BaseTransport):
        def __init__(self) -> None:
            self.n = 0

        def handle_request(self, request: httpx.Request) -> httpx.Response:
            self.n += 1
            raise httpx.ConnectError("offline")

    transport = CountingTransport()
    client = RestClient(
        "https://public.example",
        "https://private.example/v1",
        max_retries=3,
        http=httpx.Client(transport=transport),
    )
    try:
        with pytest.raises(BitbankAPIError):
            client.get_ticker("btc_jpy")
        assert transport.n == 3
    finally:
        client.close()


def test_http_404_json_exposes_bitbank_code() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"success": 0, "data": {"code": 10000}},
        )

    client = RestClient(
        "https://public.example",
        "https://private.example/v1",
        http=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    try:
        with pytest.raises(BitbankAPIError) as caught:
            client.get_candlestick("btc_jpy", "5min", "20260916")
        assert caught.value.http_status == 404
        assert caught.value.code == 10000
    finally:
        client.close()
