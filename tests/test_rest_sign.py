from __future__ import annotations

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
