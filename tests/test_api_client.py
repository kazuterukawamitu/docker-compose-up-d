from __future__ import annotations

from unittest.mock import MagicMock

from bitbank_bot.api_client import BitbankAPIClient
from bitbank_bot.engine import Engine
from bitbank_bot.rest_client import BitbankAPIError, RestClient
from tests.helpers import cfg


def test_facade_create_order_requires_live_confirmed() -> None:
    rest = RestClient("https://public.example", "https://private.example", "k", "s")
    api = BitbankAPIClient(rest=rest)
    try:
        raised = False
        try:
            api.create_order("btc_jpy", "0.001", "buy", "limit", "1000000")
        except BitbankAPIError as exc:
            raised = True
            assert "live_confirmed" in str(exc)
        assert raised
    finally:
        api.close()


def test_from_config_uses_cfg_urls() -> None:
    c = cfg(public_url="https://public.example", private_url="https://private.example")
    api = BitbankAPIClient.from_config(c)
    try:
        assert api.rest.public_url == "https://public.example"
        assert api.rest.private_url == "https://private.example"
        assert api.websocket is None
    finally:
        api.close()


def test_engine_unwraps_api_client() -> None:
    fake = MagicMock()
    api = BitbankAPIClient(rest=fake)
    engine = Engine(cfg(), client=api)
    assert engine.client is fake
    assert engine.api is api
