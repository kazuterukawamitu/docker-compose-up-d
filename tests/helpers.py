from __future__ import annotations

from decimal import Decimal

from bitbank_bot.config import LIVE_CONFIRM_PHRASE, MODE_LIVE, Config
from bitbank_bot.money import D
from bitbank_bot.risk import RiskManager


def cfg(**overrides: object) -> Config:
    base = Config()
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def live_cfg(**overrides: object) -> Config:
    return cfg(
        dry_run=False,
        live_trading=True,
        trading_mode=MODE_LIVE,
        live_trading_confirm=LIVE_CONFIRM_PHRASE,
        api_key="k",
        api_secret="s",
        **overrides,
    )


def risk(c: Config | None = None) -> RiskManager:
    return RiskManager(c or cfg())


def dec(value: str | int) -> Decimal:
    return D(value)
