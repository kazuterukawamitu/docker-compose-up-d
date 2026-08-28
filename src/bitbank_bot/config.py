"""Environment-driven configuration. Secrets are never logged or stringified."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv

from bitbank_bot.money import D

PAIR = "btc_jpy"
PUBLIC_URL = "https://public.bitbank.cc"
PRIVATE_URL = "https://api.bitbank.cc/v1"
WS_URL = "wss://stream.bitbank.cc/socket.io/?EIO=4&transport=websocket"

SHORT_CANDLE_TYPES = frozenset({"1min", "5min", "15min", "30min", "1hour"})
LONG_CANDLE_TYPES = frozenset(
    {"4hour", "8hour", "12hour", "1day", "1week", "1month"}
)
CANDLE_TYPES = SHORT_CANDLE_TYPES | LONG_CANDLE_TYPES


class ConfigError(ValueError):
    pass


def _env(env: Mapping[str, str], key: str, default: str | None = None) -> str | None:
    value = env.get(key)
    if value is None or value.strip() == "":
        return default
    return value.strip()


def _bool(env: Mapping[str, str], key: str, default: bool) -> bool:
    raw = _env(env, key)
    if raw is None:
        return default
    return raw.lower() in {"1", "true", "yes", "on"}


def _int(env: Mapping[str, str], key: str, default: int) -> int:
    raw = _env(env, key)
    if raw is None:
        return default
    return int(raw)


def _dec(env: Mapping[str, str], key: str, default: str) -> Decimal:
    raw = _env(env, key, default)
    return D(raw)


@dataclass
class Config:
    pair: str = PAIR
    public_url: str = PUBLIC_URL
    private_url: str = PRIVATE_URL
    ws_url: str = WS_URL
    api_key: str = ""
    api_secret: str = field(default="", repr=False)
    dry_run: bool = True
    live_trading: bool = False
    simulate_fill: bool = True
    candle_type: str = "1hour"
    ma_period: int = 25
    short_ma_period: int = 25
    long_ma_period: int = 75
    ma_kind: str = "sma"
    ma_slope_threshold: Decimal = D("0.0002")
    buy1_tp: Decimal = D("0.03")
    buy2_tp: Decimal = D("0.05")
    buy2_golden_tp: Decimal = D("0.08")
    buy3_tp: Decimal = D("0.04")
    buy4_tp: Decimal = D("0.05")
    buy3_extend: Decimal = D("0.05")
    buy4_dip: Decimal = D("0.05")
    sell1_extend: Decimal = D("0.04")
    sell4_dip: Decimal = D("0.04")
    max_balance_usage: Decimal = D("0.95")
    sell_safety_factor: Decimal = D("0.999")
    fee_buffer: Decimal = D("0.0015")
    min_amount_btc: Decimal = D("0.0001")
    amount_precision: Decimal = D("0.0001")
    price_tick: Decimal = D("1")
    order_type: str = "limit"
    max_position_btc: Decimal = D("1")
    max_order_btc: Decimal = D("10")
    max_daily_loss_jpy: Decimal = D("100000")
    daily_pnl_floor: Decimal = D("150")
    kill_switch: bool = False
    http_timeout_sec: float = 15.0
    max_retries: int = 5
    access_time_window_ms: int = 5000
    query_rps: int = 10
    update_rps: int = 6
    stale_ws_sec: float = 30.0
    poll_sec: float = 15.0
    no_trade_timeout_seconds: int = 900
    enable_websocket: bool = True
    dashboard: bool = False
    log_level: str = "INFO"
    log_dir: str = "logs"
    state_path: str = "data/state.json"
    lock_path: str = "data/bot.lock"
    candle_lookback_days: int = 14
    ws_rooms: tuple[str, ...] = (
        "ticker_btc_jpy",
        "transactions_btc_jpy",
        "depth_whole_btc_jpy",
    )

    @property
    def has_keys(self) -> bool:
        return bool(self.api_key) and bool(self.api_secret)

    @property
    def may_place_live_orders(self) -> bool:
        return (not self.dry_run) and self.live_trading and self.has_keys

    def safe_dict(self) -> dict[str, object]:
        return {
            "pair": self.pair,
            "has_api_key": bool(self.api_key),
            "has_api_secret": bool(self.api_secret),
            "dry_run": self.dry_run,
            "live_trading": self.live_trading,
            "candle_type": self.candle_type,
            "ma_period": self.ma_period,
            "order_type": self.order_type,
            "kill_switch": self.kill_switch,
            "enable_websocket": self.enable_websocket,
            "log_level": self.log_level,
        }


def load_config(
    env_file: str | Path | None = None,
    environ: Mapping[str, str] | None = None,
    load_default_dotenv: bool = True,
) -> Config:
    if env_file:
        load_dotenv(env_file, override=False)
    elif load_default_dotenv:
        load_dotenv(override=False)
    env: Mapping[str, str] = environ if environ is not None else os.environ
    pair = (_env(env, "BITBANK_PAIR", PAIR) or PAIR).lower()
    if pair != PAIR:
        raise ConfigError("This bot executes Bitbank btc_jpy only")

    dry_run = _bool(env, "DRY_RUN", True)
    live_trading = _bool(env, "LIVE_TRADING", False)
    if dry_run and live_trading:
        raise ConfigError("LIVE_TRADING and DRY_RUN cannot both be true")
    if not live_trading and not dry_run:
        raise ConfigError(
            "DRY_RUN=false requires LIVE_TRADING=true (dual confirmation)."
        )

    candle_type = _env(env, "CANDLE_TYPE", "1hour") or "1hour"
    if candle_type not in CANDLE_TYPES:
        raise ConfigError(f"unsupported CANDLE_TYPE={candle_type}")

    ma_kind = (_env(env, "MA_KIND", "sma") or "sma").lower()
    if ma_kind not in {"sma", "ema"}:
        raise ConfigError("MA_KIND must be sma or ema")

    order_type = (
        _env(env, "ORDER_TYPE") or _env(env, "BITBANK_ORDER_TYPE") or "limit"
    ).lower()
    if order_type not in {"market", "limit"}:
        raise ConfigError("ORDER_TYPE must be market or limit")

    window = _int(env, "ACCESS_TIME_WINDOW_MS", _int(env, "ACCESS_TIME_WINDOW", 5000))
    if window < 1 or window > 60000:
        raise ConfigError("ACCESS_TIME_WINDOW_MS must be 1..60000")

    usage = _dec(env, "MAX_BALANCE_USAGE", "0.95")
    if usage <= 0 or usage > 1:
        raise ConfigError("MAX_BALANCE_USAGE must be in (0, 1]")

    cfg = Config(
        pair=pair,
        public_url=_env(env, "BITBANK_PUBLIC_URL", PUBLIC_URL) or PUBLIC_URL,
        private_url=_env(env, "BITBANK_PRIVATE_URL", PRIVATE_URL) or PRIVATE_URL,
        ws_url=_env(env, "BITBANK_WS_URL", WS_URL) or WS_URL,
        api_key=_env(env, "BITBANK_API_KEY", "") or "",
        api_secret=_env(env, "BITBANK_API_SECRET", "") or "",
        dry_run=dry_run,
        live_trading=live_trading,
        simulate_fill=_bool(env, "DRY_RUN_SIMULATE_FILL", True),
        candle_type=candle_type,
        ma_period=_int(env, "MA_PERIOD", 25),
        short_ma_period=_int(env, "SHORT_MA_PERIOD", _int(env, "MA_SHORT_PERIOD", 25)),
        long_ma_period=_int(env, "LONG_MA_PERIOD", _int(env, "MA_LONG_PERIOD", 75)),
        ma_kind=ma_kind,
        ma_slope_threshold=_dec(env, "MA_SLOPE_THRESHOLD", "0.0002"),
        buy1_tp=_dec(env, "BUY1_TP", "0.03"),
        buy2_tp=_dec(env, "BUY2_TP", "0.05"),
        buy2_golden_tp=_dec(env, "BUY2_GOLDEN_TP", "0.08"),
        buy3_tp=_dec(env, "BUY3_TP", "0.04"),
        buy4_tp=_dec(env, "BUY4_TP", "0.05"),
        buy3_extend=_dec(env, "BUY3_EXTEND", "0.05"),
        buy4_dip=_dec(env, "BUY4_DIP", "0.05"),
        sell1_extend=_dec(env, "SELL1_EXTEND", "0.04"),
        sell4_dip=_dec(env, "SELL4_DIP", "0.04"),
        max_balance_usage=usage,
        sell_safety_factor=_dec(env, "SELL_SAFETY_FACTOR", "0.999"),
        fee_buffer=_dec(env, "FEE_BUFFER", "0.0015"),
        min_amount_btc=_dec(env, "MIN_AMOUNT_BTC", "0.0001"),
        amount_precision=_dec(env, "AMOUNT_PRECISION", "0.0001"),
        price_tick=_dec(env, "PRICE_TICK", "1"),
        order_type=order_type,
        max_position_btc=_dec(env, "MAX_POSITION_BTC", "1"),
        max_order_btc=_dec(env, "MAX_ORDER_BTC", "10"),
        max_daily_loss_jpy=_dec(env, "MAX_DAILY_LOSS_JPY", "100000"),
        daily_pnl_floor=_dec(env, "DAILY_PNL_FLOOR", "150"),
        kill_switch=_bool(env, "KILL_SWITCH", False),
        http_timeout_sec=float(_env(env, "HTTP_TIMEOUT_SEC", "15") or "15"),
        max_retries=_int(env, "MAX_RETRIES", 5),
        access_time_window_ms=window,
        query_rps=_int(env, "QUERY_RPS", 10),
        update_rps=_int(env, "UPDATE_RPS", 6),
        stale_ws_sec=float(
            _env(env, "STALE_WS_SEC") or _env(env, "STALE_DATA_SECONDS") or "30"
        ),
        poll_sec=float(_env(env, "POLL_SEC") or _env(env, "LOOP_SECONDS") or "15"),
        no_trade_timeout_seconds=_int(env, "NO_TRADE_TIMEOUT_SECONDS", 900),
        enable_websocket=_bool(env, "ENABLE_WEBSOCKET", True),
        dashboard=_bool(env, "DASHBOARD", False),
        log_level=(_env(env, "LOG_LEVEL", "INFO") or "INFO").upper(),
        log_dir=_env(env, "LOG_DIR", "logs") or "logs",
        state_path=_env(env, "STATE_PATH", "data/state.json") or "data/state.json",
        lock_path=_env(env, "LOCK_PATH", "data/bot.lock") or "data/bot.lock",
        candle_lookback_days=_int(env, "CANDLE_LOOKBACK_DAYS", 14),
    )
    if live_trading and not cfg.has_keys:
        raise ConfigError("LIVE_TRADING requires BITBANK_API_KEY and BITBANK_API_SECRET")
    if cfg.ma_period < 2 or cfg.short_ma_period < 2 or cfg.long_ma_period < 2:
        raise ConfigError("MA periods must be >= 2")
    if cfg.long_ma_period < cfg.short_ma_period:
        raise ConfigError("LONG_MA_PERIOD must be >= SHORT_MA_PERIOD")
    return cfg
