from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from bitbank_bot.config import Settings
from bitbank_bot.models import OrderType


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    values: dict[str, object] = {
        "pair": "btc_jpy",
        "dry_run": True,
        "api_key": "",
        "api_secret": "",
        "candle_type": "5min",
        "loop_seconds": 30,
        "ma_period": 3,
        "ma_type": "sma",
        "fast_ma": 3,
        "slow_ma": 5,
        "trend_lookback": 2,
        "trend_threshold": Decimal("0.001"),
        "order_type": OrderType.LIMIT,
        "taker_fee_rate": Decimal("0.0012"),
        "safety_margin": Decimal("0.002"),
        "max_position_btc": Decimal("1"),
        "max_loss_fraction": Decimal("0.50"),
        "stop_loss_pct": Decimal("0.03"),
        "trailing_stop_pct": Decimal("0.02"),
        "take_profit_cap_pct": Decimal("0.10"),
        "compounding": True,
        "strategies": ("granville",),
        "ml_enabled": False,
        "ml_model_path": "",
        "log_dir": tmp_path / "logs",
        "data_dir": tmp_path / "data",
        "lock_file": tmp_path / "data" / "bot.lock",
        "dashboard": False,
        "log_level": "INFO",
    }
    values.update(overrides)
    return Settings(**values)  # type: ignore[arg-type]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)
