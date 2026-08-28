"""Moving-average trading strategy.

The rules mirror the description in ``README.md``:

* Trade around a single simple moving average (SMA) of the close price.
* Enter (buy with all available cash) when price crosses **above** the SMA.
* Choose a take-profit target based on the SMA trend at entry time:
  a rising ("golden cross"-like) SMA aims higher (default +8%), a flat SMA
  aims lower (default +3%), and anything in between uses the default (+5%).
* Exit the whole position when the take-profit target is hit or when price
  crosses back **below** the SMA.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class StrategyParams:
    """Tunable parameters for :class:`MovingAverageStrategy`."""

    window: int = 50
    take_profit_uptrend: float = 0.08
    take_profit_default: float = 0.05
    take_profit_flat: float = 0.03
    #: Relative SMA slope (per bar) above which the trend is considered "rising".
    rising_slope_threshold: float = 0.001
    #: Relative SMA slope magnitude below which the trend is considered "flat".
    flat_slope_threshold: float = 0.0002


class MovingAverageStrategy:
    """Generate entry signals and take-profit targets from price data."""

    def __init__(self, params: StrategyParams | None = None) -> None:
        self.params = params or StrategyParams()

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Return a copy of ``df`` enriched with signal columns.

        Added columns: ``sma``, ``sma_slope`` (relative), ``cross_up``,
        ``cross_down`` and ``take_profit_pct`` (the target for a bar on which an
        entry is allowed, ``NaN`` otherwise).
        """
        p = self.params
        out = df.copy()

        close = out["close"]
        sma = close.rolling(p.window).mean()
        out["sma"] = sma

        # Relative slope keeps the thresholds price-independent.
        out["sma_slope"] = sma.diff() / sma

        prev_close = close.shift(1)
        prev_sma = sma.shift(1)
        out["cross_up"] = (prev_close <= prev_sma) & (close > sma)
        out["cross_down"] = (prev_close >= prev_sma) & (close < sma)

        slope = out["sma_slope"]
        tp = np.where(
            slope >= p.rising_slope_threshold,
            p.take_profit_uptrend,
            np.where(
                slope.abs() <= p.flat_slope_threshold,
                p.take_profit_flat,
                p.take_profit_default,
            ),
        )
        out["take_profit_pct"] = np.where(out["cross_up"], tp, np.nan)

        return out
