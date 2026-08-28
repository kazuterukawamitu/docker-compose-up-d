from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from bitbank_bot.config import Settings


def make_settings(tmp_path: Path | None = None, **overrides: object) -> Settings:
    state_dir = (tmp_path or Path(".")) / "state"
    log_dir = (tmp_path or Path(".")) / "logs"
    values: dict[str, object] = dict(
        dry_run=True,
        api_key="",
        api_secret="",
        pair="btc_jpy",
        candle_type="5min",
        ma_kind="ema",
        ma_period=3,
        ema_fast=3,
        ema_slow=5,
        slope_lookback=1,
        flat_threshold=Decimal("0.0005"),
        order_size_mode="min_unit",
        min_btc=Decimal("0.0001"),
        balance_usage_ratio=Decimal("0.99"),
        max_position_btc=Decimal("1"),
        max_daily_loss_jpy=Decimal("50000"),
        max_loss_jpy=Decimal("100000"),
        order_type="limit",
        stale_ms=15_000,
        loop_seconds=5.0,
        log_level="INFO",
        log_dir=log_dir,
        state_dir=state_dir,
        kill_switch=False,
        dashboard=False,
        public_base="https://public.bitbank.cc",
        private_base="https://api.bitbank.cc",
        ws_url="wss://stream.bitbank.cc/socket.io/?EIO=4&transport=websocket",
        min_hold_bars=1,
        query_rps=8.0,
        update_rps=4.0,
    )
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]
