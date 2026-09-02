from __future__ import annotations

from decimal import Decimal

from bitbank_bot.config import Config
from bitbank_bot.money import D
from bitbank_bot.risk import RiskManager


def cfg(**overrides: object) -> Config:
    base = Config()
    for key, value in overrides.items():
        setattr(base, key, value)
    return base


def risk(c: Config | None = None) -> RiskManager:
    return RiskManager(c or cfg())


def dec(value: str | int) -> Decimal:
    return D(value)
