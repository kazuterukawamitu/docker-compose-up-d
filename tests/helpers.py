from __future__ import annotations

from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.money import D
from bitbank_bot.risk import RiskManager


def cfg(**overrides: object) -> Config:
    base = Config()
    if overrides.get("dry_run") is False and overrides.get("live_trading") is True:
        if "live_trading_confirm" not in overrides:
            overrides = {**overrides, "live_trading_confirm": True}
        if "trading_mode" not in overrides:
            overrides = {**overrides, "trading_mode": "LIVE"}
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def risk(c: Config | None = None) -> RiskManager:
    return RiskManager(c or cfg())


def dec(value: str | int) -> Decimal:
    return D(value)
