"""Bitbank-only adapter. Strategies must not call REST URLs themselves."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from bitbank_bot.rest_client import RestClient


class BitbankAdapter:
    def __init__(self, client: RestClient) -> None:
        self.client = client

    def get_ticker(self, pair: str) -> dict[str, Any]:
        return self.client.get_ticker(pair)

    def get_candles(self, pair: str, candle_type: str, date_key: str) -> list[list[Any]]:
        return self.client.get_candlestick(pair, candle_type, date_key)

    def get_depth(self, pair: str) -> Any:
        return self.client.public_get(f"/{pair}/depth")

    def get_assets(self) -> dict[str, Any]:
        return self.client.get_assets()

    def get_active_orders(self, pair: str) -> list[dict[str, Any]]:
        return self.client.get_active_orders(pair)

    def get_order(self, pair: str, order_id: str) -> dict[str, Any]:
        return self.client.get_order(pair, order_id)

    def place_order(
        self,
        pair: str,
        amount: str,
        side: str,
        order_type: str,
        price: str | None = None,
        post_only: bool | None = None,
        *,
        live_confirmed: bool = False,
    ) -> dict[str, Any]:
        return self.client.create_order(
            pair,
            amount,
            side,
            order_type,
            price,
            post_only,
            live_confirmed=live_confirmed,
        )

    def cancel_order(self, pair: str, order_id: str) -> dict[str, Any]:
        return self.client.cancel_order(pair, order_id)

    def get_trade_history(self, pair: str) -> list[dict[str, Any]]:
        return self.client.get_trade_history(pair)

    def free_amount(self, asset: str) -> Decimal:
        return self.client.free_amount(asset)
