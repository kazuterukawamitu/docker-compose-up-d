from decimal import Decimal

from bitbank_bot.exchange.auth import (
    sign_get_nonce,
    sign_get_time_window,
    sign_post_nonce,
    sign_post_time_window,
)


def test_official_get_nonce_vector() -> None:
    sig = sign_get_nonce("hoge", "1721121776490", "/v1/user/assets")
    assert sig == "f957817b95c3af6cf5e2e9dfe1503ea8088f46879d4ab73051467fd7b94f1aba"


def test_official_post_nonce_vector() -> None:
    body = '{"pair": "xrp_jpy", "price": "20", "amount": "1","side": "buy", "type": "limit"}'
    sig = sign_post_nonce("hoge", "1721121776490", body)
    assert sig == "8ef83c2b991765b18c95aade7678471747c06890a23a453c76238345b5c86fb8"


def test_official_get_time_window_vector() -> None:
    sig = sign_get_time_window("hoge", "1721121776490", "1000", "/v1/user/assets")
    assert sig == "9ec5745960d05573c8fb047cdd9191bd0c6ede26f07700bb40ecf1a3920abae8"


def test_official_post_time_window_vector() -> None:
    body = '{"pair": "xrp_jpy", "price": "20", "amount": "1","side": "buy", "type": "limit"}'
    sig = sign_post_time_window("hoge", "1721121776490", "1000", body)
    assert sig == "7868665738ae3f8a796224e0413c1351ddd7ec2af121db12815c0a5b74b8764c"
