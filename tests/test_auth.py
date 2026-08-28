from bitbank_bot.exchange.signing import hmac_sha256, sign_get, sign_post


def test_official_get_signature() -> None:
    # Sample from bitbankinc/bitbank-api-docs rest-api.md ACCESS-NONCE GET /v1/user/assets
    sig = sign_get("hoge", "1721121776490", "/v1/user/assets")
    assert sig == "f957817b95c3af6cf5e2e9dfe1503ea8088f46879d4ab73051467fd7b94f1aba"


def test_official_post_signature() -> None:
    body = '{"pair": "xrp_jpy", "price": "20", "amount": "1","side": "buy", "type": "limit"}'
    sig = sign_post("hoge", "1721121776490", body)
    assert sig == "8ef83c2b991765b18c95aade7678471747c06890a23a453c76238345b5c86fb8"


def test_hmac_is_hex() -> None:
    digest = hmac_sha256("secret", "payload")
    assert len(digest) == 64
    int(digest, 16)
