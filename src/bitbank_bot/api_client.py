"""Single Bitbank API façade.

REST HMAC, rate limits, and POST /user/spot/order stay in ``RestClient``.
Public websocket stays in ``BitbankWebsocket``. This class does not add a
second HTTP client or a second order POST path.

``OrderExecutor`` remains the only production caller that reaches
``create_order`` with ``live_confirmed=True``. Callers that need the raw
REST object use ``client.rest``.
"""

from __future__ import annotations

from typing import Any

from bitbank_bot.config import Config
from bitbank_bot.rest_client import RestClient
from bitbank_bot.websocket_client import BitbankWebsocket


class BitbankAPIClient:
    """Unified handle for Bitbank public REST, private REST, and optional WS."""

    def __init__(
        self,
        rest: RestClient,
        websocket: BitbankWebsocket | None = None,
    ) -> None:
        self.rest = rest
        self.websocket = websocket

    @classmethod
    def from_config(
        cls,
        cfg: Config,
        *,
        http: Any | None = None,
        websocket: BitbankWebsocket | None = None,
    ) -> "BitbankAPIClient":
        rest = RestClient(
            public_url=cfg.public_url,
            private_url=cfg.private_url,
            api_key=cfg.api_key,
            api_secret=cfg.api_secret,
            access_time_window_ms=cfg.access_time_window_ms,
            timeout_sec=cfg.http_timeout_sec,
            max_retries=cfg.max_retries,
            query_rps=cfg.query_rps,
            update_rps=cfg.update_rps,
            http=http,
        )
        return cls(rest=rest, websocket=websocket)

    def close(self) -> None:
        if self.websocket is not None:
            try:
                self.websocket.stop()
            except Exception:
                pass
        self.rest.close()

    def __enter__(self) -> "BitbankAPIClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def get_ticker(self, pair: str) -> dict[str, Any]:
        return self.rest.get_ticker(pair)

    def get_candlestick(
        self, pair: str, candle_type: str, date_key: str
    ) -> list[list[Any]]:
        return self.rest.get_candlestick(pair, candle_type, date_key)

    def get_spot_status(self, pair: str | None = None) -> dict[str, Any] | None:
        return self.rest.get_spot_status(pair)

    def get_assets(self) -> dict[str, Any]:
        return self.rest.get_assets()

    def free_amount(self, asset: str) -> Any:
        return self.rest.free_amount(asset)

    def get_order(self, pair: str, order_id: str) -> dict[str, Any]:
        return self.rest.get_order(pair, order_id)

    def get_trade_history(self, pair: str) -> list[dict[str, Any]]:
        return self.rest.get_trade_history(pair)

    def get_active_orders(self, pair: str) -> list[dict[str, Any]]:
        return self.rest.get_active_orders(pair)

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
        """Delegate only. Still refuses POST unless ``live_confirmed`` is true."""
        return self.rest.create_order(
            pair,
            amount,
            side,
            order_type,
            price,
            post_only,
            live_confirmed=live_confirmed,
        )
