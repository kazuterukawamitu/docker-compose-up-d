"""Named runtime facades. They wrap existing modules; they do not add a second order path."""

from __future__ import annotations

from typing import Any

from bitbank_bot.config import Config
from bitbank_bot.engine_state import BotState, load_state, save_state
from bitbank_bot.exchange import BitbankAdapter
from bitbank_bot.logging_setup import slog
from bitbank_bot.market_data import Candle, CandleCache, fetch_candles
from bitbank_bot.orders import OrderExecutor, OrderResult
from bitbank_bot.rest_client import RestClient
from bitbank_bot.websocket_client import BitbankWebsocket


class ConnectionManager:
    def __init__(self, cfg: Config, client: Any | None = None) -> None:
        self.cfg = cfg
        self.client = client
        self.ws: BitbankWebsocket | None = None

    def rest(self) -> Any:
        if self.client is None:
            self.client = BitbankAdapter.from_config(self.cfg)
        elif isinstance(self.client, RestClient):
            self.client = BitbankAdapter.wrap(self.client)
        return self.client

    def start_ws(self) -> BitbankWebsocket | None:
        if not self.cfg.enable_websocket or self.ws is not None:
            return self.ws
        try:
            self.ws = BitbankWebsocket(
                self.cfg.ws_url, self.cfg.ws_rooms, stale_sec=self.cfg.stale_ws_sec
            )
            self.ws.start()
        except Exception as exc:
            slog("WEBSOCKET", "start failed; REST only", error=type(exc).__name__)
            self.ws = None
        return self.ws

    def stop_ws(self) -> None:
        if self.ws is not None:
            self.ws.stop()
            self.ws = None

    def snapshot(self) -> dict[str, object]:
        ws = self.ws
        return {
            "rest": self.client is not None,
            "ws_enabled": self.cfg.enable_websocket,
            "ws_connected": bool(ws and ws.is_connected()),
            "ws_stale": bool(ws and self.cfg.enable_websocket and ws.is_stale()),
        }


class DataManager:
    def __init__(self, cfg: Config, client: Any, cache: CandleCache) -> None:
        self.cfg = cfg
        self.client = client
        self.cache = cache

    def fetch_candles(self, *, latest_only: bool = False) -> list[Candle]:
        return fetch_candles(self.client, self.cfg, latest_only=latest_only)

    def ticker(self) -> dict[str, Any]:
        return self.client.get_ticker(self.cfg.pair)

    def depth(self) -> dict[str, Any]:
        if not hasattr(self.client, "get_depth"):
            return {}
        return self.client.get_depth(self.cfg.pair)


class StateManager:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def load(self) -> BotState:
        return load_state(self.cfg.state_path, self.cfg)

    def save(self, state: BotState) -> None:
        save_state(self.cfg.state_path, state)


class ExecutionMonitor:
    def __init__(self, cfg: Config, client: Any | None) -> None:
        self.cfg = cfg
        self.orders = OrderExecutor(cfg, client)

    def open_order_count(self) -> int:
        active = self.orders.active_orders()
        if not isinstance(active, list):
            slog("ERROR", "active_orders was not a list", type=type(active).__name__)
            return 0
        return len(active)

    def poll(self, order_id: str, fallback_amount: Any) -> OrderResult:
        return self.orders.poll(order_id, fallback_amount)

    def cancel(self, order_id: str) -> bool:
        return self.orders.cancel(order_id)
