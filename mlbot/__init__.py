"""A small, self-contained Bitcoin moving-average trading backtester.

The strategy implemented here follows the moving-average rules described in the
repository ``README.md``: enter around moving-average crossovers with
trend-dependent take-profit targets, and exit on adverse crossovers or when a
take-profit target is reached.
"""

from .strategy import MovingAverageStrategy, StrategyParams
from .backtest import Backtester, BacktestResult
from .data import generate_price_series, load_price_series

__all__ = [
    "MovingAverageStrategy",
    "StrategyParams",
    "Backtester",
    "BacktestResult",
    "generate_price_series",
    "load_price_series",
]
