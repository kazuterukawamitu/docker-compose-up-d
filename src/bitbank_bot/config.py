"""Environment-driven configuration. Secrets are never logged or stringified."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Mapping

try:
    from dotenv import load_dotenv
except ImportError:  # system python without venv; start.sh installs dotenv

    def load_dotenv(*_args: object, **_kwargs: object) -> bool:
        return False

from bitbank_bot.money import D

PAIR = "btc_jpy"
PUBLIC_URL = "https://public.bitbank.cc"
PRIVATE_URL = "https://api.bitbank.cc/v1"
WS_URL = "wss://stream.bitbank.cc/socket.io/?EIO=4&transport=websocket"

DEFAULT_CANDLE_TYPE = "1hour"
DEFAULT_MA_PERIOD = 20
DEFAULT_SHORT_MA_PERIOD = 20
DEFAULT_LONG_MA_PERIOD = 50
DEFAULT_MA_KIND = "sma"
DEFAULT_MA_SLOPE = "0.0005"
DEFAULT_BUY1_TP = "0.03"
DEFAULT_BUY2_TP = "0.05"
DEFAULT_BUY2_GOLDEN_TP = "0.08"
DEFAULT_BUY3_TP = "0.04"
DEFAULT_BUY4_TP = "0.05"
DEFAULT_BUY3_EXTEND = "0.05"
DEFAULT_BUY4_DIP = "0.05"
DEFAULT_SELL1_EXTEND = "0.04"
DEFAULT_SELL4_DIP = "0.04"
DEFAULT_MAX_BALANCE_USAGE = "0.95"
DEFAULT_SELL_SAFETY = "0.999"
DEFAULT_FEE_BUFFER = "0.0015"
DEFAULT_MIN_AMOUNT = "0.0001"
DEFAULT_AMOUNT_PRECISION = "0.0001"
DEFAULT_PRICE_TICK = "1"
DEFAULT_MAX_POSITION = "1"
DEFAULT_MAX_ORDER = "10"
DEFAULT_MAX_DAILY_LOSS = "0"
DEFAULT_DAILY_PNL_FLOOR = "0"
DEFAULT_STALE_SEC = "60"
DEFAULT_POLL_SEC = "15"
DEFAULT_NO_TRADE_TIMEOUT = 900
DEFAULT_LOCK_PATH = "data/bot.lock"
DEFAULT_STATE_PATH = "data/state.json"
DEFAULT_KILL_PATH = "data/KILL"
DEFAULT_LOG_DIR = "logs"
DEFAULT_DRY_RUN_JPY = "100000"
DEFAULT_DRY_RUN_BTC = "0"
DEFAULT_LOOKBACK_DAYS = 14
DEFAULT_ACCESS_WINDOW_MS = 5000
DEFAULT_CIRCUIT_BREAKER_ERRORS = 5
DEFAULT_MAX_DRAWDOWN_JPY = "0"

SHORT_CANDLE_TYPES = frozenset({"1min", "5min", "15min", "30min", "1hour"})
LONG_CANDLE_TYPES = frozenset({"4hour", "8hour", "12hour", "1day", "1week", "1month"})
CANDLE_TYPES = SHORT_CANDLE_TYPES | LONG_CANDLE_TYPES

REJECTED_PAIR_ALIASES = frozenset(
    {
        "btc_jpn",
        "jpn_btc",
        "jpy_btc",
        "jpc_btc",
        "btc_jpc",
        "jpn_jpy",
        "btcjpy",
        "jpc_jpy",
    }
)


class ConfigError(ValueError):
    pass


def normalize_pair(raw: str) -> str:
    return raw.strip().lower().replace("/", "_").replace("-", "_").replace(" ", "")


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
    candle_type: str = DEFAULT_CANDLE_TYPE
    ma_period: int = DEFAULT_MA_PERIOD
    short_ma_period: int = DEFAULT_SHORT_MA_PERIOD
    long_ma_period: int = DEFAULT_LONG_MA_PERIOD
    ma_kind: str = DEFAULT_MA_KIND
    ma_slope_threshold: Decimal = D(DEFAULT_MA_SLOPE)
    buy1_tp: Decimal = D(DEFAULT_BUY1_TP)
    buy2_tp: Decimal = D(DEFAULT_BUY2_TP)
    buy2_golden_tp: Decimal = D(DEFAULT_BUY2_GOLDEN_TP)
    buy3_tp: Decimal = D(DEFAULT_BUY3_TP)
    buy4_tp: Decimal = D(DEFAULT_BUY4_TP)
    buy3_extend: Decimal = D(DEFAULT_BUY3_EXTEND)
    buy4_dip: Decimal = D(DEFAULT_BUY4_DIP)
    sell1_extend: Decimal = D(DEFAULT_SELL1_EXTEND)
    sell4_dip: Decimal = D(DEFAULT_SELL4_DIP)
    max_balance_usage: Decimal = D(DEFAULT_MAX_BALANCE_USAGE)
    sell_safety_factor: Decimal = D(DEFAULT_SELL_SAFETY)
    fee_buffer: Decimal = D(DEFAULT_FEE_BUFFER)
    min_amount_btc: Decimal = D(DEFAULT_MIN_AMOUNT)
    amount_precision: Decimal = D(DEFAULT_AMOUNT_PRECISION)
    price_tick: Decimal = D(DEFAULT_PRICE_TICK)
    order_type: str = "limit"
    max_position_btc: Decimal = D(DEFAULT_MAX_POSITION)
    max_order_btc: Decimal = D(DEFAULT_MAX_ORDER)
    max_daily_loss_jpy: Decimal = D(DEFAULT_MAX_DAILY_LOSS)
    daily_pnl_floor: Decimal = D(DEFAULT_DAILY_PNL_FLOOR)
    kill_switch: bool = False
    kill_switch_path: str = DEFAULT_KILL_PATH
    post_only: bool = False
    dry_run_free_jpy: Decimal = D(DEFAULT_DRY_RUN_JPY)
    dry_run_free_btc: Decimal = D(DEFAULT_DRY_RUN_BTC)
    http_timeout_sec: float = 15.0
    max_retries: int = 5
    access_time_window_ms: int = DEFAULT_ACCESS_WINDOW_MS
    query_rps: int = 10
    update_rps: int = 6
    stale_ws_sec: float = float(DEFAULT_STALE_SEC)
    poll_sec: float = float(DEFAULT_POLL_SEC)
    no_trade_timeout_seconds: int = DEFAULT_NO_TRADE_TIMEOUT
    enable_websocket: bool = True
    log_level: str = "INFO"
    log_dir: str = DEFAULT_LOG_DIR
    state_path: str = DEFAULT_STATE_PATH
    lock_path: str = DEFAULT_LOCK_PATH
    candle_lookback_days: int = DEFAULT_LOOKBACK_DAYS
    circuit_breaker_errors: int = DEFAULT_CIRCUIT_BREAKER_ERRORS
    max_drawdown_jpy: Decimal = D(DEFAULT_MAX_DRAWDOWN_JPY)
    ws_rooms: tuple[str, ...] = ("ticker_btc_jpy",)

    def __str__(self) -> str:
        return f"Config(pair={self.pair}, dry_run={self.dry_run}, live_trading={self.live_trading})"

    def __repr__(self) -> str:
        return self.__str__()

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
            "may_place_live_orders": self.may_place_live_orders,
            "simulate_fill": self.simulate_fill,
            "candle_type": self.candle_type,
            "ma_period": self.ma_period,
            "short_ma_period": self.short_ma_period,
            "long_ma_period": self.long_ma_period,
            "ma_kind": self.ma_kind,
            "ma_slope_threshold": str(self.ma_slope_threshold),
            "order_type": self.order_type,
            "kill_switch": self.kill_switch,
            "enable_websocket": self.enable_websocket,
            "lock_path": self.lock_path,
            "stale_ws_sec": self.stale_ws_sec,
            "log_level": self.log_level,
            "max_balance_usage": str(self.max_balance_usage),
            "min_amount_btc": str(self.min_amount_btc),
            "circuit_breaker_errors": self.circuit_breaker_errors,
            "max_drawdown_jpy": str(self.max_drawdown_jpy),
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
    pair = normalize_pair(_env(env, "BITBANK_PAIR", PAIR) or PAIR)
    if pair in REJECTED_PAIR_ALIASES:
        raise ConfigError(f"rejected pair alias {pair}; use {PAIR}")
    if pair != PAIR:
        raise ConfigError("This bot executes Bitbank btc_jpy only")

    dry_run = _bool(env, "DRY_RUN", True)
    live_trading = _bool(env, "LIVE_TRADING", False)
    if dry_run and live_trading:
        raise ConfigError("LIVE_TRADING and DRY_RUN cannot both be true")
    if not live_trading and not dry_run:
        raise ConfigError("DRY_RUN=false requires LIVE_TRADING=true (dual confirmation).")

    candle_type = _env(env, "CANDLE_TYPE", DEFAULT_CANDLE_TYPE) or DEFAULT_CANDLE_TYPE
    if candle_type not in CANDLE_TYPES:
        raise ConfigError(f"unsupported CANDLE_TYPE={candle_type}")

    ma_kind = (_env(env, "MA_KIND", DEFAULT_MA_KIND) or DEFAULT_MA_KIND).lower()
    if ma_kind not in {"sma", "ema"}:
        raise ConfigError("MA_KIND must be sma or ema")

    order_type = (
        _env(env, "ORDER_TYPE") or _env(env, "BITBANK_ORDER_TYPE") or "limit"
    ).lower()
    if order_type not in {"market", "limit"}:
        raise ConfigError("ORDER_TYPE must be market or limit")

    window = _int(
        env, "ACCESS_TIME_WINDOW_MS", _int(env, "ACCESS_TIME_WINDOW", DEFAULT_ACCESS_WINDOW_MS)
    )
    if window < 1 or window > 60000:
        raise ConfigError("ACCESS_TIME_WINDOW_MS must be 1..60000")

    if _env(env, "BALANCE_USAGE_RATIO") is not None:
        usage = _dec(env, "BALANCE_USAGE_RATIO", DEFAULT_MAX_BALANCE_USAGE)
    else:
        usage = _dec(env, "MAX_BALANCE_USAGE", DEFAULT_MAX_BALANCE_USAGE)
    if usage <= 0 or usage > 1:
        raise ConfigError("MAX_BALANCE_USAGE / BALANCE_USAGE_RATIO must be in (0, 1]")

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
        ma_period=_int(env, "MA_PERIOD", DEFAULT_MA_PERIOD),
        short_ma_period=_int(
            env, "SHORT_MA_PERIOD", _int(env, "MA_SHORT_PERIOD", DEFAULT_SHORT_MA_PERIOD)
        ),
        long_ma_period=_int(
            env, "LONG_MA_PERIOD", _int(env, "MA_LONG_PERIOD", DEFAULT_LONG_MA_PERIOD)
        ),
        ma_kind=ma_kind,
        ma_slope_threshold=_dec(env, "MA_SLOPE_THRESHOLD", DEFAULT_MA_SLOPE),
        buy1_tp=_dec(env, "BUY1_TP", DEFAULT_BUY1_TP),
        buy2_tp=_dec(env, "BUY2_TP", DEFAULT_BUY2_TP),
        buy2_golden_tp=_dec(env, "BUY2_GOLDEN_TP", DEFAULT_BUY2_GOLDEN_TP),
        buy3_tp=_dec(env, "BUY3_TP", DEFAULT_BUY3_TP),
        buy4_tp=_dec(env, "BUY4_TP", DEFAULT_BUY4_TP),
        buy3_extend=_dec(env, "BUY3_EXTEND", DEFAULT_BUY3_EXTEND),
        buy4_dip=_dec(env, "BUY4_DIP", DEFAULT_BUY4_DIP),
        sell1_extend=_dec(env, "SELL1_EXTEND", DEFAULT_SELL1_EXTEND),
        sell4_dip=_dec(env, "SELL4_DIP", DEFAULT_SELL4_DIP),
        max_balance_usage=usage,
        sell_safety_factor=_dec(env, "SELL_SAFETY_FACTOR", DEFAULT_SELL_SAFETY),
        fee_buffer=_dec(env, "FEE_BUFFER", DEFAULT_FEE_BUFFER),
        min_amount_btc=_dec(env, "MIN_AMOUNT_BTC", DEFAULT_MIN_AMOUNT),
        amount_precision=_dec(env, "AMOUNT_PRECISION", DEFAULT_AMOUNT_PRECISION),
        price_tick=_dec(env, "PRICE_TICK", DEFAULT_PRICE_TICK),
        order_type=order_type,
        max_position_btc=_dec(env, "MAX_POSITION_BTC", DEFAULT_MAX_POSITION),
        max_order_btc=_dec(env, "MAX_ORDER_BTC", DEFAULT_MAX_ORDER),
        max_daily_loss_jpy=_dec(env, "MAX_DAILY_LOSS_JPY", DEFAULT_MAX_DAILY_LOSS),
        daily_pnl_floor=_dec(env, "DAILY_PNL_FLOOR", DEFAULT_DAILY_PNL_FLOOR),
        kill_switch=_bool(env, "KILL_SWITCH", False),
        kill_switch_path=_env(env, "KILL_SWITCH_PATH", DEFAULT_KILL_PATH) or DEFAULT_KILL_PATH,
        post_only=_bool(env, "POST_ONLY", False),
        dry_run_free_jpy=_dec(env, "DRY_RUN_FREE_JPY", DEFAULT_DRY_RUN_JPY),
        dry_run_free_btc=_dec(env, "DRY_RUN_FREE_BTC", DEFAULT_DRY_RUN_BTC),
        http_timeout_sec=float(_env(env, "HTTP_TIMEOUT_SEC", "15") or "15"),
        max_retries=_int(env, "MAX_RETRIES", 5),
        access_time_window_ms=window,
        query_rps=_int(env, "QUERY_RPS", 10),
        update_rps=_int(env, "UPDATE_RPS", 6),
        stale_ws_sec=float(
            _env(env, "STALE_WS_SEC") or _env(env, "STALE_DATA_SECONDS") or DEFAULT_STALE_SEC
        ),
        poll_sec=float(_env(env, "POLL_SEC") or _env(env, "LOOP_SECONDS") or DEFAULT_POLL_SEC),
        no_trade_timeout_seconds=_int(env, "NO_TRADE_TIMEOUT_SECONDS", DEFAULT_NO_TRADE_TIMEOUT),
        enable_websocket=_bool(env, "ENABLE_WEBSOCKET", True),
        log_level=(_env(env, "LOG_LEVEL", "INFO") or "INFO").upper(),
        log_dir=_env(env, "LOG_DIR", DEFAULT_LOG_DIR) or DEFAULT_LOG_DIR,
        state_path=_env(env, "STATE_PATH", DEFAULT_STATE_PATH) or DEFAULT_STATE_PATH,
        lock_path=_env(env, "LOCK_PATH", DEFAULT_LOCK_PATH) or DEFAULT_LOCK_PATH,
        candle_lookback_days=_int(
            env, "CANDLE_LOOKBACK_DAYS", _int(env, "HISTORY_DAYS", DEFAULT_LOOKBACK_DAYS)
        ),
        circuit_breaker_errors=_int(
            env, "CIRCUIT_BREAKER_ERRORS", DEFAULT_CIRCUIT_BREAKER_ERRORS
        ),
        max_drawdown_jpy=_dec(env, "MAX_DRAWDOWN_JPY", DEFAULT_MAX_DRAWDOWN_JPY),
    )
    if live_trading and not cfg.has_keys:
        raise ConfigError("LIVE_TRADING requires BITBANK_API_KEY and BITBANK_API_SECRET")
    if cfg.ma_period < 2 or cfg.short_ma_period < 2 or cfg.long_ma_period < 2:
        raise ConfigError("MA periods must be >= 2")
    if cfg.long_ma_period < cfg.short_ma_period:
        raise ConfigError("LONG_MA_PERIOD must be >= SHORT_MA_PERIOD")
    return cfg
