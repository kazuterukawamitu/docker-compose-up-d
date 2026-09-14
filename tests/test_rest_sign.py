from __future__ import annotations

import httpx

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


def test_create_order_does_not_retry_http_500() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport, timeout=5.0)
    client = RestClient(
        "https://public.example",
        "https://private.example",
        "k",
        "s",
        http=http,
        max_retries=5,
    )
    try:
        raised = False
        try:
            client.create_order(
                "btc_jpy",
                "0.001",
                "buy",
                "limit",
                "1000000",
                live_confirmed=True,
            )
        except BitbankAPIError as exc:
            raised = True
            assert exc.http_status == 500
        assert raised
        assert calls["n"] == 1
    finally:
        client.close()
