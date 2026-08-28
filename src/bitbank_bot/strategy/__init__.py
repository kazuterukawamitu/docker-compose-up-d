"""Strategy plugins."""

from bitbank_bot.strategy.base import CombinedStrategy, StrategyBase
from bitbank_bot.strategy.granville import GranvilleStrategy
from bitbank_bot.strategy.plugins import (
    AtrBreakoutStrategy,
    DeathCrossStrategy,
    GoldenCrossStrategy,
    MacdStrategy,
    RsiContrarianStrategy,
    build_strategies,
)

__all__ = [
    "AtrBreakoutStrategy",
    "CombinedStrategy",
    "DeathCrossStrategy",
    "GoldenCrossStrategy",
    "GranvilleStrategy",
    "MacdStrategy",
    "RsiContrarianStrategy",
    "StrategyBase",
    "build_strategies",
]
