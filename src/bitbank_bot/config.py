"""Load settings from environment. Defaults keep the bot in dry-run."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from bitbank_bot.exceptions import ConfigError
from bitbank_bot.models import OrderType

SUPPORTED_PAIR = "btc_jpy"
SUPPORTED_CANDLES = frozenset(
    {
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
    }
)
MIN_ORDER_BTC = Decimal("0.0001")
PRICE_TICK = Decimal("1")
PUBLIC_REST = "https://public.bitbank.cc"
PRIVATE_REST = "https://api.bitbank.cc"
WS_URL = "wss://stream.bitbank.cc/socket.io/?EIO=4&transport=websocket"


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def _decimal(name: str, default: str) -> Decimal:
    raw = os.getenv(name, default)
    try:
        return Decimal(raw)
    except Exception as exc:
        raise ConfigError(f"{name} must be a decimal number") from exc


@dataclass(frozen=True, slots=True)
class Settings:
    pair: str
    dry_run: bool
    api_key: str
    api_secret: str
    candle_type: str
    loop_seconds: int
    ma_period: int
    ma_type: str
    fast_ma: int
    slow_ma: int
    trend_lookback: int
    trend_threshold: Decimal
    order_type: OrderType
    taker_fee_rate: Decimal
    safety_margin: Decimal
    max_position_btc: Decimal
    max_loss_fraction: Decimal
    stop_loss_pct: Decimal
    trailing_stop_pct: Decimal
    take_profit_cap_pct: Decimal
    compounding: bool
    strategies: tuple[str, ...]
    ml_enabled: bool
    ml_model_path: str
    log_dir: Path
    data_dir: Path
    lock_file: Path
    dashboard: bool
    log_level: str
    public_rest: str = PUBLIC_REST
    private_rest: str = PRIVATE_REST
    ws_url: str = WS_URL
    min_order_btc: Decimal = MIN_ORDER_BTC
    price_tick: Decimal = PRICE_TICK

    @property
    def pair_display(self) -> str:
        return "BTC/JPY"

    def require_live_keys(self) -> None:
        if self.dry_run:
            return
        if not self.api_key or not self.api_secret:
            raise ConfigError("BITBANK_API_KEY and BITBANK_API_SECRET are required when DRY_RUN=false")


def load_settings(env_file: str | Path | None = ".env") -> Settings:
    if env_file:
        path = Path(env_file)
        if path.exists():
            load_dotenv(path, override=False)
        else:
            load_dotenv(override=False)
    else:
        load_dotenv(override=False)

    pair = os.getenv("PAIR", SUPPORTED_PAIR).strip().lower()
    if pair != SUPPORTED_PAIR:
        raise ConfigError(f"Only {SUPPORTED_PAIR} is supported (got {pair!r})")

    candle_type = os.getenv("CANDLE_TYPE", "5min").strip()
    if candle_type not in SUPPORTED_CANDLES:
        raise ConfigError(f"Unsupported CANDLE_TYPE={candle_type}")

    ma_type = os.getenv("MA_TYPE", "sma").strip().lower()
    if ma_type not in {"sma", "ema"}:
        raise ConfigError("MA_TYPE must be sma or ema")

    order_raw = os.getenv("ORDER_TYPE", "limit").strip().lower()
    try:
        order_type = OrderType(order_raw)
    except ValueError as exc:
        raise ConfigError("ORDER_TYPE must be limit or market") from exc

    strategies = tuple(
        s.strip().lower()
        for s in os.getenv("STRATEGIES", "granville").split(",")
        if s.strip()
    )
    if not strategies:
        strategies = ("granville",)

    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    lock_file = Path(os.getenv("LOCK_FILE", str(data_dir / "bitbank_bot.lock")))

    settings = Settings(
        pair=pair,
        dry_run=_bool("DRY_RUN", True),
        api_key=os.getenv("BITBANK_API_KEY", "").strip(),
        api_secret=os.getenv("BITBANK_API_SECRET", "").strip(),
        candle_type=candle_type,
        loop_seconds=max(5, _int("LOOP_SECONDS", 30)),
        ma_period=max(2, _int("MA_PERIOD", 20)),
        ma_type=ma_type,
        fast_ma=max(2, _int("FAST_MA", 20)),
        slow_ma=max(3, _int("SLOW_MA", 50)),
        trend_lookback=max(2, _int("TREND_LOOKBACK", 5)),
        trend_threshold=_decimal("TREND_THRESHOLD", "0.001"),
        order_type=order_type,
        taker_fee_rate=_decimal("TAKER_FEE_RATE", "0.0012"),
        safety_margin=_decimal("SAFETY_MARGIN", "0.002"),
        max_position_btc=_decimal("MAX_POSITION_BTC", "0.05"),
        max_loss_fraction=_decimal("MAX_LOSS_FRACTION", "0.05"),
        stop_loss_pct=_decimal("STOP_LOSS_PCT", "0.03"),
        trailing_stop_pct=_decimal("TRAILING_STOP_PCT", "0.02"),
        take_profit_cap_pct=_decimal("TAKE_PROFIT_CAP_PCT", "0.10"),
        compounding=_bool("COMPOUNDING", True),
        strategies=strategies,
        ml_enabled=_bool("ML_ENABLED", False),
        ml_model_path=os.getenv("ML_MODEL_PATH", "").strip(),
        log_dir=log_dir,
        data_dir=data_dir,
        lock_file=lock_file,
        dashboard=_bool("DASHBOARD", True),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
    )
    if settings.fast_ma >= settings.slow_ma:
        raise ConfigError("FAST_MA must be smaller than SLOW_MA")
    settings.require_live_keys()
    return settings
