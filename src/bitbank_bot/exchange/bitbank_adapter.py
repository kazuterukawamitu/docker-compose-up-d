"""Thin Bitbank venue wrapper. RestClient remains the only HTTP + HMAC layer.

Strategy never imports this module. OrderExecutor is still the only caller of
``create_order`` on the live path; this adapter only forwards.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from bitbank_bot.config import Config
from bitbank_bot.rest_client import RestClient


class BitbankAdapter:
    def __init__(self, rest: RestClient) -> None:
        self.rest = rest

    @classmethod
    def wrap(cls, client: RestClient | "BitbankAdapter") -> "BitbankAdapter":
        if isinstance(client, BitbankAdapter):
            return client
        return cls(client)

    @classmethod
    def from_config(cls, cfg: Config) -> "BitbankAdapter":
        return cls(
            RestClient(
                public_url=cfg.public_url,
                private_url=cfg.private_url,
                api_key=cfg.api_key,
                api_secret=cfg.api_secret,
                access_time_window_ms=cfg.access_time_window_ms,
                timeout_sec=cfg.http_timeout_sec,
                max_retries=cfg.max_retries,
                query_rps=cfg.query_rps,
                update_rps=cfg.update_rps,
            )
        )

    def close(self) -> None:
        self.rest.close()

    def get_ticker(self, pair: str) -> dict[str, Any]:
        return self.rest.get_ticker(pair)

    def get_depth(self, pair: str) -> dict[str, Any]:
        return self.rest.get_depth(pair)

    def get_candlestick(self, pair: str, candle_type: str, date_key: str) -> list[list[Any]]:
        return self.rest.get_candlestick(pair, candle_type, date_key)

    def get_spot_status(self, pair: str | None = None) -> dict[str, Any] | None:
        return self.rest.get_spot_status(pair)

    def get_assets(self) -> dict[str, Any]:
        return self.rest.get_assets()

    def free_amount(self, asset: str) -> Decimal:
        return self.rest.free_amount(asset)

    def get_order(self, pair: str, order_id: str) -> dict[str, Any]:
        return self.rest.get_order(pair, order_id)

    def get_trade_history(self, pair: str) -> list[dict[str, Any]]:
        return self.rest.get_trade_history(pair)

    def get_active_orders(self, pair: str) -> list[dict[str, Any]]:
        return list(self.rest.get_active_orders(pair) or [])

    def create_order(
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
        return self.rest.create_order(
            pair,
            amount,
            side,
            order_type,
            price,
            post_only,
            live_confirmed=live_confirmed,
        )

    def cancel_order(
        self,
        pair: str,
        order_id: str,
        *,
        live_confirmed: bool = False,
    ) -> dict[str, Any]:
        return self.rest.cancel_order(pair, order_id, live_confirmed=live_confirmed)
