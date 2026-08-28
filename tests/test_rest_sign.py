from bitbank_bot.rest_client import dump_json, get_sign_payload, sign_access_time_window


def test_official_get_signature() -> None:
    sig = sign_access_time_window(
        "hoge",
        "1721121776490",
        "1000",
        "/v1/user/assets",
    )
    assert sig == "9ec5745960d05573c8fb047cdd9191bd0c6ede26f07700bb40ecf1a3920abae8"


def test_official_post_signature() -> None:
    body = '{"pair": "xrp_jpy", "price": "20", "amount": "1","side": "buy", "type": "limit"}'
    sig = sign_access_time_window("hoge", "1721121776490", "1000", body)
    assert sig == "7868665738ae3f8a796224e0413c1351ddd7ec2af121db12815c0a5b74b8764c"


def test_get_sign_payload_matches_python_bitbankcc() -> None:
    assert get_sign_payload("/user/assets") == "/v1/user/assets"
    assert (
        get_sign_payload("/user/spot/order", {"pair": "btc_jpy", "order_id": "1"})
        == "/v1/user/spot/order?pair=btc_jpy&order_id=1"
    )


def test_dump_json_compact() -> None:
    raw = dump_json(
        {
            "pair": "xrp_jpy",
            "price": "20",
            "amount": "1",
            "side": "buy",
            "type": "limit",
        }
    )
    assert " " not in raw
    assert raw.startswith("{")
    assert '"pair":"xrp_jpy"' in raw
