from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

from bitbank_bot.decimal_utils import d
from bitbank_bot.exceptions import ConfigError

CandleType = Literal[
    "1min",
    "5min",
    "15min",
    "30min",
    "1hour",
    "4hour",
    "8hour",
    "12hour",
    "1day",
    "1week",
    "1month",
]

TIMEFRAMES: tuple[CandleType, ...] = (
    "1min",
    "5min",
    "15min",
    "30min",
    "1hour",
    "4hour",
    "8hour",
    "12hour",
    "1day",
    "1week",
    "1month",
)

OrderSizeMode = Literal["min_unit", "max_available"]
MaKind = Literal["ema", "sma"]
OrderType = Literal["limit", "market"]


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value


def _bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _decimal(name: str, default: str) -> Decimal:
    return d(_env(name, default))


def _int(name: str, default: int) -> int:
    return int(_env(name, str(default)))


@dataclass(frozen=True)
class Settings:
    dry_run: bool
    api_key: str
    api_secret: str
    pair: str
    candle_type: CandleType
    ma_kind: MaKind
    ma_period: int
    ema_fast: int
    ema_slow: int
    slope_lookback: int
    flat_threshold: Decimal
    order_size_mode: OrderSizeMode
    min_btc: Decimal
    balance_usage_ratio: Decimal
    max_position_btc: Decimal
    max_daily_loss_jpy: Decimal
    max_loss_jpy: Decimal
    order_type: OrderType
    stale_ms: int
    loop_seconds: float
    log_level: str
    log_dir: Path
    state_dir: Path
    kill_switch: bool
    dashboard: bool
    public_base: str
    private_base: str
    ws_url: str
    min_hold_bars: int
    query_rps: float
    update_rps: float
    wiki_cross_rules: bool
    heartbeat_seconds: float
    no_trade_timeout_seconds: int

    @property
    def display_pair(self) -> str:
        return self.pair.replace("_", "/").upper()

    def require_keys_for_live(self) -> None:
        if self.dry_run:
            return
        if not self.api_key or not self.api_secret:
            raise ConfigError("Live trading requires BITBANK_API_KEY and BITBANK_API_SECRET")


def load_settings(env_file: str | Path | None = ".env") -> Settings:
    if env_file:
        path = Path(env_file)
        if path.is_file():
            load_dotenv(path, override=False)

    candle = _env("CANDLE_TYPE", "5min") or "5min"
    if candle not in TIMEFRAMES:
        raise ConfigError(f"Unsupported CANDLE_TYPE={candle}. Allowed: {', '.join(TIMEFRAMES)}")

    ma_kind = (_env("MA_KIND", "ema") or "ema").lower()
    if ma_kind not in {"ema", "sma"}:
        raise ConfigError("MA_KIND must be ema or sma")

    size_mode = (_env("ORDER_SIZE_MODE", "min_unit") or "min_unit").lower()
    if size_mode not in {"min_unit", "max_available"}:
        raise ConfigError("ORDER_SIZE_MODE must be min_unit or max_available")

    order_type = (_env("ORDER_TYPE", "limit") or "limit").lower()
    if order_type not in {"limit", "market"}:
        raise ConfigError("ORDER_TYPE must be limit or market")

    settings = Settings(
        dry_run=_bool("DRY_RUN", True),
        api_key=_env("BITBANK_API_KEY", "") or "",
        api_secret=_env("BITBANK_API_SECRET", "") or "",
        pair=(_env("PAIR", "btc_jpy") or "btc_jpy").lower(),
        candle_type=candle,  # type: ignore[arg-type]
        ma_kind=ma_kind,  # type: ignore[arg-type]
        ma_period=_int("MA_PERIOD", 20),
        ema_fast=_int("EMA_FAST", 20),
        ema_slow=_int("EMA_SLOW", 50),
        slope_lookback=_int("SLOPE_LOOKBACK", 3),
        flat_threshold=_decimal("FLAT_THRESHOLD", "0.0005"),
        order_size_mode=size_mode,  # type: ignore[arg-type]
        min_btc=_decimal("MIN_BTC", "0.0001"),
        balance_usage_ratio=_decimal("BALANCE_USAGE_RATIO", "0.99"),
        max_position_btc=_decimal("MAX_POSITION_BTC", "0.01"),
        max_daily_loss_jpy=_decimal("MAX_DAILY_LOSS_JPY", "50000"),
        max_loss_jpy=_decimal("MAX_LOSS_JPY", "100000"),
        order_type=order_type,  # type: ignore[arg-type]
        stale_ms=_int("STALE_MS", 15000),
        loop_seconds=float(_env("LOOP_SECONDS", "5") or "5"),
        log_level=(_env("LOG_LEVEL", "INFO") or "INFO").upper(),
        log_dir=Path(_env("LOG_DIR", "logs") or "logs"),
        state_dir=Path(_env("STATE_DIR", "state") or "state"),
        kill_switch=_bool("KILL_SWITCH", False),
        dashboard=_bool("DASHBOARD", True),
        public_base=_env("BITBANK_PUBLIC_BASE", "https://public.bitbank.cc") or "https://public.bitbank.cc",
        private_base=_env("BITBANK_PRIVATE_BASE", "https://api.bitbank.cc") or "https://api.bitbank.cc",
        ws_url=_env("BITBANK_WS_URL", "wss://stream.bitbank.cc/socket.io/?EIO=4&transport=websocket")
        or "wss://stream.bitbank.cc/socket.io/?EIO=4&transport=websocket",
        min_hold_bars=_int("MIN_HOLD_BARS", 1),
        query_rps=float(_env("QUERY_RPS", "8") or "8"),
        update_rps=float(_env("UPDATE_RPS", "4") or "4"),
        wiki_cross_rules=_bool("WIKI_CROSS_RULES", False),
        heartbeat_seconds=float(_env("HEARTBEAT_SECONDS", "10") or "10"),
        no_trade_timeout_seconds=_int("NO_TRADE_TIMEOUT_SECONDS", 900),
    )
    if settings.pair != "btc_jpy":
        raise ConfigError("This bot is scoped to Bitbank btc_jpy only")
    if settings.ma_period < 2 or settings.ema_fast < 2 or settings.ema_slow < settings.ema_fast:
        raise ConfigError("MA periods are invalid (need ema_slow >= ema_fast >= 2)")
    settings.require_keys_for_live()
    return settings
